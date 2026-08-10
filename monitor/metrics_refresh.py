"""One-shot metrics re-fetch for harvest posts (plan 2026-08-10-002).

Each post is eligible for exactly one by-ID metrics refresh after
``metrics_refresh.delay_hours`` from first ``fetched_at``. Replaces the
continuous official/staff quote-count recheck loop.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from django.utils import timezone as dj_timezone

from core.models import Post
from x_monitor.apify import TwitterApiClient
from x_monitor.config import Config, MetricsRefreshConfig

logger = logging.getLogger(__name__)


def _mrc(cfg: Config | None) -> MetricsRefreshConfig:
    if cfg is None:
        return MetricsRefreshConfig()
    return getattr(cfg, "metrics_refresh", None) or MetricsRefreshConfig()


def select_due_posts(
    *,
    delay_hours: float,
    per_cycle_cap: int,
    now: datetime | None = None,
) -> list[str]:
    """Return tweet_ids due for one-shot metrics refresh (oldest first)."""
    now = now or dj_timezone.now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    cutoff = now - timedelta(hours=float(delay_hours))
    qs = (
        Post.objects.filter(metrics_refreshed_at__isnull=True, fetched_at__lte=cutoff)
        .order_by("fetched_at")
        .values_list("tweet_id", flat=True)[: int(per_cycle_cap)]
    )
    return [str(t) for t in qs]


def apply_metrics_to_post(tweet_id: str, info: dict[str, Any], *, now: datetime | None = None) -> bool:
    """Update engagement counts and stamp metrics_refreshed_at. Returns True if row updated."""
    now = now or dj_timezone.now()
    updates: dict[str, Any] = {"metrics_refreshed_at": now}
    for key in ("like_count", "retweet_count", "reply_count", "quote_count"):
        if key in info and info[key] is not None:
            updates[key] = int(info[key])
    # Optional extras if API / client ever supplies them
    for key in ("view_count", "bookmark_count"):
        if key in info and info[key] is not None:
            updates[key] = int(info[key])
    n = Post.objects.filter(tweet_id=str(tweet_id)).update(**updates)
    return n > 0


def run_metrics_refresh(
    api: TwitterApiClient,
    cfg: Config | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Select due posts, by-ID refresh metrics, stamp once. Never raises."""
    mrc = _mrc(cfg)
    out: dict[str, Any] = {
        "enabled": bool(mrc.enabled),
        "n_due": 0,
        "n_refreshed": 0,
        "n_missing": 0,
        "n_errors": 0,
        "delay_hours": float(mrc.delay_hours),
        "per_cycle_cap": int(mrc.per_cycle_cap),
    }
    if not mrc.enabled:
        return out

    try:
        due = select_due_posts(
            delay_hours=mrc.delay_hours,
            per_cycle_cap=mrc.per_cycle_cap,
            now=now,
        )
    except Exception as exc:
        logger.warning("metrics_refresh: select_due_posts failed: %s", exc)
        out["n_errors"] = 1
        out["error"] = str(exc)
        return out

    out["n_due"] = len(due)
    if not due:
        return out

    try:
        fresh = api.get_tweets_by_ids(due)
    except Exception as exc:
        logger.warning("metrics_refresh: get_tweets_by_ids failed: %s", exc)
        out["n_errors"] = 1
        out["error"] = str(exc)
        return out

    if not isinstance(fresh, dict):
        fresh = {}

    stamp_now = now or dj_timezone.now()
    for tid in due:
        info = fresh.get(tid)
        if not info:
            out["n_missing"] += 1
            continue
        try:
            ok = apply_metrics_to_post(tid, info, now=stamp_now)
            if ok:
                out["n_refreshed"] += 1
            else:
                out["n_missing"] += 1
        except Exception as exc:
            logger.warning("metrics_refresh: apply failed for %s: %s", tid, exc)
            out["n_errors"] += 1

    logger.info(
        "metrics_refresh: due=%d refreshed=%d missing=%d errors=%d",
        out["n_due"],
        out["n_refreshed"],
        out["n_missing"],
        out["n_errors"],
    )
    return out
