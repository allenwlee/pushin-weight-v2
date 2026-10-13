"""Historical source evidence and coverage share existing runs/scopes/observations.

Numeric admission remains the reviewed history importer's responsibility. Missing
source evidence creates a coverage outcome, never a zero-valued metric row.
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta

from django.db import transaction
from django.utils import timezone

from core.benchmark_metric_history import import_history, prepare_history
from core.benchmark_metric_store import aware_instant
from core.collection_identity import qualified_ownership
from core.collection_jobs import register_job, set_job_state
from core.collection_state import (
    BusyJob,
    checkpoint_scope,
    claim_job,
    fenced_run,
    finish_run,
)
from core.measurement_taxonomy import digest, require
from core.models import (
    BrandCompany,
    CollectionJob,
    CollectionObservation,
    CollectionRun,
    DataSource,
    HFOrg,
    Product,
    SourceSubjectMapping,
)
from scripts.benchmark_download_collector.history import date_chunks
from scripts.benchmark_download_collector.sources import (
    Budget,
    SourceError,
    arena,
    openrouter,
)


def _native_record(run, scoped, identifier, kind, payload, *, metadata=None):
    from core.benchmark_metric_store import safe_payload

    safe_payload(payload)
    resource = digest({"identifier": identifier, "kind": kind, "payload": payload})
    return CollectionObservation.objects.get_or_create(
        run=run,
        observation_key=resource,
        defaults={
            "scope_run": scoped,
            "resource_key": resource,
            "source_identifier": identifier,
            "source_subject_kind": "repository",
            "listing": payload,
            "dimensions": {"kind": kind},
            "source_metadata": metadata or {},
        },
    )[0]


def _latest_before_cutoff(observations, date_of, cutoff):
    """Select a source-dated revision without materializing a repository history."""
    head, order = None, None
    for row in observations.iterator(chunk_size=100):
        value = date_of(row)
        if not value:
            continue
        try:
            instant = aware_instant(value)
        except (ValueError, TypeError):
            continue
        candidate = (instant, row.observation_key)
        if instant < cutoff and (order is None or candidate > order):
            head, order = row, candidate
    return head


def _github_history(claim, job, pins, budget, items):
    import os

    from core.github_catalog import _events, _pinned_metadata, _record
    from core.github_metadata_client import GitHubMetadataClient

    client = GitHubMetadataClient(
        budget, key=os.environ.get("PUSHINWEIGHT_GITHUB_API_TOKEN")
    )
    for pin in pins:
        mapping = SourceSubjectMapping.objects.select_related("publisher_account").get(
            pk=pin["mapping_id"]
        )
        identifier = pin["native_identifier"]
        old = (
            CollectionRun.objects.get(pk=claim.run_id)
            .scopes.filter(scope_kind="repository_history", scope_key=identifier)
            .first()
        )
        if old and old.enumeration_complete:
            continue
        ownership = {
            "repository_id": identifier,
            "publisher_account_key": str(mapping.publisher_account_id),
            "mapping_hash": mapping.mapping_hash,
        }
        if old and old.observations.exists():
            repository = old.observations.first()
        else:
            aliases = mapping.identifier_metadata.get("aliases", [])
            require(aliases, "reviewed GitHub full-name alias required")
            result = client.repository(aliases[-1])
            if result.status != 200:
                raise SourceError(f"http_{result.status}")
            data = result.payload
            require(
                isinstance(data, dict)
                and str(data.get("id")) == identifier
                and data.get("private") is False
                and str(data.get("owner", {}).get("id"))
                == mapping.publisher_account.normalized_identifier,
                "public reviewed repository identity mismatch",
            )
            created = []

            def write(
                run,
                scoped,
                created=created,
                identifier=identifier,
                data=data,
                result=result,
            ):
                created.append(
                    _record(
                        run,
                        scoped,
                        identifier,
                        "repository",
                        data,
                        observed_at=result.observed_at,
                    )
                )

            checkpoint_scope(
                claim,
                scope_kind="repository_history",
                scope_key=identifier,
                ownership=ownership,
                write=write,
            )
            repository = created[0]
        _events(
            claim,
            client,
            repository,
            "releases",
            items,
            job.definition["budgets"]["items"],
        )
        _events(
            claim, client, repository, "tags", items, job.definition["budgets"]["items"]
        )
        commits = _events(
            claim,
            client,
            repository,
            "commits",
            items,
            job.definition["budgets"]["items"],
        )
        cutoff = aware_instant(job.definition["scope"]["cutoff"])
        head = _latest_before_cutoff(
            commits.observations.all(),
            lambda o: o.source_metadata.get("clocks", {}).get("committer_at"),
            cutoff,
        )
        if head:
            _pinned_metadata(claim, client, repository, commits, head=head)
        checkpoint_scope(
            claim,
            scope_kind="repository_history",
            scope_key=identifier,
            ownership=ownership,
            enumeration_complete=True,
            outcome="observed",
        )


def _hf_history(claim, job, pins, budget, items):
    from core.hf_metadata_client import HFMetadataClient

    budget.check()
    before = budget.remaining
    client = HFMetadataClient(
        budget.client,
        max_requests=budget.remaining,
        max_seconds=budget.deadline - budget.clock(),
        max_bytes=budget.max_bytes,
        max_total_bytes=budget.max_bytes - budget.total_bytes_read,
        clock=budget.clock,
        sleep=budget.sleep,
    )
    try:
        for pin in pins:
            identifier = pin["native_identifier"]
            namespace = identifier.split("/", 1)[0]
            org = HFOrg.objects.get(pk=namespace, confirmed=True)
            require(
                BrandCompany.objects.filter(
                    company_id=org.company_id,
                    brand_id=job.definition["scope"]["brand_id"],
                ).exists(),
                "HF publisher ownership changed",
            )
            ownership = {
                "repository_id": identifier,
                "namespace": namespace,
                "company_id": org.company_id,
            }
            head = (
                CollectionRun.objects.get(pk=claim.run_id)
                .scopes.filter(scope_kind="hf_history_head", scope_key=identifier)
                .first()
            )
            if head is None:
                result = client.model_group(identifier, "detail")
                if result.outcome != "ok":
                    raise SourceError(result.outcome)
                data = result.payload
                require(
                    isinstance(data, dict) and isinstance(data.get("sha"), str),
                    "native HF head revision required",
                )
                checkpoint_scope(
                    claim,
                    scope_kind="hf_history_head",
                    scope_key=identifier,
                    ownership=ownership,
                    enumeration_complete=True,
                    outcome="observed",
                    envelopes=[
                        {
                            "revision": data["sha"],
                            "attempts": json.loads(json.dumps(result.attempts)),
                        }
                    ],
                    write=lambda run, scoped, identifier=identifier, data=data: (
                        _native_record(
                            run,
                            scoped,
                            identifier,
                            "hf_metadata",
                            data,
                            metadata={
                                "revision": data["sha"],
                                "historical_public_visibility_proven": False,
                            },
                        )
                    ),
                )
                revision = data["sha"]
            else:
                revision = head.envelopes[0]["revision"]
            for kind in ("commits", "tree"):
                if kind == "tree":
                    commits = CollectionObservation.objects.filter(
                        run_id=claim.run_id,
                        source_identifier=identifier,
                        dimensions__kind="hf_commits",
                    )
                    dated_head = _latest_before_cutoff(
                        commits,
                        lambda o: o.source_metadata.get("source_record_date"),
                        aware_instant(job.definition["scope"]["cutoff"]),
                    )
                    if dated_head is None:
                        checkpoint_scope(
                            claim,
                            scope_kind="hf_repository_history",
                            scope_key=identifier + ":tree",
                            ownership=ownership,
                            enumeration_complete=True,
                            outcome="history_unavailable",
                            envelopes=[{"reason": "no_qualified_commit_at_cutoff"}],
                        )
                        continue
                    revision = dated_head.listing["id"]
                key = identifier + ":" + kind
                scoped = (
                    CollectionRun.objects.get(pk=claim.run_id)
                    .scopes.filter(scope_kind="hf_repository_history", scope_key=key)
                    .first()
                )
                while scoped is None or not scoped.enumeration_complete:
                    if items[0] >= job.definition["budgets"]["items"]:
                        raise SourceError("item_cap")
                    result = client.history_page(
                        identifier, revision, kind, scoped.cursor if scoped else None
                    )
                    if result.outcome != "ok":
                        raise SourceError(result.outcome)
                    require(
                        len(result.payload)
                        <= job.definition["budgets"]["items"] - items[0],
                        "HF history item budget exceeded",
                    )
                    history = [
                        *(scoped.cursor_history if scoped else []),
                        scoped.cursor if scoped and scoped.cursor else "first",
                    ]
                    require(
                        result.next_cursor is None or result.next_cursor not in history,
                        "HF history cursor loop",
                    )

                    def write(
                        run,
                        scope,
                        rows=result.payload,
                        kind=kind,
                        identifier=identifier,
                        revision=revision,
                    ):
                        for row in rows:
                            _native_record(
                                run,
                                scope,
                                identifier,
                                "hf_" + kind,
                                row,
                                metadata={
                                    "revision": revision,
                                    "source_record_date": row.get("date"),
                                    "historical_public_visibility_proven": False,
                                },
                            )

                    scoped = checkpoint_scope(
                        claim,
                        scope_kind="hf_repository_history",
                        scope_key=key,
                        ownership=ownership,
                        cursor=result.next_cursor,
                        cursor_history=history,
                        enumeration_complete=result.next_cursor is None,
                        outcome="observed" if result.next_cursor is None else "partial",
                        write=write,
                        envelopes=[
                            *(scoped.envelopes if scoped else []),
                            {"revision": revision, "attempts": result.attempts},
                        ],
                    )
                    items[0] += len(result.payload)
    finally:
        budget.remaining = before - client.requests
        budget.total_bytes_read += client.bytes_received


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


def history_windows(start_at, cutoff, source, *, size=365):
    start, end = (
        aware_instant(start_at).astimezone(UTC).date(),
        aware_instant(cutoff).astimezone(UTC).date() - timedelta(days=1),
    )
    gaps = []
    if source == "openrouter" and start < datetime(2025, 1, 1, tzinfo=UTC).date():
        floor = datetime(2025, 1, 1, tzinfo=UTC).date()
        gaps.append(
            {
                "outcome": "outside_provider_coverage",
                "start_date": start.isoformat(),
                "end_date": min(end, floor - timedelta(days=1)).isoformat(),
                "reason": "provider_history_floor_2025_01_01",
            }
        )
        start = floor
    return (
        list(date_chunks(start.isoformat(), end.isoformat(), size=size))
        if start <= end
        else []
    ), gaps


def validate_model_pins(job):
    """Frozen ownership and identifiers cannot silently follow a later edit."""
    models = job.definition["scope"].get("models", [])
    require(
        isinstance(models, list) and len(models) <= 100,
        "bounded frozen model list required",
    )
    keys = [row["product_key"] for row in models]
    require(len(set(keys)) == len(keys), "duplicate frozen model")
    products = {
        str(p.product_key): p for p in Product.objects.filter(product_key__in=keys)
    }
    require(set(products) == set(keys), "frozen product no longer exists")
    for row in models:
        product = products[row["product_key"]]
        require(
            product.brand_id == job.definition["scope"]["brand_id"]
            and product.type in {"llm-model", "other-ai-model"},
            "frozen product ownership/type changed",
        )
        for pin in row.get("provider_pins", []):
            mapping = SourceSubjectMapping.objects.select_related(
                "subject", "publisher_account"
            ).get(pk=pin["mapping_id"], purpose="catalog")
            require(
                mapping.mapping_hash == pin["mapping_hash"]
                and mapping.subject.product_id == product.product_key,
                "frozen mapping changed",
            )
            require(
                mapping.publisher_account is not None
                and qualified_ownership(mapping.publisher_account, mapping.subject),
                "publisher ownership changed",
            )
            if mapping.source_id == "github":
                require(
                    mapping.publisher_account.normalized_identifier
                    == str(mapping.identity_snapshot["owner_id"]),
                    "native publisher identity changed",
                )
    return products


def import_selected_history(claim, manifest):
    """Admit a hashed sparse archive and checkpoint its provenance atomically."""
    manifest = copy.deepcopy(manifest)
    with fenced_run(claim) as (job, run):
        scope = job.definition["scope"]
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


def acquire_hf_archives(claim, job, budget):
    """Read reviewed immutable archive coordinates, persisting selected JSON first."""
    from scripts.benchmark_download_collector.hf_archive import (
        ArchiveBudget,
        select_snapshot,
    )

    scope = job.definition["scope"]
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
    revisions = archive.get("revisions", [])
    require(
        isinstance(revisions, list)
        and len(revisions) <= job.definition["budgets"]["items"],
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
        if scope.get("numeric_contract_id") and snap["payload"]["rows"]:
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
