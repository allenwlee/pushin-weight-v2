"""Stable read-only reports of jobs, scopes, provenance and qualified coverage."""

from django.db.models import Q
from django.utils import timezone

from core.models import CollectionJob


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
    scope = job.definition["scope"]
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
        "budgets": job.definition["budgets"],
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
