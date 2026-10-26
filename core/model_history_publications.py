"""Shared provider publication windows and selected-model evidence.

Numeric admission remains the reviewed history importer's responsibility. Missing
source evidence creates a coverage outcome, never a zero-valued metric row.
"""

from __future__ import annotations

import copy
import json
from contextlib import contextmanager
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from core.benchmark_metric_identity import SOURCE_STATISTICS_POLICY
from core.benchmark_metric_store import calendar_window, native_date
from core.collection_capture import observation_object_documents
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

WINDOW_CAPTURE = "publication-window-v1"
ROW_CAPTURE = "publication-row-v1"
SCOPE_PHASE = "typed-publication-v1"
DATASETS = {
    "openrouter": "openrouter/rankings-daily",
    "arena": "lmarena-ai/leaderboard-dataset",
}


def _shared_key(job):
    scope = job.scope
    return _window_key(
        job.source_id,
        scope["cohort_hash"],
        scope["start_date"],
        scope["end_date"],
        scope["config"],
        window_policy=scope.get("window_policy"),
        acquisition_generation=scope.get("acquisition_generation"),
        arena_publication_mode=scope.get("arena_publication_mode"),
    )


def validate_typed_scope(job, run, kind, key, ownership, contract, observation):
    require(
        job.purpose == "catalog"
        and job.operation == "model_history"
        and job.source_id in DATASETS
        and run.job_id == job.pk,
        "publication history owner required",
    )
    current = run.scopes.filter(scope_kind=kind, scope_key=key).first()
    require(
        current is None or current.phase == SCOPE_PHASE,
        "historical publication scope requires typed adoption",
    )
    if kind == "publication_window":
        frozen = job.scope
        require(
            frozen.get("role") == kind
            and contract is None
            and observation is None
            and ownership
            == {"source": job.source_id, "cohort_hash": frozen["cohort_hash"]}
            and key == _shared_key(job)
            and native_date(frozen["start_date"]) <= native_date(frozen["end_date"]),
            "shared publication window differs from sealed selection",
        )
    else:
        require(
            kind == "publication_selection"
            and contract is not None
            and str(contract.pk) == job.scope.get("numeric_contract_id")
            and observation is not None
            and observation.observation_kind == "publication_window"
            and observation.projection_kind == WINDOW_CAPTURE
            and observation.run.job.source_id == job.source_id
            and observation.source_dataset_id is not None
            and observation.source_dataset.source_id == job.source_id
            and observation.source_dataset.code
            == contract.source_configuration[job.source_id]["publication_provenance"][
                "dataset_id"
            ]
            and ownership
            == {
                "publication_observation_id": observation.pk,
                "contract_hash": contract.contract_hash,
            }
            and key == digest([observation.pk, contract.contract_hash]),
            "selected publication differs from frozen source and contract",
        )


def _checkpoint(claim, *, write=None, **kwargs):
    def save(run, scope):
        scope.phase = SCOPE_PHASE
        fields = ["phase"]
        if scope.scope_kind == "publication_window":
            for field, key in (
                ("requested_start_date", "start_date"),
                ("requested_end_date", "end_date"),
            ):
                expected = native_date(run.job.scope[key])
                require(
                    getattr(scope, field) in (None, expected),
                    "publication request bounds changed",
                )
                setattr(scope, field, expected)
                fields.append(field)
        scope.save(update_fields=fields)
        if write is not None:
            write(run, scope)

    return checkpoint_scope(claim, typed=True, write=save, **kwargs)


@contextmanager
def _capture_window(claim, budget, *, scope_key, ownership):
    from core.collection_capture import RequestCapture

    scope = _checkpoint(
        claim, scope_kind="publication_window", scope_key=scope_key, ownership=ownership
    )
    previous = budget.capture, budget.collection_scope
    budget.capture, budget.collection_scope = RequestCapture(claim), scope
    try:
        yield scope
    finally:
        budget.capture, budget.collection_scope = previous


def _complete_publication(payload):
    return not payload.get("missing_dates") and payload.get("coverage") not in {
        "latest_publication_only",
        "partial",
        "partial_publication_window",
    }


def observation_documents(observation):
    """Read source artifacts through explicit typed window/selection owners."""
    from core.collection_capture import read_document

    scope, run = observation.scope_run, observation.run
    source = run.job.source_id
    require(
        source in DATASETS
        and run.job.purpose == "catalog"
        and run.job.operation == "model_history"
        and scope is not None
        and scope.run_id == run.pk
        and scope.phase == SCOPE_PHASE,
        "typed publication evidence owner changed",
    )
    if observation.projection_kind == WINDOW_CAPTURE:
        require(
            scope.scope_kind == "publication_window"
            and observation.observation_kind == "publication_window"
            and observation.source_subject_kind == "aggregate"
            and run.payload_archive_id is not None
            and scope.scope_key == observation.observation_key == _shared_key(run.job)
            and scope.requested_start_date == native_date(run.job.scope["start_date"])
            and scope.requested_end_date == native_date(run.job.scope["end_date"])
            and observation.config_key == run.job.scope["config"]
            and observation.source_dataset_id is not None
            and observation.source_dataset_id == run.source_dataset_id,
            "publication artifact identity changed",
        )
        require(
            observation.source_dataset.source_id == source
            and observation.source_dataset.code == DATASETS[source]
            and scope.source_dataset_id == observation.source_dataset_id,
            "publication measurement source changed",
        )
        payload = read_document(run.payload_archive)
        require(
            isinstance(payload, dict)
            and isinstance(payload.get("rows"), list)
            and digest(payload) == observation.payload_sha256 == run.payload_sha256
            and payload.get("coverage") == observation.processing_outcome
            and _complete_publication(payload) == observation.publication_complete,
            "publication artifact contents changed",
        )
        inputs = list(
            observation.inputs.filter(
                input_role="publication_source_response"
            ).select_related("input_request__attempt", "input_request__archive")
        )
        require(inputs, "publication artifact requires its physical source responses")
        for edge in inputs:
            request = edge.input_request
            require(
                request is not None
                and request.scope_run_id == scope.pk
                and request.attempt.run_id == run.pk
                and request.archive_id is not None
                and request.transport_outcome == "received"
                and request.http_status == 200
                and edge.input_sha256 == request.archive.content_sha256,
                "publication physical input changed",
            )
        return (
            payload,
            {"kind": "publication_window", "cache_key": observation.observation_key},
            {
                "requested_start": scope.requested_start_date.isoformat(),
                "requested_end": scope.requested_end_date.isoformat(),
                "config": observation.config_key,
                "retrieved_at": observation.original_retrieved_at.isoformat()
                if observation.original_retrieved_at
                else None,
                "provider_limits": observation.processing_outcome,
                "dataset_revision": payload.get("revision"),
                **(
                    {"arena_publication_mode": run.job.scope["arena_publication_mode"]}
                    if run.job.scope.get("arena_publication_mode")
                    else {}
                ),
            },
        )
    require(
        observation.projection_kind == ROW_CAPTURE
        and observation.observation_kind == "publication_row"
        and scope.scope_kind == "publication_selection"
        and scope.projection_contract_id is not None,
        "typed publication row required",
    )
    links = list(
        observation.inputs.filter(input_role="publication_row_origin").select_related(
            "input_observation__run__job"
        )
    )
    require(len(links) == 1, "one publication row origin required")
    (edge,) = links
    origin = edge.input_observation
    require(
        origin is not None
        and origin.pk == scope.resource_observation_id
        and origin.run.job.source_id == source
        and origin.projection_kind == WINDOW_CAPTURE
        and edge.input_sha256 == origin.observation_key
        and observation.observed_at == origin.observed_at,
        "selected publication source changed",
    )
    listing, _, _ = observation_documents(origin)
    locator = edge.row_locator
    require(
        isinstance(locator, str)
        and locator.isascii()
        and locator.isdecimal()
        and str(int(locator)) == locator
        and int(locator) < len(listing["rows"]),
        "publication row position changed",
    )
    raw = listing["rows"][int(locator)]
    field = "model_permaslug" if source == "openrouter" else "model_name"
    period = raw["date"] if source == "openrouter" else raw["leaderboard_publish_date"]
    revision = listing.get("revision") or listing.get("artifact_sha256") or digest(raw)
    payload = {**{k: v for k, v in listing.items() if k != "rows"}, "rows": [raw]}
    settings = scope.projection_contract.source_configuration[source]
    require(
        raw[field] == observation.source_identifier
        and observation.source_subject_kind
        == ("aggregate" if raw[field] == "other" else "model")
        and native_date(period) == observation.source_record_date
        and scope.requested_start_date is not None
        and scope.requested_end_date is not None
        and scope.requested_start_date
        <= native_date(period)
        <= scope.requested_end_date
        and listing.get("config") == observation.config_key
        and raw.get("category") == observation.category_key
        and revision == observation.provider_revision
        and digest(payload) == observation.payload_sha256
        and observation.source_dataset_id is not None
        and observation.source_dataset.source_id == source
        and observation.source_dataset.code
        == settings["publication_provenance"]["dataset_id"],
        "selected publication coordinates changed",
    )
    snapshot = {
        "dataset_id": observation.source_dataset.code,
        "native_identifier": observation.source_identifier,
        "period": period,
        "config": observation.config_key,
        "category": observation.category_key,
        "revision": observation.provider_revision,
    }
    require(
        observation.observation_key
        == digest(
            ["publication-evidence", scope.projection_contract.contract_hash, snapshot]
        ),
        "selected publication identity changed",
    )
    return (
        payload,
        {"kind": "publication_row", "config": observation.config_key, "period": period},
        {
            "publication_provenance": settings["publication_provenance"],
            "numeric_snapshot_identity": snapshot,
            "origin_publication_observation_id": origin.pk,
            "origin_publication_run_id": str(origin.run_id),
            "clocks": {
                "publication_date" if source == "arena" else "period_label_date": period
            },
        },
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
            observation_kind="publication_window",
            observation_key=cache_key,
        )
        .order_by("pk")
        .first()
    )
    if cached:
        require(
            cached.projection_kind == WINDOW_CAPTURE,
            "historical publication artifact requires typed adoption",
        )
        observation_documents(cached)
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
    claim = claim_job(shared.pk, typed=True)
    prior_requests = (
        shared.runs.only("request_count").get(pk=claim.run_id).request_count
    )
    parent_remaining = budget.remaining
    budget.remaining = min(budget.remaining, shared.budgets["requests"])
    before = budget.remaining
    try:
        with _capture_window(
            claim,
            budget,
            scope_key=cache_key,
            ownership={"source": parent.source_id, "cohort_hash": scope["cohort_hash"]},
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
            from core.collection_capture import archive_document, link_request
            from core.collection_datasets import resolve_dataset
            from core.collection_resources import project_observation_facts

            requests = list(
                scoped.requests.filter(
                    attempt_id=claim.attempt_id,
                    transport_outcome="received",
                    http_status=200,
                    archive__isnull=False,
                )
                .select_related("archive")
                .order_by("ordinal")
            )
            require(
                requests, "publication artifact requires its physical source responses"
            )
            archive = archive_document(
                json.dumps(
                    payload, sort_keys=True, separators=(",", ":"), allow_nan=False
                ).encode(),
                encoding="selected-json-canonical-v1",
                capture_kind="selected_payload",
            )
            dataset = resolve_dataset(
                parent.source_id, {"dataset_id": DATASETS[parent.source_id]}
            )
            retrieved_at = timezone.now()
            require(
                run.payload_archive_id in (None, archive.pk),
                "publication payload already committed",
            )
            run.payload_archive, run.payload_sha256 = archive, digest(payload)
            run.source_dataset, run.observed_at = dataset, retrieved_at
            run.save(
                update_fields=[
                    "payload_archive",
                    "payload_sha256",
                    "source_dataset",
                    "observed_at",
                ]
            )
            scoped.source_dataset = dataset
            scoped.save(update_fields=["source_dataset"])
            observation, created = CollectionObservation.objects.get_or_create(
                run=run,
                observation_key=cache_key,
                defaults={
                    "scope_run": scoped,
                    "resource_key": cache_key,
                    "source_identifier": f"publication:{start}:{end}",
                    "source_subject_kind": "aggregate",
                    "observation_kind": "publication_window",
                    "projection_kind": WINDOW_CAPTURE,
                    "source_dataset": dataset,
                    "config_key": config,
                    "provider_revision": payload.get("revision")
                    or payload.get("artifact_sha256"),
                    "payload_sha256": run.payload_sha256,
                    "observed_at": retrieved_at,
                    "original_retrieved_at": retrieved_at,
                    "processing_outcome": payload.get("coverage"),
                    "publication_complete": _complete_publication(payload),
                },
            )
            require(created, "publication artifact already exists")
            for request in requests:
                link_request(observation, request, role="publication_source_response")
            observation_documents(observation)
            project_observation_facts(observation)

        _checkpoint(
            claim,
            scope_kind="publication_window",
            scope_key=cache_key,
            ownership={"source": parent.source_id, "cohort_hash": scope["cohort_hash"]},
            enumeration_complete=True,
            outcome="observed",
            raw_count=len(payload["rows"]),
            write=write,
        )
        finish_run(
            claim,
            status="success",
            request_count=prior_requests + before - budget.remaining,
            selected_count=1,
            success_count=1,
            typed=True,
            physical_accounting_complete=True,
        )
    except (ValueError, TypeError, KeyError) as exc:
        finish_run(
            claim,
            status="partial",
            request_count=prior_requests + before - budget.remaining,
            error_code=str(exc)
            if isinstance(exc, SourceError)
            else "invalid_publication",
            typed=True,
            physical_accounting_complete=False,
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
    listing, _, source_metadata = observation_object_documents(publication)
    payload = copy.deepcopy(listing)
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
        "immutable_revision": digest(listing),
        "file_path": "selected-publication.json",
        "raw_artifact_sha256": digest(payload),
        "payload": payload,
        "upstream_retrieval_coordinates": source_metadata,
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
    previous = CollectionScopeRun.objects.filter(
        run_id=claim.run_id,
        scope_kind="publication_selection",
        scope_key=selection_key,
    ).first()
    require(
        previous is None or previous.phase == SCOPE_PHASE,
        "historical publication selection requires typed adoption",
    )
    if previous and previous.enumeration_complete:
        require(
            previous.resource_observation_id == publication.pk
            and previous.projection_contract_id == contract.pk
            and previous.requested_start_date == native_date(start)
            and previous.requested_end_date == native_date(end),
            "completed publication selection changed",
        )
        return []
    source = job.source_id
    settings = contract.source_configuration[source]
    listing, _, _ = observation_object_documents(publication)
    positions = {id(row): str(position) for position, row in enumerate(listing["rows"])}
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
        for row in listing["rows"]
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
        for row in listing["rows"]
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
        from core.collection_resources import project_observation_facts

        scoped.requested_start_date, scoped.requested_end_date = (
            native_date(start),
            native_date(end),
        )
        scoped.save(update_fields=["requested_start_date", "requested_end_date"])
        for raw in rows:
            period = (
                raw["date"]
                if source == "openrouter"
                else raw["leaderboard_publish_date"]
            )
            revision = listing.get("revision") or listing.get("artifact_sha256")
            if not revision:
                revision = digest(raw)
            snapshot = {
                "dataset_id": settings["publication_provenance"]["dataset_id"],
                "native_identifier": raw[field],
                "period": period,
                "config": listing.get("config"),
                "category": raw.get("category"),
                "revision": revision,
            }
            key = digest(["publication-evidence", contract.contract_hash, snapshot])
            payload = {
                **{k: copy.deepcopy(v) for k, v in listing.items() if k != "rows"},
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
                    "observation_kind": "publication_row",
                    "projection_kind": ROW_CAPTURE,
                    "source_dataset": publication.source_dataset,
                    "config_key": payload.get("config"),
                    "category_key": raw.get("category"),
                    "provider_revision": revision,
                    "source_record_date": native_date(period),
                    "payload_sha256": digest(payload),
                },
            )
            require(
                publication.run.job.source_id == source,
                "selected publication belongs to another measurement source",
            )
            edge, _ = CollectionObservationInput.objects.get_or_create(
                observation=evidence,
                input_observation=publication,
                input_role="publication_row_origin",
                defaults={
                    "input_sha256": publication.observation_key,
                    "row_locator": positions[id(raw)],
                },
            )
            require(
                edge.input_sha256 == publication.observation_key
                and edge.row_locator == positions[id(raw)],
                "selected publication origin evidence changed",
            )
            require(
                observation_documents(evidence)[0]["rows"] == payload["rows"],
                "immutable selected publication conflict",
            )
            project_observation_facts(evidence)
            selected_ids.append(evidence.pk)
        if selected_ids:
            enqueue_projection(claim, contract=contract, evidence_ids=selected_ids)

    _checkpoint(
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
        raw_count=len(rows),
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
        payload, _, _ = observation_object_documents(publication)
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
        if not observation.provider_revision:
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
                        "source_metadata": {
                            "immutable_revision": observation.provider_revision
                        },
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
