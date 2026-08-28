"""Read-only operator status for shared trend-narrative state."""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import (
    BrandTrendNarrative,
    TrendNarrative,
    TrendNarrativeProviderCall,
    TrendNarrativeRun,
    TrendNarrativeVisibleRun,
    TrendNarrativeWorkSlot,
)
from monitor.trend_narrative_candidates import MAX_EDITOR_BRANDS_PER_BATCH
from monitor.trend_narrative_lifecycle import TERMINAL_BRAND_STATUSES
from monitor.trend_narrative_projection import trend_narrative_state
from x_monitor.config import load_config


class Command(BaseCommand):
    help = "Show provider-free trend narrative freshness and attempt state."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options) -> None:
        config = load_config(Path("config.yaml")).headline_narrative
        now = timezone.now()
        windows = []
        for window_days in (1, 7, 30, 365):
            current = (
                TrendNarrative.objects.filter(
                    window_days=window_days,
                    is_current=True,
                )
                .prefetch_related("subjects")
                .first()
            )
            latest = (
                TrendNarrative.objects.filter(window_days=window_days)
                .order_by("-created_at", "-pk")
                .first()
            )
            per_brand = _per_brand_status(
                window_days=window_days,
                config=config,
                now=now,
            )
            state, checked_at = trend_narrative_state(
                current,
                window_days=window_days,
                config=config,
                now=now,
            )
            windows.append(
                {
                    "window_days": window_days,
                    "state": state,
                    "current_source_cycle_id": (
                        current.source_cycle_id if current else None
                    ),
                    "semantic_fingerprint": (
                        current.semantic_fingerprint if current else None
                    ),
                    "facts_as_of": _iso(current.facts_as_of if current else None),
                    "generated_at": _iso(current.generated_at if current else None),
                    "checked_at": _iso(checked_at),
                    "latest_checked_source_cycle_id": (
                        current.latest_checked_source_cycle_id if current else None
                    ),
                    "latest_status": latest.status if latest else None,
                    "output_schema_version": (
                        current.output_schema_version if current else None
                    ),
                    "selected_candidate_ids": (
                        current.selected_candidate_ids if current else []
                    ),
                    "subjects": _safe_subjects(current),
                    "call_slot_consumed": (
                        latest.call_slot_consumed if latest else False
                    ),
                    "transport_started": bool(latest and latest.transport_started_at),
                    "transport_completed": bool(
                        latest and latest.transport_completed_at
                    ),
                    "claim_owner": latest.claim_owner if latest else "",
                    "claim_fence": latest.claim_fence if latest else 0,
                    "claim_expires_at": _iso(
                        latest.claim_expires_at if latest else None
                    ),
                    "generated_at_latest": _iso(
                        latest.generated_at if latest else None
                    ),
                    "published_at_latest": _iso(
                        latest.published_at if latest else None
                    ),
                    "next_attempt_at": _iso(latest.next_attempt_at if latest else None),
                    "consecutive_failures": (
                        latest.consecutive_failures if latest else 0
                    ),
                    "error_code": latest.error_code if latest else "",
                    "provider": latest.provider if latest else config.provider,
                    "provider_host": (latest.provider_host if latest else "configured"),
                    "model": (
                        latest.resolved_llm_model_name if latest else config.model
                    ),
                    "prompt_version": (
                        latest.prompt_version if latest else config.prompt_version
                    ),
                    "publication_epoch": (
                        latest.publication_epoch if latest else config.publication_epoch
                    ),
                    "input_tokens": latest.input_tokens if latest else 0,
                    "output_tokens": latest.output_tokens if latest else 0,
                    "latency_ms": latest.latency_ms if latest else None,
                    "output_hash": latest.output_hash if latest else "",
                    # These legacy fields remain at the established top level
                    # for operators and backward-compatible scripts.  The
                    # parallel section below intentionally contains only
                    # persisted per-brand operational metadata, never packets,
                    # provider responses, evidence, or credentials.
                    "per_brand": per_brand,
                }
            )
        payload = {
            "control_revision": config.control_revision,
            "activation_state": config.activation_state,
            "serving_enabled": config.serving_enabled,
            "enqueue_enabled": config.enqueue_enabled,
            "provider_calls_enabled": config.provider_calls_enabled,
            "serving_active": config.serving_active,
            "enqueue_active": config.enqueue_active,
            "provider_calls_active": config.provider_calls_active,
            "windows": windows,
        }
        if options["as_json"]:
            self.stdout.write(json.dumps(payload, indent=2))
            return
        self.stdout.write(
            "headline controls "
            f"revision={config.control_revision} "
            f"activation={config.activation_state} "
            "requested["
            f"serving={config.serving_enabled} "
            f"enqueue={config.enqueue_enabled} "
            f"provider={config.provider_calls_enabled}] "
            "active["
            f"serving={config.serving_active} "
            f"enqueue={config.enqueue_active} "
            f"provider={config.provider_calls_active}]"
        )
        for row in windows:
            self.stdout.write(
                f"{row['window_days']}d {row['state']} "
                f"status={row['latest_status'] or '-'} "
                f"schema={row['output_schema_version'] or '-'} "
                f"subjects={len(row['subjects'])} "
                f"source={row['current_source_cycle_id'] or '-'} "
                f"checked={row['checked_at'] or '-'} "
                f"slot={int(row['call_slot_consumed'])} "
                f"transport={int(row['transport_started'])}/{int(row['transport_completed'])} "
                f"claim={row['claim_owner'] or '-'}:{row['claim_fence']} "
                f"failures={row['consecutive_failures']} "
                f"error={row['error_code'] or '-'}"
            )
            per_brand = row["per_brand"]
            run = per_brand["run"]
            self.stdout.write(
                "  per-brand "
                f"run={run['source_cycle_id'] or '-'} "
                f"status={run['status'] or '-'} "
                f"complete={int(run['complete'])} "
                f"outcomes={run['outcome_count']}/{run['manifest_brand_count']} "
                f"held={len(per_brand['held_brands'])} "
                f"ambiguous={per_brand['transport']['ambiguous_count']} "
                f"backlog={int(per_brand['backlog']['active'])}/"
                f"{int(per_brand['backlog']['queued'])}"
            )


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _safe_subjects(narrative: TrendNarrative | None) -> list[dict[str, object]]:
    """Expose identity/support diagnostics without private evidence IDs."""
    if narrative is None:
        return []
    return [
        {
            "position": subject.position,
            "support_type": subject.support_type,
            "entity_type": subject.entity_type,
            "identity_type": subject.identity_type,
            "key": subject.canonical_key_snapshot or None,
        }
        for subject in narrative.subjects.all()
    ]


_CALL_STAGES = tuple(TrendNarrativeProviderCall.Stage.values)
_CALL_STATES = tuple(TrendNarrativeProviderCall.State.values)


def _per_brand_status(*, window_days: int, config, now) -> dict[str, object]:
    """Return safe operational state for the newest relevant per-brand run.

    ``headline_status`` is deliberately a read-only, provider-free command.
    The output contains public brand snapshots and transport counters only;
    it never traverses JSON request/response packets or evidence fields.
    """
    slot = (
        TrendNarrativeWorkSlot.objects.filter(window_days=window_days)
        .select_related("active_run")
        .first()
    )
    visible = (
        TrendNarrativeVisibleRun.objects.filter(window_days=window_days)
        .select_related("run")
        .first()
    )
    latest = (
        TrendNarrativeRun.objects.filter(window_days=window_days)
        .order_by("-created_at", "-pk")
        .first()
    )
    run = (slot.active_run if slot and slot.active_run_id else None) or latest
    outcomes = list(
        BrandTrendNarrative.objects.filter(run=run)
        .select_related("last_good")
        .order_by("brand_key_snapshot")
        if run is not None
        else []
    )
    outcome_keys = {outcome.brand_key_snapshot for outcome in outcomes}
    manifest = [str(key) for key in (run.brand_manifest if run else [])]
    missing = [key for key in manifest if key not in outcome_keys]
    terminal_count = sum(
        outcome.status in TERMINAL_BRAND_STATUSES for outcome in outcomes
    )
    calls = list(
        TrendNarrativeProviderCall.objects.filter(run=run).only(
            "stage",
            "state",
            "error_code",
            "input_tokens",
            "output_tokens",
            "latency_ms",
        )
        if run is not None
        else []
    )
    latest_attempt_at = max(
        (outcome.attempted_at for outcome in outcomes), default=None
    )
    latest_verification_at = max(
        (
            _served_verification_at(outcome)
            for outcome in outcomes
            if _served_verification_at(outcome) is not None
        ),
        default=None,
    )
    return {
        "run": {
            "id": run.pk if run else None,
            "source_cycle_id": run.source_cycle_id if run else None,
            "status": run.status if run else None,
            "suspension_reason": run.suspension_reason if run else "",
            "facts_as_of": _iso(run.facts_as_of if run else None),
            "created_at": _iso(run.created_at if run else None),
            "activated_at": _iso(run.activated_at if run else None),
            "manifest_brand_count": len(manifest),
            "outcome_count": len(outcomes),
            "terminal_outcome_count": terminal_count,
            "missing_brand_keys": missing,
            "complete": bool(run)
            and len(outcomes) == len(manifest)
            and not missing
            and terminal_count == len(manifest),
            "visible": bool(visible and run and visible.run_id == run.pk),
        },
        "brand_outcomes": [
            _brand_outcome_status(outcome, now=now) for outcome in outcomes
        ],
        "held_brands": [
            _brand_outcome_status(outcome, now=now)
            for outcome in outcomes
            if outcome.status == BrandTrendNarrative.Status.HELD
        ],
        "latest_attempt_at": _iso(latest_attempt_at),
        "last_verification_at": _iso(latest_verification_at),
        "transport": _transport_status(calls),
        "backlog": _backlog_status(slot),
        "drain": _drain_status(
            window_days=window_days,
            run=run,
            calls=calls,
            config=config,
        ),
    }


def _brand_outcome_status(outcome: BrandTrendNarrative, *, now) -> dict[str, object]:
    served_verification_at = _served_verification_at(outcome)
    return {
        "brand_key": outcome.brand_key_snapshot,
        "status": outcome.status,
        "critic_decision": outcome.critic_decision,
        "error_code": outcome.error_code,
        "latest_attempt_at": _iso(outcome.attempted_at),
        "last_verification_at": _iso(served_verification_at),
        "stale_duration_seconds": _stale_duration_seconds(
            served_verification_at, now=now
        ),
        "last_good_available": bool(outcome.last_good_id),
    }


def _served_verification_at(outcome: BrandTrendNarrative):
    if outcome.status == BrandTrendNarrative.Status.HELD:
        return outcome.last_good.verified_at
    return outcome.verified_at


def _stale_duration_seconds(value, *, now) -> int | None:
    if value is None:
        return None
    return max(0, int((now - value).total_seconds()))


def _transport_status(calls: list[TrendNarrativeProviderCall]) -> dict[str, object]:
    stages: dict[str, dict[str, object]] = {}
    for stage in _CALL_STAGES:
        stage_calls = [call for call in calls if call.stage == stage]
        states = {
            state: sum(call.state == state for call in stage_calls)
            for state in _CALL_STATES
        }
        failed_codes = sorted(
            {
                call.error_code
                for call in stage_calls
                if call.state == TrendNarrativeProviderCall.State.FAILED
                and call.error_code
            }
        )
        ambiguous_codes = sorted(
            {
                call.error_code
                for call in stage_calls
                if call.state == TrendNarrativeProviderCall.State.AMBIGUOUS
                and call.error_code
            }
        )
        stages[stage] = {
            "total": len(stage_calls),
            "states": states,
            "failure_count": states[TrendNarrativeProviderCall.State.FAILED],
            "failure_codes": failed_codes,
            "ambiguous_count": states[TrendNarrativeProviderCall.State.AMBIGUOUS],
            "ambiguous_codes": ambiguous_codes,
        }
    return {
        "call_count": len(calls),
        "failed_count": sum(
            call.state == TrendNarrativeProviderCall.State.FAILED for call in calls
        ),
        "ambiguous_count": sum(
            call.state == TrendNarrativeProviderCall.State.AMBIGUOUS for call in calls
        ),
        "stages": stages,
    }


def _backlog_status(slot: TrendNarrativeWorkSlot | None) -> dict[str, object]:
    return {
        "active": bool(slot and slot.active_source_cycle_id),
        "active_source_cycle_id": slot.active_source_cycle_id if slot else None,
        "active_facts_as_of": _iso(slot.active_facts_as_of if slot else None),
        "active_run_id": slot.active_run_id if slot else None,
        "queued": bool(slot and slot.queued_source_cycle_id),
        "queued_source_cycle_id": slot.queued_source_cycle_id if slot else None,
        "queued_facts_as_of": _iso(slot.queued_facts_as_of if slot else None),
        "snapshot_claim_active": bool(
            slot and slot.snapshot_claim_expires_at and slot.snapshot_claim_owner
        ),
        "snapshot_claim_expires_at": _iso(
            slot.snapshot_claim_expires_at if slot else None
        ),
    }


def _drain_status(
    *, window_days: int, run: TrendNarrativeRun | None, calls, config
) -> dict[str, object]:
    eligible_count = sum(
        dossier.get("outcome") == "narrative_eligible"
        for dossier in ((run.snapshot or {}).get("dossiers", []) if run else [])
    )
    expected_calls = (
        1
        + 2
        * (
            (eligible_count + MAX_EDITOR_BRANDS_PER_BATCH - 1)
            // MAX_EDITOR_BRANDS_PER_BATCH
        )
        if eligible_count
        else 0
    )
    window_expected_arrival_calls_per_hour = (
        expected_calls * 60 / config.cadence_minutes[window_days]
    )
    fleet_expected_calls = 1 + 2 * (
        (config.per_brand_expected_max_brands + MAX_EDITOR_BRANDS_PER_BATCH - 1)
        // MAX_EDITOR_BRANDS_PER_BATCH
    )
    fleet_expected_arrival_calls_per_hour = sum(
        fleet_expected_calls * 60 / config.cadence_minutes[window]
        for window in config.cadence_minutes
    )
    capacity_calls_per_hour = float(
        3600
        * config.per_brand_worker_concurrency
        / config.per_brand_p95_latency_seconds
    )
    fleet_expected_utilization = (
        fleet_expected_arrival_calls_per_hour / capacity_calls_per_hour
        if capacity_calls_per_hour
        else None
    )
    return {
        "eligible_brand_count": eligible_count,
        "expected_call_count": expected_calls,
        "recorded_call_count": len(calls),
        "worker_concurrency": config.per_brand_worker_concurrency,
        "p95_latency_seconds": float(config.per_brand_p95_latency_seconds),
        "estimated_run_drain_seconds": float(
            expected_calls
            * config.per_brand_p95_latency_seconds
            / config.per_brand_worker_concurrency
        ),
        "window_expected_arrival_calls_per_hour": window_expected_arrival_calls_per_hour,
        "fleet_expected_call_count_per_window": fleet_expected_calls,
        "fleet_expected_arrival_calls_per_hour": fleet_expected_arrival_calls_per_hour,
        "p95_capacity_calls_per_hour": capacity_calls_per_hour,
        "fleet_expected_utilization": fleet_expected_utilization,
    }
