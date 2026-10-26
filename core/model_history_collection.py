"""Historical source evidence and coverage share existing runs/scopes/observations.

Numeric admission remains the reviewed history importer's responsibility. Missing
source evidence creates a coverage outcome, never a zero-valued metric row.
"""

from __future__ import annotations

from copy import copy, deepcopy
from datetime import UTC, datetime, timedelta

from django.db import transaction
from django.utils import timezone

from core.benchmark_metric_store import aware_instant
from core.collection_state import (
    BusyJob,
    checkpoint_scope,
    claim_job,
    finish_run,
)
from core.measurement_taxonomy import digest, require
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
    CollectionObservationInput,
    CollectionRun,
    CollectionScopeRun,
    CompanyAccount,
    Product,
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
    "history_report",
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

EVIDENCE_FACT_FIELDS = (
    "provider_revision", "source_record_at", "source_record_date",
    "original_retrieved_at", "archive_snapshot_date", "reconstruction_date",
    "history_reconstructed", "secondary_source", "publication_complete",
    "payload_sha256", "definition_sha256", "mapping_sha256",
)
EVIDENCE_FIELDS = (
    "id", "run_id", "source_identifier", "observed_at", "publication_precision",
    "published_at", "published_date", "observation_kind", "config_key",
    "category_key", "coordinate_key", "resource_snapshot", *EVIDENCE_FACT_FIELDS,
)


def _existing_evidence(job, model, pins):
    from django.db.models import Q

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
        .select_related("resource_snapshot")
        .only(*EVIDENCE_FIELDS)
        .order_by("-observed_at", "-pk")[:1000]
    )
    for row in rows:
        snapshot = row.resource_snapshot if hasattr(row, "resource_snapshot") else None
        native_time = _native_source_time(row, snapshot)
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
                **_typed_evidence_facts(row, snapshot),
                "source_time_precision": precision,
                "source_time_before_cutoff": True if precision != "unknown" else None,
            }
        )
    return selected


def _native_source_time(observation, snapshot):
    return (
        observation.published_at or observation.published_date
        or observation.source_record_at or observation.source_record_date
        or (snapshot.committed_at if snapshot else None)
        or observation.archive_snapshot_date
    )


def _typed_evidence_facts(observation, snapshot=None):
    """Source facts retain their original owner; raw documents are audit evidence."""
    def serialized(value):
        return value.isoformat() if hasattr(value, "isoformat") else value

    metadata = {
        name: serialized(getattr(observation, name))
        for name in EVIDENCE_FACT_FIELDS
        if getattr(observation, name) is not None
    }
    if snapshot is not None:
        metadata.update({
            "resource_revision": snapshot.revision,
            "tree_revision": snapshot.tree_revision,
            "publisher_account_id": snapshot.publisher_account_id,
            "clocks": {
                "author_at": serialized(snapshot.authored_at),
                "committer_at": serialized(snapshot.committed_at),
            },
        })
    return {
        "dimensions": {
            key: getattr(observation, field)
            for key, field in (
                ("kind", "observation_kind"), ("config", "config_key"),
                ("category", "category_key"), ("coordinate", "coordinate_key"),
            )
            if getattr(observation, field) is not None
        },
        "source_metadata": metadata,
    }


def _coverage_writer(claim, cell):
    """Freeze this evaluation's source owners without copying provider packets."""
    def write(run, scope):
        _retain_coverage_result(run, scope, cell, evaluation_key=str(claim.attempt_id))
    return write


def _retain_coverage_result(run, scope, cell, *, evaluation_key):
    require(type(cell["coverage_complete"]) is bool, "history coverage completeness must be explicit")
    require(cell["outcome"] in COVERAGE_OUTCOMES and type(cell["reason"]) is str
            and 0 < len(cell["reason"]) <= 64, "invalid history coverage outcome")
    product = (Product.objects.only("pk", "product_key").get(product_key=cell["product_key"])
               if cell.get("product_key") else None)
    identifiers = {entry["observation_id"] for entry in cell["evidence"]}
    sources = CollectionObservation.objects.filter(
        pk__in=identifiers, run__job__source_id=run.job.source_id,
    ).exclude(observation_kind="coverage")
    source_hashes = dict(sources.values_list("pk", "payload_sha256"))
    require(set(source_hashes) == identifiers,
            "history evidence owner is missing or belongs to another source")
    result, created = CollectionObservation.objects.get_or_create(
        run=run, observation_key=digest(["history-coverage", scope.pk, evaluation_key]),
        defaults={
            "scope_run": scope, "resource_key": evaluation_key,
            "source_dataset": scope.source_dataset, "observation_kind": "coverage",
            "source_subject_kind": "model" if cell.get("product_key") else "aggregate",
            "source_identifier": cell.get("product_key", str(run.job_id)),
            "product": product,
            "processing_outcome": cell["reason"], "publication_complete": cell["coverage_complete"],
            "definition_sha256": run.job.definition_sha256,
        },
    )
    require(result.scope_run_id == scope.pk and result.processing_outcome == cell["reason"]
            and result.publication_complete == cell["coverage_complete"]
            and result.product_id == (product.pk if product else None), "history evaluation identity changed")
    if created:
        CollectionObservationInput.objects.bulk_create([
            CollectionObservationInput(observation=result, input_observation_id=identifier,
                                       input_role="history_evidence", input_sha256=source_hashes[identifier])
            for identifier in sorted(identifiers)
        ])
    else:
        require(set(result.inputs.values_list("input_observation_id", flat=True)) == identifiers,
                "history evaluation evidence changed")
    scope.resource_observation = result


@transaction.atomic
def project_legacy_history_coverage(scope):
    """Explicit migration of one archived checkpoint; never a serving fallback.

    Archive the old columns first. This operation creates no HTTP request,
    attempt, or metric. Its new observation time records projection; the absent
    original evaluation timestamp remains unknown.
    """
    from core.collection_capture import read_document
    from core.collection_state import _validate_typed_model_history_scope

    scope = CollectionScopeRun.objects.select_for_update(of=("self",)).select_related("run__job", "legacy_archive").get(pk=scope.pk)
    require(scope.scope_kind in {"model_coverage", "native_publication_coverage"}
            and scope.legacy_archive_id is not None, "history coverage must be archived before projection")
    document = read_document(scope.legacy_archive)
    cells = document.get("envelopes") if isinstance(document, dict) else None
    require(isinstance(cells, list) and len(cells) == 1 and isinstance(cells[0], dict),
            "invalid archived history coverage checkpoint")
    if any(field.name == "envelopes" for field in CollectionScopeRun._meta.fields):
        require(not scope.envelopes or scope.envelopes == cells,
                "history coverage archive is stale")
    cell, job = cells[0], scope.run.job
    require(cell.get("source") == job.source_id and cell.get("outcome") == scope.outcome,
            "archived history coverage source or outcome changed")
    if scope.scope_kind == "model_coverage":
        require(cell.get("product_key") == scope.scope_key, "archived history product changed")
        start, end = aware_instant(cell["requested_start_at"]), aware_instant(cell["requested_cutoff"])
    else:
        require(cell.get("native_identifiers") == job.scope.get("native_publication_identifiers"),
                "archived native publication selection changed")
        runtime = scope.run.scopes.filter(scope_kind="publication_runtime", scope_key="window").first()
        start = runtime.requested_start_at if runtime else aware_instant(job.scope["global_start_at"])
        end = runtime.requested_end_at if runtime else aware_instant(job.scope["cutoff"])
    _validate_typed_model_history_scope(job, scope.run, scope.scope_kind, scope.scope_key,
                                       document.get("ownership"), start, end, None)
    require(scope.requested_start_at in (None, start) and scope.requested_end_at in (None, end),
            "history coverage typed bounds changed")
    if scope.resource_observation_id is not None:
        existing = _coverage_cell(scope, job)
        require(existing["reason"] == cell["reason"]
                and existing["coverage_complete"] == cell["coverage_complete"]
                and {row["observation_id"] for row in existing["evidence"]}
                == {row["observation_id"] for row in cell["evidence"]},
                "history coverage typed evidence differs from archive")
        return scope
    _retain_coverage_result(scope.run, scope, cell, evaluation_key=scope.legacy_archive.content_sha256)
    scope.requested_start_at, scope.requested_end_at = start, end
    scope.save(update_fields=["resource_observation", "requested_start_at", "requested_end_at"])
    return scope


def _coverage_cell(scope, job):
    from django.db.models import Prefetch

    result = scope.resource_observation
    require(result is not None and result.observation_kind == "coverage"
            and result.scope_run_id == scope.pk and result.run_id == scope.run_id,
            "saved history coverage needs typed migration before resume")
    require(scope.requested_start_at is not None and scope.requested_end_at is not None,
            "saved history coverage lacks typed bounds")
    evidence = []
    originals = CollectionObservation.objects.only(*EVIDENCE_FIELDS).select_related(
        "resource_snapshot",
    ).prefetch_related("values")
    inputs = result.inputs.filter(input_role="history_evidence").prefetch_related(
        Prefetch("input_observation", queryset=originals),
    ).order_by("input_observation_id")
    for link in inputs:
        original = link.input_observation
        require(link.input_sha256 is None or link.input_sha256 == original.payload_sha256,
                "history input checksum changed")
        snapshot = original.resource_snapshot if hasattr(original, "resource_snapshot") else None
        native_time = _native_source_time(original, snapshot)
        precision = "unknown" if native_time is None else "instant" if isinstance(native_time, datetime) else "date"
        before_cutoff = (
            None if native_time is None else native_time < scope.requested_end_at
            if precision == "instant" else native_time < scope.requested_end_at.astimezone(UTC).date()
        )
        evidence.append({
            "observation_id": original.pk, "run_id": str(original.run_id),
            "observed_at": original.observed_at.isoformat(),
            "publication_precision": original.publication_precision,
            "published_at": original.published_at.isoformat() if original.published_at else None,
            "published_date": original.published_date.isoformat() if original.published_date else None,
            "input_id": link.pk,
            "metric_value_ids": [value.pk for value in original.values.all()],
            "source_metric_ids": [value.source_metric_id for value in original.values.all()],
            "source_time_precision": precision, "source_time_before_cutoff": before_cutoff,
            **_typed_evidence_facts(original, snapshot),
        })
    cell = {
        "source": job.source_id, "outcome": scope.outcome,
        "reason": result.processing_outcome, "evidence": evidence,
        "coverage_observation_id": result.pk,
        "requested_start_at": scope.requested_start_at.isoformat(),
        "requested_cutoff": scope.requested_end_at.isoformat(),
        "numeric_values_inferred": False, "coverage_complete": result.publication_complete,
        "native_evidence_reference_limit": 1000,
    }
    if scope.scope_kind == "model_coverage":
        product_key = Product.objects.filter(pk=result.product_id).values_list("product_key", flat=True).first()
        require(product_key is not None and str(product_key) == scope.scope_key,
                "history coverage product changed")
        cell["product_key"] = str(product_key)
        windows, gaps = history_windows(scope.requested_start_at.isoformat(), scope.requested_end_at.isoformat(), job.source_id)
        cell.update(acquisition_windows=[list(window) for window in windows], gaps=gaps)
    else:
        cell["native_identifiers"] = job.scope["native_publication_identifiers"]
    return cell


def history_report(run):
    """Operational coverage from typed evaluations; raw packets remain evidence.

    Source observation/input and metric IDs replace echoed provider row arrays.
    Inspect those immutable captures for source wording; a missing numeric value
    is not reported as an empty provider response or inferred measurement.
    """
    job = run.job
    require(job.operation == "model_history", "history report requires a model-history run")
    coverage = [
        _coverage_cell(scope, job) for scope in run.scopes.filter(
            scope_kind__in=["model_coverage", "native_publication_coverage"],
        ).select_related("resource_observation").order_by("pk")
    ]
    attempt = run.attempts.order_by("-ordinal").first()
    pending = run.scopes.filter(scope_kind="numeric_projection").exclude(outcome="complete").exists()
    return {
        "coverage": coverage, "evaluated_cells": len(coverage),
        "observed_cells": sum(cell["outcome"] == "observed" for cell in coverage),
        "all_requested_history_available": bool(coverage) and all(cell["coverage_complete"] for cell in coverage),
        "stop_reason": run.error_code,
        "numeric_projection": {"after_acquisition": {"pending": pending}},
        "numeric_run_ids": sorted({str(identifier) for identifier in run.scopes.filter(
            scope_kind="archive_import", result_run__isnull=False,
        ).values_list("result_run_id", flat=True)}),
        "physical_requests_this_invocation": attempt.actual_requests if attempt else None,
        "physical_accounting_complete": attempt.accounting_complete if attempt else False,
        "publication_requests_accounted_in_shared_window_runs": job.source_id in {"openrouter", "arena"},
    }


def execute_model_history(job_id, *, budget=None, key=None):
    job = CollectionJob.objects.get(pk=job_id)
    require(job.operation == "model_history", "model history job required")
    require(
        job.scope.get("role") != "publication_window",
        "shared windows execute through their parent campaign",
    )
    validate_model_pins(job)
    history_statistics_contract(job)
    claim = claim_job(job.pk, typed=True)
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
            error_code=str(exc) if isinstance(exc, SourceError) else "invalid_history_evidence",
            typed=True, physical_accounting_complete=False,
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
            typed=True,
            requested_start_at=start_at,
            requested_end_at=cutoff,
        )
    runtime = copy(job)
    runtime.definition = deepcopy(job.definition)
    runtime._runtime_scope = {**job.scope, **window}
    return runtime


def _execute_models(claim, job, budget, *, key, before):
    drain_pending_projections(
        job.pk, budget=budget, origin_claim=claim
    )
    coverage = []
    items = [0]
    if job.source_id == "hf":
        acquire_hf_archives(claim, job, budget)
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
            requested_start_at=aware_instant(scope.get("publication_start_at") or scope["global_start_at"]),
            requested_end_at=aware_instant(scope["cutoff"]),
            typed=True, write=_coverage_writer(claim, cell),
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
            coverage.append(_coverage_cell(old, job))
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
            requested_start_at=aware_instant(model["creation"]["at"]),
            requested_end_at=aware_instant(job.scope["cutoff"]),
            typed=True, write=_coverage_writer(claim, cell),
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
        typed=True, physical_accounting_complete=True,
    )
