from __future__ import annotations

from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from x_monitor.config import Config

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def _cfg():
    return Config(enabled_models=["deepseek"], daily_ceiling=100)


def _state(tweet_id: str):
    from core.models import Post, PostEnrichmentState

    post = Post.objects.create(tweet_id=tweet_id, text="DeepSeek release")
    return PostEnrichmentState.objects.create(post=post)


def test_claims_are_bounded_and_active_claims_are_not_double_owned():
    from monitor.cycle import _claim_enrichment_states

    for index in range(51):
        _state(f"claim-{index:02d}")
    cfg = _cfg().harvest.enrichment

    first = _claim_enrichment_states(cfg=cfg, run_id="run-1")
    second = _claim_enrichment_states(cfg=cfg, run_id="run-2")

    assert len(first.states) == 50
    assert len(second.states) == 1
    assert {state.claim_run_id for state in first.states} == {"run-1"}
    assert {state.claim_run_id for state in second.states} == {"run-2"}
    assert all(state.translation_attempts == 1 for state in first.states)
    assert all(state.classification_attempts == 1 for state in first.states)


def test_expired_claim_is_recoverable_by_the_next_cycle():
    from monitor.cycle import _claim_enrichment_states

    state = _state("expired-claim")
    state.claim_owner = "dead-worker"
    state.claim_run_id = "old-run"
    state.claimed_at = timezone.now() - timedelta(minutes=10)
    state.claim_expires_at = timezone.now() - timedelta(minutes=5)
    state.save()

    batch = _claim_enrichment_states(
        cfg=_cfg().harvest.enrichment,
        run_id="replacement-run",
    )

    assert [claimed.pk for claimed in batch.states] == [state.pk]
    assert batch.states[0].claim_run_id == "replacement-run"


def test_attempt_and_age_exhaustion_transition_to_failed_without_claiming():
    from core.models import PostEnrichmentState
    from monitor.cycle import _claim_enrichment_states

    exhausted = _state("attempts-exhausted")
    exhausted.translation_attempts = 8
    exhausted.classification_attempts = 8
    exhausted.save()
    aged = _state("age-exhausted")
    PostEnrichmentState.objects.filter(pk=aged.pk).update(
        created_at=timezone.now() - timedelta(hours=25)
    )

    batch = _claim_enrichment_states(
        cfg=_cfg().harvest.enrichment,
        run_id="run-quarantine",
    )

    assert batch.states == ()
    assert batch.quarantined == 2
    exhausted.refresh_from_db()
    aged.refresh_from_db()
    assert exhausted.translation_status == PostEnrichmentState.Status.FAILED
    assert exhausted.classification_status == PostEnrichmentState.Status.FAILED
    assert exhausted.translation_error_code == "attempts_exhausted"
    assert aged.classification_error_code == "age_exhausted"


def test_post_fetch_reaches_classifier_when_expired_debt_fills_claim_window(
    monkeypatch,
):
    """Expired debt must not consume every bounded production claim slot."""
    from core.models import PostEnrichmentState
    from monitor.cycle import CycleRunner
    from x_monitor import attribution, reattribute, translator

    expired = [_state(f"expired-debt-{index:02d}") for index in range(25)]
    PostEnrichmentState.objects.filter(pk__in=[state.pk for state in expired]).update(
        created_at=timezone.now() - timedelta(hours=25)
    )
    older_due = [_state(f"older-due-{index:02d}") for index in range(50)]
    PostEnrichmentState.objects.filter(pk__in=[state.pk for state in older_due]).update(
        created_at=timezone.now() - timedelta(hours=23)
    )
    fresh = _state("fresh-after-expired-debt")

    client = object()
    classified_ids: list[str] = []
    monkeypatch.setattr(
        reattribute,
        "build_translator_client_from_env",
        lambda cfg: client,
    )
    monkeypatch.setattr(
        reattribute,
        "build_anthropic_client_from_env",
        lambda cfg: client,
    )
    monkeypatch.setattr(
        translator,
        "translate_batch_pragmatics",
        lambda tweets, locales, client, **kwargs: [
            {
                "tweet_id": tweet["tweet_id"],
                "text_en": tweet["text"],
                "text_zh_cn": "深度求索发布",
                "en_equivalent": "The release signals another competitive step.",
                "cn_equivalent": "这次发布表明竞争又向前推进了一步。",
                "lang_detected": "en",
            }
            for tweet in tweets
        ],
    )

    def classify(tweets, brands, client, **kwargs):
        classified_ids.extend(tweet["tweet_id"] for tweet in tweets)
        return [{"by_brand": {}, "unsanctioned_flags": []} for _tweet in tweets]

    monkeypatch.setattr(attribution, "classify_batch_pragmatics_full", classify)

    counters = CycleRunner(cfg=_cfg())._run_post_fetch(
        [],
        run_id="run-after-expired-debt",
    )

    fresh.refresh_from_db()
    assert fresh.pk in classified_ids
    assert len(classified_ids) == 50
    assert counters["n_enrichment_claimed"] == 50
    assert counters["n_enrichment_quarantined"] == 25
    assert fresh.translation_status == PostEnrichmentState.Status.SUCCEEDED
    assert fresh.classification_status == PostEnrichmentState.Status.SUCCEEDED


def test_releasing_a_claim_preserves_stage_status_and_clears_lease():
    from core.models import PostEnrichmentState
    from monitor.cycle import _claim_enrichment_states, _release_enrichment_claim

    state = _state("release-claim")
    batch = _claim_enrichment_states(
        cfg=_cfg().harvest.enrichment,
        run_id="run-release",
    )
    claimed = batch.states[0]
    claimed.translation_status = PostEnrichmentState.Status.SUCCEEDED
    claimed.translation_error_code = ""
    claimed.save(update_fields=["translation_status", "translation_error_code"])

    _release_enrichment_claim(claimed.pk, run_id="run-release")

    state.refresh_from_db()
    assert state.translation_status == PostEnrichmentState.Status.SUCCEEDED
    assert state.claim_owner == ""
    assert state.claim_run_id == ""
    assert state.claimed_at is None
    assert state.claim_expires_at is None


def test_deadline_defers_work_without_claiming_or_spending_an_attempt():
    from monitor.cycle import CycleRunner

    class ExhaustedDeadline:
        requested_seconds = None

        def can_start(self, seconds):
            self.requested_seconds = seconds
            return False

    state = _state("deadline-deferred")
    deadline = ExhaustedDeadline()
    runner = CycleRunner(cfg=_cfg())

    counters = runner._run_post_fetch([], run_id="deadline-run", deadline=deadline)

    state.refresh_from_db()
    assert (
        deadline.requested_seconds
        == 2 * _cfg().harvest.enrichment.attempt_budget_seconds
    )
    assert counters["n_enrichment_claimed"] == 0
    assert counters["n_enrichment_deferred"] == 1
    assert state.translation_attempts == 0
    assert state.classification_attempts == 0
    assert state.claim_run_id == ""


def test_claim_prefers_the_pre_cycle_cohort_over_current_cycle_inserts():
    from core.models import PostEnrichmentState
    from monitor.cycle import _claim_enrichment_states

    cutoff = timezone.now()
    previous = [_state(f"previous-{index}") for index in range(2)]
    current = [_state(f"current-{index}") for index in range(2)]
    PostEnrichmentState.objects.filter(pk=previous[0].pk).update(
        created_at=cutoff - timedelta(minutes=2),
        translation_attempts=1,
    )
    PostEnrichmentState.objects.filter(pk=previous[1].pk).update(
        created_at=cutoff - timedelta(minutes=1)
    )
    PostEnrichmentState.objects.filter(pk=current[0].pk).update(
        created_at=cutoff + timedelta(seconds=1)
    )
    PostEnrichmentState.objects.filter(pk=current[1].pk).update(
        created_at=cutoff + timedelta(seconds=2)
    )
    cfg = _cfg().harvest.enrichment.model_copy(update={"claim_per_cycle": 2})

    batch = _claim_enrichment_states(
        cfg=cfg,
        run_id="pre-cycle-first",
        now=cutoff + timedelta(seconds=3),
        prefer_created_before=cutoff,
    )

    assert [state.pk for state in batch.states] == [previous[0].pk, previous[1].pk]


def test_claim_preserves_full_latest_50_against_37_current_cycle_inserts():
    from core.models import PostEnrichmentState
    from monitor.cycle import _claim_enrichment_states

    cutoff = timezone.now().astimezone(ZoneInfo("Asia/Tokyo"))
    retained = [_state(f"retained-{index:02d}") for index in range(50)]
    current = [_state(f"new-arrival-{index:02d}") for index in range(37)]
    PostEnrichmentState.objects.filter(pk__in=[state.pk for state in retained]).update(
        created_at=cutoff - timedelta(minutes=30)
    )
    PostEnrichmentState.objects.filter(pk__in=[state.pk for state in current]).update(
        created_at=cutoff + timedelta(minutes=1)
    )

    batch = _claim_enrichment_states(
        cfg=_cfg().harvest.enrichment,
        run_id="production-displacement-shape",
        now=cutoff + timedelta(minutes=2),
        prefer_created_before=cutoff,
    )

    assert len(batch.states) == 50
    assert {state.pk for state in batch.states} == {state.pk for state in retained}


def test_translation_timeout_does_not_consume_classifier_stage_budget(monkeypatch):
    from core.models import PostEnrichmentState
    from monitor.cycle import CycleRunner
    from x_monitor import attribution, reattribute, translator

    state = _state("separate-stage-deadlines")
    client = object()
    clock = [0.0]
    monkeypatch.setattr(reattribute, "build_translator_client_from_env", lambda cfg: client)
    monkeypatch.setattr(reattribute, "build_anthropic_client_from_env", lambda cfg: client)

    def translate(tweets, locales, client, **kwargs):
        assert kwargs["deadline"].remaining() == 300
        clock[0] = 300.0
        return [
            {
                "tweet_id": tweet["tweet_id"],
                "text_en": tweet["text"],
                "text_zh_cn": "深度求索发布",
                "en_equivalent": "The release is strategically relevant.",
                "cn_equivalent": "这次发布具有战略意义。",
                "lang_detected": "en",
            }
            for tweet in tweets
        ]

    def classify(tweets, brands, client, **kwargs):
        assert kwargs["deadline"].remaining() == 300
        return [{"by_brand": {}, "unsanctioned_flags": []} for _tweet in tweets]

    monkeypatch.setattr(translator, "translate_batch_pragmatics", translate)
    monkeypatch.setattr(attribution, "classify_batch_pragmatics_full", classify)

    CycleRunner(cfg=_cfg(), _monotonic=lambda: clock[0])._run_post_fetch(
        [], run_id="separate-stage-deadlines"
    )

    state.refresh_from_db()
    assert state.translation_status == PostEnrichmentState.Status.SUCCEEDED
    assert state.classification_status == PostEnrichmentState.Status.SUCCEEDED


def _complete_translation(tweet_id: str, source: str) -> dict:
    return {
        "tweet_id": tweet_id,
        "text_en": None,
        "text_zh_cn": "深度求索发布了更新",
        "en_equivalent": "DeepSeek has a new release worth evaluating.",
        "cn_equivalent": "DeepSeek 又上新了，值得关注。",
        "lang_detected": "en",
    }


def test_recent_incomplete_translation_success_is_reopened_without_touching_classification():
    from core.models import Post, PostEnrichmentState
    from monitor.cycle import _requeue_recent_incomplete_translations

    now = timezone.now()
    incomplete = _state("recent-false-success")
    incomplete.translation_status = PostEnrichmentState.Status.SUCCEEDED
    incomplete.classification_status = PostEnrichmentState.Status.SUCCEEDED
    incomplete.save()

    complete_post = Post.objects.create(
        tweet_id="recent-complete",
        text="DeepSeek shipped",
        text_en="DeepSeek shipped",
        text_zh_cn="DeepSeek 发布了更新",
        commentary_en="DeepSeek has a release worth evaluating.",
        commentary_zh_cn="DeepSeek 又上新了，值得关注。",
        lang_detected="en",
    )
    complete = PostEnrichmentState.objects.create(
        post=complete_post,
        translation_status=PostEnrichmentState.Status.SUCCEEDED,
        classification_status=PostEnrichmentState.Status.SUCCEEDED,
    )

    invalid_lang_post = Post.objects.create(
        tweet_id="recent-invalid-lang",
        text="DeepSeek shipped",
        text_en="DeepSeek shipped",
        text_zh_cn="DeepSeek 发布了更新",
        commentary_en="DeepSeek has a release worth evaluating.",
        commentary_zh_cn="DeepSeek 又上新了，值得关注。",
        lang_detected="english",
    )
    invalid_lang = PostEnrichmentState.objects.create(
        post=invalid_lang_post,
        translation_status=PostEnrichmentState.Status.SUCCEEDED,
        classification_status=PostEnrichmentState.Status.SUCCEEDED,
    )

    copied_commentary_post = Post.objects.create(
        tweet_id="recent-copied-commentary",
        text="DeepSeek shipped",
        text_en="DeepSeek shipped",
        text_zh_cn="DeepSeek 发布了更新",
        commentary_en="DeepSeek 发布了更新",
        commentary_zh_cn="DeepSeek 又上新了，值得关注。",
        lang_detected="en",
    )
    copied_commentary = PostEnrichmentState.objects.create(
        post=copied_commentary_post,
        translation_status=PostEnrichmentState.Status.SUCCEEDED,
        classification_status=PostEnrichmentState.Status.SUCCEEDED,
    )

    aged = _state("aged-false-success")
    aged.translation_status = PostEnrichmentState.Status.SUCCEEDED
    aged.classification_status = PostEnrichmentState.Status.SUCCEEDED
    aged.save()
    PostEnrichmentState.objects.filter(pk=aged.pk).update(
        created_at=now - timedelta(hours=25)
    )

    reopened = _requeue_recent_incomplete_translations(
        cfg=_cfg().harvest.enrichment,
        now=now,
    )

    incomplete.refresh_from_db()
    complete.refresh_from_db()
    invalid_lang.refresh_from_db()
    copied_commentary.refresh_from_db()
    aged.refresh_from_db()
    assert reopened == 3
    assert incomplete.translation_status == PostEnrichmentState.Status.PENDING
    assert incomplete.translation_error_code == "translation_output_incomplete"
    assert incomplete.classification_status == PostEnrichmentState.Status.SUCCEEDED
    assert complete.translation_status == PostEnrichmentState.Status.SUCCEEDED
    assert invalid_lang.translation_status == PostEnrichmentState.Status.PENDING
    assert copied_commentary.translation_status == PostEnrichmentState.Status.PENDING
    assert aged.translation_status == PostEnrichmentState.Status.SUCCEEDED


def test_translation_only_debt_does_not_rerun_classifier(monkeypatch):
    from core.models import PostEnrichmentState
    from monitor.cycle import CycleRunner
    from x_monitor import attribution, reattribute, translator

    state = _state("translation-only")
    state.classification_status = PostEnrichmentState.Status.SUCCEEDED
    state.save()
    client = object()
    classifier_calls: list[list[dict]] = []
    monkeypatch.setattr(reattribute, "build_translator_client_from_env", lambda cfg: client)
    monkeypatch.setattr(reattribute, "build_anthropic_client_from_env", lambda cfg: client)
    monkeypatch.setattr(
        translator,
        "translate_batch_pragmatics",
        lambda tweets, locales, client, **kwargs: [
            _complete_translation(tweet["tweet_id"], tweet["text"])
            for tweet in tweets
        ],
    )

    def classify(tweets, brands, client, **kwargs):
        classifier_calls.append(tweets)
        return []

    monkeypatch.setattr(attribution, "classify_batch_pragmatics_full", classify)

    CycleRunner(cfg=_cfg())._run_post_fetch([], run_id="translation-only-run")

    state.refresh_from_db()
    state.post.refresh_from_db()
    assert state.translation_status == PostEnrichmentState.Status.SUCCEEDED
    assert state.classification_status == PostEnrichmentState.Status.SUCCEEDED
    assert state.post.commentary_en
    assert state.post.commentary_zh_cn
    assert classifier_calls == []


def test_classification_only_debt_does_not_rerun_translator(monkeypatch):
    from core.models import PostEnrichmentState
    from monitor.cycle import CycleRunner
    from x_monitor import attribution, reattribute, translator

    state = _state("classification-only")
    state.translation_status = PostEnrichmentState.Status.SUCCEEDED
    state.post.text_en = state.post.text
    state.post.text_zh_cn = "深度求索发布了更新"
    state.post.commentary_en = "DeepSeek has a release worth evaluating."
    state.post.commentary_zh_cn = "DeepSeek 又上新了，值得关注。"
    state.post.lang_detected = "en"
    state.post.save()
    state.save()
    client = object()
    translator_calls: list[list[dict]] = []
    monkeypatch.setattr(reattribute, "build_translator_client_from_env", lambda cfg: client)
    monkeypatch.setattr(reattribute, "build_anthropic_client_from_env", lambda cfg: client)

    def translate(tweets, locales, client, **kwargs):
        translator_calls.append(tweets)
        return []

    monkeypatch.setattr(translator, "translate_batch_pragmatics", translate)
    monkeypatch.setattr(
        attribution,
        "classify_batch_pragmatics_full",
        lambda tweets, brands, client, **kwargs: [
            {"by_brand": {}, "unsanctioned_flags": []} for _tweet in tweets
        ],
    )

    CycleRunner(cfg=_cfg())._run_post_fetch([], run_id="classification-only-run")

    state.refresh_from_db()
    assert state.translation_status == PostEnrichmentState.Status.SUCCEEDED
    assert state.classification_status == PostEnrichmentState.Status.SUCCEEDED
    assert translator_calls == []


def test_failed_translation_does_not_erase_previously_valid_fields(monkeypatch):
    from core.models import PostEnrichmentState
    from monitor.cycle import CycleRunner
    from x_monitor import attribution, reattribute, translator

    state = _state("preserve-partial-output")
    state.classification_status = PostEnrichmentState.Status.SUCCEEDED
    state.post.text_zh_cn = "已有中文翻译"
    state.post.commentary_zh_cn = "已有中文评论"
    state.post.save()
    state.save()
    client = object()
    monkeypatch.setattr(reattribute, "build_translator_client_from_env", lambda cfg: client)
    monkeypatch.setattr(reattribute, "build_anthropic_client_from_env", lambda cfg: client)
    monkeypatch.setattr(
        translator,
        "translate_batch_pragmatics",
        lambda tweets, locales, client, **kwargs: [
            {
                "tweet_id": tweets[0]["tweet_id"],
                "text_en": None,
                "text_zh_cn": None,
                "en_equivalent": None,
                "cn_equivalent": None,
                "lang_detected": None,
                "translation_failed": True,
            }
        ],
    )
    monkeypatch.setattr(
        attribution,
        "classify_batch_pragmatics_full",
        lambda *args, **kwargs: pytest.fail("classification should not rerun"),
    )

    CycleRunner(cfg=_cfg())._run_post_fetch([], run_id="preserve-output-run")

    state.refresh_from_db()
    state.post.refresh_from_db()
    assert state.translation_status == PostEnrichmentState.Status.PENDING
    assert state.translation_error_code == "translation_incomplete"
    assert state.post.text_zh_cn == "已有中文翻译"
    assert state.post.commentary_zh_cn == "已有中文评论"


def test_copied_commentary_cannot_mark_translation_succeeded(monkeypatch):
    from core.models import PostEnrichmentState
    from monitor.cycle import CycleRunner
    from x_monitor import attribution, reattribute, translator

    state = _state("copied-commentary-boundary")
    state.classification_status = PostEnrichmentState.Status.SUCCEEDED
    state.save()
    client = object()
    monkeypatch.setattr(reattribute, "build_translator_client_from_env", lambda cfg: client)
    monkeypatch.setattr(reattribute, "build_anthropic_client_from_env", lambda cfg: client)
    monkeypatch.setattr(
        translator,
        "translate_batch_pragmatics",
        lambda tweets, locales, client, **kwargs: [
            {
                "tweet_id": tweets[0]["tweet_id"],
                "text_en": tweets[0]["text"],
                "text_zh_cn": "深度求索发布了更新",
                "en_equivalent": "深度求索发布了更新",
                "cn_equivalent": "这次发布值得继续关注。",
                "lang_detected": "en",
            }
        ],
    )
    monkeypatch.setattr(
        attribution,
        "classify_batch_pragmatics_full",
        lambda *args, **kwargs: pytest.fail("classification should not rerun"),
    )

    CycleRunner(cfg=_cfg())._run_post_fetch([], run_id="copied-commentary-run")

    state.refresh_from_db()
    state.post.refresh_from_db()
    assert state.translation_status == PostEnrichmentState.Status.PENDING
    assert state.translation_error_code == "translation_incomplete"
    assert state.post.commentary_en is None


def test_zh_hans_source_is_persisted_as_text_zh_cn(monkeypatch):
    from core.models import PostEnrichmentState
    from monitor.cycle import CycleRunner
    from x_monitor import attribution, reattribute, translator

    state = _state("zh-hans-source")
    state.post.text = "深度求索发布了更新"
    state.post.save()
    state.classification_status = PostEnrichmentState.Status.SUCCEEDED
    state.save()
    client = object()
    monkeypatch.setattr(reattribute, "build_translator_client_from_env", lambda cfg: client)
    monkeypatch.setattr(reattribute, "build_anthropic_client_from_env", lambda cfg: client)
    monkeypatch.setattr(
        translator,
        "translate_batch_pragmatics",
        lambda tweets, locales, client, **kwargs: [
            {
                "tweet_id": tweets[0]["tweet_id"],
                "text_en": "DeepSeek shipped an update",
                "text_zh_cn": None,
                "en_equivalent": "DeepSeek has a new release worth evaluating.",
                "cn_equivalent": "DeepSeek 又上新了，值得关注。",
                "lang_detected": "zh-Hans",
            }
        ],
    )
    monkeypatch.setattr(
        attribution,
        "classify_batch_pragmatics_full",
        lambda *args, **kwargs: pytest.fail("classification should not rerun"),
    )

    CycleRunner(cfg=_cfg())._run_post_fetch([], run_id="zh-hans-source-run")

    state.refresh_from_db()
    state.post.refresh_from_db()
    assert state.translation_status == PostEnrichmentState.Status.SUCCEEDED
    assert state.post.text_zh_cn == state.post.text


def test_classifier_deadline_preserves_flags_and_keeps_stage_pending(monkeypatch):
    from core.models import PostEnrichmentState, PostUnsanctionedFlag
    from monitor.cycle import CycleRunner
    from x_monitor import attribution, reattribute, translator

    state = _state("classifier-deadline")
    state.translation_status = PostEnrichmentState.Status.SUCCEEDED
    state.post.text_en = state.post.text
    state.post.text_zh_cn = "深度求索发布了更新"
    state.post.commentary_en = "DeepSeek has a release worth evaluating."
    state.post.commentary_zh_cn = "DeepSeek 又上新了，值得关注。"
    state.post.lang_detected = "en"
    state.post.save()
    state.save()
    PostUnsanctionedFlag.objects.create(
        post=state.post,
        flags='["market_manipulation"]',
        flag_set=["market_manipulation"],
    )
    client = object()
    monkeypatch.setattr(reattribute, "build_translator_client_from_env", lambda cfg: client)
    monkeypatch.setattr(reattribute, "build_anthropic_client_from_env", lambda cfg: client)
    monkeypatch.setattr(
        translator,
        "translate_batch_pragmatics",
        lambda *args, **kwargs: pytest.fail("translation should not rerun"),
    )
    monkeypatch.setattr(
        attribution,
        "classify_batch_pragmatics_full",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            TimeoutError("enrichment_attempt_deadline_exhausted")
        ),
    )

    CycleRunner(cfg=_cfg())._run_post_fetch([], run_id="classifier-deadline-run")

    state.refresh_from_db()
    assert state.classification_status == PostEnrichmentState.Status.PENDING
    assert state.classification_error_code == "classifier_exception"
    assert PostUnsanctionedFlag.objects.get(post=state.post).flag_set == [
        "market_manipulation"
    ]
