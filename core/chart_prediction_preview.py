"""Transient, coverage-qualified release comparison scenarios."""

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal


def temporary_preview(
    *,
    target_posts,
    historical_posts,
    historical_metrics,
    completed_day,
    cutoff,
    target_launch,
    source,
    metric,
    comparable=False,
    accounting_known=False,
    forecast_permitted=False,
    history_mode="strict",
    horizon=28,
):
    """Scale eligible historical measurements; never infer missing coverage.

    Callers must establish counting compatibility, known collection accounting,
    source permissions and cutoff eligibility for every input before opting in.
    """
    unavailable = {
        "status": "unavailable",
        "reason": "insufficient comparable post history",
        "points": {},
    }
    if (
        not comparable
        or not accounting_known
        or not forecast_permitted
        or (source, metric)
        not in {("hf", "net_download_change"), ("openrouter", "total_tokens")}
        or history_mode not in {"strict", "hindsight"}
        or cutoff.utcoffset() != timedelta(0)
        or completed_day < 2
        or horizon < completed_day
        or horizon > 28
        or datetime.combine(
            target_launch + timedelta(days=completed_day + 1), time.min, tzinfo=UTC
        )
        > cutoff
    ):
        return unavailable
    days = range(completed_day - 2, completed_day + 1)
    if any(
        target_posts.get(day) is None or historical_posts.get(day) is None
        for day in days
    ):
        return unavailable
    if any(target_posts[day] < 0 or historical_posts[day] < 0 for day in days):
        return unavailable
    denominator = sum(historical_posts[day] for day in days)
    if denominator <= 0:
        return unavailable
    ratio = Decimal(sum(target_posts[day] for day in days)) / Decimal(denominator)
    points = {}
    for day in range(completed_day + 1, horizon + 1):
        value = historical_metrics.get(day)
        eligible = historical_posts.get(day) is not None and historical_posts[day] > 0
        trailing = [historical_metrics.get(d) for d in range(day - 2, day + 1)]
        points[day] = {
            "value": ratio * Decimal(value) if eligible and value is not None else None,
            "smoothed": ratio * sum(map(Decimal, trailing)) / 3
            if eligible and day - 2 >= 0 and all(v is not None for v in trailing)
            else None,
        }
    return {
        "status": "available",
        "ratio": ratio,
        "points": points,
        "history_mode": history_mode,
        "cutoff": cutoff,
        "warning": "Experimental estimate: assumes this collected-post ratio continues; collection coverage may differ.",
    }
