"""Preserve job location occurrences and serve only resolved shared places."""

from django.db import connections, transaction
from django.db.models import Prefetch
from django.utils import timezone

from core.collection_capture import archive_legacy, read_document
from core.geolocation_resolution import resolve_geolocation
from core.geolocations import geolocation_label
from core.models import JobListing, JobListingLocation


@transaction.atomic
def write_job_locations(listing, locations, *, reported_value=None, evidence=None, observed_at=None):
    """Replace current occurrences under the listing lock; retain their source.

    Input is an already parsed source array. JSONB is archived with its honest
    legacy-serialization label; original HTTP bytes are not claimed here.
    """
    if not isinstance(locations, list):
        raise TypeError("Job location source must be an array")
    if reported_value is not None and not isinstance(reported_value, str):
        raise TypeError("Reported job location wording must be text")
    owner = JobListing.objects.select_for_update().get(pk=listing.pk)
    if evidence is not None and evidence.listing_id != owner.pk:
        raise ValueError("Job location evidence must belong to the same listing")
    current = list(owner.location_occurrences.filter(superseded_at__isnull=True))
    # A replay cannot replace a newer accepted source observation, including
    # one whose location array was empty.
    if observed_at is not None and observed_at < owner.last_seen_at:
        return current
    if observed_at is not None and observed_at > owner.last_seen_at:
        JobListing.objects.filter(pk=owner.pk).update(last_seen_at=observed_at)
    values = locations or ([reported_value] if reported_value and reported_value.strip() else [])
    source = {"locations": locations, "reported_value": reported_value}
    if owner.geolocation_source_archive_id and read_document(owner.geolocation_source_archive) == source:
        return current
    captured = archive_legacy(source)
    now = timezone.now()
    JobListingLocation.objects.filter(pk__in=[row.pk for row in current]).update(superseded_at=now)
    JobListing.objects.filter(pk=owner.pk).update(geolocation_source_archive=captured)
    listing.geolocation_source_archive_id = captured.pk
    rows = []
    for ordinal, value in enumerate(values):
        existing = JobListingLocation.objects.filter(
            listing=owner, source_archive=captured, ordinal=ordinal, observed_at=observed_at,
        ).first()
        if existing is not None:
            # A source identity may be replayed, but an obsolete observation
            # cannot become current again under that same identity.
            raise ValueError("Cannot reactivate a superseded job location observation")
        # Insert the immutable source wording with its occurrence. It is not a
        # field on the canonical ORM model and cannot be changed after insert.
        alias = owner._state.db or "default"
        with connections[alias].cursor() as cursor:
            cursor.execute(
                """INSERT INTO job_listing_locations
                (listing_id, evidence_id, source_archive_id, ordinal, observed_at,
                 recorded_at, geolocation_id, reported_value)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                [owner.pk, evidence.pk if evidence else None, captured.pk, ordinal,
                 observed_at, now, resolve_geolocation(value),
                 value if isinstance(value, str) else None],
            )
            row_id = cursor.fetchone()[0]
        rows.append(JobListingLocation.objects.using(alias).get(pk=row_id))
    getattr(listing, "_prefetched_objects_cache", {}).pop("location_occurrences", None)
    return rows


def location_prefetch(*, prefix=""):
    return Prefetch(
        prefix + "location_occurrences",
        queryset=JobListingLocation.objects.filter(
            superseded_at__isnull=True, geolocation__isnull=False,
        ).select_related("geolocation").prefetch_related("geolocation__alternate_names"),
    )


def canonical_job_locations(listing, *, locale="en"):
    """Deduplicate resolved places; never fall back to a source string."""
    rows = getattr(listing, "_prefetched_objects_cache", {}).get("location_occurrences")
    if rows is None:
        rows = location_prefetch().queryset.filter(listing=listing)
    seen = set()
    result = []
    for row in rows:
        if row.superseded_at is not None or row.geolocation_id is None:
            continue
        if row.geolocation_id not in seen:
            seen.add(row.geolocation_id)
            result.append({"id": row.geolocation_id, "label": geolocation_label(row.geolocation, locale)})
    return result
