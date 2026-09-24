"""Secret-free, provider-free inspection of rare-type search ledgers."""

from __future__ import annotations

import json
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from core.intelligence_readers import rare_type_post_document
from core.models import (
    PostEnrichmentState,
    RareTypeDecisionAttempt,
    RareTypeSearchHit,
    RareTypeSearchRun,
    TargetedExtractionState,
)

USD_QUANTUM = Decimal("0.000000001")


def _iso(value):
    return value.isoformat() if value else None


def _elapsed_ms(start, end):
    if start is None or end is None:
        return None
    return max(round((end - start).total_seconds() * 1000), 0)


def _usd(value: Decimal) -> str:
    return str(value.quantize(USD_QUANTUM))


def _decision_attempt_cost(hits: list[RareTypeSearchHit], *, run_id: int) -> dict:
    """Summarize physical attempts for decisions referenced by this run's hits."""

    decision_ids = {hit.decision_id for hit in hits if hit.decision_id is not None}
    attempts = list(
        RareTypeDecisionAttempt.objects.filter(decision_id__in=decision_ids).values(
            "state", "reserved_usd", "accounted_usd", "confirmed_usd"
        )
    )
    settled = [
        attempt
        for attempt in attempts
        if attempt["state"] == RareTypeDecisionAttempt.State.SETTLED
    ]
    confirmed = [
        attempt for attempt in settled if attempt["confirmed_usd"] is not None
    ]
    unconfirmed = [
        attempt for attempt in settled if attempt["confirmed_usd"] is None
    ]
    reused_decision_count = (
        RareTypeSearchHit.objects.filter(decision_id__in=decision_ids)
        .exclude(run_id=run_id)
        .values("decision_id")
        .distinct()
        .count()
        if decision_ids
        else 0
    )
    confirmation_status = "not_applicable"
    if attempts:
        confirmation_status = (
            "complete" if len(confirmed) == len(attempts) else "incomplete"
        )
    return {
        "scope": "unique_decisions_referenced_by_run_hits",
        "billing_attribution": "decision_attempt_evidence_not_search_run_billing",
        "decision_count": len(decision_ids),
        "reused_decision_count": reused_decision_count,
        "attempt_count": len(attempts),
        "settled_attempt_count": len(settled),
        "unknown_usage_attempt_count": sum(
            attempt["state"] == RareTypeDecisionAttempt.State.RETAINED
            for attempt in attempts
        ),
        "in_flight_attempt_count": sum(
            attempt["state"]
            in {
                RareTypeDecisionAttempt.State.RESERVED,
                RareTypeDecisionAttempt.State.SENT,
            }
            for attempt in attempts
        ),
        "reservation_ceiling_usd": _usd(
            sum((attempt["reserved_usd"] for attempt in attempts), Decimal(0))
        ),
        "accounted_usd": _usd(
            sum((attempt["accounted_usd"] for attempt in settled), Decimal(0))
        ),
        "estimated_unconfirmed_usd": _usd(
            sum((attempt["accounted_usd"] for attempt in unconfirmed), Decimal(0))
        ),
        "confirmed_usd": (
            _usd(
                sum(
                    (attempt["confirmed_usd"] for attempt in confirmed), Decimal(0)
                )
            )
            if confirmed
            else None
        ),
        "confirmation_status": confirmation_status,
    }


def _hit_status(hit: RareTypeSearchHit) -> dict:
    enrichment = (
        PostEnrichmentState.objects.filter(post_id=hit.post_id).first()
        if hit.post_id
        else None
    )
    extraction = (
        list(
            TargetedExtractionState.objects.filter(post_id=hit.post_id)
            .order_by("role")
            .values(
                "role",
                "status",
                "attempts",
                "model",
                "prompt_version",
                "last_error_code",
                "last_attempted_at",
                "completed_at",
            )
        )
        if hit.post_id
        else []
    )
    decision = hit.decision
    return {
        "hit_id": hit.pk,
        "provider_post_id": hit.provider_post_id,
        "post_id": hit.post_id,
        "gate": {
            "state": hit.gate_state,
            "decision_status": decision.status if decision else None,
            "model": decision.model if decision else None,
            "question_version": decision.question_version if decision else None,
            "threshold_version": decision.threshold_version if decision else None,
            "derived_types": decision.derived_types if decision else [],
            "attempts": decision.attempts if decision else 0,
            "cost_usd": str(decision.cost_usd) if decision else None,
        },
        "classification": {
            "status": enrichment.classification_status if enrichment else None,
            "attempts": enrichment.classification_attempts if enrichment else 0,
            "error_code": enrichment.classification_error_code if enrichment else "",
        },
        "translation": {
            "status": enrichment.translation_status if enrichment else None,
            "attempts": enrichment.translation_attempts if enrichment else 0,
            "error_code": enrichment.translation_error_code if enrichment else "",
        },
        "extraction": extraction,
        "latency": {
            "fetched_at": _iso(hit.fetched_at),
            "gate_completed_at": _iso(hit.gate_completed_at),
            "post_persisted_at": _iso(hit.post_persisted_at),
            "classified_at": _iso(hit.classified_at),
            "extracted_at": _iso(hit.extracted_at),
            "first_visible_at": _iso(hit.first_visible_at),
            "fetch_to_gate_ms": _elapsed_ms(hit.fetched_at, hit.gate_completed_at),
            "fetch_to_post_ms": _elapsed_ms(hit.fetched_at, hit.post_persisted_at),
            "fetch_to_classification_ms": _elapsed_ms(
                hit.fetched_at, hit.classified_at
            ),
            "fetch_to_extraction_ms": _elapsed_ms(hit.fetched_at, hit.extracted_at),
            "fetch_to_visible_ms": _elapsed_ms(hit.fetched_at, hit.first_visible_at),
        },
        "last_error_code": hit.last_error_code,
    }


def run_status(run_id: int) -> dict:
    run = RareTypeSearchRun.objects.select_related("source_query").get(pk=run_id)
    hits = list(
        run.hits.select_related("decision", "post").order_by("fetched_at", "id")
    )
    states = {
        row["gate_state"]: row["count"]
        for row in run.hits.values("gate_state").annotate(count=Count("id"))
    }
    return {
        "schema_version": "rare-type-status/v1",
        "kind": "run",
        "run_id": run.pk,
        "status": run.status,
        "query": {
            "id": run.source_query.query_id,
            "version": run.query_version,
            "hash": run.query_hash,
            "rendered": run.query_string,
        },
        "window": {"start": _iso(run.window_start), "end": _iso(run.window_end)},
        "cost": {
            "twitterapi": {
                "reserved_credits": run.reserved_credits,
                "estimated_credits": run.estimated_credits,
                "confirmed_credits": run.confirmed_credits,
            },
            "jev": {
                "reserved_usd": str(run.decision_usd_reserved),
                "accounted_usd": str(run.decision_usd_accounted),
                "confirmed_usd": str(run.decision_usd_confirmed),
            },
            "jev_decision_attempts": _decision_attempt_cost(hits, run_id=run.pk),
        },
        "counts": {
            "requests": run.request_count,
            "raw": run.raw_result_count,
            "normalized": run.normalized_result_count,
            "persisted_posts": len(
                {str(hit.post_id) for hit in hits if hit.post_id is not None}
            ),
            "classified_hits": sum(hit.classified_at is not None for hit in hits),
            "extracted_hits": sum(hit.extracted_at is not None for hit in hits),
            "visible_hits": sum(hit.first_visible_at is not None for hit in hits),
            "gate_states": states,
        },
        "latency": {
            "dispatched_at": _iso(run.dispatched_at),
            "returned_at": _iso(run.returned_at),
            "finished_at": _iso(run.finished_at),
            "dispatch_to_return_ms": _elapsed_ms(run.dispatched_at, run.returned_at),
            "reservation_to_finish_ms": _elapsed_ms(run.reserved_at, run.finished_at),
        },
        "gap": {
            "present": run.has_coverage_gap,
            "reason": run.gap_reason,
            "start": _iso(run.gap_start),
            "end": _iso(run.gap_end),
            "truncated": run.truncated,
        },
        "error_code": run.error_code,
        "hits": [_hit_status(hit) for hit in hits],
    }


def post_status(post_id: str) -> dict:
    result = rare_type_post_document(post_id)
    hits = list(
        RareTypeSearchHit.objects.filter(post_id=post_id)
        .select_related("decision", "post")
        .order_by("fetched_at", "id")
    )
    result.update(
        {
            "schema_version": "rare-type-status/v1",
            "kind": "post",
            "hits": [_hit_status(hit) for hit in hits],
        }
    )
    return result


class Command(BaseCommand):
    help = "Show secret-free rare-type run or post status."

    def add_arguments(self, parser):
        target = parser.add_mutually_exclusive_group(required=True)
        target.add_argument("--run-id", type=int)
        target.add_argument("--post-id")
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        try:
            document = (
                run_status(options["run_id"])
                if options["run_id"]
                else post_status(options["post_id"])
            )
        except RareTypeSearchRun.DoesNotExist as exc:
            raise CommandError("rare-type run not found") from exc
        output = json.dumps(document, sort_keys=True, default=str)
        self.stdout.write(output)
