"""Tests for monitor.metrics_refresh (plan 2026-08-10-002)."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO = Path(__file__).resolve().parent.parent

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def test_select_due_excludes_young_and_already_refreshed():
    from django.utils import timezone
    from core.models import Post
    from monitor.metrics_refresh import select_due_posts

    now = timezone.now()
    Post.objects.create(tweet_id="old_m", text="x")
    Post.objects.create(tweet_id="young_m", text="y")
    Post.objects.create(tweet_id="done_m", text="z")
    Post.objects.filter(tweet_id="old_m").update(fetched_at=now - timedelta(hours=3))
    Post.objects.filter(tweet_id="young_m").update(fetched_at=now - timedelta(minutes=30))
    Post.objects.filter(tweet_id="done_m").update(
        fetched_at=now - timedelta(hours=5),
        metrics_refreshed_at=now - timedelta(hours=1),
    )

    due = select_due_posts(delay_hours=2.0, per_cycle_cap=200, now=now)
    assert "old_m" in due
    assert "young_m" not in due
    assert "done_m" not in due


def test_select_due_respects_cap():
    from django.utils import timezone
    from core.models import Post
    from monitor.metrics_refresh import select_due_posts

    now = timezone.now()
    for i in range(5):
        tid = f"cap_m_{i}"
        Post.objects.create(tweet_id=tid, text="t")
        Post.objects.filter(tweet_id=tid).update(fetched_at=now - timedelta(hours=10 - i))
    due = select_due_posts(delay_hours=2.0, per_cycle_cap=2, now=now)
    # at least cap size from our seeds (may include other suite rows; filter)
    ours = [t for t in due if t.startswith("cap_m_")]
    assert len(ours) <= 2
    assert ours[0] == "cap_m_0"


def test_run_metrics_refresh_updates_counts_and_stamps():
    from django.utils import timezone
    from core.models import Post
    from monitor.metrics_refresh import run_metrics_refresh
    from x_monitor.config import load_config

    now = timezone.now()
    Post.objects.create(tweet_id="P1_m", text="hello", like_count=1)
    Post.objects.filter(tweet_id="P1_m").update(fetched_at=now - timedelta(hours=3))

    api = MagicMock()
    api.get_tweets_by_ids.return_value = {
        "P1_m": {
            "like_count": 10,
            "retweet_count": 2,
            "reply_count": 3,
            "quote_count": 4,
        }
    }
    cfg = load_config(REPO / "config.yaml")
    out = run_metrics_refresh(api, cfg, now=now)
    assert out["n_refreshed"] >= 1
    p = Post.objects.get(tweet_id="P1_m")
    assert p.like_count == 10
    assert p.retweet_count == 2
    assert p.reply_count == 3
    assert p.quote_count == 4
    assert p.metrics_refreshed_at is not None


def test_run_metrics_refresh_api_error_does_not_stamp():
    from django.utils import timezone
    from core.models import Post
    from monitor.metrics_refresh import run_metrics_refresh
    from x_monitor.config import load_config

    now = timezone.now()
    Post.objects.create(tweet_id="P2_m", text="x")
    Post.objects.filter(tweet_id="P2_m").update(fetched_at=now - timedelta(hours=5))
    api = MagicMock()
    api.get_tweets_by_ids.side_effect = RuntimeError("boom")
    out = run_metrics_refresh(api, load_config(REPO / "config.yaml"), now=now)
    assert out["n_errors"] == 1
    assert Post.objects.get(tweet_id="P2_m").metrics_refreshed_at is None
