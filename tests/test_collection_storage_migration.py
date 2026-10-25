"""The collection archive copy is exact, repeatable, and detects live changes."""

import pytest

from core.collection_capture import read_document
from core.collection_storage_migration import (
    archive_legacy_batch,
    project_benchmark_provenance_batch,
    project_run_ingestion_mode,
    provenance_mismatch_counts,
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


def test_benchmark_provenance_copy_is_bounded_and_repeatable():
    run, _, scope = execution()
    run.source_metadata = {"ingestion_mode": "direct"}
    run.save(update_fields=["source_metadata"])
    observation = CollectionObservation.objects.create(
        run=run,
        scope_run=scope,
        source_identifier="historical",
        source_subject_kind="model",
        observation_key="b" * 64,
        source_metadata={
            "history_basis": "reconstructed_current_relationships",
            "secondary_source": True,
            "publication_complete": False,
            "reconstruction_date": "2026-10-24",
        },
    )
    assert provenance_mismatch_counts() == (1, 1)
    assert project_run_ingestion_mode() == 1
    first = project_benchmark_provenance_batch(
        after_id=observation.pk - 1, batch_size=1
    )
    assert (first.last_id, first.scanned, first.updated) == (observation.pk, 1, 1)
    assert project_benchmark_provenance_batch(
        after_id=observation.pk - 1, batch_size=1
    ).updated == 0
    run.refresh_from_db()
    observation.refresh_from_db()
    assert run.direct_ingestion is True
    assert observation.history_reconstructed is True
    assert observation.secondary_source is True
    assert observation.publication_complete is False
    assert observation.reconstruction_date.isoformat() == "2026-10-24"
    assert provenance_mismatch_counts() == (0, 0)

    observation.source_metadata["reconstruction_date"] = "2026-10-23"
    observation.save(update_fields=["source_metadata"])
    assert provenance_mismatch_counts() == (0, 1)
    assert project_benchmark_provenance_batch(
        after_id=observation.pk - 1, batch_size=1
    ).updated == 1
    observation.refresh_from_db()
    assert observation.reconstruction_date.isoformat() == "2026-10-23"
    assert provenance_mismatch_counts() == (0, 0)
