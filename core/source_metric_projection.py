"""Reviewed native statistics projected from durable evidence without HTTP.

Acquisition and replay share prepare_rows/commit_prepared_rows with benchmark
imports. Catalog evidence stays immutable; metric runs own pinned projections.
"""

from __future__ import annotations

import copy
import json
from contextlib import contextmanager
from time import monotonic

from django.db import transaction
from django.db.models import Q

from core.benchmark_metric_identity import (
    SOURCE_STATISTICS_POLICY,
    configure_collection,
)
from core.benchmark_metric_store import (
    collection_lock,
    commit_prepared_rows,
    native_rows,
    prepare_rows,
)
from core.collection_capture import observation_object_documents
from core.collection_state import checkpoint_scope, claim_job, fenced_run, finish_run
from core.measurement_taxonomy import digest, require
from core.models import (
    BrandAccount,
    CollectionJob,
    CollectionObservation,
    CompanyAccount,
)


def _ownership_pin(account):
    return {
        "companies": sorted(
            [
                {"company_id": row.company_id, "confirmed": row.ownership_confirmed}
                for row in CompanyAccount.objects.filter(
                    account=account, role_id="official"
                )
            ],
            key=lambda row: row["company_id"],
        ),
        "brands": sorted(
            BrandAccount.objects.filter(
                account=account, role_id="official"
            ).values_list("brand_id", flat=True)
        ),
    }


def validate_statistics_mapping(subject, row, source, taxonomy):
    """Separate reviewed resource ownership from canonical product eligibility."""
    from core.collection_identity import qualified_ownership
    from core.models import Account

    if source in {"openrouter", "arena"}:
        from core.models import SourceSubjectMapping

        metadata = row.get("identifier_metadata", {})
        reviewed = SourceSubjectMapping.objects.select_related(
            "subject", "publisher_account"
        ).get(
            pk=metadata.get("catalog_mapping_id"), purpose="catalog", source_id=source
        )
        require(
            reviewed.mapping_hash == metadata.get("catalog_mapping_hash")
            and reviewed.subject_id == subject.pk
            and reviewed.external_identifier == row["external_identifier"]
            and reviewed.identifier_scope_code
            == ("rankings_permaslug" if source == "openrouter" else "arena_model_name")
            and reviewed.publisher_account is not None
            and qualified_ownership(reviewed.publisher_account, subject),
            "reviewed publication identifier/ownership changed",
        )
        require(
            str(reviewed.publisher_account_id) == str(row.get("publisher_account_key")),
            "publication publisher changed",
        )
        pin = metadata.get("publisher_ownership")
        require(
            pin == _ownership_pin(reviewed.publisher_account),
            "publisher ownership pin changed",
        )
        account = reviewed.publisher_account
        require(
            metadata.get("publisher_native_identity")
            == {
                "source": account.data_source_id,
                "identifier": account.normalized_identifier,
                "account_kind": account.account_kind,
            },
            "publication publisher native identity changed",
        )
        if account.data_source_id == "hf":
            require(
                CompanyAccount.objects.filter(
                    account=account, role_id="official", ownership_confirmed=True
                ).exists(),
                "HF publication publisher ownership unconfirmed",
            )
        frozen = taxonomy.snapshot["products"][str(subject.product_id)]
        require(
            subject.product.brand_id == frozen["brand"]
            and subject.product.product_type_code == frozen["type"]
            and subject.product.private is not True
            and subject.product.disabled is not True,
            "publication product identity changed",
        )
        if frozen.get("model_kind_qualification"):
            from core.model_kind_qualification import validate_model_kind

            validate_model_kind(subject.product, frozen["model_kind_qualification"])
        return

    publisher = row.get("publisher_account_key")
    require(publisher is not None, "reviewed publisher required")
    account = Account.objects.get(pk=publisher, data_source_id=source)
    pin = row.get("identifier_metadata", {}).get("publisher_ownership")
    if pin is not None:
        require(pin == _ownership_pin(account), "publisher ownership pin changed")
    official = CompanyAccount.objects.filter(account=account, role_id="official")
    if source == "hf":
        official = official.filter(ownership_confirmed=True)
    require(
        official.exists()
        or source == "github"
        and BrandAccount.objects.filter(account=account, role_id="official").exists(),
        "verified publisher ownership required",
    )
    require(
        subject.subject_kind in {"account", "product"}, "unsupported statistics subject"
    )
    require(qualified_ownership(account, subject), "publisher does not own subject")
    if subject.subject_kind == "product":
        require(
            row.get("identifier_metadata", {}).get("role")
            in {"dedicated_model", "family_repository"},
            "reviewed repository relation required",
        )
        require(
            row["source_subject_kind"] in {"repository", "model"},
            "resource mapping required",
        )
        frozen = taxonomy.snapshot["products"][str(subject.product_id)]
        require(
            subject.product.brand_id == frozen["brand"]
            and subject.product.product_type_code == frozen["type"]
            and subject.product.private is not True
            and subject.product.disabled is not True,
            "statistics product identity changed",
        )
        require(
            frozen["type"] in {"llm-model", "other-ai-model", "agent-harness"}
            or frozen.get("model_kind_qualification"),
            "unreviewed statistics product type",
        )
        if frozen.get("model_kind_qualification"):
            from core.model_kind_qualification import validate_model_kind

            validate_model_kind(subject.product, frozen["model_kind_qualification"])


def validate_publication_provenance(source, settings):
    provenance = settings.get("publication_provenance", {})
    require(
        provenance.get("dataset_id")
        == {
            "openrouter": "openrouter/rankings-daily",
            "arena": "lmarena-ai/leaderboard-dataset",
        }[source]
        and provenance.get("reviewed_by")
        and provenance.get("source_url")
        == {
            "openrouter": "https://openrouter.ai/rankings",
            "arena": "https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset",
        }[source],
        "reviewed official publication provenance required",
    )


def configure_source_statistics(spec):
    """Create/reuse an immutable policy partition; never enable a source or job."""
    selected = copy.deepcopy(spec)
    from core.models import Account

    for mapping in selected["mappings"]:
        publisher = mapping.get("publisher_account_key")
        require(publisher is not None, "reviewed publisher required")
        account = Account.objects.get(pk=publisher)
        require(
            mapping["source"] in {"arena", "openrouter"}
            or account.data_source_id == mapping["source"],
            "publisher source mismatch",
        )
        pin = _ownership_pin(account)
        mapping.setdefault("identifier_metadata", {}).setdefault(
            "publisher_ownership", pin
        )
        if mapping["source"] in {"openrouter", "arena"}:
            mapping["identifier_metadata"].setdefault(
                "publisher_native_identity",
                {
                    "source": account.data_source_id,
                    "identifier": account.normalized_identifier,
                    "account_kind": account.account_kind,
                },
            )
    for source, settings in selected["source_configuration"].items():
        if source == "hf":
            versions = settings.setdefault("metric_versions", {})
            for key in ("downloads", "downloads_all_time"):
                if key in settings["metrics"]:
                    versions.setdefault(key, 2)
    return configure_collection(selected, eligibility_policy=SOURCE_STATISTICS_POLICY)


def configure_statistics_partitions(spec):
    """Deterministically partition 1,000-mapping contracts, reserving one native owner.

    Pass one brand/source selection at a time. Publisher mappings repeat for
    admission; only the first partition accepts unmapped native resources.
    Reuse the returned contracts for routine and historical jobs.
    """
    selected = copy.deepcopy(spec)
    require(
        len(selected["source_configuration"]) == 1, "partition one source at a time"
    )
    publishers = sorted(
        (m for m in selected["mappings"] if m["source_subject_kind"] == "account"),
        key=lambda m: (m["source"], m["external_identifier"]),
    )
    models = sorted(
        (m for m in selected["mappings"] if m["source_subject_kind"] != "account"),
        key=lambda m: (m["source"], m["external_identifier"], m["subject_id"]),
    )
    require(0 < len(publishers) < 1000, "bounded publisher mappings required")
    size = 1000 - len(publishers)
    result = []
    for start in range(0, max(1, len(models)), size):
        partition = copy.deepcopy(selected)
        partition["mappings"] = publishers + models[start : start + size]
        for settings in partition["source_configuration"].values():
            settings["native_resources"] = (
                settings.get("native_resources", True) and start == 0
            )
            settings["native_exclusions"] = sorted(
                m["external_identifier"].casefold()
                if m["source"] == "hf"
                else m["external_identifier"]
                for m in models[start + size :]
                if m.get("identifier_metadata", {}).get("role") == "dedicated_model"
            )
        result.append(configure_source_statistics(partition))
    return result


def _publisher(contract, source, identifier):
    normalized = identifier.casefold() if source == "hf" else identifier
    mapping = (
        contract.mappings.select_related("subject__account")
        .filter(
            source_id=source,
            source_subject_kind="account",
            normalized_identifier=normalized,
        )
        .first()
    )
    require(mapping is not None, "resource owner outside reviewed publishers")
    validate_statistics_mapping(
        mapping.subject,
        {
            "publisher_account_key": str(mapping.subject.account_id),
            "source_subject_kind": "account",
            "identifier_metadata": mapping.identifier_metadata,
        },
        source,
        contract.taxonomy_version,
    )
    require(
        mapping.identity_snapshot
        == contract.catalog_snapshot["subjects"][str(mapping.subject_id)],
        "publisher snapshot mismatch",
    )
    account = mapping.subject.account
    require(
        account.normalized_identifier == normalized
        and account.data_source_id == source,
        "publisher native identity changed",
    )
    return mapping


def evidence_rows(contract, source, evidence):
    """Yield supported native rows; preserve snapshot and effective clocks separately."""
    require(
        evidence.run.job.purpose == "catalog" and evidence.run.job.source_id == source,
        "catalog evidence source mismatch",
    )
    require(evidence.status == "ok", "source evidence is an error")
    raw, captured_dimensions, captured_metadata = observation_object_documents(evidence)
    require(isinstance(raw, dict), "native object evidence required")
    if source in {"openrouter", "arena"}:
        yield from _publication_rows(
            contract, source, evidence, raw, captured_dimensions, captured_metadata,
        )
        return
    dimensions = {}
    if evidence.source_subject_kind == "account":
        identity = evidence.source_identifier
        require(source in {"hf", "github"}, "unsupported statistics account")
        if source == "github":
            require(str(raw.get("id")) == identity, "native account identity mismatch")
        else:
            require(
                (
                    raw.get("name")
                    or raw.get("user")
                    or raw.get("organization")
                    or raw.get("id")
                    or ""
                ).casefold()
                == identity.casefold(),
                "native account identity mismatch",
            )
        publisher = _publisher(contract, source, identity)
        native = {
            "account_identifier": identity,
            "account_kind": publisher.identifier_scope_code,
            "raw": raw,
        }
    elif source == "hf":
        identity = raw.get("id") or raw.get("modelId")
        require(
            isinstance(identity, str)
            and "/" in identity
            and identity.casefold() == evidence.source_identifier.casefold(),
            "HF evidence identity mismatch",
        )
        require(raw.get("private") is not True, "private repository")
        publisher = _publisher(contract, source, identity.split("/", 1)[0])
        native = {"repo_id": identity, "raw": raw}
    elif source == "github":
        kind = captured_dimensions.get("kind")
        require(
            kind in {"repository", "repository_access", "release_asset"},
            "unsupported numeric evidence kind",
        )
        identity = (
            str(raw.get("id"))
            if kind in {"repository", "repository_access"}
            else evidence.source_identifier
        )
        require(
            identity == evidence.source_identifier,
            "native repository identity mismatch",
        )
        if kind in {"repository", "repository_access"}:
            require(
                type(raw.get("id")) is int
                and raw["id"] > 0
                and raw.get("private") is False,
                "public native repository required",
            )
            owner = str(raw.get("owner", {}).get("id"))
        else:
            owner = str(captured_metadata.get("owner_id"))
            require(
                raw.get("id") == captured_dimensions.get("asset_id")
                and captured_dimensions.get("release_id") is not None,
                "asset identity required",
            )
            dimensions = {
                key: captured_dimensions[key] for key in ("release_id", "asset_id")
            }
        publisher = _publisher(contract, source, owner)
        native = {"repository_id": identity, "raw": raw, "dimensions": dimensions}
    else:
        raise ValueError("unsupported native statistics source")
    from core.benchmark_metric_timing import native_origin

    created = native_origin(raw)
    if "numeric_fields" in captured_metadata:
        fields = set(captured_metadata["numeric_fields"])
        native["raw"] = {
            key: value
            for key, value in raw.items()
            if key in fields or key in {"id", "modelId", "private"}
        }
    row = next(native_rows(source, {"status": "ok", "rows": [native]}))
    row["observed_at"] = evidence.observed_at.isoformat()
    row["native_created_at"] = created
    row["dimensions"] = dimensions
    row["resource_key"] = identity + (
        ":asset:" + str(dimensions["asset_id"]) if dimensions else ""
    )
    # Native publication/period/revision pins may be supplied by history adapters.
    # Repository modification times never substitute for a measurement end.
    snapshot = captured_metadata.get("numeric_snapshot_identity")
    snapshot_kind = "publication" if snapshot else "capture"
    if not snapshot:
        snapshot = {
            "origin_observation_id": evidence.pk,
            "observation_key": evidence.observation_key,
            "observed_at": evidence.observed_at.isoformat(),
            "payload_sha256": digest(raw),
        }
    metadata = {
        **copy.deepcopy(captured_metadata),
        "projection_kind": SOURCE_STATISTICS_POLICY,
        "snapshot_kind": snapshot_kind,
        "snapshot_identity": snapshot,
        "origin_observation_id": evidence.pk,
        "origin_run_id": str(evidence.run_id),
        "source_payload_sha256": digest(raw),
        "publisher_mapping_id": str(publisher.pk),
        "publisher_mapping_hash": publisher.mapping_hash,
        "contract_hash": contract.contract_hash,
        "definitions_sha256": digest(
            contract.source_configuration[source]["definitions"]
        ),
        "clocks": copy.deepcopy(captured_metadata.get("clocks", {})),
    }
    row["source_metadata"] = metadata
    row["projection_key"] = digest(
        [
            SOURCE_STATISTICS_POLICY,
            source,
            contract.contract_hash,
            metadata["definitions_sha256"],
            evidence.source_subject_kind,
            identity.casefold() if source == "hf" else identity,
            dimensions,
            snapshot,
        ]
    )
    row["publication_precision"] = evidence.publication_precision
    if evidence.published_at:
        row["published_at"] = evidence.published_at.isoformat()
    if evidence.published_date:
        row["published_date"] = evidence.published_date.isoformat()
    # History adapters pin precision; the shared writer resolves omitted reported timing.
    for key, times in captured_metadata.get("metric_times", {}).items():
        if key in row["metrics"]:
            row["metrics"][key].update(times)
    yield row


def _publication_rows(contract, source, evidence, payload, captured_dimensions, captured_metadata):
    settings = contract.source_configuration[source]
    validate_publication_provenance(source, settings)
    require(
        captured_dimensions.get("kind") == "publication_row",
        "selected publication evidence required",
    )
    require(
        captured_metadata.get("publication_provenance")
        == settings["publication_provenance"],
        "publication provenance pin mismatch",
    )
    require(len(payload.get("rows", [])) == 1, "one immutable publication row required")
    if source == "arena":
        require(
            payload.get("config") == settings.get("config"),
            "Arena contract configuration mismatch",
        )
    row = next(native_rows(source, payload))
    row["identifier_scope"] = (
        "rankings_permaslug" if source == "openrouter" else "arena_model_name"
    )
    row["observed_at"] = evidence.observed_at.isoformat()
    row["resource_key"] = row["source_identifier"]
    snapshot = captured_metadata["numeric_snapshot_identity"]
    row["dimensions"]["revision"] = snapshot["revision"]
    row["source_metadata"] = {
        **row["source_metadata"],
        "projection_kind": SOURCE_STATISTICS_POLICY,
        "snapshot_kind": "publication",
        "snapshot_identity": snapshot,
        "origin_observation_id": evidence.pk,
        "origin_run_id": str(evidence.run_id),
        "source_payload_sha256": digest(payload),
        "publication_provenance": settings["publication_provenance"],
        "dataset_id": settings["publication_provenance"]["dataset_id"],
        "clocks": copy.deepcopy(captured_metadata.get("clocks", {})),
    }
    row["projection_key"] = digest(
        [
            SOURCE_STATISTICS_POLICY,
            source,
            contract.contract_hash,
            digest(settings["definitions"]),
            row["source_subject_kind"],
            row["source_identifier"],
            row["dimensions"],
            snapshot,
        ]
    )
    yield row


def enqueue_projection(claim, *, contract, evidence_ids):
    """Call within the evidence commit transaction: retain pending IDs atomically.

    The acquisition worker keeps its own claim. A later metric-purpose worker
    consumes the durable reference; this creates no execution or scheduler.
    """
    require(
        transaction.get_connection().in_atomic_block,
        "enqueue inside evidence transaction",
    )
    with fenced_run(claim) as (_, run):
        require(
            run.job.purpose == "catalog"
            and run.job.source_id in contract.source_configuration,
            "projection queue requires catalog source evidence",
        )
        ids = sorted(set(evidence_ids))
        require(
            len(ids) <= 100000
            and CollectionObservation.objects.filter(run=run, pk__in=ids).count()
            == len(ids),
            "queue evidence outside capture run",
        )
        key = str(contract.pk)
        existing = run.scopes.filter(
            scope_kind="numeric_projection", scope_key=key
        ).first()
        # Ownership stays immutable; pending references live in envelopes.
        references = sorted(
            set(
                ids
                + (
                    [r["observation_id"] for r in existing.envelopes]
                    if existing
                    else []
                )
            )
        )
        return checkpoint_scope(
            claim,
            scope_kind="numeric_projection",
            scope_key=key,
            ownership={"contract_id": key, "contract_hash": contract.contract_hash},
            projection_contract=contract,
            envelopes=[{"observation_id": pk} for pk in references],
            outcome="pending",
            raw_count=len(references),
        )


def _project_evidence(
    claim, evidence_ids, *, cursor=None, complete=True, deadline=None
):
    """Write a bounded batch and its checkpoint under source lock + claim fence.

    Returns a terminal metric attempt. Unknown ownership produces explicit gaps;
    immutable identity conflicts raise and roll back all rows/checkpoints.
    """
    started = monotonic()
    job = CollectionJob.objects.select_related("contract", "source").get(
        pk=claim.job_id
    )
    contract, source = job.contract, job.source_id
    require(
        job.purpose == "metric" and contract is not None,
        "metric projection run required",
    )
    settings = contract.source_configuration[source]
    require(
        settings.get("eligibility_policy") == SOURCE_STATISTICS_POLICY,
        "statistics contract required",
    )
    require(
        len(evidence_ids)
        == len(set(evidence_ids))
        <= job.budgets["items"],
        "projection item budget exceeded or duplicate evidence",
    )
    from core.benchmark_attribution import enforce_source_collection

    enforce_source_collection(contract, source)
    selected = list(
        CollectionObservation.objects.select_related("run", "source_dataset", "legacy_archive")
        .prefetch_related("run__job")
        .filter(pk__in=evidence_ids)
        .order_by("pk")
    )
    require(len(selected) == len(evidence_ids), "source evidence missing")
    require(
        sum(_evidence_bytes(evidence) for evidence in selected)
        <= job.budgets["bytes"],
        "projection byte budget exceeded",
    )
    prepared, rejections, terminal_ids = [], [], []
    for evidence in selected:
        require(
            monotonic() - started <= job.budgets["seconds"]
            and (deadline is None or monotonic() < deadline),
            "projection time budget exceeded",
        )
        try:
            from core.collection_datasets import observation_dataset_code

            dataset = observation_dataset_code(evidence)
            if dataset:
                enforce_source_collection(contract, source, dataset=dataset)
            rows = list(evidence_rows(contract, source, evidence))
            entries = prepare_rows(
                contract,
                source,
                {"config": contract.source_configuration[source].get("config")}
                if source == "arena"
                else {},
                adapter=lambda _, prepared_rows=rows: prepared_rows,
            )
            for data, values in entries:
                mapping = data["mapping"]
                native_identifier = (
                    data["source_identifier"].casefold()
                    if source == "hf"
                    else data["source_identifier"]
                )
                if mapping is None and (
                    not settings.get("native_resources", True)
                    or native_identifier in settings.get("native_exclusions", [])
                ):
                    raise ValueError("native resource belongs to destination partition")
                for rejection in data["source_metadata"].get("metric_rejections", []):
                    rejections.append(
                        {
                            "observation_id": evidence.pk,
                            "outcome": "invalid",
                            **rejection,
                        }
                    )
                if not values:
                    terminal_ids.append(evidence.pk)
                    rejections.append(
                        {
                            "observation_id": evidence.pk,
                            "terminal": True,
                            "outcome": "invalid"
                            if data["source_metadata"].get("metric_rejections")
                            else "not_returned",
                            "reason": "no supported numeric counters returned",
                        }
                    )
                else:
                    prepared.append((data, values))
        except (ValueError, KeyError, TypeError) as exc:
            rejections.append({"observation_id": evidence.pk, "reason": str(exc)})
    with collection_lock(contract, source), fenced_run(claim) as (_, run):
        observations, accounting = commit_prepared_rows(
            run, prepared, reuse_snapshots=True
        )
        previous = run.scopes.filter(
            scope_kind="numeric_projection", scope_key="saved-evidence"
        ).first()
        prior = previous.envelopes[0] if previous and previous.envelopes else {}
        mapped = sum(observation.product_id is not None for observation in observations)
        projection = {
            **accounting,
            "selected_resources": len(selected),
            "admitted_resources": len(observations),
            "terminal_resources": len(set(terminal_ids)),
            "mapped_resources": mapped,
            "native_only_resources": len(observations) - mapped,
            "rejections": rejections,
            "observation_ids": [observation.pk for observation in observations],
            "source_observation_ids": [evidence.pk for evidence in selected],
        }
        for counter in (
            "selected_resources",
            "admitted_resources",
            "terminal_resources",
            "mapped_resources",
            "native_only_resources",
            "written_values",
            "written_observations",
        ):
            projection[counter] += prior.get(counter, 0)
        for references in (
            "observation_ids",
            "source_observation_ids",
            "reused_observation_ids",
            "rejections",
        ):
            projection[references] = prior.get(references, []) + projection[references]
        coverage = [
            {
                "source": source,
                "observation_id": observation.pk,
                "source_identifier": observation.source_identifier,
                "dimensions": observation_object_documents(observation)[1],
                "outcome": "native_only"
                if observation.product_id is None
                else "reused"
                if observation.pk in accounting["reused_observation_ids"]
                else "written",
            }
            for observation in observations
        ]
        coverage += [
            {
                "source": source,
                "origin_observation_id": rejection["observation_id"],
                "outcome": rejection.get(
                    "outcome", "not_returned" if "metric" in rejection else "unmapped"
                ),
                "reason": rejection["reason"],
                **({"metric": rejection["metric"]} if "metric" in rejection else {}),
            }
            for rejection in rejections
        ]
        coverage = (
            run.report.get("coverage", []) if not prior else prior.get("coverage", [])
        ) + coverage
        projection["coverage"] = coverage
        checkpoint_scope(
            claim,
            scope_kind="numeric_projection",
            scope_key="saved-evidence",
            ownership={"contract_hash": contract.contract_hash},
            projection_contract=contract,
            cursor=cursor,
            enumeration_complete=complete,
            outcome="complete" if complete else "pending",
            raw_count=projection["selected_resources"],
            envelopes=[projection],
        )
        # Rejections of malformed optional fields do not invalidate admitted resources.
        missing = (
            projection["admitted_resources"] + projection["terminal_resources"]
            != projection["selected_resources"]
        )
        return finish_run(
            claim,
            status="success" if complete and not missing else "partial",
            selected_count=projection["selected_resources"],
            success_count=projection["admitted_resources"],
            request_count=0,
            report={
                "projection": projection,
                "coverage": coverage,
                "physical_accounting_complete": True,
            },
        )


def _evidence_bytes(evidence):
    listing, dimensions, metadata = observation_object_documents(evidence)
    return len(
        json.dumps(
            [listing, metadata, dimensions],
            ensure_ascii=False,
        ).encode("utf-8")
    )


def project_evidence(claim, evidence_ids, *, cursor=None, complete=True, deadline=None):
    """Project one fenced batch; invalid/conflicting evidence produces a failed receipt.

    Unexpected exceptions retain the active claim for ordinary crash/reclaim
    handling. A stale claim can never publish a failure over its successor.
    """
    from core.collection_state import StaleClaim

    try:
        return _project_evidence(
            claim, evidence_ids, cursor=cursor, complete=complete, deadline=deadline
        )
    except StaleClaim:
        raise
    except (ValueError, KeyError, TypeError) as exc:
        # Source lock contention is retryable within the same still-live claim.
        if str(exc) == "metric collection is already running":
            raise
        finish_run(
            claim,
            status="failed",
            error_code="invalid_numeric_projection",
            report={"projection_error": str(exc)},
            request_count=0,
        )
        raise


def replay_saved_evidence(job_id):
    """Default CLI hook: bounded database cursor; no provider client is constructed."""
    started = monotonic()
    job = CollectionJob.objects.select_related("contract").get(pk=job_id)
    deadline = started + job.budgets["seconds"]
    scope = job.scope
    runs, jobs = scope.get("origin_run_ids", []), scope.get("origin_job_ids", [])
    require(
        isinstance(runs, list)
        and isinstance(jobs, list)
        and 0 < len(runs) + len(jobs) <= 1000,
        "bounded origin run/job selection required",
    )
    require(
        job.purpose == "metric"
        and job.contract
        and job.contract.source_configuration.get(job.source_id, {}).get(
            "eligibility_policy"
        )
        == SOURCE_STATISTICS_POLICY,
        "statistics replay contract required",
    )
    claim = claim_job(job.pk)
    with fenced_run(claim) as (_, run):
        previous = run.scopes.filter(
            scope_kind="numeric_projection", scope_key="saved-evidence"
        ).first()
        cursor = int(previous.cursor) if previous and previous.cursor else 0
    selected = CollectionObservation.objects.filter(
        Q(run_id__in=runs) | Q(run__job_id__in=jobs),
        run__job__source_id=job.source_id,
        run__job__purpose="catalog",
        pk__gt=cursor,
        source_subject_kind__in=["repository", "account", "model", "aggregate"],
        status="ok",
    ).order_by("pk")
    if job.source_id == "github":
        selected = selected.filter(
            Q(source_subject_kind="account")
            | Q(observation_kind__in=["repository", "repository_access", "release_asset"])
        )
    if job.source_id in {"openrouter", "arena"}:
        selected = selected.filter(observation_kind="publication_row")
    ids, consumed, complete = [], 0, True
    last_processed = cursor
    evidence_rows = selected.select_related("legacy_archive").only(
        "id", "listing", "source_metadata", "dimensions",
        "legacy_archive__body", "legacy_archive__content_sha256",
    ).iterator(chunk_size=100)
    for evidence in evidence_rows:
        if monotonic() >= deadline:
            complete = False
            break
        if job.source_id == "hf" and observation_object_documents(evidence)[2].get("numeric_fields") == []:
            last_processed = evidence.pk
            continue
        size = _evidence_bytes(evidence)
        require(
            size <= job.budgets["bytes"],
            "projection byte budget exceeded for one snapshot",
        )
        if (
            len(ids) == job.budgets["items"]
            or consumed + size > job.budgets["bytes"]
            or monotonic() >= deadline
        ):
            complete = False
            break
        ids.append(evidence.pk)
        consumed += size
        last_processed = evidence.pk
    return project_evidence(
        claim,
        ids,
        cursor=str(last_processed),
        complete=complete,
        deadline=deadline,
    )


@contextmanager
def _projection_origin(catalog_job_id, origin_claim):
    """Fence live acquisition or lock an idle origin for standalone recovery."""
    if origin_claim is not None:
        require(
            str(origin_claim.job_id) == str(catalog_job_id),
            "projection origin claim mismatch",
        )
        with fenced_run(origin_claim) as (job, _):
            yield job
    else:
        with transaction.atomic():
            job = CollectionJob.objects.select_for_update().get(pk=catalog_job_id)
            require(
                job.active_run_id is None,
                "active catalog projection requires origin claim",
            )
            yield job


def drain_pending_projections(catalog_job_id, *, budget=None, origin_claim=None):
    """Consume durable capture references with one finite shared-writer budget.

    Acknowledgement follows numeric commit. A crash between them safely reuses
    immutable snapshots on the next call. Failed admission stays pending and
    inspectable; routine attempts do not enumerate completed captures.

    Acquisition callers must pass their held origin_claim. Omitting it permits
    standalone saved-queue recovery only while the origin has no active run.
    Origin locks never span metric job registration, claiming or projection:
    campaign claims lock peer jobs in their own order. Recheck the origin at
    acknowledgement so a replaced worker leaves pending references intact.
    """
    from core.collection_jobs import register_job, set_job_state, validate_job
    from core.models import CollectionScopeRun, MetricCollectionContract

    with _projection_origin(catalog_job_id, origin_claim) as origin:
        validate_job(origin)
        require(origin.purpose == "catalog", "catalog projection origin required")
    limits = origin.budgets
    started = monotonic()
    usage = {"items": 0, "bytes": 0}
    if budget is not None:
        if not hasattr(budget, "source_projection_usage"):
            budget.source_projection_usage = {}
        usage = budget.source_projection_usage.setdefault(str(origin.pk), usage)
    consumed, selected_count = usage["bytes"], usage["items"]
    remaining_seconds = lambda: min(
        limits["seconds"] - (monotonic() - started),
        budget.deadline - budget.clock() if budget is not None else limits["seconds"],
    )
    result = {
        "written_values": 0,
        "reused_resources": 0,
        "acknowledged": 0,
        "pending": False,
        "runs": [],
    }
    pending = (
        CollectionScopeRun.objects.filter(
            run__job=origin, scope_kind="numeric_projection", outcome="pending"
        )
        .select_related("run", "projection_contract")
        .order_by("pk")
    )
    for scope in pending.iterator():
        with _projection_origin(catalog_job_id, origin_claim):
            pass
        if selected_count >= limits["items"] or remaining_seconds() <= 0:
            break
        if scope.projection_contract_id:
            contract = scope.projection_contract
            require(
                str(contract.pk) == scope.scope_key,
                "projection contract pin changed",
            )
        else:
            contract = MetricCollectionContract.objects.get(
                pk=scope.ownership["contract_id"]
            )
            require(
                contract.contract_hash == scope.ownership["contract_hash"],
                "projection contract pin changed",
            )
        definition = {
            "version": 1,
            "scope": {
                "origin_run_ids": [str(scope.run_id)],
                "projection_scope_id": scope.pk,
            },
            "schedule": {"kind": "manual", "driver": "manual"},
            "budgets": {**limits, "requests": 1},
        }
        campaign = origin.campaign_settings
        if campaign:
            definition["campaign"] = {
                **campaign,
                "role": "projection",
                "phase": "replay",
                "contract_partition": str(contract.pk),
            }
        job = register_job(
            job_key="projection:"
            + digest([str(origin.pk), scope.pk, contract.contract_hash]),
            source=origin.source,
            purpose="metric",
            operation="collect_metrics",
            mode="manual",
            contract=contract,
            definition=definition,
        )
        if job.state == "paused":
            job = set_job_state(job.pk, "ready")
        ids = []
        evidence_batch = CollectionObservation.objects.filter(
            pk__in=[row["observation_id"] for row in scope.envelopes]
        ).order_by("pk")[: limits["items"] - selected_count]
        for evidence in evidence_batch.iterator(chunk_size=100):
            size = _evidence_bytes(evidence)
            if (
                selected_count + len(ids) >= limits["items"]
                or consumed + size > limits["bytes"]
                or remaining_seconds() <= 0
            ):
                break
            ids.append(evidence.pk)
            consumed += size
        if not ids:
            break
        with _projection_origin(catalog_job_id, origin_claim):
            pass
        claim = claim_job(job.pk)
        run = project_evidence(claim, ids, deadline=monotonic() + remaining_seconds())
        projection = run.report["projection"]
        rejected = {
            row["observation_id"]
            for row in projection["rejections"]
            if "metric" not in row and not row.get("terminal")
        }
        committed = set(ids) - rejected
        # Fence the acquisition before locking its queue row, matching enqueue's
        # job/run/scope order. An independent numeric commit remains valid when
        # this fence fails; its successor will reuse that immutable snapshot.
        with _projection_origin(catalog_job_id, origin_claim):
            current = CollectionScopeRun.objects.select_for_update().get(pk=scope.pk)
            current.envelopes = [
                row
                for row in current.envelopes
                if row["observation_id"] not in committed
            ]
            current.outcome = "pending" if current.envelopes else "complete"
            current.enumeration_complete = not current.envelopes
            current.cursor = str(max(committed)) if committed else current.cursor
            current.save()
        result["written_values"] += projection["written_values"]
        result["reused_resources"] += len(projection["reused_observation_ids"])
        result["acknowledged"] += len(committed)
        result["runs"].append(str(run.pk))
        selected_count += len(ids)
        usage.update(items=selected_count, bytes=consumed)
        if rejected:
            break
    result["pending"] = CollectionScopeRun.objects.filter(
        run__job=origin, scope_kind="numeric_projection", outcome="pending"
    ).exists()
    result["pending_resources"] = sum(
        len(scope.envelopes)
        for scope in CollectionScopeRun.objects.filter(
            run__job=origin, scope_kind="numeric_projection", outcome="pending"
        )
    )
    return result
