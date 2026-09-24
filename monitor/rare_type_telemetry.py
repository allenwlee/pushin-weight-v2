"""Counts-only telemetry for the optional rare-type harvest lane."""

from __future__ import annotations

import math
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from django.db.models import Q

from core.models import (
    BrandDiscoveryCandidateTokenEvidence,
    EventEvidence,
    JobListingEvidence,
    ModelReleaseEvidence,
    Opportunity,
    PersonBrandAffiliationEvidence,
    PostEnrichmentState,
    ProductVerificationProposal,
    RareTypeDecision,
    RareTypeDecisionAttempt,
    RareTypeDecisionProcessingCycle,
    RareTypeSearchHit,
    RareTypeSearchRun,
    TargetedExtractionState,
)


def _sum_int(rows: list[Mapping[str, Any]], key: str) -> int:
    total = 0
    for row in rows:
        try:
            total += max(int(row.get(key) or 0), 0)
        except (TypeError, ValueError):
            continue
    return total


def _durations_ms(hits: list[RareTypeSearchHit], field: str) -> list[int]:
    durations: list[int] = []
    for hit in hits:
        end = getattr(hit, field, None)
        if end is None:
            continue
        durations.append(max(round((end - hit.fetched_at).total_seconds() * 1000), 0))
    return durations


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[max(math.ceil(len(ordered) * 0.95) - 1, 0)]


def build_rare_type_cycle_summary(summary: Mapping[str, Any]) -> dict[str, int | float | str] | None:
    """Build a redaction-safe projection for rare calls present in one cycle.

    Current-cycle result and record counts are scoped to the durable search-run
    IDs emitted by those calls. Pending queue counts are deliberately global,
    because they answer the operator's separate "what work remains?" question.
    """

    rare_calls = [
        row
        for row in (summary.get("calls") or [])
        if isinstance(row, Mapping) and row.get("call_id") == "RARE_EXTRA"
    ]
    if not rare_calls:
        return None

    run_ids: set[int] = set()
    for row in rare_calls:
        try:
            if row.get("run_id") is not None:
                run_ids.add(int(row["run_id"]))
        except (TypeError, ValueError):
            continue

    runs = list(RareTypeSearchRun.objects.filter(pk__in=run_ids).order_by("id"))
    hits = list(
        RareTypeSearchHit.objects.filter(run_id__in=run_ids)
        .select_related("decision", "post")
        .order_by("id")
    )
    post_ids = {str(hit.post_id) for hit in hits if hit.post_id is not None}

    processing_cycles = RareTypeDecisionProcessingCycle.objects.none()
    started_at = summary.get("started_at")
    if started_at:
        try:
            parsed_start = datetime.fromisoformat(str(started_at))
            if parsed_start.tzinfo is None:
                parsed_start = parsed_start.replace(tzinfo=UTC)
            parsed_start = parsed_start.astimezone(UTC)
            slot_start = parsed_start.replace(
                minute=(parsed_start.minute // 15) * 15,
                second=0,
                microsecond=0,
            )
            service_name = os.environ.get("RENDER_SERVICE_NAME", "").lower()
            environment = "staging" if "staging" in service_name else "normal"
            processing_cycles = RareTypeDecisionProcessingCycle.objects.filter(
                lane="rare_types",
                environment=environment,
                slot_start=slot_start,
            )
        except ValueError:
            pass
    processing_cycle_ids = list(processing_cycles.values_list("id", flat=True))
    jev_attempts = RareTypeDecisionAttempt.objects.filter(
        processing_cycle_id__in=processing_cycle_ids
    )
    if not processing_cycle_ids:
        jev_attempts = RareTypeDecisionAttempt.objects.filter(
            decision__hits__run_id__in=run_ids
        ).distinct()
    if processing_cycle_ids:
        jev_slot_usd_reserved = sum(
            cycle.decision_usd_reserved for cycle in processing_cycles
        )
        jev_slot_usd_accounted = sum(
            cycle.decision_usd_accounted for cycle in processing_cycles
        )
        jev_slot_usd_confirmed = sum(
            cycle.decision_usd_confirmed for cycle in processing_cycles
        )
    else:
        jev_slot_usd_reserved = sum(
            attempt.reserved_usd
            for attempt in jev_attempts
            if attempt.state in {"reserved", "sent", "retained"}
        )
        jev_slot_usd_accounted = sum(
            attempt.accounted_usd for attempt in jev_attempts
        )
        jev_slot_usd_confirmed = sum(
            attempt.confirmed_usd or 0 for attempt in jev_attempts
        )

    gate_counts = {
        state: sum(hit.gate_state == state for hit in hits)
        for state in RareTypeSearchHit.GateState.values
    }
    decision_statuses = {
        status: sum(bool(hit.decision and hit.decision.status == status) for hit in hits)
        for status in RareTypeDecision.Status.values
    }

    release_evidence = ModelReleaseEvidence.objects.filter(source_post_id__in=post_ids)
    event_evidence = EventEvidence.objects.filter(source_post_id__in=post_ids)
    job_evidence = JobListingEvidence.objects.filter(source_post_id__in=post_ids)
    affiliation_evidence = PersonBrandAffiliationEvidence.objects.filter(
        source_post_id__in=post_ids
    )
    opportunities = Opportunity.objects.filter(source_post_id__in=post_ids)
    token_evidence = BrandDiscoveryCandidateTokenEvidence.objects.filter(
        source_hit__run_id__in=run_ids
    )

    domain_record_counts = {
        "model_releases": release_evidence.values("release_id").distinct().count(),
        "events": event_evidence.values("event_id").distinct().count(),
        "job_listings": job_evidence.values("listing_id").distinct().count(),
        "affiliations": affiliation_evidence.values("affiliation_id").distinct().count(),
        "opportunities": opportunities.values("id").distinct().count(),
    }
    evidence_counts = {
        "model_releases": release_evidence.count(),
        "events": event_evidence.count(),
        "job_listings": job_evidence.count(),
        "affiliations": affiliation_evidence.count(),
        # Opportunity currently carries its source directly on the canonical row.
        "opportunities": opportunities.count(),
    }

    pending_hit_filter = Q(
        gate_state__in=[
            RareTypeSearchHit.GateState.DECISION_PENDING,
            RareTypeSearchHit.GateState.PROVIDER_FAILED,
            RareTypeSearchHit.GateState.REVIEW_NEEDED,
        ]
    )
    gate_latency = _durations_ms(hits, "gate_completed_at")
    post_latency = _durations_ms(hits, "post_persisted_at")
    classification_latency = _durations_ms(hits, "classified_at")
    extraction_latency = _durations_ms(hits, "extracted_at")
    visible_latency = _durations_ms(hits, "first_visible_at")

    result: dict[str, int | float | str] = {
        "schema_version": "1",
        "n_provider_attempts": sum(bool(row.get("provider_called")) for row in rare_calls),
        "n_raw_paid_results": _sum_int(rare_calls, "raw_count"),
        "n_normalized_hits": _sum_int(rare_calls, "normalized_count"),
        "search_credits_reserved": sum(run.reserved_credits for run in runs),
        "search_credits_estimated": sum(run.estimated_credits or 0 for run in runs),
        "search_credits_confirmed": sum(run.confirmed_credits or 0 for run in runs),
        "n_search_credit_confirmations": sum(
            run.confirmed_credits is not None for run in runs
        ),
        "n_search_usage_unknown": sum(
            run.status == RareTypeSearchRun.Status.USAGE_UNKNOWN for run in runs
        ),
        # Jev funding is keyed by the shared 15-minute processing slot, not by
        # the source search run. It can therefore include old saved hits and
        # concurrent workers that draw from the same gate allocation.
        "jev_slot_usd_reserved": float(jev_slot_usd_reserved),
        "jev_slot_usd_accounted": float(jev_slot_usd_accounted),
        "jev_slot_usd_confirmed": float(jev_slot_usd_confirmed),
        "n_jev_slot_attempts": jev_attempts.count(),
        "n_jev_completed": decision_statuses.get(RareTypeDecision.Status.COMPLETED, 0),
        "n_jev_review_needed": decision_statuses.get(
            RareTypeDecision.Status.REVIEW_NEEDED, 0
        ),
        "n_jev_failed": decision_statuses.get(RareTypeDecision.Status.FAILED, 0),
        "n_hits_kept": gate_counts.get(RareTypeSearchHit.GateState.KEPT, 0),
        "n_hits_junk": gate_counts.get(RareTypeSearchHit.GateState.JUNK, 0),
        "n_posts_persisted": len(post_ids),
        "n_posts_classified": len(
            {
                str(hit.post_id)
                for hit in hits
                if hit.post_id is not None and hit.classified_at is not None
            }
        ),
        "n_posts_extracted": len(
            {
                str(hit.post_id)
                for hit in hits
                if hit.post_id is not None and hit.extracted_at is not None
            }
        ),
        "n_posts_visible": len(
            {
                str(hit.post_id)
                for hit in hits
                if hit.post_id is not None and hit.first_visible_at is not None
            }
        ),
        "n_canonical_records": sum(domain_record_counts.values()),
        "n_evidence_attachments": sum(evidence_counts.values()),
        "n_model_releases": domain_record_counts["model_releases"],
        "n_model_release_evidence": evidence_counts["model_releases"],
        "n_events": domain_record_counts["events"],
        "n_event_evidence": evidence_counts["events"],
        "n_opportunities": domain_record_counts["opportunities"],
        "n_opportunity_evidence": evidence_counts["opportunities"],
        "n_job_listings": domain_record_counts["job_listings"],
        "n_job_evidence": evidence_counts["job_listings"],
        "n_affiliations": domain_record_counts["affiliations"],
        "n_affiliation_evidence": evidence_counts["affiliations"],
        "n_unknown_tokens": token_evidence.values("token_id").distinct().count(),
        "n_unknown_token_evidence": token_evidence.count(),
        "n_pending_hits_global": RareTypeSearchHit.objects.filter(
            pending_hit_filter
        ).count(),
        "n_pending_post_persistence_global": RareTypeSearchHit.objects.filter(
            gate_state=RareTypeSearchHit.GateState.KEPT,
            post_id__isnull=True,
        ).count(),
        "n_pending_classification": PostEnrichmentState.objects.filter(
            post_id__in=post_ids,
            classification_status=PostEnrichmentState.Status.PENDING,
        ).count(),
        "n_pending_extraction": TargetedExtractionState.objects.filter(
            post_id__in=post_ids,
            status__in=["pending", "failed"],
        ).count(),
        "n_pending_product_verification": ProductVerificationProposal.objects.filter(
            source_post_id__in=post_ids,
            review_status="pending",
            resolved_product_id__isnull=True,
        ).count(),
        "n_gap_runs": sum(run.has_coverage_gap for run in runs),
        "n_truncated_runs": sum(run.truncated for run in runs),
        "fetch_to_gate_p95_ms": _p95(gate_latency),
        "fetch_to_post_p95_ms": _p95(post_latency),
        "fetch_to_classification_p95_ms": _p95(classification_latency),
        "fetch_to_extraction_p95_ms": _p95(extraction_latency),
        "fetch_to_visible_p95_ms": _p95(visible_latency),
    }
    return result
