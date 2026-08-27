"""PostgreSQL contracts for the durable per-brand narrative stage graph."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from core.models import (
    Brand,
    BrandTrendNarrative,
    TrendNarrativeProviderCall,
    TrendNarrativeRun,
    TrendNarrativeVisibleRun,
    TrendNarrativeWorkSlot,
)
from monitor.trend_narrative_generation import PerBrandProviderResponse
from monitor.trend_narrative_tasks import (
    _provider_budget_reason,
    execute_per_brand_stage,
    finalize_per_brand_run,
    initialize_per_brand_snapshot,
    reconcile_per_brand_trend_narratives,
)
from x_monitor.config import HeadlineNarrativeConfig

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]

NOW = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)


def _config(**overrides) -> HeadlineNarrativeConfig:
    return HeadlineNarrativeConfig(
        activation_state="owner_override",
        provider_calls_enabled=True,
        enqueue_enabled=True,
        **overrides,
    )


def _envelope(source: str, at: datetime) -> dict[str, object]:
    return {
        "schema_version": 1,
        "source_cycle_id": source,
        "completed_at": at.isoformat(),
        "outcome": "completed",
        "dry_run": False,
    }


def _snapshot(count: int, *, window_days: int = 1) -> dict[str, object]:
    return {
        "packet_schema_version": 3,
        "window_days": window_days,
        "as_of": NOW.isoformat(),
        "baseline_context": {"kind": "prior_period", "label_en": "prior"},
        "dossiers": [
            {
                "brand_key": f"brand-{index:02d}",
                "display_name_en": f"Brand {index:02d}",
                "display_name_zh_cn": f"品牌 {index:02d}",
                "outcome": "narrative_eligible",
                "facts": [
                    {
                        "fact_id": f"brand-{index:02d}:post_count",
                        "display_en": "10 posts",
                        "display_zh_cn": "10条帖子",
                    }
                ],
                "evidence": [],
                "corpus_signals": [],
            }
            for index in range(count)
        ],
    }


def _narrative(brand_key: str) -> dict[str, object]:
    return {
        "brand_key": brand_key,
        "headline_en": f"{brand_key} conversation focused on practical use.",
        "headline_zh_cn": f"{brand_key}讨论集中在实际使用。",
        "secondary_en": "Users discussed setup and performance tradeoffs.",
        "secondary_zh_cn": "用户讨论了设置与性能之间的权衡。",
        "narrative_kind": "content_shift",
        "confidence": "medium",
        "headline_proposition_ids": [f"{brand_key}:p1"],
        "secondary_proposition_ids": [f"{brand_key}:p2"],
        "propositions": [
            {
                "proposition_id": f"{brand_key}:p1",
                "output_section": "headline",
                "claim_en": f"{brand_key} conversation focused on practical use.",
                "claim_zh_cn": f"{brand_key}讨论集中在实际使用。",
                "claim_type": "content_summary",
                "fact_ids": [],
                "evidence_ids": [],
            },
            {
                "proposition_id": f"{brand_key}:p2",
                "output_section": "secondary",
                "claim_en": "Users discussed setup and performance tradeoffs.",
                "claim_zh_cn": "用户讨论了设置与性能之间的权衡。",
                "claim_type": "content_summary",
                "fact_ids": [],
                "evidence_ids": [],
            },
        ],
        "events": [],
    }


def _provider_raw(call: TrendNarrativeProviderCall) -> str:
    envelope = call.request_packet["envelope"]
    if call.stage == TrendNarrativeProviderCall.Stage.RANK:
        dossiers = envelope["analysis_packet"]["dossiers"]
        payload = {
            "rank_response_schema_version": 1,
            "packet_hash": envelope["packet_hash"],
            "batch_key": envelope["batch_key"],
            "ordered_brands": [
                {
                    "brand_key": dossier["brand_key"],
                    "confidence": "medium",
                    "reason_refs": [
                        {"kind": "fact", "id": dossier["facts"][0]["fact_id"]}
                    ],
                }
                for dossier in reversed(dossiers)
            ],
        }
    elif call.stage == TrendNarrativeProviderCall.Stage.EDITOR:
        payload = {
            "editor_response_schema_version": 1,
            "packet_hash": envelope["packet_hash"],
            "batch_key": envelope["batch_key"],
            "brands": [_narrative(key) for key in envelope["manifest_brand_keys"]],
        }
    else:
        editor = json.loads(envelope["editor_response_raw"])
        decisions = []
        for narrative in editor["brands"]:
            hold = narrative["brand_key"] == "brand-00"
            decisions.append(
                {
                    "brand_key": narrative["brand_key"],
                    "decision": "hold" if hold else "approve",
                    "narrative": None if hold else narrative,
                    "hold_code": "unsupported_causality" if hold else None,
                }
            )
        payload = {
            "critic_response_schema_version": 1,
            "packet_hash": envelope["packet_hash"],
            "batch_key": envelope["batch_key"],
            "decisions": decisions,
        }
    return json.dumps(payload, separators=(",", ":"))


def test_work_slots_keep_one_active_and_only_the_latest_queued_cutoff(monkeypatch):
    config = _config()
    monkeypatch.setattr("monitor.trend_narrative_tasks._load_config", lambda: config)
    scheduled: list[tuple[str, dict[str, object]]] = []

    def enqueue(kind, **kwargs):
        scheduled.append((kind, kwargs))

    reconcile_per_brand_trend_narratives(
        _envelope("cycle-a", NOW), now=NOW, enqueue=enqueue
    )
    reconcile_per_brand_trend_narratives(
        _envelope("cycle-b", NOW + timedelta(seconds=10)),
        now=NOW + timedelta(seconds=10),
        enqueue=enqueue,
    )
    reconcile_per_brand_trend_narratives(
        _envelope("cycle-c", NOW + timedelta(seconds=20)),
        now=NOW + timedelta(seconds=20),
        enqueue=enqueue,
    )

    assert len(scheduled) == 4
    for slot in TrendNarrativeWorkSlot.objects.all():
        assert slot.active_source_cycle_id == "cycle-a"
        assert slot.queued_source_cycle_id == "cycle-c"
        assert slot.queued_facts_as_of == NOW + timedelta(seconds=20)


def test_lost_snapshot_handoff_is_reclaimed_only_after_lease_expiry(monkeypatch):
    config = _config()
    monkeypatch.setattr("monitor.trend_narrative_tasks._load_config", lambda: config)
    attempts: list[dict[str, object]] = []

    def broken(kind, **kwargs):
        attempts.append(kwargs)
        raise RuntimeError("broker unavailable")

    envelope = _envelope("cycle-a", NOW)
    reconcile_per_brand_trend_narratives(envelope, now=NOW, enqueue=broken)
    reconcile_per_brand_trend_narratives(
        envelope, now=NOW + timedelta(seconds=30), enqueue=broken
    )
    reconcile_per_brand_trend_narratives(
        envelope,
        now=NOW + timedelta(seconds=config.lease_seconds + 1),
        enqueue=broken,
    )

    assert len(attempts) == 8
    assert {attempt["fence"] for attempt in attempts[:4]} == {1}
    assert {attempt["fence"] for attempt in attempts[4:]} == {2}


def test_twenty_brands_use_one_rank_four_editor_four_critic_calls(monkeypatch):
    config = _config()
    snapshot = _snapshot(20)
    Brand.objects.bulk_create(
        [
            Brand(
                nickname=dossier["brand_key"],
                display_name=dossier["display_name_en"],
                display_name_en=dossier["display_name_en"],
                display_name_zh_cn=dossier["display_name_zh_cn"],
            )
            for dossier in snapshot["dossiers"]
        ]
    )
    queued: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr("monitor.trend_narrative_tasks._load_config", lambda: config)
    monkeypatch.setattr(
        "monitor.trend_narrative_tasks.build_trend_analysis_snapshot",
        lambda *_args, **_kwargs: snapshot,
    )
    monkeypatch.setattr(
        "monitor.trend_narrative_tasks._enqueue_per_brand_stage",
        lambda kind, **kwargs: queued.append((kind, kwargs)),
    )
    monkeypatch.setattr("monitor.trend_narrative_tasks.timezone.now", lambda: NOW)

    run = initialize_per_brand_snapshot(
        source_cycle_id="cycle-20",
        window_days=1,
        facts_as_of=NOW,
        enqueue=lambda kind, **kwargs: queued.append((kind, kwargs)),
    )
    assert run is not None
    while queued:
        kind, kwargs = queued.pop(0)
        if kind == "stage":
            call = TrendNarrativeProviderCall.objects.get(pk=kwargs["call_id"])
            raw = _provider_raw(call)
            monkeypatch.setattr(
                "monitor.trend_narrative_tasks.execute_per_brand_provider_request",
                lambda *_args, _raw=raw, **_kwargs: PerBrandProviderResponse(
                    raw_text=_raw,
                    input_tokens=100,
                    output_tokens=100,
                    latency_ms=10,
                ),
            )
            execute_per_brand_stage(**kwargs, now=NOW)
        elif kind == "finalize":
            finalize_per_brand_run(kwargs["run_id"], now=NOW + timedelta(seconds=1))
        else:  # pragma: no cover - a promoted snapshot would be a regression here
            raise AssertionError(kind)

    run.refresh_from_db()
    assert run.status == TrendNarrativeRun.Status.ACTIVE
    assert TrendNarrativeProviderCall.objects.filter(run=run).count() == 9
    assert (
        list(
            TrendNarrativeProviderCall.objects.filter(run=run)
            .values_list("stage", flat=True)
            .order_by("pk")
        ).count("rank")
        == 1
    )
    assert (
        TrendNarrativeProviderCall.objects.filter(run=run, stage="editor").count() == 4
    )
    assert (
        TrendNarrativeProviderCall.objects.filter(run=run, stage="critic").count() == 4
    )
    assert [len(batch["brand_keys"]) for batch in run.batch_manifest] == [5, 5, 5, 5]
    assert run.internal_order[0] == "brand-19"
    assert (
        BrandTrendNarrative.objects.filter(
            run=run, status=BrandTrendNarrative.Status.APPROVED
        ).count()
        == 19
    )
    assert (
        BrandTrendNarrative.objects.get(run=run, brand_key_snapshot="brand-00").status
        == BrandTrendNarrative.Status.UNAVAILABLE
    )
    assert TrendNarrativeVisibleRun.objects.get(window_days=1).run_id == run.pk
    assert not TrendNarrativeWorkSlot.objects.get(window_days=1).active_source_cycle_id


def test_budget_counts_reserved_work_and_stops_before_the_next_transport():
    run = TrendNarrativeRun.objects.create(
        source_cycle_id="budget-cycle",
        window_days=1,
        facts_as_of=NOW,
        packet_schema_version=3,
        snapshot=_snapshot(1),
        brand_manifest=["brand-00"],
    )
    config = _config(
        per_brand_expected_max_brands=1,
        per_brand_call_cap=3,
    )
    request = {
        "model": config.model,
        "max_tokens": 100,
        "thinking": {"type": "disabled"},
        "system": "test",
        "messages": [{"role": "user", "content": "test"}],
    }
    for index in range(3):
        TrendNarrativeProviderCall.objects.create(
            run=run,
            stage="rank" if index == 0 else "editor",
            batch_key=f"batch-{index}",
            request_identity=f"budget-{index}",
            request_hash=f"{index:064x}",
            request_packet={"provider_request": request},
            reserved_at=NOW,
        )

    assert (
        _provider_budget_reason(run, next_request=request, config=config) == "call_cap"
    )


def test_active_capacity_fails_closed_when_p95_drain_exceeds_arrival_rate():
    with pytest.raises(ValueError, match="drain rate"):
        _config(per_brand_p95_latency_seconds="120")
