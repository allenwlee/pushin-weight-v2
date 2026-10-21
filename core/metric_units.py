"""Bounded mapping of exact unit identities without changing source definitions."""

from django.db import transaction
from django.db.models import Case, F, Q, When

from core.models import MeasurementUnit, SourceMetric


def map_metric_units(
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
    units = MeasurementUnit.objects.using(database).values("pk")
    eligible = metrics.filter(
        Q(unit_reference__isnull=True, unit__in=units)
        | Q(window_unit_reference__isnull=True, window_unit__in=units)
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
                # Re-evaluate current wording and both roles at UPDATE time.
                # A concurrent old writer cannot install a stale reference.
                updated += eligible.filter(pk__in=ids).update(
                    unit_reference_id=Case(
                        When(unit__in=units, then=F("unit")), default=None
                    ),
                    window_unit_reference_id=Case(
                        When(window_unit__in=units, then=F("window_unit")),
                        default=None,
                    ),
                )
            examined += len(ids)
            after_metric_id = ids[-1]
    return {
        "apply": apply,
        "examined": examined,
        "updated": updated,
        "after_metric_id": after_metric_id,
        "remaining_resolvable": eligible.count(),
        "unmatched_unit_count": metrics.exclude(unit__in=units).count(),
        "unmatched_window_unit_count": metrics.filter(window_unit__isnull=False)
        .exclude(window_unit__in=units)
        .count(),
    }
