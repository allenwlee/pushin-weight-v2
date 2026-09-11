"""Durable, coalesced demand for per-brand trend narratives."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from copy import deepcopy
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone

from core.models import Brand, TrendNarrativeDemand, TrendNarrativeRun
from x_monitor.config import HeadlineNarrativeConfig

WINDOWS = frozenset({1, 7, 30, 365})
REASON_PRIORITY = {
    TrendNarrativeDemand.Reason.PREWARM: 10,
    TrendNarrativeDemand.Reason.VISIBLE: 50,
    TrendNarrativeDemand.Reason.OPERATOR: 100,
}


def target_identity(config: HeadlineNarrativeConfig) -> tuple[str, str, str]:
    """Return the version identity that makes old work non-publishable."""
    contract = f"per-brand-v3:epoch-{config.publication_epoch}"
    prompt = (
        f"{config.prompt_version}:{config.rank_prompt_version}:"
        f"{config.editor_prompt_version}:{config.critic_prompt_version}"
    )
    return contract[:64], prompt[:255], config.model[:128]


def record_trend_narrative_demand(
    *,
    brand_keys: Iterable[str],
    window_days: int,
    reason: str,
    config: HeadlineNarrativeConfig,
    now=None,
    hot_minutes: int | None = None,
    pinned: bool = False,
) -> int:
    """Upsert one row per brand/window and return the accepted brand count."""
    if window_days not in WINDOWS:
        raise ValueError("unsupported trend narrative window")
    if reason not in TrendNarrativeDemand.Reason.values:
        raise ValueError("unsupported trend narrative demand reason")
    requested_at = now or timezone.now()
    duration = hot_minutes or config.demand_hot_minutes
    hot_until = requested_at + timedelta(minutes=duration)
    contract, prompt, model = target_identity(config)
    keys = list(dict.fromkeys(str(key) for key in brand_keys if str(key)))
    existing_keys = set(Brand.objects.filter(pk__in=keys).values_list("pk", flat=True))
    accepted = 0
    for brand_key in keys:
        if brand_key not in existing_keys:
            continue
        _record_one(
            brand_key=brand_key,
            window_days=window_days,
            reason=reason,
            priority=REASON_PRIORITY[reason],
            contract=contract,
            prompt=prompt,
            model=model,
            requested_at=requested_at,
            hot_until=hot_until,
            pinned=pinned,
        )
        accepted += 1
    return accepted


def _record_one(**values) -> None:
    for attempt in range(2):
        try:
            with transaction.atomic():
                row = (
                    TrendNarrativeDemand.objects.select_for_update()
                    .filter(
                        brand_id=values["brand_key"],
                        window_days=values["window_days"],
                    )
                    .first()
                )
                if row is None:
                    TrendNarrativeDemand.objects.create(
                        brand_id=values["brand_key"],
                        window_days=values["window_days"],
                        target_contract_version=values["contract"],
                        target_prompt_version=values["prompt"],
                        target_model=values["model"],
                        demand_reason=values["reason"],
                        priority=values["priority"],
                        first_requested_at=values["requested_at"],
                        last_requested_at=values["requested_at"],
                        hot_until=values["hot_until"],
                        is_pinned=values["pinned"],
                        operator_request_count=(
                            1
                            if values["reason"] == TrendNarrativeDemand.Reason.OPERATOR
                            else 0
                        ),
                    )
                    return
                version_changed = (
                    row.target_contract_version != values["contract"]
                    or row.target_prompt_version != values["prompt"]
                    or row.target_model != values["model"]
                )
                row.target_contract_version = values["contract"]
                row.target_prompt_version = values["prompt"]
                row.target_model = values["model"]
                if values["priority"] >= row.priority:
                    row.demand_reason = values["reason"]
                row.priority = max(row.priority, values["priority"])
                row.request_count += 1
                if values["reason"] == TrendNarrativeDemand.Reason.OPERATOR:
                    row.operator_request_count += 1
                row.last_requested_at = values["requested_at"]
                row.hot_until = max(row.hot_until, values["hot_until"])
                row.is_pinned = row.is_pinned or values["pinned"]
                row.state = TrendNarrativeDemand.State.PENDING
                row.last_decision_reason = "version_changed" if version_changed else ""
                if version_changed:
                    row.last_material_input_fingerprint = ""
                    row.last_enqueued_request_count = 0
                    row.last_enqueued_operator_request_count = 0
                    row.last_enqueued_at = None
                row.save()
                return
        except IntegrityError:
            if attempt:
                raise


def eligible_demand_exists(*, window_days: int, now=None) -> bool:
    current = now or timezone.now()
    return (
        TrendNarrativeDemand.objects.filter(window_days=window_days)
        .filter(Q(is_pinned=True) | Q(hot_until__gte=current))
        .exists()
    )


def select_demanded_snapshot(
    snapshot: Mapping[str, Any],
    *,
    config: HeadlineNarrativeConfig,
    now=None,
) -> dict[str, Any]:
    """Retain hot, materially changed dossiers and record every decision."""
    current = now or timezone.now()
    copied = deepcopy(dict(snapshot))
    window_days = int(copied["window_days"])
    with transaction.atomic():
        rows = {
            row.brand_id: row
            for row in TrendNarrativeDemand.objects.select_for_update()
            .filter(window_days=window_days)
            .filter(Q(is_pinned=True) | Q(hot_until__gte=current))
        }
        selected = []
        fingerprints: dict[str, str] = {}
        targets: dict[str, dict[str, Any]] = {}
        for dossier in copied.get("dossiers") or []:
            key = str(dossier.get("brand_key") or "")
            demand = rows.get(key)
            if demand is None:
                continue
            fingerprint = material_input_fingerprint(dossier, config=config)
            operator_refresh = (
                demand.operator_request_count
                > demand.last_enqueued_operator_request_count
            )
            changed = demand.last_material_input_fingerprint != fingerprint
            if changed or operator_refresh:
                selected.append(dossier)
                fingerprints[key] = fingerprint
                targets[key] = {
                    "contract_version": demand.target_contract_version,
                    "prompt_version": demand.target_prompt_version,
                    "model": demand.target_model,
                    "operator_request_count": demand.operator_request_count,
                }
                TrendNarrativeDemand.objects.filter(pk=demand.pk).update(
                    state=TrendNarrativeDemand.State.SCHEDULED,
                    last_enqueued_at=current,
                    last_enqueued_request_count=F("request_count"),
                    last_enqueued_operator_request_count=F("operator_request_count"),
                    last_decision_reason=(
                        "operator_refresh" if operator_refresh else "material_change"
                    ),
                )
            else:
                TrendNarrativeDemand.objects.filter(pk=demand.pk).update(
                    state=TrendNarrativeDemand.State.SUPPRESSED,
                    last_decision_reason="unchanged",
                    suppression_count=F("suppression_count") + 1,
                )
    copied["dossiers"] = selected
    copied["demand_selection"] = {
        "policy_version": config.materiality_policy_version,
        "fingerprints": fingerprints,
        "targets": targets,
    }
    return copied


def material_input_fingerprint(
    dossier: Mapping[str, Any], *, config: HeadlineNarrativeConfig
) -> str:
    """Hash only inputs that can materially change published narrative text."""
    payload = _material_dossier_projection(
        dossier,
        policy_version=config.materiality_policy_version,
        band_percent=config.fingerprint_band_percent,
    )
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _material_dossier_projection(
    dossier: Mapping[str, Any], *, policy_version: str, band_percent: int
) -> dict[str, Any]:
    facts = sorted(
        (
            {
                key: fact.get(key)
                for key in (
                    "fact_id",
                    "unit",
                    "family",
                    "metric",
                    "direction",
                    "label_key",
                )
            }
            | {
                "current_band": _band_value(
                    fact.get("current_value"),
                    unit=str(fact.get("unit") or ""),
                    band_percent=band_percent,
                ),
                "baseline_band": _band_value(
                    fact.get("baseline_value"),
                    unit=str(fact.get("unit") or ""),
                    band_percent=band_percent,
                ),
                "coverage_status": (fact.get("coverage_scope") or {}).get("status"),
            }
            for fact in dossier.get("facts") or []
            if isinstance(fact, Mapping)
        ),
        key=lambda row: str(row.get("fact_id") or ""),
    )
    evidence = sorted(
        (
            {
                key: _stable_value(row.get(key))
                for key in (
                    "evidence_id",
                    "author_group_id",
                    "classification_status",
                    "created_at",
                    "discourse_keys",
                    "excerpt",
                    "first_party_role",
                    "handle_snapshot",
                    "original_text",
                    "post_type_keys",
                    "roles",
                    "sentiment_keys",
                    "source_cluster_id",
                    "source_flags",
                    "source_language",
                    "taxonomy",
                    "text_en",
                    "text_ja",
                    "text_zh_cn",
                    "theme_cluster_id",
                    "translation_status",
                )
                if key in row
            }
            for row in dossier.get("evidence") or []
            if isinstance(row, Mapping)
        ),
        key=lambda row: str(row.get("evidence_id") or ""),
    )
    family_summaries = {
        str(family): {
            key: summary.get(key)
            for key in ("status", "current_leader", "largest_change")
        }
        for family, summary in (dossier.get("family_summaries") or {}).items()
        if isinstance(summary, Mapping)
    }
    corpus_signals = sorted(
        (
            {
                "corpus_signal_id": row.get("corpus_signal_id"),
                "phrase": row.get("phrase"),
                "prevalence_band": _band_value(
                    row.get("prevalence"), unit="posts", band_percent=band_percent
                ),
                "prior_prevalence_band": _band_value(
                    row.get("prior_prevalence"),
                    unit="posts",
                    band_percent=band_percent,
                ),
                "peer_brand_count_band": _band_value(
                    row.get("peer_brand_count"),
                    unit="posts",
                    band_percent=band_percent,
                ),
                "representative_excerpt": row.get("representative_excerpt"),
                "representative_evidence_ids": sorted(
                    str(value)
                    for value in row.get("representative_evidence_ids") or []
                ),
            }
            for row in dossier.get("corpus_signals") or []
            if isinstance(row, Mapping)
        ),
        key=lambda row: (
            str(row.get("corpus_signal_id") or ""),
            str(row.get("phrase") or ""),
        ),
    )
    return {
        "policy": policy_version,
        "brand_key": dossier.get("brand_key"),
        "outcome": dossier.get("outcome"),
        "enrichment_coverage": _coverage_projection(
            dossier.get("enrichment_coverage") or {}, band_percent=band_percent
        ),
        "comparison_status": _comparison_projection(
            dossier.get("comparison_status") or {}, band_percent=band_percent
        ),
        "family_summaries": family_summaries,
        "facts": facts,
        "shape_summary": _shape_projection(
            dossier.get("shape_summary") or {}, band_percent=band_percent
        ),
        "corpus_signals": corpus_signals,
        "evidence": evidence,
    }


def _coverage_projection(
    value: Mapping[str, Any], *, band_percent: int
) -> dict[str, Any]:
    return {
        "translation_status": value.get("translation_status"),
        "classification_status": value.get("classification_status"),
        "total_post_count_band": _band_value(
            value.get("total_post_count"), unit="posts", band_percent=band_percent
        ),
        "fully_enriched_count_band": _band_value(
            value.get("fully_enriched_count"),
            unit="posts",
            band_percent=band_percent,
        ),
        "translation_succeeded_count_band": _band_value(
            value.get("translation_succeeded_count"),
            unit="posts",
            band_percent=band_percent,
        ),
        "classification_succeeded_count_band": _band_value(
            value.get("classification_succeeded_count"),
            unit="posts",
            band_percent=band_percent,
        ),
    }


def _comparison_projection(
    value: Mapping[str, Any], *, band_percent: int
) -> dict[str, Any]:
    selected = value.get("selected_coverage") or {}
    prior = value.get("prior_coverage") or {}
    return {
        "allowed": value.get("allowed"),
        "suppression_reasons": sorted(
            str(reason) for reason in value.get("suppression_reasons") or []
        ),
        "current_post_count_band": _band_value(
            value.get("current_post_count"), unit="posts", band_percent=band_percent
        ),
        "prior_post_count_band": _band_value(
            value.get("prior_post_count"), unit="posts", band_percent=band_percent
        ),
        "selected_coverage": {
            "state": selected.get("state"),
            "ratio_band": _band_value(
                selected.get("ratio"), unit="ratio", band_percent=band_percent
            ),
            "known_backlog_overlap": selected.get("known_backlog_overlap"),
        },
        "prior_coverage": {
            "state": prior.get("state"),
            "ratio_band": _band_value(
                prior.get("ratio"), unit="ratio", band_percent=band_percent
            ),
            "known_backlog_overlap": prior.get("known_backlog_overlap"),
        },
    }


def _shape_projection(
    value: Mapping[str, Any], *, band_percent: int
) -> dict[str, Any]:
    peak = value.get("peak") or {}
    trough = value.get("trough") or {}
    transition = value.get("dominant_transition") or {}
    return {
        "direction": value.get("direction"),
        "comparison_state": value.get("comparison_state"),
        "total_change_band": _band_value(
            value.get("total_change_pct"),
            unit="percent",
            band_percent=band_percent,
        ),
        "start_segment_count_band": _band_value(
            value.get("start_segment_post_count"),
            unit="posts",
            band_percent=band_percent,
        ),
        "end_segment_count_band": _band_value(
            value.get("end_segment_post_count"),
            unit="posts",
            band_percent=band_percent,
        ),
        "peak_count_band": _band_value(
            peak.get("post_count"), unit="posts", band_percent=band_percent
        ),
        "trough_count_band": _band_value(
            trough.get("post_count"), unit="posts", band_percent=band_percent
        ),
        "transition_count_band": _band_value(
            transition.get("post_count_change"),
            unit="posts",
            band_percent=band_percent,
        ),
        "transition_share_band": _band_value(
            transition.get("net_change_share_pct"),
            unit="percent",
            band_percent=band_percent,
        ),
    }


def _band_value(value: Any, *, unit: str, band_percent: int) -> str:
    if value in (None, ""):
        return ""
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return str(value)
    if unit == "percent":
        step = Decimal(band_percent)
    elif unit == "ratio":
        step = Decimal(band_percent) / Decimal(100)
    elif unit == "posts":
        step = max(
            Decimal(1),
            (abs(number) * Decimal(band_percent) / Decimal(100)).quantize(
                Decimal(1), rounding=ROUND_HALF_UP
            ),
        )
    else:
        return format(number.normalize(), "f")
    banded = (number / step).quantize(Decimal(1), rounding=ROUND_HALF_UP) * step
    return format(banded.normalize(), "f")


def _stable_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _stable_value(item) for key, item in value.items()}
    if isinstance(value, list):
        projected = [_stable_value(item) for item in value]
        if all(
            isinstance(item, (str, int, float, bool, type(None)))
            for item in projected
        ):
            return sorted(projected, key=lambda item: (type(item).__name__, str(item)))
        return projected
    return value


def mark_run_demands_satisfied(run: TrendNarrativeRun, *, now=None) -> int:
    selection = (run.snapshot or {}).get("demand_selection") or {}
    fingerprints = selection.get("fingerprints") or {}
    targets = selection.get("targets") or {}
    if not isinstance(fingerprints, dict) or not isinstance(targets, dict):
        return 0
    current = now or timezone.now()
    updated = 0
    for brand_key, fingerprint in fingerprints.items():
        target = targets.get(brand_key)
        if not isinstance(target, Mapping):
            continue
        updated += TrendNarrativeDemand.objects.filter(
            brand_id=brand_key,
            window_days=run.window_days,
            target_contract_version=target.get("contract_version"),
            target_prompt_version=target.get("prompt_version"),
            target_model=target.get("model"),
            operator_request_count=target.get("operator_request_count"),
        ).update(
            state=TrendNarrativeDemand.State.SATISFIED,
            last_material_input_fingerprint=str(fingerprint),
            last_satisfied_at=current,
            last_decision_reason="published_or_terminal",
        )
    return updated
