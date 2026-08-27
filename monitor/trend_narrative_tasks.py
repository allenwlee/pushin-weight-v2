"""Bounded orchestration for one committed harvest completion envelope."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from billiard.exceptions import SoftTimeLimitExceeded
from django.db import transaction
from django.utils import timezone

from core.models import (
    BrandTrendNarrative,
    TrendNarrative,
    TrendNarrativeProviderCall,
    TrendNarrativeRun,
    TrendNarrativeVisibleRun,
    TrendNarrativeWorkSlot,
)
from monitor.trend_narrative_candidates import (
    EvidenceSelectionPolicy,
    _fit_editor_batch_to_packet_budget,
    _provider_dossier,
    build_trend_analysis_snapshot,
    project_provider_packet,
)
from monitor.trend_narrative_facts import (
    ALLOWED_TREND_WINDOWS,
    TrendFactThresholds,
)
from monitor.trend_narrative_generation import (
    HEADLINE_OUTPUT_SCHEMA_VERSION,
    HeadlineGenerationError,
    build_per_brand_critic_request,
    build_per_brand_editor_request,
    build_per_brand_rank_request,
    execute_per_brand_provider_request,
    generate_trend_narrative,
    generation_fingerprint,
    validate_per_brand_critic_response,
    validate_per_brand_editor_response,
    validate_per_brand_rank_response,
)
from monitor.trend_narrative_lifecycle import (
    abandon_expired_attempts,
    activate_trend_narrative_run,
    advance_current_check,
    attempt_failure_history,
    claim_trend_narrative_provider_call,
    complete_trend_narrative_provider_call,
    fail_generation,
    fail_trend_narrative_provider_call,
    has_active_generation_backoff,
    mark_transport_completed,
    mark_transport_started,
    mark_trend_narrative_provider_call_ambiguous,
    mark_trend_narrative_provider_call_sent,
    next_failure_backoff,
    prepare_brand_trend_narrative,
    prune_narrative_history,
    publish_generation,
    record_no_call_check,
    reserve_generation,
    reserve_trend_narrative_provider_call,
)
from x_monitor.config import HeadlineNarrativeConfig, load_config

logger = logging.getLogger(__name__)


class _PerBrandBudgetExceeded(RuntimeError):
    """Internal control-flow signal raised before an over-budget transport."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def process_trend_narrative_envelope(
    envelope: dict[str, Any],
    *,
    now=None,
    clock=None,
) -> dict[str, Any]:
    """Visit fixed windows sequentially with at most four physical attempts."""
    clock = clock or timezone.now
    processed_at = now or clock()
    source_cycle_id, facts_as_of = _validate_envelope(envelope)
    config = _load_config()
    stats: dict[str, Any] = {
        "status": "completed",
        "source_cycle_id": source_cycle_id,
        "control_revision": config.control_revision,
        "slots_consumed": 0,
        "transport_started": 0,
        "published": 0,
        "failed": 0,
        "suppressed": 0,
        "checks_advanced": 0,
        "not_due": 0,
        "outdated": 0,
        "errors": [],
    }
    if processed_at > facts_as_of + timedelta(seconds=config.task_expiry_seconds):
        stats["status"] = "expired"
        return stats

    abandon_expired_attempts(
        now=processed_at,
        cadence_minutes=config.cadence_minutes,
        stale_minutes=config.stale_minutes,
    )
    thresholds = _thresholds(config)
    evidence_policy = _evidence_policy(config)
    for window_days in sorted(ALLOWED_TREND_WINDOWS):
        if stats["slots_consumed"] >= config.call_cap:
            break
        rows = TrendNarrative.objects.filter(window_days=window_days)
        if rows.filter(facts_as_of__gte=facts_as_of).exists():
            stats["outdated"] += 1
            continue
        cadence_rows = rows.exclude(
            status__in=[
                TrendNarrative.Status.FAILED,
                TrendNarrative.Status.ABANDONED,
            ]
        ).exclude(
            status=TrendNarrative.Status.SUPPRESSED,
            error_code="provider_backoff",
        )
        if config.provider_calls_active:
            cadence_rows = cadence_rows.exclude(
                status=TrendNarrative.Status.SUPPRESSED,
                error_code="provider_calls_disabled",
            )
        latest = cadence_rows.order_by(
            "-latest_checked_at", "-created_at", "-pk"
        ).first()
        last_activity = None
        if latest is not None:
            last_activity = latest.latest_checked_at or latest.created_at
        cadence = timedelta(minutes=config.cadence_minutes[window_days])
        if last_activity is not None and processed_at < last_activity + cadence:
            stats["not_due"] += 1
            continue

        try:
            snapshot = build_trend_analysis_snapshot(
                window_days,
                as_of=facts_as_of,
                thresholds=thresholds,
                evidence_policy=evidence_policy,
            )
        except SoftTimeLimitExceeded:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "trend snapshot failed for %sd source=%s error_type=%s",
                window_days,
                source_cycle_id,
                type(exc).__name__,
            )
            stats["failed"] += 1
            stats["errors"].append(f"{window_days}d:snapshot_failed")
            failure_facts = {
                "snapshot_schema_version": 1,
                "window_days": window_days,
                "as_of": facts_as_of.isoformat(),
                "failure_stage": "snapshot",
                "candidates": [],
            }
            failure_fingerprint = hashlib.sha256(
                (f"snapshot-failure-v1:{window_days}:{type(exc).__name__}").encode()
            ).hexdigest()
            _record_no_call(
                source_cycle_id=source_cycle_id,
                window_days=window_days,
                facts_as_of=facts_as_of,
                fingerprint=failure_fingerprint,
                facts=failure_facts,
                processed_at=processed_at,
                status=TrendNarrative.Status.SUPPRESSED,
                reason="snapshot_failed",
            )
            continue
        active_config = _load_config()
        stats["control_revision"] = active_config.control_revision
        fingerprint = generation_fingerprint(snapshot, active_config)
        current = rows.filter(is_current=True).first()
        if current is not None and current.semantic_fingerprint == fingerprint:
            if advance_current_check(
                window_days=window_days,
                semantic_fingerprint=fingerprint,
                source_cycle_id=source_cycle_id,
                checked_as_of=facts_as_of,
                checked_at=processed_at,
                facts=snapshot,
            ):
                stats["checks_advanced"] += 1
            continue

        if not snapshot["candidates"]:
            _record_no_call(
                source_cycle_id=source_cycle_id,
                window_days=window_days,
                facts_as_of=facts_as_of,
                fingerprint=fingerprint,
                facts=snapshot,
                processed_at=processed_at,
                status=TrendNarrative.Status.CHECKED,
                reason="insufficient_data",
            )
            stats["suppressed"] += 1
            continue
        if not active_config.provider_calls_active:
            _record_no_call(
                source_cycle_id=source_cycle_id,
                window_days=window_days,
                facts_as_of=facts_as_of,
                fingerprint=fingerprint,
                facts=snapshot,
                processed_at=processed_at,
                status=TrendNarrative.Status.SUPPRESSED,
                reason="provider_calls_disabled",
            )
            stats["suppressed"] += 1
            continue

        provider_host = urlsplit(active_config.base_url).hostname or ""
        if has_active_generation_backoff(
            window_days=window_days,
            semantic_fingerprint=fingerprint,
            publication_epoch=active_config.publication_epoch,
            prompt_version=active_config.prompt_version,
            provider=active_config.provider,
            provider_host=provider_host,
            llm_model_name=active_config.model,
            now=processed_at,
        ):
            _record_no_call(
                source_cycle_id=source_cycle_id,
                window_days=window_days,
                facts_as_of=facts_as_of,
                fingerprint=fingerprint,
                facts=snapshot,
                processed_at=processed_at,
                status=TrendNarrative.Status.SUPPRESSED,
                reason="provider_backoff",
            )
            stats["suppressed"] += 1
            continue

        owner = f"headline:{source_cycle_id}:{window_days}"[:128]
        attempt_started_at = now or clock()
        attempt = reserve_generation(
            source_cycle_id=source_cycle_id,
            window_days=window_days,
            facts_as_of=facts_as_of,
            semantic_fingerprint=fingerprint,
            generation_facts=snapshot,
            publication_epoch=active_config.publication_epoch,
            prompt_version=active_config.prompt_version,
            provider=active_config.provider,
            provider_host=provider_host,
            llm_model_name=active_config.model,
            owner=owner,
            now=attempt_started_at,
            lease_seconds=active_config.lease_seconds,
            output_schema_version=HEADLINE_OUTPUT_SCHEMA_VERSION,
        )
        if attempt is None:
            continue
        stats["slots_consumed"] += 1
        if not mark_transport_started(
            attempt.pk,
            owner=owner,
            fence=attempt.claim_fence,
            now=attempt_started_at,
        ):
            stats["failed"] += 1
            stats["errors"].append(f"{window_days}d:claim_lost")
            continue
        stats["transport_started"] += 1
        transport_completed = False
        try:
            generated = generate_trend_narrative(snapshot, active_config)
            transport_completed = mark_transport_completed(
                attempt.pk,
                owner=owner,
                fence=attempt.claim_fence,
                now=(now or clock()),
            )
            if generated.semantic_fingerprint != fingerprint:
                raise ValueError("generation fingerprint mismatch")
            published = publish_generation(
                attempt.pk,
                owner=owner,
                fence=attempt.claim_fence,
                body_en=generated.body_en,
                body_zh_cn=generated.body_zh_cn,
                output_hash=generated.output_hash,
                input_tokens=generated.input_tokens,
                output_tokens=generated.output_tokens,
                latency_ms=generated.latency_ms,
                now=now or clock(),
                observations_en=generated.observations_en,
                observations_zh_cn=generated.observations_zh_cn,
                selected_candidate_ids=generated.selected_candidate_ids,
                claims=generated.claims,
                subjects=generated.subjects,
            )
            if published:
                stats["published"] += 1
            else:
                stats["failed"] += 1
                stats["errors"].append(f"{window_days}d:claim_lost")
        except HeadlineGenerationError as exc:
            logger.warning(
                "trend narrative generation rejected for %sd source=%s category=%s",
                window_days,
                source_cycle_id,
                exc,
            )
            if exc.transport_completed:
                transport_completed = mark_transport_completed(
                    attempt.pk,
                    owner=owner,
                    fence=attempt.claim_fence,
                    now=(now or clock()),
                )
            _record_failure(
                attempt=attempt,
                owner=owner,
                config=active_config,
                processed_at=(now or clock()),
                error_code=exc.code,
                transport_completed=transport_completed,
            )
            stats["failed"] += 1
            stats["errors"].append(f"{window_days}d:generation_failed")
        except SoftTimeLimitExceeded:
            raise
        # Fail closed for unexpected provider/SDK/runtime errors while keeping
        # the consumed slot terminal and logging only the safe exception type.
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "trend narrative generation failed for %sd source=%s error_type=%s",
                window_days,
                source_cycle_id,
                type(exc).__name__,
            )
            _record_failure(
                attempt=attempt,
                owner=owner,
                config=active_config,
                processed_at=(now or clock()),
                error_code="headline_runtime_failure",
                transport_completed=transport_completed,
            )
            stats["failed"] += 1
            stats["errors"].append(f"{window_days}d:generation_failed")

    prune_narrative_history(
        now=processed_at,
        keep_days=config.retention_days,
        keep_per_window=config.retention_rows_per_window,
    )
    return stats


def _record_no_call(
    *,
    source_cycle_id: str,
    window_days: int,
    facts_as_of,
    fingerprint: str,
    facts: dict[str, Any],
    processed_at,
    status: str,
    reason: str,
) -> None:
    record_no_call_check(
        source_cycle_id=source_cycle_id,
        window_days=window_days,
        facts_as_of=facts_as_of,
        semantic_fingerprint=fingerprint,
        facts=facts,
        checked_at=processed_at,
        status=status,
        reason_code=reason,
    )


def _record_failure(
    *,
    attempt,
    owner,
    config,
    processed_at,
    error_code: str,
    transport_completed: bool,
) -> None:
    failures = attempt_failure_history(
        attempt,
        transport_completed=transport_completed,
    )
    consecutive_failures, next_attempt_at = next_failure_backoff(
        failures,
        window_days=attempt.window_days,
        now=processed_at,
        cadence_minutes=config.cadence_minutes,
        stale_minutes=config.stale_minutes,
    )
    fail_generation(
        attempt.pk,
        owner=owner,
        fence=attempt.claim_fence,
        error_code=error_code,
        now=processed_at,
        consecutive_failures=consecutive_failures,
        next_attempt_at=next_attempt_at,
    )


def _load_config() -> HeadlineNarrativeConfig:
    return load_config(Path("config.yaml")).headline_narrative


def _thresholds(config: HeadlineNarrativeConfig) -> TrendFactThresholds:
    return TrendFactThresholds(
        min_posts=config.min_posts,
        min_authors=config.min_authors,
        contested_ratio=config.contested_ratio,
        minimum_coverage=config.minimum_coverage,
        surging_ratio=config.surging_ratio,
        rising_ratio=config.rising_ratio,
        steady_ratio=config.steady_ratio,
        episode_peak_ratio=config.episode_peak_ratio,
    )


def _evidence_policy(
    config: HeadlineNarrativeConfig,
) -> EvidenceSelectionPolicy:
    return EvidenceSelectionPolicy(
        version=config.evidence_policy_version,
        reservoir_rank_limit=config.evidence_reservoir_rank_limit,
        floor=config.evidence_floor,
        lead_ceiling=config.evidence_lead_ceiling,
        comparison_ceiling=config.evidence_comparison_ceiling,
        excerpt_characters=config.evidence_excerpt_characters,
        provider_packet_bytes=config.evidence_provider_packet_bytes,
    )


def _validate_envelope(envelope: dict[str, Any]) -> tuple[str, datetime]:
    if not isinstance(envelope, dict) or envelope.get("schema_version") != 1:
        raise ValueError("invalid trend narrative envelope schema")
    if envelope.get("dry_run") is not False:
        raise ValueError("dry-run harvests cannot generate narratives")
    if envelope.get("outcome") not in {"completed", "degraded"}:
        raise ValueError("ineligible harvest outcome")
    source_cycle_id = str(envelope.get("source_cycle_id") or "")
    if not source_cycle_id or len(source_cycle_id) > 128:
        raise ValueError("invalid source cycle id")
    raw_completed_at = str(envelope.get("completed_at") or "")
    try:
        completed_at = datetime.fromisoformat(raw_completed_at)
    except ValueError as exc:
        raise ValueError("invalid envelope completion time") from exc
    if completed_at.tzinfo is None or completed_at.utcoffset() is None:
        raise ValueError("envelope completion time must be timezone-aware")
    return source_cycle_id, completed_at.astimezone(UTC)


# U4 durable per-brand graph.  The legacy shared-headline helper above stays
# importable for historical rows, but the production Celery entrypoint calls
# this graph.  A provider call is always reserved and marked sent before the
# one transport below; a redelivery can therefore only observe a terminal or
# leased row and cannot issue a second request.


def reconcile_per_brand_trend_narratives(
    envelope: dict[str, Any], *, now: datetime | None = None, enqueue=None
) -> dict[str, Any]:
    """Schedule bounded durable work for one harvest envelope and ready runs."""
    source_cycle_id, facts_as_of = _validate_envelope(envelope)
    config = _load_config()
    current = now or timezone.now()
    if current > facts_as_of + timedelta(seconds=config.task_expiry_seconds):
        return {"status": "expired", "transport_started": 0, "scheduled": 0}
    if not config.provider_calls_active:
        return {"status": "provider_disabled", "transport_started": 0, "scheduled": 0}
    enqueue = enqueue or _enqueue_per_brand_stage
    scheduled = 0
    for window_days in sorted(ALLOWED_TREND_WINDOWS):
        scheduled += _coalesce_window_envelope(
            window_days=window_days,
            source_cycle_id=source_cycle_id,
            facts_as_of=facts_as_of,
            config=config,
            now=current,
            enqueue=enqueue,
        )
    return {
        "status": "reconciled",
        "transport_started": 0,
        "scheduled": scheduled,
    }


def initialize_per_brand_snapshot(
    *,
    source_cycle_id: str,
    window_days: int,
    facts_as_of: datetime,
    owner: str = "",
    fence: int = 0,
    now: datetime | None = None,
    enqueue=None,
) -> TrendNarrativeRun | None:
    """Create one immutable run and resolve no-content/data-quality rows."""
    current = now or timezone.now()
    if not _owns_snapshot_slot(
        window_days=window_days,
        source_cycle_id=source_cycle_id,
        facts_as_of=facts_as_of,
        owner=owner,
        fence=fence,
        now=current,
    ):
        return None
    existing = TrendNarrativeRun.objects.filter(
        source_cycle_id=source_cycle_id, window_days=window_days
    ).first()
    if existing is not None:
        _attach_run_to_work_slot(existing)
        _reconcile_run(
            existing,
            config=_load_config(),
            now=current,
            enqueue=enqueue or _enqueue_per_brand_stage,
        )
        return existing
    config = _load_config()
    snapshot = build_trend_analysis_snapshot(
        window_days,
        as_of=facts_as_of,
        thresholds=_thresholds(config),
        evidence_policy=_evidence_policy(config),
    )
    dossiers = list(snapshot.get("dossiers") or [])
    manifest = [str(row["brand_key"]) for row in dossiers]
    with transaction.atomic():
        run, created = TrendNarrativeRun.objects.get_or_create(
            source_cycle_id=source_cycle_id,
            window_days=window_days,
            defaults={
                "facts_as_of": facts_as_of,
                "packet_schema_version": int(
                    snapshot.get("packet_schema_version") or 3
                ),
                "snapshot": snapshot,
                "brand_manifest": manifest,
                "internal_order": sorted(
                    manifest, key=lambda key: (key.casefold(), key)
                ),
            },
        )
        slot = TrendNarrativeWorkSlot.objects.select_for_update().get(
            window_days=window_days
        )
        if (
            slot.active_source_cycle_id != source_cycle_id
            or slot.active_facts_as_of != facts_as_of
        ):
            return None
        slot.active_run = run
        slot.snapshot_claim_owner = ""
        slot.snapshot_claim_fence = 0
        slot.snapshot_claimed_at = None
        slot.snapshot_claim_expires_at = None
        slot.save(
            update_fields=[
                "active_run",
                "snapshot_claim_owner",
                "snapshot_claim_fence",
                "snapshot_claimed_at",
                "snapshot_claim_expires_at",
                "updated_at",
            ]
        )
    if not created:
        return run
    for dossier in dossiers:
        outcome = str(dossier.get("outcome") or "data_quality_unavailable")
        if outcome == "narrative_eligible":
            continue
        status = (
            BrandTrendNarrative.Status.NO_CONTENT
            if outcome == "no_content"
            else BrandTrendNarrative.Status.DATA_QUALITY_UNAVAILABLE
        )
        _prepare_outcome(run, dossier, status=status, now=current, error_code=outcome)
    expected_calls = 1 + 2 * ((len([d for d in dossiers if d.get("outcome") == "narrative_eligible"]) + 4) // 5)
    if expected_calls > config.per_brand_call_cap:
        _suspend_run(
            run,
            reason="call_cap",
            config=config,
            now=current,
            enqueue=enqueue or _enqueue_per_brand_stage,
        )
        return run
    _reconcile_run(
        run, config=config, now=current, enqueue=enqueue or _enqueue_per_brand_stage
    )
    return run


def _coalesce_window_envelope(
    *,
    window_days: int,
    source_cycle_id: str,
    facts_as_of: datetime,
    config: HeadlineNarrativeConfig,
    now: datetime,
    enqueue,
) -> int:
    """Keep one active cutoff and replace only the one newer queued cutoff."""
    snapshot_job: dict[str, Any] | None = None
    active_run: TrendNarrativeRun | None = None
    with transaction.atomic():
        TrendNarrativeWorkSlot.objects.get_or_create(window_days=window_days)
        slot = TrendNarrativeWorkSlot.objects.select_for_update(
            of=("self",)
        ).select_related("active_run").get(window_days=window_days)
        if slot.active_run is not None and slot.active_run.status in {
            TrendNarrativeRun.Status.ACTIVE,
            TrendNarrativeRun.Status.SUPERSEDED,
            TrendNarrativeRun.Status.SUSPENDED,
        }:
            _promote_or_clear_slot(slot)
        if not slot.active_source_cycle_id:
            slot.active_source_cycle_id = source_cycle_id
            slot.active_facts_as_of = facts_as_of
        elif (
            source_cycle_id != slot.active_source_cycle_id
            and facts_as_of > slot.active_facts_as_of
            and (
                slot.queued_facts_as_of is None
                or facts_as_of > slot.queued_facts_as_of
            )
        ):
            slot.queued_source_cycle_id = source_cycle_id
            slot.queued_facts_as_of = facts_as_of
        if slot.active_run_id is None:
            snapshot_job = _claim_snapshot_slot(slot, config=config, now=now)
        else:
            active_run = slot.active_run
        slot.save()
    scheduled = 0
    if snapshot_job is not None:
        try:
            enqueue("snapshot", **snapshot_job)
            scheduled += 1
        except Exception:  # noqa: BLE001 - the persisted lease enables recovery
            logger.exception(
                "trend narrative snapshot broker handoff failed window=%s",
                window_days,
            )
    if active_run is not None and active_run.status in {
        TrendNarrativeRun.Status.PREPARING,
        TrendNarrativeRun.Status.TERMINAL,
    }:
        scheduled += _reconcile_run(
            active_run, config=config, now=now, enqueue=enqueue
        )
    return scheduled


def _claim_snapshot_slot(
    slot: TrendNarrativeWorkSlot,
    *,
    config: HeadlineNarrativeConfig,
    now: datetime,
) -> dict[str, Any] | None:
    """Claim an unbuilt active snapshot before its best-effort broker handoff."""
    if not slot.active_source_cycle_id or slot.active_facts_as_of is None:
        return None
    if (
        slot.snapshot_claim_expires_at is not None
        and slot.snapshot_claim_expires_at > now
    ):
        return None
    slot.snapshot_claim_fence += 1
    slot.snapshot_claim_owner = (
        f"snapshot:{slot.window_days}:{slot.snapshot_claim_fence}"
    )[:128]
    slot.snapshot_claimed_at = now
    slot.snapshot_claim_expires_at = now + timedelta(
        seconds=config.lease_seconds
    )
    return {
        "source_cycle_id": slot.active_source_cycle_id,
        "window_days": slot.window_days,
        "facts_as_of": slot.active_facts_as_of.isoformat(),
        "owner": slot.snapshot_claim_owner,
        "fence": slot.snapshot_claim_fence,
    }


def _owns_snapshot_slot(
    *,
    window_days: int,
    source_cycle_id: str,
    facts_as_of: datetime,
    owner: str,
    fence: int,
    now: datetime,
) -> bool:
    """Validate the durable snapshot handoff, with a direct-test adoption path."""
    with transaction.atomic():
        TrendNarrativeWorkSlot.objects.get_or_create(window_days=window_days)
        slot = TrendNarrativeWorkSlot.objects.select_for_update().get(
            window_days=window_days
        )
        if not owner and not fence:
            if not slot.active_source_cycle_id:
                slot.active_source_cycle_id = source_cycle_id
                slot.active_facts_as_of = facts_as_of
                slot.save()
            return (
                slot.active_source_cycle_id == source_cycle_id
                and slot.active_facts_as_of == facts_as_of
            )
        return (
            slot.active_source_cycle_id == source_cycle_id
            and slot.active_facts_as_of == facts_as_of
            and slot.snapshot_claim_owner == owner
            and slot.snapshot_claim_fence == fence
            and slot.snapshot_claim_expires_at is not None
            and slot.snapshot_claim_expires_at >= now
        )


def _attach_run_to_work_slot(run: TrendNarrativeRun) -> None:
    """Repair a committed run whose task died before attaching its work slot."""
    with transaction.atomic():
        TrendNarrativeWorkSlot.objects.get_or_create(window_days=run.window_days)
        slot = TrendNarrativeWorkSlot.objects.select_for_update().get(
            window_days=run.window_days
        )
        if not slot.active_source_cycle_id:
            slot.active_source_cycle_id = run.source_cycle_id
            slot.active_facts_as_of = run.facts_as_of
        if (
            slot.active_source_cycle_id == run.source_cycle_id
            and slot.active_facts_as_of == run.facts_as_of
        ):
            slot.active_run = run
            slot.snapshot_claim_owner = ""
            slot.snapshot_claim_fence = 0
            slot.snapshot_claimed_at = None
            slot.snapshot_claim_expires_at = None
            slot.save()


def _promote_or_clear_slot(slot: TrendNarrativeWorkSlot) -> None:
    """Promote the latest queued cutoff or make the window idle."""
    if slot.queued_source_cycle_id:
        slot.active_source_cycle_id = slot.queued_source_cycle_id
        slot.active_facts_as_of = slot.queued_facts_as_of
    else:
        slot.active_source_cycle_id = ""
        slot.active_facts_as_of = None
    slot.active_run = None
    slot.snapshot_claim_owner = ""
    slot.snapshot_claim_fence = 0
    slot.snapshot_claimed_at = None
    slot.snapshot_claim_expires_at = None
    slot.queued_source_cycle_id = ""
    slot.queued_facts_as_of = None


def _complete_work_slot(
    run: TrendNarrativeRun,
    *,
    config: HeadlineNarrativeConfig,
    now: datetime,
    enqueue,
) -> int:
    """Release one terminal run and durably hand off its latest queued cutoff."""
    snapshot_job: dict[str, Any] | None = None
    with transaction.atomic():
        slot = (
            TrendNarrativeWorkSlot.objects.select_for_update()
            .filter(window_days=run.window_days)
            .first()
        )
        if slot is None or (
            slot.active_run_id not in {None, run.pk}
            or slot.active_source_cycle_id != run.source_cycle_id
        ):
            return 0
        _promote_or_clear_slot(slot)
        if slot.active_source_cycle_id:
            snapshot_job = _claim_snapshot_slot(slot, config=config, now=now)
        slot.save()
    if snapshot_job is None:
        return 0
    try:
        enqueue("snapshot", **snapshot_job)
    except Exception:  # noqa: BLE001 - the persisted lease enables recovery
        logger.exception(
            "trend narrative promoted snapshot handoff failed window=%s",
            run.window_days,
        )
        return 0
    return 1


def _suspend_run(
    run: TrendNarrativeRun,
    *,
    reason: str,
    config: HeadlineNarrativeConfig,
    now: datetime,
    enqueue,
) -> None:
    """Persist a pre-send budget stop and release the window for newer work."""
    with transaction.atomic():
        locked = TrendNarrativeRun.objects.select_for_update().get(pk=run.pk)
        if locked.status != TrendNarrativeRun.Status.PREPARING:
            return
        locked.status = TrendNarrativeRun.Status.SUSPENDED
        locked.suspension_reason = reason[:64]
        locked.save(update_fields=["status", "suspension_reason", "updated_at"])
    _complete_work_slot(
        locked, config=config, now=now, enqueue=enqueue
    )


def execute_per_brand_stage(
    call_id: int, *, owner: str = "", fence: int = 0, now: datetime | None = None
) -> dict[str, Any]:
    """Execute exactly one rank, editor, or critic transport for a claimed call."""
    current = now or timezone.now()
    config = _load_config()
    call = TrendNarrativeProviderCall.objects.select_related("run").get(pk=call_id)
    if not config.provider_calls_active:
        return {"status": "provider_disabled", "call_id": call_id}
    if owner and fence:
        claimed = (
            call
            if call.claim_owner == owner
            and call.claim_fence == fence
            and call.claim_expires_at
            and call.claim_expires_at >= current
            else None
        )
    else:
        owner = f"per-brand:{call.pk}"[:128]
        claimed = claim_trend_narrative_provider_call(
            call.pk, owner=owner, now=current, lease_seconds=config.lease_seconds
        )
    if claimed is None:
        return {"status": "not_claimed", "call_id": call_id}
    if not mark_trend_narrative_provider_call_sent(
        claimed.pk, owner=owner, fence=claimed.claim_fence, now=current
    ):
        return {"status": "claim_lost", "call_id": call_id}
    try:
        response = execute_per_brand_provider_request(
            claimed.request_packet["provider_request"], config
        )
    except HeadlineGenerationError as exc:
        # Once sent, even a timeout is unknown rather than safely retryable.
        marker = (
            mark_trend_narrative_provider_call_ambiguous
            if not exc.transport_completed
            else fail_trend_narrative_provider_call
        )
        marker(
            claimed.pk,
            owner=owner,
            fence=claimed.claim_fence,
            error_code=exc.code,
            now=timezone.now(),
        )
        _reconcile_run(
            claimed.run,
            config=config,
            now=timezone.now(),
            enqueue=_enqueue_per_brand_stage,
        )
        return {"status": "terminal_failure", "call_id": call_id}
    payload = {
        "raw_text": response.raw_text,
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
        "latency_ms": response.latency_ms,
    }
    complete_trend_narrative_provider_call(
        claimed.pk,
        owner=owner,
        fence=claimed.claim_fence,
        response_hash=hashlib.sha256(response.raw_text.encode("utf-8")).hexdigest(),
        response_payload=payload,
        now=timezone.now(),
    )
    TrendNarrativeProviderCall.objects.filter(pk=claimed.pk).update(
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        latency_ms=response.latency_ms,
    )
    _reconcile_run(
        claimed.run, config=config, now=timezone.now(), enqueue=_enqueue_per_brand_stage
    )
    return {"status": "completed", "call_id": call_id}


def finalize_per_brand_run(run_id: int, *, now: datetime | None = None) -> bool:
    current = now or timezone.now()
    activated = activate_trend_narrative_run(run_id, now=current)
    run = TrendNarrativeRun.objects.get(pk=run_id)
    completed = activated
    if not activated:
        visible = TrendNarrativeVisibleRun.objects.filter(
            window_days=run.window_days,
            facts_as_of__gte=run.facts_as_of,
        ).first()
        if visible is not None:
            with transaction.atomic():
                locked = TrendNarrativeRun.objects.select_for_update().get(pk=run_id)
                if locked.status in {
                    TrendNarrativeRun.Status.PREPARING,
                    TrendNarrativeRun.Status.TERMINAL,
                }:
                    locked.status = TrendNarrativeRun.Status.SUPERSEDED
                    locked.activated_at = current
                    locked.save(
                        update_fields=["status", "activated_at", "updated_at"]
                    )
            completed = True
    if completed:
        _complete_work_slot(
            run,
            config=_load_config(),
            now=current,
            enqueue=_enqueue_per_brand_stage,
        )
    return completed


def _reconcile_run(run: TrendNarrativeRun, *, config, now: datetime, enqueue) -> int:
    """Materialize successors after durable terminal state, then enqueue them."""
    run.refresh_from_db()
    if run.status == TrendNarrativeRun.Status.TERMINAL:
        enqueue("finalize", run_id=run.pk)
        return 1
    if run.status != TrendNarrativeRun.Status.PREPARING:
        return 0
    eligible = [
        d
        for d in run.snapshot.get("dossiers", [])
        if d.get("outcome") == "narrative_eligible"
    ]
    if not eligible:
        TrendNarrativeRun.objects.filter(
            pk=run.pk, status=TrendNarrativeRun.Status.PREPARING
        ).update(status=TrendNarrativeRun.Status.TERMINAL)
        enqueue("finalize", run_id=run.pk)
        return 1
    try:
        rank = _ensure_call(
            run,
            "rank",
            "rank",
            config=config,
            packet=project_provider_packet(run.snapshot),
            now=now,
        )
    except _PerBrandBudgetExceeded as exc:
        _suspend_run(
            run,
            reason=exc.reason,
            config=config,
            now=now,
            enqueue=enqueue,
        )
        return 0
    if rank.state == TrendNarrativeProviderCall.State.RESERVED:
        _claim_and_enqueue(rank, config=config, now=now, enqueue=enqueue)
        return 1
    if rank.state == TrendNarrativeProviderCall.State.SENT:
        return 0
    batches = _resolved_batches(run, rank)
    scheduled = 0
    for batch in batches:
        key = str(batch["batch_key"])
        try:
            editor = _ensure_call(
                run, "editor", key, config=config, packet=batch, now=now
            )
        except _PerBrandBudgetExceeded as exc:
            _suspend_run(
                run,
                reason=exc.reason,
                config=config,
                now=now,
                enqueue=enqueue,
            )
            return scheduled
        if editor.state == TrendNarrativeProviderCall.State.RESERVED:
            _claim_and_enqueue(editor, config=config, now=now, enqueue=enqueue)
            scheduled += 1
            continue
        if editor.state in {
            TrendNarrativeProviderCall.State.AMBIGUOUS,
            TrendNarrativeProviderCall.State.FAILED,
        }:
            for dossier in batch["dossiers"]:
                _prepare_outcome(
                    run,
                    dossier,
                    status=BrandTrendNarrative.Status.HELD,
                    now=now,
                    error_code=editor.error_code or "editor_terminal",
                )
            continue
        if editor.state != TrendNarrativeProviderCall.State.COMPLETED:
            continue
        raw = str((editor.response_payload or {}).get("raw_text") or "")
        parse = _parse_editor(raw, editor.request_packet["envelope"])
        try:
            critic_envelope, _request = build_per_brand_critic_request(
                editor.request_packet["envelope"], raw, parse, config
            )
        except HeadlineGenerationError:
            for dossier in batch["dossiers"]:
                _prepare_outcome(
                    run,
                    dossier,
                    status=BrandTrendNarrative.Status.HELD,
                    now=now,
                    error_code="editor_packet_invalid",
                )
            continue
        try:
            critic = _ensure_call(
                run,
                "critic",
                key,
                config=config,
                packet=critic_envelope,
                now=now,
                provider_request=_request,
            )
        except _PerBrandBudgetExceeded as exc:
            _suspend_run(
                run,
                reason=exc.reason,
                config=config,
                now=now,
                enqueue=enqueue,
            )
            return scheduled
        if critic.state == TrendNarrativeProviderCall.State.RESERVED:
            _claim_and_enqueue(critic, config=config, now=now, enqueue=enqueue)
            scheduled += 1
        elif critic.state in {
            TrendNarrativeProviderCall.State.AMBIGUOUS,
            TrendNarrativeProviderCall.State.FAILED,
        }:
            for dossier in batch["dossiers"]:
                _prepare_outcome(
                    run,
                    dossier,
                    status=BrandTrendNarrative.Status.HELD,
                    now=now,
                    error_code=critic.error_code or "critic_terminal",
                )
        elif critic.state == TrendNarrativeProviderCall.State.COMPLETED:
            _apply_critic(run, batch, critic, now=now)
    if set(run.brand_narratives.values_list("brand_key_snapshot", flat=True)) == set(
        run.brand_manifest
    ):
        TrendNarrativeRun.objects.filter(
            pk=run.pk, status=TrendNarrativeRun.Status.PREPARING
        ).update(status=TrendNarrativeRun.Status.TERMINAL)
        enqueue("finalize", run_id=run.pk)
        scheduled += 1
    return scheduled


def _resolved_batches(
    run: TrendNarrativeRun, rank: TrendNarrativeProviderCall
) -> list[dict[str, Any]]:
    """Use model ordering when valid, otherwise canonical deterministic fallback."""
    if not run.batch_manifest:
        order = sorted(
            [
                str(d["brand_key"])
                for d in run.snapshot.get("dossiers", [])
                if d.get("outcome") == "narrative_eligible"
            ],
            key=lambda key: (key.casefold(), key),
        )
        if rank.state == TrendNarrativeProviderCall.State.COMPLETED:
            try:
                parsed = json.loads(
                    str((rank.response_payload or {}).get("raw_text") or "")
                )
                valid = validate_per_brand_rank_response(
                    parsed, rank.request_packet["envelope"]
                )
                order = [str(row["brand_key"]) for row in valid["ordered_brands"]]
            except (ValueError, TypeError, HeadlineGenerationError):
                pass
        batches = _batches_for_order(run.snapshot, order)
        run.internal_order = order
        run.batch_manifest = [
            {"batch_key": b["batch_key"], "brand_keys": b["manifest_brand_keys"]}
            for b in batches
        ]
        run.save(update_fields=["internal_order", "batch_manifest", "updated_at"])
    return _batches_for_order(run.snapshot, list(run.internal_order))


def _batches_for_order(
    snapshot: dict[str, Any], order: list[str]
) -> list[dict[str, Any]]:
    """Freeze the resolved rank/fallback order into exact one-to-five packets."""
    dossiers = {str(row["brand_key"]): row for row in snapshot.get("dossiers", [])}
    eligible = [
        key
        for key in order
        if dossiers.get(key, {}).get("outcome") == "narrative_eligible"
    ]
    batches = []
    for index in range(0, len(eligible), 5):
        keys = eligible[index : index + 5]
        batch = {
            "packet_schema_version": int(snapshot["packet_schema_version"]),
            "window_days": snapshot["window_days"],
            "as_of": snapshot["as_of"],
            "baseline_context": dict(snapshot["baseline_context"]),
            "batch_key": f"{snapshot['window_days']}d:{index // 5 + 1:03d}",
            "manifest_brand_keys": keys,
            "dossiers": [_provider_dossier(dossiers[key]) for key in keys],
        }
        _fit_editor_batch_to_packet_budget(batch)
        batches.append(batch)
    return batches


def _ensure_call(
    run, stage: str, batch_key: str, *, config, packet, now, provider_request=None
):
    if stage == "rank":
        envelope, request = build_per_brand_rank_request(packet, config)
    elif stage == "editor":
        envelope, request = build_per_brand_editor_request(packet, config)
    else:
        envelope, request = packet, provider_request
    if not isinstance(request, dict):
        raise HeadlineGenerationError("headline_provider_request_binding_failed")
    canonical = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    identity = f"tnr:{run.pk}:{stage}:{batch_key}:{digest[:24]}"[:128]
    with transaction.atomic():
        locked_run = TrendNarrativeRun.objects.select_for_update().get(pk=run.pk)
        existing = TrendNarrativeProviderCall.objects.filter(
            run=locked_run, stage=stage, batch_key=batch_key
        ).first()
        if existing is not None:
            return existing
        budget_reason = _provider_budget_reason(
            locked_run, next_request=request, config=config
        )
        if budget_reason:
            raise _PerBrandBudgetExceeded(budget_reason)
        reserved = reserve_trend_narrative_provider_call(
            run=locked_run,
            stage=stage,
            batch_key=batch_key,
            request_identity=identity,
            request_hash=digest,
            request_packet={"envelope": envelope, "provider_request": request},
            now=now,
        )
        return reserved or TrendNarrativeProviderCall.objects.get(
            run=locked_run, stage=stage, batch_key=batch_key
        )


def _provider_budget_reason(
    run: TrendNarrativeRun,
    *,
    next_request: dict[str, Any],
    config: HeadlineNarrativeConfig,
) -> str:
    """Return a closed pre-send budget reason, including reserved work."""
    calls = list(run.provider_calls.all())
    if len(calls) + 1 > config.per_brand_call_cap:
        return "call_cap"
    input_tokens = 0
    output_tokens = 0
    for call in calls:
        if (
            call.state == TrendNarrativeProviderCall.State.COMPLETED
            and (call.input_tokens or call.output_tokens)
        ):
            input_tokens += call.input_tokens
            output_tokens += call.output_tokens
            continue
        request = (call.request_packet or {}).get("provider_request") or {}
        estimated_input, estimated_output = _estimate_request_tokens(request)
        input_tokens += estimated_input
        output_tokens += estimated_output
    estimated_input, estimated_output = _estimate_request_tokens(next_request)
    input_tokens += estimated_input
    output_tokens += estimated_output
    if input_tokens > config.per_brand_input_token_cap:
        return "input_token_cap"
    if output_tokens > config.per_brand_output_token_cap:
        return "output_token_cap"
    cost = (
        Decimal(input_tokens)
        * config.per_brand_input_usd_per_million
        + Decimal(output_tokens)
        * config.per_brand_output_usd_per_million
    ) / Decimal(1_000_000)
    if cost > config.per_brand_cost_cap_usd:
        return "dollar_cap"
    return ""


def _estimate_request_tokens(request: dict[str, Any]) -> tuple[int, int]:
    """Conservatively estimate request input and reserve the full output bound."""
    canonical = json.dumps(request, sort_keys=True, separators=(",", ":"))
    input_tokens = max(1, (len(canonical.encode("utf-8")) + 3) // 4)
    output_tokens = max(0, int(request.get("max_tokens") or 0))
    return input_tokens, output_tokens


def _parse_editor(raw: str, envelope: dict[str, Any]) -> dict[str, Any]:
    try:
        validate_per_brand_editor_response(json.loads(raw), envelope)
    except (TypeError, ValueError, HeadlineGenerationError):
        return {"status": "invalid", "error_codes": ["editor_json_invalid"]}
    return {"status": "valid", "error_codes": []}


def _apply_critic(run, batch, call, *, now):
    try:
        response = json.loads(str((call.response_payload or {}).get("raw_text") or ""))
        valid = validate_per_brand_critic_response(
            response, call.request_packet["envelope"]
        )
    except (TypeError, ValueError, HeadlineGenerationError):
        valid = {
            "decisions": [
                {
                    "brand_key": d["brand_key"],
                    "decision": "hold",
                    "hold_code": "critic_response_invalid",
                    "narrative": None,
                }
                for d in batch["dossiers"]
            ]
        }
    dossier_by_key = {str(d["brand_key"]): d for d in batch["dossiers"]}
    for decision in valid["decisions"]:
        dossier = dossier_by_key[str(decision["brand_key"])]
        if decision["decision"] == "hold":
            _prepare_outcome(
                run,
                dossier,
                status=BrandTrendNarrative.Status.HELD,
                now=now,
                error_code=str(decision.get("hold_code") or "critic_hold"),
            )
            continue
        narrative = decision["narrative"]
        prepare_brand_trend_narrative(
            run=run,
            brand_key=str(dossier["brand_key"]),
            brand_name_en=str(dossier.get("display_name_en") or dossier["brand_key"]),
            brand_name_zh_cn=str(
                dossier.get("display_name_zh_cn") or dossier["brand_key"]
            ),
            status=BrandTrendNarrative.Status.APPROVED,
            attempted_at=now,
            verified_at=now,
            headline_en=narrative["headline_en"],
            headline_zh_cn=narrative["headline_zh_cn"],
            secondary_en=narrative["secondary_en"],
            secondary_zh_cn=narrative["secondary_zh_cn"],
            critic_decision=decision["decision"],
            narrative_kind=narrative["narrative_kind"],
            confidence=narrative["confidence"],
            propositions=narrative["propositions"],
            events=narrative["events"],
            cited_fact_ids=sorted(
                {
                    str(fact_id)
                    for proposition in narrative["propositions"]
                    for fact_id in proposition.get("fact_ids", [])
                }
            ),
            cited_evidence_ids=sorted(
                {
                    str(evidence_id)
                    for proposition in narrative["propositions"]
                    for evidence_id in proposition.get("evidence_ids", [])
                }
            ),
            selected_evidence_packet=dossier.get("evidence", []),
            final_critic_payload=decision,
        )


def _prepare_outcome(run, dossier, *, status, now, error_code):
    return prepare_brand_trend_narrative(
        run=run,
        brand_key=str(dossier["brand_key"]),
        brand_name_en=str(dossier.get("display_name_en") or dossier["brand_key"]),
        brand_name_zh_cn=str(dossier.get("display_name_zh_cn") or dossier["brand_key"]),
        status=status,
        attempted_at=now,
        error_code=error_code,
        selected_evidence_packet=dossier.get("evidence", []),
    )


def _enqueue_per_brand_stage(kind: str, **kwargs) -> None:
    """Broker handoff is intentionally best-effort; the next reconcile recovers it."""
    from monitor import tasks

    mapping = {
        "snapshot": tasks.initialize_trend_narrative_snapshot,
        "stage": tasks.execute_trend_narrative_stage,
        "finalize": tasks.finalize_trend_narrative_run,
    }
    mapping[kind].apply_async(kwargs=kwargs, queue="trend-narratives")


def _claim_and_enqueue(call, *, config, now, enqueue) -> bool:
    """Persist the broker handoff lease before enqueue; expiry repairs loss."""
    owner = f"enqueue:{call.pk}:{call.claim_fence + 1}"[:128]
    claim = claim_trend_narrative_provider_call(
        call.pk, owner=owner, now=now, lease_seconds=config.lease_seconds
    )
    if claim is None:
        return False
    try:
        enqueue("stage", call_id=call.pk, owner=owner, fence=claim.claim_fence)
    except Exception:  # noqa: BLE001 - lease expiry is the durable recovery path
        logger.exception("trend narrative stage broker handoff failed call=%s", call.pk)
        return False
    return True
