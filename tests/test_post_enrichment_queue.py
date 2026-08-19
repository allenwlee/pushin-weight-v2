from __future__ import annotations

from datetime import timedelta

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

    for index in range(21):
        _state(f"claim-{index:02d}")
    cfg = _cfg().harvest.enrichment

    first = _claim_enrichment_states(cfg=cfg, run_id="run-1")
    second = _claim_enrichment_states(cfg=cfg, run_id="run-2")

    assert len(first.states) == 20
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
    older_due = [_state(f"older-due-{index:02d}") for index in range(20)]
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
    assert len(classified_ids) == 20
    assert counters["n_enrichment_claimed"] == 20
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
        == _cfg().harvest.enrichment.attempt_budget_seconds
    )
    assert counters["n_enrichment_claimed"] == 0
    assert counters["n_enrichment_deferred"] == 1
    assert state.translation_attempts == 0
    assert state.classification_attempts == 0
    assert state.claim_run_id == ""
