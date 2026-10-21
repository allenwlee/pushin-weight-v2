"""Audit canonical metric-unit references after the one-time cutover."""

from core.models import SourceMetric


def map_metric_units(*, database="default"):
    metrics = SourceMetric.objects.using(database)
    missing_required = metrics.filter(unit_reference__isnull=True).count()
    missing_window = metrics.filter(
        window_unit_reference__isnull=True,
        window_mode__in=("rolling", "calendar", "fixed"),
    ).count()
    unknown_window = metrics.exclude(
        window_unit_reference_id__in=("day", "second")
    ).filter(window_mode__in=("rolling", "calendar", "fixed")).count()
    return {
        "operation": "audit",
        "updated": 0,
        "metric_count": metrics.count(),
        "missing_required_unit_reference_count": missing_required,
        "missing_window_unit_reference_count": missing_window,
        "invalid_window_unit_reference_count": unknown_window,
        "healthy": not (missing_required or missing_window or unknown_window),
    }
