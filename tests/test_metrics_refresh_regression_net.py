"""Full regression net for plan 2026-08-10-002 (pins P-U*, P-A*, P-C*)."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO / "config.yaml"


def _django_setup():
    import os
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
    os.environ.setdefault("TWITTERAPI_IO_API_KEY", "dummy_for_regression_test")
    import django
    if not django.apps.apps.ready:
        django.setup()


# ---------- P-U* unchanged (no DB) ----------

def test_P_U1_post_engagement_columns_exist():
    """P-U1: Post still has engagement columns."""
    _django_setup()
    from core.models import Post
    names = {f.name for f in Post._meta.get_fields() if hasattr(f, "name")}
    for col in (
        "like_count",
        "retweet_count",
        "reply_count",
        "quote_count",
        "view_count",
        "bookmark_count",
        "metrics_refreshed_at",
    ):
        assert col in names, col


def test_P_U2_get_tweets_by_ids_maps_counts():
    """P-U2: by-ids maps likeCount→like_count etc."""
    from x_monitor.apify import TwitterApiClient

    client = TwitterApiClient(api_key="x")
    payload = {
        "tweets": [
            {
                "id": "99",
                "likeCount": 5,
                "retweetCount": 1,
                "replyCount": 2,
                "quoteCount": 3,
            }
        ]
    }
    with patch.object(client, "_get", return_value=payload):
        out = client.get_tweets_by_ids(["99"])
    assert out["99"]["like_count"] == 5
    assert out["99"]["retweet_count"] == 1
    assert out["99"]["reply_count"] == 2
    assert out["99"]["quote_count"] == 3


def test_P_U3_plan_calls_produces_calls():
    """P-U3: cycle still plans search calls."""
    _django_setup()
    from monitor.cycle import plan_calls_for_cycle
    from x_monitor.config import load_config

    calls = plan_calls_for_cycle(cfg=load_config(CONFIG_PATH))
    assert isinstance(calls, list)
    assert len(calls) >= 1


def test_P_U5_cursor_config_defaults():
    """P-U5: cursor defaults lookback 0.25h, overlap 60s."""
    from x_monitor.config import load_config

    cfg = load_config(CONFIG_PATH)
    assert cfg.cycle.max_lookback_hours == 0.25
    assert cfg.cycle.cursor_overlap_seconds == 60


def test_P_A5_A6_metrics_refresh_config_defaults():
    """P-A5/P-A6: delay 2.0, cap 200."""
    from x_monitor.config import MetricsRefreshConfig, load_config

    assert MetricsRefreshConfig().delay_hours == 2.0
    assert MetricsRefreshConfig().per_cycle_cap == 200
    cfg = load_config(CONFIG_PATH)
    assert cfg.metrics_refresh.delay_hours == 2.0
    assert cfg.metrics_refresh.per_cycle_cap == 200


def test_P_A4_quote_tweets_channel_is_noop():
    """P-A4: run_quote_tweet_channel does not call get_quote_tweets."""
    _django_setup()
    from monitor.quote_tweets import run_quote_tweet_channel

    api = MagicMock()
    runner = MagicMock()
    out = run_quote_tweet_channel(
        runner,
        api,
        index=None,
        brand_search_terms={},
        enabled_models=["deepseek"],
    )
    assert out.get("disabled") is True
    api.get_quote_tweets.assert_not_called()
    api.get_tweets_by_ids.assert_not_called()


def test_P_A2_A3_cycle_source_uses_metrics_not_qt_capture():
    """P-A2/P-A3: cycle source uses metrics_refresh, not QT capture."""
    src = (REPO / "monitor/cycle.py").read_text()
    assert "run_metrics_refresh" in src
    assert "capture_official_quote_tweets" not in src
    assert "capture_nonofficial_quote_tweets_daily" not in src
    assert "run_quote_tweet_channel" not in src


# ---------- Postgres-backed pins ----------

@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_P_A7_A8_A9_due_selection():
    """P-A7/A8/A9: due / young / once-only."""
    from django.utils import timezone
    from core.models import Post
    from monitor.metrics_refresh import select_due_posts

    now = timezone.now()
    Post.objects.create(tweet_id="due1_r", text="a")
    Post.objects.create(tweet_id="young1_r", text="b")
    Post.objects.create(tweet_id="done1_r", text="c")
    Post.objects.filter(tweet_id="due1_r").update(fetched_at=now - timedelta(hours=3))
    Post.objects.filter(tweet_id="young1_r").update(fetched_at=now - timedelta(minutes=20))
    Post.objects.filter(tweet_id="done1_r").update(
        fetched_at=now - timedelta(hours=4),
        metrics_refreshed_at=now,
    )
    due = select_due_posts(delay_hours=2.0, per_cycle_cap=50, now=now)
    assert "due1_r" in due
    assert "young1_r" not in due
    assert "done1_r" not in due


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_P_C1_C2_cycle_metrics_refresh_not_quotes():
    """P-C1/P-C2: metrics refresh uses by-ids for due only; never get_quote_tweets."""
    from django.utils import timezone
    from core.models import Post
    from monitor.metrics_refresh import run_metrics_refresh
    from x_monitor.config import load_config

    now = timezone.now()
    Post.objects.create(tweet_id="DUE99_r", text="old")
    Post.objects.filter(tweet_id="DUE99_r").update(fetched_at=now - timedelta(hours=5))
    Post.objects.create(tweet_id="YOUNG99_r", text="new")
    Post.objects.filter(tweet_id="YOUNG99_r").update(fetched_at=now - timedelta(minutes=10))

    api = MagicMock()
    api.get_tweets_by_ids.return_value = {
        "DUE99_r": {
            "like_count": 9,
            "retweet_count": 0,
            "reply_count": 0,
            "quote_count": 1,
        }
    }
    out = run_metrics_refresh(api, load_config(CONFIG_PATH), now=now)
    assert out["n_refreshed"] >= 1
    called_ids = api.get_tweets_by_ids.call_args[0][0]
    assert "DUE99_r" in called_ids
    assert "YOUNG99_r" not in called_ids
    api.get_quote_tweets.assert_not_called()


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_P_C3_second_run_skips_stamped():
    """P-C3: second refresh does not re-fetch stamped ids."""
    from django.utils import timezone
    from core.models import Post
    from monitor.metrics_refresh import run_metrics_refresh
    from x_monitor.config import load_config

    now = timezone.now()
    Post.objects.create(tweet_id="ONCE_r", text="x")
    Post.objects.filter(tweet_id="ONCE_r").update(fetched_at=now - timedelta(hours=4))
    api = MagicMock()
    api.get_tweets_by_ids.return_value = {
        "ONCE_r": {
            "like_count": 1,
            "retweet_count": 0,
            "reply_count": 0,
            "quote_count": 0,
        }
    }
    cfg = load_config(CONFIG_PATH)
    run_metrics_refresh(api, cfg, now=now)
    api.reset_mock()
    api.get_tweets_by_ids.return_value = {}
    out2 = run_metrics_refresh(api, cfg, now=now)
    if api.get_tweets_by_ids.called:
        ids = api.get_tweets_by_ids.call_args[0][0]
        assert "ONCE_r" not in ids
    assert out2["n_refreshed"] == 0
