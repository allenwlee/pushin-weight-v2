"""Reference reducer, oracle, reversibility, and latest-intent contracts."""

from __future__ import annotations

import json
from pathlib import Path

from tests.ui_assurance.reference import (
    ALL,
    MULTI_CONTROLS,
    begin_request,
    bulk_action,
    filter_posts,
    initial_state,
    projection,
    set_control,
    settle_request,
    toggle_pulse_brand,
)

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/ui_assurance/data.json").read_text(
        encoding="utf-8"
    )
)


def test_deepseek_select_then_deselect_restores_all_brand_state() -> None:
    baseline = initial_state()
    selected = toggle_pulse_brand(baseline, "deepseek")
    restored = toggle_pulse_brand(selected, "deepseek")

    assert selected["filters"]["brands"] == ["deepseek"]
    assert projection(FIXTURE, selected)["feed"] == ["p01"]
    assert restored == baseline
    assert projection(FIXTURE, restored) == projection(FIXTURE, baseline)


def test_mimo_seven_to_one_race_commits_only_the_latest_generation() -> None:
    state = set_control(initial_state(), "window", 7)
    state = set_control(state, "brands", "mimo")
    state, old_generation = begin_request(state)
    state = set_control(state, "window", 1)
    state, new_generation = begin_request(state)

    state, new_result = settle_request(state, new_generation, succeeded=True)
    state, old_result = settle_request(state, old_generation, succeeded=True)

    assert new_result.committed is True
    assert old_result.committed is False
    assert old_result.warning_visible is False
    assert state["committed_generation"] == new_generation
    assert projection(FIXTURE, state)["chart"] == {
        "window": 1,
        "series": {"mimo": 1},
    }


def test_an_obsolete_failure_cannot_surface_a_warning() -> None:
    state, old_generation = begin_request(initial_state())
    state = set_control(state, "window", 7)
    state, new_generation = begin_request(state)
    state, _ = settle_request(state, new_generation, succeeded=True)
    state, old_result = settle_request(state, old_generation, succeeded=False)

    assert old_result.committed is False
    assert old_result.warning_visible is False


def test_aborts_never_surface_a_failure_warning() -> None:
    state, generation = begin_request(initial_state())
    _state, result = settle_request(
        state, generation, succeeded=False, aborted=True
    )

    assert result.committed is False
    assert result.warning_visible is False


def test_unsanctioned_only_and_off_are_an_exact_partition() -> None:
    state = set_control(initial_state(), "window", 365)
    off = filter_posts(FIXTURE, set_control(state, "unsanctioned", "off"))
    only = filter_posts(FIXTURE, set_control(state, "unsanctioned", "only"))
    in_window = {
        post["id"] for post in FIXTURE["posts"] if post["age_hours"] <= 365 * 24
    }

    off_ids = {post["id"] for post in off}
    only_ids = {post["id"] for post in only}
    assert off_ids.isdisjoint(only_ids)
    assert off_ids | only_ids == in_window
    assert all(not post["flagged"] for post in off)
    assert all(post["flagged"] for post in only)


def test_locale_change_preserves_filters_window_timezone_and_lenses() -> None:
    state = set_control(initial_state(), "brands", ["minimax", "qwen"])
    state = set_control(state, "sentiment", "positive")
    state = set_control(state, "window", 30)
    state = set_control(state, "timezone", "ca")
    state = set_control(state, "brand_lens", "closed")
    before = projection(FIXTURE, state)
    after = projection(FIXTURE, set_control(state, "locale", "zh_cn"))

    assert after["controls"] == before["controls"]
    assert after["persistence"]["timezone"] == "ca"
    assert after["persistence"]["brand_lens"] == "closed"
    assert after["persistence"]["locale"] == "zh_cn"


def test_or_within_one_dimension_and_and_across_dimensions() -> None:
    state = set_control(initial_state(), "brands", ["deepseek", "minimax"])
    state = set_control(state, "sentiment", ["mixed", "neutral"])
    assert projection(FIXTURE, state)["feed"] == ["p01", "p03"]

    state = set_control(state, "role", "official")
    assert projection(FIXTURE, state)["feed"] == ["p01"]


def test_every_multi_select_bulk_clear_and_all_is_reversible() -> None:
    for control in MULTI_CONTROLS:
        cleared = bulk_action(initial_state(), control, "clear")
        restored = bulk_action(cleared, control, "all")
        assert cleared["filters"][control] == []
        assert restored["filters"][control] == ALL


def test_hover_freeze_is_transient_brand_only_and_one_day_only() -> None:
    state = set_control(initial_state(), "brands", "qwen")
    state = set_control(state, "sentiment", "negative")
    state = set_control(state, "lang", "ja")
    state = set_control(state, "unsanctioned", "only")
    state = set_control(state, "freeze_point", "first")
    frozen_state = set_control(state, "chart_hover_freeze", "frozen")
    frozen = projection(FIXTURE, frozen_state)

    assert frozen["controls"]["sentiment"] == ["negative"]
    assert frozen["controls"]["lang"] == ["ja"]
    assert frozen["controls"]["unsanctioned"] == "only"
    assert frozen["network"]["effective_feed_filters"] == {
        "brands": ["qwen"],
        "window": 1,
    }
    assert frozen["network"]["chart_refresh_paused"] is True
    assert frozen["network"]["feed_refresh_paused"] is True
    assert frozen["accessibility"]["locale_selected"] == []

    same_state = set_control(frozen_state, "freeze_point", "same")
    assert projection(FIXTURE, same_state)["network"]["feed_refresh_paused"] is True

    released_state = set_control(same_state, "freeze_point", "other")
    released_state = set_control(
        released_state, "chart_hover_freeze", "released"
    )
    released = projection(FIXTURE, released_state)
    assert released["controls"] == frozen["controls"]
    assert released["network"]["chart_refresh_paused"] is False
    assert released["network"]["feed_refresh_paused"] is False
    assert released["accessibility"]["locale_selected"] == ["en"]

    unavailable_state = set_control(frozen_state, "window", 7)
    unavailable = projection(FIXTURE, unavailable_state)
    assert unavailable["network"]["chart_refresh_paused"] is False
    assert unavailable["network"]["feed_refresh_paused"] is False
