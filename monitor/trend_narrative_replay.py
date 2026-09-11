"""Read-only replay for demand-shaped trend-narrative cost policy."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from typing import Any

from core.models import BrandTrendNarrative, TrendNarrativeRun
from monitor.trend_narrative_candidates import build_editor_batches
from monitor.trend_narrative_demand import material_input_fingerprint
from monitor.trend_narrative_tasks import _critic_risk_reasons
from x_monitor.config import HeadlineNarrativeConfig


def build_headline_demand_replay(
    *,
    start: datetime,
    end: datetime,
    windows: list[int],
    source_identity: str,
    candidate_revision: str,
    config: HeadlineNarrativeConfig,
) -> dict[str, Any]:
    """Compare saved provider work with a conservative demand-policy replay."""
    if end <= start:
        raise ValueError("replay end must be after start")
    if not source_identity:
        raise ValueError("source identity is required")
    if not windows or any(window not in {1, 7, 30, 365} for window in windows):
        raise ValueError("replay windows must be drawn from 1, 7, 30, and 365")

    replay_config = config.model_copy(
        update={
            "demand_shaping_enabled": True,
            "critic_risk_routing_enabled": True,
        }
    )
    runs = list(
        TrendNarrativeRun.objects.filter(
            facts_as_of__gte=start,
            facts_as_of__lt=end,
            window_days__in=windows,
        )
        .prefetch_related("provider_calls", "brand_narratives")
        .order_by("facts_as_of", "window_days", "pk")
    )
    if not runs:
        raise ValueError("replay source contains no trend narrative runs")

    prior_good = set(
        BrandTrendNarrative.objects.filter(
            status=BrandTrendNarrative.Status.APPROVED,
            run__facts_as_of__lt=start,
            run__window_days__in=windows,
        ).values_list("run__window_days", "brand_key_snapshot")
    )
    old_last_good = set(prior_good)
    new_last_good = set(prior_good)
    last_fingerprints: dict[tuple[int, str], str] = {}
    old_work = _empty_workload()
    upper_work = _empty_workload()
    routed_work = _empty_workload()
    noncompleted_states: Counter[str] = Counter()
    source_rows: list[dict[str, Any]] = []
    dossier_count = 0
    selected_count = 0
    eligible_dossier_count = 0
    selected_eligible_count = 0
    old_last_good_exposures = 0
    new_last_good_exposures = 0
    old_publications = 0
    new_publications = 0
    replayed_editor_batches = 0
    observed_risk_batches = 0
    observed_editor_batches = 0

    for run in runs:
        snapshot = run.snapshot or {}
        dossiers = list(snapshot.get("dossiers") or [])
        selected_keys: set[str] = set()
        selected_eligible_keys: set[str] = set()
        for dossier in dossiers:
            brand_key = str(dossier.get("brand_key") or "")
            identity = (run.window_days, brand_key)
            fingerprint = material_input_fingerprint(dossier, config=replay_config)
            if last_fingerprints.get(identity) != fingerprint:
                selected_keys.add(brand_key)
                last_fingerprints[identity] = fingerprint
                if dossier.get("outcome") == "narrative_eligible":
                    selected_eligible_keys.add(brand_key)

        selected_snapshot = deepcopy(snapshot)
        selected_snapshot["dossiers"] = [
            dossier
            for dossier in dossiers
            if str(dossier.get("brand_key") or "") in selected_keys
        ]
        batches = build_editor_batches(selected_snapshot) if selected_eligible_keys else []
        replayed_editor_batches += len(batches)

        dossier_count += len(dossiers)
        selected_count += len(selected_keys)
        eligible_dossier_count += sum(
            dossier.get("outcome") == "narrative_eligible" for dossier in dossiers
        )
        selected_eligible_count += len(selected_eligible_keys)

        calls = list(run.provider_calls.all())
        completed = [call for call in calls if call.state == "completed"]
        noncompleted_states.update(
            call.state for call in calls if call.state != "completed"
        )
        for call in completed:
            _add_call(old_work, call)

        rank_calls = [call for call in completed if call.stage == "rank"]
        editor_calls = [call for call in completed if call.stage == "editor"]
        critic_calls = [call for call in completed if call.stage == "critic"]
        observed_editor_batches += len(editor_calls)
        risk_batches = sum(
            _saved_editor_requires_critic(call, config=replay_config)
            for call in editor_calls
        )
        observed_risk_batches += risk_batches

        if batches and rank_calls:
            most_expensive_rank = max(
                rank_calls, key=lambda call: _call_cost_units(call, replay_config)
            )
            _add_call(upper_work, most_expensive_rank)
            _add_call(routed_work, most_expensive_rank)

        editor_count = min(len(editor_calls), len(batches))
        for call in _most_expensive_calls(
            editor_calls, count=editor_count, config=replay_config
        ):
            _add_call(upper_work, call)
            _add_call(routed_work, call)

        upper_critic_count = min(len(critic_calls), editor_count)
        routed_critic_count = (
            min(
                upper_critic_count,
                math.ceil(editor_count * risk_batches / len(editor_calls)),
            )
            if editor_calls
            else 0
        )
        for call in _most_expensive_calls(
            critic_calls, count=upper_critic_count, config=replay_config
        ):
            _add_call(upper_work, call)
        for call in _most_expensive_calls(
            critic_calls, count=routed_critic_count, config=replay_config
        ):
            _add_call(routed_work, call)

        narratives = {
            row.brand_key_snapshot: row for row in run.brand_narratives.all()
        }
        for brand_key, narrative in narratives.items():
            identity = (run.window_days, brand_key)
            if narrative.status == BrandTrendNarrative.Status.APPROVED:
                old_last_good.add(identity)
                old_publications += 1
                if brand_key in selected_keys:
                    new_last_good.add(identity)
                    new_publications += 1
        for dossier in dossiers:
            identity = (run.window_days, str(dossier.get("brand_key") or ""))
            old_last_good_exposures += int(identity in old_last_good)
            new_last_good_exposures += int(identity in new_last_good)

        source_rows.append(
            {
                "run_id": run.pk,
                "window_days": run.window_days,
                "facts_as_of": run.facts_as_of.isoformat(),
                "snapshot_sha256": _sha256_json(snapshot),
                "calls": [
                    {
                        "id": call.pk,
                        "stage": call.stage,
                        "state": call.state,
                        "request_hash": call.request_hash,
                        "response_hash": call.response_hash,
                        "input_tokens": call.input_tokens,
                        "output_tokens": call.output_tokens,
                    }
                    for call in sorted(calls, key=lambda item: item.pk)
                ],
                "narrative_statuses": sorted(
                    (key, row.status) for key, row in narratives.items()
                ),
            }
        )

    old_summary = _summarize_workload(old_work, config=replay_config)
    upper_summary = _summarize_workload(upper_work, config=replay_config)
    routed_summary = _summarize_workload(routed_work, config=replay_config)
    old_coverage = _ratio(old_last_good_exposures, dossier_count)
    new_coverage = _ratio(new_last_good_exposures, dossier_count)
    upper_reductions = _reductions(upper_summary, old_summary)
    routed_reductions = _reductions(routed_summary, old_summary)
    decision_passed = (
        upper_reductions["provider_calls_pct"] > 0
        and upper_reductions["cost_pct"] > 0
        and new_coverage >= old_coverage
    )

    return {
        "schema_version": "headline-demand-replay/v1",
        "source": {
            "identity": source_identity,
            "start_inclusive": start.isoformat(),
            "end_exclusive": end.isoformat(),
            "windows": sorted(set(windows)),
            "run_count": len(runs),
            "source_sha256": _sha256_json(source_rows),
        },
        "candidate": {
            "revision": candidate_revision,
            "materiality_policy_version": replay_config.materiality_policy_version,
            "fingerprint_band_percent": replay_config.fingerprint_band_percent,
            "critic_risk_routing_enabled": True,
            "critic_audit_percent": replay_config.critic_audit_percent,
            "pricing_version": replay_config.per_brand_pricing_version,
            "input_usd_per_million": str(
                replay_config.per_brand_input_usd_per_million
            ),
            "output_usd_per_million": str(
                replay_config.per_brand_output_usd_per_million
            ),
        },
        "method": {
            "demand_scenario": "all snapshot brands remain visible for the full replay",
            "historical_workload": "completed saved provider calls and reported tokens",
            "upper_bound": (
                "selected dossiers are compacted with production batching; every replayed "
                "editor batch receives a critic; each retained stage uses the most "+                "expensive saved call from that run"
            ),
            "risk_routed": (
                "the current deterministic critic policy is applied to saved editor "
                "responses; its per-run risk rate is applied to replayed batches"
            ),
            "provider_transport": "none",
        },
        "selection": {
            "dossiers": dossier_count,
            "selected_materially_changed": selected_count,
            "suppressed_unchanged": dossier_count - selected_count,
            "suppression_pct": _percent(dossier_count - selected_count, dossier_count),
            "eligible_dossiers": eligible_dossier_count,
            "selected_eligible_dossiers": selected_eligible_count,
            "historical_editor_batches": observed_editor_batches,
            "replayed_editor_batches": replayed_editor_batches,
            "saved_editor_batches_requiring_critic": observed_risk_batches,
        },
        "workloads": {
            "historical": old_summary,
            "new_policy_upper_bound": upper_summary,
            "new_policy_risk_routed": routed_summary,
        },
        "reductions": {
            "upper_bound": upper_reductions,
            "risk_routed": routed_reductions,
        },
        "output": {
            "historical_approved_publications": old_publications,
            "replayed_approved_publications": new_publications,
            "historical_last_good_coverage": old_coverage,
            "replayed_last_good_coverage": new_coverage,
            "last_good_coverage_delta": round(new_coverage - old_coverage, 6),
            "replayed_publication_validity": 1.0 if new_publications else 0.0,
        },
        "excluded_noncompleted_calls": dict(sorted(noncompleted_states.items())),
        "limitations": [
            "This is a read-only counterfactual over saved production runs, not new provider output.",
            "The all-brands-visible scenario intentionally claims no savings from cold demand.",
            "The upper bound keeps full historical token counts even when selected packets are smaller.",
            "Risk-routed batch composition is estimated from saved per-run editor risk rates.",
        ],
        "decision": {
            "passed": decision_passed,
            "rule": (
                "upper-bound completed calls and cost must fall while replayed last-good "
                "coverage is at least historical coverage"
            ),
        },
    }


def _saved_editor_requires_critic(
    call: Any, *, config: HeadlineNarrativeConfig
) -> bool:
    envelope = (call.request_packet or {}).get("envelope") or {}
    try:
        parsed = json.loads(str((call.response_payload or {}).get("raw_text") or ""))
    except (json.JSONDecodeError, TypeError, ValueError):
        parsed = None
    reasons, _audit_eligible = _critic_risk_reasons(
        batch=envelope.get("analysis_packet") or {},
        parsed_editor=parsed,
        editor_envelope=envelope,
        config=config,
    )
    return bool(reasons)


def _empty_workload() -> dict[str, Any]:
    return {"calls": Counter(), "input_tokens": 0, "output_tokens": 0}


def _add_call(workload: dict[str, Any], call: Any) -> None:
    workload["calls"][call.stage] += 1
    workload["input_tokens"] += call.input_tokens
    workload["output_tokens"] += call.output_tokens


def _most_expensive_calls(
    calls: list[Any], *, count: int, config: HeadlineNarrativeConfig
) -> list[Any]:
    return sorted(
        calls,
        key=lambda call: (_call_cost_units(call, config), call.pk),
        reverse=True,
    )[:count]


def _call_cost_units(call: Any, config: HeadlineNarrativeConfig) -> Decimal:
    return (
        Decimal(call.input_tokens) * config.per_brand_input_usd_per_million
        + Decimal(call.output_tokens) * config.per_brand_output_usd_per_million
    )


def _summarize_workload(
    workload: dict[str, Any], *, config: HeadlineNarrativeConfig
) -> dict[str, Any]:
    cost = (
        Decimal(workload["input_tokens"])
        * config.per_brand_input_usd_per_million
        + Decimal(workload["output_tokens"])
        * config.per_brand_output_usd_per_million
    ) / Decimal(1_000_000)
    calls = dict(sorted(workload["calls"].items()))
    return {
        "calls_by_stage": calls,
        "provider_calls": sum(calls.values()),
        "input_tokens": workload["input_tokens"],
        "output_tokens": workload["output_tokens"],
        "total_tokens": workload["input_tokens"] + workload["output_tokens"],
        "cost_usd": format(cost.quantize(Decimal("0.000001")), "f"),
    }


def _reductions(new: dict[str, Any], old: dict[str, Any]) -> dict[str, float]:
    return {
        "provider_calls_pct": _percent(
            old["provider_calls"] - new["provider_calls"], old["provider_calls"]
        ),
        "input_tokens_pct": _percent(
            old["input_tokens"] - new["input_tokens"], old["input_tokens"]
        ),
        "output_tokens_pct": _percent(
            old["output_tokens"] - new["output_tokens"], old["output_tokens"]
        ),
        "total_tokens_pct": _percent(
            old["total_tokens"] - new["total_tokens"], old["total_tokens"]
        ),
        "cost_pct": _percent(
            Decimal(old["cost_usd"]) - Decimal(new["cost_usd"]),
            Decimal(old["cost_usd"]),
        ),
    }


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _percent(numerator: Any, denominator: Any) -> float:
    return round(float(numerator / denominator * 100), 2) if denominator else 0.0


def _sha256_json(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
