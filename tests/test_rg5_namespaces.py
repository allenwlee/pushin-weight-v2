"""Namespace identity follows captured evidence, not the matching coordinator."""

import pytest
from django.db import IntegrityError, transaction

from core.collection_jobs import register_job
from core.identifier_namespaces import namespace_id, target_namespace_id
from core.models import (
    CollectionObservation,
    CollectionRun,
    DataSource,
    SourceSubjectMapping,
)
from tests.collection_fixtures import evidence_job
from tests.test_benchmark_download_persistence import configured

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def test_matching_target_uses_evidence_source_and_keeps_instruction_hash_stable():
    contract = configured()
    mapping = contract.mappings.get()
    run = CollectionRun.objects.create(
        job=evidence_job(source_id="hf"), status="pending", ingestion_key="9" * 64
    )
    observation = CollectionObservation.objects.create(
        run=run,
        source_identifier="lab/Model",
        source_subject_kind="repository",
        observation_key="a" * 64,
    )
    coordinator, _ = DataSource.objects.get_or_create(
        pk="arena", defaults={"name": "Arena", "source_type": "benchmark"}
    )
    target = {
        "target_key": "candidate",
        "target_kind": "match_candidate",
        "target_role": "selected",
        "resolution_state": "unresolved",
        "gap_reason": "awaiting_review",
        "evidence_observation_id": observation.pk,
        "identifier_scope": "model",
    }
    arguments = {
        "job_key": "rg5-matcher",
        "source": coordinator,
        "purpose": "catalog",
        "operation": "model_inventory",
        "mode": "historical",
        "definition": {"version": 2, "options": {}},
        "settings": {
            "owner_kind": "source",
            "schedule_kind": "manual",
            "schedule_driver": "manual",
            "max_requests": 1,
            "max_bytes": 1000,
            "max_seconds": 10,
            "max_items": 1,
        },
        "targets": [target],
    }
    job = register_job(**arguments)
    retained = job.targets.get().identifier_scope
    assert (retained.data_source_id, retained.subject_kind, retained.code) == (
        "hf",
        "model",
        "model",
    )
    again = register_job(**arguments)
    assert (again.pk, again.definition_sha256, again.relational_sha256) == (
        job.pk,
        job.definition_sha256,
        job.relational_sha256,
    )
    assert job.scope is not None
    wrong_kind = namespace_id("hf", "account", "model")
    with pytest.raises(IntegrityError), transaction.atomic():
        SourceSubjectMapping.objects.filter(pk=mapping.pk).update(
            identifier_scope_id=wrong_kind
        )
    wrong_source = namespace_id("arena", "repository", "model")
    with pytest.raises(IntegrityError), transaction.atomic():
        SourceSubjectMapping.objects.filter(pk=mapping.pk).update(
            identifier_scope_id=wrong_source
        )
    with pytest.raises(ValueError, match="pinned"):
        target_namespace_id({"identifier_scope": "model"})


def test_resource_and_namespace_references_pin_their_parent_source():
    from core.models import CollectionResourceSnapshot
    from core.source_vocabulary import reference_id

    configured()
    DataSource.objects.get_or_create(
        pk="github", defaults={"name": "GitHub", "source_type": "model_adoption"}
    )
    hf_run = CollectionRun.objects.create(
        job=evidence_job(source_id="hf"), status="pending", ingestion_key="b" * 64
    )
    github_run = CollectionRun.objects.create(
        job=evidence_job(source_id="github"), status="pending", ingestion_key="c" * 64
    )
    observation = CollectionObservation.objects.create(
        run=hf_run,
        source_identifier="lab/model",
        source_subject_kind="repository",
        observation_key="d" * 64,
    )
    snapshot = CollectionResourceSnapshot.objects.create(
        observation=observation,
        resource_kind="repository",
        native_identifier="lab/model",
        library_name_id=reference_id("software_libraries", "hf", "transformers"),
    )
    with pytest.raises(IntegrityError, match="pinned"), transaction.atomic():
        CollectionObservation.objects.filter(pk=observation.pk).update(run=github_run)
    with pytest.raises(IntegrityError, match="pinned"), transaction.atomic():
        CollectionRun.objects.filter(pk=hf_run.pk).update(job=github_run.job)
    other = reference_id("software_libraries", "github", "transformers")
    with pytest.raises(IntegrityError), transaction.atomic():
        CollectionResourceSnapshot.objects.filter(pk=snapshot.pk).update(
            library_name_id=other
        )
