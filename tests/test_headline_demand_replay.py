from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from core.models import (
    BrandTrendNarrative,
    TrendNarrativeProviderCall,
    TrendNarrativeRun,
)
from monitor.trend_narrative_replay import build_headline_demand_replay
from x_monitor.config import HeadlineNarrativeConfig

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]

NOW = datetime(2026, 9, 11, 0, 0, tzinfo=UTC)


def _config() -> HeadlineNarrativeConfig:
    return HeadlineNarrativeConfig(
        activation_state="owner_override",
        demand_shaping_enabled=True,
        critic_risk_routing_enabled=True,
        critic_audit_percent=0,
    )


def _snapshot(*, changed_brand: str | None = None) -> dict[str, object]:
    dossiers = []
    for index in range(6):
        brand_key = f"brand-{index}"
        dossiers.append(
            {
                "brand_key": brand_key,
                "display_name_en": f"Brand {index}",
                "display_name_zh_cn": f"品牌 {index}",
                "outcome": "narrative_eligible",
                "enrichment_coverage": {
                    "translation_status": "complete",
                    "classification_status": "complete",
                },
                "facts": [
                    {
                        "fact_id": f"{brand_key}:share",
                        "unit": "percent",
                        "family": "post_type",
                        "metric": "share_pct",
                        "direction": "increase",
                        "current_value": (
                            "55" if brand_key == changed_brand else "50"
                        ),
                        "baseline_value": "40",
                        "coverage_scope": {"status": "complete"},
                    }
                ],
                "family_summaries": {},
                "shape_summary": {},
                "corpus_signals": [],
                "evidence": [],
            }
        )
    return {
        "packet_schema_version": 3,
        "window_days": 1,
        "as_of": NOW.isoformat(),
        "baseline_context": {"kind": "prior_period"},
        "dossiers": dossiers,
    }


def _run(*, index: int, snapshot: dict[str, object]) -> TrendNarrativeRun:
    run = TrendNarrativeRun.objects.create(
        source_cycle_id=f"cycle-{index}",
        window_days=1,
        facts_as_of=NOW + timedelta(hours=index),
        packet_schema_version=3,
        snapshot=snapshot,
        brand_manifest=[f"brand-{brand_index}" for brand_index in range(6)],
    )
    for stage, batch_key in (
        ("rank", "rank"),
        ("editor", "1d:001"),
        ("editor", "1d:002"),
        ("critic", "1d:001"),
        ("critic", "1d:002"),
    ):
        response = {
            "raw_text": json.dumps(
                {
                    "editor_response_schema_version": 1,
                    "packet_hash": f"packet-{index}-{batch_key}",
                    "batch_key": batch_key,
                    "brands": [],
                }
            )
        }
        TrendNarrativeProviderCall.objects.create(
            run=run,
            stage=stage,
            batch_key=batch_key,
            request_identity=f"request-{index}-{stage}-{batch_key}",
            request_hash=f"request-hash-{index}-{stage}-{batch_key}",
            response_hash=f"response-hash-{index}-{stage}-{batch_key}",
            request_packet={
                "envelope": {
                    "packet_hash": f"packet-{index}-{batch_key}",
                    "batch_key": batch_key,
                    "analysis_packet": {"dossiers": []},
                }
            },
            response_payload=response,
            state=TrendNarrativeProviderCall.State.COMPLETED,
            reserved_at=run.facts_as_of,
            sent_at=run.facts_as_of,
            completed_at=run.facts_as_of,
            input_tokens=100,
            output_tokens=50,
        )
    for brand_index in range(6):
        brand_key = f"brand-{brand_index}"
        BrandTrendNarrative.objects.create(
            run=run,
            brand_key_snapshot=brand_key,
            brand_name_en_snapshot=f"Brand {brand_index}",
            brand_name_zh_cn_snapshot=f"品牌 {brand_index}",
            status=BrandTrendNarrative.Status.APPROVED,
            headline_en="Headline",
            headline_zh_cn="标题",
            secondary_en="Secondary",
            secondary_zh_cn="补充",
            attempted_at=run.facts_as_of,
            verified_at=run.facts_as_of,
        )
    return run


def test_replay_compacts_unchanged_brands_without_losing_last_good() -> None:
    _run(index=0, snapshot=_snapshot())
    _run(index=1, snapshot=_snapshot(changed_brand="brand-0"))

    report = build_headline_demand_replay(
        start=NOW,
        end=NOW + timedelta(hours=3),
        windows=[1],
        source_identity="fixture",
        candidate_revision="test-revision",
        config=_config(),
    )

    assert report["selection"] == {
        "dossiers": 12,
        "selected_materially_changed": 7,
        "suppressed_unchanged": 5,
        "suppression_pct": 41.67,
        "eligible_dossiers": 12,
        "selected_eligible_dossiers": 7,
        "historical_editor_batches": 4,
        "replayed_editor_batches": 3,
        "saved_editor_batches_requiring_critic": 0,
    }
    assert report["workloads"]["historical"]["provider_calls"] == 10
    assert report["workloads"]["new_policy_upper_bound"]["provider_calls"] == 8
    assert report["workloads"]["new_policy_risk_routed"]["provider_calls"] == 5
    assert report["output"]["historical_last_good_coverage"] == 1.0
    assert report["output"]["replayed_last_good_coverage"] == 1.0
    assert report["decision"]["passed"] is True
