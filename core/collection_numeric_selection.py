"""HF capture selection, distinct from projected numbers and metric gaps."""

from dataclasses import dataclass
from uuid import UUID

from django.db import connection, transaction

from core.benchmark_metric_identity import SOURCE_STATISTICS_POLICY, definition_snapshot
from core.collection_capture import observation_object_documents
from core.collection_jobs import validate_job
from core.measurement_taxonomy import digest, require
from core.models import (
    CollectionJob,
    CollectionObservation,
    CollectionObservationMetricSelection,
    CollectionRun,
    MetricCollectionContract,
    SourceMetric,
)

# This is the existing first-response selection order, not a new metric catalogue.
HF_SELECTION_FIELDS = ("downloads", "likes", "downloadsAllTime", "trendingScore")


def _legacy_fields(observation, metadata=None):
    metadata = observation_object_documents(observation)[2] if metadata is None else metadata
    if "numeric_fields" not in metadata:
        return None
    fields = metadata["numeric_fields"]
    require(
        type(fields) is list and all(type(field) is str for field in fields)
        and len(fields) == len(set(fields)) and set(fields) <= set(HF_SELECTION_FIELDS),
        "invalid HF numeric field selection",
    )
    return fields


def _pinned_definitions(contract):
    if hasattr(contract, "_hf_selection_definitions"):
        return contract._hf_selection_definitions
    settings = contract.source_configuration.get("hf", {})
    policy = settings.get("eligibility_policy")
    require(policy in (None, "text-benchmark-v1", SOURCE_STATISTICS_POLICY),
            "unsupported HF capture eligibility policy")
    frozen_contract = {
        "schema_version": contract.schema_version,
        "taxonomy_version": str(contract.taxonomy_version_id),
        "catalog_hash": contract.catalog_hash, "mapping_hash": contract.mapping_hash,
        "methodology_hash": contract.methodology_hash,
        "source_configuration": contract.source_configuration,
        "methodology": contract.methodology,
    }
    if policy == SOURCE_STATISTICS_POLICY:
        frozen_contract["eligibility_policy"] = SOURCE_STATISTICS_POLICY
    require(digest(frozen_contract) == contract.contract_hash, "capture contract hash changed")
    frozen = settings["definitions"]
    definitions = SourceMetric.objects.in_bulk([row["id"] for row in frozen])
    require(len(definitions) == len(frozen), "missing capture metric definition")
    wires = {}
    for row in frozen:
        definition = definitions[row["id"]]
        require(
            definition.source_id == "hf" and definition_snapshot(definition) == row
            and definition.version == settings.get("metric_versions", {}).get(definition.metric_key, 1),
            "pinned capture metric definition changed",
        )
        wire = definition.definition_metadata.get("wire_field")
        require(wire not in wires, "ambiguous capture wire field")
        wires[wire] = definition
    require({row["metric_key"] for row in frozen} == set(settings["metrics"]),
            "capture selected metrics differ from frozen definitions")
    contract._hf_selection_definitions = wires
    return wires


def _job_contract(job, *, write=False, verify_only=False):
    require(job.source_id == "hf" and job.purpose == "catalog", "HF catalog owner required")
    validate_job(job)
    if job.instruction_version == 1:
        pin = job.definition.get("scope", {}).get("numeric_contract_id")
        identifier = UUID(str(pin)) if pin is not None else None
        require(job.numeric_contract_id in (None, identifier), "capture contract pin conflict")
    else:
        identifier = job.numeric_contract_id
    if identifier is None:
        return None, False
    contract = MetricCollectionContract.objects.get(pk=identifier)
    _pinned_definitions(contract)
    missing = job.numeric_contract_id is None
    require(not verify_only or not missing, "capture contract pin is not projected")
    if write and missing:
        job.numeric_contract = contract
        job.save(update_fields=["numeric_contract"])
    return contract, missing


def numeric_fields(observation, *, legacy_metadata=None):
    """None is implicit selection; [] is a verified explicit empty selection."""
    if observation.numeric_fields_explicit is None:
        return _legacy_fields(observation, legacy_metadata)
    require(observation.run.job.source_id == "hf" and observation.run.job.purpose == "catalog",
            "typed numeric selection has a non-HF catalog owner")
    selections = list(observation.numeric_selections.all())
    if not observation.numeric_fields_explicit:
        require(not selections, "implicit capture has explicit metric selections")
        return None
    if not selections:
        return []
    job = observation.run.job
    require(job.numeric_contract_id is not None, "selected capture has no typed contract pin")
    pinned = _pinned_definitions(job.numeric_contract)
    by_id = {definition.pk: wire for wire, definition in pinned.items()}
    require(all(row.source_metric_id in by_id for row in selections),
            "selected metric differs from pinned capture definition")
    fields = {by_id[row.source_metric_id] for row in selections}
    require(fields <= set(HF_SELECTION_FIELDS), "unsupported selected HF wire field")
    return [wire for wire in HF_SELECTION_FIELDS if wire in fields]


def _apply_selection(observation, fields, contract, *, verify_only=False):
    explicit = fields is not None
    definitions = _pinned_definitions(contract) if contract is not None else {}
    require(not fields or contract is not None, "selected capture has no frozen contract")
    require(all(field in definitions for field in fields or ()), "field missing from capture contract")
    expected = {definitions[field].pk for field in fields or ()}
    actual = set(observation.numeric_selections.values_list("source_metric_id", flat=True))
    marker = observation.numeric_fields_explicit
    if marker is not None:
        require(marker == explicit and actual == expected, "typed capture selection conflicts with evidence")
        return False
    require(not verify_only, "capture selection is not projected")
    require(actual <= expected, "unverified capture selection conflicts with evidence")
    CollectionObservationMetricSelection.objects.bulk_create([
        CollectionObservationMetricSelection(observation=observation, source_metric_id=identifier)
        for identifier in expected - actual
    ])
    observation.numeric_fields_explicit = explicit
    observation.save(update_fields=["numeric_fields_explicit"])
    if hasattr(observation, "_prefetched_objects_cache"):
        observation._prefetched_objects_cache.pop("numeric_selections", None)
    return True


@transaction.atomic
def adopt_numeric_selection(observation):
    """Called in the capture transaction before its checkpoint is published."""
    if observation.numeric_fields_explicit is not None:
        return
    job = CollectionJob.objects.select_for_update().get(pk=observation.run.job_id)
    if job.source_id != "hf" or job.purpose != "catalog":
        return
    CollectionRun.objects.select_for_update().get(pk=observation.run_id)
    owner = CollectionObservation.objects.select_for_update().get(pk=observation.pk)
    require(owner.run_id == observation.run_id, "capture owner changed")
    contract, _ = _job_contract(job, write=True)
    _apply_selection(owner, _legacy_fields(owner), contract)
    observation.numeric_fields_explicit = owner.numeric_fields_explicit


@dataclass(frozen=True)
class JobPinBatch:
    last_id: str | None
    scanned: int
    updated: int
    exhausted: bool


@dataclass(frozen=True)
class SelectionBatch:
    last_id: int
    scanned: int
    updated: int
    implicit: int
    explicit_empty: int
    explicit_selected: int
    selection_rows: int
    exhausted: bool


def _batch_limits(batch_size):
    require(type(batch_size) is int and 1 <= batch_size <= 200, "invalid selection batch size")
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout = '5s'")
        cursor.execute("SET LOCAL statement_timeout = '30s'")


@transaction.atomic
def project_hf_numeric_job_pins_batch(*, after_id=None, batch_size=100, verify_only=False):
    """Copy only the already frozen numeric contract, without changing job identity."""
    _batch_limits(batch_size)
    query = CollectionJob.objects.filter(source_id="hf", purpose="catalog").order_by("pk")
    if after_id is not None:
        query = query.filter(pk__gt=UUID(str(after_id)))
    if not verify_only:
        query = query.select_for_update()
    jobs = list(query[:batch_size])
    updated = 0
    for job in jobs:
        _, missing = _job_contract(job, write=not verify_only, verify_only=verify_only)
        updated += int(missing)
    return JobPinBatch(str(jobs[-1].pk) if jobs else after_id, len(jobs), updated, len(jobs) < batch_size)


@transaction.atomic
def project_hf_numeric_selections_batch(*, after_id=0, batch_size=100, verify_only=False):
    """Copy/compare every HF catalog capture, including implicit and empty states."""
    _batch_limits(batch_size)
    require(type(after_id) is int and after_id >= 0, "invalid selection cursor")
    query = CollectionObservation.objects.filter(
        pk__gt=after_id, run__job__source_id="hf", run__job__purpose="catalog",
    ).order_by("pk")
    owners = list(query.values_list("pk", "run_id", "run__job_id")[:batch_size])
    jobs = CollectionJob.objects.filter(pk__in={row[2] for row in owners}).order_by("pk")
    if not verify_only:
        jobs = jobs.select_for_update()
    contracts = {}
    for job in jobs:
        # Job pin preparation is a separate bounded step and is independently verified.
        contracts[job.pk], _ = _job_contract(job, verify_only=True)
    if not verify_only:
        list(CollectionRun.objects.select_for_update().filter(
            pk__in={row[1] for row in owners},
        ).order_by("pk").values_list("pk", flat=True))
    observations = query.filter(pk__in=[row[0] for row in owners]).select_related("run", "legacy_archive")
    if not verify_only:
        observations = observations.select_for_update(of=("self",))
    counts = {"implicit": 0, "explicit_empty": 0, "explicit_selected": 0}
    updated = selection_rows = 0
    expected_owners = {row[0]: row[1:] for row in owners}
    for observation in observations:
        require((observation.run_id, observation.run.job_id) == expected_owners[observation.pk],
                "selection owner moved while locking")
        fields = _legacy_fields(observation)
        counts["implicit" if fields is None else "explicit_selected" if fields else "explicit_empty"] += 1
        selection_rows += len(fields or ())
        updated += int(_apply_selection(
            observation, fields, contracts[observation.run.job_id], verify_only=verify_only,
        ))
    return SelectionBatch(
        owners[-1][0] if owners else after_id, len(owners), updated,
        **counts, selection_rows=selection_rows, exhausted=len(owners) < batch_size,
    )


def hf_numeric_selection_integrity_counts():
    """Global complements to the bounded field-by-field historical comparison."""
    selections = CollectionObservationMetricSelection.objects.all()
    return {
        "unprojected": CollectionObservation.objects.filter(
            run__job__source_id="hf", run__job__purpose="catalog", numeric_fields_explicit__isnull=True,
        ).count(),
        "invalid_selection_owners": selections.exclude(
            observation__run__job__source_id="hf", observation__run__job__purpose="catalog",
            observation__numeric_fields_explicit=True, source_metric__source_id="hf",
            observation__run__job__numeric_contract__isnull=False,
        ).count(),
    }
