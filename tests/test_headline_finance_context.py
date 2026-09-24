"""Finance-style descriptions must be based on observed, scoped measurements."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from monitor import trend_narrative_facts as facts

AS_OF = datetime(2026, 9, 24, tzinfo=UTC)


def series(counts, *, hours=1):
    start = AS_OF - timedelta(hours=len(counts) * hours)
    return [{"start_at": (start + timedelta(hours=i * hours)).isoformat(),
             "end_at": (start + timedelta(hours=(i + 1) * hours)).isoformat(),
             "post_count": count} for i, count in enumerate(counts)]


def context(rows, **kwargs):
    return facts.build_finance_context(
        "alpha", rows, as_of=AS_OF, window_days=1, bucket_seconds=3600,
        selected_coverage={"state": "sufficient", "known_backlog_overlap": False},
        thresholds=facts.DEFAULT_TREND_THRESHOLDS, **kwargs,
    )


def values(packet):
    return {row["metric"]: row["source_value"] for row in packet["facts"]}


def test_spike_then_cooling_differs_from_steady_rise_with_same_endpoints():
    spike = context(series([10, 20, 80, 40, 15]))
    rise = context(series([10, 11, 12, 13, 15]))
    s, r = values(spike), values(rise)
    assert Decimal(s["overall_rate_change_pct"]) == Decimal(r["overall_rate_change_pct"]) == 50
    assert Decimal(s["recent_rate_change_pct"]) < 0 < Decimal(r["recent_rate_change_pct"])
    assert Decimal(s["directional_efficiency"]) < Decimal(r["directional_efficiency"]) == 1
    assert Decimal(s["drop_from_peak_pct"]) == Decimal("81.25")
    assert spike["phases"][-1]["kind"] == "cooling"
    assert spike["phases"][-1]["provisional"] is True
    assert len(spike["phases"]) <= 3
    assert spike["historical_status"]["state"] == "unavailable"


def test_flat_zero_incomplete_and_future_buckets_do_not_create_a_decline():
    flat = values(context(series([0, 0, 0])))
    assert "overall_rate_change_pct" not in flat
    assert Decimal(flat["directional_efficiency"]) == 0
    rows = series([20, 20, 20])
    rows[-1]["end_at"] = (AS_OF - timedelta(minutes=30)).isoformat()
    rows[-1]["post_count"] = 2
    rows.append({"start_at": AS_OF.isoformat(), "end_at": (AS_OF + timedelta(hours=1)).isoformat(),
                 "post_count": 0})
    result = values(context(rows))
    assert Decimal(result["recent_rate_change_pct"]) == 0
    assert Decimal(result["drop_from_peak_pct"]) == 0


def test_missing_buckets_are_not_zero_and_counts_use_duration_adjusted_rates():
    rows = series([20, 40, 60])
    rows[1]["end_at"] = rows[2]["end_at"]
    rows.pop()
    packet = values(context(rows))
    assert Decimal(packet["overall_rate_change_pct"]) == 0  # 20/hour vs 40/2 hours
    gappy = series([10, 20, 30])
    gappy.pop(1)
    assert context(gappy)["shape_status"]["reason"] == "noncontiguous_buckets"


def test_matching_history_needs_provenance_and_does_not_treat_seasonality_as_burst():
    history = []
    for week in range(1, 9):
        end = AS_OF - timedelta(weeks=week)
        history.append({"start_at": (end - timedelta(days=1)).isoformat(), "end_at": end.isoformat(),
                        "post_count": 240, "coverage": "1", "regime": "same",
                        "coverage_proven": True, "backlog_overlap": False})
    eligible = facts.matched_history_summary(
        history, as_of=AS_OF, window_days=1, observed_count=240, regime="same"
    )
    assert eligible["state"] == "available" and eligible["sample_size"] == 8
    assert Decimal(eligible["observed_expected_ratio"]) == 1
    for row in history:
        row["coverage_proven"] = False
    rejected = facts.matched_history_summary(
        history, as_of=AS_OF, window_days=1, observed_count=240, regime="same"
    )
    assert rejected["state"] == "unavailable"
    assert "observed_expected_ratio" not in rejected


def test_history_does_not_accept_wrong_regime_future_or_zero_expected():
    end = AS_OF - timedelta(weeks=1)
    row = {"start_at": (end - timedelta(days=1)).isoformat(), "end_at": end.isoformat(),
           "post_count": 0, "coverage": "1", "regime": "other", "coverage_proven": True}
    packet = facts.matched_history_summary(
        [row] * 8, as_of=AS_OF, window_days=1, observed_count=2, regime="same"
    )
    assert packet["state"] == "unavailable" and packet["sample_size"] == 0


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_observed_breadth_is_exact_across_buckets_and_excludes_later_fetches():
    from core.models import Account, Brand, Post, PostBrand

    brand = Brand.objects.create(nickname="finance_alpha")
    author = Account.objects.create(author_id="finance_author")
    for index in range(5):
        post = Post.objects.create(
            tweet_id=f"finance-{index}", author=author, text="same repeated source",
            created_at=AS_OF - timedelta(hours=2 + index * 3),
        )
        PostBrand.objects.create(post=post, brand=brand)
        Post.objects.filter(pk=post.pk).update(
            fetched_at=AS_OF + timedelta(days=1) if index == 4 else AS_OF - timedelta(hours=1)
        )
    observed = facts.fetch_finance_observations([brand.pk], window_days=1, as_of=AS_OF)[brand.pk]
    assert observed["participation"] == {
        "status": "available", "post_count": 4, "distinct_authors": 1, "deduplicated_sources": 1,
    }
    assert sum(row["post_count"] for row in observed["series"]) == 4
    assert len(observed["history"]) == 8
    assert all(row["coverage_proven"] is False for row in observed["history"])
    assert "same repeated source" not in str(observed)


def test_projected_finance_keeps_permitted_within_window_change_but_not_history_counts():
    from monitor.trend_narrative_packet import project_dossier

    finance = context(series([10, 20, 80, 40, 15]))
    finance["history_intervals"] = [{"post_count": 123456789}]
    projected = project_dossier({
        "brand_key": "alpha", "comparison_status": {"allowed": False}, "finance_context": finance,
    })
    assert "123456789" not in str(projected)
    overall = next(row for row in projected["facts"] if row["metric"] == "overall_rate_change_pct")
    assert Decimal(overall["value"]) == 50
    assert projected["scopes"][overall["scope_ref"]]["basis"] == "completed_bucket_rate_change"
    assert "shape_summary" not in projected


def test_finance_policy_and_material_change_invalidate_demand_identity():
    from monitor.trend_narrative_demand import (
        material_input_fingerprint,
        target_identity,
    )
    from x_monitor.config import HeadlineNarrativeConfig

    config = HeadlineNarrativeConfig()
    first = {"brand_key": "alpha", "finance_context": context(series([10, 20, 80, 40, 15]))}
    second = {"brand_key": "alpha", "finance_context": context(series([10, 11, 12, 13, 15]))}
    assert material_input_fingerprint(first, config=config) != material_input_fingerprint(second, config=config)
    assert "activity-context-v1" in target_identity(config)[0]


def test_repeated_bursts_do_not_get_mislabeled_as_one_continuous_buildup():
    packet = context(series([10, 40, 10, 50, 10]))
    assert packet["phases"][0]["kind"] == "repeated_bursts"
    assert len(packet["phases"]) <= 3
    assert all(row["kind"] not in {"return_to_usual", "sustained_elevated"} for row in packet["phases"])
