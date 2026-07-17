# {{AGENT_ATTRIBUTION}}
"""Tests for x_monitor.dashboard.serialize_home_chart (U2 of
feat/pushin-weight-home-pages, 2026-07-06).

Covers the multi-brand Pushin' Weight home chart data layer:
- Per-day bucketing of posts into the active window
- Filter narrowing at post-include step (discourse, post_type, role,
  cn/us_nationalism, unsanctioned)
- Empty DB → all-zero series, no error
- Brand with 0 matching posts renders as zero-line, not omitted
- totals reflect filtered counts
- stacked breakdown maps known discourse keys + bucket unknown into __none__
- applied_filters echo
"""

from __future__ import annotations

from datetime import datetime, timezone

from x_monitor.dashboard import (
    _DASHBOARD_DISCOURSE_KEYS,
    _DASHBOARD_POST_TYPE_KEYS,
    _DASHBOARD_ROLE_KEYS,
    _DASHBOARD_NATIONALISM_KEYS,
    _post_matches_filter,
    serialize_home_chart,
)


def _post(
    *,
    created_at: str,
    brand: str = "minimax",
    discourse: list[str] | None = None,
    post_types: list[str] | None = None,
    role_key: str = "community",
    cn_nationalism: str | None = None,
    us_nationalism: str | None = None,
    unsanctioned: bool = False,
) -> dict:
    """Build a denormalized post dict for serialize_home_chart input."""
    return {
        "tweet_id": f"t-{created_at}",
        "created_at": created_at,
        "text": "stub",
        "brand_id": brand,
        "discourse": discourse or [],
        "post_types": post_types or [],
        "role_key": role_key,
        "cn_nationalism": cn_nationalism,
        "us_nationalism": us_nationalism,
        "unsanctioned": unsanctioned,
    }


# ---------------------------------------------------------------------------
# Constant sanity checks
# ---------------------------------------------------------------------------


def test_discourse_keys_count_is_10():
    assert len(_DASHBOARD_DISCOURSE_KEYS) == 10


def test_discourse_keys_contain_advertising_marketing():
    assert "advertising-marketing" in _DASHBOARD_DISCOURSE_KEYS


def test_post_type_keys_count_is_6():
    assert len(_DASHBOARD_POST_TYPE_KEYS) == 6


def test_post_type_keys_include_027_additions():
    assert "advertising_marketing" in _DASHBOARD_POST_TYPE_KEYS
    assert "event_announcement" in _DASHBOARD_POST_TYPE_KEYS


def test_role_keys_count_is_3():
    assert len(_DASHBOARD_ROLE_KEYS) == 3
    assert set(_DASHBOARD_ROLE_KEYS) == {"official", "staff", "community"}


def test_nationalism_keys_count_is_6():
    assert len(_DASHBOARD_NATIONALISM_KEYS) == 6


# ---------------------------------------------------------------------------
# _post_matches_filter
# ---------------------------------------------------------------------------


def test_filter_no_filters_matches_everything():
    p = _post(created_at="2026-07-06T12:00:00+00:00")
    assert _post_matches_filter(p, {}) is True


def test_filter_discourse_overlap_passes():
    p = _post(created_at="2026-07-06T12:00:00+00:00", discourse=["genuine_hype"])
    assert _post_matches_filter(p, {"discourse": ["sarcasm", "genuine_hype"]}) is True


def test_filter_discourse_no_overlap_blocks():
    p = _post(created_at="2026-07-06T12:00:00+00:00", discourse=["genuine_hype"])
    assert _post_matches_filter(p, {"discourse": ["sarcasm"]}) is False


def test_filter_post_types_overlap_passes():
    p = _post(
        created_at="2026-07-06T12:00:00+00:00",
        post_types=["buzz_releases", "hands_on_usage"],
    )
    assert _post_matches_filter(p, {"post_types": ["buzz_releases"]}) is True


def test_filter_role_matches():
    p = _post(created_at="2026-07-06T12:00:00+00:00", role_key="official")
    assert _post_matches_filter(p, {"role": ["official", "staff"]}) is True
    assert _post_matches_filter(p, {"role": ["community"]}) is False


# ---------------------------------------------------------------------------
# account.role other synthetic bucket (feat/role-filter-other)
# ---------------------------------------------------------------------------


def test_filter_role_other_matches_null_role():
    # role_key=None passes when other is in the active set.
    p = _post(created_at="2026-07-06T12:00:00+00:00", role_key=None)
    assert _post_matches_filter(p, {"role": ["other"]}) is True
    assert _post_matches_filter(p, {"role": ["official", "staff", "community", "other"]}) is True


def test_filter_role_other_matches_unknown_role_key():
    # role_key not in the 3 known taxonomy keys matches other.
    p = _post(created_at="2026-07-06T12:00:00+00:00", role_key="marketing_bot")
    assert _post_matches_filter(p, {"role": ["other"]}) is True


def test_filter_role_other_unchecked_blocks_null():
    # When other is unchecked, null-role posts are filtered out.
    p = _post(created_at="2026-07-06T12:00:00+00:00", role_key=None)
    assert _post_matches_filter(p, {"role": ["official", "staff", "community"]}) is False


def test_filter_role_other_unchecked_blocks_unknown():
    # When other is unchecked, unknown role_keys are filtered out.
    p = _post(created_at="2026-07-06T12:00:00+00:00", role_key="marketing_bot")
    assert _post_matches_filter(p, {"role": ["official", "staff", "community"]}) is False


def test_filter_role_empty_list_blocks_all():
    # Empty active role list blocks everything (no-opinion rule reversed for role).
    p = _post(created_at="2026-07-06T12:00:00+00:00", role_key="official")
    assert _post_matches_filter(p, {"role": []}) is False


def test_filter_cn_nationalism_matches():
    p = _post(created_at="2026-07-06T12:00:00+00:00", cn_nationalism="pro")
    assert _post_matches_filter(p, {"cn_nationalism": ["pro"]}) is True
    assert _post_matches_filter(p, {"cn_nationalism": ["anti"]}) is False


def test_filter_us_nationalism_matches():
    p = _post(created_at="2026-07-06T12:00:00+00:00", us_nationalism="mild_pro")
    assert _post_matches_filter(p, {"us_nationalism": ["mild_pro"]}) is True


def test_filter_unsanctioned_off_blocks_flagged():
    """Plan R7: unsanctioned off → posts with any unsanctioned flag are
    filtered out (the default UI state)."""
    p = _post(created_at="2026-07-06T12:00:00+00:00", unsanctioned=True)
    assert _post_matches_filter(p, {"unsanctioned": "off"}) is False
    p_ok = _post(created_at="2026-07-06T12:00:00+00:00", unsanctioned=False)
    assert _post_matches_filter(p_ok, {"unsanctioned": "off"}) is True


def test_filter_unsanctioned_only_keeps_flagged():
    """Plan R7: unsanctioned only → posts WITHOUT any unsanctioned flag
    are excluded (so the operator can see what was flagged)."""
    p = _post(created_at="2026-07-06T12:00:00+00:00", unsanctioned=True)
    assert _post_matches_filter(p, {"unsanctioned": "only"}) is True
    p_ok = _post(created_at="2026-07-06T12:00:00+00:00", unsanctioned=False)
    assert _post_matches_filter(p_ok, {"unsanctioned": "only"}) is False


def test_filter_unsanctioned_any_keeps_everything():
    p_flag = _post(created_at="2026-07-06T12:00:00+00:00", unsanctioned=True)
    p_ok = _post(created_at="2026-07-06T12:00:00+00:00", unsanctioned=False)
    assert _post_matches_filter(p_flag, {"unsanctioned": "any"}) is True
    assert _post_matches_filter(p_ok, {"unsanctioned": "any"}) is True


def test_filter_combined_narrows_intersectively():
    """Multiple filter dimensions intersect (AND, not OR)."""
    p = _post(
        created_at="2026-07-06T12:00:00+00:00",
        discourse=["genuine_hype"],
        post_types=["buzz_releases"],
        role_key="official",
    )
    # All three pass
    assert _post_matches_filter(
        p,
        {
            "discourse": ["genuine_hype"],
            "post_types": ["buzz_releases"],
            "role": ["official"],
        },
    ) is True
    # One fails → overall fail
    assert _post_matches_filter(
        p,
        {
            "discourse": ["sarcasm"],
            "post_types": ["buzz_releases"],
            "role": ["official"],
        },
    ) is False


# ---------------------------------------------------------------------------
# serialize_home_chart — happy path
# ---------------------------------------------------------------------------


def test_home_chart_returns_seven_day_default_window():
    out = serialize_home_chart(
        ["minimax"],
        {},
        window_days=7,
        latest_run=None,
        now=datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert out["window_days"] == 7
    assert len(out["days"]) == 7
    assert out["days"][0] == "2026-06-30"  # oldest
    assert out["days"][-1] == "2026-07-06"  # newest (today)
    # Empty input → all zeros
    assert out["series"] == {"minimax": [0] * 7}
    assert out["totals"] == {"minimax": 0}


def test_home_chart_buckets_a_post_into_correct_day():
    now = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)
    posts_by_brand = {
        "minimax": [
            _post(created_at="2026-07-04T08:00:00+00:00", brand="minimax"),
            _post(created_at="2026-07-06T01:00:00+00:00", brand="minimax"),
        ]
    }
    out = serialize_home_chart(
        ["minimax"], posts_by_brand, window_days=7, now=now
    )
    # 2026-07-04 is the 5th day from 2026-07-06 (days_ago=2), idx = 7-1-2 = 4
    # 2026-07-06 is the newest, idx = 7-1-0 = 6
    assert out["series"]["minimax"][4] == 1
    assert out["series"]["minimax"][6] == 1
    assert out["totals"]["minimax"] == 2


def test_home_chart_filters_narrow_counts():
    """With only `discourse=[genuine_hype]` active, the series per brand
    is smaller than the default-all count."""
    now = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)
    posts = [
        _post(
            created_at="2026-07-05T08:00:00+00:00",
            discourse=["genuine_hype"],
        ),
        _post(
            created_at="2026-07-05T09:00:00+00:00",
            discourse=["sarcasm"],
        ),
        _post(
            created_at="2026-07-05T10:00:00+00:00",
            discourse=[],
        ),
    ]
    default = serialize_home_chart(
        ["minimax"], {"minimax": posts}, window_days=7, now=now
    )
    filtered = serialize_home_chart(
        ["minimax"],
        {"minimax": posts},
        window_days=7,
        now=now,
        filters={"discourse": ["genuine_hype"]},
    )
    assert default["totals"]["minimax"] == 3
    assert filtered["totals"]["minimax"] == 1


def test_home_chart_brand_with_zero_matches_renders_as_zero_line():
    """Plan R6 + R8: a brand with 0 matching posts in the window renders
    as a zero-line, NOT omitted from the chart."""
    out = serialize_home_chart(
        ["minimax", "qwen"],
        {"minimax": [], "qwen": []},
        window_days=7,
        now=datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert set(out["series"].keys()) == {"minimax", "qwen"}
    assert out["series"]["minimax"] == [0] * 7
    assert out["series"]["qwen"] == [0] * 7


def test_home_chart_empty_db_is_zero_lines_no_error():
    out = serialize_home_chart(
        ["minimax", "qwen", "deepseek"],
        {},
        window_days=7,
        now=datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert all(s == [0] * 7 for s in out["series"].values())
    assert out["totals"] == {b: 0 for b in ["minimax", "qwen", "deepseek"]}


def test_home_chart_stacked_breaks_down_known_discourse_keys():
    """The stacked breakdown should include every known discourse key
    (10 keys) with zero-filled series, and bucket unknown keys into __none__."""
    now = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)
    posts = [
        _post(
            created_at="2026-07-05T08:00:00+00:00",
            discourse=["genuine_hype"],
        ),
        _post(
            created_at="2026-07-05T09:00:00+00:00",
            discourse=["unknown_key"],
        ),
    ]
    out = serialize_home_chart(
        ["minimax"], {"minimax": posts}, window_days=7, now=now
    )
    # All 10 known keys are present
    for dk in _DASHBOARD_DISCOURSE_KEYS:
        assert dk in out["stacked"]["minimax"]
        assert len(out["stacked"]["minimax"][dk]) == 7
    # __none__ buckets the unknown key
    assert "__none__" in out["stacked"]["minimax"]


def test_home_chart_applied_filters_echo():
    """The output echoes the input filter shape so the JS can confirm
    the server's narrowing matched its own state."""
    filters = {
        "discourse": ["genuine_hype", "sarcasm"],
        "post_types": ["buzz_releases"],
        "role": ["official"],
        "unsanctioned": "off",
    }
    out = serialize_home_chart(
        ["minimax"],
        {"minimax": []},
        window_days=7,
        now=datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc),
        filters=filters,
    )
    assert out["applied_filters"] == filters


def test_home_chart_colors_match_brand_accent_map():
    out = serialize_home_chart(
        ["minimax", "qwen", "unknown_brand"],
        {},
        window_days=7,
        now=datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert out["colors"]["minimax"] == "#3b82f6"
    assert out["colors"]["qwen"] == "#f97316"
    # Unknown brand → gray fallback (matches combined chart behavior)
    assert out["colors"]["unknown_brand"] == "#9ca3af"


def test_home_chart_latest_run_anchors_now():
    """When latest_run has a finished_at, the now-anchor is derived from
    it (matches serialize_combined_chart's contract)."""
    latest_run = {"finished_at": "2026-07-01T12:00:00+00:00"}
    out = serialize_home_chart(
        ["minimax"],
        {},
        window_days=7,
        latest_run=latest_run,
    )
    # Window is anchored to 2026-07-01
    assert out["days"][-1] == "2026-07-01"
    assert out["days"][0] == "2026-06-25"
