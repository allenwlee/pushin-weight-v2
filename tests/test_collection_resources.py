"""Typed observation facts survive readers reprocessing captured evidence."""

import pytest

from core.collection_resources import observation_fact_values, project_observation_facts
from core.models import CollectionObservation
from tests.test_collection_relational_storage import execution

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def publication_observation(*, metadata, dimensions, source="openrouter"):
    from django.utils import timezone

    from core.models import CollectionRun, DataSource
    from tests.collection_fixtures import evidence_job

    DataSource.objects.get_or_create(id=source, defaults={"name": source, "source_type": "benchmark"})
    run = CollectionRun.objects.create(
        job=evidence_job(source_id=source), ingestion_key="e" * 64,
        status="success", completed_at=timezone.now(),
    )
    return CollectionObservation.objects.create(
        run=run, source_identifier="vendor/model", source_subject_kind="model",
        observation_key="d" * 64, dimensions=dimensions, source_metadata=metadata,
    )


def test_replaying_typed_observation_does_not_erase_facts_when_old_json_is_absent():
    run, _, scope = execution()
    observation = CollectionObservation.objects.create(
        run=run, scope_run=scope, source_identifier="publisher/repo",
        source_subject_kind="repository", observation_key="a" * 64,
        dimensions={"kind": "repository", "config": "default", "category": "code"},
        source_metadata={
            "revision": "original-revision", "definitions_sha256": "b" * 64,
            "publisher_mapping_hash": "c" * 64, "period_status": "complete",
            "row_semantic_hash": "d" * 64, "historical_public_visibility_proven": True,
            "history_basis": "reconstructed_current_relationships",
            "secondary_source": True, "publication_complete": False,
            "reconstruction_date": "2026-09-01", "archive_snapshot_date": "2026-09-02",
            "source_record_date": "2026-09-01T01:02:03Z",
            "original_retrieved_at": "2026-09-02T01:02:03Z",
        },
        listing={"id": 42, "private": False},
    )
    fields = list(observation_fact_values(observation))
    project_observation_facts(observation)
    before = {field: getattr(observation, field) for field in fields}
    CollectionObservation.objects.filter(pk=observation.pk).update(
        dimensions={}, source_metadata={}, listing={},
    )
    observation.refresh_from_db()
    project_observation_facts(observation)
    assert {field: getattr(observation, field) for field in fields} == before
    observation.dimensions = {"config": None}
    project_observation_facts(observation)
    assert observation.config_key is None
    assert observation.provider_revision == "original-revision"


def test_hf_commit_projection_repairs_only_missing_revision_and_refuses_conflicts():
    from django.utils import timezone

    from core.collection_resources import snapshot_resource
    from core.models import CollectionResourceSnapshot, CollectionRun, DataSource
    from tests.collection_fixtures import evidence_job

    DataSource.objects.get_or_create(id="hf", defaults={"name": "HF", "source_type": "benchmark"})
    run = CollectionRun.objects.create(
        job=evidence_job(source_id="hf"), ingestion_key="c" * 64, status="success",
        completed_at=timezone.now(),
    )
    observation = CollectionObservation.objects.create(
        run=run, source_identifier="publisher/repository", source_subject_kind="repository",
        observation_key="a" * 64, observation_kind="hf_commits", provider_revision="head-revision",
        listing={"id": "commit-revision"},
    )
    snapshot = CollectionResourceSnapshot.objects.create(
        observation=observation, resource_kind="hf_commits", native_identifier=observation.source_identifier,
    )
    assert snapshot_resource(observation).revision == "commit-revision"
    observation.refresh_from_db()
    assert observation.provider_revision == "head-revision"
    assert snapshot_resource(observation).revision == "commit-revision"
    observation.listing = {"id": "changed-commit"}
    with pytest.raises(ValueError, match="conflicts with captured evidence"):
        snapshot_resource(observation)
    snapshot.refresh_from_db()
    assert snapshot.revision == "commit-revision"
    observation.listing = {"id": 123}
    with pytest.raises(ValueError, match="HF commit revision is missing"):
        snapshot_resource(observation)


@pytest.mark.parametrize("key", ["numeric_snapshot_identity", "snapshot_identity"])
def test_publication_identity_projects_nested_coordinates_without_inventing_publication_date(key):
    from datetime import date

    observation = publication_observation(
        metadata={key: {
            "native_identifier": "vendor/model", "dataset_id": "vendor/archive",
            "period": "2026-09-03", "config": "daily", "category": "overall", "revision": "r1",
        }},
        dimensions={"kind": "publication_row", "period": "2026-09-03", "config": "daily"},
    )
    original_key = observation.observation_key
    project_observation_facts(observation)
    assert observation.provider_revision == "r1"
    assert observation.config_key == "daily"
    assert observation.category_key == "overall"
    assert observation.source_record_date == date(2026, 9, 3)
    assert observation.published_date is None and observation.published_at is None
    assert observation.observation_key == original_key
    observation.dimensions, observation.source_metadata = {}, {}
    project_observation_facts(observation)
    assert observation.provider_revision == "r1"
    assert observation.category_key == "overall"
    assert observation.source_record_date == date(2026, 9, 3)


def test_ordinary_openrouter_row_keeps_its_source_day_without_publication_claim():
    from datetime import date

    observation = publication_observation(metadata={}, dimensions={"date": "2026-09-03"})
    project_observation_facts(observation)
    assert observation.source_record_date == date(2026, 9, 3)
    assert observation.published_date is None and observation.published_at is None


@pytest.mark.parametrize("field,value", [
    ("revision", "conflict"), ("config", "conflict"), ("category", "conflict"),
    ("period", "2026-09-04"), ("native_identifier", "different/model"),
])
def test_conflicting_publication_coordinates_are_rejected_before_projection(field, value):
    observation = publication_observation(
        metadata={"numeric_snapshot_identity": {
            "native_identifier": "vendor/model", "period": "2026-09-03",
            "config": "daily", "category": "overall", "revision": "r1", field: value,
        }},
        dimensions={"date": "2026-09-03", "config": "daily", "category": "overall", "revision": "r1"},
    )
    with pytest.raises(ValueError, match="conflicting publication"):
        project_observation_facts(observation)
    observation.refresh_from_db()
    assert observation.provider_revision is None
    assert observation.source_record_date is None


def test_publication_snapshot_requires_an_object_before_any_fact_is_written():
    observation = publication_observation(
        metadata={"snapshot_identity": []}, dimensions={"date": "2026-09-03"},
    )
    with pytest.raises(TypeError, match="invalid publication snapshot identity"):
        project_observation_facts(observation)
    observation.refresh_from_db()
    assert observation.source_record_date is None
