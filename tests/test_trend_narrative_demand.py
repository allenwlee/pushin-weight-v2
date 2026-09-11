from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from core.models import Brand, TrendNarrativeDemand, TrendNarrativeRun
from monitor.trend_narrative_demand import (
    mark_run_demands_satisfied,
    material_input_fingerprint,
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


def _material_dossier() -> dict[str, object]:
    return {
        "brand_key": "minimax",
        "outcome": "narrative_eligible",
        "enrichment_coverage": {
            "translation_status": "complete",
            "classification_status": "complete",
            "total_post_count": 100,
            "fully_enriched_count": 100,
            "translation_succeeded_count": 100,
            "classification_succeeded_count": 100,
        },
        "comparison_status": {
            "allowed": True,
            "current_post_count": 100,
            "prior_post_count": 80,
            "suppression_reasons": [],
            "selected_coverage": {
                "state": "sufficient",
                "ratio": "0.99",
                "earliest_at": "2026-09-01T00:00:00Z",
                "known_backlog_overlap": False,
            },
            "prior_coverage": {
                "state": "sufficient",
                "ratio": "0.98",
                "earliest_at": "2026-08-01T00:00:00Z",
                "known_backlog_overlap": False,
            },
        },
        "family_summaries": {
            "post_type": {
                "status": "available",
                "current_leader": "research_explanations",
                "largest_change": "job_listings",
                "denominator": 100,
            }
        },
        "facts": [
            {
                "fact_id": "minimax:research-share",
                "unit": "percent",
                "family": "post_type",
                "metric": "research_share_pct",
                "direction": "increase",
                "label_key": "research_explanations",
                "current_value": "51",
                "baseline_value": "40",
                "coverage_scope": {"status": "complete", "covered_post_count": 100},
                "display_en": "51%",
            }
        ],
        "shape_summary": {
            "direction": "increase",
            "comparison_state": "available",
            "total_change_pct": "11",
            "start_segment_post_count": 100,
            "end_segment_post_count": 102,
            "peak": {"at": "2026-09-10T01:00:00Z", "post_count": 52},
            "trough": {"at": "2026-09-10T00:00:00Z", "post_count": 48},
            "dominant_transition": {
                "from": "2026-09-10T00:00:00Z",
                "to": "2026-09-10T01:00:00Z",
                "post_count_change": 4,
                "net_change_share_pct": "11",
            },
        },
        "corpus_signals": [
            {
                "corpus_signal_id": "signal-research",
                "phrase": "new research",
                "prevalence": 100,
                "prior_prevalence": 80,
                "peer_brand_count": 20,
                "representative_excerpt": "A new research result",
                "representative_evidence_ids": ["evidence-2", "evidence-1"],
                "burst_interval": {"start_bucket": 1, "end_bucket": 2},
            }
        ],
        "evidence": [
            {
                "evidence_id": "evidence-2",
                "created_at": "2026-09-10T01:00:00Z",
                "post_type_keys": ["research_explanations", "announcements_releases"],
                "roles": ["supporting_context"],
                "source_cluster_id": "cluster-2",
                "original_text": "A new research result",
                "_interactions": 400,
                "_ranks": {"top_engaged_original": 1},
            },
            {
                "evidence_id": "evidence-1",
                "created_at": "2026-09-10T00:00:00Z",
                "post_type_keys": ["research_explanations"],
                "roles": ["official_or_catalyst"],
                "source_cluster_id": "cluster-1",
                "original_text": "Earlier context",
                "_interactions": 200,
                "_ranks": {"top_engaged_original": 2},
            },
        ],
    }


def test_material_fingerprint_ignores_nonmaterial_jitter_and_order() -> None:
    config = _config()
    original = _material_dossier()
    jittered = deepcopy(original)
    jittered["facts"][0]["current_value"] = "52"
    jittered["facts"][0]["display_en"] = "52%"
    jittered["enrichment_coverage"]["total_post_count"] = 101
    jittered["family_summaries"]["post_type"]["denominator"] = 101
    jittered["shape_summary"]["peak"]["at"] = "2026-09-10T01:05:00Z"
    jittered["shape_summary"]["dominant_transition"]["to"] = (
        "2026-09-10T01:05:00Z"
    )
    jittered["corpus_signals"][0]["burst_interval"] = {
        "start_bucket": 0,
        "end_bucket": 1,
    }
    jittered["evidence"].reverse()
    for evidence in jittered["evidence"]:
        evidence["_interactions"] += 999
        evidence["_ranks"] = {"top_engaged_original": 99}

    assert material_input_fingerprint(
        original, config=config
    ) == material_input_fingerprint(jittered, config=config)


def test_material_fingerprint_changes_for_semantic_evidence_or_fact_band() -> None:
    config = _config()
    original = _material_dossier()
    changed_fact = deepcopy(original)
    changed_fact["facts"][0]["current_value"] = "54"
    changed_evidence = deepcopy(original)
    changed_evidence["evidence"][0]["original_text"] = "A corrected research result"

    original_fingerprint = material_input_fingerprint(original, config=config)
    assert material_input_fingerprint(changed_fact, config=config) != original_fingerprint
    assert (
        material_input_fingerprint(changed_evidence, config=config)
        != original_fingerprint
    )


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
