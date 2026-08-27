"""Runtime database drift must not silently expand selectable UI brands."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from html import unescape
from unittest.mock import patch

import pytest

from core.models import Brand
from monitor.views import (
    HOME_SELECTABLE_BRAND_NICKNAMES,
    _build_brands_context,
    _build_home_chart_payload,
    _clear_home_pulse_cache,
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
        defaults={"display_name": "Test fixture brand", "is_sentinel": False},
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
    assert set(context_keys) <= set(HOME_SELECTABLE_BRAND_NICKNAMES)


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
