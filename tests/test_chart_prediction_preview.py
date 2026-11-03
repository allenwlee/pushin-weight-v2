from datetime import UTC, datetime
from decimal import Decimal

from core.chart_prediction_preview import temporary_preview


def inputs(**changes):
    data = {
        "target_posts": {0: 14, 1: 14, 2: 14},
        "historical_posts": {0: 10, 1: 10, 2: 10, 3: 5, 4: 5, 5: 5},
        "historical_metrics": {3: Decimal(10), 4: Decimal(-5), 5: Decimal(7)},
        "completed_day": 2,
        "cutoff": datetime(2026, 9, 13, tzinfo=UTC),
        "target_launch": datetime(2026, 9, 10, tzinfo=UTC).date(),
        "source": "hf",
        "metric": "net_download_change",
        "comparable": True,
        "accounting_known": True,
        "forecast_permitted": True,
        "history_mode": "hindsight",
    }
    data.update(changes)
    return data


def test_ratio_uses_totals_and_preserves_signed_metric():
    result = temporary_preview(**inputs())
    assert result["ratio"] == Decimal("1.4")
    assert result["points"][4]["value"] == Decimal(-7)
    assert result["points"][5]["smoothed"] == Decimal("5.6")
    assert "coverage" in result["warning"].lower()
    assert "inflate" in result["warning"].lower()


def test_zero_target_is_valid_but_missing_or_zero_historical_is_not():
    assert temporary_preview(**inputs(target_posts={0: 0, 1: 0, 2: 0}))["ratio"] == 0
    assert (
        temporary_preview(**inputs(target_posts={0: 1, 1: 1}))["status"]
        == "unavailable"
    )
    assert (
        temporary_preview(**inputs(historical_posts={0: 0, 1: 0, 2: 0}))["status"]
        == "unavailable"
    )


def test_unverified_scope_coverage_rights_or_future_calibration_are_unavailable():
    for overrides in (
        {"accounting_known": False},
        {"comparable": False},
        {"forecast_permitted": False},
        {"completed_day": 3},
        {"metric": "rank"},
    ):
        assert temporary_preview(**inputs(**overrides))["status"] == "unavailable"


def test_missing_future_history_is_gap_and_horizon_is_bounded():
    result = temporary_preview(
        **inputs(historical_posts={0: 10, 1: 10, 2: 10, 3: 0, 4: 5}, horizon=4)
    )
    assert result["points"][3]["value"] is None
    assert result["points"][4]["value"] == Decimal(-7)
    assert 5 not in result["points"]
