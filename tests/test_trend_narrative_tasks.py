"""PostgreSQL tests for the bounded headline refresh worker."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from billiard.exceptions import SoftTimeLimitExceeded
from django.conf import settings

from core.models import Brand, TrendNarrative, TrendNarrativeSubject
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


def _snapshot(window_days: int, *, as_of: datetime, changed: bool = False) -> dict:
    brand = "qwen" if changed else "minimax"
    candidate_id = f"{brand}:full_window"
    return {
        "snapshot_schema_version": 1,
        "window_days": window_days,
        "as_of": as_of.isoformat().replace("+00:00", "Z"),
        "coverage": {
            "selected": {
                "state": "sufficient",
                "ratio": "1.000000",
                "earliest_at": "2025-08-12T12:00:00+00:00",
            },
            "prior": {
                "state": "sufficient",
                "ratio": "1.000000",
                "earliest_at": "2025-08-12T12:00:00+00:00",
            },
        },
        "comparison_allowed": True,
        "thresholds": {"min_posts": 20, "min_authors": 10},
        "series_axis": {
            "coarse": {
                "bucket_count": 2,
                "bucket_seconds": 10_800,
                "starts": ["start-one", "start-two"],
                "ends": ["end-one", "end-two"],
            },
            "fine": {
                "bucket_count": 0,
                "bucket_seconds": 900,
                "starts": [],
                "ends": [],
            },
        },
        "selection": {"candidate_count": 1},
        "candidates": [
            {
                "candidate_id": candidate_id,
                "source_candidate_id": candidate_id,
                "brand_key": brand,
                "display_name_en": brand.title(),
                "display_name_zh_cn": brand.title(),
                "kind": "full_window",
                "start_at": "window-start",
                "end_at": "window-end",
                "signals": [{"family": "volume", "rank": 1}],
                "family_facts": {"volume": {"selected_posts": 25}},
                "episodes": [],
                "series": {
                    "coarse": {
                        "post_counts": [20, 25],
                        "author_counts": [10, 12],
                        "engagement": {
                            "eligible_counts": [20, 25],
                            "missing_counts": [0, 0],
                            "coverage_ratios": ["1.000000", "1.000000"],
                            "likes": [40, 50],
                            "reposts": [10, 12],
                            "quotes": [4, 5],
                            "replies": [2, 3],
                            "interactions": [56, 70],
                            "intensities": ["2.800000", "2.800000"],
                            "concentrations": ["0.200000", "0.200000"],
                            "post_kinds": {},
                        },
                    },
                    "fine": {},
                },
                "evidence_support": {
                    "official_source_count": 0,
                    "distinct_author_group_count": 0,
                    "distinct_source_cluster_count": 0,
                    "event_claim_may_be_supported": False,
                    "evidence_only_entity_may_be_supported": False,
                },
                "evidence": [],
            }
        ],
    }


def _result(snapshot: dict, config: HeadlineNarrativeConfig):
    from monitor.trend_narrative_generation import generation_fingerprint

    candidate = snapshot["candidates"][0]
    brand = candidate["display_name_en"]
    candidate_id = candidate["candidate_id"]
    return SimpleNamespace(
        output_schema_version=3,
        body_en=f"{brand} leads attention across the market.",
        body_zh_cn=f"当前市场讨论中，{brand} 更受关注。",
        observations_en=("Attention rises and then holds.",),
        observations_zh_cn=("讨论热度上升后保持稳定。",),
        selected_candidate_ids=(candidate_id,),
        subjects=(
            {
                "position": 0,
                "support_type": "measured_candidate",
                "entity_type": "brand",
                "identity_type": "brand",
                "observed_name": "",
                "canonical_key_snapshot": candidate["brand_key"],
                "name_en_snapshot": brand,
                "name_zh_cn_snapshot": brand,
                "candidate_id": candidate_id,
                "evidence_ids": [],
            },
        ),
        claims=(
            {
                "observation_index": -1,
                "candidate_ids": [candidate_id],
                "families": ["volume"],
                "evidence_ids": [],
                "quantitative_fact_ids": [],
                "event_anchor": "",
                "explanation_type": "aggregate_trajectory",
                "evidence_confidence": "aggregate_only",
            },
            {
                "observation_index": 0,
                "candidate_ids": [candidate_id],
                "families": ["volume"],
                "evidence_ids": [],
                "quantitative_fact_ids": [],
                "event_anchor": "",
                "explanation_type": "aggregate_trajectory",
                "evidence_confidence": "aggregate_only",
            },
        ),
        output_hash="b" * 64,
        input_tokens=100,
        output_tokens=40,
        latency_ms=200,
        semantic_fingerprint=generation_fingerprint(snapshot, config),
    )


def _enable(monkeypatch, *, fail_window: int | None = None, changed=None):
    config = HeadlineNarrativeConfig(provider_calls_enabled=True)
    calls: list[int] = []
    changed = changed or set()
    for nickname in ("minimax", "qwen"):
        Brand.objects.update_or_create(
            nickname=nickname,
            defaults={
                "display_name": nickname.title(),
                "display_name_en": nickname.title(),
                "display_name_zh_cn": nickname.title(),
            },
        )

    monkeypatch.setattr(
        "monitor.trend_narrative_tasks._load_config",
        lambda: config,
    )
    monkeypatch.setattr(
        "monitor.trend_narrative_tasks.build_trend_analysis_snapshot",
        lambda window_days, *, as_of, thresholds, evidence_policy: _snapshot(
            window_days,
            as_of=as_of,
            changed=window_days in changed,
        ),
    )

    def generate(snapshot, active_config):
        calls.append(snapshot["window_days"])
        if snapshot["window_days"] == fail_window:
            raise RuntimeError("fixture provider outage")
        return _result(snapshot, active_config)

    monkeypatch.setattr(
        "monitor.trend_narrative_tasks.generate_trend_narrative",
        generate,
    )
    return config, calls


def test_cold_refresh_makes_exactly_four_calls_and_duplicate_makes_zero(
    monkeypatch,
):
    _config, calls = _enable(monkeypatch)

    first = process_trend_narrative_envelope(_envelope(), now=NOW)
    duplicate = process_trend_narrative_envelope(_envelope(), now=NOW)

    assert first["slots_consumed"] == 4
    assert first["published"] == 4
    assert duplicate["slots_consumed"] == 0
    assert calls == [1, 7, 30, 365]
    assert TrendNarrative.objects.filter(call_slot_consumed=True).count() == 4
    assert TrendNarrative.objects.filter(output_schema_version=3).count() == 4
    assert TrendNarrativeSubject.objects.count() == 4
    one_day = TrendNarrative.objects.get(window_days=1, is_current=True)
    assert one_day.body_zh_cn == one_day.body_zh_hans
    assert one_day.llm_model_name == one_day.model_name == "deepseek-v4-pro"
    assert one_day.selected_candidate_ids == ["minimax:full_window"]


def test_scheduled_task_reaches_generation_with_pinned_provider_controls(
    monkeypatch,
):
    config, calls = _enable(monkeypatch)
    task_module = __import__(
        "monitor.trend_narrative_tasks",
        fromlist=["generate_trend_narrative"],
    )
    configured_generate = task_module.generate_trend_narrative
    observed: list[tuple[int, str, str]] = []
    observed_policies = []

    monkeypatch.setattr(
        "monitor.trend_narrative_queue.coalesce_envelope",
        lambda envelope: envelope,
    )
    monkeypatch.setattr("monitor.trend_narrative_tasks.timezone.now", lambda: NOW)

    def capture_snapshot(window_days, *, as_of, thresholds, evidence_policy):
        observed_policies.append(evidence_policy)
        return _snapshot(window_days, as_of=as_of)

    monkeypatch.setattr(
        "monitor.trend_narrative_tasks.build_trend_analysis_snapshot",
        capture_snapshot,
    )

    def capture_generation(snapshot, active_config):
        observed.append(
            (
                snapshot["window_days"],
                active_config.provider,
                active_config.model,
            )
        )
        return configured_generate(snapshot, active_config)

    monkeypatch.setattr(
        "monitor.trend_narrative_tasks.generate_trend_narrative",
        capture_generation,
    )

    result = refresh_trend_narratives.run(_envelope())

    assert result["published"] == 4
    assert calls == [1, 7, 30, 365]
    assert observed == [
        (window_days, "deepseek", "deepseek-v4-pro")
        for window_days in (1, 7, 30, 365)
    ]
    assert config.model == "deepseek-v4-pro"
    assert [policy.version for policy in observed_policies] == [
        "adaptive-v1",
        "adaptive-v1",
        "adaptive-v1",
        "adaptive-v1",
    ]
    assert all(policy.lead_ceiling == 48 for policy in observed_policies)


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
    assert TrendNarrative.objects.count() == 4


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
    assert TrendNarrative.objects.filter(call_slot_consumed=True).count() == 5


def test_provider_disabled_consumes_envelope_with_zero_reservations(monkeypatch):
    config = HeadlineNarrativeConfig(provider_calls_enabled=False)
    monkeypatch.setattr(
        "monitor.trend_narrative_tasks._load_config",
        lambda: config,
    )
    monkeypatch.setattr(
        "monitor.trend_narrative_tasks.build_trend_analysis_snapshot",
        lambda window_days, *, as_of, thresholds, evidence_policy: _snapshot(
            window_days, as_of=as_of
        ),
    )

    result = process_trend_narrative_envelope(_envelope(), now=NOW)

    assert result["slots_consumed"] == 0
    assert result["suppressed"] == 4
    assert not TrendNarrative.objects.filter(call_slot_consumed=True).exists()
    assert TrendNarrative.objects.filter(status="suppressed").count() == 4


def test_provider_disable_after_envelope_start_consumes_zero_slots(monkeypatch):
    enabled = HeadlineNarrativeConfig(
        provider_calls_enabled=True,
        control_revision="enabled-v1",
    )
    disabled = enabled.model_copy(
        update={
            "provider_calls_enabled": False,
            "control_revision": "disabled-v2",
        }
    )
    active = {"config": enabled}
    generation_calls: list[int] = []

    monkeypatch.setattr(
        "monitor.trend_narrative_tasks._load_config",
        lambda: active["config"],
    )

    def build(window_days, *, as_of, thresholds, evidence_policy):
        active["config"] = disabled
        return _snapshot(window_days, as_of=as_of)

    monkeypatch.setattr(
        "monitor.trend_narrative_tasks.build_trend_analysis_snapshot",
        build,
    )
    monkeypatch.setattr(
        "monitor.trend_narrative_tasks.generate_trend_narrative",
        lambda snapshot, config: generation_calls.append(snapshot["window_days"]),
    )

    result = process_trend_narrative_envelope(_envelope(), now=NOW)

    assert result["control_revision"] == "disabled-v2"
    assert result["slots_consumed"] == 0
    assert result["transport_started"] == 0
    assert result["suppressed"] == 4
    assert generation_calls == []
    assert not TrendNarrative.objects.filter(call_slot_consumed=True).exists()
    assert set(
        TrendNarrative.objects.values_list("error_code", flat=True)
    ) == {"provider_calls_disabled"}


def test_snapshot_soft_timeout_stops_before_later_windows(monkeypatch):
    config = HeadlineNarrativeConfig(provider_calls_enabled=True)
    attempted_windows: list[int] = []
    monkeypatch.setattr(
        "monitor.trend_narrative_tasks._load_config",
        lambda: config,
    )

    def timeout(window_days, *, as_of, thresholds, evidence_policy):
        attempted_windows.append(window_days)
        raise SoftTimeLimitExceeded()

    monkeypatch.setattr(
        "monitor.trend_narrative_tasks.build_trend_analysis_snapshot",
        timeout,
    )

    with pytest.raises(SoftTimeLimitExceeded):
        process_trend_narrative_envelope(_envelope(), now=NOW)

    assert attempted_windows == [1]
    assert not TrendNarrative.objects.exists()


def test_generation_soft_timeout_stops_before_later_windows(monkeypatch):
    _config, _calls = _enable(monkeypatch)

    def timeout(snapshot, config):
        raise SoftTimeLimitExceeded()

    monkeypatch.setattr(
        "monitor.trend_narrative_tasks.generate_trend_narrative",
        timeout,
    )

    with pytest.raises(SoftTimeLimitExceeded):
        process_trend_narrative_envelope(_envelope(), now=NOW)

    assert TrendNarrative.objects.count() == 1
    attempt = TrendNarrative.objects.get()
    assert attempt.window_days == 1
    assert attempt.call_slot_consumed
    assert attempt.transport_started_at is not None
    assert attempt.transport_completed_at is None


def test_post_response_failure_records_transport_completion(monkeypatch):
    _config, _calls = _enable(monkeypatch)

    def mismatch(snapshot, config):
        generated = _result(snapshot, config)
        generated.semantic_fingerprint = "f" * 64
        return generated

    monkeypatch.setattr(
        "monitor.trend_narrative_tasks.generate_trend_narrative",
        mismatch,
    )

    result = process_trend_narrative_envelope(_envelope(), now=NOW)

    assert result["slots_consumed"] == 4
    assert result["failed"] == 4
    assert result["published"] == 0
    assert not TrendNarrative.objects.filter(
        transport_completed_at__isnull=True
    ).exists()


def test_provider_enable_fills_cold_cache_without_waiting_for_cadence(monkeypatch):
    disabled = HeadlineNarrativeConfig(provider_calls_enabled=False)
    monkeypatch.setattr(
        "monitor.trend_narrative_tasks._load_config",
        lambda: disabled,
    )
    monkeypatch.setattr(
        "monitor.trend_narrative_tasks.build_trend_analysis_snapshot",
        lambda window_days, *, as_of, thresholds, evidence_policy: _snapshot(
            window_days, as_of=as_of
        ),
    )
    process_trend_narrative_envelope(_envelope(), now=NOW)

    still_disabled_at = NOW + timedelta(seconds=30)
    still_disabled = process_trend_narrative_envelope(
        _envelope("cycle-b", completed_at=still_disabled_at),
        now=still_disabled_at,
    )

    assert still_disabled["not_due"] == 4
    assert TrendNarrative.objects.count() == 4

    _config, calls = _enable(monkeypatch)
    later = NOW + timedelta(minutes=1)
    result = process_trend_narrative_envelope(
        _envelope("cycle-c", completed_at=later),
        now=later,
    )

    assert result["slots_consumed"] == 4
    assert result["published"] == 4
    assert result["not_due"] == 0
    assert calls == [1, 7, 30, 365]


def test_one_window_failure_does_not_discard_other_publications(monkeypatch):
    _config, calls = _enable(monkeypatch, fail_window=7)

    result = process_trend_narrative_envelope(_envelope(), now=NOW)

    assert result["slots_consumed"] == 4
    assert result["published"] == 3
    assert result["failed"] == 1
    assert calls == [1, 7, 30, 365]
    assert TrendNarrative.objects.filter(status="failed").count() == 1
    assert TrendNarrative.objects.filter(is_current=True).count() == 3


def test_one_snapshot_failure_does_not_discard_other_publications(monkeypatch):
    _config, calls = _enable(monkeypatch)
    normal_builder = __import__(
        "monitor.trend_narrative_tasks",
        fromlist=["build_trend_analysis_snapshot"],
    ).build_trend_analysis_snapshot

    def build(window_days, *, as_of, thresholds, evidence_policy):
        if window_days == 7:
            raise RuntimeError("fixture snapshot failure")
        return normal_builder(
            window_days,
            as_of=as_of,
            thresholds=thresholds,
            evidence_policy=evidence_policy,
        )

    monkeypatch.setattr(
        "monitor.trend_narrative_tasks.build_trend_analysis_snapshot",
        build,
    )

    result = process_trend_narrative_envelope(_envelope(), now=NOW)

    assert result["slots_consumed"] == 3
    assert result["published"] == 3
    assert result["failed"] == 1
    assert result["errors"] == ["7d:snapshot_failed"]
    assert calls == [1, 30, 365]
    failure = TrendNarrative.objects.get(window_days=7)
    assert failure.status == TrendNarrative.Status.SUPPRESSED
    assert failure.error_code == "snapshot_failed"
    assert failure.call_slot_consumed is False
    assert failure.latest_checked_facts["failure_stage"] == "snapshot"


def test_empty_candidate_snapshot_records_no_call_and_skips_provider(monkeypatch):
    config, calls = _enable(monkeypatch)

    def empty_snapshot(window_days, *, as_of, thresholds, evidence_policy):
        snapshot = _snapshot(window_days, as_of=as_of)
        snapshot["candidates"] = []
        snapshot["selection"]["candidate_count"] = 0
        return snapshot

    monkeypatch.setattr(
        "monitor.trend_narrative_tasks.build_trend_analysis_snapshot",
        empty_snapshot,
    )

    result = process_trend_narrative_envelope(_envelope(), now=NOW)

    assert config.provider_calls_enabled
    assert result["slots_consumed"] == 0
    assert result["suppressed"] == 4
    assert calls == []
    assert TrendNarrative.objects.filter(status="checked").count() == 4


def test_failure_backoff_retries_at_window_cadence_boundary(
    monkeypatch,
):
    config, calls = _enable(monkeypatch, fail_window=365)
    first = process_trend_narrative_envelope(_envelope(), now=NOW)
    calls.clear()

    cadence_minutes = config.cadence_minutes[365]
    before = NOW + timedelta(minutes=cadence_minutes - 1)
    blocked = process_trend_narrative_envelope(
        _envelope("cycle-b", completed_at=before),
        now=before,
    )
    assert blocked["slots_consumed"] == 0
    assert blocked["suppressed"] == 1
    assert calls == []

    boundary = NOW + timedelta(minutes=cadence_minutes)
    _enable(monkeypatch)
    retried = process_trend_narrative_envelope(
        _envelope("cycle-c", completed_at=boundary),
        now=boundary,
    )

    assert first["failed"] == 1
    assert retried["slots_consumed"] == 1
    assert retried["published"] == 1


def test_consecutive_failure_counter_drives_bounded_backoff(monkeypatch):
    config, _calls = _enable(monkeypatch, fail_window=365)
    process_trend_narrative_envelope(_envelope(), now=NOW)
    first = TrendNarrative.objects.get(window_days=365, status="failed")
    assert first.consecutive_failures == 1

    second_at = NOW + timedelta(minutes=config.cadence_minutes[365])
    process_trend_narrative_envelope(
        _envelope("cycle-b", completed_at=second_at),
        now=second_at,
    )
    second = TrendNarrative.objects.filter(
        window_days=365,
        status="failed",
    ).latest("pk")

    assert second.consecutive_failures == 2
    assert second.next_attempt_at == second_at + timedelta(
        minutes=config.stale_minutes[365]
    )


@pytest.mark.parametrize(
    ("window_days", "expected_first_delay"),
    [(1, 30), (7, 60), (30, 360), (365, 1440)],
)
def test_first_failure_waits_one_window_cadence(
    monkeypatch,
    window_days,
    expected_first_delay,
):
    _config, _calls = _enable(monkeypatch, fail_window=window_days)

    process_trend_narrative_envelope(_envelope(), now=NOW)

    failure = TrendNarrative.objects.get(window_days=window_days, status="failed")
    assert failure.next_attempt_at == NOW + timedelta(
        minutes=expected_first_delay
    )


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
        TrendNarrative.objects.order_by("window_days").values_list(
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
