"""Resolve exact registered zones for events/offers without rewriting evidence."""

from django.db import transaction
from django.db.models import F

from core.models import Event, Opportunity, TimeZone

OWNERS = {"events": Event, "opportunities": Opportunity}


def map_intelligence_time_zones(
    *,
    owner,
    database="default",
    batch_size=500,
    max_batches=10,
    after_id=0,
    apply=False,
):
    if owner not in OWNERS:
        raise ValueError("Owner must be events or opportunities")
    if not 1 <= batch_size <= 10000 or not 1 <= max_batches <= 10000 or after_id < 0:
        raise ValueError("Positive bounded batch limits and nonnegative ID required")
    rows = OWNERS[owner].objects.using(database)
    zones = TimeZone.objects.using(database).values("pk")
    eligible = rows.filter(
        source_timezone_reference__isnull=True, source_timezone__in=zones
    )
    examined = updated = 0
    for _ in range(max_batches):
        with transaction.atomic(using=database):
            ids = list(
                eligible.filter(pk__gt=after_id)
                .order_by("pk")
                .values_list("pk", flat=True)[:batch_size]
            )
            if not ids:
                break
            if apply:
                # Current wording/eligibility is rechecked after row-lock waits.
                updated += eligible.filter(pk__in=ids).update(
                    source_timezone_reference_id=F("source_timezone")
                )
            examined += len(ids)
            after_id = ids[-1]
    absent = rows.filter(source_timezone__isnull=True) | rows.filter(source_timezone="")
    return {
        "owner": owner,
        "apply": apply,
        "examined": examined,
        "updated": updated,
        "after_id": after_id,
        "remaining_resolvable": eligible.count(),
        "unmatched_count": rows.exclude(source_timezone__in=zones)
        .exclude(source_timezone__isnull=True)
        .exclude(source_timezone="")
        .count(),
        "absent_count": absent.count(),
    }
