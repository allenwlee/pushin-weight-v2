"""Tests for monitor.quote_tweets — v2 quote-tweet channel (v1 parity)."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from monitor import quote_tweets as qt
from x_monitor.config import QuoteTweetConfig


def test_iso_to_epoch_roundtrip():
    assert qt._iso_to_epoch(None) is None
    assert qt._iso_to_epoch("") is None
    dt = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)
    expected = int(dt.timestamp())
    assert qt._iso_to_epoch("2026-07-01T12:00:00+00:00") == expected
    assert qt._iso_to_epoch(dt) == expected
    assert qt._iso_to_epoch(expected) == expected


def test_ingest_attaches_parent_text_when_quoted_missing():
    runner = MagicMock()
    # attribute leaves items attributed
    def _attr(items, index, terms):
        for it in items:
            it["_unattributed"] = False
            it["brand_ids"] = ["glm"]
        return 1

    runner._attribute_items.side_effect = _attr
    runner._persist_items.return_value = (1, 0, 1, 0)

    items = [
        {
            "id": "qt1",
            "text": "🔥",
            "quoted_status_id": "parent1",
            # no quoted_text — should attach parent
        }
    ]
    n = qt.ingest_quote_tweets(
        runner,
        items,
        "parent1",
        "GLM 5.2 is great",
        index=None,
        brand_search_terms={},
    )
    assert n == 1
    assert items[0]["quoted_text"] == "GLM 5.2 is great"
    runner._persist_items.assert_called_once()


def test_ingest_does_not_overwrite_foreign_quote():
    runner = MagicMock()

    def _attr(items, index, terms):
        for it in items:
            it["_unattributed"] = True  # filtered out
        return 0

    runner._attribute_items.side_effect = _attr
    items = [
        {
            "id": "qt1",
            "text": "🔥",
            "quoted_status_id": "other_parent",
        }
    ]
    n = qt.ingest_quote_tweets(
        runner,
        items,
        "parent1",
        "parent body",
        index=None,
        brand_search_terms={},
    )
    assert n == 0
    assert items[0].get("quoted_text") in (None, "")
    runner._persist_items.assert_not_called()


def test_official_capture_skips_below_delta(django_db_setup=None):
    """When quote_count growth < official_delta, do not call get_quote_tweets."""
    cfg = QuoteTweetConfig(official_delta=5, track_recency_days=14, official_call_budget=20)
    runner = MagicMock()
    api = MagicMock()
    api.get_tweets_by_ids.return_value = {
        "P1": {"quote_count": 7, "retweet_count": 0},
    }
    # Patch Post queryset to return one tracked parent
    fake_row = {
        "tweet_id": "P1",
        "text": "official post",
        "last_quote_count_seen": 5,  # delta=2 < 5
        "last_quote_fetched_at": None,
    }
    with (
        patch.object(qt.Post.objects, "filter") as mock_filter,
        patch.object(qt, "update_quote_tracking") as mock_track,
    ):
        chain = mock_filter.return_value.filter.return_value
        chain.values.return_value = [fake_row]
        out = qt.capture_official_quote_tweets(
            runner,
            api,
            index=None,
            brand_search_terms={},
            staff_handles={"Zai_org"},
            cfg=cfg,
        )
    assert out["official_n_tracked"] == 1
    assert out.get("official_n_calls", 0) == 0
    api.get_quote_tweets.assert_not_called()
    mock_track.assert_not_called()


def test_official_capture_fetches_when_delta_met():
    cfg = QuoteTweetConfig(official_delta=5, max_pages=2, official_call_budget=10)
    runner = MagicMock()

    def _attr(items, index, terms):
        for it in items:
            it["_unattributed"] = False
            it["brand_ids"] = ["glm"]
        return len(items)

    runner._attribute_items.side_effect = _attr
    runner._persist_items.return_value = (1, 0, 1, 0)
    api = MagicMock()
    api.get_tweets_by_ids.return_value = {"P1": {"quote_count": 12}}
    api.get_quote_tweets.return_value = [
        {"id": "QT1", "text": "nice", "quoted_status_id": "P1"},
    ]
    fake_row = {
        "tweet_id": "P1",
        "text": "GLM launch",
        "last_quote_count_seen": 5,  # delta=7 >= 5
        "last_quote_fetched_at": None,
    }
    with (
        patch.object(qt.Post.objects, "filter") as mock_filter,
        patch.object(qt, "update_quote_tracking") as mock_track,
    ):
        chain = mock_filter.return_value.filter.return_value
        chain.values.return_value = [fake_row]
        out = qt.capture_official_quote_tweets(
            runner,
            api,
            index=None,
            brand_search_terms={"glm": "glm"},
            staff_handles={"Zai_org"},
            cfg=cfg,
        )
    assert out["official_n_calls"] == 1
    assert out["official_n_qts_fetched"] == 1
    assert out["official_n_ingested"] == 1
    api.get_quote_tweets.assert_called_once()
    mock_track.assert_called_once()


def test_daily_marker_short_circuits(tmp_path, settings):
    cfg = QuoteTweetConfig(daily_enabled=True)
    today = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    ).date().isoformat()
    marker = tmp_path / "_qt_daily_marker"
    marker.write_text(today, encoding="utf-8")
    with patch.object(qt, "_data_dir", return_value=tmp_path):
        out = qt.capture_nonofficial_quote_tweets_daily(
            MagicMock(),
            MagicMock(),
            index=None,
            brand_search_terms={},
            staff_handles=set(),
            cfg=cfg,
        )
    assert out == {"daily_ran": False}


def test_run_quote_tweet_channel_is_disabled_noop():
    """AFTER plan 2026-08-10-002: channel is metrics-only noop (no QT regimes)."""
    runner = MagicMock()
    api = MagicMock()
    out = qt.run_quote_tweet_channel(
        runner,
        api,
        index=None,
        brand_search_terms={},
        enabled_models=["glm"],
    )
    assert out.get("disabled") is True
    assert out.get("official_n_ingested") == 0
    assert out.get("daily_n_ingested") == 0
    api.get_tweets_by_ids.assert_not_called()
    api.get_quote_tweets.assert_not_called()
