"""Durable, coalesced demand for per-brand trend narratives."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from copy import deepcopy
from datetime import timedelta
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
    rows = {
        row.brand_id: row
        for row in TrendNarrativeDemand.objects.filter(window_days=window_days).filter(
            Q(is_pinned=True) | Q(hot_until__gte=current)
        )
    }
    selected = []
    fingerprints: dict[str, str] = {}
    for dossier in copied.get("dossiers") or []:
        key = str(dossier.get("brand_key") or "")
        demand = rows.get(key)
        if demand is None:
            continue
        fingerprint = material_input_fingerprint(dossier, config=config)
        operator_refresh = (
            demand.operator_request_count > demand.last_enqueued_operator_request_count
        )
        changed = demand.last_material_input_fingerprint != fingerprint
        if changed or operator_refresh:
            selected.append(dossier)
            fingerprints[key] = fingerprint
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
    }
    return copied


def material_input_fingerprint(
    dossier: Mapping[str, Any], *, config: HeadlineNarrativeConfig
) -> str:
    """Hash only inputs that can materially change published narrative text."""
    payload = {
        "policy": config.materiality_policy_version,
        "brand_key": dossier.get("brand_key"),
        "outcome": dossier.get("outcome"),
        "enrichment_coverage": dossier.get("enrichment_coverage"),
        "comparison_status": dossier.get("comparison_status"),
        "family_summaries": dossier.get("family_summaries"),
        "facts": dossier.get("facts"),
        "shape_summary": dossier.get("shape_summary"),
        "corpus_signals": dossier.get("corpus_signals"),
        "evidence": dossier.get("evidence"),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def mark_run_demands_satisfied(run: TrendNarrativeRun, *, now=None) -> int:
    selection = (run.snapshot or {}).get("demand_selection") or {}
    fingerprints = selection.get("fingerprints") or {}
    if not isinstance(fingerprints, dict):
        return 0
    current = now or timezone.now()
    updated = 0
    for brand_key, fingerprint in fingerprints.items():
        updated += TrendNarrativeDemand.objects.filter(
            brand_id=brand_key,
            window_days=run.window_days,
        ).update(
            state=TrendNarrativeDemand.State.SATISFIED,
            last_material_input_fingerprint=str(fingerprint),
            last_satisfied_at=current,
            last_decision_reason="published_or_terminal",
        )
    return updated
