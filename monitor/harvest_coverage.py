"""Read scheduled X search coverage without inferring it from post timestamps."""

from datetime import UTC, datetime, timedelta

from django.db.models import OuterRef, Prefetch, Subquery
from django.db.models.functions import Coalesce

from core.models import (
    CollectionAttempt,
    CollectionJobTarget,
    CollectionRun,
    CollectionScopeRun,
)
from x_monitor.config import VALID_CALL_IDS


def closed_five_minute_boundary(at: datetime) -> datetime:
    at = at.astimezone(UTC)
    return at.replace(minute=at.minute // 5 * 5, second=0, microsecond=0)


def latest_scheduled_coverage(at: datetime) -> dict[str, str] | None:
    """Require every ordinary frozen target in a settled scheduled execution.

    Optional discovery queries cannot certify or withhold ordinary coverage.
    A cursor is unsuitable: truncated searches can transfer unfinished windows
    into the backlog and advance that cursor. Empty, fully enumerated searches
    are valid coverage. No new persistence or provider request is needed.
    """
    settled_attempt = CollectionAttempt.objects.filter(
        run_id=OuterRef("pk"), finished_at__isnull=False,
    ).order_by("-ordinal").values("finished_at")[:1]
    runs = (
        CollectionRun.objects.annotate(chart_completed_at=Coalesce("completed_at", Subquery(settled_attempt))).filter(
            job__source_id="x", job__purpose="content", job__operation="x_cycle",
            job__mode="recurring", chart_completed_at__lte=at,
            chart_completed_at__gte=at - timedelta(days=1), scheduled_slot_at__isnull=False,
        ).exclude(status="running")
        .select_related("job")
        .only("id", "job_id", "job__id")
        .prefetch_related(
            Prefetch("job__targets", queryset=CollectionJobTarget.objects.filter(
                target_kind="query", target_key__in=VALID_CALL_IDS,
            ).only("id", "job_id"), to_attr="chart_targets"),
            Prefetch("scopes", queryset=CollectionScopeRun.objects.filter(
                scope_kind="x_query", scope_key__in=VALID_CALL_IDS,
            ).only("run_id", "job_target_id", "enumeration_complete", "coverage_state",
                   "execution_state", "requested_start_at", "requested_end_at"), to_attr="chart_scopes"),
        )
        .order_by("-chart_completed_at")[:96]
    )
    for run in runs:
        targets = {target.pk for target in run.job.chart_targets}
        scopes = run.chart_scopes
        if not targets or {scope.job_target_id for scope in scopes} != targets:
            continue
        if any(
            not scope.enumeration_complete or scope.coverage_state != "complete"
            or scope.execution_state != "completed"
            or scope.requested_start_at is None or scope.requested_end_at is None
            or not scope.requested_start_at < scope.requested_end_at <= at
            for scope in scopes
        ):
            continue
        searched_through = min(scope.requested_end_at for scope in scopes)
        end = closed_five_minute_boundary(searched_through)
        # All calls must cover the full last bucket, even after a cold start.
        if max(scope.requested_start_at for scope in scopes) > end - timedelta(minutes=5):
            continue
        return {
            "run_id": str(run.pk),
            "searched_through": searched_through.isoformat(),
            "completed_at": run.chart_completed_at.isoformat(),
            "chart_end_at": end.isoformat(),
        }
    return None
