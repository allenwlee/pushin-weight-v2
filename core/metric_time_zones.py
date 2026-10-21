"""Bounded exact-identity mapping without changing reported metric definitions."""

from django.db import transaction
from django.db.models import F

from core.models import SourceMetric, TimeZone


def map_metric_time_zones(
    *,
    database="default",
    batch_size=500,
    max_batches=10,
    after_metric_id=0,
    apply=False,
):
    if (
        not 1 <= batch_size <= 10000
        or not 1 <= max_batches <= 10000
        or after_metric_id < 0
    ):
        raise ValueError(
            "Positive bounded batch limits and nonnegative metric ID required"
        )
    metrics = SourceMetric.objects.using(database)
    zones = TimeZone.objects.using(database).values("pk")
    eligible = metrics.filter(
        source_timezone_reference_id__isnull=True, source_timezone__in=zones
    )
    examined = updated = 0
    for _ in range(max_batches):
        with transaction.atomic(using=database):
            ids = list(
                eligible.filter(pk__gt=after_metric_id)
                .order_by("pk")
                .values_list("pk", flat=True)[:batch_size]
            )
            if not ids:
                break
            if apply:
                # Re-evaluate both predicates at UPDATE time. A concurrent raw
                # timezone change cannot install the formerly selected value.
                updated += eligible.filter(pk__in=ids).update(
                    source_timezone_reference_id=F("source_timezone")
                )
            examined += len(ids)
            after_metric_id = ids[-1]
    return {
        "apply": apply,
        "examined": examined,
        "updated": updated,
        "after_metric_id": after_metric_id,
        "remaining_resolvable": eligible.count(),
        "unmatched_count": metrics.exclude(source_timezone__in=zones).count(),
    }
