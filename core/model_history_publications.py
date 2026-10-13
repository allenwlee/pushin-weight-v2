"""Shared provider publication windows and selected-model evidence.

Numeric admission remains the reviewed history importer's responsibility. Missing
source evidence creates a coverage outcome, never a zero-valued metric row.
"""

from __future__ import annotations

import copy

from django.db import transaction
from django.utils import timezone

from core.collection_jobs import register_job, set_job_state
from core.collection_state import (
    checkpoint_scope,
    claim_job,
    finish_run,
)
from core.measurement_taxonomy import digest, require
from core.model_history_archives import import_selected_history
from core.model_history_cohort import history_windows
from core.models import (
    CollectionJob,
    CollectionObservation,
    DataSource,
    SourceSubjectMapping,
)
from scripts.benchmark_download_collector.sources import (
    SourceError,
    arena,
    openrouter,
)


def _window_key(source, cohort_hash, start, end, config):
    return digest(
        {
            "source": source,
            "cohort_hash": cohort_hash,
            "start": start,
            "end": end,
            "config": config,
        }
    )


def _publication_window(parent, budget, start, end, *, key, config):
    """A shared instruction serializes acquisition; DB evidence survives temp-file loss."""
    scope = parent.definition["scope"]
    cache_key = _window_key(parent.source_id, scope["cohort_hash"], start, end, config)
    cached = (
        CollectionObservation.objects.filter(
            run__source_id=parent.source_id,
            status="ok",
            dimensions__kind="publication_window",
            dimensions__cache_key=cache_key,
        )
        .order_by("pk")
        .first()
    )
    if cached:
        return cached
    definition = {
        "version": 1,
        "scope": {
            "role": "publication_window",
            "cohort_hash": scope["cohort_hash"],
            "start_date": start,
            "end_date": end,
            "config": config,
            "models": [],
        },
        "schedule": {"kind": "manual", "driver": "manual"},
        "budgets": parent.definition["budgets"],
    }
    with transaction.atomic():
        DataSource.objects.select_for_update().get(pk=parent.source_id)
        shared = CollectionJob.objects.filter(
            job_key="publication-window:" + cache_key
        ).first()
        if shared is None:
            shared = register_job(
                job_key="publication-window:" + cache_key,
                source=parent.source,
                purpose="catalog",
                operation="model_history",
                mode="historical",
                definition=definition,
            )
        require(
            shared.definition["scope"] == definition["scope"],
            "shared publication identity changed",
        )
    if shared.state == "paused":
        set_job_state(shared.pk, "ready")
    claim = claim_job(shared.pk)
    parent_remaining = budget.remaining
    budget.remaining = min(budget.remaining, shared.definition["budgets"]["requests"])
    before = budget.remaining
    try:
        payload = (
            openrouter(budget, start, end, key=key)
            if parent.source_id == "openrouter"
            else arena(budget, start, end, history=True, config=config)
        )
        require(
            budget.total_bytes_read <= budget.max_bytes, "global byte budget exceeded"
        )
        require(
            len(payload["rows"]) <= shared.definition["budgets"]["items"],
            "publication row budget exceeded",
        )

        def write(run, scoped):
            CollectionObservation.objects.get_or_create(
                run=run,
                observation_key=cache_key,
                defaults={
                    "scope_run": scoped,
                    "resource_key": cache_key,
                    "source_identifier": f"publication:{start}:{end}",
                    "source_subject_kind": "aggregate",
                    "listing": payload,
                    "dimensions": {
                        "kind": "publication_window",
                        "cache_key": cache_key,
                    },
                    "source_metadata": {
                        "requested_start": start,
                        "requested_end": end,
                        "config": config,
                        "retrieved_at": timezone.now().isoformat(),
                        "provider_limits": payload.get("coverage"),
                        "dataset_revision": payload.get("revision"),
                    },
                },
            )

        checkpoint_scope(
            claim,
            scope_kind="publication_window",
            scope_key=cache_key,
            ownership={"source": parent.source_id, "cohort_hash": scope["cohort_hash"]},
            enumeration_complete=True,
            outcome="observed",
            write=write,
        )
        finish_run(
            claim,
            status="success",
            request_count=before - budget.remaining,
            selected_count=1,
            success_count=1,
        )
    except (ValueError, TypeError, KeyError) as exc:
        finish_run(
            claim,
            status="partial",
            request_count=before - budget.remaining,
            report={
                "stop_reason": str(exc)
                if isinstance(exc, SourceError)
                else "invalid_publication"
            },
        )
        raise
    finally:
        budget.remaining = parent_remaining - (before - budget.remaining)
    return CollectionObservation.objects.get(
        run_id=claim.run_id, observation_key=cache_key
    )


def _admit_publication(claim, job, publication, start, end):
    contract_id = job.definition["scope"].get("numeric_contract_id")
    if not contract_id:
        return
    identifiers = set(
        SourceSubjectMapping.objects.filter(
            contract_id=contract_id, purpose="metric", source_id=job.source_id
        ).values_list("external_identifier", flat=True)
    )
    payload = copy.deepcopy(publication.listing)
    field = "model_permaslug" if job.source_id == "openrouter" else "model_name"
    payload["rows"] = [
        r for r in payload["rows"] if r[field] in identifiers and r[field] != "other"
    ]
    if not payload["rows"]:
        return
    dataset = (
        "openrouter/rankings-daily"
        if job.source_id == "openrouter"
        else "lmarena-ai/leaderboard-dataset"
    )
    publisher = "openrouter" if job.source_id == "openrouter" else "lmarena-ai"
    snap = {
        "date": end,
        "immutable_revision": digest(publication.listing),
        "file_path": "selected-publication.json",
        "raw_artifact_sha256": digest(payload),
        "payload": payload,
        "upstream_retrieval_coordinates": publication.source_metadata,
    }
    import_selected_history(
        claim,
        {
            "schema_version": 1,
            "contract_id": contract_id,
            "source": job.source_id,
            "dataset_id": dataset,
            "archive_publisher": publisher,
            "artifact_kind": "selected_json",
            "start_date": start,
            "end_date": end,
            "snapshots": [snap],
        },
    )


def _publication_evidence(claim, job, model, pins, budget, *, key):
    scope = job.definition["scope"]
    config = scope.get("arena_config")
    if job.source_id == "arena" and config not in {"text", "text_style_control"}:
        return [], {
            "outcome": "history_unavailable",
            "reason": "unreviewed_arena_configuration",
        }
    start_at = scope.get("global_start_at") or model["creation"]["at"]
    size = (
        min(365, max(1, job.definition["budgets"]["items"] // 51))
        if job.source_id == "openrouter"
        else 330
    )
    windows, _ = history_windows(start_at, scope["cutoff"], job.source_id, size=size)
    evidence = []
    identifiers = {
        p["native_identifier"]
        for p in pins
        if p["identifier_scope"] in {"rankings_permaslug", "arena_model_name"}
    }
    if not identifiers:
        return [], {
            "outcome": "unmapped",
            "reason": "reviewed_usage_or_score_identifier_missing",
        }
    for start, end in windows:
        publication = _publication_window(
            job, budget, start, end, key=key, config=config
        )
        payload = publication.listing
        _admit_publication(claim, job, publication, start, end)
        field = "model_permaslug" if job.source_id == "openrouter" else "model_name"
        rows = [
            r
            for r in payload["rows"]
            if r[field] in identifiers and r[field] != "other"
        ]
        evidence.append(
            {
                "observation_id": publication.pk,
                "run_id": str(publication.run_id),
                "requested_start_date": start,
                "requested_end_date": end,
                "matched_rows": rows,
                "provider_coverage": payload.get("coverage"),
                "missing_dates": payload.get("missing_dates", []),
                "other_assigned_to_model": False,
                "scope": payload.get("config"),
            }
        )
    return evidence, {
        "outcome": "observed"
        if any(e["matched_rows"] for e in evidence)
        else "history_unavailable",
        "reason": "native_publications"
        if any(e["matched_rows"] for e in evidence)
        else "not_in_provider_publications",
    }
