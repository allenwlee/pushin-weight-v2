"""Sparse historical archive admission and immutable retrieval provenance.

Numeric admission remains the reviewed history importer's responsibility. Missing
source evidence creates a coverage outcome, never a zero-valued metric row.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime

from core.benchmark_metric_history import import_history, prepare_history
from core.benchmark_metric_identity import SOURCE_STATISTICS_POLICY
from core.benchmark_metric_store import aware_instant
from core.collection_state import (
    checkpoint_scope,
    fenced_run,
)
from core.measurement_taxonomy import digest, require
from core.model_history_cohort import validate_model_pins
from core.model_history_statistics import history_statistics_contract
from core.models import (
    CollectionObservation,
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
        ids = sorted(set(run.report.get("numeric_run_ids", [])) | {str(imported.pk)})
        run.report = {**run.report, "numeric_run_ids": ids}
        run.save(update_fields=["report", "updated_at"])
        key = digest(manifest)
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
            envelopes=[
                {
                    "selected_manifest_sha256": key,
                    "numeric_run_id": str(imported.pk),
                    "snapshots": [
                        {
                            k: s.get(k)
                            for k in (
                                "date",
                                "immutable_revision",
                                "file_path",
                                "raw_artifact_sha256",
                                "upstream_binary_sha256",
                            )
                        }
                        for s in manifest["snapshots"]
                    ],
                }
            ],
        )
        return imported


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
        isinstance(revisions, list)
        and len(revisions) <= job.budgets["items"],
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
        old = CollectionObservation.objects.filter(
            run_id=claim.run_id, observation_key=cache_key
        ).first()
        if old:
            snap = old.listing
        else:
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

            def write(run, scoped, snap=snap, cache_key=cache_key):
                CollectionObservation.objects.get_or_create(
                    run=run,
                    observation_key=cache_key,
                    defaults={
                        "scope_run": scoped,
                        "resource_key": cache_key,
                        "source_identifier": archive["dataset_id"],
                        "source_subject_kind": "aggregate",
                        "listing": snap,
                        "dimensions": {"kind": "archive_snapshot"},
                        "source_metadata": {
                            "secondary_source": True,
                            "cohort_hash": scope["cohort_hash"],
                        },
                    },
                )

            checkpoint_scope(
                claim,
                scope_kind="archive_snapshot",
                scope_key=cache_key,
                ownership={
                    "dataset_id": archive["dataset_id"],
                    "cohort_hash": scope["cohort_hash"],
                },
                enumeration_complete=True,
                outcome="observed",
                write=write,
            )
        snapshots.append(snap)
        contract = history_statistics_contract(job)
        if (
            contract
            and contract.source_configuration["hf"].get("eligibility_policy")
            == SOURCE_STATISTICS_POLICY
        ):
            _queue_hf_archive(claim, job, contract, archive, snap)
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


def _queue_hf_archive(claim, job, contract, archive, snapshot):
    from core.source_metric_projection import enqueue_projection

    key = digest(
        [
            archive["dataset_id"],
            snapshot["immutable_revision"],
            snapshot["date"],
            contract.contract_hash,
        ]
    )
    # Capture and enqueue share the checkpoint transaction. Its durable queue
    # survives interruption; a completed capture must never recreate that work.
    if CollectionScopeRun.objects.filter(
        run_id=claim.run_id,
        scope_kind="archive_projection",
        scope_key=key,
        enumeration_complete=True,
    ).exists():
        return

    def write(run, scoped):
        ids = []
        for row in snapshot["payload"]["rows"]:
            identifier = row["repo_id"]
            identity = {
                "dataset_id": archive["dataset_id"],
                "revision": snapshot["immutable_revision"],
                "date": snapshot["date"],
                "native_identifier": identifier,
            }
            observation_key = digest(["hf-archive-native", identity])
            payload = {"id": identifier, "private": False, **row["raw"]}
            observation, _ = CollectionObservation.objects.get_or_create(
                run=run,
                observation_key=observation_key,
                defaults={
                    "scope_run": scoped,
                    "resource_key": observation_key,
                    "source_identifier": identifier,
                    "source_subject_kind": "repository",
                    "listing": payload,
                    "dimensions": {"kind": "hf_archive_metadata"},
                    "source_metadata": {
                        "secondary_source": True,
                        "dataset_id": archive["dataset_id"],
                        "archive_publisher": archive["archive_publisher"],
                        "numeric_snapshot_identity": identity,
                        "archive_snapshot_date": snapshot["date"],
                        "clocks": {"archive_snapshot_date": snapshot["date"]},
                        "metric_times": {
                            metric: {
                                "temporal_status": "date_only",
                                "as_of_date": snapshot["date"],
                            }
                            for metric in ("likes", "trending_score")
                        },
                        "retrieval_coordinates": snapshot[
                            "upstream_retrieval_coordinates"
                        ],
                    },
                },
            )
            require(observation.listing == payload, "immutable HF archive conflict")
            ids.append(observation.pk)
        if ids:
            enqueue_projection(claim, contract=contract, evidence_ids=ids)

    checkpoint_scope(
        claim,
        scope_kind="archive_projection",
        scope_key=key,
        ownership={
            "dataset_id": archive["dataset_id"],
            "contract_hash": contract.contract_hash,
        },
        enumeration_complete=True,
        outcome="observed",
        write=write,
    )
