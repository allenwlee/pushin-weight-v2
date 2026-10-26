"""Shared provider publication windows and selected-model evidence.

Numeric admission remains the reviewed history importer's responsibility. Missing
source evidence creates a coverage outcome, never a zero-valued metric row.
"""

from __future__ import annotations

import copy
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from core.benchmark_metric_identity import SOURCE_STATISTICS_POLICY
from core.benchmark_metric_store import calendar_window, native_date
from core.collection_jobs import register_job, set_job_state
from core.collection_state import (
    checkpoint_scope,
    claim_job,
    finish_run,
)
from core.measurement_taxonomy import digest, require
from core.model_history_archives import import_selected_history
from core.model_history_cohort import history_windows
from core.model_history_statistics import history_statistics_contract
from core.models import (
    CollectionJob,
    CollectionObservation,
    CollectionObservationInput,
    CollectionScopeRun,
    DataSource,
    MetricValue,
    SourceSubjectMapping,
)
from scripts.benchmark_download_collector.sources import (
    SourceError,
    arena,
    openrouter,
)


def _window_key(
    source,
    cohort_hash,
    start,
    end,
    config,
    *,
    window_policy=None,
    acquisition_generation=None,
    arena_publication_mode=None,
):
    identity = {
        "source": source,
        "cohort_hash": cohort_hash,
        "start": start,
        "end": end,
        "config": config,
    }
    if window_policy:
        identity["window_policy"] = window_policy
    if acquisition_generation:
        identity["acquisition_generation"] = acquisition_generation
    if arena_publication_mode:
        identity["arena_publication_mode"] = arena_publication_mode
    return digest(identity)


def _arena_publication_mode(job):
    scope = job.scope
    if "arena_publication_mode" not in scope:
        return None
    mode = scope["arena_publication_mode"]
    contract = history_statistics_contract(job)
    require(
        mode == "latest-artifact-v1"
        and job.source_id == "arena"
        and scope.get("numeric_projection_policy") == SOURCE_STATISTICS_POLICY
        and contract is not None
        and contract.source_configuration["arena"].get("eligibility_policy")
        == SOURCE_STATISTICS_POLICY,
        "unsupported Arena publication mode",
    )
    return mode


def _publication_window(parent, budget, start, end, *, key, config):
    """A shared instruction serializes acquisition; DB evidence survives temp-file loss."""
    scope = parent.scope
    acquisition_mode = _arena_publication_mode(parent)
    contract = history_statistics_contract(parent)
    statistics = bool(
        contract
        and contract.source_configuration[parent.source_id].get("eligibility_policy")
        == SOURCE_STATISTICS_POLICY
    )
    if statistics:
        from core.benchmark_attribution import enforce_source_collection

        enforce_source_collection(
            contract,
            parent.source_id,
            dataset=contract.source_configuration[parent.source_id][
                "publication_provenance"
            ]["dataset_id"],
        )
    cache_key = _window_key(
        parent.source_id,
        scope["cohort_hash"],
        start,
        end,
        config,
        window_policy="source-statistics-exact-window-v1" if statistics else None,
        acquisition_generation=scope.get("acquisition_generation")
        if scope.get("publication_window_policy") == "rolling-completed-days-v1"
        else None,
        arena_publication_mode=acquisition_mode,
    )
    cached = (
        CollectionObservation.objects.filter(
            run__job__source_id=parent.source_id,
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
        "budgets": parent.budgets,
    }
    if statistics:
        definition["scope"]["window_policy"] = "source-statistics-exact-window-v1"
        definition["scope"]["carry_in_days"] = 0
    if acquisition_mode:
        definition["scope"]["arena_publication_mode"] = acquisition_mode
    if scope.get("publication_window_policy") == "rolling-completed-days-v1":
        definition["scope"]["acquisition_generation"] = scope["acquisition_generation"]
    if parent.campaign_settings:
        definition["campaign"] = {
            **parent.campaign_settings,
            "role": "history",
            "phase": "acquire",
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
            shared.scope == definition["scope"],
            "shared publication identity changed",
        )
    if shared.state == "paused":
        set_job_state(shared.pk, "ready")
    claim = claim_job(shared.pk)
    parent_remaining = budget.remaining
    budget.remaining = min(budget.remaining, shared.budgets["requests"])
    before = budget.remaining
    try:
        from core.collection_capture import capture_budget

        with capture_budget(
            claim, budget, scope_kind="publication_window", scope_key=cache_key,
            ownership={"source": parent.source_id, "cohort_hash": scope["cohort_hash"]},
            requested_start_date=native_date(start), requested_end_date=native_date(end),
        ):
            payload = (
                openrouter(budget, start, end, key=key)
                if parent.source_id == "openrouter"
                else arena(
                    budget,
                    start,
                    end,
                    history=acquisition_mode != "latest-artifact-v1",
                    config=config,
                    carry_in_days=0 if statistics else 30,
                )
            )
        require(
            budget.total_bytes_read <= budget.max_bytes, "global byte budget exceeded"
        )
        require(
            len(payload["rows"]) <= shared.budgets["items"],
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
                        **(
                            {"arena_publication_mode": acquisition_mode}
                            if acquisition_mode
                            else {}
                        ),
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
            report={"physical_accounting_complete": True},
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
    contract = history_statistics_contract(job)
    if (
        contract
        and contract.source_configuration[job.source_id].get("eligibility_policy")
        == SOURCE_STATISTICS_POLICY
    ):
        return _queue_publication(claim, job, publication, contract, start, end)
    contract_id = job.scope.get("numeric_contract_id")
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


def _queue_publication(claim, job, publication, contract, start, end):
    """Commit selected native rows and their pending projection together."""
    from core.source_metric_projection import enqueue_projection

    selection_key = digest([publication.pk, contract.contract_hash])
    if CollectionScopeRun.objects.filter(
        run_id=claim.run_id,
        scope_kind="publication_selection",
        scope_key=selection_key,
        enumeration_complete=True,
    ).exists():
        return []
    source = job.source_id
    settings = contract.source_configuration[source]
    births = {
        pin["native_identifier"]: model["creation"]["at"][:10]
        for model in job.scope.get("models", [])
        for pin in model.get("provider_pins", [])
        if pin["source"] == source
    }
    field = "model_permaslug" if source == "openrouter" else "model_name"
    identifiers = set(
        contract.mappings.filter(source_id=source).values_list(
            "external_identifier", flat=True
        )
    )
    rows = [
        row
        for row in publication.listing["rows"]
        if row[field] == "other"
        or row[field] in identifiers
        and (row["date"] if source == "openrouter" else row["leaderboard_publish_date"])
        >= births.get(row[field], "0001-01-01")
    ]
    # Explicit native-only scopes may select identifiers separately, never infer
    # rankings identities from catalog IDs/canonical_slug.
    native_ids = set(job.scope.get("native_publication_identifiers", []))
    rows += [
        row
        for row in publication.listing["rows"]
        if row[field] in native_ids
        and row[field] not in identifiers
        and row[field] != "other"
    ]
    rows = [
        row
        for row in rows
        if start
        <= (row["date"] if source == "openrouter" else row["leaderboard_publish_date"])
        <= end
    ]
    selected_ids = []

    def write(run, scoped):
        for raw in rows:
            period = (
                raw["date"]
                if source == "openrouter"
                else raw["leaderboard_publish_date"]
            )
            revision = publication.listing.get("revision") or publication.listing.get(
                "artifact_sha256"
            )
            if not revision:
                revision = digest(raw)
            snapshot = {
                "dataset_id": settings["publication_provenance"]["dataset_id"],
                "native_identifier": raw[field],
                "period": period,
                "config": publication.listing.get("config"),
                "category": raw.get("category"),
                "revision": revision,
            }
            key = digest(["publication-evidence", contract.contract_hash, snapshot])
            payload = {
                **{
                    k: copy.deepcopy(v)
                    for k, v in publication.listing.items()
                    if k != "rows"
                },
                "rows": [copy.deepcopy(raw)],
            }
            evidence, _created = CollectionObservation.objects.get_or_create(
                run=run,
                observation_key=key,
                defaults={
                    "scope_run": scoped,
                    "resource_key": key,
                    "source_identifier": raw[field],
                    "source_subject_kind": "aggregate"
                    if raw[field] == "other"
                    else "model",
                    "observed_at": publication.observed_at,
                    "published_date": period if source == "arena" else None,
                    "publication_precision": "date" if source == "arena" else "unknown",
                    "listing": payload,
                    "dimensions": {
                        "kind": "publication_row",
                        "config": payload.get("config"),
                        "period": period,
                    },
                    "source_metadata": {
                        "publication_provenance": settings["publication_provenance"],
                        "numeric_snapshot_identity": snapshot,
                        "origin_publication_observation_id": publication.pk,
                        "origin_publication_run_id": str(publication.run_id),
                        "clocks": {"publication_date": period}
                        if source == "arena"
                        else {"period_label_date": period},
                    },
                },
            )
            require(
                evidence.listing["rows"] == payload["rows"],
                "immutable selected publication conflict",
            )
            require(
                publication.run.job.source_id == source,
                "selected publication belongs to another measurement source",
            )
            edge, _ = CollectionObservationInput.objects.get_or_create(
                observation=evidence, input_observation=publication,
                input_role="publication_row_origin",
                defaults={"input_sha256": publication.observation_key},
            )
            require(
                edge.input_sha256 == publication.observation_key,
                "selected publication origin evidence changed",
            )
            selected_ids.append(evidence.pk)
        if selected_ids:
            enqueue_projection(claim, contract=contract, evidence_ids=selected_ids)

    checkpoint_scope(
        claim,
        scope_kind="publication_selection",
        scope_key=selection_key,
        ownership={
            "publication_observation_id": publication.pk,
            "contract_hash": contract.contract_hash,
        },
        resource_observation=publication,
        projection_contract=contract,
        enumeration_complete=True,
        outcome="observed",
        write=write,
    )
    return selected_ids


def _publication_evidence(claim, job, model, pins, budget, *, key):
    scope = job.scope
    acquisition_mode = _arena_publication_mode(job)
    config = scope.get("arena_config")
    if job.source_id == "arena" and config not in {
        "text",
        "text_style_control",
        "agent",
    }:
        return [], {
            "outcome": "history_unavailable",
            "reason": "unreviewed_arena_configuration",
        }
    start_at = (
        scope.get("publication_start_at")
        or scope.get("global_start_at")
        or model["creation"]["at"]
    )
    size = (
        min(365, max(1, job.budgets["items"] // 51))
        if job.source_id == "openrouter"
        else 330
    )
    if scope.get("numeric_projection_policy") == SOURCE_STATISTICS_POLICY:
        window_days = scope.get("publication_window_days", 7)
        require(
            type(window_days) is int and 1 <= window_days <= 90,
            "bounded publication window required",
        )
        size = min(size, window_days)
    windows, _ = history_windows(start_at, scope["cutoff"], job.source_id, size=size)
    if acquisition_mode and windows:
        # Latest is one publication artifact, never daily historical acquisition.
        windows = [(windows[0][0], windows[-1][1])]
    evidence = []
    identifiers = {
        p["native_identifier"]
        for p in pins
        if p["identifier_scope"] in {"rankings_permaslug", "arena_model_name"}
    }
    identifiers.update(scope.get("native_publication_identifiers", []))
    if not identifiers:
        return [], {
            "outcome": "unmapped",
            "reason": "reviewed_usage_or_score_identifier_missing",
        }
    acquisition_windows = []
    for start, end in windows:
        if (
            job.source_id == "openrouter"
            and scope.get("numeric_projection_policy") == SOURCE_STATISTICS_POLICY
        ):
            reused, missing_windows = _reuse_openrouter_days(
                job, model, identifiers, start, end
            )
            evidence.extend(reused)
            acquisition_windows.extend(missing_windows)
        else:
            acquisition_windows.append((start, end))
    for start, end in acquisition_windows:
        publication = _publication_window(
            job, budget, start, end, key=key, config=config
        )
        payload = publication.listing
        _admit_publication(claim, job, publication, start, end)
        field = "model_permaslug" if job.source_id == "openrouter" else "model_name"
        rows = [
            r
            for r in payload["rows"]
            if r[field] in identifiers
            and r[field] != "other"
            and start
            <= (
                r["date"]
                if job.source_id == "openrouter"
                else r["leaderboard_publish_date"]
            )
            <= end
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
    missing = any(e.get("missing_dates") for e in evidence)
    coverage = {e.get("provider_coverage") for e in evidence}
    if missing or coverage & {
        "latest_publication_only",
        "partial",
        "partial_publication_window",
    }:
        return evidence, {
            "outcome": "not_published",
            "reason": "partial_provider_publication_coverage",
        }
    return evidence, {
        "outcome": "observed"
        if any(e["matched_rows"] for e in evidence)
        else "history_unavailable",
        "reason": "native_publications"
        if any(e["matched_rows"] for e in evidence)
        else "not_in_provider_publications",
    }


def _reuse_openrouter_days(job, model, identifiers, start, end):
    """Reuse proved complete native daily cells, preserving their original owners.

    A saved latest observation is a selection rule, not a claim that the provider
    cannot publish another revision. Routine rolling windows still recheck HTTP.
    """
    if job.scope.get("publication_window_policy"):
        return [], [(start, end)]
    contract = history_statistics_contract(job)
    definition = next(
        row
        for row in contract.source_configuration["openrouter"]["definitions"]
        if row["metric_key"] == "total_tokens"
    )
    start_date, end_date = native_date(start), native_date(end)
    values = (
        MetricValue.objects.filter(
            source_metric_id=definition["id"],
            observation__run__job__source_id="openrouter",
            observation__run__status__in=["success", "partial"],
            observation__status="ok",
            observation__source_identifier__in=identifiers,
            temporal_status="exact",
            period_label_date__range=(start_date, end_date),
        )
        .select_related("observation__run__job", "observation__mapping__subject")
        .defer("observation__run__job__definition")
        .order_by("-observation__observed_at", "-pk")
    )
    selected = {}
    for value in values[: job.budgets["items"]].iterator(chunk_size=100):
        observation = value.observation
        metadata = observation.source_metadata
        revision = metadata.get("immutable_revision") or metadata.get(
            "snapshot_identity", {}
        ).get("revision")
        if not revision:
            continue
        expected = calendar_window(value.period_label_date.isoformat(), "UTC")
        if (
            value.window_start_at,
            value.window_end_at,
        ) != expected or value.integer_value is None:
            continue
        if observation.mapping_id and str(
            observation.mapping.subject.product_id
        ) != model.get("product_key"):
            continue
        selected.setdefault(
            (value.period_label_date, observation.source_identifier), value
        )
    reused, missing = [], []
    day = start_date
    while day <= end_date:
        daily = [selected.get((day, identifier)) for identifier in sorted(identifiers)]
        if not daily or any(value is None for value in daily):
            missing.append(day)
        else:
            for value in daily:
                observation = value.observation
                reused.append(
                    {
                        "observation_id": observation.pk,
                        "run_id": str(observation.run_id),
                        "contract_id": str(observation.run.job.contract_id),
                        "value_id": value.pk,
                        "source_metric_id": value.source_metric_id,
                        "original_observed_at": observation.observed_at.isoformat(),
                        "source_metadata": observation.source_metadata,
                        "mapping_id": str(observation.mapping_id)
                        if observation.mapping_id
                        else None,
                        "native_only": observation.mapping_id is None,
                        "selection_rule": "latest_saved_observation",
                        "numeric_reused": True,
                        "requested_start_date": day.isoformat(),
                        "requested_end_date": day.isoformat(),
                        "provider_coverage": "persisted_completed_day",
                        "matched_rows": [
                            {
                                "date": day.isoformat(),
                                "model_permaslug": observation.source_identifier,
                                "total_tokens": str(value.integer_value),
                            }
                        ],
                    }
                )
        day += timedelta(days=1)
    windows = []
    for day in missing:
        if windows and native_date(windows[-1][1]) + timedelta(days=1) == day:
            windows[-1] = (windows[-1][0], day.isoformat())
        else:
            windows.append((day.isoformat(), day.isoformat()))
    return reused, windows
