"""PostgreSQL contracts for the provider-free public headline projection."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from html import unescape

import pytest

from core.models import Brand
from monitor.trend_narrative_lifecycle import (
    mark_transport_started,
    publish_generation,
    reserve_generation,
)
from monitor.trend_narrative_projection import project_trend_narrative
from monitor.views import _build_home_chart_payload
from x_monitor.config import HeadlineNarrativeConfig

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


def _config(*, enabled: bool = True) -> HeadlineNarrativeConfig:
    return HeadlineNarrativeConfig(serving_enabled=enabled)


def _publish(window_days: int = 1):
    brand = Brand.objects.create(
        nickname="minimax",
        display_name="MiniMax",
        display_name_en="MiniMax",
        display_name_zh_cn="MiniMax",
    )
    facts = {
        "schema_version": 1,
        "window_days": window_days,
        "as_of": NOW.isoformat().replace("+00:00", "Z"),
        "coverage": {"state": "sufficient", "ratio": "1.000000"},
        "narrative_type": "leader",
        "primary_brand": {
            "key": brand.pk,
            "display_name_en": "MiniMax",
            "display_name_zh_hans": "MiniMax",
        },
        "secondary_brand": None,
        "earlier_leader": None,
        "momentum": "rising",
    }
    row = reserve_generation(
        source_cycle_id="cycle-a",
        window_days=window_days,
        facts_as_of=NOW,
        semantic_fingerprint="a" * 64,
        generation_facts=facts,
        publication_epoch=1,
        prompt_version="headline-v1",
        provider="anthropic",
        provider_host="api.anthropic.com",
        model_name="claude-haiku-4-5-20251001",
        owner="worker-a",
        now=NOW,
        lease_seconds=90,
    )
    assert row is not None
    assert mark_transport_started(
        row.pk,
        owner="worker-a",
        fence=row.claim_fence,
        now=NOW,
    )
    assert publish_generation(
        row.pk,
        owner="worker-a",
        fence=row.claim_fence,
        body_en="MiniMax leads attention across the market.",
        body_zh_hans="当前市场讨论中，MiniMax 更受关注。",
        output_hash="b" * 64,
        input_tokens=100,
        output_tokens=40,
        latency_ms=200,
        now=NOW + timedelta(seconds=1),
    )
    row.refresh_from_db()
    return row


@pytest.mark.parametrize(
    ("locale", "expected"),
    [
        ("en", "MiniMax leads attention across the market."),
        ("original", "MiniMax leads attention across the market."),
        ("zh_cn", "当前市场讨论中，MiniMax 更受关注。"),
        ("zh-CN", "当前市场讨论中，MiniMax 更受关注。"),
        ("zh_hans", "当前市场讨论中，MiniMax 更受关注。"),
    ],
)
def test_available_projection_selects_locale_and_public_brand_link(locale, expected):
    row = _publish()

    payload = project_trend_narrative(
        1,
        locale=locale,
        now=NOW + timedelta(minutes=30),
        config=_config(),
    )

    assert payload["schema_version"] == 1
    assert payload["window_days"] == 1
    assert payload["state"] == "available"
    assert payload["state_label"] == (
        "可用" if locale in {"zh_cn", "zh-CN", "zh_hans"} else "Available"
    )
    assert payload["body"] == expected
    assert payload["primary_brand"] == {
        "key": "minimax",
        "display_name": "MiniMax",
        "url": "/brands/minimax/",
    }
    assert payload["generated_at"] == row.generated_at.isoformat()
    assert "provider" not in payload
    assert "error" not in payload
    assert "claim" not in payload


def test_stale_uses_last_good_body_and_deleted_brand_loses_only_link():
    row = _publish()
    Brand.objects.get(pk="minimax").delete()

    payload = project_trend_narrative(
        1,
        locale="en",
        now=NOW + timedelta(hours=2),
        config=_config(),
    )

    assert payload["state"] == "stale"
    assert payload["state_label"] == "Stale"
    assert payload["body"] == row.body_en
    assert payload["primary_brand"]["display_name"] == "MiniMax"
    assert payload["primary_brand"]["url"] is None


@pytest.mark.parametrize(
    ("locale", "phrase"),
    [
        ("en", "Trend summary is warming up"),
        ("original", "Trend summary is warming up"),
        ("zh_cn", "趋势摘要正在准备中"),
    ],
)
def test_cold_fallback_is_localized_and_readable(locale, phrase):
    payload = project_trend_narrative(
        30,
        locale=locale,
        now=NOW,
        config=_config(),
    )

    assert payload["state"] == "unavailable"
    assert payload["state_label"] == ("准备中" if locale == "zh_cn" else "Warming up")
    assert phrase in payload["body"]
    assert payload["primary_brand"] is None


def test_serving_control_off_returns_disabled_copy_even_with_current_row():
    _publish()

    payload = project_trend_narrative(
        1,
        locale="en",
        now=NOW,
        config=_config(enabled=False),
    )

    assert payload["state"] == "disabled"
    assert payload["state_label"] == "Disabled"
    assert payload["primary_brand"] is None
    assert "unavailable" in payload["body"].lower()


def test_chart_payload_has_one_identity_for_chart_pulse_narrative_and_voices(
    monkeypatch,
):
    _publish()
    monkeypatch.setattr(
        "monitor.trend_narrative_projection._load_config",
        lambda: _config(),
    )

    payload = _build_home_chart_payload(1, {}, now=NOW, locale="en")

    assert payload["window_days"] == payload["pulse"]["window_days"]
    assert payload["window_days"] == payload["trend_narrative"]["window_days"]
    assert payload["window_days"] == payload["top_voices"]["window_days"]
    assert payload["computed_at"] == payload["pulse"]["computed_at"]
    assert payload["computed_at"] == payload["trend_narrative"]["computed_at"]
    assert payload["computed_at"] == payload["top_voices"]["computed_at"]


def test_ten_window_requests_are_database_only_and_ignore_filters(
    client,
    monkeypatch,
):
    _publish()
    monkeypatch.setattr(
        "monitor.trend_narrative_projection._load_config",
        lambda: _config(),
    )
    monkeypatch.setattr(
        "monitor.trend_narrative_generation.generate_trend_narrative",
        lambda *_args, **_kwargs: pytest.fail("web request reached provider"),
    )
    monkeypatch.setattr(
        "monitor.tasks.refresh_trend_narratives.apply_async",
        lambda *_args, **_kwargs: pytest.fail("web request enqueued worker"),
    )
    bodies = []
    for index in range(10):
        window = [1, 7, 30, 365][index % 4]
        response = client.get(
            "/chart.html",
            {
                "window": window,
                "filters": json.dumps(
                    {"window": window, "brands": [f"filter-{index}"]}
                ),
                "locale": "en",
            },
        )
        assert response.status_code == 200
        raw = response.content.decode("utf-8")
        marker = "data-home='"
        encoded = raw.split(marker, 1)[1].split("'", 1)[0]
        payload = json.loads(unescape(encoded))
        bodies.append(payload["trend_narrative"]["body"])
    assert bodies[0] == bodies[4] == bodies[8]
