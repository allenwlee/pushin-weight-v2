from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from core.collection_capture import archive_document, read_document
from core.geolocation_evidence import source_evidence, write_source_evidence
from core.geolocation_resolution import resolve_geolocation, source_geonames_id
from core.job_locations import canonical_job_locations, write_job_locations
from core.models import (
    Brand,
    Geolocation,
    GeolocationAlternateName,
    JobListing,
    JobListingEvidence,
    JobListingLocation,
)

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


@pytest.fixture
def listing():
    brand = Brand.objects.create(nickname="geo-job-test", display_name="Geo Job")
    now = timezone.now()
    return JobListing.objects.create(
        brand=brand, hiring_organization="Geo Job", title="Researcher",
        listing_identity="geo-job-identity", first_seen_at=now, last_seen_at=now,
    )


@pytest.fixture
def india():
    archive = archive_document(b"India source fixture")
    row = Geolocation.objects.create(
        geonames_id=1269750, place_kind=4, iso2_country_code="IN", source_archive=archive,
    )
    GeolocationAlternateName.objects.create(
        geolocation=row, name="India", locale_id="en", is_preferred=True, source_archive=archive,
    )
    return row


def test_strict_resolution_does_not_accept_a_unique_local_alias(india):
    GeolocationAlternateName.objects.create(
        geolocation=india, name="Springfield", locale_id="en", source_archive=india.source_archive,
    )
    assert resolve_geolocation("India") == india.pk
    assert resolve_geolocation("Springfield") is None
    assert resolve_geolocation("IN") is None
    assert resolve_geolocation("IN", context="country") == india.pk
    assert source_geonames_id("Korea") == 1835841
    assert source_geonames_id("Congo") == 203312
    assert source_geonames_id("North Korea") != 1835841
    assert source_geonames_id("Republic of the Congo") != 203312
    assert source_geonames_id("Georgia") is None
    assert source_geonames_id("Georgia", context="country") == 614540


def test_multiple_source_occurrences_preserve_structure_and_deduplicate_serving(listing, india):
    values = ["India", {"country": "India", "city": None, "admin_area": None}, "Springfield", "Remote", "India"]
    rows = write_job_locations(listing, values, observed_at=listing.last_seen_at)
    assert [row.geolocation_id for row in rows] == [india.pk, india.pk, None, None, india.pk]
    assert read_document(rows[1].source_archive)["locations"] == values
    assert source_evidence(rows[1]).reported_value is None  # No lossy Python-dict string.
    assert canonical_job_locations(listing) == [{"id": india.pk, "label": "India"}]
    assert [row.pk for row in write_job_locations(listing, values, observed_at=listing.last_seen_at)] == [row.pk for row in rows]
    assert JobListingLocation.objects.count() == 5


def test_changed_source_invalidates_prior_resolution_and_preserves_history(listing, india):
    old = write_job_locations(listing, ["India"], observed_at=listing.last_seen_at)[0]
    later = listing.last_seen_at + timedelta(seconds=1)
    rows = write_job_locations(listing, ["Springfield"], observed_at=later)
    old.refresh_from_db()
    assert old.superseded_at is not None and old.geolocation_id == india.pk
    assert rows[0].geolocation_id is None and source_evidence(rows[0]).reported_value == "Springfield"
    assert canonical_job_locations(listing) == []
    assert read_document(old.source_archive)["locations"] == ["India"]
    write_job_locations(listing, [], observed_at=later + timedelta(seconds=1))
    assert not listing.location_occurrences.filter(superseded_at__isnull=True).exists()
    listing.refresh_from_db()
    assert read_document(listing.geolocation_source_archive)["locations"] == []
    assert write_job_locations(listing, ["India"], observed_at=later) == []
    with pytest.raises(IntegrityError), transaction.atomic():
        JobListingLocation.objects.filter(pk=old.pk).update(superseded_at=None)
    with pytest.raises(IntegrityError), transaction.atomic():
        JobListingLocation.objects.filter(pk=old.pk).delete()


def test_mutable_evidence_does_not_mutate_location_source(listing, india):
    evidence = JobListingEvidence.objects.create(
        listing=listing, source_url="https://example.test/job", source_relationship="official",
        extraction_method="structured_text", extraction_identity="test", evidence_hash="fixture",
        observed_at=listing.last_seen_at,
    )
    write_source_evidence(evidence, raw_evidence={"location": "India"})
    row = write_job_locations(listing, ["India"], evidence=evidence, observed_at=listing.last_seen_at)[0]
    write_source_evidence(evidence, raw_evidence={"location": "unresolved"})
    assert read_document(row.source_archive)["locations"] == ["India"]
    other = JobListing.objects.create(
        brand=listing.brand, hiring_organization="Other", title="Role", listing_identity="other-job",
        first_seen_at=listing.first_seen_at, last_seen_at=listing.last_seen_at,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        JobListingLocation.objects.create(
            listing=other, source_archive=row.source_archive, evidence=evidence, ordinal=0,
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        write_source_evidence(row, reported_value="changed")


def test_structured_city_claim_is_not_silently_coarsened(listing, india):
    rows = write_job_locations(listing, [{"country": "India", "city": "unverified", "admin_area": None}])
    assert rows[0].geolocation_id is None
    assert canonical_job_locations(listing) == []


def test_legacy_source_change_invalidates_current_location_selection(listing, india):
    from django.db import connection

    original = write_job_locations(listing, ["India"], observed_at=listing.last_seen_at)[0]
    with connection.cursor() as cursor:
        cursor.execute("UPDATE job_listings SET locations=%s::jsonb WHERE id=%s", ['["Springfield"]', listing.pk])
    listing.refresh_from_db()
    original.refresh_from_db()
    assert listing.geolocation_source_archive_id is None
    assert original.superseded_at is not None
    assert canonical_job_locations(listing) == []
    current = write_job_locations(listing, ["Springfield"], observed_at=listing.last_seen_at)[0]
    assert current.geolocation_id is None
    with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
        JobListing.objects.filter(pk=listing.pk).update(geolocation_source_archive=original.source_archive)
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_official_source_call_chain_writes_ids_and_keeps_changed_location_evidence(india):
    from dataclasses import replace

    from core.job_sources.sync import sync_snapshot
    from core.job_sources.types import SourceJob, SourceSnapshot

    Brand.objects.create(nickname="qwen", display_name="Qwen")
    now = timezone.now()
    job = SourceJob(
        source_listing_id="geography-job", title="Researcher",
        canonical_url="https://talent.quark.cn/job/geography-job", locations=("India",),
    )
    snapshot = SourceSnapshot(source_key="qwen", jobs=(job,), declared_total=1, complete=True, observed_at=now)
    sync_snapshot(snapshot)
    listing = JobListing.objects.get()
    original = listing.location_occurrences.get()
    evidence_id = original.evidence_id
    assert original.geolocation_id == india.pk
    sync_snapshot(replace(snapshot, jobs=(replace(job, locations=("Springfield",)),), observed_at=now + timedelta(seconds=1)))
    current = listing.location_occurrences.get(superseded_at__isnull=True)
    assert current.geolocation_id is None and current.evidence_id == evidence_id
    original.refresh_from_db()
    assert original.superseded_at is not None
    assert read_document(original.source_archive)["locations"] == ["India"]
    assert canonical_job_locations(listing) == []
