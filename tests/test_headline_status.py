"""The headline status command is observable and side-effect free."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from core.models import (
    Brand,
    BrandTrendNarrative,
    TrendNarrative,
    TrendNarrativeProviderCall,
    TrendNarrativeRun,
    TrendNarrativeSubject,
    TrendNarrativeWorkSlot,
)
from monitor.trend_narrative_lifecycle import (
    mark_transport_completed,
    mark_transport_started,
    publish_generation,
    reserve_generation,
)

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def test_empty_status_is_redacted_and_does_not_call_provider_or_queue(monkeypatch):
    monkeypatch.setenv("X_MONITOR_HEADLINE_API_KEY", "must-not-appear")
    monkeypatch.setenv("X_MONITOR_HEADLINE_SERVING_ENABLED", "True")
    monkeypatch.setenv("X_MONITOR_HEADLINE_ENQUEUE_ENABLED", "True")
    monkeypatch.setenv("X_MONITOR_HEADLINE_PROVIDER_CALLS_ENABLED", "True")
    monkeypatch.setenv("X_MONITOR_HEADLINE_ACTIVATION_STATE", "pending")
    monkeypatch.setattr(
        "monitor.trend_narrative_generation.execute_per_brand_provider_request",
        lambda *_args, **_kwargs: pytest.fail("status called provider"),
    )
    monkeypatch.setattr(
        "monitor.tasks.refresh_trend_narratives.apply_async",
        lambda *_args, **_kwargs: pytest.fail("status enqueued work"),
    )
    stdout = StringIO()

    call_command("headline_status", "--json", stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert payload["activation_state"] == "pending"
    assert payload["serving_enabled"] is True
    assert payload["enqueue_enabled"] is True
    assert payload["provider_calls_enabled"] is True
    assert payload["serving_active"] is False
    assert payload["enqueue_active"] is False
    assert payload["provider_calls_active"] is False
    assert [row["window_days"] for row in payload["windows"]] == [1, 7, 30, 365]
    assert all(row["state"] == "disabled" for row in payload["windows"])
    assert all(row["output_schema_version"] is None for row in payload["windows"])
    assert all(row["selected_candidate_ids"] == [] for row in payload["windows"])
    assert all(row["subjects"] == [] for row in payload["windows"])
    assert all(row["consecutive_failures"] == 0 for row in payload["windows"])
    assert "must-not-appear" not in stdout.getvalue()
    assert TrendNarrative.objects.count() == 0


def test_plain_status_distinguishes_requested_and_active_controls(monkeypatch):
    monkeypatch.setenv("X_MONITOR_HEADLINE_SERVING_ENABLED", "True")
    monkeypatch.setenv("X_MONITOR_HEADLINE_ENQUEUE_ENABLED", "True")
    monkeypatch.setenv("X_MONITOR_HEADLINE_PROVIDER_CALLS_ENABLED", "True")
    monkeypatch.setenv("X_MONITOR_HEADLINE_ACTIVATION_STATE", "pending")
    stdout = StringIO()

    call_command("headline_status", stdout=stdout)

    first_line = stdout.getvalue().splitlines()[0]
    assert "activation=pending" in first_line
    assert "requested[serving=True enqueue=True provider=True]" in first_line
    assert "active[serving=False enqueue=False provider=False]" in first_line


def test_status_reports_schema_two_subjects_without_private_evidence():
    now = datetime(2026, 8, 13, 8, 0, tzinfo=UTC)
    brand = Brand.objects.create(
        nickname="minimax",
        display_name="MiniMax",
        display_name_en="MiniMax",
        display_name_zh_cn="MiniMax",
    )
    facts = {
        "snapshot_schema_version": 1,
        "window_days": 1,
        "as_of": now.isoformat().replace("+00:00", "Z"),
        "coverage": {"state": "sufficient", "ratio": "1.000000"},
        "candidates": [
            {
                "candidate_id": "minimax:full_window",
                "brand_key": brand.pk,
                "display_name_en": "MiniMax",
                "display_name_zh_cn": "MiniMax",
                "evidence": [],
            }
        ],
    }
    row = reserve_generation(
        source_cycle_id="cycle-status",
        window_days=1,
        facts_as_of=now,
        semantic_fingerprint="a" * 64,
        generation_facts=facts,
        publication_epoch=5,
        prompt_version="headline-v5-analytical",
        provider="deepseek",
        provider_host="api.deepseek.com",
        llm_model_name="deepseek-v4-pro",
        owner="worker-status",
        now=now,
        lease_seconds=90,
        output_schema_version=2,
    )
    assert row is not None
    assert mark_transport_started(
        row.pk,
        owner="worker-status",
        fence=row.claim_fence,
        now=now,
    )
    assert mark_transport_completed(
        row.pk,
        owner="worker-status",
        fence=row.claim_fence,
        now=now + timedelta(milliseconds=500),
    )
    assert publish_generation(
        row.pk,
        owner="worker-status",
        fence=row.claim_fence,
        body_en="MiniMax attention rises and holds.",
        body_zh_cn="MiniMax 关注度上升后保持稳定。",
        output_hash="b" * 64,
        input_tokens=100,
        output_tokens=40,
        latency_ms=200,
        now=now + timedelta(seconds=1),
        observations_en=["Attention rises and then holds."],
        observations_zh_cn=["讨论热度上升后保持稳定。"],
        selected_candidate_ids=["minimax:full_window"],
        claims=[
            {
                "observation_index": -1,
                "candidate_ids": ["minimax:full_window"],
                "families": ["volume"],
                "evidence_ids": [],
            },
            {
                "observation_index": 0,
                "candidate_ids": ["minimax:full_window"],
                "families": ["volume"],
                "evidence_ids": [],
            }
        ],
        subjects=[
            {
                "position": 0,
                "support_type": "measured_candidate",
                "entity_type": "brand",
                "identity_type": "brand",
                "canonical_key_snapshot": "minimax",
                "name_en_snapshot": "MiniMax",
                "name_zh_cn_snapshot": "MiniMax",
                "candidate_id": "minimax:full_window",
                "evidence_ids": [],
            }
        ],
    )
    TrendNarrativeSubject.objects.create(
        trend_narrative=row,
        position=1,
        support_type="evidence_only",
        entity_type="model",
        identity_type="unresolved",
        observed_name="PrivateObservedName",
        name_en_snapshot="PrivateObservedName",
        name_zh_cn_snapshot="PrivateObservedName",
        evidence_ids=["private-evidence-one", "private-evidence-two"],
    )
    stdout = StringIO()

    call_command("headline_status", "--json", stdout=stdout)

    payload = json.loads(stdout.getvalue())
    status = payload["windows"][0]
    assert status["output_schema_version"] == 2
    assert status["selected_candidate_ids"] == ["minimax:full_window"]
    assert status["subjects"] == [
        {
            "position": 0,
            "support_type": "measured_candidate",
            "entity_type": "brand",
            "identity_type": "brand",
            "key": "minimax",
        },
        {
            "position": 1,
            "support_type": "evidence_only",
            "entity_type": "model",
            "identity_type": "unresolved",
            "key": None,
        },
    ]
    assert "private-evidence" not in stdout.getvalue()
    assert "PrivateObservedName" not in stdout.getvalue()


def test_status_reports_safe_per_brand_run_transport_and_backlog_diagnostics():
    now = timezone.now()
    alpha = Brand.objects.create(
        nickname="alpha",
        display_name="Alpha",
        display_name_en="Alpha",
        display_name_zh_cn="阿尔法",
    )
    bravo = Brand.objects.create(
        nickname="bravo",
        display_name="Bravo",
        display_name_en="Bravo",
        display_name_zh_cn="布拉沃",
    )
    run = TrendNarrativeRun.objects.create(
        source_cycle_id="per-brand-status",
        window_days=1,
        facts_as_of=now - timedelta(minutes=10),
        packet_schema_version=3,
        snapshot={
            "dossiers": [
                {"brand_key": "alpha", "outcome": "narrative_eligible"},
                {"brand_key": "bravo", "outcome": "narrative_eligible"},
                {"brand_key": "charlie", "outcome": "narrative_eligible"},
            ],
            "private_packet_must_not_appear": "do-not-expose",
        },
        brand_manifest=["alpha", "bravo", "charlie"],
    )
    approved = BrandTrendNarrative.objects.create(
        run=run,
        brand=alpha,
        brand_key_snapshot="alpha",
        brand_name_en_snapshot="Alpha",
        brand_name_zh_cn_snapshot="阿尔法",
        status=BrandTrendNarrative.Status.APPROVED,
        headline_en="Alpha headline",
        headline_zh_cn="阿尔法标题",
        secondary_en="Alpha secondary",
        secondary_zh_cn="阿尔法补充",
        critic_decision=BrandTrendNarrative.CriticDecision.APPROVE,
        attempted_at=now - timedelta(hours=2),
        verified_at=now - timedelta(hours=2),
        selected_evidence_packet={"private_evidence": "never expose"},
        final_critic_payload={"private_response": "never expose"},
    )
    BrandTrendNarrative.objects.create(
        run=run,
        brand=bravo,
        brand_key_snapshot="bravo",
        brand_name_en_snapshot="Bravo",
        brand_name_zh_cn_snapshot="布拉沃",
        status=BrandTrendNarrative.Status.HELD,
        attempted_at=now - timedelta(minutes=5),
        error_code="critic_rejected",
        last_good=approved,
    )
    TrendNarrativeProviderCall.objects.create(
        run=run,
        stage=TrendNarrativeProviderCall.Stage.RANK,
        batch_key="",
        request_identity="per-brand-status:rank",
        request_hash="a" * 64,
        request_packet={"private_request": "never expose"},
        state=TrendNarrativeProviderCall.State.FAILED,
        reserved_at=now - timedelta(minutes=9),
        sent_at=now - timedelta(minutes=8),
        error_code="rank_http_500",
    )
    TrendNarrativeProviderCall.objects.create(
        run=run,
        stage=TrendNarrativeProviderCall.Stage.EDITOR,
        batch_key="batch-01",
        request_identity="per-brand-status:editor",
        request_hash="b" * 64,
        request_packet={"private_request": "never expose"},
        state=TrendNarrativeProviderCall.State.AMBIGUOUS,
        reserved_at=now - timedelta(minutes=7),
        sent_at=now - timedelta(minutes=6),
        error_code="editor_timeout",
    )
    TrendNarrativeWorkSlot.objects.create(
        window_days=1,
        active_source_cycle_id=run.source_cycle_id,
        active_facts_as_of=run.facts_as_of,
        active_run=run,
        queued_source_cycle_id="newer-cycle",
        queued_facts_as_of=now,
    )
    stdout = StringIO()

    call_command("headline_status", "--json", stdout=stdout)

    payload = json.loads(stdout.getvalue())
    status = payload["windows"][0]["per_brand"]
    assert status["run"] == {
        "id": run.pk,
        "source_cycle_id": "per-brand-status",
        "status": TrendNarrativeRun.Status.PREPARING,
        "suspension_reason": "",
        "facts_as_of": run.facts_as_of.isoformat(),
        "created_at": run.created_at.isoformat(),
        "activated_at": None,
        "manifest_brand_count": 3,
        "outcome_count": 2,
        "terminal_outcome_count": 2,
        "missing_brand_keys": ["charlie"],
        "complete": False,
        "visible": False,
    }
    assert status["held_brands"] == [
        {
            "brand_key": "bravo",
            "status": "held",
            "critic_decision": "",
            "error_code": "critic_rejected",
            "latest_attempt_at": (now - timedelta(minutes=5)).isoformat(),
            "last_verification_at": (now - timedelta(hours=2)).isoformat(),
            "stale_duration_seconds": pytest.approx(7200, abs=2),
            "last_good_available": True,
        }
    ]
    assert status["latest_attempt_at"] == (now - timedelta(minutes=5)).isoformat()
    assert status["last_verification_at"] == (now - timedelta(hours=2)).isoformat()
    assert status["transport"]["failed_count"] == 1
    assert status["transport"]["ambiguous_count"] == 1
    assert status["transport"]["stages"]["rank"]["failure_codes"] == [
        "rank_http_500"
    ]
    assert status["transport"]["stages"]["editor"]["ambiguous_codes"] == [
        "editor_timeout"
    ]
    assert status["backlog"]["active"] is True
    assert status["backlog"]["queued"] is True
    assert status["backlog"]["queued_source_cycle_id"] == "newer-cycle"
    assert status["drain"] == {
        "eligible_brand_count": 3,
        "expected_call_count": 3,
        "recorded_call_count": 2,
        "worker_concurrency": 1,
        "p95_latency_seconds": 45.0,
        "estimated_run_drain_seconds": 135.0,
        "window_expected_arrival_calls_per_hour": 6.0,
        "fleet_expected_call_count_per_window": 17,
        "fleet_expected_arrival_calls_per_hour": pytest.approx(54.5416666667),
        "p95_capacity_calls_per_hour": 80.0,
        "fleet_expected_utilization": pytest.approx(0.6817708333),
    }
    assert "private_packet_must_not_appear" not in stdout.getvalue()
    assert "do-not-expose" not in stdout.getvalue()
    assert "private_evidence" not in stdout.getvalue()
    assert "private_response" not in stdout.getvalue()
    assert "private_request" not in stdout.getvalue()
