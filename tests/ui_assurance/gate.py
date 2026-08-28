"""Affected/full PushinWeight UI assurance gate used by fix-ui and CI."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from tests.ui_assurance.evidence import build_evidence

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_RELATIVE_PATH = Path(".ollija/tmp/ui-assurance-evidence.json")
EVIDENCE_PATH = ROOT / EVIDENCE_RELATIVE_PATH
FOCUSED_TESTS = [
    "tests/test_ui_assurance_contract.py",
    "tests/test_ui_assurance_evidence.py",
    "tests/test_ui_assurance_reference.py",
    "tests/test_ui_assurance_browser.py",
    "tests/test_fix_ui_skill_assurance.py",
    "tests/test_cyber_quan_icon_contract.py",
    "tests/test_cyber_quan_visual_regression.py",
    "tests/test_trend_narrative_projection_fallback_names.py",
    "tests/test_home_v22_browser.py::HomeV22MetadataParityBrowserTests::test_hover_freeze_feed_range_is_half_open_and_keeps_only_brand_filter",
    "tests/test_home_v22_browser.py::HomeV22MetadataParityBrowserTests::test_hover_freeze_feed_range_rejects_invalid_or_out_of_horizon_values",
    "tests/test_home_v22_browser.py::HomeV22MetadataParityBrowserTests::test_hover_freeze_click_persists_then_restores_the_mobile_home",
    "tests/test_home_v22_browser.py::HomeV22MetadataParityBrowserTests::test_hover_freeze_zh_cn_datetime_and_restore_at_320px",
]
FULL_ADDITIONAL_TESTS = [
    "tests/test_home_chart_pulse.py",
    "tests/test_home_v22_filter_pills.py",
    "tests/test_home_v22_topbar_layout.py",
    "tests/test_ui_assurance_brand_inventory.py",
    "tests/test_home_v22_browser.py::HomeV22BrowserTests::test_anonymous_filters_window_and_pulse_share_one_request_state",
]


def _run(*command: str, env_overrides: dict[str, str] | None = None) -> None:
    environment = None
    if env_overrides:
        environment = {**os.environ, **env_overrides}
    subprocess.run(command, cwd=ROOT, check=True, env=environment)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=("affected", "candidate"), required=True)
    parser.add_argument("--candidate-revision")
    parser.add_argument("--bridgewright", default="bridgewright")
    args = parser.parse_args(argv)

    _run(args.bridgewright, "assurance-validate", "--project-root", str(ROOT))
    _run(args.bridgewright, "assurance-prescribe", "--project-root", str(ROOT))
    tests = FOCUSED_TESTS + (FULL_ADDITIONAL_TESTS if args.scope == "candidate" else [])
    # The existing Django browser suites intentionally use HTTP live-server
    # URLs; isolate their test-only DEBUG setting from Bridgewright and Node.
    _run(
        "pytest",
        "-q",
        *tests,
        env_overrides={"DEBUG": "1", "CYBER_QUAN_CAPTURE_ONLY": ""},
    )
    _run("node", "tests/test_pw_chart_filter.js")
    _run("node", "tests/test_pw_feed_formatter.js")
    _run("node", "tests/test_pw_tz.js")

    if args.scope == "candidate":
        if not args.candidate_revision:
            parser.error("--candidate-revision is required for candidate scope")
        evidence = build_evidence(
            ROOT,
            candidate_revision=args.candidate_revision,
            browser_runtime="playwright-chromium",
        )
        EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE_PATH.unlink(missing_ok=True)
        EVIDENCE_PATH.write_text(
            json.dumps(evidence.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _run(
            args.bridgewright,
            "assurance-assess",
            "--project-root",
            str(ROOT),
            "--evidence",
            str(EVIDENCE_RELATIVE_PATH),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
