"""Historical source evidence and coverage share existing runs/scopes/observations.

Numeric admission remains the reviewed history importer's responsibility. Missing
source evidence creates a coverage outcome, never a zero-valued metric row.
"""

from __future__ import annotations

from datetime import UTC, datetime

from core.benchmark_metric_store import aware_instant
from core.collection_state import (
    BusyJob,
    checkpoint_scope,
    claim_job,
    finish_run,
)
from core.measurement_taxonomy import require
from core.model_history_archives import (
    acquire_hf_archives,
    import_selected_history,
)
from core.model_history_cohort import (
    history_windows,
    validate_model_pins,
)
from core.model_history_publications import _publication_evidence
from core.model_native_history import _github_history, _hf_history
from core.models import (
    CollectionJob,
    CollectionObservation,
    CollectionRun,
    HFOrg,
)
from scripts.benchmark_download_collector.sources import (
    Budget,
    SourceError,
)

__all__ = [
    "COVERAGE_OUTCOMES",
    "acquire_hf_archives",
    "execute_model_history",
    "history_windows",
    "import_selected_history",
    "validate_model_pins",
]

COVERAGE_OUTCOMES = frozenset(
    {
        "observed",
        "not_published",
        "outside_provider_coverage",
        "history_unavailable",
        "unmapped",
        "partial",
        "inaccessible",
        "unranked",
        "failed",
    }
)


def _existing_evidence(job, model, pins):
    from django.db.models import Q

    selected = []
    rows = (
        CollectionObservation.objects.filter(
            run__source_id=job.source_id,
            source_identifier__in={p["native_identifier"] for p in pins},
            status="ok",
        )
        .filter(
            Q(mapping__isnull=True)
            | Q(mapping__subject__product_id=model["product_key"])
        )
        .filter(Q(dimensions__kind__isnull=True) | ~Q(dimensions__kind="coverage"))
        .order_by("-observed_at", "-pk")[:1000]
    )
    for row in rows:
        native_time = (
            row.published_at
            or row.published_date
            or row.source_metadata.get("source_record_date")
            or row.source_metadata.get("clocks", {}).get("committer_at")
            or row.source_metadata.get("archive_snapshot_date")
        )
        precision = "unknown"
        if native_time:
            if isinstance(native_time, datetime):
                instant = native_time
            else:
                try:
                    instant = aware_instant(str(native_time))
                except ValueError:
                    instant = None
            if instant is not None:
                if instant >= aware_instant(job.definition["scope"]["cutoff"]):
                    continue
                precision = "instant"
            elif len(str(native_time)) == 10:
                if (
                    str(native_time)
                    >= aware_instant(job.definition["scope"]["cutoff"])
                    .astimezone(UTC)
                    .date()
                    .isoformat()
                ):
                    continue
                precision = "date"
        selected.append(
            {
                "observation_id": row.pk,
                "run_id": str(row.run_id),
                "observed_at": row.observed_at.isoformat(),
                "publication_precision": row.publication_precision,
                "published_at": row.published_at.isoformat()
                if row.published_at
                else None,
                "published_date": row.published_date.isoformat()
                if row.published_date
                else None,
                "source_metadata": row.source_metadata,
                "dimensions": row.dimensions,
                "source_time_precision": precision,
                "source_time_before_cutoff": True if precision != "unknown" else None,
            }
        )
    return selected


def execute_model_history(job_id, *, budget=None, key=None):
    job = CollectionJob.objects.get(pk=job_id)
    require(job.operation == "model_history", "model history job required")
    require(
        job.definition["scope"].get("role") != "publication_window",
        "shared windows execute through their parent campaign",
    )
    validate_model_pins(job)
    claim = claim_job(job.pk)
    owned_client = None
    if budget is None:
        import httpx

        owned_client = httpx.Client(trust_env=False)
        limits = job.definition["budgets"]
        budget = Budget(
            owned_client,
            max_requests=limits["requests"],
            max_seconds=limits["seconds"],
            max_bytes=limits["bytes"],
        )
    limits = job.definition["budgets"]
    budget.cumulative = True
    budget.remaining = min(budget.remaining, limits["requests"])
    budget.max_bytes = min(budget.max_bytes, budget.total_bytes_read + limits["bytes"])
    budget.deadline = min(budget.deadline, budget.clock() + limits["seconds"])
    before = budget.remaining
    try:
        return _execute_models(claim, job, budget, key=key, before=before)
    except (ValueError, TypeError, KeyError, HFOrg.DoesNotExist) as exc:
        prior = CollectionRun.objects.get(pk=claim.run_id)
        return finish_run(
            claim,
            status="partial",
            request_count=prior.request_count
            + (before - budget.remaining if job.source_id in {"hf", "github"} else 0),
            report={
                "stop_reason": str(exc)
                if isinstance(exc, SourceError)
                else "invalid_history_evidence"
            },
        )
    finally:
        if owned_client:
            owned_client.close()


def _execute_models(claim, job, budget, *, key, before):
    coverage = []
    items = [0]
    archive_outcome = None
    if job.source_id == "hf":
        archive_outcome = acquire_hf_archives(claim, job, budget)
    for model in job.definition["scope"].get("models", []):
        pin = {
            "product_key": model["product_key"],
            "cohort_hash": job.definition["scope"]["cohort_hash"],
            "provider_pins": model.get("provider_pins", []),
        }
        old = (
            CollectionRun.objects.get(pk=claim.run_id)
            .scopes.filter(
                scope_kind="model_coverage",
                scope_key=model["product_key"],
                enumeration_complete=True,
            )
            .first()
        )
        if old:
            coverage.extend(old.envelopes)
            continue
        source_pins = [
            p for p in model.get("provider_pins", []) if p["source"] == job.source_id
        ]
        creation = model.get("creation", {})
        if (
            not source_pins
            and job.source_id == "hf"
            and creation.get("source") == "hf"
            and creation.get("native_identifier")
        ):
            source_pins = [
                {
                    "source": "hf",
                    "native_identifier": creation["native_identifier"],
                    "identifier_scope": "model",
                    "qualification": "first_party_creation_record",
                }
            ]
        windows, gaps = history_windows(
            model["creation"]["at"], job.definition["scope"]["cutoff"], job.source_id
        )
        pending_native = False
        inaccessible_reason = None
        if source_pins and job.source_id in {"hf", "github"}:
            try:
                (_hf_history if job.source_id == "hf" else _github_history)(
                    claim, job, source_pins, budget, items
                )
            except SourceError as exc:
                if str(exc) in {"not_found", "private", "http_404", "http_410"}:
                    inaccessible_reason = str(exc)
                else:
                    pending_native = True
        evidence = _existing_evidence(job, model, source_pins)
        outcome = (
            "unmapped"
            if not source_pins
            else "observed"
            if evidence
            else "history_unavailable"
        )
        reason = (
            "provider_mapping_missing"
            if not source_pins
            else "native_evidence_only"
            if evidence
            else "no_observed_or_reviewed_archive_history"
        )
        if pending_native:
            outcome, reason = "partial", "bounded_native_history_pending"
        if inaccessible_reason:
            outcome, reason = "inaccessible", inaccessible_reason
        if source_pins and job.source_id in {"openrouter", "arena"}:
            try:
                fetched, disposition = _publication_evidence(
                    claim, job, model, source_pins, budget, key=key
                )
                evidence.extend(fetched)
                outcome, reason = disposition["outcome"], disposition["reason"]
            except (SourceError, BusyJob):
                outcome, reason = "partial", "bounded_acquisition_pending"
        cell = {
            "product_key": model["product_key"],
            "source": job.source_id,
            "outcome": outcome,
            "requested_start_at": model["creation"]["at"],
            "requested_cutoff": job.definition["scope"]["cutoff"],
            "acquisition_windows": [list(window) for window in windows],
            "gaps": gaps,
            "evidence": evidence,
            "numeric_values_inferred": False,
            "coverage_complete": False,
            "native_evidence_reference_limit": 1000,
            "reason": reason,
        }
        checkpoint_scope(
            claim,
            scope_kind="model_coverage",
            scope_key=model["product_key"],
            ownership=pin,
            enumeration_complete=outcome != "partial",
            outcome=outcome,
            envelopes=[cell],
        )
        coverage.append(cell)
    run = CollectionRun.objects.get(pk=claim.run_id)
    return finish_run(
        claim,
        status="partial"
        if any(c["outcome"] == "partial" for c in coverage)
        else "success",
        selected_count=len(coverage),
        success_count=len(coverage),
        request_count=run.request_count
        + (before - budget.remaining if job.source_id in {"hf", "github"} else 0),
        report={
            **run.report,
            "coverage": coverage,
            "evaluated_cells": len(coverage),
            "observed_cells": sum(c["outcome"] == "observed" for c in coverage),
            "all_requested_history_available": bool(coverage)
            and all(c["coverage_complete"] for c in coverage),
            "archive": archive_outcome,
            "physical_requests_this_invocation": before - budget.remaining,
            "publication_requests_accounted_in_shared_window_runs": job.source_id
            in {"openrouter", "arena"},
        },
    )
