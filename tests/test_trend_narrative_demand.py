from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.models import Brand, TrendNarrativeDemand, TrendNarrativeRun
from monitor.trend_narrative_demand import (
    mark_run_demands_satisfied,
    record_trend_narrative_demand,
    select_demanded_snapshot,
)
from x_monitor.config import HeadlineNarrativeConfig

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]

NOW = datetime(2026, 9, 11, 4, 0, tzinfo=UTC)


def _config(**overrides) -> HeadlineNarrativeConfig:
    return HeadlineNarrativeConfig(
        activation_state="owner_override",
        demand_shaping_enabled=True,
        critic_audit_percent=0,
        **overrides,
    )


def _snapshot() -> dict[str, object]:
    return {
        "packet_schema_version": 3,
        "window_days": 1,
        "as_of": NOW.isoformat(),
        "baseline_context": {"kind": "prior_period"},
        "dossiers": [
            {
                "brand_key": "minimax",
                "display_name_en": "MiniMax",
                "display_name_zh_cn": "MiniMax",
                "outcome": "narrative_eligible",
                "enrichment_coverage": {"classification_status": "complete"},
                "facts": [{"fact_id": "minimax:volume", "display_en": "10 posts"}],
                "evidence": [],
                "corpus_signals": [],
            }
        ],
    }


def test_repeated_views_coalesce_and_unchanged_snapshot_is_suppressed():
    Brand.objects.create(nickname="minimax", display_name="MiniMax")
    config = _config()
    for minute in range(10):
        assert (
            record_trend_narrative_demand(
                brand_keys=["minimax"],
                window_days=1,
                reason="visible",
                config=config,
                now=NOW + timedelta(minutes=minute),
            )
            == 1
        )

    demand = TrendNarrativeDemand.objects.get()
    assert demand.request_count == 10
    assert demand.last_requested_at == NOW + timedelta(minutes=9)

    selected = select_demanded_snapshot(
        _snapshot(), config=config, now=NOW + timedelta(minutes=10)
    )
    assert [row["brand_key"] for row in selected["dossiers"]] == ["minimax"]
    run = TrendNarrativeRun.objects.create(
        source_cycle_id="demand-cycle",
        window_days=1,
        facts_as_of=NOW,
        packet_schema_version=3,
        snapshot=selected,
        brand_manifest=["minimax"],
    )
    assert mark_run_demands_satisfied(run, now=NOW + timedelta(minutes=11)) == 1

    unchanged = select_demanded_snapshot(
        _snapshot(), config=config, now=NOW + timedelta(minutes=12)
    )
    assert unchanged["dossiers"] == []
    demand.refresh_from_db()
    assert demand.state == TrendNarrativeDemand.State.SUPPRESSED
    assert demand.suppression_count == 1
    assert demand.last_decision_reason == "unchanged"


def test_operator_request_forces_one_refresh_without_changing_identity():
    Brand.objects.create(nickname="minimax", display_name="MiniMax")
    config = _config()
    record_trend_narrative_demand(
        brand_keys=["minimax"],
        window_days=1,
        reason="visible",
        config=config,
        now=NOW,
    )
    first = select_demanded_snapshot(_snapshot(), config=config, now=NOW)
    run = TrendNarrativeRun.objects.create(
        source_cycle_id="first",
        window_days=1,
        facts_as_of=NOW,
        packet_schema_version=3,
        snapshot=first,
        brand_manifest=["minimax"],
    )
    mark_run_demands_satisfied(run, now=NOW)
    record_trend_narrative_demand(
        brand_keys=["minimax"],
        window_days=1,
        reason="operator",
        config=config,
        now=NOW + timedelta(minutes=1),
        pinned=True,
    )

    forced = select_demanded_snapshot(
        _snapshot(), config=config, now=NOW + timedelta(minutes=2)
    )
    assert [row["brand_key"] for row in forced["dossiers"]] == ["minimax"]
    demand = TrendNarrativeDemand.objects.get()
    assert demand.last_decision_reason == "operator_refresh"
