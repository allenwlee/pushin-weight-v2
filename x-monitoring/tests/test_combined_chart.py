# {{AGENT_ATTRIBUTION}}
"""Tests for x_monitor.dashboard.serialize_combined_chart (Unit 1, v2.0 plan).

Mirrors the per-model serializer pattern in test_dashboard.py: tmpdir,
real Store, posts with Q1-Q6 source_query_ids, latest_run["finished_at"]
as the now anchor.

serialize_combined_chart(brands, posts_by_brand, *, window_days, latest_run, now)
returns:
    {
        "days": [iso_date_str] * window_days,        # oldest -> newest
        "series": {brand: [int] * window_days},       # total per brand per day
        "stacked": {brand: {signal: [int] * window_days}},  # per signal
        "window_days": int,
        "fetched_at": iso_str,
    }

Conventions (mirror serialize_grid_card):
- now defaults to datetime.now(utc) when latest_run is None; falls back
  to latest_run["finished_at"] when present
- chart_series_keys order = (release, community_question, criticism,
  commenter_capture, other, praise)
- posts with unparseable created_at are silently skipped
- days outside [now - window_days, now) are zero-filled
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from x_monitor.dashboard import serialize_combined_chart
from x_monitor.store import Store


# ---------------------------------------------------------------------------
# Happy path — N brands, mixed signals, full window
# ---------------------------------------------------------------------------


def test_serialize_combined_chart_happy_path_2_brands_30d():
    """2 brands × 30 days, mixed Q1-Q6 posts → correct shape."""
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        store = Store(data / "x.db")
        try:
            now_iso = "2026-06-19T12:00:00+00:00"
            now_dt = datetime.fromisoformat(now_iso)
            # 3 posts for minimax on day "today" (1 Q1 + 1 Q3 + 1 Q6)
            # 2 posts for qwen on day "today - 1d" (1 Q2 + 1 Q4)
            posts = [
                {
                    "tweet_id": "m1", "model_id": "minimax", "author_handle": "u",
                    "text": "x", "favorite_count": 1, "created_at": now_iso,
                    "source_query_id": "Q1",
                },
                {
                    "tweet_id": "m2", "model_id": "minimax", "author_handle": "u",
                    "text": "x", "favorite_count": 1, "created_at": now_iso,
                    "source_query_id": "Q3",
                },
                {
                    "tweet_id": "m3", "model_id": "minimax", "author_handle": "u",
                    "text": "x", "favorite_count": 1, "created_at": now_iso,
                    "source_query_id": "Q6",
                },
                {
                    "tweet_id": "q1", "model_id": "qwen", "author_handle": "u",
                    "text": "x", "favorite_count": 1,
                    "created_at": "2026-06-18T12:00:00+00:00",
                    "source_query_id": "Q2",
                },
                {
                    "tweet_id": "q2", "model_id": "qwen", "author_handle": "u",
                    "text": "x", "favorite_count": 1,
                    "created_at": "2026-06-18T12:00:00+00:00",
                    "source_query_id": "Q4",
                },
            ]
            store.insert_posts(posts)
            latest = {"degraded": {}, "finished_at": now_iso}
            out = serialize_combined_chart(
                ["minimax", "qwen"],
                {
                    "minimax": store.get_all_posts("minimax"),
                    "qwen": store.get_all_posts("qwen"),
                },
                window_days=30,
                latest_run=latest,
            )
            assert len(out["days"]) == 30
            assert out["window_days"] == 30
            assert set(out["series"].keys()) == {"minimax", "qwen"}
            assert set(out["stacked"].keys()) == {"minimax", "qwen"}
            # Last day = today for minimax: total 3, release=1, criticism=1, praise=1
            minimax_total_today = out["series"]["minimax"][-1]
            assert minimax_total_today == 3
            assert out["stacked"]["minimax"]["release"][-1] == 1
            assert out["stacked"]["minimax"]["criticism"][-1] == 1
            assert out["stacked"]["minimax"]["praise"][-1] == 1
            # Day -1 for qwen: total 2, community_question=1, commenter_capture=1
            assert out["series"]["qwen"][-2] == 2
            assert out["stacked"]["qwen"]["community_question"][-2] == 1
            assert out["stacked"]["qwen"]["commenter_capture"][-2] == 1
            # All other days for both brands are zero
            for i in range(30):
                if i != 29:  # today
                    assert out["series"]["minimax"][i] == 0
                if i != 28:  # yesterday
                    assert out["series"]["qwen"][i] == 0
        finally:
            store.close()


def test_serialize_combined_chart_includes_all_six_signals_per_brand():
    """Every brand in `stacked` has all 6 signal keys, even if empty."""
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            out = serialize_combined_chart(
                ["minimax"],
                {"minimax": []},
                window_days=14,
                latest_run=None,
                now=datetime(2026, 6, 19, tzinfo=timezone.utc),
            )
            expected_signals = {
                "release", "community_question", "criticism",
                "commenter_capture", "other", "praise",
            }
            assert set(out["stacked"]["minimax"].keys()) == expected_signals
            for sig in expected_signals:
                assert out["stacked"]["minimax"][sig] == [0] * 14
        finally:
            store.close()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_serialize_combined_chart_brand_with_zero_posts_renders_zero_line():
    """A brand with no posts still appears in series (zero-filled)."""
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            out = serialize_combined_chart(
                ["minimax", "ghost_brand"],
                {"minimax": [], "ghost_brand": []},
                window_days=7,
                latest_run=None,
                now=datetime(2026, 6, 19, tzinfo=timezone.utc),
            )
            assert "ghost_brand" in out["series"]
            assert out["series"]["ghost_brand"] == [0] * 7
            assert "ghost_brand" in out["stacked"]
        finally:
            store.close()


def test_serialize_combined_chart_skips_unparseable_timestamps():
    """Posts with bad created_at are silently skipped, not crash."""
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            posts = [
                {
                    "tweet_id": "ok", "model_id": "minimax", "author_handle": "u",
                    "text": "x", "favorite_count": 1,
                    "created_at": "2026-06-19T12:00:00+00:00",
                    "source_query_id": "Q1",
                },
                {
                    "tweet_id": "bad", "model_id": "minimax", "author_handle": "u",
                    "text": "x", "favorite_count": 1,
                    "created_at": "totally bogus",
                    "source_query_id": "Q2",
                },
            ]
            store.insert_posts(posts)
            out = serialize_combined_chart(
                ["minimax"],
                {"minimax": store.get_all_posts("minimax")},
                window_days=7,
                latest_run=None,
                now=datetime(2026, 6, 19, tzinfo=timezone.utc),
            )
            # Only the good post counts
            assert out["series"]["minimax"][-1] == 1
            assert out["stacked"]["minimax"]["release"][-1] == 1
        finally:
            store.close()


def test_serialize_combined_chart_window_360d_with_only_14d_history():
    """window_days=360 with sparse history: early days zero-fill, no error."""
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            now_iso = "2026-06-19T12:00:00+00:00"
            posts = [
                {
                    "tweet_id": "f", "model_id": "minimax", "author_handle": "u",
                    "text": "x", "favorite_count": 1, "created_at": now_iso,
                    "source_query_id": "Q1",
                }
            ]
            store.insert_posts(posts)
            out = serialize_combined_chart(
                ["minimax"],
                {"minimax": store.get_all_posts("minimax")},
                window_days=360,
                latest_run={"degraded": {}, "finished_at": now_iso},
            )
            assert len(out["days"]) == 360
            # 359 days are zero, last day has 1 post
            assert sum(out["series"]["minimax"]) == 1
            assert out["series"]["minimax"][-1] == 1
        finally:
            store.close()


# ---------------------------------------------------------------------------
# Error / fallback paths
# ---------------------------------------------------------------------------


def test_serialize_combined_chart_latest_run_none_uses_now():
    """latest_run=None: anchor to now parameter (no exception)."""
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            out = serialize_combined_chart(
                ["minimax"],
                {"minimax": []},
                window_days=7,
                latest_run=None,
                now=datetime(2026, 6, 19, tzinfo=timezone.utc),
            )
            assert len(out["days"]) == 7
            assert out["days"][-1] == "2026-06-19"
        finally:
            store.close()


def test_serialize_combined_chart_latest_run_finished_at_anchors_when_now_is_none():
    """When now is None, latest_run["finished_at"] anchors the window.

    Matches the serialize_grid_card convention: explicit `now` test
    seam always wins (callers wanting latest_run behavior pass now=None).
    """
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            now_iso = "2026-06-15T12:00:00+00:00"
            posts = [
                {
                    "tweet_id": "f", "model_id": "minimax", "author_handle": "u",
                    "text": "x", "favorite_count": 1, "created_at": now_iso,
                    "source_query_id": "Q1",
                }
            ]
            store.insert_posts(posts)
            out = serialize_combined_chart(
                ["minimax"],
                {"minimax": store.get_all_posts("minimax")},
                window_days=7,
                latest_run={"degraded": {}, "finished_at": now_iso},
                now=None,  # explicit: defer to latest_run
            )
            # Anchor is now_iso (June 15), so days end at 2026-06-15
            assert out["days"][-1] == "2026-06-15"
            # The post is on 2026-06-15 (last day of window)
            assert out["series"]["minimax"][-1] == 1
        finally:
            store.close()


def test_serialize_combined_chart_explicit_now_overrides_latest_run():
    """When now is explicitly passed, it wins over latest_run (test seam)."""
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            now_iso = "2026-06-15T12:00:00+00:00"
            now_dt = datetime(2026, 6, 19, tzinfo=timezone.utc)
            out = serialize_combined_chart(
                ["minimax"],
                {"minimax": []},
                window_days=7,
                latest_run={"degraded": {}, "finished_at": now_iso},
                now=now_dt,  # explicit: caller controls
            )
            # Anchor is now_dt (June 19), not now_iso (June 15)
            assert out["days"][-1] == "2026-06-19"
        finally:
            store.close()


# ---------------------------------------------------------------------------
# Integration: locale is ignored (D6 in plan)
# ---------------------------------------------------------------------------


def test_serialize_combined_chart_ignores_locale_kwarg_if_passed():
    """Combined chart data is locale-independent (no top posts in payload)."""
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            out = serialize_combined_chart(
                ["minimax"],
                {"minimax": []},
                window_days=14,
                latest_run=None,
                now=datetime(2026, 6, 19, tzinfo=timezone.utc),
            )
            # No locale-dependent keys in payload
            assert "display_locale" not in out
            assert "top_posts" not in out
        finally:
            store.close()