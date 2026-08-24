"""Bounded orchestration for one committed harvest completion envelope."""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from billiard.exceptions import SoftTimeLimitExceeded
from django.utils import timezone

from core.models import TrendNarrative
from monitor.trend_narrative_candidates import (
    EvidenceSelectionPolicy,
    build_trend_analysis_snapshot,
)
from monitor.trend_narrative_facts import (
    ALLOWED_TREND_WINDOWS,
    TrendFactThresholds,
)
from monitor.trend_narrative_generation import (
    HEADLINE_OUTPUT_SCHEMA_VERSION,
    HeadlineGenerationError,
    generate_trend_narrative,
    generation_fingerprint,
)
from monitor.trend_narrative_lifecycle import (
    abandon_expired_attempts,
    advance_current_check,
    fail_generation,
    mark_transport_completed,
    mark_transport_started,
    next_failure_backoff,
    prune_narrative_history,
    publish_generation,
    record_no_call_check,
    reserve_generation,
)
from x_monitor.config import HeadlineNarrativeConfig, load_config

logger = logging.getLogger(__name__)


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
        if config.provider_calls_enabled:
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
                (
                    "snapshot-failure-v1:"
                    f"{window_days}:{type(exc).__name__}"
                ).encode()
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
        if not active_config.provider_calls_enabled:
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

        failures = TrendNarrative.objects.filter(
            window_days=window_days,
            semantic_fingerprint=fingerprint,
            status__in=[
                TrendNarrative.Status.FAILED,
                TrendNarrative.Status.ABANDONED,
            ],
        )
        latest_failure = failures.order_by("-created_at", "-pk").first()
        if (
            latest_failure is not None
            and latest_failure.next_attempt_at is not None
            and latest_failure.next_attempt_at > processed_at
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
            provider_host=urlsplit(active_config.base_url).hostname or "",
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
        try:
            generated = generate_trend_narrative(snapshot, active_config)
            mark_transport_completed(
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
                mark_transport_completed(
                    attempt.pk,
                    owner=owner,
                    fence=attempt.claim_fence,
                    now=(now or clock()),
                )
            _record_failure(
                attempt=attempt,
                owner=owner,
                failures=failures,
                config=active_config,
                processed_at=(now or clock()),
                error_code=exc.code,
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
                failures=failures,
                config=active_config,
                processed_at=(now or clock()),
                error_code="headline_runtime_failure",
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
    *, attempt, owner, failures, config, processed_at, error_code: str
) -> None:
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
