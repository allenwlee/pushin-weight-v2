"""Catalog facts are copied without inventing transport or changing known history."""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from core.collection_resources import resource_snapshot_values
from core.collection_storage_migration import project_resource_snapshots_batch
from core.models import CollectionObservation, CollectionResourceSnapshot
from tests.test_collection_resources import publication_observation

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def captured_commit():
    row = publication_observation(
        source="hf", metadata={"revision": "requested-head"}, dimensions={"kind": "hf_commits"},
    )
    row.listing = {"id": "selected-commit", "date": "2026-09-20T12:00:00Z"}
    row.provider_revision = "requested-head"
    row.save(update_fields=["listing", "provider_revision"])
    return row


def test_missing_resource_and_commit_revision_copy_is_exact_repeatable_and_bounded():
    first = captured_commit()
    second = CollectionObservation.objects.create(
        run=first.run, source_identifier=first.source_identifier, source_subject_kind="repository",
        observation_key="b" * 64, dimensions={"kind": "hf_commits"},
        listing={"id": "second-commit"},
    )
    snapshot = CollectionResourceSnapshot.objects.create(
        observation=first, **{**resource_snapshot_values(first), "revision": None},
    )
    before = list(CollectionObservation.objects.order_by("pk").values())
    with pytest.raises(ValueError, match="not projected"):
        project_resource_snapshots_batch(verify_only=True)
    with CaptureQueriesContext(connection) as queries:
        result = project_resource_snapshots_batch(batch_size=1)
    assert (result.last_id, result.scanned, result.updated) == (first.pk, 1, 1)
    assert not any('"raw_payload"' in row["sql"] or '"definition"' in row["sql"] for row in queries)
    snapshot.refresh_from_db()
    assert snapshot.revision == "selected-commit"
    assert not CollectionResourceSnapshot.objects.filter(pk=second.pk).exists()
    assert project_resource_snapshots_batch(after_id=first.pk).updated == 1
    assert project_resource_snapshots_batch().updated == 0
    assert project_resource_snapshots_batch(verify_only=True).scanned == 2
    assert list(CollectionObservation.objects.order_by("pk").values()) == before
    assert first.run.attempts.count() == 0


def test_resource_copy_refuses_known_revision_conflict_without_rewriting_it():
    row = captured_commit()
    snapshot = CollectionResourceSnapshot.objects.create(
        observation=row, **{**resource_snapshot_values(row), "revision": "known-different"},
    )
    with pytest.raises(ValueError, match="typed resource fact conflicts: revision"):
        project_resource_snapshots_batch()
    snapshot.refresh_from_db()
    assert snapshot.revision == "known-different"


def test_resource_copy_refuses_malformed_native_commit_identity_before_creation():
    row = captured_commit()
    CollectionObservation.objects.filter(pk=row.pk).update(listing={"id": 123})
    with pytest.raises(ValueError, match="commit revision is missing"):
        project_resource_snapshots_batch()
    assert not CollectionResourceSnapshot.objects.exists()


def test_verification_does_not_register_missing_vocabulary():
    from core.models import ModelTask

    row = captured_commit()
    CollectionObservation.objects.filter(pk=row.pk).update(
        listing={"id": "selected-commit", "pipeline_tag": "rg6-copy-fixture"},
    )
    with CaptureQueriesContext(connection) as queries, pytest.raises(
        ValueError, match="unregistered source vocabulary code",
    ):
        project_resource_snapshots_batch(verify_only=True)
    assert not any("INSERT INTO" in query["sql"] for query in queries)
    assert not ModelTask.objects.filter(code="rg6-copy-fixture").exists()
    assert not CollectionResourceSnapshot.objects.exists()
    assert project_resource_snapshots_batch().updated == 1
    assert ModelTask.objects.filter(code="rg6-copy-fixture", data_source_id="hf").count() == 1
    assert project_resource_snapshots_batch(verify_only=True).updated == 0
