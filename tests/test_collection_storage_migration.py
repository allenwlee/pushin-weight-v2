"""The collection archive copy is exact, repeatable, and detects live changes."""

import pytest

from core.collection_capture import read_document
from core.collection_storage_migration import (
    archive_legacy_batch,
    stale_legacy_archive_count,
)
from core.models import CollectionObservation
from tests.test_collection_relational_storage import execution

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def test_legacy_documents_are_archived_once_and_changed_rows_are_reconciled():
    run, _, scope = execution()
    run.source_metadata = {"ingestion_mode": "direct"}
    run.raw_payload = {"items": [{"id": "one"}]}
    run.save(update_fields=["source_metadata", "raw_payload"])
    scope.ownership = {"query": "example"}
    scope.save(update_fields=["ownership"])
    observation = CollectionObservation.objects.create(
        run=run,
        scope_run=scope,
        source_identifier="one",
        source_subject_kind="model",
        observation_key="a" * 64,
        dimensions={"config": "text"},
        source_metadata={"history_basis": "reported"},
    )

    for table in (
        "collection_runs", "collection_scope_runs", "collection_observations"
    ):
        assert archive_legacy_batch(table).archived == 1
        assert archive_legacy_batch(table).archived == 0
        assert stale_legacy_archive_count(table) == 0

    run.refresh_from_db()
    scope.refresh_from_db()
    observation.refresh_from_db()
    assert read_document(run.legacy_archive)["raw_payload"] == {
        "items": [{"id": "one"}]
    }
    assert read_document(scope.legacy_archive)["ownership"] == {"query": "example"}
    assert read_document(observation.legacy_archive)["dimensions"] == {
        "config": "text"
    }
    run.report = {"retry": 2}
    run.save(update_fields=["report"])
    assert stale_legacy_archive_count("collection_runs") == 1
    assert archive_legacy_batch("collection_runs", repair_stale=True).archived == 1
    run.refresh_from_db()
    assert read_document(run.legacy_archive)["report"] == {"retry": 2}
    assert stale_legacy_archive_count("collection_runs") == 0
