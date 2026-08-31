"""Execute normalized target obligations and emit Bridgewright evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from bridgewright.assurance.contracts import AssuranceDeclaration, AssuranceEvidence
from bridgewright.assurance.engine import compile_obligations, control_model_digest

from tests.ui_assurance.covering import covered_tuples, covering_rows, required_tuples
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


def load_documents(root: Path) -> tuple[AssuranceDeclaration, dict[str, Any]]:
    declaration = AssuranceDeclaration.model_validate_json(
        (root / "tests/fixtures/ui_assurance/declaration.json").read_text(
            encoding="utf-8"
        )
    )
    fixture_path = root / declaration.fixture.path
    fixture_bytes = fixture_path.read_bytes()
    if hashlib.sha256(fixture_bytes).hexdigest() != declaration.fixture.sha256:
        raise AssertionError("deterministic fixture digest does not match declaration")
    return declaration, json.loads(fixture_bytes)


def _apply_control(state: dict[str, Any], control: str, value: str) -> dict[str, Any]:
    if control == "bulk_action":
        if value == "idle":
            return state
        for target in MULTI_CONTROLS:
            state = bulk_action(state, target, value)
        return state
    return set_control(state, control, value)


def _apply_action(state: dict[str, Any], action: str) -> dict[str, Any]:
    if action.startswith("pulse:"):
        _, brand, desired = action.split(":", 2)
        selected = brand in state["pulse_brands"]
        if selected != (desired == "on"):
            return toggle_pulse_brand(state, brand)
        return state
    control, value = action.split(":", 1)
    return _apply_control(state, control, value)


def _check_transition(
    declaration: AssuranceDeclaration,
    fixture: dict[str, Any],
    control: str,
    value: str,
) -> None:
    state = _apply_control(initial_state(), control, value)
    observed = projection(fixture, state)
    assert observed["counts"] == len(observed["feed"])
    if control in MULTI_CONTROLS:
        expected = ALL if value == ALL else [value]
        assert state["filters"][control] == expected
    elif control in {"unsanctioned", "window"}:
        expected = int(value) if control == "window" else value
        assert state["filters"][control] == expected
    elif control != "bulk_action":
        assert state[control] == value
    elif value in {"all", "clear"}:
        expected = ALL if value == "all" else []
        assert all(state["filters"][target] == expected for target in MULTI_CONTROLS)
    assert any(item.id == control for item in declaration.controls)


def _check_inverse(
    fixture: dict[str, Any], control: str, value: str, initial: str
) -> None:
    state = _apply_control(initial_state(), control, value)
    state = _apply_control(state, control, initial)
    expected = initial_state()
    assert projection(fixture, state) == projection(fixture, expected)


def _check_tway(fixture: dict[str, Any], assignments: list[str]) -> None:
    state = initial_state()
    for assignment in assignments:
        control, value = assignment.split("=", 1)
        state = _apply_control(state, control, value)
    observed = projection(fixture, state)
    assert observed["counts"] == len(observed["feed"])
    assert observed["chart"]["window"] == state["filters"]["window"]
    for assignment in assignments:
        control, value = assignment.split("=", 1)
        if control in MULTI_CONTROLS:
            expected = ALL if value == ALL else [value]
            assert observed["controls"][control] == expected
        elif control in {"unsanctioned", "window"}:
            expected = int(value) if control == "window" else value
            assert observed["controls"][control] == expected
        elif control in {
            "feed_text",
            "headline_detail",
            "role_badge",
            "account_geography",
            "chart_hover_freeze",
            "freeze_point",
        }:
            assert observed["accessibility"][control] == value
        else:
            assert observed["persistence"][control] == value


def _check_invariant(fixture: dict[str, Any], invariant_id: str) -> None:
    if invariant_id == "filter-state-agrees":
        state = toggle_pulse_brand(initial_state(), "deepseek")
        observed = projection(fixture, state)
        assert observed["controls"]["brands"] == ["deepseek"]
        assert observed["accessibility"]["pulse_pressed"] == ["deepseek"]
        assert observed["persistence"]["filters"] == observed["controls"]
    elif invariant_id in {"feed-oracle-agrees", "chart-oracle-agrees"}:
        observed = projection(fixture, initial_state())
        assert observed["counts"] == len(observed["feed"])
        assert sum(observed["chart"]["series"].values()) == observed["counts"]
    elif invariant_id == "latest-intent-wins":
        state, old = begin_request(initial_state())
        state, new = begin_request(state)
        state, newest = settle_request(state, new, succeeded=True)
        state, obsolete = settle_request(state, old, succeeded=False)
        assert newest.committed and not obsolete.committed
        assert not obsolete.warning_visible
        assert state["committed_generation"] == new
    elif invariant_id == "locale-preserves-preferences":
        state = set_control(initial_state(), "brands", "minimax")
        before = projection(fixture, state)["controls"]
        after = projection(fixture, set_control(state, "locale", "zh_cn"))
        assert after["controls"] == before
    elif invariant_id == "flagged-partition-is-exact":
        state = set_control(initial_state(), "window", 365)
        off = filter_posts(fixture, set_control(state, "unsanctioned", "off"))
        only = filter_posts(fixture, set_control(state, "unsanctioned", "only"))
        off_ids = {row["id"] for row in off}
        only_ids = {row["id"] for row in only}
        in_window = {
            row["id"]
            for row in fixture["posts"]
            if row["age_hours"] <= 365 * 24
        }
        assert off_ids.isdisjoint(only_ids)
        assert off_ids | only_ids == in_window
        assert all(not row["flagged"] for row in off)
        assert all(row["flagged"] for row in only)
    elif invariant_id == "feed-disclosure-agrees":
        state = set_control(initial_state(), "feed_text", "source_expanded")
        state = set_control(state, "headline_detail", "expanded")
        state = set_control(state, "role_badge", "staff")
        accessibility = projection(fixture, state)["accessibility"]
        assert accessibility["feed_text"] == "source_expanded"
        assert accessibility["headline_detail"] == "expanded"
        assert accessibility["headline_expanded"] is True
        assert accessibility["role_badge"] == "staff"
        assert accessibility["role_label"] == "staff"
    elif invariant_id == "account-geography-agrees":
        expected_flags = {
            "none": [],
            "country": ["US"],
            "hierarchy": ["CN", "HK"],
            "taiwan": ["CN"],
            "region": [],
        }
        for kind, flags in expected_flags.items():
            state = set_control(initial_state(), "account_geography", kind)
            accessibility = projection(fixture, state)["accessibility"]
            assert accessibility["account_geography"] == kind
            assert accessibility["geography_flags"] == flags
            assert accessibility["geography_uses_tw_flag"] is False
        official = set_control(initial_state(), "role_badge", "official")
        official = set_control(official, "account_geography", "country")
        assert projection(fixture, official)["accessibility"]["metadata_order"] == [
            "followers", "role-official", "geography"
        ]
        staff = set_control(initial_state(), "role_badge", "staff")
        staff = set_control(staff, "account_geography", "hierarchy")
        assert projection(fixture, staff)["accessibility"]["metadata_order"] == [
            "followers", "geography", "role-staff"
        ]
        taiwan_zh = set_control(initial_state(), "locale", "zh_cn")
        taiwan_zh = set_control(taiwan_zh, "account_geography", "taiwan")
        assert projection(fixture, taiwan_zh)["accessibility"]["geography_label"] == "台湾"
    elif invariant_id == "hover-freeze-agrees":
        state = set_control(initial_state(), "brands", "qwen")
        state = set_control(state, "sentiment", "negative")
        state = set_control(state, "lang", "ja")
        state = set_control(state, "unsanctioned", "only")
        state = set_control(state, "freeze_point", "first")
        frozen = projection(
            fixture,
            set_control(state, "chart_hover_freeze", "frozen"),
        )
        assert frozen["controls"]["sentiment"] == ["negative"]
        assert frozen["controls"]["lang"] == ["ja"]
        assert frozen["controls"]["unsanctioned"] == "only"
        assert frozen["accessibility"]["locale_selected"] == []
        assert frozen["accessibility"]["feed_title"] == "bucket_datetime"
        assert frozen["network"]["effective_feed_filters"] == {
            "brands": ["qwen"],
            "window": 1,
        }
        assert frozen["network"]["chart_refresh_paused"] is True
        assert frozen["network"]["feed_refresh_paused"] is True
        assert frozen["network"]["bucket"] == "five-minute-half-open"

        same_state = set_control(state, "chart_hover_freeze", "frozen")
        same_state = set_control(same_state, "freeze_point", "same")
        assert projection(fixture, same_state)["network"]["feed_refresh_paused"] is True

        released_state = set_control(same_state, "freeze_point", "other")
        released_state = set_control(
            released_state, "chart_hover_freeze", "released"
        )
        released = projection(fixture, released_state)
        assert released["accessibility"]["locale_selected"] == ["en"]
        assert released["accessibility"]["feed_title"] == "default"
        assert released["network"]["chart_refresh_paused"] is False
        assert released["network"]["feed_refresh_paused"] is False
        assert released["network"]["effective_feed_filters"] == released["controls"]

        unavailable_state = set_control(state, "window", 7)
        unavailable_state = set_control(
            unavailable_state, "chart_hover_freeze", "frozen"
        )
        unavailable = projection(fixture, unavailable_state)
        assert unavailable["network"]["chart_refresh_paused"] is False
        assert unavailable["accessibility"]["locale_selected"] == ["en"]
    else:
        raise AssertionError(f"unimplemented invariant: {invariant_id}")


def _check_race(
    fixture: dict[str, Any], older_action: str, newer_action: str, fault: str
) -> None:
    state = _apply_action(initial_state(), older_action)
    state, old = begin_request(state)
    state = _apply_action(state, newer_action)
    state, new = begin_request(state)
    state, latest = settle_request(state, new, succeeded=True)
    assert latest.committed and not latest.warning_visible

    if fault in {"delayed", "out_of_order"}:
        state, obsolete = settle_request(state, old, succeeded=True)
        assert not obsolete.committed and not obsolete.warning_visible
    elif fault == "failed":
        state, obsolete = settle_request(state, old, succeeded=False)
        assert not obsolete.committed and not obsolete.warning_visible
    elif fault == "aborted":
        state, obsolete = settle_request(
            state, old, succeeded=False, aborted=True
        )
        assert not obsolete.committed and not obsolete.warning_visible
    elif fault == "duplicate":
        state, first = settle_request(state, old, succeeded=True)
        state, duplicate = settle_request(state, old, succeeded=True)
        assert not first.committed and not first.warning_visible
        assert not duplicate.committed and not duplicate.warning_visible
    else:
        raise AssertionError(f"unimplemented race fault: {fault}")
    assert state["committed_generation"] == new
    expected = _apply_action(_apply_action(initial_state(), older_action), newer_action)
    observed_projection = projection(fixture, state)
    expected_projection = projection(fixture, expected)
    assert observed_projection["controls"] == expected_projection["controls"]
    for key in ("chart_hover_freeze", "freeze_point", "locale_selected"):
        assert observed_projection["accessibility"][key] == expected_projection[
            "accessibility"
        ][key]


def _check_seed(fixture: dict[str, Any], seed_id: str) -> None:
    if seed_id == "deepseek-select-deselect-restores-all":
        baseline = initial_state()
        state = toggle_pulse_brand(baseline, "deepseek")
        assert projection(fixture, state)["feed"] == ["p01"]
        assert toggle_pulse_brand(state, "deepseek") == baseline
    elif seed_id == "mimo-seven-to-one-latest-wins":
        state = set_control(initial_state(), "window", 7)
        state = set_control(state, "brands", "mimo")
        state, old = begin_request(state)
        state = set_control(state, "window", 1)
        state, new = begin_request(state)
        state, result = settle_request(state, new, succeeded=True)
        state, obsolete = settle_request(state, old, succeeded=False)
        assert result.committed and not obsolete.warning_visible
        assert projection(fixture, state)["chart"] == {
            "window": 1,
            "series": {"mimo": 1},
        }
    elif seed_id == "unsanctioned-only-off-partition":
        _check_invariant(fixture, "flagged-partition-is-exact")
    elif seed_id == "hover-freeze-preserves-brand-and-restores-locale":
        state = set_control(initial_state(), "brands", "qwen")
        state = set_control(state, "freeze_point", "first")
        state = set_control(state, "chart_hover_freeze", "frozen")
        frozen = projection(fixture, state)
        assert frozen["controls"]["brands"] == ["qwen"]
        assert frozen["accessibility"]["locale_selected"] == []
        state = set_control(state, "freeze_point", "same")
        assert projection(fixture, state)["network"]["feed_refresh_paused"] is True
        state = set_control(state, "freeze_point", "other")
        state = set_control(state, "chart_hover_freeze", "released")
        released = projection(fixture, state)
        assert released["controls"]["brands"] == ["qwen"]
        assert released["accessibility"]["locale_selected"] == ["en"]
        assert released["network"]["feed_refresh_paused"] is False
    elif seed_id == "guiding-country-taiwan-region-stay-distinct":
        hierarchy = projection(
            fixture,
            set_control(initial_state(), "account_geography", "hierarchy"),
        )["accessibility"]
        taiwan = projection(
            fixture,
            set_control(initial_state(), "account_geography", "taiwan"),
        )["accessibility"]
        region = projection(
            fixture,
            set_control(initial_state(), "account_geography", "region"),
        )["accessibility"]
        assert hierarchy["geography_flags"] == ["CN", "HK"]
        assert taiwan["geography_flags"] == ["CN"]
        assert taiwan["geography_uses_tw_flag"] is False
        assert region["geography_flags"] == []
    else:
        raise AssertionError(f"unimplemented seed: {seed_id}")


def _check_ordered(
    fixture: dict[str, Any], group_id: str, actions: list[str]
) -> None:
    state = initial_state()
    for action in actions:
        state = _apply_action(state, action)
    observed = projection(fixture, state)
    assert observed["counts"] == len(observed["feed"])
    assert observed["persistence"]["filters"] == observed["controls"]

    def last_value(prefix: str) -> str | None:
        for action in reversed(actions):
            if action.startswith(f"{prefix}:"):
                return action.split(":", 1)[1]
        return None

    if group_id == "chart-intent-order":
        brand = last_value("brands")
        window = last_value("window")
        if brand is not None:
            assert observed["controls"]["brands"] == [brand]
        if window is not None:
            assert observed["chart"]["window"] == int(window)
    elif group_id == "brand-reversal-order":
        desired = last_value("pulse")
        if desired is not None:
            brand, enabled = desired.split(":", 1)
            expected = [brand] if enabled == "on" else ALL
            assert observed["controls"]["brands"] == expected
            assert observed["accessibility"]["pulse_pressed"] == (
                [brand] if enabled == "on" else []
            )
    elif group_id == "flag-reversal-order":
        mode = last_value("unsanctioned")
        if mode is not None:
            assert observed["controls"]["unsanctioned"] == mode
    elif group_id == "preference-order":
        brand = last_value("brands")
        locale = last_value("locale")
        timezone = last_value("timezone")
        if brand is not None:
            assert observed["controls"]["brands"] == [brand]
        if locale is not None:
            assert observed["persistence"]["locale"] == locale
        if timezone is not None:
            assert observed["persistence"]["timezone"] == timezone
    elif group_id == "zh-text-order":
        assert observed["accessibility"]["feed_text"] == last_value("feed_text")
    elif group_id == "headline-disclosure-order":
        assert observed["accessibility"]["headline_detail"] == last_value(
            "headline_detail"
        )
    elif group_id == "geography-presentation-order":
        assert observed["accessibility"]["account_geography"] == last_value(
            "account_geography"
        )
    elif group_id == "hover-freeze-state-order":
        assert observed["accessibility"]["chart_hover_freeze"] == last_value(
            "chart_hover_freeze"
        )
    elif group_id == "hover-freeze-point-order":
        assert observed["accessibility"]["freeze_point"] == last_value(
            "freeze_point"
        )
    else:
        raise AssertionError(f"unimplemented ordered group: {group_id}")


def _execute_obligation(
    declaration: AssuranceDeclaration,
    fixture: dict[str, Any],
    obligation_id: str,
) -> None:
    parts = obligation_id.split("/")
    family = parts[0]
    if family == "transition":
        _check_transition(declaration, fixture, parts[1], parts[2])
    elif family == "inverse":
        _check_inverse(fixture, parts[1], parts[2], parts[3])
    elif family == "tway":
        _check_tway(fixture, parts[2:])
    elif family == "ordered":
        _check_ordered(fixture, parts[1], parts[2:])
    elif family == "invariant":
        _check_invariant(fixture, parts[1])
    elif family == "race":
        scenario = next(item for item in declaration.races if item.id == parts[1])
        _check_race(
            fixture,
            scenario.older_action,
            scenario.newer_action,
            parts[2],
        )
    elif family == "seed":
        _check_seed(fixture, parts[1])
    else:
        raise AssertionError(f"unimplemented obligation family: {family}")


def build_evidence(
    root: Path,
    *,
    candidate_revision: str,
    browser_runtime: str,
) -> AssuranceEvidence:
    declaration, fixture = load_documents(root)
    declaration_data = declaration.model_dump(mode="json")
    rows = covering_rows(declaration_data)
    assert covered_tuples(declaration_data, rows) == required_tuples(declaration_data)

    results = []
    for obligation in compile_obligations(declaration):
        try:
            _execute_obligation(declaration, fixture, obligation.id)
        except Exception as error:  # noqa: BLE001 - evidence must record any runner failure
            results.append(
                {
                    "obligation_id": obligation.id,
                    "status": "failed",
                    "replay_id": f"{type(error).__name__}:{obligation.id}",
                }
            )
        else:
            results.append({"obligation_id": obligation.id, "status": "passed"})

    return AssuranceEvidence.model_validate(
        {
            "schema_version": "bridgewright.assurance.evidence/v1",
            "profile": "stateful-ui-assurance/v1",
            "identity": {
                "source_revision": declaration.source_revision,
                "candidate_revision": candidate_revision,
                "fixture_digest": declaration.fixture.sha256,
                "control_model_digest": control_model_digest(declaration),
                "generator": declaration.generator.label(),
                "environments": [
                    {
                        "id": "desktop-chromium",
                        "browser_runtime": browser_runtime,
                    }
                ],
            },
            "results": results,
        }
    )
