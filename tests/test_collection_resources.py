"""Typed observation facts survive readers reprocessing captured evidence."""

import pytest

from core.collection_resources import observation_fact_values, project_observation_facts
from core.models import CollectionObservation
from tests.test_collection_relational_storage import execution

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


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
