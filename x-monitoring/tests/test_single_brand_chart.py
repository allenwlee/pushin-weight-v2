# {{AGENT_ATTRIBUTION}}
"""Tests for x_monitor.dashboard.serialize_single_brand_chart (U3 of
feat/pushin-weight-home-pages, 2026-07-06).

Covers the single-brand Pushin' Weight area chart data layer:
- All 6 tab_datasets (post_type, discourse, account_roles, us_nationalism,
  cn_nationalism, unsanctioned) populate from a single posts list
- Default tab is post_type
- Each tab carries its full category set, even when no posts hit it
- unsanctioned tab is the synthetic flagged/unflagged split
- Brand with 0 posts → all-zero series, no error
- Filter narrowing applies to the input posts
- color_vars includes a CSS variable per category per tab
- applied_filters and tab echo the input
"""

from __future__ import annotations

from datetime import datetime, timezone

from x_monitor.dashboard import (
    _DASHBOARD_DISCOURSE_KEYS,
    _DASHBOARD_NATIONALISM_KEYS,
    _DASHBOARD_POST_TYPE_KEYS,
    _DASHBOARD_ROLE_KEYS,
    _SINGLE_BRAND_TABS,
    serialize_single_brand_chart,
)


def _post(
    *,
    created_at: str,
    discourse: list[str] | None = None,
    post_types: list[str] | None = None,
    role_key: str = "community",
    cn_nationalism: str | None = None,
    us_nationalism: str | None = None,
    unsanctioned: bool = False,
) -> dict:
    return {
        "tweet_id": f"t-{created_at}",
        "created_at": created_at,
        "text": "stub",
        "discourse": discourse or [],
        "post_types": post_types or [],
        "role_key": role_key,
        "cn_nationalism": cn_nationalism,
        "us_nationalism": us_nationalism,
        "unsanctioned": unsanctioned,
    }


# ---------------------------------------------------------------------------
# Tab spec constant sanity
# ---------------------------------------------------------------------------


def test_single_brand_tabs_count_is_6():
    assert len(_SINGLE_BRAND_TABS) == 6


def test_single_brand_tabs_order_matches_plan():
    """R14: post_type (default) | discourse | account_roles | us_nationalism
    | cn_nationalism | unsanctioned."""
    assert _SINGLE_BRAND_TABS == (
        "post_type", "discourse", "account_roles",
        "us_nationalism", "cn_nationalism", "unsanctioned",
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_single_brand_chart_default_tab_is_post_type():
    """R14: post_type is the default tab on first render."""
    out = serialize_single_brand_chart(
        "minimax", [], window_days=7,
        now=datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert out["tab"] == "post_type"


def test_single_brand_chart_seven_day_default_window():
    out = serialize_single_brand_chart(
        "minimax", [], window_days=7,
        now=datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert out["window_days"] == 7
    assert len(out["days"]) == 7
    assert out["days"][0] == "2026-06-30"
    assert out["days"][-1] == "2026-07-06"


def test_single_brand_chart_includes_all_six_tab_datasets():
    out = serialize_single_brand_chart(
        "minimax", [], window_days=7,
        now=datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert set(out["tab_datasets"].keys()) == {
        "post_type", "discourse", "account_roles",
        "us_nationalism", "cn_nationalism", "unsanctioned",
    }


def test_single_brand_chart_each_tab_carries_full_category_set():
    """Plan R14: every category in each tab is present in the output,
    even when no posts hit it (so toggling tabs never reshapes axes)."""
    out = serialize_single_brand_chart(
        "minimax", [], window_days=7,
        now=datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert set(out["tab_datasets"]["post_type"].keys()) == set(
        _DASHBOARD_POST_TYPE_KEYS
    )
    assert set(out["tab_datasets"]["discourse"].keys()) == set(
        _DASHBOARD_DISCOURSE_KEYS
    )
    assert set(out["tab_datasets"]["account_roles"].keys()) == set(
        _DASHBOARD_ROLE_KEYS
    )
    assert set(out["tab_datasets"]["us_nationalism"].keys()) == set(
        _DASHBOARD_NATIONALISM_KEYS
    )
    assert set(out["tab_datasets"]["cn_nationalism"].keys()) == set(
        _DASHBOARD_NATIONALISM_KEYS
    )
    assert set(out["tab_datasets"]["unsanctioned"].keys()) == {
        "flagged", "unflagged",
    }


def test_single_brand_chart_empty_brand_zero_series_no_error():
    """Edge case: brand with 0 posts in the window → all-zero series, no error."""
    out = serialize_single_brand_chart(
        "minimax", [], window_days=7,
        now=datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc),
    )
    for tab_key, cats in out["tab_datasets"].items():
        for cat_key, series in cats.items():
            assert series == [0] * 7, (
                f"tab={tab_key} cat={cat_key} should be zero series"
            )


def test_single_brand_chart_buckets_a_post_into_correct_day():
    now = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)
    posts = [
        _post(
            created_at="2026-07-04T08:00:00+00:00",
            post_types=["buzz_releases"],
            discourse=["genuine_hype"],
            role_key="official",
        ),
    ]
    out = serialize_single_brand_chart(
        "minimax", posts, window_days=7, now=now,
    )
    # 2026-07-04 → days_ago=2 → idx=7-1-2=4
    assert out["tab_datasets"]["post_type"]["buzz_releases"][4] == 1
    assert out["tab_datasets"]["discourse"]["genuine_hype"][4] == 1
    assert out["tab_datasets"]["account_roles"]["official"][4] == 1
    # Other categories untouched
    assert out["tab_datasets"]["post_type"]["hands_on_usage"][4] == 0


def test_single_brand_chart_unsanctioned_is_synthetic_2bucket():
    """R14: unsanctioned tab is a 2-bucket split (flagged / unflagged),
    NOT one of the 6 nationalism keys."""
    now = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)
    posts = [
        _post(created_at="2026-07-05T08:00:00+00:00", unsanctioned=True),
        _post(created_at="2026-07-05T09:00:00+00:00", unsanctioned=False),
    ]
    out = serialize_single_brand_chart(
        "minimax", posts, window_days=7, now=now,
    )
    # Both posts go to idx=5 (2026-07-05, days_ago=1)
    assert out["tab_datasets"]["unsanctioned"]["flagged"][5] == 1
    assert out["tab_datasets"]["unsanctioned"]["unflagged"][5] == 1


def test_single_brand_chart_only_present_post_type_keys_have_nonzero():
    """A brand with only 3 of 6 post_type keys present should have the
    other 3 categories at zero-lists, NOT omitted from the output."""
    now = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)
    posts = [
        _post(
            created_at="2026-07-05T08:00:00+00:00",
            post_types=["buzz_releases"],
        ),
    ]
    out = serialize_single_brand_chart(
        "minimax", posts, window_days=7, now=now,
    )
    assert all(
        out["tab_datasets"]["post_type"][k] == [0] * 7
        for k in _DASHBOARD_POST_TYPE_KEYS
        if k != "buzz_releases"
    )
    assert out["tab_datasets"]["post_type"]["buzz_releases"][5] == 1


def test_single_brand_chart_filters_narrow_input_posts():
    """With only `discourse=[genuine_hype]` active, posts with other
    discourse keys are excluded from ALL tab_datasets."""
    now = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)
    posts = [
        _post(
            created_at="2026-07-05T08:00:00+00:00",
            discourse=["genuine_hype"],
            post_types=["buzz_releases"],
        ),
        _post(
            created_at="2026-07-05T09:00:00+00:00",
            discourse=["sarcasm"],
            post_types=["hands_on_usage"],
        ),
    ]
    out = serialize_single_brand_chart(
        "minimax", posts, window_days=7, now=now,
        filters={"discourse": ["genuine_hype"]},
    )
    # Only the genuine_hype post should be counted
    assert out["tab_datasets"]["post_type"]["buzz_releases"][5] == 1
    assert out["tab_datasets"]["post_type"]["hands_on_usage"][5] == 0
    assert out["tab_datasets"]["discourse"]["genuine_hype"][5] == 1
    assert out["tab_datasets"]["discourse"]["sarcasm"][5] == 0


def test_single_brand_chart_unsanctioned_tab_counts_full_set_regardless_of_filter():
    """The unsanctioned tab counts BOTH flagged and unflagged posts
    regardless of the active unsanctioned filter — otherwise the tab
    would render a single empty bucket when unsanctioned=off (the
    default), making the stacked area visually useless. The filter
    still narrows the OTHER 5 tabs."""
    now = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)
    posts = [
        _post(created_at="2026-07-05T08:00:00+00:00", unsanctioned=True),
        _post(created_at="2026-07-05T09:00:00+00:00", unsanctioned=False),
    ]
    out = serialize_single_brand_chart(
        "minimax", posts, window_days=7, now=now,
        filters={"unsanctioned": "off"},
    )
    # unsanctioned tab still shows both buckets
    assert out["tab_datasets"]["unsanctioned"]["flagged"][5] == 1
    assert out["tab_datasets"]["unsanctioned"]["unflagged"][5] == 1
    # The other 5 tabs respect the filter (the flagged post has no
    # post_types / discourse / role / nationalism, so they all show
    # the unflagged post's contribution only).
    assert out["tab_datasets"]["post_type"]["buzz_releases"][5] == 0


def test_single_brand_chart_color_vars_per_category():
    """Each tab's color_vars maps every category to a CSS var() string."""
    out = serialize_single_brand_chart(
        "minimax", [], window_days=7,
        now=datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc),
    )
    for cat in _DASHBOARD_POST_TYPE_KEYS:
        assert out["color_vars"]["post_type"][cat] == f"var(--pt-{cat.replace('_', '-')})"
    for cat in _DASHBOARD_DISCOURSE_KEYS:
        assert out["color_vars"]["discourse"][cat] == f"var(--bar-{cat.replace('_', '-')})"
    for cat in _DASHBOARD_ROLE_KEYS:
        assert out["color_vars"]["account_roles"][cat] == f"var(--role-{cat.replace('_', '-')})"
    for cat in _DASHBOARD_NATIONALISM_KEYS:
        assert out["color_vars"]["us_nationalism"][cat] == f"var(--nat-{cat.replace('_', '-')})"
    # unsanctioned is special-cased
    assert out["color_vars"]["unsanctioned"]["flagged"] == "var(--yellow)"
    assert out["color_vars"]["unsanctioned"]["unflagged"] == "var(--muted)"


def test_single_brand_chart_tab_echo():
    out = serialize_single_brand_chart(
        "minimax", [], window_days=7, tab="discourse",
        now=datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert out["tab"] == "discourse"


def test_single_brand_chart_invalid_tab_falls_back_to_post_type():
    out = serialize_single_brand_chart(
        "minimax", [], window_days=7, tab="invalid",
        now=datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert out["tab"] == "post_type"


def test_single_brand_chart_applied_filters_echo():
    filters = {"discourse": ["sarcasm"], "unsanctioned": "off"}
    out = serialize_single_brand_chart(
        "minimax", [], window_days=7, filters=filters,
        now=datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert out["applied_filters"] == filters


def test_single_brand_chart_brand_metadata():
    out = serialize_single_brand_chart(
        "minimax", [], window_days=7,
        now=datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert out["brand_id"] == "minimax"
    assert out["display_name"] == "MiniMax AI"
    assert out["accent_color"] == "#3b82f6"


def test_single_brand_chart_unknown_brand_uses_fallbacks():
    out = serialize_single_brand_chart(
        "nonexistent_brand", [], window_days=7,
        now=datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert out["display_name"] == "nonexistent_brand"
    assert out["accent_color"] == "#9ca3af"



# ---------------------------------------------------------------------------
# window_days=1 -> per-minute bucketing for single-brand chart
# ---------------------------------------------------------------------------


def test_single_brand_chart_window_one_uses_minute_buckets():
    """window_days=1 must produce 1440 per-minute buckets."""
    now = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)
    posts = [
        _post(created_at="2026-07-06T11:30:00+00:00"),
        _post(created_at="2026-07-06T12:00:00+00:00"),
    ]
    out = serialize_single_brand_chart(
        "minimax", posts, window_days=1, now=now
    )
    assert out["granularity"] == "minute"
    assert len(out["days"]) == 1440
    for tab_key in out["tab_datasets"]:
        for cat in out["tab_datasets"][tab_key]:
            assert len(out["tab_datasets"][tab_key][cat]) == 1440


def test_single_brand_chart_window_seven_unchanged_by_minute_branch():
    """Regression guard: window_days=7 stays per-day with granularity='day'."""
    now = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)
    out = serialize_single_brand_chart(
        "minimax", [], window_days=7, now=now
    )
    assert out["granularity"] == "day"
    assert len(out["days"]) == 7
    for d in out["days"]:
        assert "T" not in d
