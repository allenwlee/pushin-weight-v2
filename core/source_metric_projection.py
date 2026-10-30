"""Reviewed native statistics projected from durable evidence without HTTP.

Acquisition and replay share prepare_rows/commit_prepared_rows with benchmark
imports. Catalog evidence stays immutable; metric runs own pinned projections.
"""

from __future__ import annotations

import copy
import json
import logging
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
    CollectionScopeRun,
    CompanyAccount,
    MetricValue,
)

PROJECTION_ITEM_KIND = "numeric_projection_item"
PROJECTION_QUEUE_PHASE = "projection_queue"
PROJECTION_RESULT_KIND = "numeric_projection_result"
PROJECTION_OUTPUT_KIND = "numeric_projection_output"
PROJECTION_RESULT_PHASE = "projection_results_v1"
logger = logging.getLogger(__name__)


def _empty_scope_compatibility():
    return {"ownership": {}} if any(
        field.name == "ownership" for field in CollectionScopeRun._meta.fields
    ) else {}


def _result_parent(claim, run, contract):
    previous = run.scopes.filter(scope_kind="numeric_projection", scope_key="saved-evidence").first()
    require(previous is None or previous.phase == PROJECTION_RESULT_PHASE,
            "historical projection summary requires explicit adoption before continuation")
    scope = previous or checkpoint_scope(
        claim, scope_kind="numeric_projection", scope_key="saved-evidence", typed=True,
        ownership={"contract_hash": contract.contract_hash}, projection_contract=contract,
    )
    if previous is None:
        scope.phase = PROJECTION_RESULT_PHASE
        scope.save(update_fields=["phase"])
    return scope


def _eligible_evidence_owner(evidence, source):
    job = evidence.run.job
    return job.source_id == source and (
        job.purpose == "catalog"
        or source in {"hf", "github"} and job.purpose == "content"
        and job.operation == "release_acquisition"
        and evidence.projection_kind == f"{source}-release-exact-v1"
    )


def _eligible_projection_origin(job):
    return job.purpose == "catalog" or (
        job.purpose == "content" and job.source_id in {"hf", "github"}
        and job.operation == "release_acquisition"
    )


def _retain_results(scope, selected, prepared, observations, accounting, before_values, rejections, terminal_ids):
    """One source evaluation and its actual outputs; reused rows keep their run."""
    from core.collection_capture import archive_document

    outputs = {}
    for observation, (data, values) in zip(observations, prepared, strict=True):
        outputs.setdefault(data["source_metadata"]["origin_observation_id"], []).append((observation, values))
    retained = {key: set(values) for key, values in before_values.items()}
    terminal_ids = set(terminal_ids)
    written = created = 0
    for evidence in selected:
        require(_eligible_evidence_owner(evidence, scope.run.job.source_id),
                "projection source owner changed")
        rows = outputs.get(evidence.pk, [])
        require(len(rows) <= 1, "one projection output per source capture required")
        diagnostics = [row for row in rejections if row["observation_id"] == evidence.pk]
        outcome = ("admitted_with_gaps" if diagnostics else "admitted") if rows else (
            "terminal_invalid" if any(row.get("outcome") == "invalid" for row in diagnostics)
            else "terminal_missing"
        ) if evidence.pk in terminal_ids else "rejected"
        diagnostic_archive = None
        if diagnostics:
            diagnostic_archive = archive_document(
                json.dumps({"version": 1, "source_observation_id": evidence.pk, "rejections": diagnostics},
                           sort_keys=True, separators=(",", ":"), allow_nan=False).encode(),
                encoding="selected-json-canonical-v1", capture_kind="numeric_projection_evidence",
            )
        # Re-evaluating a source in one logical run would destroy the original
        # accounting. New attempts/runs or an advancing cursor own new work.
        item = CollectionScopeRun.objects.create(
            run=scope.run, scope_kind=PROJECTION_RESULT_KIND, scope_key=str(evidence.pk),
            parent_scope=scope, resource_observation=evidence,
            projection_contract=scope.projection_contract, phase=PROJECTION_RESULT_PHASE,
            outcome=outcome, enumeration_complete=outcome != "rejected", raw_count=1,
            execution_state="yielded" if outcome == "rejected" else "completed",
            coverage_state="complete" if outcome == "admitted" else "partial",
            legacy_archive=diagnostic_archive, **_empty_scope_compatibility(),
        )
        for observation, values in rows:
            require(observation.run.job.contract_id == scope.projection_contract_id
                    and observation.run.job.source_id == scope.run.job.source_id
                    and observation.projection_kind == SOURCE_STATISTICS_POLICY,
                    "projection output contract or source changed")
            reused = observation.observation_key in retained
            previous = retained.setdefault(observation.observation_key, set())
            supplied = {value["source_metric"].pk for value in values}
            count = len(supplied - previous)
            previous.update(supplied)
            written += count
            created += not reused
            CollectionScopeRun.objects.create(
                run=scope.run, scope_kind=PROJECTION_OUTPUT_KIND,
                scope_key=f"{evidence.pk}:{observation.pk}", parent_scope=item,
                resource_observation=observation, projection_contract=scope.projection_contract,
                phase="reused" if reused else "written",
                admission_outcome="mapped" if observation.product_id is not None else "native_only",
                outcome="complete", enumeration_complete=True, raw_count=count,
                execution_state="completed", coverage_state="complete",
                **_empty_scope_compatibility(),
            )
    require(written == accounting["written_values"], "projection value accounting differs from committed rows")
    require(created == accounting["written_observations"], "projection observation accounting differs from committed rows")


def projection_report(run):
    """Operational status from typed results; exact diagnostics remain evidence."""
    from core.benchmark_serving import github_asset_coordinates, observation_dimensions

    scope = run.scopes.only("pk", "phase", "projection_contract_id").get(scope_kind="numeric_projection", scope_key="saved-evidence")
    require(scope.phase == PROJECTION_RESULT_PHASE and scope.projection_contract_id == run.job.contract_id,
            "projection results are not typed or have a different contract")
    items = list(scope.child_scopes.filter(scope_kind=PROJECTION_RESULT_KIND).select_related("resource_observation__run__job").only(
        "pk", "run_id", "scope_key", "phase", "outcome", "enumeration_complete", "raw_count",
        "projection_contract_id", "resource_observation_id", "resource_observation__run_id",
        "resource_observation__projection_kind", "resource_observation__run__job__operation",
        "resource_observation__run__job_id", "resource_observation__run__job__purpose",
        "resource_observation__run__job__source_id",
    ))
    output_rows = list(CollectionScopeRun.objects.filter(
        parent_scope__in=items, scope_kind=PROJECTION_OUTPUT_KIND,
    ).select_related("resource_observation__run__job", "parent_scope").only(
        "pk", "run_id", "scope_key", "phase", "outcome", "enumeration_complete", "raw_count",
        "admission_outcome", "projection_contract_id", "parent_scope_id", "parent_scope__resource_observation_id",
        "resource_observation_id", "resource_observation__source_identifier", "resource_observation__projection_kind",
        "resource_observation__config_key", "resource_observation__category_key", "resource_observation__source_record_date",
        "resource_observation__run_id", "resource_observation__run__job_id",
        "resource_observation__run__job__source_id", "resource_observation__run__job__contract_id",
    ))
    asset_coordinates = github_asset_coordinates(
        [row.resource_observation_id for row in output_rows],
    ) if run.job.source_id == "github" else {}
    by_source = {}
    for output in output_rows:
        observation = output.resource_observation
        require(output.run_id == run.pk and output.projection_contract_id == run.job.contract_id
                and output.phase in {"written", "reused"} and output.outcome == "complete"
                and output.admission_outcome in {"mapped", "native_only"}
                and output.enumeration_complete and output.raw_count >= 0 and observation is not None
                and observation.run.job.contract_id == run.job.contract_id
                and observation.run.job.source_id == run.job.source_id
                and observation.projection_kind == SOURCE_STATISTICS_POLICY
                and output.scope_key == f"{output.parent_scope.resource_observation_id}:{observation.pk}",
                "projection output identity changed")
        by_source.setdefault(output.parent_scope_id, []).append(output)
    rejections, coverage = [], []
    for item in items:
        evidence = item.resource_observation
        require(item.run_id == run.pk and item.projection_contract_id == run.job.contract_id
                and evidence is not None and _eligible_evidence_owner(evidence, run.job.source_id)
                and item.scope_key == str(evidence.pk) and item.phase == PROJECTION_RESULT_PHASE
                and item.raw_count == 1
                and item.outcome in {"admitted", "admitted_with_gaps", "terminal_invalid", "terminal_missing", "rejected"}
                and item.enumeration_complete == (item.outcome != "rejected"),
                "projection result identity changed")
        require(len(by_source.get(item.pk, [])) == (1 if item.outcome.startswith("admitted") else 0),
                "projection result output count changed")
        if item.outcome != "admitted":
            rejection = {
                "observation_id": evidence.pk, "outcome": item.outcome,
                "reason": item.outcome.replace("_", " "),
                "diagnostic_scope_id": item.pk,
            }
            if item.outcome.startswith("terminal"):
                rejection["terminal"] = True
            rejections.append(rejection)
            coverage.append({"source": run.job.source_id, "origin_observation_id": evidence.pk, **rejection})
    for output in output_rows:
        observation = output.resource_observation
        coverage.append({"source": run.job.source_id, "observation_id": observation.pk,
                         "source_identifier": observation.source_identifier,
                         "dimensions": asset_coordinates.get(observation.pk, observation_dimensions(observation)),
                         "outcome": "native_only" if output.admission_outcome == "native_only" else output.phase})
    return {
        "selected_resources": len(items), "admitted_resources": len(output_rows),
        "terminal_resources": sum(item.outcome.startswith("terminal") for item in items),
        "mapped_resources": sum(row.admission_outcome == "mapped" for row in output_rows),
        "native_only_resources": sum(row.admission_outcome == "native_only" for row in output_rows),
        "written_values": sum(row.raw_count for row in output_rows),
        "written_observations": sum(row.phase == "written" for row in output_rows),
        "reused_observation_ids": [row.resource_observation_id for row in output_rows if row.phase == "reused"],
        "observation_ids": [row.resource_observation_id for row in output_rows],
        "source_observation_ids": [item.resource_observation_id for item in items],
        "rejections": rejections, "coverage": coverage,
    }


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
            in {"dedicated_model", "dedicated_product", "family_repository"},
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
                if m.get("identifier_metadata", {}).get("role") in {"dedicated_model", "dedicated_product"}
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


def _evidence_documents(evidence):
    from core.collection_numeric_selection import numeric_fields
    from core.github_resource_evidence import asset_documents

    if evidence.observation_kind == "release_asset":
        return asset_documents(evidence)
    documents = observation_object_documents(evidence)
    if documents[1].get("kind") == "release_asset":
        return asset_documents(evidence, legacy_documents=documents)
    if evidence.run.job.source_id == "hf":
        fields = numeric_fields(evidence, legacy_metadata=documents[2])
        metadata = {**documents[2]}
        if fields is None:
            metadata.pop("numeric_fields", None)
        else:
            metadata["numeric_fields"] = fields
        return documents[0], documents[1], metadata
    return documents


def evidence_rows(contract, source, evidence):
    """Yield supported native rows; preserve snapshot and effective clocks separately."""
    require(
        _eligible_evidence_owner(evidence, source),
        "catalog or exact release evidence source mismatch",
    )
    require(evidence.status == "ok", "source evidence is an error")
    raw, captured_dimensions, captured_metadata = _evidence_documents(evidence)
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


def _projection_items(scope):
    return scope.child_scopes.filter(scope_kind=PROJECTION_ITEM_KIND)


def _retain_projection_items(scope, evidence_ids):
    """Keep one durable work item per actual source result, including completion."""
    ids = sorted(set(evidence_ids))
    require(
        len(ids) <= 100000 and all(type(pk) is int and pk > 0 for pk in ids)
        and CollectionObservation.objects.filter(
            pk__in=ids, run__job_id=scope.run.job_id,
        ).count() == len(ids),
        "queue evidence outside capture job",
    )
    CollectionScopeRun.objects.bulk_create([
        CollectionScopeRun(
            run_id=scope.run_id, scope_kind=PROJECTION_ITEM_KIND,
            scope_key=f"{scope.projection_contract_id}:{observation_id}",
            **_empty_scope_compatibility(), parent_scope=scope, resource_observation_id=observation_id,
            projection_contract_id=scope.projection_contract_id,
        )
        for observation_id in ids
    ], ignore_conflicts=True, batch_size=500)
    actual = {
        item.scope_key: item for item in CollectionScopeRun.objects.filter(
            run_id=scope.run_id, scope_kind=PROJECTION_ITEM_KIND,
            scope_key__in=[f"{scope.projection_contract_id}:{pk}" for pk in ids],
        )
    }
    for observation_id in ids:
        item = actual.get(f"{scope.projection_contract_id}:{observation_id}")
        require(
            item is not None and item.parent_scope_id == scope.pk
            and item.resource_observation_id == observation_id
            and item.projection_contract_id == scope.projection_contract_id,
            "numeric projection item identity changed",
        )


def _legacy_projection_ids(scope):
    from core.collection_capture import scope_object_documents

    _, _, references = scope_object_documents(scope)
    require(
        isinstance(references, list) and len(references) <= 100000 and all(
            isinstance(row, dict) and set(row) == {"observation_id"}
            and type(row["observation_id"]) is int and row["observation_id"] > 0
            for row in references
        ),
        "invalid historical numeric projection references",
    )
    ids = [row["observation_id"] for row in references]
    require(len(ids) == len(set(ids)), "duplicate historical numeric projection reference")
    return ids


def _adopt_projection_queue(scope):
    """Adopt old pending references once, under the origin and queue locks."""
    require(
        scope.scope_kind == "numeric_projection"
        and _eligible_projection_origin(scope.run.job)
        and scope.projection_contract_id is not None
        and scope.scope_key == str(scope.projection_contract_id),
        "numeric projection queue identity changed",
    )
    if scope.phase != PROJECTION_QUEUE_PHASE:
        _retain_projection_items(scope, _legacy_projection_ids(scope))
        scope.phase = PROJECTION_QUEUE_PHASE
        scope.save(update_fields=["phase"])
    require(
        not _projection_items(scope).exclude(
            run_id=scope.run_id, projection_contract_id=scope.projection_contract_id,
            resource_observation__run__job_id=scope.run.job_id,
        ).exists(),
        "numeric projection item ownership mismatch",
    )
    if scope.run.job.purpose == "content":
        require(
            not _projection_items(scope).exclude(
                resource_observation__projection_kind=f"{scope.run.job.source_id}-release-exact-v1"
            ).exists(),
            "release projection needs exact source captures",
        )
    for item in _projection_items(scope).only(
        "scope_key", "resource_observation_id", "outcome", "enumeration_complete",
    ):
        require(
            item.scope_key == f"{scope.projection_contract_id}:{item.resource_observation_id}"
            and item.outcome in {"pending", "complete"}
            and item.enumeration_complete == (item.outcome == "complete"),
            "numeric projection item state mismatch",
        )
    if scope.outcome == "pending" and not _projection_items(scope).filter(outcome="pending").exists():
        scope.outcome, scope.enumeration_complete = "complete", True
        scope.execution_state, scope.coverage_state = "completed", "complete"
        scope.save(update_fields=[
            "outcome", "enumeration_complete", "execution_state", "coverage_state",
        ])


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
            _eligible_projection_origin(run.job)
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
        if run.job.purpose == "content":
            require(
                CollectionObservation.objects.filter(
                    run=run, pk__in=ids, projection_kind=f"{run.job.source_id}-release-exact-v1"
                ).count() == len(ids),
                "release projection needs exact source captures",
            )
        key = str(contract.pk)
        existing = run.scopes.filter(
            scope_kind="numeric_projection", scope_key=key
        ).first()
        scope = existing or checkpoint_scope(
            claim, scope_kind="numeric_projection", scope_key=key,
            ownership={"contract_id": key, "contract_hash": contract.contract_hash},
            projection_contract=contract, typed=True,
        )
        if existing is None:
            scope.phase = PROJECTION_QUEUE_PHASE
            scope.save(update_fields=["phase"])
        scope = CollectionScopeRun.objects.select_for_update().get(pk=scope.pk)
        require(scope.projection_contract_id == contract.pk, "projection contract pin changed")
        _adopt_projection_queue(scope)
        _retain_projection_items(scope, ids)
        count = _projection_items(scope).filter(outcome="pending").count()
        scope.outcome = "pending" if count else "complete"
        scope.enumeration_complete = not count
        scope.execution_state = "pending" if count else "completed"
        scope.coverage_state = "pending" if count else "complete"
        scope.raw_count = count
        scope.save(update_fields=[
            "outcome", "enumeration_complete", "execution_state", "coverage_state", "raw_count",
        ])
        return scope


def _authorized_release_contracts(evidence):
    """Find currently active reviewed contracts which admit an exact capture."""
    from core.benchmark_attribution import enforce_source_collection
    from core.models import MetricCollectionContract

    source = evidence.run.job.source_id
    require(source in {"hf", "github"} and _eligible_evidence_owner(evidence, source)
            and evidence.run.job.operation == "release_acquisition", "exact release capture required")
    if source == "github":
        from core.product_release_acquisition import github_exact_observation_documents

        row, _, _ = github_exact_observation_documents(evidence)
        owner_id = row.get("owner", {}).get("id") if isinstance(row.get("owner"), dict) else None
        if type(owner_id) is not int or owner_id <= 0:
            return []
        namespace = str(owner_id)
        resource_id = evidence.source_identifier
        identifier_scope = "repository_id"
    else:
        namespace = evidence.source_identifier.split("/", 1)[0]
        resource_id = evidence.source_identifier.casefold()
        identifier_scope = "model"
    contracts = MetricCollectionContract.objects.filter(
        collectionjob__source_id=source, collectionjob__purpose="metric",
        collectionjob__authority_enabled=True, collectionjob__state="ready",
        mappings__purpose="metric", mappings__source_id=source,
        mappings__source_subject_kind="account", mappings__normalized_identifier=namespace.casefold(),
    ).distinct()
    accepted = []
    for contract in contracts:
        settings = contract.source_configuration.get(source, {})
        if settings.get("eligibility_policy") != SOURCE_STATISTICS_POLICY:
            continue
        try:
            enforce_source_collection(contract, source)
            publisher = _publisher(contract, source, namespace)
            mappings = list(contract.mappings.filter(
                purpose="metric", source_id=source, source_subject_kind="repository",
                identifier_scope__code=identifier_scope, normalized_identifier=resource_id,
            ).select_related("subject__product", "publisher_account", "identifier_scope"))
            if mappings:
                require(len(mappings) == 1, "ambiguous repository mapping")
                mapping = mappings[0]
                require(mapping.subject.subject_kind == "product"
                        and mapping.identifier_metadata.get("role") in {"dedicated_model", "dedicated_product"}
                        and mapping.publisher_account_id == publisher.subject.account_id
                        and (source != "hf" or (mapping.subject.product.repo_id or "").casefold()
                             == evidence.source_identifier.casefold()), "dedicated product mapping required")
                validate_statistics_mapping(
                    mapping.subject,
                    {"external_identifier": mapping.external_identifier,
                     "source_subject_kind": mapping.source_subject_kind,
                     "publisher_account_key": str(mapping.publisher_account_id),
                     "identifier_metadata": mapping.identifier_metadata},
                    source, contract.taxonomy_version,
                )
            else:
                require(settings.get("native_resources", True)
                        and resource_id not in settings.get("native_exclusions", []),
                        "repository outside native partition")
        except (ValueError, KeyError, TypeError):
            continue
        accepted.append(contract)
    return accepted


def enqueue_authorized_release_projection(claim, evidence):
    """Queue exact capture under an active, reviewed publisher contract.

    A dedicated reviewed mapping admits product attribution. Without one, an
    eligible native partition retains measurements on the repository alone.
    No contract or product mapping is guessed or created.
    """
    require(transaction.get_connection().in_atomic_block, "enqueue inside capture transaction")
    contracts = _authorized_release_contracts(evidence)
    for contract in contracts:
        enqueue_projection(claim, contract=contract, evidence_ids=[evidence.pk])
    return [str(contract.pk) for contract in contracts]


def retain_release_projection_followup(evidence):
    """Remember a saved capture until a reviewed measurement contract admits it."""
    require(transaction.get_connection().in_atomic_block, "retain follow-up inside transaction")
    source = evidence.run.job.source_id
    require(source in {"hf", "github"} and _eligible_evidence_owner(evidence, source)
            and evidence.run.job.operation == "release_acquisition", "exact release capture required")
    # A product-mapped projection is already a durable request, even if complete.
    # A native-only partition does not replace a later reviewed Product mapping.
    if any(
        _release_contract_is_dedicated(contract, evidence)
        and CollectionScopeRun.objects.filter(
            run_id=evidence.run_id, scope_kind=PROJECTION_ITEM_KIND,
            resource_observation=evidence, projection_contract=contract,
        ).exists()
        for contract in _authorized_release_contracts(evidence)
    ):
        return None
    scope, _ = CollectionScopeRun.objects.get_or_create(
        run_id=evidence.run_id, scope_kind="release_metric_followup", scope_key=str(evidence.pk),
        defaults={"resource_observation": evidence, "phase": "awaiting_authority",
                  "error_code": "awaiting_reviewed_contract", "raw_count": 1,
                  **_empty_scope_compatibility()},
    )
    require(scope.resource_observation_id == evidence.pk, "release follow-up identity changed")
    if scope.outcome in {"excluded", "failed"}:
        scope.outcome, scope.execution_state, scope.coverage_state = "pending", "pending", "pending"
        scope.error_code, scope.retry_at, scope.enumeration_complete = "awaiting_reviewed_contract", None, False
        scope.save(update_fields=["outcome", "execution_state", "coverage_state", "error_code",
                                  "retry_at", "enumeration_complete"])
    return scope


def _release_contract_is_dedicated(contract, evidence):
    source = evidence.run.job.source_id
    filters = {
        "purpose": "metric", "source_id": source, "source_subject_kind": "repository",
        "identifier_scope__code": "model" if source == "hf" else "repository_id",
        "normalized_identifier": evidence.source_identifier.casefold() if source == "hf" else evidence.source_identifier,
        "identifier_metadata__role__in": ["dedicated_model", "dedicated_product"],
        "subject__subject_kind": "product",
    }
    if source == "hf":
        filters["subject__product__repo_id__iexact"] = evidence.source_identifier
    return contract.mappings.filter(**filters).exists()


def recover_release_projection_followups(*, limit=25, observation_ids=None):
    """Recheck bounded saved captures after reviewed source authority changes.

    Missing authority is a waiting state, never a zero-valued measurement. No
    provider request, model call, new contract, or scheduler is created here.
    """
    from datetime import timedelta

    from django.db import DatabaseError
    from django.utils import timezone

    from core.product_release_acquisition import _has_eligible_claim

    require(type(limit) is int and 1 <= limit <= 100, "invalid follow-up budget")
    if observation_ids is not None:
        require(isinstance(observation_ids, (list, tuple)) and 1 <= len(observation_ids) <= 100
                and all(type(value) is int and value > 0 for value in observation_ids),
                "select 1..100 observation IDs")
    now = timezone.now()
    due = CollectionScopeRun.objects.filter(
        Q(retry_at__isnull=True) | Q(retry_at__lte=now),
        scope_kind="release_metric_followup", outcome="pending",
    )
    if observation_ids is not None:
        due = due.filter(resource_observation_id__in=observation_ids)
    ids = list(due.order_by("retry_at", "pk").values_list("pk", flat=True)[:limit])
    result = {"selected": len(ids), "queued": 0, "waiting": 0, "busy": 0, "excluded": 0, "failed": 0}
    for scope_id in ids:
        try:
            with transaction.atomic():
                followup = CollectionScopeRun.objects.select_for_update(skip_locked=True, of=("self",)).filter(
                    Q(retry_at__isnull=True) | Q(retry_at__lte=now),
                    pk=scope_id, scope_kind="release_metric_followup", outcome="pending",
                ).select_related("resource_observation__run__job").first()
                if followup is None:
                    result["busy"] += 1
                    continue
                evidence = followup.resource_observation
                require(evidence is not None and evidence.run_id == followup.run_id
                        and followup.scope_key == str(evidence.pk), "release follow-up ownership changed")
                origin = CollectionJob.objects.select_for_update(nowait=True).get(pk=evidence.run.job_id)
                if origin.active_run_id is not None:
                    followup.retry_at = now + timedelta(minutes=5)
                    followup.save(update_fields=["retry_at"])
                    result["busy"] += 1
                    continue
                if not _has_eligible_claim(origin):
                    followup.outcome, followup.execution_state = "excluded", "completed"
                    followup.coverage_state, followup.error_code = "unavailable", "release_excluded"
                    followup.enumeration_complete = True
                    followup.save(update_fields=["outcome", "execution_state", "coverage_state",
                                                "error_code", "enumeration_complete"])
                    result["excluded"] += 1
                    continue
                contracts = _authorized_release_contracts(evidence)
                if not contracts:
                    followup.retry_at = now + timedelta(hours=6)
                    followup.save(update_fields=["retry_at"])
                    result["waiting"] += 1
                    continue
                for contract in contracts:
                    key = str(contract.pk)
                    queue, _ = CollectionScopeRun.objects.get_or_create(
                        run_id=evidence.run_id, scope_kind="numeric_projection", scope_key=key,
                        defaults={"projection_contract": contract, "phase": PROJECTION_QUEUE_PHASE,
                                  **_empty_scope_compatibility()},
                    )
                    queue = CollectionScopeRun.objects.select_for_update().get(pk=queue.pk)
                    require(queue.projection_contract_id == contract.pk, "projection contract pin changed")
                    _adopt_projection_queue(queue)
                    _retain_projection_items(queue, [evidence.pk])
                    count = _projection_items(queue).filter(outcome="pending").count()
                    queue.outcome = "pending" if count else "complete"
                    queue.enumeration_complete = not count
                    queue.execution_state = "pending" if count else "completed"
                    queue.coverage_state = "pending" if count else "complete"
                    queue.raw_count = count
                    queue.save(update_fields=["outcome", "enumeration_complete", "execution_state",
                                              "coverage_state", "raw_count"])
                dedicated = any(_release_contract_is_dedicated(contract, evidence) for contract in contracts)
                followup.outcome = "complete" if dedicated else "pending"
                followup.execution_state = "completed" if dedicated else "pending"
                followup.coverage_state = "complete" if dedicated else "pending"
                followup.error_code = None if dedicated else "awaiting_product_mapping"
                followup.retry_at = None if dedicated else now + timedelta(hours=6)
                followup.enumeration_complete = dedicated
                followup.save(update_fields=["outcome", "execution_state", "coverage_state", "error_code",
                                            "retry_at", "enumeration_complete"])
                result["queued"] += 1
                result["waiting"] += int(not dedicated)
        except DatabaseError as error:
            cause = error.__cause__
            if getattr(cause, "sqlstate", None) != "55P03" and getattr(cause, "pgcode", None) != "55P03":
                raise
            # A concurrent acquisition owns this source; leave the marker intact.
            result["busy"] += 1
        except (ValueError, KeyError, TypeError):
            logger.exception("Invalid release measurement follow-up %s", scope_id)
            CollectionScopeRun.objects.filter(pk=scope_id, outcome="pending").update(
                outcome="failed", execution_state="failed", coverage_state="unavailable",
                error_code="invalid_release_followup", retry_at=None,
            )
            result["failed"] += 1
    remaining = CollectionScopeRun.objects.filter(
        Q(retry_at__isnull=True) | Q(retry_at__lte=timezone.now()),
        scope_kind="release_metric_followup", outcome="pending",
    )
    if observation_ids is not None:
        remaining = remaining.filter(resource_observation_id__in=observation_ids)
    result["due_remaining"] = remaining.exists()
    return result


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
        .prefetch_related("run__job__numeric_contract", "numeric_selections")
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
        scope = _result_parent(claim, run, contract)
        existing_outputs = dict(CollectionObservation.objects.filter(
            observation_key__in=[data["observation_key"] for data, _ in prepared],
            run__job__contract_id=contract.pk, run__job__source_id=source,
            run__job__purpose="metric",
        ).values_list("pk", "observation_key"))
        before_values = {key: set() for key in existing_outputs.values()}
        for observation_id, metric_id in MetricValue.objects.filter(observation_id__in=existing_outputs).values_list("observation_id", "source_metric_id"):
            before_values[existing_outputs[observation_id]].add(metric_id)
        observations, accounting = commit_prepared_rows(run, prepared, reuse_snapshots=True)
        _retain_results(scope, selected, prepared, observations, accounting, before_values, rejections, terminal_ids)
        projection = projection_report(run)
        checkpoint_scope(
            claim, scope_kind="numeric_projection", scope_key="saved-evidence", typed=True,
            ownership={"contract_hash": contract.contract_hash}, projection_contract=contract,
            cursor=cursor, enumeration_complete=complete,
            outcome="complete" if complete else "pending", raw_count=projection["selected_resources"],
        )
        missing = projection["admitted_resources"] + projection["terminal_resources"] != projection["selected_resources"]
        return finish_run(
            claim, status="success" if complete and not missing else "partial", typed=True,
            physical_accounting_complete=True, selected_count=projection["selected_resources"],
            success_count=projection["admitted_resources"], request_count=0,
        )


def _evidence_bytes(evidence):
    listing, dimensions, metadata = _evidence_documents(evidence)
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
        from core.collection_capture import archive_document

        with fenced_run(claim) as (job, failed_run):
            scope = _result_parent(claim, failed_run, job.contract)
            scope.legacy_archive = archive_document(
                json.dumps({"version": 1, "projection_error": str(exc)},
                           sort_keys=True, separators=(",", ":"), allow_nan=False).encode(),
                encoding="selected-json-canonical-v1", capture_kind="numeric_projection_evidence",
            )
            scope.outcome = "failed"
            scope.execution_state = "failed"
            scope.coverage_state = "unavailable"
            scope.save(update_fields=["legacy_archive", "outcome", "execution_state", "coverage_state"])
        finish_run(
            claim,
            status="failed",
            error_code="invalid_numeric_projection",
            typed=True, physical_accounting_complete=True, request_count=0,
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
    claim = claim_job(job.pk, typed=True)
    with fenced_run(claim) as (_, run):
        previous = run.scopes.filter(
            scope_kind="numeric_projection", scope_key="saved-evidence"
        ).first()
        cursor = int(previous.cursor) if previous and previous.cursor else 0
    allowed_origin = Q(run__job__purpose="catalog")
    if job.source_id in {"hf", "github"}:
        allowed_origin |= Q(
            run__job__purpose="content", run__job__operation="release_acquisition",
            projection_kind=f"{job.source_id}-release-exact-v1",
        )
    selected = CollectionObservation.objects.filter(
        Q(run_id__in=runs) | Q(run__job_id__in=jobs),
        allowed_origin,
        run__job__source_id=job.source_id,
        pk__gt=cursor,
        source_subject_kind__in=["repository", "account", "model", "aggregate"],
        status="ok",
    ).order_by("pk")
    if job.source_id == "github":
        selected = selected.filter(
            Q(source_subject_kind="account")
            | Q(observation_kind__in=["repository", "repository_access", "release_asset", "github_release_exact"])
        )
    if job.source_id in {"openrouter", "arena"}:
        selected = selected.filter(observation_kind="publication_row")
    ids, consumed, complete = [], 0, True
    last_processed = cursor
    evidence_rows = selected.select_related("legacy_archive").prefetch_related(
        "run__job__numeric_contract", "numeric_selections",
    ).only(
        "id", "run_id", "numeric_fields_explicit",
        "legacy_archive__body", "legacy_archive__content_sha256",
    ).iterator(chunk_size=100)
    for evidence in evidence_rows:
        if monotonic() >= deadline:
            complete = False
            break
        from core.collection_numeric_selection import numeric_fields

        if job.source_id == "hf" and numeric_fields(evidence) == []:
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

    with _projection_origin(catalog_job_id, origin_claim) as origin:
        validate_job(origin)
        require(_eligible_projection_origin(origin), "supported projection origin required")
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
        .select_related("run__job", "projection_contract")
        .order_by("pk")
    )
    for scope in pending.iterator():
        if selected_count >= limits["items"] or remaining_seconds() <= 0:
            break
        with _projection_origin(catalog_job_id, origin_claim):
            scope = CollectionScopeRun.objects.select_for_update(of=("self",)).select_related(
                "run__job", "projection_contract",
            ).get(pk=scope.pk)
            _adopt_projection_queue(scope)
        if scope.outcome != "pending":
            continue
        contract = scope.projection_contract
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
            pk__in=_projection_items(scope).filter(outcome="pending").values(
                "resource_observation_id",
            ),
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
        claim = claim_job(job.pk, typed=True)
        run = project_evidence(claim, ids, deadline=monotonic() + remaining_seconds())
        projection = projection_report(run)
        rejected = set(run.scopes.filter(
            scope_kind=PROJECTION_RESULT_KIND, outcome="rejected",
        ).values_list("resource_observation_id", flat=True))
        committed = set(ids) - rejected
        # Fence the acquisition before locking its queue row, matching enqueue's
        # job/run/scope order. An independent numeric commit remains valid when
        # this fence fails; its successor will reuse that immutable snapshot.
        with _projection_origin(catalog_job_id, origin_claim):
            current = CollectionScopeRun.objects.select_for_update().get(pk=scope.pk)
            _adopt_projection_queue(current)
            _projection_items(current).filter(
                resource_observation_id__in=committed, outcome="pending",
            ).update(
                outcome="complete", enumeration_complete=True,
                execution_state="completed", coverage_state="complete",
            )
            remaining = _projection_items(current).filter(outcome="pending").exists()
            current.outcome = "pending" if remaining else "complete"
            current.enumeration_complete = not remaining
            current.execution_state = "pending" if remaining else "completed"
            current.coverage_state = "partial" if remaining else "complete"
            current.cursor = str(max(committed)) if committed else current.cursor
            current.save(update_fields=[
                "outcome", "enumeration_complete", "execution_state", "coverage_state", "cursor",
            ])
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
    result["pending_resources"] = 0
    for scope in CollectionScopeRun.objects.filter(
        run__job=origin, scope_kind="numeric_projection", outcome="pending",
    ):
        result["pending_resources"] += (
            _projection_items(scope).filter(outcome="pending").count()
            if scope.phase == PROJECTION_QUEUE_PHASE else len(_legacy_projection_ids(scope))
        )
    return result
