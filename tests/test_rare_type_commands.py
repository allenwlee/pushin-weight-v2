from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone as django_timezone

from core.models import (
    Brand,
    ModelRelease,
    Post,
    PostBrand,
    PostBrandSignal,
    PostEnrichmentState,
    PostTypeKey,
    RareTypeDecision,
    RareTypeDecisionAttempt,
    RareTypeDecisionProcessingCycle,
    RareTypeSearchDailyBudget,
    RareTypeSearchHit,
    SearchQuery,
    SentimentKey,
    TargetedExtractionState,
)
from core.rare_type_search import (
    mark_search_dispatched,
    persist_hit_batch,
    reserve_search_run,
)
from monitor.cycle import CycleRunner
from x_monitor.config import load_config

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
NOW = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)


def _hits(*tweet_ids: str) -> list[RareTypeSearchHit]:
    query = SearchQuery.objects.create(
        query_id=f"command-{SearchQuery.objects.count()}"
    )
    slot = NOW + timedelta(minutes=15 * SearchQuery.objects.count())
    reservation = reserve_search_run(
        lane="rare_types",
        slot_start=slot,
        source_query=query,
        query_string="(released OR joined) min_faves:0",
        query_hash="c" * 64,
        query_version="rare-v3",
        environment="test",
        release_sha="test-sha",
        now=slot,
    )
    assert reservation.run is not None
    mark_search_dispatched(reservation.run.pk, now=slot)
    return persist_hit_batch(
        reservation.run.pk,
        [
            {
                "id": tweet_id,
                "text": f"DeepSeek released {tweet_id}",
                "created_at": slot.isoformat(),
                "author_id": f"author-{tweet_id}",
                "author_handle": "deepseek_ai",
            }
            for tweet_id in tweet_ids
        ],
        now=slot,
        raw_count=len(tweet_ids),
        normalized_count=len(tweet_ids),
    )


def _mark_kept_and_link(hit: RareTypeSearchHit, post: Post) -> None:
    hit.gate_state = RareTypeSearchHit.GateState.KEPT
    hit.gate_completed_at = NOW
    hit.post = post
    hit.post_persisted_at = NOW
    hit.save(
        update_fields=[
            "gate_state",
            "gate_completed_at",
            "post",
            "post_persisted_at",
            "updated_at",
        ]
    )


def _classification_results(tweets):
    return [
        {
            "by_brand": {
                brand_id: {
                    "outcome": "classified",
                    "post_types": ["releases_updates"],
                    "product_labels": [],
                    "sentiment": "neutral",
                    "china_nationalism": None,
                    "us_nationalism": None,
                }
                for brand_id in tweet.get("brand_ids", [])
            },
            "unsanctioned_flags": [],
            "valid": bool(tweet.get("brand_ids")),
        }
        for tweet in tweets
    ]


def _patch_replay_preflight(monkeypatch) -> None:
    monkeypatch.setattr("monitor.cycle._resolve_enabled_models", lambda *_a: [])
    monkeypatch.setattr("monitor.cycle._build_brand_index", lambda *_a: (None, {}))
    monkeypatch.setattr("monitor.cycle._load_brand_search_terms", dict)
    monkeypatch.setattr(
        "x_monitor.reattribute.build_relevancy_client_from_env", lambda _cfg: None
    )
    monkeypatch.setattr(
        "x_monitor.apify.TwitterApiClient.from_env",
        classmethod(
            lambda cls, *_a, **_kw: pytest.fail(
                "saved-hit replay must not construct a TwitterAPI client"
            )
        ),
    )
    monkeypatch.setattr(
        "core.product_verification.drain_pending_verifications",
        lambda **_kw: pytest.fail("saved-hit replay must not drain Hugging Face work"),
    )


def test_replay_dry_run_reads_ids_but_makes_no_writes_or_provider_construction(
    monkeypatch,
):
    hit = _hits("dry-run-only")[0]
    monkeypatch.setattr(
        "monitor.cycle.CycleRunner",
        lambda **_kw: pytest.fail("dry-run must not construct the pipeline"),
    )
    output = StringIO()

    call_command("replay_rare_type_hits", hit.pk, "--json", stdout=output)

    assert json.loads(output.getvalue()) == {
        "schema_version": "rare-type-replay/v1",
        "mode": "dry-run",
        "hit_ids": [hit.pk],
        "writes": 0,
        "provider_calls": 0,
    }
    hit.refresh_from_db()
    assert hit.gate_state == RareTypeSearchHit.GateState.DECISION_PENDING
    assert RareTypeDecision.objects.count() == 0


def test_status_reports_query_cost_gate_latency_and_post_pipeline_without_text():
    hit = _hits("status-evidence")[0]
    hit.run.refresh_from_db()
    run_output = StringIO()

    call_command(
        "rare_type_search_status", "--run-id", hit.run_id, "--json", stdout=run_output
    )

    document = json.loads(run_output.getvalue())
    assert document["schema_version"] == "rare-type-status/v1"
    assert document["query"]["rendered"] == "(released OR joined) min_faves:0"
    assert document["cost"]["twitterapi"] == {
        "reserved_credits": 300,
        "estimated_credits": 15,
        "confirmed_credits": None,
    }
    assert document["cost"]["jev"] == {
        "reserved_usd": "0E-9",
        "accounted_usd": "0E-9",
        "confirmed_usd": "0E-9",
    }
    assert document["cost"]["jev_decision_attempts"] == {
        "scope": "unique_decisions_referenced_by_run_hits",
        "billing_attribution": "decision_attempt_evidence_not_search_run_billing",
        "decision_count": 0,
        "reused_decision_count": 0,
        "attempt_count": 0,
        "settled_attempt_count": 0,
        "unknown_usage_attempt_count": 0,
        "in_flight_attempt_count": 0,
        "reservation_ceiling_usd": "0E-9",
        "accounted_usd": "0E-9",
        "estimated_unconfirmed_usd": "0E-9",
        "confirmed_usd": None,
        "confirmation_status": "not_applicable",
    }
    assert document["counts"]["raw"] == 1
    assert document["counts"]["normalized"] == 1
    assert document["counts"]["persisted_posts"] == 0
    assert document["counts"]["classified_hits"] == 0
    assert document["counts"]["extracted_hits"] == 0
    assert document["counts"]["visible_hits"] == 0
    assert document["hits"][0]["gate"]["state"] == "decision_pending"
    assert document["hits"][0]["classification"]["status"] is None
    assert "DeepSeek released" not in run_output.getvalue()


def test_status_attributes_attempt_evidence_without_calling_it_run_billing():
    hit = _hits("status-funded")[0]
    other_hit = _hits("status-prior-source")[0]
    decision = RareTypeDecision.objects.create(
        provider_post_id=hit.provider_post_id,
        content_hash="d" * 64,
        model="jev-1.13.0",
        question_version="jev-q-v1",
        threshold_version="jev-threshold-v1",
    )
    RareTypeSearchHit.objects.filter(pk__in=[hit.pk, other_hit.pk]).update(
        decision=decision
    )
    budget = RareTypeSearchDailyBudget.objects.create(
        usage_date=NOW.date(), lane="rare_types-attempt-status"
    )
    cycle = RareTypeDecisionProcessingCycle.objects.create(
        lane="rare_types-attempt-status",
        environment="normal",
        slot_start=NOW,
        usage_date=NOW.date(),
        daily_budget=budget,
        allocation_started_at=NOW,
        allocation_deadline=NOW + timedelta(minutes=1),
    )
    RareTypeDecisionAttempt.objects.create(
        decision=decision,
        processing_cycle=cycle,
        fence=1,
        state=RareTypeDecisionAttempt.State.SETTLED,
        reserved_usd=Decimal("0.002000000"),
        accounted_usd=Decimal("0.000050400"),
        confirmed_usd=None,
        reserved_at=NOW,
        sent_at=NOW,
        settled_at=NOW,
    )
    RareTypeDecisionAttempt.objects.create(
        decision=decision,
        processing_cycle=cycle,
        fence=2,
        state=RareTypeDecisionAttempt.State.SETTLED,
        reserved_usd=Decimal("0.002000000"),
        accounted_usd=Decimal("0.000060000"),
        confirmed_usd=Decimal("0.000060000"),
        reserved_at=NOW,
        sent_at=NOW,
        settled_at=NOW,
    )
    RareTypeDecisionAttempt.objects.create(
        decision=decision,
        processing_cycle=cycle,
        fence=3,
        state=RareTypeDecisionAttempt.State.RETAINED,
        reserved_usd=Decimal("0.002000000"),
        reserved_at=NOW,
        sent_at=NOW,
    )

    output = StringIO()
    call_command("rare_type_search_status", "--run-id", hit.run_id, stdout=output)

    cost = json.loads(output.getvalue())["cost"]
    assert cost["jev"] == {
        "reserved_usd": "0E-9",
        "accounted_usd": "0E-9",
        "confirmed_usd": "0E-9",
    }
    assert cost["jev_decision_attempts"] == {
        "scope": "unique_decisions_referenced_by_run_hits",
        "billing_attribution": "decision_attempt_evidence_not_search_run_billing",
        "decision_count": 1,
        "reused_decision_count": 1,
        "attempt_count": 3,
        "settled_attempt_count": 2,
        "unknown_usage_attempt_count": 1,
        "in_flight_attempt_count": 0,
        "reservation_ceiling_usd": "0.006000000",
        "accounted_usd": "0.000110400",
        "estimated_unconfirmed_usd": "0.000050400",
        "confirmed_usd": "0.000060000",
        "confirmation_status": "incomplete",
    }


def test_committed_replay_requires_explicit_bounded_llm_budget(monkeypatch):
    hit = _hits("budget-required")[0]
    monkeypatch.setenv("RARE_TYPE_REPLAY_ENABLED", "1")

    with pytest.raises(CommandError, match="requires explicit --max-llm-calls"):
        call_command("replay_rare_type_hits", hit.pk, "--commit")
    with pytest.raises(CommandError, match="between 0 and 20"):
        call_command(
            "replay_rare_type_hits",
            hit.pk,
            "--commit",
            "--max-llm-calls",
            "21",
        )


def test_committed_replay_forwards_pinned_jev_config_and_never_builds_x_client(
    monkeypatch,
):
    hit = _hits("jev-config-forwarding")[0]
    monkeypatch.setenv("RARE_TYPE_REPLAY_ENABLED", "1")
    _patch_replay_preflight(monkeypatch)
    observed = {}

    class Gate:
        def process_hit(self, hit_id, **kwargs):
            RareTypeSearchHit.objects.filter(pk=hit_id).update(
                gate_state=RareTypeSearchHit.GateState.JUNK,
                gate_completed_at=NOW,
            )
            return SimpleNamespace(outcome="junk")

    def build_gate(cfg, *, environment, now):
        jev = cfg.discovery.rare_types.jev
        observed.update(
            model=jev.model,
            endpoint=jev.endpoint,
            question_version=jev.question_set_version,
            question_hash=jev.question_content_sha256,
            threshold_version=jev.threshold_version,
            threshold_hash=jev.threshold_values_sha256,
            environment=environment,
        )
        return Gate()

    monkeypatch.setattr("monitor.cycle.build_jev_decision_gate", build_gate)
    monkeypatch.setattr(
        CycleRunner,
        "_run_post_fetch",
        lambda self, *_a, **_kw: {"n_enrichment_claimed": 0},
    )
    output = StringIO()

    call_command(
        "replay_rare_type_hits",
        hit.pk,
        "--commit",
        "--max-llm-calls",
        "0",
        "--json",
        stdout=output,
    )

    fixture = load_config(Path("config.yaml")).discovery.rare_types.jev
    assert observed == {
        "model": fixture.model,
        "endpoint": fixture.endpoint,
        "question_version": fixture.question_set_version,
        "question_hash": fixture.question_content_sha256,
        "threshold_version": fixture.threshold_version,
        "threshold_hash": fixture.threshold_values_sha256,
        "environment": "normal",
    }
    result = json.loads(output.getvalue())
    assert result["twitterapi_calls"] == 0
    assert result["budgets"]["translation_and_classification_calls"] == 0
    assert result["budgets"]["hugging_face_requests"] == 0


def test_explicit_replay_enriches_only_selected_linked_hit(monkeypatch):
    brand = Brand.objects.create(nickname="deepseek", display_name="DeepSeek")
    SentimentKey.objects.create(key="neutral")
    PostTypeKey.objects.create(key="releases_updates")
    selected_post = Post.objects.create(tweet_id="selected-replay", text="DeepSeek R2")
    unrelated_post = Post.objects.create(
        tweet_id="unrelated-replay", text="DeepSeek R3"
    )
    for post in (selected_post, unrelated_post):
        PostBrand.objects.create(post=post, brand=brand)
        PostEnrichmentState.objects.create(post=post)
    selected_hit, unrelated_hit = _hits(selected_post.pk, unrelated_post.pk)
    _mark_kept_and_link(selected_hit, selected_post)
    _mark_kept_and_link(unrelated_hit, unrelated_post)
    monkeypatch.setenv("RARE_TYPE_REPLAY_ENABLED", "1")
    _patch_replay_preflight(monkeypatch)
    client = object()
    monkeypatch.setattr(
        "x_monitor.reattribute.build_translator_client_from_env", lambda _cfg: client
    )
    monkeypatch.setattr(
        "x_monitor.reattribute.build_classifier_client_from_env", lambda _cfg: client
    )
    monkeypatch.setattr(
        "x_monitor.translator.translate_batch_pragmatics",
        lambda tweets, locales, _client, **_kw: [
            {
                "tweet_id": tweet["tweet_id"],
                "text_en": tweet["text"],
                "text_zh_cn": "模型发布",
                "en_equivalent": "A model release.",
                "cn_equivalent": "一次模型发布。",
                "lang_detected": "en",
            }
            for tweet in tweets
        ],
    )
    monkeypatch.setattr(
        "x_monitor.attribution.classify_batch_pragmatics_full",
        lambda tweets, _brands, _client, **_kw: _classification_results(tweets),
    )

    call_command(
        "replay_rare_type_hits",
        selected_hit.pk,
        "--commit",
        "--max-llm-calls",
        "4",
    )

    selected_state = PostEnrichmentState.objects.get(post=selected_post)
    unrelated_state = PostEnrichmentState.objects.get(post=unrelated_post)
    selected_hit.refresh_from_db()
    unrelated_hit.refresh_from_db()
    assert selected_state.translation_status == PostEnrichmentState.Status.SUCCEEDED
    assert selected_state.classification_status == PostEnrichmentState.Status.SUCCEEDED
    assert unrelated_state.translation_status == PostEnrichmentState.Status.PENDING
    assert unrelated_state.classification_status == PostEnrichmentState.Status.PENDING
    assert unrelated_state.translation_attempts == 0
    assert unrelated_state.classification_attempts == 0
    assert selected_hit.classified_at is not None
    assert unrelated_hit.classified_at is None


def test_zero_llm_budget_blocks_translation_and_classification_transport(
    monkeypatch,
):
    brand = Brand.objects.create(nickname="deepseek", display_name="DeepSeek")
    post = Post.objects.create(tweet_id="zero-budget", text="DeepSeek release")
    PostBrand.objects.create(post=post, brand=brand)
    PostEnrichmentState.objects.create(post=post)
    hit = _hits(post.pk)[0]
    _mark_kept_and_link(hit, post)
    monkeypatch.setenv("RARE_TYPE_REPLAY_ENABLED", "1")
    _patch_replay_preflight(monkeypatch)

    class Provider:
        calls = 0

        def messages_create(self, **_kwargs):
            self.calls += 1
            raise AssertionError("zero budget reached the downstream provider")

    provider = Provider()
    monkeypatch.setattr(
        "x_monitor.reattribute.build_translator_client_from_env",
        lambda _cfg: provider,
    )
    monkeypatch.setattr(
        "x_monitor.reattribute.build_classifier_client_from_env",
        lambda _cfg: provider,
    )
    monkeypatch.setattr(
        "x_monitor.translator.translate_batch_pragmatics",
        lambda tweets, locales, client, **_kw: client.messages_create(),
    )
    monkeypatch.setattr(
        "x_monitor.attribution.classify_batch_pragmatics_full",
        lambda tweets, brands, client, **_kw: client.messages_create(),
    )

    call_command(
        "replay_rare_type_hits",
        hit.pk,
        "--commit",
        "--max-llm-calls",
        "0",
    )

    assert provider.calls == 0


def test_replay_retries_targeted_extraction_for_already_classified_post(monkeypatch):
    brand = Brand.objects.create(nickname="deepseek", display_name="DeepSeek")
    sentiment = SentimentKey.objects.create(key="neutral")
    post_type = PostTypeKey.objects.create(key="releases_updates")
    post = Post.objects.create(
        tweet_id="targeted-retry",
        created_at=django_timezone.now() - timedelta(minutes=1),
        text="DeepSeek announces R2",
        text_en="DeepSeek announces R2",
        text_zh_cn="DeepSeek 发布 R2",
        commentary_en="A supported release announcement.",
        commentary_zh_cn="这是有来源支持的发布公告。",
        lang_detected="en",
    )
    PostBrand.objects.create(post=post, brand=brand)
    PostBrandSignal.objects.create(
        post=post,
        brand=brand,
        post_type=post_type,
        sentiment=sentiment,
    )
    PostEnrichmentState.objects.create(
        post=post,
        translation_status=PostEnrichmentState.Status.SUCCEEDED,
        classification_status=PostEnrichmentState.Status.SUCCEEDED,
    )
    selected_targeted = TargetedExtractionState.objects.create(
        post=post,
        role="model_release_extraction",
        status="failed",
        content_identity="prior-failed-input",
        model="deepseek-ai/DeepSeek-V4-Flash-0731",
        prompt_version="model-release-extraction-v1",
        attempts=1,
        last_error_code="TimeoutError",
    )
    unrelated_post = Post.objects.create(
        tweet_id="targeted-unrelated",
        text="DeepSeek announces an unrelated model",
    )
    PostBrand.objects.create(post=unrelated_post, brand=brand)
    PostBrandSignal.objects.create(
        post=unrelated_post,
        brand=brand,
        post_type=post_type,
        sentiment=sentiment,
    )
    PostEnrichmentState.objects.create(
        post=unrelated_post,
        translation_status=PostEnrichmentState.Status.SUCCEEDED,
        classification_status=PostEnrichmentState.Status.SUCCEEDED,
    )
    unrelated_targeted = TargetedExtractionState.objects.create(
        post=unrelated_post,
        role="model_release_extraction",
        status="failed",
        content_identity="unrelated-failed-input",
        model="deepseek-ai/DeepSeek-V4-Flash-0731",
        prompt_version="model-release-extraction-v1",
        attempts=1,
        last_error_code="TimeoutError",
    )
    hit = _hits(post.pk)[0]
    decision = RareTypeDecision.objects.create(
        provider_post_id=post.pk,
        content_hash=hit.content_hash,
        model="typesafe/jev-1.13-20260917",
        question_version="rare-types-jev-questions-v1",
        threshold_version="rare-types-jev-thresholds-v1",
        status=RareTypeDecision.Status.COMPLETED,
        response_id="targeted-retry-response",
        probabilities={},
        derived_types=["model_releases"],
        gate_outcome=RareTypeDecision.GateOutcome.KEPT,
        completed_at=NOW,
    )
    _mark_kept_and_link(hit, post)
    hit.decision = decision
    hit.save(update_fields=["decision", "updated_at"])
    cfg = load_config(Path("config.yaml"))
    cfg.targeted_extraction.enabled = True
    cfg.targeted_extraction.max_calls_per_cycle = 1
    monkeypatch.setattr("x_monitor.config.load_config", lambda _path: cfg)
    monkeypatch.setenv("RARE_TYPE_REPLAY_ENABLED", "1")
    _patch_replay_preflight(monkeypatch)

    def targeted_calls(**_kwargs):
        return {
            "model_release_extraction": lambda *_args: {
                "records": [
                    {
                        "brand_id": "deepseek",
                        "organization_name": "DeepSeek",
                        "model_name": "DeepSeek R2",
                        "version": "R2",
                        "release_channel": "stable",
                        "release_value": "2026-09-24",
                        "release_precision": "day",
                        "categories": ["llm-model"],
                    }
                ]
            }
        }

    monkeypatch.setattr(
        "core.targeted_extraction.build_targeted_extraction_calls", targeted_calls
    )

    call_command(
        "replay_rare_type_hits",
        hit.pk,
        "--commit",
        "--max-llm-calls",
        "0",
    )

    release = ModelRelease.objects.get()
    selected_targeted.refresh_from_db()
    unrelated_targeted.refresh_from_db()
    assert release.observed_model_name == "DeepSeek R2"
    assert release.evidence.get().source_post_id == post.pk
    assert selected_targeted.status == "succeeded"
    assert selected_targeted.attempts == 2
    assert unrelated_targeted.status == "failed"
    assert unrelated_targeted.attempts == 1
    hit.refresh_from_db()
    assert hit.extracted_at is not None
    assert hit.first_visible_at is not None


def test_selected_persistence_failure_recovers_without_touching_other_hit(monkeypatch):
    Brand.objects.create(
        nickname="_unattributed", display_name="Unattributed", is_sentinel=True
    )
    selected, unrelated = _hits("persist-selected", "persist-unrelated")
    for hit in (selected, unrelated):
        hit.gate_state = RareTypeSearchHit.GateState.KEPT
        hit.gate_completed_at = NOW
        hit.save(update_fields=["gate_state", "gate_completed_at", "updated_at"])
    cfg = load_config(Path("config.yaml"))
    runner = CycleRunner(cfg=cfg)
    original = runner._persist_items
    monkeypatch.setattr(runner, "_persist_items", lambda _items: (0, 0, 0, 1))

    first = runner._ingest_kept_rare_type_hits(
        run_id="first", index=(None, {}), search_terms={}, hit_ids={selected.pk}
    )

    selected.refresh_from_db()
    unrelated.refresh_from_db()
    assert first["failed"] == 1
    assert selected.last_error_code == "post_persistence_failed"
    assert unrelated.last_error_code == ""
    assert unrelated.post_id is None

    monkeypatch.setattr(runner, "_persist_items", original)
    second = runner._ingest_kept_rare_type_hits(
        run_id="second", index=(None, {}), search_terms={}, hit_ids={selected.pk}
    )
    selected.refresh_from_db()
    unrelated.refresh_from_db()
    assert second["persisted"] == 1
    assert selected.post_id == "persist-selected"
    assert selected.last_error_code == ""
    assert unrelated.post_id is None


def test_explicit_targeted_retry_respects_deadline_before_provider_call():
    brand = Brand.objects.create(nickname="deepseek", display_name="DeepSeek")
    sentiment = SentimentKey.objects.create(key="neutral")
    post_type = PostTypeKey.objects.create(key="events")
    post = Post.objects.create(tweet_id="targeted-deadline", text="DeepSeek live event")
    PostBrand.objects.create(post=post, brand=brand)
    PostBrandSignal.objects.create(
        post=post,
        brand=brand,
        post_type=post_type,
        sentiment=sentiment,
    )
    PostEnrichmentState.objects.create(
        post=post,
        translation_status=PostEnrichmentState.Status.SUCCEEDED,
        classification_status=PostEnrichmentState.Status.SUCCEEDED,
    )
    hit = _hits(post.pk)[0]
    _mark_kept_and_link(hit, post)
    cfg = load_config(Path("config.yaml"))
    cfg.targeted_extraction.enabled = True
    called = 0

    def provider(*_args):
        nonlocal called
        called += 1
        return {"records": []}

    class Deadline:
        requested = None

        def can_start(self, seconds):
            self.requested = seconds
            return False

    deadline = Deadline()
    runner = CycleRunner(
        cfg=cfg,
        _targeted_extraction_calls={"event_extraction": provider},
    )

    result = runner._replay_targeted_extractions(post_ids={post.pk}, deadline=deadline)

    assert called == 0
    assert result["calls"] == 0
    assert result["deferred_roles"] == ["event_extraction"]
    assert deadline.requested == cfg.targeted_extraction.request_timeout_seconds + 8
    hit.refresh_from_db()
    assert hit.extracted_at is None

    runner._targeted_extraction_calls = {
        "event_extraction": lambda *_args: (_ for _ in ()).throw(
            RuntimeError("provider failed")
        )
    }
    failed = runner._replay_targeted_extractions(post_ids={post.pk})
    assert failed["failed_roles"] == ["event_extraction"]
    hit.refresh_from_db()
    assert hit.extracted_at is None


def test_no_applicable_targeted_role_does_not_mark_extracted():
    post = Post.objects.create(tweet_id="no-targeted-role", text="General AI update")
    PostEnrichmentState.objects.create(
        post=post,
        classification_status=PostEnrichmentState.Status.SUCCEEDED,
    )
    hit = _hits(post.pk)[0]
    _mark_kept_and_link(hit, post)
    cfg = load_config(Path("config.yaml"))
    cfg.targeted_extraction.enabled = True
    result = CycleRunner(cfg=cfg)._replay_targeted_extractions(post_ids={post.pk})
    assert result["selected_posts"] == 1
    assert result["calls"] == 0
    hit.refresh_from_db()
    assert hit.extracted_at is None


def test_explicit_post_scope_excludes_global_requeue_and_quarantine_side_effects():
    from monitor.cycle import (
        _claim_enrichment_states,
        _requeue_recent_incomplete_translations,
    )

    selected_post = Post.objects.create(
        tweet_id="maintenance-selected", text="selected"
    )
    unrelated_false_success_post = Post.objects.create(
        tweet_id="maintenance-false-success", text="unrelated"
    )
    unrelated_aged_post = Post.objects.create(
        tweet_id="maintenance-aged", text="unrelated aged"
    )
    unrelated_exhausted_post = Post.objects.create(
        tweet_id="maintenance-exhausted", text="unrelated exhausted"
    )
    selected = PostEnrichmentState.objects.create(
        post=selected_post,
        translation_status=PostEnrichmentState.Status.SUCCEEDED,
        classification_status=PostEnrichmentState.Status.SUCCEEDED,
    )
    unrelated_false_success = PostEnrichmentState.objects.create(
        post=unrelated_false_success_post,
        translation_status=PostEnrichmentState.Status.SUCCEEDED,
        classification_status=PostEnrichmentState.Status.SUCCEEDED,
    )
    unrelated_aged = PostEnrichmentState.objects.create(post=unrelated_aged_post)
    unrelated_exhausted = PostEnrichmentState.objects.create(
        post=unrelated_exhausted_post,
        translation_attempts=8,
        classification_attempts=8,
    )
    now = django_timezone.now()
    PostEnrichmentState.objects.filter(pk=unrelated_aged.pk).update(
        created_at=now - timedelta(hours=25)
    )
    cfg = load_config(Path("config.yaml")).harvest.enrichment

    reopened = _requeue_recent_incomplete_translations(
        cfg=cfg,
        now=now,
        post_ids={selected_post.pk},
    )
    batch = _claim_enrichment_states(
        cfg=cfg,
        run_id="explicit-maintenance-scope",
        now=now,
        post_ids={selected_post.pk},
    )

    selected.refresh_from_db()
    unrelated_false_success.refresh_from_db()
    unrelated_aged.refresh_from_db()
    unrelated_exhausted.refresh_from_db()
    assert reopened == 1
    assert [state.post_id for state in batch.states] == [selected_post.pk]
    assert batch.quarantined == 0
    assert selected.translation_status == PostEnrichmentState.Status.PENDING
    assert (
        unrelated_false_success.translation_status
        == PostEnrichmentState.Status.SUCCEEDED
    )
    assert unrelated_aged.translation_status == PostEnrichmentState.Status.PENDING
    assert unrelated_aged.classification_status == PostEnrichmentState.Status.PENDING
    assert unrelated_exhausted.translation_status == PostEnrichmentState.Status.PENDING
    assert (
        unrelated_exhausted.classification_status == PostEnrichmentState.Status.PENDING
    )
    assert unrelated_exhausted.translation_attempts == 8
