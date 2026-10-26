"""Historical coordinate copies preserve native identity and unknown clocks."""

from datetime import date

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from core.collection_storage_migration import project_publication_coordinates_batch
from core.models import CollectionObservation
from tests.test_collection_resources import publication_observation

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def observation():
    return publication_observation(
        dimensions={"date": "2026-09-20"},
        metadata={"numeric_snapshot_identity": {
            "native_identifier": "vendor/model", "revision": "rev-17",
            "category": "overall", "period": "2026-09-20",
        }},
    )


def test_copy_is_bounded_repeatable_and_does_not_create_a_publication_time():
    first = observation()
    second = CollectionObservation.objects.create(
        run=first.run, source_identifier="vendor/second", source_subject_kind="model",
        observation_key="b" * 64, dimensions={"date": "2026-09-21"},
    )
    before = list(CollectionObservation.objects.order_by("pk").values(
        "pk", "run_id", "observation_key", "listing", "source_metadata", "dimensions",
    ))
    with pytest.raises(ValueError, match="not projected"):
        project_publication_coordinates_batch(verify_only=True)
    with CaptureQueriesContext(connection) as queries:
        copied = project_publication_coordinates_batch(batch_size=1)
    assert (copied.last_id, copied.scanned, copied.updated) == (first.pk, 1, 1)
    assert not any('"listing"' in row["sql"] or '"raw_payload"' in row["sql"] for row in queries)
    second.refresh_from_db()
    assert second.source_record_date is None
    assert project_publication_coordinates_batch(after_id=first.pk).updated == 1
    assert project_publication_coordinates_batch().updated == 0
    assert project_publication_coordinates_batch(verify_only=True).scanned == 2
    first.refresh_from_db()
    assert first.source_record_date == date(2026, 9, 20)
    assert first.provider_revision == "rev-17"
    assert first.category_key == "overall"
    assert first.published_date is None and first.published_at is None
    assert list(CollectionObservation.objects.order_by("pk").values(
        "pk", "run_id", "observation_key", "listing", "source_metadata", "dimensions",
    )) == before


@pytest.mark.parametrize("conflict", ["typed", "source", "identity"])
def test_conflicting_coordinates_abort_without_changing_known_facts(conflict):
    row = observation()
    if conflict == "typed":
        row.provider_revision = "different"
    elif conflict == "source":
        row.dimensions["revision"] = "different"
    else:
        row.source_metadata["numeric_snapshot_identity"]["native_identifier"] = "another/model"
    row.save(update_fields=["provider_revision", "dimensions", "source_metadata"])
    with pytest.raises(ValueError, match="conflict"):
        project_publication_coordinates_batch()
    row.refresh_from_db()
    assert row.source_record_date is None
    assert row.provider_revision == ("different" if conflict == "typed" else None)


def test_absent_old_coordinates_do_not_clear_a_typed_only_observation():
    row = observation()
    project_publication_coordinates_batch()
    CollectionObservation.objects.filter(pk=row.pk).update(source_metadata={}, dimensions={})
    assert project_publication_coordinates_batch().scanned == 0
    row.refresh_from_db()
    assert row.provider_revision == "rev-17"
    assert row.source_record_date == date(2026, 9, 20)
