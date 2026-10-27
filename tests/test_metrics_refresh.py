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
    assert ours[0] == "cap_m_4"


def test_recent_due_post_is_not_starved_by_unavailable_historical_backlog():
    from django.utils import timezone

    from core.models import Post
    from monitor.metrics_refresh import select_due_posts

    now = timezone.now()
    for tweet_id, age in [("historical_missing", timedelta(days=90)),
                          ("recent_due", timedelta(minutes=20))]:
        Post.objects.create(tweet_id=tweet_id)
        Post.objects.filter(tweet_id=tweet_id).update(fetched_at=now - age)

    assert select_due_posts(delay_hours=0.25, per_cycle_cap=1, now=now) == ["recent_due"]


def test_early_refresh_excludes_expired_and_historical_backfill_posts():
    from django.utils import timezone

    from core.models import Post
    from monitor.metrics_refresh import select_due_posts

    now = timezone.now()
    for tweet_id in ["expired", "backfill", "early", "too_young"]:
        Post.objects.create(tweet_id=tweet_id, created_at=now - timedelta(minutes=25))
        Post.objects.filter(tweet_id=tweet_id).update(fetched_at=now - timedelta(minutes=20))
    Post.objects.filter(tweet_id="expired").update(fetched_at=now - timedelta(hours=25))
    Post.objects.filter(tweet_id="backfill").update(created_at=now - timedelta(days=30))
    Post.objects.filter(tweet_id="too_young").update(fetched_at=now - timedelta(minutes=14))

    assert select_due_posts(delay_hours=0.25, per_cycle_cap=200, now=now) == ["early"]


def test_refresh_persists_actual_http_lookup_counts_and_skips_unavailable(monkeypatch):
    import json

    import requests
    from django.utils import timezone

    from core.models import Post
    from monitor.metrics_refresh import run_metrics_refresh
    from x_monitor.config import load_config
    from x_monitor.x_client import XClient

    now = timezone.now()
    for tweet_id in ["2111255857925349616", "2111255830230368630"]:
        Post.objects.create(tweet_id=tweet_id, like_count=1)
        Post.objects.filter(tweet_id=tweet_id).update(fetched_at=now - timedelta(minutes=20))
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs["params"]))
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps({"status": "success", "code": 0, "tweets": [
            {"id": "", "unavailable": True},
            {"id": "2111255857925349616", "likeCount": 10, "retweetCount": 2,
             "replyCount": 3, "quoteCount": 4, "viewCount": 500, "bookmarkCount": 6},
        ]}).encode()
        return response

    monkeypatch.setattr("x_monitor.x_client.requests.get", get)
    out = run_metrics_refresh(XClient(api_key="test", max_retries=0),
                              load_config(REPO / "config.yaml"), now=now)
    assert len(calls) == 1
    assert set(calls[0][1]["tweet_ids"].split(",")) == {"2111255857925349616", "2111255830230368630"}
    assert (out["n_refreshed"], out["n_missing"], out["n_errors"]) == (1, 1, 0)
    post = Post.objects.get(tweet_id="2111255857925349616")
    assert (post.like_count, post.retweet_count, post.reply_count, post.quote_count,
            post.view_count, post.bookmark_count) == (10, 2, 3, 4, 500, 6)
    assert post.metrics_refreshed_at == now
    missing = Post.objects.get(tweet_id="2111255830230368630")
    assert missing.metrics_refreshed_at is None
    assert missing.like_count == 1


def test_http_200_provider_error_is_reported_without_stamping_post(monkeypatch):
    import requests
    from django.utils import timezone

    from core.models import Post
    from monitor.metrics_refresh import run_metrics_refresh
    from x_monitor.config import load_config
    from x_monitor.x_client import XClient

    now = timezone.now()
    Post.objects.create(tweet_id="2111255857925349616", like_count=7)
    Post.objects.filter(tweet_id="2111255857925349616").update(
        fetched_at=now - timedelta(minutes=20)
    )
    response = requests.Response()
    response.status_code = 200
    response._content = b'{"status":"error","tweets":[],"msg":"provider failed"}'
    monkeypatch.setattr("x_monitor.x_client.requests.get", lambda *_args, **_kwargs: response)

    out = run_metrics_refresh(
        XClient(api_key="test", max_retries=0),
        load_config(REPO / "config.yaml"), now=now,
    )

    assert (out["n_refreshed"], out["n_missing"], out["n_errors"], out["n_deferred"]) == (0, 0, 1, 1)
    post = Post.objects.get(tweet_id="2111255857925349616")
    assert post.metrics_refreshed_at is None
    assert post.like_count == 7


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


def test_run_metrics_refresh_defers_before_a_request_that_cannot_fit():
    from django.utils import timezone

    from core.models import Post
    from monitor.metrics_refresh import run_metrics_refresh
    from x_monitor.config import load_config

    class NoWindow:
        requested_seconds = None

        def can_start(self, seconds):
            self.requested_seconds = seconds
            return False

    now = timezone.now()
    Post.objects.create(tweet_id="late_metrics", text="x")
    Post.objects.filter(tweet_id="late_metrics").update(
        fetched_at=now - timedelta(hours=5)
    )
    api = MagicMock(timeout_s=60, max_retries=2)
    deadline = NoWindow()

    out = run_metrics_refresh(
        api,
        load_config(REPO / "config.yaml"),
        now=now,
        deadline=deadline,
    )

    assert deadline.requested_seconds == 188
    assert out["n_deferred"] >= 1
    api.get_tweets_by_ids.assert_not_called()


def test_run_metrics_refresh_rechecks_deadline_before_each_chunk():
    from django.utils import timezone

    from core.models import Post
    from monitor.metrics_refresh import run_metrics_refresh
    from x_monitor.config import load_config

    class OneWindow:
        checks = 0

        def can_start(self, seconds):
            assert seconds == 188
            self.checks += 1
            return self.checks == 1

    class RecordingApi:
        timeout_s = 60
        max_retries = 2

        def __init__(self):
            self.calls = []

        def get_tweets_by_ids(self, ids):
            self.calls.append(list(ids))
            return {}

    now = timezone.now()
    for index in range(55):
        tweet_id = f"chunked_metrics_{index:02d}"
        Post.objects.create(tweet_id=tweet_id, text="x")
        Post.objects.filter(tweet_id=tweet_id).update(
            fetched_at=now - timedelta(hours=5)
        )
    api = RecordingApi()

    out = run_metrics_refresh(
        api,
        load_config(REPO / "config.yaml"),
        now=now,
        deadline=OneWindow(),
    )

    assert len(api.calls) == 1
    assert len(api.calls[0]) == 50
    assert out["n_deferred"] == 5
    assert out["n_missing"] == 50


def test_later_chunk_failure_preserves_updates_from_earlier_chunk(monkeypatch):
    from monitor import metrics_refresh
    from x_monitor.config import load_config

    due = [f"partial-{index:02d}" for index in range(21)]
    calls: list[list[str]] = []
    applied: list[str] = []

    class Api:
        timeout_s = 60
        max_retries = 2

        def get_tweets_by_ids(self, ids):
            calls.append(list(ids))
            if len(calls) == 2:
                raise RuntimeError("second chunk failed")
            return {tweet_id: {"like_count": 1} for tweet_id in ids}

    monkeypatch.setattr(metrics_refresh, "_TWEETS_BY_IDS_CHUNK", 20)
    monkeypatch.setattr(metrics_refresh, "select_due_posts", lambda **_kwargs: due)
    monkeypatch.setattr(
        metrics_refresh,
        "apply_metrics_to_post",
        lambda tweet_id, _info, **_kwargs: applied.append(tweet_id) or True,
    )

    out = metrics_refresh.run_metrics_refresh(
        Api(), load_config(REPO / "config.yaml")
    )

    assert calls == [due[:20], due[20:]]
    assert applied == due[:20]
    assert out["n_refreshed"] == 20
    assert out["n_errors"] == 1
    assert out["n_deferred"] == 1
