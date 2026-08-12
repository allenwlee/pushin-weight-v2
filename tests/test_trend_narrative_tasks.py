"""PostgreSQL tests for the bounded headline refresh worker."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from django.conf import settings

from core.models import TrendNarrativeVersion
from monitor.tasks import refresh_trend_narratives
from monitor.trend_narrative_tasks import process_trend_narrative_envelope
from x_monitor.config import HeadlineNarrativeConfig

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


def _envelope(
    source: str = "cycle-a",
    *,
    completed_at: datetime = NOW,
) -> dict:
    return {
        "schema_version": 1,
        "source_cycle_id": source,
        "completed_at": completed_at.isoformat().replace("+00:00", "Z"),
        "outcome": "completed",
        "dry_run": False,
    }


def _facts(window_days: int, *, as_of: datetime, changed: bool = False) -> dict:
    brand = "qwen" if changed else "minimax"
    return {
        "schema_version": 1,
        "window_days": window_days,
        "as_of": as_of.isoformat().replace("+00:00", "Z"),
        "window_start": (as_of - timedelta(days=window_days))
        .isoformat()
        .replace("+00:00", "Z"),
        "midpoint": (as_of - timedelta(days=window_days / 2))
        .isoformat()
        .replace("+00:00", "Z"),
        "coverage": {
            "state": "sufficient",
            "ratio": "1.000000",
            "earliest_at": "2025-01-15T00:00:00Z",
        },
        "thresholds": {"min_posts": 20, "min_authors": 10},
        "narrative_type": "leader",
        "primary_brand": {
            "key": brand,
            "display_name_en": brand.title(),
            "display_name_zh_hans": brand.title(),
            "recent_posts": 25,
            "recent_authors": 12,
            "earlier_posts": 20,
            "earlier_authors": 10,
        },
        "secondary_brand": None,
        "earlier_leader": None,
        "momentum": "rising",
    }


def _result(facts: dict, config: HeadlineNarrativeConfig):
    from monitor.trend_narrative_generation import generation_fingerprint

    brand = facts["primary_brand"]["display_name_en"]
    return SimpleNamespace(
        body_en=f"{brand} leads attention across the market.",
        body_zh_hans=f"当前市场讨论中，{brand} 更受关注。",
        output_hash="b" * 64,
        input_tokens=100,
        output_tokens=40,
        latency_ms=200,
        semantic_fingerprint=generation_fingerprint(facts, config),
    )


def _enable(monkeypatch, *, fail_window: int | None = None, changed=None):
    config = HeadlineNarrativeConfig(provider_calls_enabled=True)
    calls: list[int] = []
    changed = changed or set()

    monkeypatch.setattr(
        "monitor.trend_narrative_tasks._load_config",
        lambda: config,
    )
    monkeypatch.setattr(
        "monitor.trend_narrative_tasks.build_trend_fact_packet",
        lambda window_days, *, as_of, thresholds, earliest_at: _facts(
            window_days,
            as_of=as_of,
            changed=window_days in changed,
        ),
    )

    def generate(facts, active_config):
        calls.append(facts["window_days"])
        if facts["window_days"] == fail_window:
            raise RuntimeError("fixture provider outage")
        return _result(facts, active_config)

    monkeypatch.setattr(
        "monitor.trend_narrative_tasks.generate_trend_narrative",
        generate,
    )
    return config, calls


def test_cold_refresh_makes_exactly_four_calls_and_duplicate_makes_zero(
    monkeypatch,
):
    coverage_queries: list[datetime] = []
    monkeypatch.setattr(
        "monitor.trend_narrative_tasks.earliest_trend_fact_at",
        lambda *, as_of: coverage_queries.append(as_of) or NOW - timedelta(days=365),
    )
    _config, calls = _enable(monkeypatch)

    first = process_trend_narrative_envelope(_envelope(), now=NOW)
    duplicate = process_trend_narrative_envelope(_envelope(), now=NOW)

    assert first["slots_consumed"] == 4
    assert first["published"] == 4
    assert duplicate["slots_consumed"] == 0
    assert calls == [1, 7, 30, 365]
    assert coverage_queries == [NOW]
    assert TrendNarrativeVersion.objects.filter(call_slot_consumed=True).count() == 4


def test_same_semantics_after_due_cadence_advances_checks_with_zero_calls(
    monkeypatch,
):
    _config, calls = _enable(monkeypatch)
    process_trend_narrative_envelope(_envelope(), now=NOW)
    calls.clear()
    later = NOW + timedelta(days=1)

    result = process_trend_narrative_envelope(
        _envelope("cycle-b", completed_at=later),
        now=later,
    )

    assert result["slots_consumed"] == 0
    assert result["checks_advanced"] == 4
    assert calls == []
    assert TrendNarrativeVersion.objects.count() == 4


def test_only_changed_window_calls_provider_when_all_windows_are_due(monkeypatch):
    _config, calls = _enable(monkeypatch)
    process_trend_narrative_envelope(_envelope(), now=NOW)
    calls.clear()
    later = NOW + timedelta(days=1)
    _enable(monkeypatch, changed={1})

    result = process_trend_narrative_envelope(
        _envelope("cycle-b", completed_at=later),
        now=later,
    )

    assert result["slots_consumed"] == 1
    assert result["published"] == 1
    assert TrendNarrativeVersion.objects.filter(call_slot_consumed=True).count() == 5


def test_provider_disabled_consumes_envelope_with_zero_reservations(monkeypatch):
    config = HeadlineNarrativeConfig(provider_calls_enabled=False)
    monkeypatch.setattr(
        "monitor.trend_narrative_tasks._load_config",
        lambda: config,
    )
    monkeypatch.setattr(
        "monitor.trend_narrative_tasks.build_trend_fact_packet",
        lambda window_days, *, as_of, thresholds, earliest_at: _facts(
            window_days, as_of=as_of
        ),
    )

    result = process_trend_narrative_envelope(_envelope(), now=NOW)

    assert result["slots_consumed"] == 0
    assert result["suppressed"] == 4
    assert not TrendNarrativeVersion.objects.filter(call_slot_consumed=True).exists()
    assert TrendNarrativeVersion.objects.filter(status="suppressed").count() == 4


def test_one_window_failure_does_not_discard_other_publications(monkeypatch):
    _config, calls = _enable(monkeypatch, fail_window=7)

    result = process_trend_narrative_envelope(_envelope(), now=NOW)

    assert result["slots_consumed"] == 4
    assert result["published"] == 3
    assert result["failed"] == 1
    assert calls == [1, 7, 30, 365]
    assert TrendNarrativeVersion.objects.filter(status="failed").count() == 1
    assert TrendNarrativeVersion.objects.filter(is_current=True).count() == 3


def test_failure_backoff_retries_at_boundary_without_waiting_full_cadence(
    monkeypatch,
):
    config, calls = _enable(monkeypatch, fail_window=365)
    first = process_trend_narrative_envelope(_envelope(), now=NOW)
    calls.clear()

    before = NOW + timedelta(minutes=config.backoff_minutes[0] - 1)
    blocked = process_trend_narrative_envelope(
        _envelope("cycle-b", completed_at=before),
        now=before,
    )
    assert blocked["slots_consumed"] == 0
    assert blocked["suppressed"] == 1
    assert calls == []

    boundary = NOW + timedelta(minutes=config.backoff_minutes[0])
    _enable(monkeypatch)
    retried = process_trend_narrative_envelope(
        _envelope("cycle-c", completed_at=boundary),
        now=boundary,
    )

    assert first["failed"] == 1
    assert retried["slots_consumed"] == 1
    assert retried["published"] == 1


def test_each_sequential_call_receives_a_fresh_lease_clock(monkeypatch):
    current = [NOW]
    config, calls = _enable(monkeypatch)
    original_generate = __import__(
        "monitor.trend_narrative_tasks", fromlist=["generate_trend_narrative"]
    ).generate_trend_narrative

    def slow_generate(facts, active_config):
        result = original_generate(facts, active_config)
        current[0] += timedelta(seconds=40)
        return result

    monkeypatch.setattr(
        "monitor.trend_narrative_tasks.generate_trend_narrative",
        slow_generate,
    )

    result = process_trend_narrative_envelope(
        _envelope(),
        clock=lambda: current[0],
    )

    assert config.lease_seconds < 4 * 40
    assert calls == [1, 7, 30, 365]
    assert result["published"] == 4
    assert result["failed"] == 0
    claimed_at = list(
        TrendNarrativeVersion.objects.order_by("window_days").values_list(
            "claimed_at", flat=True
        )
    )
    assert claimed_at == [
        NOW,
        NOW + timedelta(seconds=40),
        NOW + timedelta(seconds=80),
        NOW + timedelta(seconds=120),
    ]


def test_older_and_expired_envelopes_make_zero_calls(monkeypatch):
    config, calls = _enable(monkeypatch)
    newer = NOW + timedelta(hours=1)
    process_trend_narrative_envelope(
        _envelope("cycle-new", completed_at=newer),
        now=newer,
    )
    calls.clear()

    old = process_trend_narrative_envelope(_envelope("cycle-old"), now=newer)
    expired = process_trend_narrative_envelope(
        _envelope("cycle-expired"),
        now=NOW + timedelta(seconds=config.task_expiry_seconds + 1),
    )

    assert old["slots_consumed"] == 0
    assert expired["status"] == "expired"
    assert calls == []


def test_task_is_queue_isolated_and_has_no_automatic_retry():
    assert refresh_trend_narratives.name == "monitor.tasks.refresh_trend_narratives"
    assert refresh_trend_narratives.max_retries == 0
    assert refresh_trend_narratives.ignore_result is True
    assert refresh_trend_narratives.acks_late is True
    assert refresh_trend_narratives.reject_on_worker_lost is True
    assert refresh_trend_narratives.time_limit < 15 * 60
    assert settings.CELERY_BROKER_TRANSPORT_OPTIONS["visibility_timeout"] > (
        refresh_trend_narratives.time_limit
    )
