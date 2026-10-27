"""Runtime database drift must not silently expand selectable UI brands."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from html import unescape
from unittest.mock import patch

import pytest
from django.http import Http404

from core.models import Brand, Post, PostBrand
from monitor.views import (
    _build_brand_chart_payload,
    _build_brands_context,
    _build_home_chart_payload,
    _build_home_pulse_payload,
    _clear_home_pulse_cache,
    _enrich_posts_with_classifications,
    _home_visible_brand_rows,
    _normalize_home_filters,
    _post_to_wire,
    _serialize_feed_row,
)
from x_monitor.config import HeadlineNarrativeConfig

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


@pytest.mark.parametrize("window", (1, 7, 30, 365))
@pytest.mark.parametrize("locale", ("en", "zh_cn", "zh_hans", "ja"))
def test_call_a_companies_do_not_expand_public_tracked_brand_surfaces(client, window, locale):
    from pathlib import Path

    from django.utils import timezone

    from tests.test_chart_harvest_coverage import record_harvest
    from x_monitor.config import load_config

    now = timezone.now()
    record_harvest(now, finished_at=now, staggered=False)
    tracked = set(load_config(Path("config.yaml")).enabled_models)
    for nickname in tracked:
        Brand.objects.get_or_create(nickname=nickname, defaults={"display_name": nickname})
    companies = [f"call-a-company-{index:03d}" for index in range(119)]
    Brand.objects.bulk_create([
        Brand(nickname=nickname, display_name=nickname) for nickname in companies
    ])
    created_at = timezone.now() - timedelta(hours=1)
    post = Post.objects.create(tweet_id="call-a-company-post", created_at=created_at)
    PostBrand.objects.create(post=post, brand_id=companies[0])
    tracked_post = Post.objects.create(tweet_id="tracked-brand-post", created_at=created_at)
    PostBrand.objects.create(post=tracked_post, brand_id="deepseek")
    _clear_home_pulse_cache()

    response = client.get("/", {"locale": locale, "window": window}, secure=True)
    assert response.status_code == 200
    assert {row["nickname"] for row in response.context["brands"]} == tracked
    assert {row["nickname"] for row in response.context["pulse"]["entries"]} == tracked
    payload = json.loads(response.context["payload"])
    assert set(payload["series"]) == tracked
    assert payload["totals"]["deepseek"] == 1
    body = response.content.decode()
    assert 'value="deepseek"' in body
    assert not any(f'value="{nickname}"' in body for nickname in companies)

    # A crafted URL must not promote a collected company into a tracked series.
    chart = client.get("/chart/", {
        "locale": locale,
        "window": window,
        "filters": json.dumps({"brands": [companies[0]], "window": window}),
    }, secure=True)
    assert chart.status_code == 200
    assert chart.json()["series"] == {}
    assert {row["nickname"] for row in chart.json()["pulse"]["entries"]} == tracked
    assert Brand.objects.filter(nickname__in=companies).count() == 119
    assert PostBrand.objects.filter(post=post, brand_id=companies[0]).exists()


def test_internal_brand_inventory_remains_broad_after_public_cache_fill(client, django_user_model):
    Brand.objects.get_or_create(nickname="deepseek", defaults={"display_name": "DeepSeek"})
    Brand.objects.create(nickname="call-a-only", display_name="Call A company")
    _clear_home_pulse_cache()
    public = client.get("/", {"locale": "en"}, secure=True)
    assert "call-a-only" not in json.loads(public.context["payload"])["series"]
    client.force_login(django_user_model.objects.create_user(username="internal-inventory"))
    internal = client.get("/internal/", {"locale": "en"}, secure=True)
    assert internal.status_code == 200
    assert "call-a-only" in {row["nickname"] for row in internal.context["brands"]}
    assert "call-a-only" in json.loads(internal.context["payload"])["series"]
    public_again = client.get("/chart/", {"locale": "en"}, secure=True).json()
    assert "call-a-only" not in public_again["series"]
    assert "call-a-only" not in {row["nickname"] for row in public_again["pulse"]["entries"]}


def test_step_history_remains_stored_while_only_stepfun_is_selectable() -> None:
    from core.models import SearchQuery

    step, _ = Brand.objects.update_or_create(
        nickname="step", defaults={"display_name": "Step", "is_sentinel": False},
    )
    Brand.objects.update_or_create(
        nickname="stepfun", defaults={"display_name": "StepFun", "is_sentinel": False},
    )
    query = SearchQuery.objects.create(query_id="historical-step-query", brand=step)
    _clear_home_pulse_cache()

    assert "step" not in {row["nickname"] for row in _build_brands_context()}
    assert "stepfun" in {row["nickname"] for row in _build_brands_context()}
    pulse = _build_home_pulse_payload(1, now=datetime(2026, 8, 27, 12, 0, tzinfo=UTC))
    assert "step" not in {row["nickname"] for row in pulse["entries"]}
    chart = _build_home_chart_payload(
        1, {"brands": "__all__", "unsanctioned": "off"},
        now=datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
    )
    assert "step" not in chart["series"]
    assert "stepfun" in chart["series"]
    assert Brand.objects.filter(nickname__in=["step", "stepfun"]).count() == 2
    query.refresh_from_db()
    assert query.brand_id == "step"


def test_step_is_not_hidden_without_canonical_stepfun() -> None:
    rows = [{"nickname": "step"}, {"nickname": "other"}]
    assert _home_visible_brand_rows(rows) == rows
    Brand.objects.create(nickname="step", display_name="Step")
    assert _normalize_home_filters({"brands": ["step"]})["brands"] == ["step"]


def test_fixture_only_brand_is_excluded_from_controls_and_chart_series() -> None:
    Brand.objects.update_or_create(
        nickname="deepseek",
        defaults={"display_name": "DeepSeek", "is_sentinel": False},
    )
    Brand.objects.update_or_create(
        nickname="test_brand",
        defaults={"display_name": "Test fixture brand", "is_sentinel": True},
    )
    _clear_home_pulse_cache()

    context_keys = [item["nickname"] for item in _build_brands_context()]
    payload = _build_home_chart_payload(
        1,
        {"brands": "__all__", "unsanctioned": "off"},
        now=datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
    )

    assert "deepseek" in context_keys
    assert "test_brand" not in context_keys
    assert "test_brand" not in payload["series"]


def test_non_sentinel_test_brand_is_included_without_nickname_allowlist() -> None:
    Brand.objects.create(
        nickname="test_brand",
        display_name="Test brand from DB",
        accent_color="#123456",
        is_sentinel=False,
    )
    _clear_home_pulse_cache()

    context = _build_brands_context()
    assert any(item["nickname"] == "test_brand" for item in context)

    pulse = _build_home_pulse_payload(
        1, now=datetime(2026, 8, 27, 12, 0, tzinfo=UTC)
    )
    assert "test_brand" in {item["nickname"] for item in pulse["entries"]}

    chart = _build_home_chart_payload(
        1,
        {"brands": "__all__", "unsanctioned": "off"},
        now=datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
    )
    assert "test_brand" in chart["series"]


def test_db_only_brand_projects_through_dashboard_and_both_feed_wire_shapes(
    client, django_user_model
):
    dots = Brand.objects.create(
        nickname="dots",
        display_name="Dots Studio",
        display_name_en="Dots Studio",
        display_name_zh_cn="点点工作室",
        accent_color="#0ea5e9",
        is_sentinel=False,
    )
    fixture = Brand.objects.create(
        nickname="test_brand",
        display_name="Fixture only",
        is_sentinel=True,
    )
    _clear_home_pulse_cache()

    context = {item["nickname"]: item for item in _build_brands_context()}
    assert context["dots"]["display_name_en"] == "Dots Studio"
    assert context["dots"]["display_name_zh_cn"] == "点点工作室"
    assert context["dots"]["accent_color"] == "#0ea5e9"
    assert "test_brand" not in context

    home_response = client.get("/?locale=zh_cn", secure=True)
    assert home_response.status_code == 200
    home_body = home_response.content.decode("utf-8")
    assert "点点工作室" in home_body
    assert 'value="dots"' in home_body
    assert "Fixture only" not in home_body

    pulse = _build_home_pulse_payload(
        1, now=datetime(2026, 8, 27, 12, 0, tzinfo=UTC)
    )
    pulse_entry = next(item for item in pulse["entries"] if item["nickname"] == "dots")
    assert pulse_entry["display_name_zh_cn"] == "点点工作室"
    assert pulse_entry["accent_color"] == "#0ea5e9"
    assert "test_brand" not in {item["nickname"] for item in pulse["entries"]}

    chart = _build_home_chart_payload(
        1,
        {"brands": "__all__", "unsanctioned": "off"},
        now=datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
    )
    assert "dots" in chart["series"]
    assert chart["colors"]["dots"] == "#0ea5e9"
    assert "test_brand" not in chart["series"]

    single_chart = _build_brand_chart_payload(
        "dots", 1, {}, "post_type", locale="zh_cn"
    )
    assert single_chart["display_name"] == "点点工作室"
    assert single_chart["accent_color"] == "#0ea5e9"

    post = Post.objects.create(
        tweet_id="dots-feed",
        created_at=datetime(2026, 8, 27, 11, 0, tzinfo=UTC),
    )
    PostBrand.objects.create(post=post, brand=dots)
    PostBrand.objects.create(post=post, brand=fixture)
    post = Post.objects.prefetch_related("brands__brand").get(pk=post.pk)
    direct_wire = _post_to_wire(post, "zh_cn")
    assert direct_wire["brands"][0]["display_name"] == "点点工作室"
    assert direct_wire["brands"][0]["accent_color"] == "#0ea5e9"
    assert direct_wire["brand_nicknames"] == ["dots"]

    enriched = _enrich_posts_with_classifications(
        Post.objects.filter(pk=post.pk).prefetch_related("brands__brand")
    )[0]
    serialized = _serialize_feed_row(enriched, "zh_cn")
    assert serialized["brands"][0]["display_name"] == "点点工作室"
    assert serialized["brands"][0]["accent_color"] == "#0ea5e9"
    assert serialized["brand_nicknames"] == ["dots"]

    with pytest.raises(Http404):
        _build_brand_chart_payload("test_brand", 1, {}, "post_type")

    user = django_user_model.objects.create_user(username="u7-brand")
    client.force_login(user)
    detail_response = client.get("/brands/dots/?locale=zh_cn", secure=True)
    assert detail_response.status_code == 200
    assert detail_response.context["brand_obj"]["display_name"] == "点点工作室"
    assert detail_response.context["brand_obj"]["accent_color"] == "#0ea5e9"


def test_brand_detail_locale_controls_include_japanese(client, django_user_model):
    """The real brand route exposes every supported review locale."""
    brand = Brand.objects.create(
        nickname="ja-brand",
        display_name="Japanese fixture brand",
        is_sentinel=False,
    )
    user = django_user_model.objects.create_user(username="u7-brand-ja")
    client.force_login(user)

    for locale in ("en", "zh_cn", "ja"):
        response = client.get(f"/brands/{brand.nickname}/?locale={locale}", secure=True)
        assert response.status_code == 200
        body = response.content.decode("utf-8")
        assert 'data-pw-locale-btn="en"' in body
        assert 'data-pw-locale-btn="zh_cn"' in body
        assert 'data-pw-locale-btn="ja"' in body
        assert 'data-pw-locale-btn="original"' not in body

    ja_response = client.get(f"/brands/{brand.nickname}/?locale=ja", secure=True)
    ja_body = ja_response.content.decode("utf-8")
    assert 'class="locale-btn is-active"\n              data-pw-locale-btn="ja"' in ja_body


def test_db_brand_projection_falls_back_for_null_display_and_accent():
    brand = Brand.objects.create(
        nickname="fallback-brand",
        display_name=None,
        display_name_en=None,
        display_name_zh_cn=None,
        accent_color=None,
        is_sentinel=False,
    )
    _clear_home_pulse_cache()
    item = next(
        item for item in _build_brands_context() if item["nickname"] == "fallback-brand"
    )
    assert item["display_name"] == "fallback-brand"
    assert item["display_name_en"] == "fallback-brand"
    assert item["display_name_zh_cn"] == "fallback-brand"
    assert item["accent_color"] == "#9ca3af"

    pulse_entry = next(
        item
        for item in _build_home_pulse_payload(
            1, now=datetime(2026, 8, 27, 12, 0, tzinfo=UTC)
        )["entries"]
        if item["nickname"] == brand.nickname
    )
    assert pulse_entry["display_name"] == "fallback-brand"
    assert pulse_entry["accent_color"] == "#9ca3af"
    chart = _build_home_chart_payload(
        1,
        {"brands": [brand.nickname], "unsanctioned": "off"},
        now=datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
    )
    assert chart["colors"][brand.nickname] == "#9ca3af"
    single = _build_brand_chart_payload(
        brand.nickname, 1, {}, "post_type", locale="zh_cn"
    )
    assert single["display_name"] == "fallback-brand"
    assert single["accent_color"] == "#9ca3af"


def test_mimo_chart_route_projects_nullable_localized_names_safely(client) -> None:
    Brand.objects.update_or_create(
        nickname="mimo",
        defaults={
            "display_name": "Xiaomi MiMo",
            "display_name_en": None,
            "display_name_zh_cn": None,
            "is_sentinel": False,
        },
    )
    _clear_home_pulse_cache()

    with patch(
        "monitor.trend_narrative_projection._load_config",
        return_value=HeadlineNarrativeConfig(
            serving_enabled=True,
            activation_state="owner_override",
            publication_source="prefer_per_brand",
            legacy_fallback_enabled=False,
        ),
    ):
        response = client.get(
            "/chart.html",
            {
                "filters": json.dumps(
                    {"brands": ["mimo"], "unsanctioned": "off", "window": 1}
                ),
                "window": "1",
                "locale": "zh_cn",
            },
            secure=True,
        )

    assert response.status_code == 200
    payload = json.loads(response.context["payload"])
    item = payload["trend_narrative"]["items"][0]
    assert item["brand"]["display_name"] == "Xiaomi MiMo"
    assert "None" not in unescape(item["headline"])
