"""Read-only source health; this module registers no scheduler or automatic work."""

from datetime import UTC

from django.db.models import Max
from django.utils import timezone

from core.measurement_taxonomy import require
from core.models import MetricCollectionRun, MetricValue

OPERATION_LIMITS = {
    "poll_seconds": (300, 604800, 86400),
    "freshness_seconds": (300, 2592000, 172800),
    "publication_freshness_seconds": (300, 2592000, 604800),
    "completed_day_lag": (0, 7, 1),
    "recheck_days": (1, 90, 7),
    "max_requests": (1, 100, 20),
    "max_seconds": (1, 300, 120),
    "max_bytes": (1, 33554432, 8388608),
}


def validate_operations(settings):
    for key, (low, high, default) in OPERATION_LIMITS.items():
        value = settings.setdefault(key, default)
        require(type(value) is int and low <= value <= high, f"invalid {key} budget")
    require(
        type(settings.get("scheduling_enabled", False)) is bool,
        "scheduling_enabled must be boolean",
    )
    settings.setdefault("scheduling_enabled", False)


def collection_health(contract, *, now=None):
    now = now or timezone.now()
    result = {}
    for source, config in contract.source_configuration.items():
        runs = MetricCollectionRun.objects.filter(
            contract=contract, source_id=source
        ).only(
            "status",
            "started_at",
            "completed_at",
            "error_code",
            "selected_count",
            "success_count",
        )
        attempt = runs.order_by("-started_at", "-id").first()
        success = runs.filter(status="success").order_by("-completed_at", "-id").first()
        values = MetricValue.objects.filter(
            observation__run__contract=contract,
            observation__run__source_id=source,
            observation__run__status__in=["success", "partial"],
            observation__status="ok",
            observation__mapping__isnull=False,
        ).aggregate(
            as_of=Max("as_of_at"),
            day=Max("as_of_date"),
            period=Max("period_label_date"),
        )
        effective = [
            v
            for v in (
                values["day"],
                values["period"],
                values["as_of"].astimezone(UTC).date() if values["as_of"] else None,
            )
            if v
        ]
        effective = max(effective) if effective else None
        threshold = config.get("freshness_seconds", 172800)
        publication_threshold = config.get("publication_freshness_seconds", 604800)

        def brief(run):
            return (
                None
                if run is None
                else {
                    "run_id": str(run.pk),
                    "status": run.status,
                    "started_at": run.started_at.isoformat(),
                    "completed_at": run.completed_at.isoformat()
                    if run.completed_at
                    else None,
                    "error_code": run.error_code,
                    "selected_count": run.selected_count,
                    "success_count": run.success_count,
                }
            )

        result[source] = {
            "last_attempt": brief(attempt),
            "last_success": brief(success),
            "retrieval_freshness": "unknown"
            if success is None
            else "stale"
            if (now - success.completed_at).total_seconds() > threshold
            else "fresh",
            "latest_effective_date": effective.isoformat() if effective else None,
            "effective_freshness": "unknown"
            if effective is None
            else "stale"
            if (now.astimezone(UTC).date() - effective).days * 86400
            > publication_threshold
            else "within_threshold",
            "effective_date_precision": "date" if effective else "unknown",
            "scheduling_enabled": config.get("scheduling_enabled", False),
            "freshness_seconds": threshold,
            "publication_freshness_seconds": publication_threshold,
        }
    return result
