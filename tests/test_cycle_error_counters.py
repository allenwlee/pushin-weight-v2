"""Tests for plan 2026-08-01-002 U5: regression net for the AFTER state.

Pin the summary's `n_errors_by_type` key so a future edit cannot silently
drop the typed counters from the --json output. The original lang_detected
bug hid for 14+ hours because the failure mode was silent; this test
ensures the silent-failure mode stays observable.
"""
import os
from pathlib import Path

import pytest


def _django_setup():
    os.environ.setdefault("DATABASE_URL", "sqlite:///data/django_dev.db")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
    os.environ.setdefault("TWITTERAPI_IO_SCHEDULED_API_KEY", "dummy")
    import django
    if not django.apps.apps.ready:
        django.setup()


def test_run_post_fetch_summary_has_n_errors_by_type():
    """CycleRunner._run_post_fetch must surface n_errors_by_type in summary."""
    _django_setup()
    from monitor.cycle import CycleRunner
    from x_monitor.config import load_config

    cfg = load_config(Path("config.yaml"))
    runner = CycleRunner(dry_run=True, cfg=cfg)
    # Initial state: counters exist + are zero
    assert "translator_batch_failed" in runner._error_counts
    assert "classifier_batch_failed" in runner._error_counts
    # Simulate post-fetch emit (the summary dict gets n_errors_by_type)
    summary = {}
    summary.setdefault("n_errors_by_type", {}).update(dict(runner._error_counts))
    assert "translator_batch_failed" in summary["n_errors_by_type"]
    assert "classifier_batch_failed" in summary["n_errors_by_type"]


def test_error_counter_increments_are_visible():
    """A typed counter increment must be reflected in --json n_errors_by_type."""
    _django_setup()
    from monitor.cycle import CycleRunner
    from x_monitor.config import load_config

    cfg = load_config(Path("config.yaml"))
    runner = CycleRunner(dry_run=True, cfg=cfg)
    # Simulate a translator_batch_failed event
    runner._error_counts["translator_batch_failed"] += 4
    summary = {"n_errors_by_type": dict(runner._error_counts)}
    assert summary["n_errors_by_type"]["translator_batch_failed"] == 4


def test_commentary_normalization_treats_translator_sentinel_as_missing():
    from monitor.post_enrichment import present_text

    assert present_text("  Chinese commentary  ") == "Chinese commentary"
    assert present_text("N/A") is None
    assert present_text("  ") is None
    assert present_text(None) is None


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_run_post_fetch_claims_durable_state_persists_flags_and_succeeds(monkeypatch):
    """Legacy compatibility writer still owns state and flag persistence."""
    _django_setup()
    from core.models import (
        Brand,
        NationalismKey,
        Post,
        PostBrand,
        PostEnrichmentState,
        PostUnsanctionedFlag,
        SentimentKey,
        UnsanctionedFlagKey,
    )
    from monitor.cycle import CycleRunner
    from x_monitor import attribution, reattribute, translator
    from x_monitor.config import Config, LlmConfig

    post = Post.objects.create(tweet_id="post-fetch-success", text="DeepSeek release")
    brand = Brand.objects.create(nickname="deepseek", display_name="DeepSeek")
    PostBrand.objects.create(post=post, brand=brand)
    from core.models import PostTypeKey

    PostTypeKey.objects.get_or_create(key="releases_updates")
    SentimentKey.objects.get_or_create(key="neutral")
    NationalismKey.objects.get_or_create(key="none")
    PostEnrichmentState.objects.create(post=post, translation_requested=True)
    UnsanctionedFlagKey.objects.get_or_create(key="scam")
    client = object()
    translator_calls = []
    classifier_calls = []
    attempt_deadlines = []
    monkeypatch.setattr(reattribute, "build_translator_client_from_env", lambda cfg: client)
    monkeypatch.setattr(reattribute, "build_anthropic_client_from_env", lambda cfg: client)

    def translate(tweets, locales, translator_client, **kwargs):
        translator_calls.append((tweets, locales, translator_client))
        attempt_deadlines.append(kwargs["deadline"])
        return [
            {
                "tweet_id": post.pk,
                "text_en": post.text,
                "text_zh_cn": "深度求索发布",
                "en_equivalent": "The release signals another competitive step.",
                "cn_equivalent": "深度求索这波很能打",
                "lang_detected": "en",
            }
        ]

    def classify(tweets, brands, classifier_client, **kwargs):
        classifier_calls.append((tweets, brands, classifier_client))
        attempt_deadlines.append(kwargs["deadline"])
        return [{"by_brand": {"deepseek": {
            "outcome": "classified", "post_types": ["releases_updates"],
            "product_labels": [], "sentiment": "neutral",
            "china_nationalism": "none", "us_nationalism": "none",
        }}, "unsanctioned_flags": ["scam"], "valid": True}]

    monkeypatch.setattr(
        translator,
        "translate_batch_pragmatics",
        translate,
    )
    monkeypatch.setattr(
        attribution,
        "classify_batch_pragmatics_full",
        classify,
    )

    runner = CycleRunner(cfg=Config(
        enabled_models=["deepseek"], daily_ceiling=100,
        llm=LlmConfig(literal_translation_v2_enabled=False),
    ))
    counters = runner._run_post_fetch([], run_id="run-flags")

    state = PostEnrichmentState.objects.get(post=post)
    assert counters["n_enrichment_claimed"] == 1
    assert counters["n_enrichment_claimed_carryover"] == 1
    assert counters["n_enrichment_claimed_current_cycle"] == 0
    assert counters["n_enrichment_succeeded"] == 1
    assert counters["enrichment_carryover_post_ids"] == [post.pk]
    assert counters["enrichment_current_cycle_post_ids"] == []
    assert counters["enrichment_state_facts"] == [
        {
            "post_id": post.pk,
            "lane": "carryover",
            "translation_status": PostEnrichmentState.Status.SUCCEEDED,
            "translation_requested": True,
            "classification_status": PostEnrichmentState.Status.SUCCEEDED,
            "output_complete": True,
        }
    ]
    assert state.translation_status == PostEnrichmentState.Status.SUCCEEDED
    assert state.classification_status == PostEnrichmentState.Status.SUCCEEDED
    assert state.claim_run_id == ""
    assert len(translator_calls) == 1
    assert translator_calls[0][1] == ["en", "zh_cn"]
    assert translator_calls[0][2]._delegate is client
    assert len(classifier_calls) == 1
    assert classifier_calls[0][2]._delegate is client
    assert attempt_deadlines[0] is not attempt_deadlines[1]
    assert all(deadline.request_timeout_seconds == 90 for deadline in attempt_deadlines)
    post.refresh_from_db()
    assert post.commentary_zh_cn == "深度求索这波很能打"
    assert post.commentary_en == "The release signals another competitive step."
    assert PostUnsanctionedFlag.objects.filter(post=post).exists()


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_profile_capture_uses_page_receipt_not_later_persistence_clock(monkeypatch):
    _django_setup()
    from datetime import UTC, datetime, timedelta

    from monitor import cycle
    from x_monitor.config import Config

    received = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    seen = []
    monkeypatch.setattr(cycle, "capture_post_profile_snapshot", lambda **kw: seen.append(kw))
    runner = cycle.CycleRunner(cfg=Config(enabled_models=["deepseek"], daily_ceiling=100))
    runner._clock = lambda: received + timedelta(hours=1)
    item = {
        "id": "receipt-clock-test",
        "author_id": "receipt-clock-author",
        "author_handle": "receiptclock",
        "text": "Saved post",
        "created_at": received.isoformat(),
        "_api_received_at": received.isoformat(),
        "brand_ids": [],
        "mentions": [],
        "classifications": {},
    }
    inserted, _, _, failed = runner._persist_items([item])
    assert (inserted, failed) == (1, 0)
    assert len(seen) == 1 and seen[0]["observed_at"] == received
    assert runner._profile_receipt_time({}) is None


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_refetched_post_captures_changed_profile_at_each_page_receipt():
    _django_setup()
    from datetime import UTC, datetime, timedelta

    from core.models import AccountProfileSnapshot
    from monitor.cycle import CycleRunner
    from x_monitor.config import Config

    received = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    runner = CycleRunner(cfg=Config(enabled_models=["deepseek"], daily_ceiling=100))
    item = {
        "id": "987654321",
        "author_id": "987654",
        "author_handle": "receiptprofile",
        "author_description": "First profile",
        "_author_present_fields": ["author_handle", "author_description"],
        "text": "Saved post",
        "created_at": received.isoformat(),
        "_api_received_at": received.isoformat(),
        "brand_ids": [],
        "mentions": [],
        "classifications": {},
    }
    assert runner._persist_items([dict(item)])[3] == 0
    second_time = received + timedelta(hours=1)
    item.update(author_description="Changed profile", _api_received_at=second_time.isoformat())
    assert runner._persist_items([dict(item)])[3] == 0
    snapshots = list(AccountProfileSnapshot.objects.filter(account__author_id="987654").order_by("first_observed_at"))
    assert [(row.description, row.first_observed_at) for row in snapshots] == [
        ("First profile", received),
        ("Changed profile", second_time),
    ]


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_persistence_marker_flows_to_current_cycle_post_fetch_evidence(monkeypatch):
    _django_setup()
    from datetime import timedelta

    from django.utils import timezone

    from core.models import PostEnrichmentState
    from monitor.cycle import CycleRunner
    from x_monitor import attribution, reattribute, translator
    from x_monitor.config import Config, LlmConfig

    cutoff = timezone.now() - timedelta(seconds=1)
    item = {
        "id": "same-cycle-insert",
        "author_id": "same-cycle-author",
        "author_handle": "same-cycle-author",
        "text": "DeepSeek release",
        "created_at": cutoff.isoformat(),
        "brand_ids": [],
        "mentions": [],
        "classifications": {},
    }
    cfg = Config(
        enabled_models=["deepseek"], daily_ceiling=100,
        llm=LlmConfig(literal_translation_v2_enabled=False),
    )
    runner = CycleRunner(cfg=cfg)
    inserted, updated, _attributed, failed = runner._persist_items([item])
    assert (inserted, updated, failed) == (1, 0, 0)
    assert item["_db_inserted"] is True
    assert item["_persisted_post_id"] == item["id"]

    # Translation is now requested explicitly; retain coverage of the legacy
    # compatibility writer here. The plaintext caller has its own regression net.
    PostEnrichmentState.objects.filter(post_id=item["id"]).update(translation_requested=True)
    client = object()
    translator_call = {}
    classifier_call = {}
    monkeypatch.setattr(reattribute, "build_translator_client_from_env", lambda cfg: client)
    monkeypatch.setattr(reattribute, "build_anthropic_client_from_env", lambda cfg: client)

    def translate(tweets, locales, translator_client, **kwargs):
        translator_call.update(
            n=len(tweets),
            max_workers=kwargs["max_workers"],
            model=kwargs["cfg"].llm.translator_model,
        )
        return [
            {
                "tweet_id": item["id"],
                "text_en": item["text"],
                "text_zh_cn": "深度求索发布",
                "en_equivalent": "The release adds competitive pressure.",
                "cn_equivalent": "这次发布增加了竞争压力。",
                "lang_detected": "en",
            }
        ]

    def classify(tweets, brands, classifier_client, **kwargs):
        classifier_call.update(
            n=len(tweets),
            max_workers=kwargs["max_workers"],
            model=kwargs["model"],
        )
        return [{"by_brand": {}, "unsanctioned_flags": []}]

    monkeypatch.setattr(translator, "translate_batch_pragmatics", translate)
    monkeypatch.setattr(attribution, "classify_batch_pragmatics_full", classify)

    counters = runner._run_post_fetch(
        [item],
        run_id="same-cycle-evidence",
        prefer_created_before=cutoff,
    )

    state = PostEnrichmentState.objects.get(post_id=item["id"])
    assert counters["inserted_post_ids"] == [item["id"]]
    assert counters["enrichment_current_cycle_post_ids"] == [item["id"]]
    assert counters["n_enrichment_claimed_current_cycle"] == 1
    assert counters["enrichment_state_facts"][0]["lane"] == "current_cycle"
    assert counters["enrichment_state_facts"][0]["output_complete"] is True
    assert translator_call == {
        "n": 1,
        "max_workers": 3,
        "model": "deepseek-v4-flash",
    }
    assert classifier_call == {
        "n": 1,
        "max_workers": 3,
        "model": "deepseek-v4-flash",
    }
    assert state.claim_run_id == ""


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_missing_clients_degrade_only_when_durable_work_exists(monkeypatch):
    _django_setup()
    from core.models import Post, PostEnrichmentState
    from monitor.cycle import CycleRunner
    from x_monitor import reattribute
    from x_monitor.config import Config, LlmConfig

    monkeypatch.setattr(reattribute, "build_translator_client_from_env", lambda cfg: None)
    monkeypatch.setattr(reattribute, "build_anthropic_client_from_env", lambda cfg: None)
    cfg = Config(
        enabled_models=["deepseek"], daily_ceiling=100,
        llm=LlmConfig(literal_translation_v2_enabled=False),
    )

    empty_runner = CycleRunner(cfg=cfg)
    empty = empty_runner._run_post_fetch([], run_id="run-empty")
    assert empty["n_enrichment_claimed"] == 0
    assert empty_runner._errors == []

    post = Post.objects.create(tweet_id="post-fetch-missing", text="DeepSeek")
    PostEnrichmentState.objects.create(post=post, translation_requested=True)
    work_runner = CycleRunner(cfg=cfg)
    work = work_runner._run_post_fetch([], run_id="run-missing")

    assert work["n_enrichment_claimed"] == 1
    assert work["n_translator_unavailable"] == 1
    assert work["n_classifier_unavailable"] == 1
    assert work["n_enrichment_pending"] == 1
    assert any("translator_unavailable" in error for error in work_runner._errors)
    assert any("classifier_unavailable" in error for error in work_runner._errors)
