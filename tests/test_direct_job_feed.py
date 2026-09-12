from __future__ import annotations

from datetime import timedelta

import pytest
from django.template.loader import render_to_string
from django.utils import timezone

from core.models import Brand, JobListing, Post, PostBrand
from monitor.views import (
    _build_home_chart_payload,
    _clear_home_pulse_cache,
    _encode_feed_cursor_values,
    _feed_page_wire,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_chart_cache():
    _clear_home_pulse_cache()
    yield
    _clear_home_pulse_cache()


def _job(*, brand: Brand, title: str, seen_at=None) -> JobListing:
    seen_at = seen_at or timezone.now() - timedelta(minutes=5)
    return JobListing.objects.create(
        brand=brand,
        hiring_organization=brand.display_name,
        source_key="qwen",
        source_name="Qwen",
        source_listing_id=title,
        canonical_url=f"https://talent.quark.cn/job/{title}",
        application_url=f"https://talent.quark.cn/job/{title}/apply",
        application_route_kind="direct_url",
        title=title,
        description_text="Build frontier models",
        locations=["Hangzhou"],
        first_seen_at=seen_at,
        last_seen_at=seen_at,
        posted_at=seen_at,
        status="open",
        listing_identity=(title.encode().hex() + "0" * 64)[:64],
    )


def test_direct_job_is_in_all_and_jobs_feed_but_not_other_post_type():
    brand = Brand.objects.create(nickname="qwen", display_name="Qwen")
    _job(brand=brand, title="Research Engineer")

    all_rows, _, _, _ = _feed_page_wire(locale="en", window_days=1, filters={})
    job_rows, _, _, _ = _feed_page_wire(
        locale="en", window_days=1, filters={"post_types": ["job_listings"]}
    )
    release_rows, _, _, _ = _feed_page_wire(
        locale="en", window_days=1, filters={"post_types": ["model_releases"]}
    )
    assert [row["title"] for row in all_rows] == ["Research Engineer"]
    assert [row["title"] for row in job_rows] == ["Research Engineer"]
    assert release_rows == []
    assert job_rows[0]["source_kind"] == "official_job"
    assert job_rows[0]["post_type_keys"] == ["job_listings"]


def test_direct_job_ssr_links_only_to_official_source():
    brand = Brand.objects.create(nickname="qwen", display_name="Qwen")
    _job(brand=brand, title="Safety Researcher")
    rows, _, _, _ = _feed_page_wire(locale="en", window_days=1, filters={})
    html = render_to_string(
        "monitor/_feed_initial_v22.html",
        {
            "feed": {"rows": rows},
            "active_locale": "en",
            "is_zh_chrome": False,
        },
    )
    assert "talent.quark.cn/job/Safety%20Researcher/apply" not in html
    assert "https://talent.quark.cn/job/Safety Researcher/apply" in html
    assert "x.com/i/web/status" not in html
    assert "View official job" in html


def test_direct_job_legacy_brand_table_is_source_aware():
    brand = Brand.objects.create(nickname="qwen", display_name="Qwen")
    _job(brand=brand, title="Brand Safety Researcher")
    rows, _, _, _ = _feed_page_wire(
        locale="en",
        window_days=1,
        filters={},
        brand_nickname="qwen",
    )
    html = render_to_string(
        "monitor/_feed_initial_legacy.html",
        {
            "feed": {"rows": rows},
            "active_locale": "en",
        },
    )
    assert 'data-source-kind="official_job"' in html
    assert "Brand Safety Researcher" in html
    assert "View official job" in html
    assert "x.com/i/status" not in html


def test_home_chart_counts_direct_jobs_with_the_same_filter_contract():
    now = timezone.now()
    brand = Brand.objects.create(nickname="qwen", display_name="Qwen")
    _job(brand=brand, title="Chart role", seen_at=now - timedelta(minutes=2))
    projection = [
        {
            "nickname": "qwen",
            "display_name": "Qwen",
            "display_name_en": "Qwen",
            "display_name_zh_cn": "通义千问",
            "accent_color": "#000000",
        }
    ]
    payload = _build_home_chart_payload(
        1, {"post_types": ["job_listings"]}, now=now, brand_projection=projection
    )
    excluded = _build_home_chart_payload(
        1, {"post_types": ["model_releases"]}, now=now, brand_projection=projection
    )
    assert payload["totals"]["qwen"] == 1
    assert excluded["totals"]["qwen"] == 0


def test_mixed_cursor_paginates_posts_and_jobs_without_duplicates():
    now = timezone.now()
    brand = Brand.objects.create(nickname="qwen", display_name="Qwen")
    newest = Post.objects.create(
        tweet_id="post-new", text="new", created_at=now - timedelta(minutes=1)
    )
    PostBrand.objects.create(post=newest, brand=brand)
    _job(brand=brand, title="Middle role", seen_at=now - timedelta(minutes=2))
    oldest = Post.objects.create(
        tweet_id="post-old", text="old", created_at=now - timedelta(minutes=3)
    )
    PostBrand.objects.create(post=oldest, brand=brand)

    first, cursor, has_more, _ = _feed_page_wire(
        locale="en", window_days=1, filters={}, limit=2
    )
    second, next_cursor, second_has_more, _ = _feed_page_wire(
        locale="en", window_days=1, filters={}, limit=2, cursor=cursor
    )
    assert [row["row_key"] for row in first] == ["p:post-new", first[1]["row_key"]]
    assert first[1]["source_kind"] == "official_job"
    assert [row["row_key"] for row in second] == ["p:post-old"]
    assert len({row["row_key"] for row in first + second}) == 3
    assert has_more is True
    assert next_cursor is None
    assert second_has_more is False


@pytest.mark.parametrize(
    ("sort", "order"),
    [
        ("created_at", "asc"),
        ("created_at", "desc"),
        ("like_count", "asc"),
        ("like_count", "desc"),
    ],
)
def test_equal_sort_values_paginate_all_source_kinds_once(sort, order):
    seen_at = timezone.now() - timedelta(minutes=5)
    brand = Brand.objects.create(nickname="qwen", display_name="Qwen")
    for title in ("Role A", "Role B"):
        _job(brand=brand, title=title, seen_at=seen_at)
    for tweet_id in ("post-a", "post-b"):
        post = Post.objects.create(
            tweet_id=tweet_id,
            text=tweet_id,
            created_at=seen_at,
            like_count=0,
        )
        PostBrand.objects.create(post=post, brand=brand)

    cursor = None
    row_keys = []
    for _ in range(5):
        rows, cursor, has_more, _ = _feed_page_wire(
            locale="en",
            window_days=1,
            filters={},
            sort=sort,
            order=order,
            cursor=cursor,
            limit=1,
        )
        row_keys.extend(row["row_key"] for row in rows)
        if not has_more:
            break

    assert len(row_keys) == 4
    assert len(set(row_keys)) == 4
    assert {key[:2] for key in row_keys} == {"j:", "p:"}


def test_malformed_job_cursor_restarts_from_first_page():
    brand = Brand.objects.create(nickname="qwen", display_name="Qwen")
    _job(brand=brand, title="First role")
    malformed = _encode_feed_cursor_values(
        "2026-09-12T00:00:00+00:00",
        "j:notint",
        sort="created_at",
        order="desc",
    )

    expected, _, _, _ = _feed_page_wire(locale="en", window_days=1, filters={}, limit=1)
    actual, _, _, _ = _feed_page_wire(
        locale="en", window_days=1, filters={}, limit=1, cursor=malformed
    )

    assert [row["row_key"] for row in actual] == [row["row_key"] for row in expected]
