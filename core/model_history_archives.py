"""Sparse historical archive admission and immutable retrieval provenance.

Numeric admission remains the reviewed history importer's responsibility. Missing
source evidence creates a coverage outcome, never a zero-valued metric row.
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime

from core.benchmark_metric_history import import_history, prepare_history
from core.benchmark_metric_identity import SOURCE_STATISTICS_POLICY
from core.benchmark_metric_store import aware_instant, native_date
from core.collection_state import (
    checkpoint_scope,
    fenced_run,
)
from core.measurement_taxonomy import digest, require
from core.model_history_cohort import validate_model_pins
from core.model_history_statistics import history_statistics_contract
from core.models import (
    CollectionObservation,
    CollectionObservationInput,
    CollectionScopeRun,
)


def import_selected_history(claim, manifest):
    """Admit a hashed sparse archive and checkpoint its provenance atomically."""
    manifest = copy.deepcopy(manifest)
    with fenced_run(claim) as (job, run):
        scope = job.scope
        validate_model_pins(job)
        require(
            job.operation == "model_history" and job.source_id == manifest["source"],
            "history source mismatch",
        )
        require(
            scope.get("numeric_contract_id") == manifest["contract_id"],
            "reviewed numeric contract pin required",
        )
        contract, _, _, _, _ = prepare_history(manifest)
        cutoff = aware_instant(scope["cutoff"]).astimezone(UTC).date()
        earliest = min(
            aware_instant(m["creation"]["at"]).astimezone(UTC).date()
            for m in scope["models"]
        )
        require(
            all(
                earliest <= datetime.fromisoformat(s["date"]).date() < cutoff
                for s in manifest["snapshots"]
            ),
            "archive snapshot outside frozen campaign",
        )
        selected = {row["product_key"] for row in scope["models"]}
        mappings = list(
            contract.mappings.filter(
                purpose="metric", source_id=job.source_id
            ).select_related("subject")
        )
        require(
            mappings and {str(m.subject.product_id) for m in mappings} <= selected,
            "numeric contract contains a different cohort",
        )
        births = {
            row["product_key"]: aware_instant(row["creation"]["at"])
            .astimezone(UTC)
            .date()
            for row in scope["models"]
        }
        identifiers = {
            (
                m.external_identifier.casefold()
                if job.source_id == "hf"
                else m.external_identifier
            ): str(m.subject.product_id)
            for m in mappings
        }
        for snap in manifest["snapshots"]:
            for row in snap["payload"]["rows"]:
                field = (
                    "repo_id"
                    if job.source_id == "hf"
                    else "model_permaslug"
                    if job.source_id == "openrouter"
                    else "model_name"
                )
                identifier = (
                    row[field].casefold() if job.source_id == "hf" else row[field]
                )
                require(
                    identifier in identifiers or identifier == "other",
                    "numeric archive includes an unselected model",
                )
                day = datetime.fromisoformat(
                    snap["date"]
                    if job.source_id == "hf"
                    else row["date"]
                    if job.source_id == "openrouter"
                    else row["leaderboard_publish_date"]
                ).date()
                if identifier in identifiers:
                    require(
                        births[identifiers[identifier]] <= day < cutoff,
                        "numeric row outside frozen model interval",
                    )
        imported = import_history(manifest, apply=True)
        require(
            imported.status in {"success", "partial"},
            "historical numeric admission failed",
        )
        key = digest(manifest)

        def retain_result(owner_run, scope):
            require(
                owner_run.pk == run.pk
                and scope.scope_kind == "archive_import"
                and imported.job.source_id == owner_run.job.source_id
                and imported.job.purpose == "metric"
                and imported.job.contract_id == contract.pk
                and scope.result_run_id in (None, imported.pk),
                "archive import result owner changed",
            )
            scope.result_run = imported
            scope.phase = "typed-archive-import-v1"

        checkpoint_scope(
            claim,
            scope_kind="archive_import",
            scope_key=key,
            ownership={
                "dataset_id": manifest["dataset_id"],
                "contract_id": str(contract.pk),
            },
            enumeration_complete=True,
            outcome="observed",
            typed=True,
            write=retain_result,
        )
        return imported


SNAPSHOT_CAPTURE = "hf-archive-snapshot-v1"
ROW_CAPTURE = "hf-archive-row-v1"
SCOPE_PHASE = "typed-hf-archive-v1"
DATASET = "cfahlgren1/hub-stats"


def _snapshot_key(job, revision):
    return digest(
        {
            "archive": DATASET,
            "revision": revision,
            "cohort_hash": job.scope["cohort_hash"],
        }
    )


def _revision(job, key):
    archive = job.scope.get("hf_archive", {})
    require(
        archive.get("dataset_id") == DATASET
        and archive.get("archive_publisher") == "cfahlgren1",
        "unsupported reviewed archive layout",
    )
    revisions = archive.get("revisions", [])
    require(
        isinstance(revisions, list) and len(revisions) <= job.budgets["items"],
        "archive revision cap",
    )
    matches = [
        revision for revision in revisions if _snapshot_key(job, revision) == key
    ]
    require(len(matches) == 1, "archive snapshot differs from frozen revision")
    revision = matches[0]
    day = native_date(revision["snapshot_date"])
    require(
        aware_instant(job.scope["global_start_at"]).date()
        <= day
        < aware_instant(job.scope["cutoff"]).date(),
        "archive date outside frozen campaign",
    )
    return revision


def validate_typed_scope(job, run, kind, key, ownership, contract, observation):
    require(
        job.purpose == "catalog"
        and job.operation == "model_history"
        and job.source_id == "hf"
        and run.job_id == job.pk,
        "HF archive history owner required",
    )
    current = run.scopes.filter(scope_kind=kind, scope_key=key).first()
    require(
        current is None or current.phase == SCOPE_PHASE,
        "historical HF archive scope requires typed adoption",
    )
    if kind == "archive_snapshot":
        revision = _revision(job, key)
        require(
            contract is None
            and observation is None
            and ownership
            == {"dataset_id": DATASET, "cohort_hash": job.scope["cohort_hash"]},
            "archive snapshot ownership changed",
        )
    else:
        require(
            kind == "archive_projection"
            and contract is not None
            and observation is not None
            and observation.run_id == run.pk
            and observation.projection_kind == SNAPSHOT_CAPTURE
            and str(contract.pk) == job.scope.get("numeric_contract_id")
            and contract.source_configuration["hf"].get("eligibility_policy")
            == SOURCE_STATISTICS_POLICY
            and ownership
            == {"dataset_id": DATASET, "contract_hash": contract.contract_hash},
            "archive projection ownership changed",
        )
        snapshot = observation_documents(observation)[0]
        require(
            key
            == digest(
                [
                    DATASET,
                    snapshot["immutable_revision"],
                    snapshot["date"],
                    contract.contract_hash,
                ]
            ),
            "archive projection identity changed",
        )
        revision = _revision(job, observation.observation_key)
    if current is not None:
        day = native_date(revision["snapshot_date"])
        require(
            current.requested_revision == revision["id"]
            and current.resource_path == "models.parquet"
            and current.requested_start_date == current.requested_end_date == day,
            "archive request coordinates changed",
        )


def _checkpoint(claim, job, revision, *, write=None, **kwargs):
    def save(run, scope):
        scope.phase = SCOPE_PHASE
        scope.requested_revision = revision["id"]
        scope.resource_path = "models.parquet"
        scope.save(update_fields=["phase", "requested_revision", "resource_path"])
        if write is not None:
            write(run, scope)

    day = native_date(revision["snapshot_date"])
    return checkpoint_scope(
        claim,
        typed=True,
        write=save,
        requested_start_date=day,
        requested_end_date=day,
        **kwargs,
    )


def observation_documents(observation):
    """Inspect one immutable selected archive or its exact ordered native row."""
    from core.collection_capture import read_document

    run, scope = observation.run, observation.scope_run
    require(
        run.job.operation == "model_history"
        and run.job.source_id == "hf"
        and run.job.purpose == "catalog"
        and scope is not None
        and scope.run_id == run.pk
        and scope.phase == SCOPE_PHASE
        and observation.source_dataset_id is not None
        and observation.source_dataset.source_id == "hf"
        and observation.source_dataset.code == DATASET
        and scope.source_dataset_id == observation.source_dataset_id
        and observation.secondary_source is True,
        "HF archive evidence owner changed",
    )
    if observation.projection_kind == SNAPSHOT_CAPTURE:
        revision = _revision(run.job, observation.observation_key)
        require(
            scope.scope_kind == "archive_snapshot"
            and scope.scope_key == observation.observation_key
            and scope.resource_observation_id == observation.pk
            and observation.observation_kind == "archive_snapshot"
            and observation.source_subject_kind == "aggregate"
            and observation.source_identifier == DATASET
            and observation.legacy_archive_id is not None
            and observation.legacy_archive.capture_kind == "hf_archive_snapshot",
            "HF archive snapshot identity changed",
        )
        snapshot = read_document(observation.legacy_archive)
        day = native_date(revision["snapshot_date"])
        require(
            digest(snapshot) == observation.payload_sha256
            and snapshot["immutable_revision"]
            == revision["id"]
            == observation.provider_revision
            and snapshot["file_path"] == scope.resource_path == "models.parquet"
            and snapshot["date"] == day.isoformat()
            and observation.archive_snapshot_date == day
            and scope.requested_start_date == scope.requested_end_date == day
            and scope.requested_revision == revision["id"]
            and snapshot["payload"].get("status") == "ok"
            and digest(snapshot["payload"]) == snapshot["raw_artifact_sha256"],
            "HF archive snapshot contents changed",
        )
        retrieval = snapshot["upstream_retrieval_coordinates"]
        require(
            retrieval["revision"] == revision["id"]
            and retrieval["file_path"] == snapshot["file_path"]
            and aware_instant(retrieval["retrieved_at"])
            == observation.observed_at
            == observation.original_retrieved_at,
            "HF archive retrieval coordinates changed",
        )
        return (
            snapshot,
            {"kind": "archive_snapshot"},
            {
                "secondary_source": True,
                "cohort_hash": run.job.scope["cohort_hash"],
                "dataset_id": DATASET,
                "archive_publisher": "cfahlgren1",
            },
        )
    require(
        observation.projection_kind == ROW_CAPTURE
        and scope.scope_kind == "archive_projection"
        and observation.observation_kind == "hf_archive_metadata"
        and observation.source_subject_kind == "repository",
        "HF archive row kind changed",
    )
    inputs = list(
        observation.inputs.filter(input_role="hf_archive_row").select_related(
            "input_observation"
        )
    )
    require(len(inputs) == 1, "HF archive row requires one selected origin")
    link = inputs[0]
    origin = link.input_observation
    require(
        origin is not None
        and origin.run_id == run.pk
        and origin.projection_kind == SNAPSHOT_CAPTURE
        and scope.resource_observation_id == origin.pk
        and link.input_sha256 == origin.payload_sha256,
        "HF archive row origin changed",
    )
    snapshot = observation_documents(origin)[0]
    position = link.row_locator
    require(
        isinstance(position, str)
        and position.isascii()
        and position.isdecimal()
        and str(int(position)) == position
        and int(position) < len(snapshot["payload"]["rows"]),
        "HF archive row position changed",
    )
    row = snapshot["payload"]["rows"][int(position)]
    identity = {
        "dataset_id": DATASET,
        "revision": snapshot["immutable_revision"],
        "date": snapshot["date"],
        "native_identifier": row["repo_id"],
    }
    payload = {"id": row["repo_id"], "private": False, **row["raw"]}
    require(
        observation.source_identifier == row["repo_id"]
        and observation.observation_key == digest(["hf-archive-native", identity])
        and observation.payload_sha256 == digest(payload)
        and observation.provider_revision
        == origin.provider_revision
        == scope.requested_revision
        and observation.archive_snapshot_date == origin.archive_snapshot_date
        and scope.requested_start_date
        == scope.requested_end_date
        == origin.archive_snapshot_date
        and observation.observed_at
        == observation.original_retrieved_at
        == origin.observed_at
        and scope.projection_contract_id is not None
        and str(scope.projection_contract_id)
        == run.job.scope.get("numeric_contract_id"),
        "HF archive selected row changed",
    )
    return (
        payload,
        {"kind": "hf_archive_metadata"},
        {
            "secondary_source": True,
            "dataset_id": DATASET,
            "archive_publisher": "cfahlgren1",
            "numeric_snapshot_identity": identity,
            "archive_snapshot_date": snapshot["date"],
            "original_retrieved_at": observation.original_retrieved_at.isoformat(),
            "clocks": {"archive_snapshot_date": snapshot["date"]},
            "metric_times": {
                metric: {"temporal_status": "date_only", "as_of_date": snapshot["date"]}
                for metric in ("likes", "trending_score")
            },
            "retrieval_coordinates": snapshot["upstream_retrieval_coordinates"],
        },
    )


def acquire_hf_archives(claim, job, budget):
    """Read reviewed immutable archive coordinates, persisting selected JSON first."""
    from scripts.benchmark_download_collector.hf_archive import (
        ArchiveBudget,
        select_snapshot,
    )

    scope = job.scope
    archive = scope.get("hf_archive")
    if not archive:
        return {
            "outcome": "history_unavailable",
            "reason": "no_reviewed_archive_coordinates",
        }
    with fenced_run(claim) as (_, owner_run):
        validate_model_pins(job)
        require(
            not owner_run.scopes.filter(
                scope_kind__in=["archive_snapshot", "archive_projection"],
            )
            .exclude(phase=SCOPE_PHASE)
            .exists(),
            "historical HF archive scope requires typed adoption",
        )
    require(
        archive.get("dataset_id") == "cfahlgren1/hub-stats"
        and archive.get("archive_publisher") == "cfahlgren1",
        "unsupported reviewed archive layout",
    )
    contract = history_statistics_contract(job)
    if (
        contract
        and contract.source_configuration["hf"].get("eligibility_policy")
        == SOURCE_STATISTICS_POLICY
    ):
        from core.benchmark_attribution import enforce_source_collection

        enforce_source_collection(contract, "hf", dataset=archive["dataset_id"])
    revisions = archive.get("revisions", [])
    require(
        isinstance(revisions, list) and len(revisions) <= job.budgets["items"],
        "archive revision cap",
    )
    selected = []
    for model in scope["models"]:
        identifiers = {
            p["native_identifier"]
            for p in model.get("provider_pins", [])
            if p["source"] == "hf"
        }
        if model["creation"].get("source") == "hf":
            identifiers.add(model["creation"]["native_identifier"])
        selected.extend({"identifier": identifier} for identifier in identifiers)
    require(selected, "archive cohort has no HF identifiers")
    snapshots = []
    for revision in revisions:
        day = datetime.fromisoformat(revision["snapshot_date"]).date()
        require(
            aware_instant(scope["global_start_at"]).date()
            <= day
            < aware_instant(scope["cutoff"]).date(),
            "archive date outside frozen campaign",
        )
        cache_key = digest(
            {
                "archive": archive["dataset_id"],
                "revision": revision,
                "cohort_hash": scope["cohort_hash"],
            }
        )
        with fenced_run(claim) as (_, owner_run):
            validate_typed_scope(
                job,
                owner_run,
                "archive_snapshot",
                cache_key,
                {"dataset_id": DATASET, "cohort_hash": scope["cohort_hash"]},
                None,
                None,
            )
        old = CollectionObservation.objects.filter(
            run_id=claim.run_id, observation_key=cache_key
        ).first()
        if old:
            require(
                old.projection_kind == SNAPSHOT_CAPTURE,
                "historical HF archive observation requires typed adoption",
            )
            snap = observation_documents(old)[0]
        else:
            _checkpoint(
                claim,
                job,
                revision,
                scope_kind="archive_snapshot",
                scope_key=cache_key,
                ownership={"dataset_id": DATASET, "cohort_hash": scope["cohort_hash"]},
            )
            budget.check()
            reader = ArchiveBudget(
                budget.client,
                requests=budget.remaining,
                max_bytes=budget.max_bytes - budget.total_bytes_read,
                seconds=budget.deadline - budget.clock(),
            )
            try:
                result = select_snapshot(reader, revision, selected)
            finally:
                budget.remaining -= reader.requests
                budget.total_bytes_read += reader.bytes
            payload = {
                "status": "ok",
                "rows": [
                    {
                        "repo_id": row["id"],
                        "status": "ok",
                        "raw": {k: v for k, v in row.items() if k != "id"},
                    }
                    for row in result["rows"]
                ],
            }
            snap = {
                "date": day.isoformat(),
                "immutable_revision": revision["id"],
                "file_path": result["file_path"],
                "raw_artifact_sha256": digest(payload),
                "payload": payload,
                "upstream_retrieval_coordinates": result,
            }
            if revision.get("upstream_binary_sha256"):
                snap["upstream_binary_sha256"] = revision["upstream_binary_sha256"]

            def write(
                run, scoped, snap=snap, cache_key=cache_key, day=day, revision=revision
            ):
                from core.collection_capture import archive_document
                from core.collection_datasets import resolve_dataset

                dataset = resolve_dataset("hf", archive)
                retrieved = aware_instant(
                    snap["upstream_retrieval_coordinates"]["retrieved_at"]
                )
                observation = CollectionObservation.objects.create(
                    run=run,
                    scope_run=scoped,
                    resource_key=cache_key,
                    observation_key=cache_key,
                    source_identifier=DATASET,
                    source_subject_kind="aggregate",
                    observation_kind="archive_snapshot",
                    projection_kind=SNAPSHOT_CAPTURE,
                    source_dataset=dataset,
                    legacy_archive=archive_document(
                        json.dumps(
                            snap,
                            sort_keys=True,
                            separators=(",", ":"),
                            ensure_ascii=False,
                            allow_nan=False,
                        ).encode(),
                        encoding="selected-json-canonical-v1",
                        capture_kind="hf_archive_snapshot",
                    ),
                    archive_snapshot_date=day,
                    provider_revision=revision["id"],
                    observed_at=retrieved,
                    original_retrieved_at=retrieved,
                    secondary_source=True,
                    payload_sha256=digest(snap),
                )
                scoped.resource_observation = observation

            _checkpoint(
                claim,
                job,
                revision,
                scope_kind="archive_snapshot",
                scope_key=cache_key,
                ownership={"dataset_id": DATASET, "cohort_hash": scope["cohort_hash"]},
                enumeration_complete=True,
                outcome="observed",
                write=write,
                raw_count=len(snap["payload"]["rows"])
                + result["identical_duplicates_collapsed"],
            )
            old = CollectionObservation.objects.get(
                run_id=claim.run_id, observation_key=cache_key
            )
            snap = observation_documents(old)[0]
        snapshots.append(snap)
        contract = history_statistics_contract(job)
        if (
            contract
            and contract.source_configuration["hf"].get("eligibility_policy")
            == SOURCE_STATISTICS_POLICY
        ):
            _queue_hf_archive(claim, job, contract, archive, snap, old)
        elif scope.get("numeric_contract_id") and snap["payload"]["rows"]:
            # A single snapshot is a bounded import chunk; sparse dates stay sparse.
            import_selected_history(
                claim,
                {
                    "schema_version": 1,
                    "contract_id": scope["numeric_contract_id"],
                    "source": "hf",
                    "dataset_id": archive["dataset_id"],
                    "archive_publisher": archive["archive_publisher"],
                    "artifact_kind": "selected_json",
                    "start_date": snap["date"],
                    "end_date": snap["date"],
                    "snapshots": [snap],
                },
            )
    return {
        "outcome": "observed",
        "snapshots": len(snapshots),
        "secondary_source": True,
        "daily_interpolation": False,
    }


def _queue_hf_archive(claim, job, contract, archive, snapshot, origin):
    from core.source_metric_projection import enqueue_projection

    key = digest(
        [
            archive["dataset_id"],
            snapshot["immutable_revision"],
            snapshot["date"],
            contract.contract_hash,
        ]
    )
    ownership = {"dataset_id": DATASET, "contract_hash": contract.contract_hash}
    with fenced_run(claim) as (_, run):
        validate_typed_scope(
            job, run, "archive_projection", key, ownership, contract, origin
        )
    # Capture and enqueue commit together; completed scopes never recreate work.
    if CollectionScopeRun.objects.filter(
        run_id=claim.run_id,
        scope_kind="archive_projection",
        scope_key=key,
        enumeration_complete=True,
    ).exists():
        return

    def write(run, scoped):
        ids = []
        for position, row in enumerate(snapshot["payload"]["rows"]):
            identifier = row["repo_id"]
            identity = {
                "dataset_id": DATASET,
                "revision": snapshot["immutable_revision"],
                "date": snapshot["date"],
                "native_identifier": identifier,
            }
            observation_key = digest(["hf-archive-native", identity])
            payload = {"id": identifier, "private": False, **row["raw"]}
            observation, created = CollectionObservation.objects.get_or_create(
                run=run,
                observation_key=observation_key,
                defaults={
                    "scope_run": scoped,
                    "resource_key": observation_key,
                    "source_identifier": identifier,
                    "source_subject_kind": "repository",
                    "observation_kind": "hf_archive_metadata",
                    "projection_kind": ROW_CAPTURE,
                    "secondary_source": True,
                    "source_dataset": origin.source_dataset,
                    "provider_revision": origin.provider_revision,
                    "archive_snapshot_date": origin.archive_snapshot_date,
                    "observed_at": origin.observed_at,
                    "original_retrieved_at": origin.observed_at,
                    "payload_sha256": digest(payload),
                },
            )
            require(
                created or observation.projection_kind == ROW_CAPTURE,
                "historical HF archive row requires typed adoption",
            )
            if created:
                CollectionObservationInput.objects.create(
                    observation=observation,
                    input_observation=origin,
                    input_role="hf_archive_row",
                    input_sha256=origin.payload_sha256,
                    row_locator=str(position),
                )
            require(
                observation_documents(observation)[0] == payload,
                "immutable HF archive conflict",
            )
            ids.append(observation.pk)
        if ids:
            enqueue_projection(claim, contract=contract, evidence_ids=ids)

    _checkpoint(
        claim,
        job,
        _revision(job, origin.observation_key),
        scope_kind="archive_projection",
        scope_key=key,
        ownership=ownership,
        projection_contract=contract,
        resource_observation=origin,
        enumeration_complete=True,
        outcome="observed",
        raw_count=len(snapshot["payload"]["rows"]),
        write=write,
    )
