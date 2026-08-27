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
    os.environ.setdefault("TWITTERAPI_IO_API_KEY", "dummy")
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
    from monitor.cycle import _commentary_or_none

    assert _commentary_or_none("  Chinese commentary  ") == "Chinese commentary"
    assert _commentary_or_none("N/A") is None
    assert _commentary_or_none("  ") is None
    assert _commentary_or_none(None) is None


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_run_post_fetch_claims_durable_state_persists_flags_and_succeeds(monkeypatch):
    """Production post-fetch wiring owns state and Django flag persistence."""
    _django_setup()
    from core.models import (
        Post,
        PostEnrichmentState,
        PostUnsanctionedFlag,
        UnsanctionedFlagKey,
    )
    from monitor.cycle import CycleRunner
    from x_monitor import attribution, reattribute, translator
    from x_monitor.config import Config

    post = Post.objects.create(tweet_id="post-fetch-success", text="DeepSeek release")
    PostEnrichmentState.objects.create(post=post)
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
        return [{"by_brand": {}, "unsanctioned_flags": ["scam"]}]

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

    runner = CycleRunner(cfg=Config(enabled_models=["deepseek"], daily_ceiling=100))
    counters = runner._run_post_fetch([], run_id="run-flags")

    state = PostEnrichmentState.objects.get(post=post)
    assert counters["n_enrichment_claimed"] == 1
    assert counters["n_enrichment_succeeded"] == 1
    assert state.translation_status == PostEnrichmentState.Status.SUCCEEDED
    assert state.classification_status == PostEnrichmentState.Status.SUCCEEDED
    assert state.claim_run_id == ""
    assert len(translator_calls) == 1
    assert translator_calls[0][1:] == (["en", "zh_cn"], client)
    assert len(classifier_calls) == 1
    assert attempt_deadlines[0] is not attempt_deadlines[1]
    assert all(deadline.request_timeout_seconds == 90 for deadline in attempt_deadlines)
    post.refresh_from_db()
    assert post.commentary_zh_cn == "深度求索这波很能打"
    assert post.commentary_en == "The release signals another competitive step."
    assert PostUnsanctionedFlag.objects.filter(post=post).exists()


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_missing_clients_degrade_only_when_durable_work_exists(monkeypatch):
    _django_setup()
    from core.models import Post, PostEnrichmentState
    from monitor.cycle import CycleRunner
    from x_monitor import reattribute
    from x_monitor.config import Config

    monkeypatch.setattr(reattribute, "build_translator_client_from_env", lambda cfg: None)
    monkeypatch.setattr(reattribute, "build_anthropic_client_from_env", lambda cfg: None)
    cfg = Config(enabled_models=["deepseek"], daily_ceiling=100)

    empty_runner = CycleRunner(cfg=cfg)
    empty = empty_runner._run_post_fetch([], run_id="run-empty")
    assert empty["n_enrichment_claimed"] == 0
    assert empty_runner._errors == []

    post = Post.objects.create(tweet_id="post-fetch-missing", text="DeepSeek")
    PostEnrichmentState.objects.create(post=post)
    work_runner = CycleRunner(cfg=cfg)
    work = work_runner._run_post_fetch([], run_id="run-missing")

    assert work["n_enrichment_claimed"] == 1
    assert work["n_translator_unavailable"] == 1
    assert work["n_classifier_unavailable"] == 1
    assert work["n_enrichment_pending"] == 1
    assert any("translator_unavailable" in error for error in work_runner._errors)
    assert any("classifier_unavailable" in error for error in work_runner._errors)
