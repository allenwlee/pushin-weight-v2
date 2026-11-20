"""Stateless negative tests for the real-browser Each evidence boundary.

Synthetic observations below test rejection/validation only. They are never
written as browser artifacts or used to report normalized obligations passed.
"""
import itertools

import pytest
from bridgewright.assurance.contracts import AssuranceDeclaration
from bridgewright.assurance.engine import compile_obligations

from tests.ui_assurance import each


def declaration():
    return AssuranceDeclaration.model_validate_json(each.DECLARATION_PATH.read_text())


def packet():
    decl = declaration()
    return {
        "schema_version": "pushinweight.each-browser/v1",
        "producer": "tests.test_dashboard_each_browser.DashboardEachGeneralStyleBrowserTests.test_left_legend_matches_stack_and_emphasis_across_tabs_modes_sizes_locales",
        "identity": each.runtime_identity(decl), "errors": [], "external": [],
        "seed_post_count": 62, "cases": [],
    }


def case_without_traces(locale="en", width=1440, tab="sentiment", mode="percent"):
    keys, labels = ["a", "b"], ["A", "B"]
    return {
        "locale": locale, "width": width, "tab": tab, "mode": mode,
        "url": f"http://localhost/dashboard/each?brand=deepseek&locale={locale}&window=7",
        "source_url": f"http://localhost/dashboard/each/chart/?brand=deepseek&tab={tab}&locale={locale}&window=7",
        "source": {"brand": "deepseek", "tab": tab, "window_days": 7, "counting_unit": "posts",
                   "days": [str(i) for i in range(7)], "totals": [8, 9, 10, 8, 9, 10, 8],
                   "series": {"a": [4, 4, 5, 4, 4, 5, 4], "b": [4, 5, 5, 4, 5, 5, 4]},
                   "entries": [{"key": key, "label": label} for key, label in zip(keys, labels)]},
        "geometry": {"viewportWidth": width, "locale": locale, "tab": tab, "mode": mode, "keys": keys, "labels": labels, "canvasWidth": 500, "pageOverflow": 0,
                     "visible": True, "chartBusy": False, "plotTop": 0, "plotBottom": 100,
                     "plotLeft": 100, "legend": [
                         {"key": "b", "text": "B", "center": 0, "top": -5, "bottom": 5, "right": 90, "labelClipped": False},
                         {"key": "a", "text": "A", "center": 100, "top": 95, "bottom": 105, "right": 90, "labelClipped": False}]},
        "tooltip_keys": keys[::-1], "request_count": 4, "traces": [],
        "tooltip": {"index": 0, "keys": keys[::-1], "body": [["B: 4 (50.0%)"], ["A: 4 (50.0%)"]] if mode == "percent" else [["B: 4"], ["A: 4"]],
                    "footer": ["8 " + {"en": "posts", "zh_cn": "帖子", "ja": "投稿"}[locale]]},
    }


def complete_dimensions_without_traces():
    value = packet()
    value["cases"] = [case_without_traces(*args) for args in itertools.product(each.LOCALES, each.WIDTHS, each.TABS, each.MODES)]
    return value


def observed(pin="none", hover="none", mode="percent"):
    active = hover if hover != "none" else pin
    index = {"none": None, "first": 0, "other": 1}[active]
    return {"controls": {"pin": pin, "hover": hover, "mode": mode},
            "pinned": [] if pin == "none" else [{"first": "a", "other": "b"}[pin]],
            "visible": True, "values": ([[50, 400 / 9, 50, 50, 400 / 9, 50, 50], [50, 500 / 9, 50, 50, 500 / 9, 50, 50]] if mode == "percent" else [[4, 4, 5, 4, 4, 5, 4], [4, 5, 5, 4, 5, 5, 4]]),
            "fills": [f"rgba(0,0,0,{'.34' if index is None else '.48' if i == index else '.055'})".replace(",.", ",0.") for i in range(2)],
            "widths": [2.7 if i == index else 2 for i in range(2)], "request_count": 4}


def test_each_declaration_separates_controls_from_legacy_homepage():
    each_decl = declaration()
    assert {item.id for item in each_decl.controls} == {"pin", "hover", "mode"}
    assert len(compile_obligations(each_decl)) == 38
    legacy = AssuranceDeclaration.model_validate_json((each.ROOT / "tests/fixtures/ui_assurance/declaration.json").read_text())
    assert len(compile_obligations(legacy)) == 5191
    assert not any(item.id.startswith("each_") for item in legacy.controls)


@pytest.mark.parametrize("pin,hover,mode", list(itertools.product(each.EMPHASIS, each.EMPHASIS, each.MODES)))
def test_measured_hover_overrides_pin_and_mode_has_exact_payload_values(pin, hover, mode):
    each._checked_state(observed(pin, hover, mode), case_without_traces())


def test_missing_browser_observations_cannot_be_replaced_by_normalized_model_results():
    value = packet()
    value["results"] = [{"obligation_id": item.id, "status": "passed"} for item in compile_obligations(declaration())]
    with pytest.raises(AssertionError, match="Incomplete Each browser matrix"):
        each.build_each_evidence(declaration(), value)


@pytest.mark.parametrize("field", ["source_revision", "candidate_revision", "fixture_digest", "control_model_digest", "generator"])
def test_stale_runtime_identity_fails_before_evidence_generation(field):
    value = packet()
    value["identity"][field] = "stale"
    with pytest.raises(AssertionError, match="identity mismatch"):
        each.build_each_evidence(declaration(), value)


def test_full_dimensions_without_traces_are_insufficient():
    with pytest.raises(AssertionError, match="Missing actual Each action traces"):
        each.build_each_evidence(declaration(), complete_dimensions_without_traces())


def test_empty_action_trace_fails():
    value = complete_dimensions_without_traces()
    value["cases"][0]["traces"] = [{"initial": observed(), "steps": []}]
    with pytest.raises(AssertionError, match="Empty Each action trace"):
        each.build_each_evidence(declaration(), value)


def test_noop_browser_action_fails_measured_state_check():
    value = complete_dimensions_without_traces()
    value["cases"][0]["traces"] = [{"initial": observed(), "steps": [{"action": "pin:first", "observed": observed()}]}]
    with pytest.raises(AssertionError, match="DOM did not execute"):
        each.build_each_evidence(declaration(), value)


def test_missing_pin_other_observations_fail_complete_matrix():
    value = complete_dimensions_without_traces()
    value["cases"][0]["traces"] = [{"initial": observed(), "steps": [{"action": "pin:first", "observed": observed(pin="first")}]}]
    with pytest.raises(AssertionError, match="Missing pin/hover observation"):
        each.build_each_evidence(declaration(), value)


@pytest.mark.parametrize("mutation", ["values", "request_count", "pinned", "fills"])
def test_corrupt_chart_or_network_observation_fails(mutation):
    value = observed(pin="first", hover="other")
    value[mutation] = {"values": [[99] * 7] * 2, "request_count": 5, "pinned": ["b"], "fills": ["rgba(0,0,0,0.34)"] * 2}[mutation]
    with pytest.raises(AssertionError):
        each._checked_state(value, case_without_traces())


def test_runtime_errors_and_missing_required_record_fail():
    value = packet()
    value["errors"] = ["runtime failure"]
    with pytest.raises(AssertionError):
        each.build_each_evidence(declaration(), value)
    with pytest.raises(AssertionError, match="Incomplete Each browser matrix"):
        each.build_each_evidence(declaration(), packet())


@pytest.mark.parametrize("field", ["body", "footer"])
def test_incorrect_tooltip_counts_or_unit_fail(field):
    value = complete_dimensions_without_traces()
    value["cases"][0]["tooltip"][field] = ["fabricated tooltip"]
    with pytest.raises(AssertionError, match="Tooltip"):
        each.build_each_evidence(declaration(), value)


def test_unknown_invariant_cannot_pass_generic_runtime_snapshot_validation():
    from bridgewright.assurance.contracts import InvariantDefinition

    changed = declaration().model_copy(deep=True)
    changed.invariants.append(InvariantDefinition(
        id="unimplemented-headline-race", projections=["network"],
    ))
    with pytest.raises(AssertionError, match="Unknown Each invariant: unimplemented-headline-race"):
        each.build_each_evidence(changed, packet())


def test_preserved_production_role_fixture_checks_counts_and_entries():
    from copy import deepcopy

    counts = [8, 9, 10, 8, 9, 10, 8]
    source = {
        "entries": [{"key": key} for key in ("other", "official", "staff", "community")],
        "counting_unit": "posts", "days": [str(i) for i in range(7)], "totals": counts[:],
        "series": {"other": counts[:], "official": [0] * 7, "staff": [0] * 7, "community": [0] * 7},
    }
    each._checked_production_role_fixture(source, counts)
    changed = deepcopy(source)
    changed["series"]["other"][0] -= 1
    with pytest.raises(AssertionError, match="Other counts"):
        each._checked_production_role_fixture(changed, counts)
    changed = deepcopy(source)
    changed["series"]["official"][0] = 1
    with pytest.raises(AssertionError, match="classification changed"):
        each._checked_production_role_fixture(changed, counts)
    changed = deepcopy(source)
    changed["entries"].pop()
    with pytest.raises(AssertionError, match="entries changed"):
        each._checked_production_role_fixture(changed, counts)
