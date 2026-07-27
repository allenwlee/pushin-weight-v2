"""Quote-tweet capture channel for v2 harvest (v1 parity).

Ports x_monitor/run.py:
  - _capture_official_quote_tweets  (every cycle, official/staff parents)
  - _capture_nonofficial_quote_tweets_daily  (once per UTC day)
  - _ingest_quote_tweets

v2 persists via Django ORM (CycleRunner._attribute_items / _persist_items)
and uses TwitterApiClient.get_tweets_by_ids + get_quote_tweets from
x_monitor.apify. Tracking columns already exist on core.models.Post:
  last_quote_count_seen, last_quote_fetched_at, quoted_text, quote_count.

This channel was ~24% of v1 stored volume and was never wired into
monitor/cycle.py — the remaining cause of the post-cutover volume gap
after the harvest-cursor restoration (see
docs/issues/2026-07-27-180000-harvest-cursor-restoration-v1-parity.md).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

from django.conf import settings
from django.db.models import Q
from django.utils import timezone as dj_timezone

from core.models import BrandAccount, Post
from x_monitor.apify import TwitterApiClient
from x_monitor.config import QuoteTweetConfig

logger = logging.getLogger(__name__)


class _Attributable(Protocol):
    def _attribute_items(
        self,
        items: list[dict[str, Any]],
        index: Any,
        brand_search_terms: dict[str, str],
    ) -> int: ...

    def _persist_items(
        self, items: list[dict[str, Any]]
    ) -> tuple[int, int, int]: ...


# ---------------------------------------------------------------------------
# Config + helpers
# ---------------------------------------------------------------------------


def load_quote_tweet_config() -> QuoteTweetConfig:
    """Return QuoteTweetConfig, optionally overridden by Django settings.

    Settings keys (all optional):
      X_MONITOR_QT_OFFICIAL_DELTA
      X_MONITOR_QT_TRACK_RECENCY_DAYS
      X_MONITOR_QT_MAX_PAGES
      X_MONITOR_QT_OFFICIAL_CALL_BUDGET
      X_MONITOR_QT_DAILY_ENABLED
      X_MONITOR_QT_DAILY_RECENCY_DAYS
      X_MONITOR_QT_DAILY_CALL_BUDGET
    """
    kwargs: dict[str, Any] = {}
    mapping = {
        "X_MONITOR_QT_OFFICIAL_DELTA": "official_delta",
        "X_MONITOR_QT_TRACK_RECENCY_DAYS": "track_recency_days",
        "X_MONITOR_QT_MAX_PAGES": "max_pages",
        "X_MONITOR_QT_OFFICIAL_CALL_BUDGET": "official_call_budget",
        "X_MONITOR_QT_DAILY_ENABLED": "daily_enabled",
        "X_MONITOR_QT_DAILY_RECENCY_DAYS": "daily_recency_days",
        "X_MONITOR_QT_DAILY_CALL_BUDGET": "daily_call_budget",
    }
    for setting_name, field in mapping.items():
        val = getattr(settings, setting_name, None)
        if val is not None and val != "":
            kwargs[field] = val
    return QuoteTweetConfig(**kwargs)


def staff_handles_set(enabled_models: list[str] | None = None) -> set[str]:
    """Handles for brands_accounts roles official + staff (role keys).

    Mirrors x_monitor.store.Store.read_brand_official_staff_handles.
    """
    qs = BrandAccount.objects.filter(
        role_id__in=["official", "staff"]
    ).select_related("account")
    if enabled_models is not None:
        qs = qs.filter(brand_id__in=list(enabled_models))
    out: set[str] = set()
    for ba in qs:
        handle = (ba.account.handle if ba.account_id else None) or ""
        handle = str(handle).lstrip("@").strip()
        if handle:
            out.add(handle)
    return out


def _iso_to_epoch(value: Any) -> int | None:
    """Parse ISO / datetime to unix seconds for sinceTime."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    try:
        return int(
            datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
        )
    except ValueError:
        return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def update_quote_tracking(
    tweet_id: str,
    quote_count: int,
    *,
    fetched_at: datetime | None = None,
) -> None:
    """Record last observed quote_count + QT-fetch timestamp on the parent post."""
    ts = fetched_at or dj_timezone.now()
    Post.objects.filter(tweet_id=str(tweet_id)).update(
        last_quote_count_seen=int(quote_count),
        last_quote_fetched_at=ts,
        quote_count=int(quote_count),
    )


def _data_dir() -> Path:
    raw = getattr(settings, "XMONITOR_DATA_DIR", None)
    if raw:
        return Path(raw)
    base = getattr(settings, "BASE_DIR", None)
    if base:
        return Path(base) / "data"
    return Path.cwd() / "data"


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------


def ingest_quote_tweets(
    runner: _Attributable,
    qt_items: list[dict[str, Any]],
    parent_tweet_id: str,
    parent_text: str,
    *,
    index: Any,
    brand_search_terms: dict[str, str],
) -> int:
    """Attribute + persist captured QTs. Returns n newly inserted.

    D5 invariant: if a QT has no quoted_text and quoted_status_id == parent,
    attach parent text so brand attribution can match the quoted body.
    """
    parent_id_str = str(parent_tweet_id or "")
    for qt in qt_items:
        if not qt.get("quoted_text") and str(
            qt.get("quoted_status_id") or ""
        ) == parent_id_str:
            qt["quoted_text"] = parent_text
        # Ensure id field for persist
        if not qt.get("id") and qt.get("tweet_id"):
            qt["id"] = qt["tweet_id"]
        if not qt.get("tweet_id") and qt.get("id"):
            qt["tweet_id"] = qt["id"]

    runner._attribute_items(qt_items, index, brand_search_terms)
    kept = [it for it in qt_items if not it.get("_unattributed")]
    if not kept:
        return 0
    n_inserted, _n_attr, _n_failed = runner._persist_items(kept)
    return n_inserted


# ---------------------------------------------------------------------------
# Capture regimes
# ---------------------------------------------------------------------------


def capture_official_quote_tweets(
    runner: _Attributable,
    api: TwitterApiClient,
    *,
    index: Any,
    brand_search_terms: dict[str, str],
    staff_handles: set[str],
    cfg: QuoteTweetConfig | None = None,
) -> dict[str, Any]:
    """Every-cycle QT capture for official/staff parent posts."""
    cfg = cfg or load_quote_tweet_config()
    out: dict[str, Any] = {"official_n_tracked": 0}
    if not staff_handles:
        return out

    cutoff_epoch = int(time.time()) - cfg.track_recency_days * 86400
    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=cfg.track_recency_days)
    staff_list = list(staff_handles)

    rows = list(
        Post.objects.filter(author_handle__in=staff_list)
        .filter(
            Q(created_at_epoch__gte=cutoff_epoch)
            | Q(created_at__gte=cutoff_dt)
        )
        .values(
            "tweet_id",
            "text",
            "last_quote_count_seen",
            "last_quote_fetched_at",
        )
    )
    out["official_n_tracked"] = len(rows)
    if not rows:
        return out

    try:
        fresh = api.get_tweets_by_ids([r["tweet_id"] for r in rows])
    except Exception as exc:
        logger.warning("official QT refresh failed: %s", exc)
        out["official_refresh_error"] = str(exc)
        return out

    n_calls = 0
    n_qts = 0
    n_ingested = 0
    for r in rows:
        tid = r["tweet_id"]
        info = fresh.get(tid)
        if not info:
            continue
        fresh_qc = int(info.get("quote_count") or 0)
        prior = int(r["last_quote_count_seen"] or 0)
        delta = fresh_qc - prior
        if delta < cfg.official_delta:
            continue
        since_time = _iso_to_epoch(r["last_quote_fetched_at"])
        try:
            qts = api.get_quote_tweets(
                tid, since_time=since_time, max_pages=cfg.max_pages
            )
        except Exception as exc:
            logger.warning("official QT fetch failed for %s: %s", tid, exc)
            continue
        n_calls += 1
        if qts:
            try:
                ingested = ingest_quote_tweets(
                    runner,
                    qts,
                    tid,
                    r["text"] or "",
                    index=index,
                    brand_search_terms=brand_search_terms,
                )
            except Exception as exc:
                logger.warning("official QT ingest failed for %s: %s", tid, exc)
                ingested = 0
            n_ingested += ingested
            n_qts += len(qts)
        # Advance tracking after successful fetch (even if 0 new QTs)
        update_quote_tracking(tid, fresh_qc)
        if n_calls >= cfg.official_call_budget:
            break

    out.update(
        official_n_calls=n_calls,
        official_n_qts_fetched=n_qts,
        official_n_ingested=n_ingested,
    )
    return out


def capture_nonofficial_quote_tweets_daily(
    runner: _Attributable,
    api: TwitterApiClient,
    *,
    index: Any,
    brand_search_terms: dict[str, str],
    staff_handles: set[str],
    cfg: QuoteTweetConfig | None = None,
) -> dict[str, Any]:
    """Once-per-UTC-day QT capture for non-official parents."""
    cfg = cfg or load_quote_tweet_config()
    out: dict[str, Any] = {"daily_ran": False}
    if not cfg.daily_enabled:
        return out

    today = datetime.now(timezone.utc).date().isoformat()
    marker = _data_dir() / "_qt_daily_marker"
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    if marker.exists() and marker.read_text(encoding="utf-8").strip() == today:
        return out  # already ran today

    cutoff_epoch = int(time.time()) - cfg.daily_recency_days * 86400
    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=cfg.daily_recency_days)
    qs = Post.objects.filter(
        Q(created_at_epoch__gte=cutoff_epoch) | Q(created_at__gte=cutoff_dt)
    )
    if staff_handles:
        qs = qs.exclude(author_handle__in=list(staff_handles))
    rows = list(
        qs.order_by("-created_at_epoch", "-created_at").values(
            "tweet_id",
            "text",
            "last_quote_count_seen",
            "last_quote_fetched_at",
        )[:500]
    )
    out["daily_n_candidates"] = len(rows)
    if not rows:
        marker.write_text(today, encoding="utf-8")
        out["daily_ran"] = True
        return out

    try:
        fresh = api.get_tweets_by_ids([r["tweet_id"] for r in rows])
    except Exception as exc:
        logger.warning("daily QT refresh failed: %s", exc)
        out["daily_refresh_error"] = str(exc)
        return out  # no marker — retry next cycle

    n_calls = 0
    n_qts = 0
    n_ingested = 0
    for r in rows:
        tid = r["tweet_id"]
        info = fresh.get(tid)
        if not info:
            continue
        fresh_qc = int(info.get("quote_count") or 0)
        delta = fresh_qc - int(r["last_quote_count_seen"] or 0)
        if delta >= 1:
            since_time = _iso_to_epoch(r["last_quote_fetched_at"])
            try:
                qts = api.get_quote_tweets(
                    tid, since_time=since_time, max_pages=cfg.max_pages
                )
            except Exception as exc:
                logger.warning("daily QT fetch failed for %s: %s", tid, exc)
                continue
            n_calls += 1
            if qts:
                try:
                    ingested = ingest_quote_tweets(
                        runner,
                        qts,
                        tid,
                        r["text"] or "",
                        index=index,
                        brand_search_terms=brand_search_terms,
                    )
                except Exception as exc:
                    logger.warning("daily QT ingest failed for %s: %s", tid, exc)
                    ingested = 0
                n_ingested += ingested
                n_qts += len(qts)
                # Only advance tracking on successful ingest (>0)
                if ingested > 0:
                    update_quote_tracking(tid, fresh_qc)
            else:
                update_quote_tracking(tid, fresh_qc)
            if n_calls >= cfg.daily_call_budget:
                break
        else:
            update_quote_tracking(tid, fresh_qc)

    marker.write_text(today, encoding="utf-8")
    out.update(
        daily_ran=True,
        daily_n_calls=n_calls,
        daily_n_qts_fetched=n_qts,
        daily_n_ingested=n_ingested,
    )
    return out


def run_quote_tweet_channel(
    runner: _Attributable,
    api: TwitterApiClient,
    *,
    index: Any,
    brand_search_terms: dict[str, str],
    enabled_models: list[str],
) -> dict[str, Any]:
    """Run official + daily QT capture; never raises (callers log warnings)."""
    cfg = load_quote_tweet_config()
    staff = staff_handles_set(enabled_models)
    out: dict[str, Any] = {"staff_handles": len(staff)}
    try:
        out.update(
            capture_official_quote_tweets(
                runner,
                api,
                index=index,
                brand_search_terms=brand_search_terms,
                staff_handles=staff,
                cfg=cfg,
            )
        )
    except Exception as exc:
        logger.warning("official QT capture failed: %s", exc)
        out["official_error"] = str(exc)
    try:
        out.update(
            capture_nonofficial_quote_tweets_daily(
                runner,
                api,
                index=index,
                brand_search_terms=brand_search_terms,
                staff_handles=staff,
                cfg=cfg,
            )
        )
    except Exception as exc:
        logger.warning("daily QT capture failed: %s", exc)
        out["daily_error"] = str(exc)
    return out
