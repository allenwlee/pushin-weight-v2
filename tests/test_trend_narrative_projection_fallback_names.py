"""Regression coverage for safe per-brand narrative identity projection."""

from datetime import UTC, datetime
from types import SimpleNamespace

from core.models import BrandTrendNarrative
from monitor.trend_narrative_projection import _per_brand_item


def test_mimo_with_nullable_localized_names_projects_a_nonempty_display_name() -> None:
    """A selected brand must never make the browser reject the chart DTO."""

    brand = SimpleNamespace(
        nickname="mimo",
        display_name="Xiaomi MiMo",
        display_name_en=None,
        display_name_zh_cn=None,
    )

    item = _per_brand_item(
        None,
        fallback_brand=brand,
        brand_key="mimo",
        window_days=1,
        is_zh=True,
        now=datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
        config=None,
    )

    assert item["brand"]["display_name"] == "Xiaomi MiMo"
    assert "None" not in item["headline"]


def test_existing_outcome_with_nullable_snapshots_uses_its_live_brand_name() -> None:
    """Old rows with null snapshots must not degrade to a nickname or null DTO."""

    brand = SimpleNamespace(
        nickname="mimo",
        display_name="Xiaomi MiMo",
        display_name_en=None,
        display_name_zh_cn=None,
    )
    outcome = SimpleNamespace(
        pk=501,
        status=BrandTrendNarrative.Status.NO_CONTENT,
        brand=brand,
        brand_id="mimo",
        brand_name_en_snapshot=None,
        brand_name_zh_cn_snapshot=None,
        verified_at=None,
        attempted_at=None,
    )

    item = _per_brand_item(
        outcome,
        fallback_brand=None,
        brand_key="mimo",
        window_days=1,
        is_zh=True,
        now=datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
        config=None,
    )

    assert item["brand"]["display_name"] == "Xiaomi MiMo"
    assert "None" not in item["headline"]
