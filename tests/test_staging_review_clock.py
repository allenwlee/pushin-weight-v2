from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings

from core.models import Brand, JobListing, Post, PostBrand
from monitor import views

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_projection_caches():
    views._clear_home_pulse_cache()
    yield
    views._clear_home_pulse_cache()


def _stale_post(*, tweet_id: str, created_at: datetime) -> None:
    brand, _created = Brand.objects.get_or_create(
        nickname="minimax",
        defaults={"display_name": "MiniMax"},
    )
    post = Post.objects.create(
        tweet_id=tweet_id,
        text="staging review fixture",
        text_en="staging review fixture",
        lang_detected="en",
        created_at=created_at,
    )
    PostBrand.objects.create(post=post, brand=brand)


@override_settings(
    OLLIJA_STAGING_MODE=True,
    STAGING_REVIEW_DATA_CLOCK_ENABLED=True,
    OLLIJA_STAGING_ALLOWED_EMAILS=frozenset({"owner@example.com"}),
)
def test_staging_one_day_feed_and_chart_follow_latest_post_across_locales():
    latest = datetime(2026, 9, 18, 14, 45, 49, tzinfo=UTC)
    _stale_post(tweet_id="staging-clock-latest", created_at=latest)
    _stale_post(
        tweet_id="staging-clock-in-window",
        created_at=latest - timedelta(hours=23),
    )
    _stale_post(
        tweet_id="staging-clock-too-old",
        created_at=latest - timedelta(hours=25),
    )

    client = Client(HTTP_HOST="localhost")
    user = get_user_model().objects.create_user(
        username="staging-clock-owner",
        email="owner@example.com",
        password="unused",
    )
    client.force_login(user)
    english = client.get("/feed/?window=1&locale=en", secure=True).json()
    japanese = client.get("/feed/?window=1&locale=ja", secure=True).json()
    chart = client.get("/chart/?window=1&locale=ja", secure=True).json()
    homepage = client.get("/?window=1&locale=en", secure=True)

    expected = ["staging-clock-latest", "staging-clock-in-window"]
    assert [row["tweet_id"] for row in english["rows"]] == expected
    assert [row["tweet_id"] for row in japanese["rows"]] == expected
    assert english["rows"][0]["meta_text"] == "just now"
    assert chart["computed_at"] == (latest + timedelta(microseconds=1)).isoformat()
    assert chart["totals"]["minimax"] == 2
    assert homepage.status_code == 200
    assert (
        f'data-pw-feed-now="{(latest + timedelta(microseconds=1)).isoformat()}"'
        in homepage.content.decode()
    )


@override_settings(
    OLLIJA_STAGING_MODE=True,
    STAGING_REVIEW_DATA_CLOCK_ENABLED=True,
)
def test_staging_receipt_cutoff_ignores_later_sparse_probe_posts(monkeypatch):
    copied_latest = datetime(2026, 9, 18, 14, 45, 49, tzinfo=UTC)
    review_now = copied_latest + timedelta(microseconds=1)
    _stale_post(tweet_id="copied-full-day", created_at=copied_latest)
    _stale_post(
        tweet_id="later-sparse-probe",
        created_at=copied_latest + timedelta(hours=12),
    )
    monkeypatch.setattr(
        views,
        "_staging_refresh_review_horizon",
        lambda: review_now,
    )

    rows, *_ = views._feed_page_wire(locale="en", window_days=1, filters={})

    assert [row["tweet_id"] for row in rows] == ["copied-full-day"]


@override_settings(
    OLLIJA_STAGING_MODE=True,
    STAGING_REVIEW_DATA_CLOCK_ENABLED=True,
)
def test_staging_review_clock_preserves_official_job_source_dates():
    latest = datetime(2026, 9, 18, 14, 45, 49, tzinfo=UTC)
    posted_at = latest - timedelta(days=5)
    _stale_post(tweet_id="staging-clock-job-anchor", created_at=latest)
    brand = Brand.objects.create(nickname="qwen", display_name="Qwen")
    job = JobListing.objects.create(
        brand=brand,
        hiring_organization="Qwen",
        source_key="qwen",
        source_name="Qwen",
        source_listing_id="historical-role",
        canonical_url="https://talent.quark.cn/job/historical-role",
        application_url="https://talent.quark.cn/job/historical-role/apply",
        application_route_kind="direct_url",
        title="Historical role",
        first_seen_at=posted_at,
        last_seen_at=posted_at,
        posted_at=posted_at,
        status="open",
        listing_identity="a" * 64,
    )

    one_day, *_ = views._feed_page_wire(
        locale="en",
        window_days=1,
        filters={"post_types": ["job_listings"]},
    )
    seven_days, *_ = views._feed_page_wire(
        locale="en",
        window_days=7,
        filters={"post_types": ["job_listings"]},
    )

    assert one_day == []
    assert [row["title"] for row in seven_days] == ["Historical role"]
    job.refresh_from_db()
    assert job.posted_at == posted_at


@override_settings(
    OLLIJA_STAGING_MODE=False,
    STAGING_REVIEW_DATA_CLOCK_ENABLED=True,
)
def test_production_never_uses_the_staging_review_clock(monkeypatch):
    wall_now = datetime(2026, 9, 19, 18, 0, tzinfo=UTC)
    _stale_post(
        tweet_id="production-clock-stays-real",
        created_at=wall_now - timedelta(days=2),
    )
    monkeypatch.setattr(views.django_timezone, "now", lambda: wall_now)

    rows, _cursor, _has_more, _normalized = views._feed_page_wire(
        locale="en",
        window_days=1,
        filters={"brands": ["minimax"]},
    )

    assert rows == []
