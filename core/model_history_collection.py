"""Historical source evidence and coverage share existing runs/scopes/observations.

Numeric admission remains the reviewed history importer's responsibility. Missing
source evidence creates a coverage outcome, never a zero-valued metric row.
"""

from __future__ import annotations

from copy import copy, deepcopy
from datetime import UTC, datetime, timedelta

from django.utils import timezone

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
from core.model_history_statistics import history_statistics_contract
from core.model_native_history import _github_history, _hf_history
from core.models import (
    CollectionJob,
    CollectionObservation,
    CollectionRun,
    CompanyAccount,
)
from core.source_metric_projection import drain_pending_projections
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

    from core.collection_capture import observation_object_documents

    selected = []
    rows = (
        CollectionObservation.objects.filter(
            run__job__source_id=job.source_id,
            source_identifier__in={p["native_identifier"] for p in pins},
            status="ok",
        )
        .filter(
            Q(mapping__isnull=True)
            | Q(mapping__subject__product_id=model["product_key"])
        )
        .exclude(observation_kind="coverage")
        .select_related("legacy_archive", "resource_snapshot")
        .order_by("-observed_at", "-pk")[:1000]
    )
    for row in rows:
        _listing, dimensions, metadata = observation_object_documents(row)
        snapshot = row.resource_snapshot if hasattr(row, "resource_snapshot") else None
        native_time = (
            row.published_at
            or row.published_date
            or row.source_record_at
            or row.source_record_date
            or (snapshot.committed_at if snapshot else None)
            or row.archive_snapshot_date
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
                if instant >= aware_instant(job.scope["cutoff"]):
                    continue
                precision = "instant"
            elif len(str(native_time)) == 10:
                if (
                    str(native_time)
                    >= aware_instant(job.scope["cutoff"])
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
                "source_metadata": metadata,
                "dimensions": dimensions,
                "source_time_precision": precision,
                "source_time_before_cutoff": True if precision != "unknown" else None,
            }
        )
    return selected


def execute_model_history(job_id, *, budget=None, key=None):
    job = CollectionJob.objects.get(pk=job_id)
    require(job.operation == "model_history", "model history job required")
    require(
        job.scope.get("role") != "publication_window",
        "shared windows execute through their parent campaign",
    )
    validate_model_pins(job)
    history_statistics_contract(job)
    claim = claim_job(job.pk)
    job = _runtime_publication_window(claim, job)
    owned_client = None
    if budget is None:
        import httpx

        owned_client = httpx.Client(trust_env=False)
        limits = job.budgets
        budget = Budget(
            owned_client,
            max_requests=limits["requests"],
            max_seconds=limits["seconds"],
            max_bytes=limits["bytes"],
        )
    limits = job.budgets
    budget.cumulative = True
    budget.remaining = min(budget.remaining, limits["requests"])
    budget.max_bytes = min(budget.max_bytes, budget.total_bytes_read + limits["bytes"])
    budget.deadline = min(budget.deadline, budget.clock() + limits["seconds"])
    before = budget.remaining
    try:
        return _execute_models(claim, job, budget, key=key, before=before)
    except (ValueError, TypeError, KeyError, CompanyAccount.DoesNotExist) as exc:
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


def _runtime_publication_window(claim, job):
    """Freeze each rolling invocation's window in DB without changing the cohort."""
    policy = job.scope.get("publication_window_policy")
    if not policy:
        return job
    require(
        job.source_id in {"openrouter", "arena"}
        and policy == "rolling-completed-days-v1",
        "unsupported moving publication policy",
    )
    days = job.scope.get("publication_recheck_days", 7)
    require(
        type(days) is int and 1 <= days <= 90, "bounded publication recheck required"
    )
    run = CollectionRun.objects.get(pk=claim.run_id)
    old = run.scopes.filter(
        scope_kind="publication_runtime", scope_key="window"
    ).first()
    if old and old.requested_start_at and old.requested_end_at:
        start_at, cutoff = old.requested_start_at, old.requested_end_at
    elif old and job.instruction_version == 1:
        # Expansion adapter for preexisting frozen windows. No new execution
        # uses this representation once the typed bounds have been populated.
        start_at = aware_instant(old.envelopes[0]["publication_start_at"])
        cutoff = aware_instant(old.envelopes[0]["cutoff"])
    else:
        require(old is None, "saved publication window lacks typed bounds")
        cutoff = (
            timezone.now()
            .astimezone(UTC)
            .replace(hour=0, minute=0, second=0, microsecond=0)
        )
        start_at = cutoff - timedelta(days=days)
    window = {
        "cutoff": cutoff.isoformat(),
        "publication_start_at": start_at.isoformat(),
        "acquisition_generation": str(claim.run_id),
    }
    if old is None or old.requested_start_at is None or old.requested_end_at is None:
        checkpoint_scope(
            claim,
            scope_kind="publication_runtime",
            scope_key="window",
            ownership={
                "policy": policy,
                "cohort_hash": job.scope["cohort_hash"],
            },
            enumeration_complete=True,
            outcome="observed",
            envelopes=[window],
            requested_start_at=start_at,
            requested_end_at=cutoff,
        )
    runtime = copy(job)
    runtime.definition = deepcopy(job.definition)
    runtime._runtime_scope = {**job.scope, **window}
    return runtime


def _execute_models(claim, job, budget, *, key, before):
    prior_projection = drain_pending_projections(
        job.pk, budget=budget, origin_claim=claim
    )
    coverage = []
    items = [0]
    archive_outcome = None
    if job.source_id == "hf":
        archive_outcome = acquire_hf_archives(claim, job, budget)
    scope = job.scope
    if (
        job.source_id in {"openrouter", "arena"}
        and not scope.get("models")
        and scope.get("native_publication_identifiers")
    ):
        evidence, disposition = _publication_evidence(
            claim,
            job,
            {"creation": {"at": scope["global_start_at"]}},
            [],
            budget,
            key=key,
        )
        cell = {
            "source": job.source_id,
            "native_identifiers": scope["native_publication_identifiers"],
            "evidence": evidence,
            "coverage_complete": False,
            **disposition,
        }
        checkpoint_scope(
            claim,
            scope_kind="native_publication_coverage",
            scope_key="selection",
            ownership={"cohort_hash": scope["cohort_hash"]},
            enumeration_complete=disposition["outcome"] != "partial",
            outcome=disposition["outcome"],
            envelopes=[cell],
        )
        coverage.append(cell)
    for model in job.scope.get("models", []):
        pin = {
            "product_key": model["product_key"],
            "cohort_hash": job.scope["cohort_hash"],
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
            model["creation"]["at"], job.scope["cutoff"], job.source_id
        )
        pending_native = False
        inaccessible_reason = None
        if source_pins and job.source_id in {"hf", "github"}:
            try:
                (_hf_history if job.source_id == "hf" else _github_history)(
                    claim, job, source_pins, budget, items
                )
            except SourceError as exc:
                if str(exc) in {"not_found", "private", "http_404", "http_410"} or (
                    job.source_id == "hf" and str(exc) in {"unauthorized", "forbidden"}
                ):
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
            "requested_cutoff": job.scope["cutoff"],
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
    projection = drain_pending_projections(job.pk, budget=budget, origin_claim=claim)
    pending_projection = projection["pending"]
    return finish_run(
        claim,
        status="partial"
        if pending_projection or any(c["outcome"] == "partial" for c in coverage)
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
            "numeric_projection": {
                "before_acquisition": prior_projection,
                "after_acquisition": projection,
            },
            "physical_requests_this_invocation": before - budget.remaining,
            "physical_accounting_complete": True,
            "publication_requests_accounted_in_shared_window_runs": job.source_id
            in {"openrouter", "arena"},
        },
    )
