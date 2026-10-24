"""Preserve job location occurrences and serve only resolved shared places."""

from django.db import transaction
from django.utils import timezone

from core.collection_capture import archive_legacy
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
    captured = archive_legacy({"locations": locations, "reported_value": reported_value}) if values else None
    unchanged = (
        bool(current) and captured is not None
        and all(row.source_archive_id == captured.pk for row in current)
    )
    if unchanged or (not values and not current):
        return current
    now = timezone.now()
    JobListingLocation.objects.filter(pk__in=[row.pk for row in current]).update(superseded_at=now)
    rows = []
    for ordinal, value in enumerate(values):
        existing = JobListingLocation.objects.filter(
            listing=owner, source_archive=captured, ordinal=ordinal, observed_at=observed_at,
        ).first()
        if existing is not None:
            # A source identity may be replayed, but an obsolete observation
            # cannot become current again under that same identity.
            raise ValueError("Cannot reactivate a superseded job location observation")
        rows.append(JobListingLocation.objects.create(
            listing=owner, evidence=evidence, source_archive=captured, ordinal=ordinal,
            observed_at=observed_at, recorded_at=now,
            geolocation_id=resolve_geolocation(value),
            reported_value=value if isinstance(value, str) else None,
        ))
    return rows


def canonical_job_locations(listing, *, locale="en"):
    """Deduplicate resolved places; never fall back to a source string."""
    rows = listing.location_occurrences.filter(
        superseded_at__isnull=True, geolocation__isnull=False,
    ).select_related("geolocation").prefetch_related("geolocation__alternate_names")
    seen = set()
    result = []
    for row in rows:
        if row.geolocation_id not in seen:
            seen.add(row.geolocation_id)
            result.append({"id": row.geolocation_id, "label": geolocation_label(row.geolocation, locale)})
    return result
