"""The headline status command is observable and side-effect free."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from io import StringIO

import pytest
from django.core.management import call_command

from core.models import Brand, TrendNarrative, TrendNarrativeSubject
from monitor.trend_narrative_lifecycle import (
    mark_transport_completed,
    mark_transport_started,
    publish_generation,
    reserve_generation,
)

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def test_empty_status_is_redacted_and_does_not_call_provider_or_queue(monkeypatch):
    monkeypatch.setenv("X_MONITOR_HEADLINE_API_KEY", "must-not-appear")
    monkeypatch.setattr(
        "monitor.trend_narrative_generation.generate_trend_narrative",
        lambda *_args, **_kwargs: pytest.fail("status called provider"),
    )
    monkeypatch.setattr(
        "monitor.tasks.refresh_trend_narratives.apply_async",
        lambda *_args, **_kwargs: pytest.fail("status enqueued work"),
    )
    stdout = StringIO()

    call_command("headline_status", "--json", stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert [row["window_days"] for row in payload["windows"]] == [1, 7, 30, 365]
    assert all(row["state"] == "disabled" for row in payload["windows"])
    assert all(row["output_schema_version"] is None for row in payload["windows"])
    assert all(row["selected_candidate_ids"] == [] for row in payload["windows"])
    assert all(row["subjects"] == [] for row in payload["windows"])
    assert all(row["consecutive_failures"] == 0 for row in payload["windows"])
    assert "must-not-appear" not in stdout.getvalue()
    assert TrendNarrative.objects.count() == 0


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
        publication_epoch=4,
        prompt_version="headline-v4-analytical",
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
