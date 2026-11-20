"""Bind Each obligations to the real-route browser's checked observations.

The legacy homepage declaration never represents Each. This adapter requires a
complete 96-case route matrix and actual DOM/chart action traces before it emits
any normalized Bridgewright result. Sample/model packets cannot close the gate.
"""
from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from bridgewright.assurance.contracts import AssuranceDeclaration, AssuranceEvidence
from bridgewright.assurance.engine import (
    assess_evidence,
    compile_obligations,
    control_model_digest,
)

ROOT = Path(__file__).resolve().parents[2]
DECLARATION_PATH = ROOT / "tests/fixtures/ui_assurance/each-declaration.json"
RUNTIME_PATH = ROOT / ".ollija/tmp/each-runtime.json"
EVIDENCE_PATH = ROOT / ".ollija/tmp/each-evidence.json"
TABS = ("sentiment", "post_types", "lang", "role", "audience_topics",
        "geopolitical_modes", "product_labels", "untracked_brand_promotions")
LOCALES = ("en", "zh_cn", "ja")
WIDTHS = (1440, 390)
MODES = ("percent", "volume")
EMPHASIS = ("none", "first", "other")
SOURCE_PATHS = (
    "core/models.py", "core/classification_readers.py", "core/materializations.py",
    "monitor/views.py", "monitor/urls.py",
    "monitor/templates/monitor/dashboard_each.html",
    "monitor/static/pw-each-chart.js", "monitor/static/pw-each-chart.css",
    "monitor/static/pro-general.css", "monitor/static/home-v20.css",
    "monitor/static/site-footer.css", "monitor/static/pw-icons.js",
    "monitor/static/pw-tz.js", "monitor/static/pw-feed.js",
    "monitor/static/pw-locale-toggle.js", "monitor/static/pw-shell.js",
    "monitor/templates/monitor/_pro_rail.html", "monitor/templates/monitor/_pro_masthead.html",
    "monitor/templates/monitor/_feed_initial_v22.html", "monitor/templates/monitor/_site_footer.html",
    "tests/general_style_browser.py", "tests/ui_assurance/local_preview.py",
    "locale/ja/LC_MESSAGES/django.mo", "locale/zh_Hans/LC_MESSAGES/django.mo",
    "locale/en/LC_MESSAGES/django.mo",
    "monitor/static/vendor/chartjs/chart.umd-4.4.0.min.js",
    "tests/test_dashboard_each_browser.py", "tests/each_area_fixture.py", "tests/v22_support.py", "tests/mockup_spec.py",
    "tests/golden/v22_mockup_fixture.json", "tests/ui_assurance/each.py",
)


def product_identity():
    digest = hashlib.sha256()
    for relative in SOURCE_PATHS:
        digest.update(relative.encode() + b"\0" + (ROOT / relative).read_bytes() + b"\0")
    return "worktree-sha256:" + digest.hexdigest()


def load_each_declaration():
    declaration = AssuranceDeclaration.model_validate_json(DECLARATION_PATH.read_text())
    assert declaration.source_revision == product_identity(), "Each source identity is stale"
    fixture = ROOT / declaration.fixture.path
    assert hashlib.sha256(fixture.read_bytes()).hexdigest() == declaration.fixture.sha256, "Each fixture digest is stale"
    return declaration


def load_seed_manifest():
    declaration = load_each_declaration()
    return json.loads((ROOT / declaration.fixture.path).read_text())


def runtime_identity(declaration):
    return {
        "source_revision": declaration.source_revision,
        "candidate_revision": product_identity(),
        "fixture_digest": declaration.fixture.sha256,
        "control_model_digest": control_model_digest(declaration),
        "generator": declaration.generator.label(),
        "environments": [{"id": "each-chromium", "browser_runtime": "playwright-chromium"}],
    }


def _checked_production_role_fixture(source, counts):
    """Pin the preserved0227 Role output; its UUID/text mismatch stays deferred."""
    keys = {entry["key"] for entry in source["entries"]}
    assert keys == {"official", "staff", "community", "other"}, "Production Role entries changed"
    assert source["counting_unit"] == "posts" and len(source["days"]) == 7
    assert source["totals"] == counts, "Production Role totals changed"
    assert source["series"]["other"] == counts, "Production Role Other counts changed"
    assert all(source["series"][key] == [0] * 7 for key in keys - {"other"}), "Production Role classification changed"


def _checked_state(state, case):
    """Check measured values against the HTTP payload, never against another model."""
    assert set(state["controls"]) == {"pin", "hover", "mode"}
    pin, hover, mode = (state["controls"][key] for key in ("pin", "hover", "mode"))
    assert pin in EMPHASIS and hover in EMPHASIS and mode in MODES
    keys = [entry["key"] for entry in case["source"]["entries"]]
    assert len(keys) >= 2 and len(set(keys)) == len(keys)
    category = "bug" if "bug" in keys else keys[0]
    other = next(key for key in keys if key != category)
    mapping = {"first": category, "other": other}
    assert state["pinned"] == ([] if pin == "none" else [mapping[pin]])
    assert state["visible"] is True
    sums = [sum(case["source"]["series"][key][i] for key in keys)
            for i in range(len(case["source"]["days"]))]
    expected = [case["source"]["series"][key] if mode == "volume" else
                [count * 100 / total if total else None for count, total in zip(case["source"]["series"][key], sums)]
                for key in keys]
    assert state["values"] == expected
    active = hover if hover != "none" else pin
    active_index = keys.index(mapping[active]) if active != "none" else None
    for index, (fill, width) in enumerate(zip(state["fills"], state["widths"], strict=True)):
        opacity = "0.34" if active_index is None else "0.48" if index == active_index else "0.055"
        assert fill.endswith(f",{opacity})")
        assert width == (2.7 if index == active_index else 2)
    assert len(state["fills"]) == len(keys)
    assert state["request_count"] == case["request_count"], "Each emphasis/mode triggered a request"


def validate_runtime(declaration, packet):
    assert packet["schema_version"] == "pushinweight.each-browser/v1"
    assert packet["producer"] == "tests.test_dashboard_each_browser.DashboardEachGeneralStyleBrowserTests.test_left_legend_matches_stack_and_emphasis_across_tabs_modes_sizes_locales"
    assert packet["identity"] == runtime_identity(declaration), "Each runtime identity mismatch"
    assert packet["errors"] == [] and packet["external"] == []
    assert packet["seed_post_count"] == 62
    cases = packet["cases"]
    expected_cases = set(itertools.product(LOCALES, WIDTHS, TABS, MODES))
    actual_cases = [(case["locale"], case["width"], case["tab"], case["mode"]) for case in cases]
    assert len(actual_cases) == len(set(actual_cases)) and set(actual_cases) == expected_cases, "Incomplete Each browser matrix"
    all_traces = []
    for case in cases:
        url = urlparse(case["url"])
        query = parse_qs(url.query)
        assert url.path == "/dashboard/each" and query["brand"] == ["deepseek"]
        assert query["locale"] == [case["locale"]] and query["window"] == ["7"]
        source_url = urlparse(case["source_url"])
        source_query = parse_qs(source_url.query)
        assert source_url.path == "/dashboard/each/chart/"
        assert source_query["tab"] == [case["tab"]] and source_query["brand"] == ["deepseek"]
        assert source_query["locale"] == [case["locale"]] and source_query["window"] == ["7"]
        source, geometry = case["source"], case["geometry"]
        assert geometry["viewportWidth"] == case["width"] and geometry["locale"] == case["locale"]
        assert geometry["tab"] == case["tab"] and geometry["mode"] == case["mode"]
        assert source["brand"] == "deepseek" and source["tab"] == case["tab"]
        assert source["window_days"] == 7 and len(source["days"]) == 7
        assert sum(source["totals"]) == 62, "Seeded cohort was not read by the real route"
        keys = [entry["key"] for entry in source["entries"]]
        labels = [entry["label"] for entry in source["entries"]]
        assert geometry["keys"] == keys and geometry["labels"] == labels
        legend = geometry["legend"]
        assert [item["key"] for item in legend] == keys[::-1]
        assert [item["text"] for item in legend] == labels[::-1]
        assert case["tooltip_keys"] == keys[::-1]
        tooltip = case["tooltip"]
        assert tooltip["keys"] == keys[::-1]
        bucket = tooltip["index"]
        assert 0 <= bucket < 7
        total = sum(source["series"][key][bucket] for key in keys)
        expected_body = []
        for entry in reversed(source["entries"]):
            count = source["series"][entry["key"]][bucket]
            suffix = f" ({count * 100 / total:.1f}%)" if case["mode"] == "percent" else ""
            expected_body.append([f"{entry['label']}: {count}{suffix}"])
        assert tooltip["body"] == expected_body, "Tooltip counts/percentages do not match payload"
        words = {"en": ("posts", "label assignments"), "zh_cn": ("帖子", "标签分配"), "ja": ("投稿", "ラベル割当")}
        noun = words[case["locale"]][0 if source["counting_unit"] == "posts" else 1]
        assert tooltip["footer"] == [f"{total} {noun}"], "Tooltip counting unit is incorrect"
        assert geometry["canvasWidth"] > 100 and geometry["pageOverflow"] <= 0
        assert geometry["visible"] and not geometry["chartBusy"]
        assert geometry["plotBottom"] > geometry["plotTop"]
        if case["tab"] == "role":
            _checked_production_role_fixture(source, load_seed_manifest()["counts"])
        else:
            for bucket in range(7):
                assert sum(source["series"][key][bucket] > 0 for key in keys) >= 2, "Each fixture lost its substantive daily stack"
        for i, item in enumerate(legend):
            expected_center = geometry["plotTop"] + i * (geometry["plotBottom"] - geometry["plotTop"]) / (len(legend) - 1)
            assert abs(item["center"] - expected_center) <= 1
            assert not item["labelClipped"] and item["right"] <= geometry["plotLeft"]
            if i:
                assert legend[i - 1]["bottom"] <= item["top"] + 1
        observed_pairs = set()
        assert case["traces"], "Missing actual Each action traces"
        for trace in case["traces"]:
            assert trace["steps"], "Empty Each action trace"
            current = trace["initial"]
            _checked_state(current, case)
            for step in trace["steps"]:
                key, value = step["action"].split(":", 1)
                assert key in current["controls"]
                controls = {**current["controls"], key: value}
                assert step["observed"]["controls"] == controls, "DOM did not execute declared action"
                _checked_state(step["observed"], case)
                current = step["observed"]
                if current["controls"]["mode"] == case["mode"]:
                    observed_pairs.add((current["controls"]["pin"], current["controls"]["hover"]))
            all_traces.append(trace)
        assert observed_pairs == set(itertools.product(EMPHASIS, repeat=2)), "Missing pin/hover observation"
    return all_traces


def build_each_evidence(declaration, packet):
    # Each declared invariant needs an explicit runtime implementation. Generic
    # snapshot validation must not close an unimplemented future invariant.
    for invariant in declaration.invariants:
        assert invariant.id == "each-stack-legend-tooltip-data-network", (
            f"Unknown Each invariant: {invariant.id}"
        )
    traces = validate_runtime(declaration, packet)
    results = []
    for obligation in compile_obligations(declaration):
        parts = obligation.id.split("/")
        witness = None
        for index, trace in enumerate(traces):
            steps = trace["steps"]
            if parts[0] == "transition":
                found = any(step["action"] == f"{parts[1]}:{parts[2]}" for step in steps)
            elif parts[0] == "inverse":
                actions = [step["action"] for step in steps]
                found = any(action == f"{parts[1]}:{parts[2]}" and f"{parts[1]}:{parts[3]}" in actions[i + 1:]
                            for i, action in enumerate(actions))
            elif parts[0] == "tway":
                required = dict(part.split("=", 1) for part in parts[2:])
                found = any(all(step["observed"]["controls"][key] == value for key, value in required.items()) for step in steps)
            elif parts[0] == "ordered":
                found = [step["action"] for step in steps] == parts[2:]
            elif parts[0] == "invariant":
                found = True  # Every observed state passed the payload/geometry checks above.
            else:
                raise AssertionError(f"Unhandled Each obligation: {obligation.id}")
            if found:
                witness = index
                break
        assert witness is not None, f"No actual browser witness for {obligation.id}"
        results.append({"obligation_id": obligation.id, "status": "passed", "replay_id": f"each-runtime:trace:{witness}"})
    evidence = AssuranceEvidence.model_validate({
        "schema_version": "bridgewright.assurance.evidence/v1", "profile": "stateful-ui-assurance/v1",
        "identity": runtime_identity(declaration), "results": results,
    })
    assessment = assess_evidence(declaration, evidence)
    assert assessment.status == "clean", assessment.model_dump_json()
    return evidence


def write_each_runtime(declaration, packet):
    evidence = build_each_evidence(declaration, packet)
    RUNTIME_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_PATH.write_text(json.dumps(packet, indent=2) + "\n")
    EVIDENCE_PATH.write_text(evidence.model_dump_json(indent=2) + "\n")
    return evidence


def assess_each_runtime():
    declaration = load_each_declaration()
    packet = json.loads(RUNTIME_PATH.read_text())
    evidence = build_each_evidence(declaration, packet)
    assert json.loads(EVIDENCE_PATH.read_text()) == evidence.model_dump(mode="json"), "Each normalized evidence is stale"
    return assess_evidence(declaration, evidence)
