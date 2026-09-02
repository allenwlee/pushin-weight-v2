"""Runtime database drift must not silently expand selectable UI brands."""

from __future__ import annotations

import json
from datetime import UTC, datetime
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
    _post_to_wire,
    _serialize_feed_row,
)
from x_monitor.config import HeadlineNarrativeConfig

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


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
