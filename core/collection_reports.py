"""Stable read-only reports of jobs, scopes, provenance and qualified coverage."""

from django.db.models import Prefetch, Q
from django.utils import timezone

from core.measurement_taxonomy import require
from core.models import (
    CollectionCorrection,
    CollectionJob,
    MetricCollectionContract,
    MetricValue,
)


def resource_statistics(*, contract_id, source, identifier, limit=1000, known_at=None):
    """Read native snapshots, with current or time-qualified attribution.

    known_at limits attribution corrections; it does not certify which provider
    data was publicly available at that time.
    """
    from core.collection_corrections import attribution_at

    require(type(limit) is int and 0 < limit <= 1000, "invalid numeric report limit")
    contract = MetricCollectionContract.objects.get(pk=contract_id)
    require(source in contract.source_configuration, "source outside contract")
    query = (
        MetricValue.objects.filter(
            observation__run__job__contract=contract,
            observation__run__job__source_id=source,
            observation__source_identifier=identifier,
            observation__status="ok",
            observation__run__status__in=["success", "partial"],
        )
        .select_related("observation__run", "source_metric")
        .prefetch_related(
            Prefetch(
                "observation__corrections",
                queryset=CollectionCorrection.objects.filter(
                    correction_kind="attribution"
                ),
                to_attr="attribution_history",
            )
        )
        .order_by("-observation__observed_at", "pk")
    )
    values = list(query[: limit + 1])
    rows = []
    for value in values[:limit]:
        observation, definition = value.observation, value.source_metric
        assignment = attribution_at(observation, known_at=known_at)
        rows.append(
            {
                "value_id": value.pk,
                "observation_id": observation.pk,
                "run_id": str(observation.run_id),
                "source_identifier": observation.source_identifier,
                "source_subject_kind": observation.source_subject_kind,
                "canonical_product_id": assignment["product_id"],
                "recorded_product_id": observation.product_id,
                "attribution_correction_id": str(assignment["correction_id"])
                if assignment["correction_id"]
                else None,
                "attribution_complete": assignment["assignment_complete"],
                "attribution_uncertainty_reason": assignment["uncertainty_reason"],
                "native_only": assignment["product_id"] is None,
                "metric": definition.metric_key,
                "version": definition.version,
                "unit": definition.unit_reference_id,
                "measurement_kind": definition.measurement_kind,
                "value": str(value.integer_value)
                if value.integer_value is not None
                else value.float_value,
                "observed_at": observation.observed_at.isoformat(),
                "temporal_status": value.temporal_status,
                **{
                    field: getattr(value, field).isoformat()
                    if getattr(value, field) is not None
                    else None
                    for field in (
                        "as_of_at",
                        "as_of_date",
                        "window_start_at",
                        "window_end_at",
                        "period_label_date",
                    )
                },
                "dimensions": observation.dimensions,
                "source_evidence": observation.source_metadata,
            }
        )
    return _redact(
        {
            "contract_id": str(contract.pk),
            "source": source,
            "source_identifier": identifier,
            "values": rows,
            "truncated": len(values) > limit,
            "limit": limit,
        }
    )


def _run(run):
    if run is None:
        return None
    return {
        "run_id": str(run.pk),
        "status": run.status,
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "request_count": run.request_count,
        "selected_count": run.selected_count,
        "success_count": run.success_count,
        "error_code": run.error_code,
    }


def _redact(value):
    if isinstance(value, dict):
        return {
            k: "[redacted]"
            if str(k).casefold()
            in {"authorization", "api_key", "token", "password", "secret", "cookie"}
            or str(k).casefold().endswith(("_api_key", "_token"))
            else _redact(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def job_status(job_id, *, now=None):
    return _redact(_job_status(job_id, now=now))


def _job_status(job_id, *, now=None):
    now = now or timezone.now()
    job = CollectionJob.objects.select_related(
        "source", "active_run", "last_attempt", "last_success"
    ).get(pk=job_id)
    active = job.active_run
    attempt = job.last_attempt
    scope = job.scope
    health = (
        "expired_lease"
        if active and active.lease_expires_at <= now
        else "running"
        if active
        else "cooldown"
        if job.next_retry_at and job.next_retry_at > now
        else job.state
    )
    coverage = attempt.report.get("coverage", []) if attempt else []
    return {
        "schema_version": 1,
        "job_id": str(job.pk),
        "job_key": job.job_key,
        "source": job.source_id,
        "purpose": job.purpose,
        "operation": job.operation,
        "mode": job.mode,
        "state": job.state,
        "health": health,
        "definition_sha256": job.definition_sha256,
        "cohort_hash": scope.get("cohort_hash"),
        "brand_id": scope.get("brand_id"),
        "cutoff": scope.get("cutoff"),
        "selected_models": scope.get("models", []),
        "qualification": scope.get("qualification"),
        "coverage": coverage,
        "coverage_evaluations": len(coverage),
        "unevaluated_cells": max(0, len(scope.get("models", [])) - len(coverage)),
        "all_requested_history_available": attempt.report.get(
            "all_requested_history_available", False
        )
        if attempt
        else False,
        "last_attempt": _run(attempt),
        "last_success": _run(job.last_success),
        "active_claim": {
            "run_id": str(active.pk),
            "expires_at": active.lease_expires_at.isoformat(),
        }
        if active
        else None,
        "next_due_at": job.next_due_at.isoformat() if job.next_due_at else None,
        "next_retry_at": job.next_retry_at.isoformat() if job.next_retry_at else None,
        "budgets": job.budgets,
        "scopes": [
            {
                "scope_run_id": s.pk,
                "kind": s.scope_kind,
                "key": s.scope_key,
                "outcome": s.outcome,
                "enumeration_complete": s.enumeration_complete,
                "has_continuation": bool(s.cursor),
                "raw_count": s.raw_count,
            }
            for s in attempt.scopes.order_by("pk")[:1000]
        ]
        if attempt
        else [],
        "scope_report_limit": 1000,
        "next_action": "reconcile_expired_claim"
        if health == "expired_lease"
        else "wait"
        if health in {"running", "cooldown"}
        else "explicit_activation_required"
        if job.state == "paused"
        else "none"
        if job.state in {"completed", "cancelled"}
        else "execute_bounded_continuation",
        "release_date_inferred": False,
        "matching": {
            "ruleset": scope["ruleset"],
            "preview_sha256": scope["preview_sha256"],
            "candidate_count": len(scope["matches"]),
            "reviewed_by": scope["review"]["reviewed_by"],
            "reviewed_candidate_count": len(scope["review"]["candidate_ids"]),
            "decisions": attempt.report.get("decisions", {}) if attempt else {},
            "remaining": attempt.report.get("remaining", len(scope["matches"]))
            if attempt
            else len(scope["matches"]),
        }
        if job.operation == "match_crosswalk"
        else None,
    }


def campaign_status(cohort_hash):
    jobs = list(
        CollectionJob.objects.filter(definition__scope__cohort_hash=cohort_hash)
        .filter(
            Q(definition__scope__role__isnull=True)
            | ~Q(definition__scope__role="publication_window")
        )
        .order_by("job_key")[:84]
    )
    cells = [job_status(job.pk) for job in jobs]
    return {
        "schema_version": 1,
        "cohort_hash": cohort_hash,
        "job_count": len(cells),
        "brands": sorted({c["brand_id"] for c in cells if c["brand_id"]}),
        "cells": cells,
        "complete_public_history_claimed": False,
    }
