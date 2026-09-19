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
    "tests/test_performance_declarations.py",
    "tests/test_fix_ui_skill_assurance.py",
    "tests/test_cyber_quan_icon_contract.py",
    "tests/test_cyber_quan_visual_regression.py",
    "tests/test_trend_narrative_projection_fallback_names.py",
    "tests/test_feed_geography.py",
    "tests/test_views.py",
    "tests/test_home_v22_filter_pills.py",
    "tests/test_home_v22_feed_row_shape.py",
    "tests/test_home_v22_browser.py::HomeV22BrowserTests::test_stage1_taxonomy_filters_round_trip_without_cross_brand_product_matches",
    "tests/test_home_v22_browser.py::HomeV22MetadataParityBrowserTests::test_multibrand_product_filter_and_brand_page_keep_brand_provenance",
    "tests/test_home_v22_browser.py::HomeV22MetadataParityBrowserTests::test_classification_states_render_without_fabricated_taxonomy",
    "tests/test_home_v22_browser.py::HomeV22MetadataParityBrowserTests::test_old_taxonomy_url_hydrates_canonical_controls_and_visible_icons",
    "tests/test_taxonomy_compatibility_surfaces.py",
    "tests/test_home_chart_pulse.py::HomeChartPulseTests::test_empty_product_labels_remain_visible_by_default_but_not_when_filtered",
    "tests/test_home_chart_pulse.py::HomeChartPulseTests::test_type_and_product_edges_require_exact_current_classified_state",
    "tests/test_home_v22_browser.py::HomeV22BrowserTests::test_per_brand_narratives_render_bilingually_as_semantic_cards",
    "tests/test_home_v22_browser.py::HomeV22MetadataParityBrowserTests::test_account_geography_matches_initial_and_replacement_feed_in_both_locales",
    "tests/test_home_v22_browser.py::HomeV22MetadataParityBrowserTests::test_feed_metadata_projection_has_a_bounded_query_count",
    "tests/test_home_v22_browser.py::HomeV22MetadataParityBrowserTests::test_hover_freeze_feed_range_is_half_open_and_keeps_only_brand_filter",
    "tests/test_home_v22_browser.py::HomeV22MetadataParityBrowserTests::test_hover_freeze_feed_range_rejects_invalid_or_out_of_horizon_values",
    "tests/test_home_v22_browser.py::HomeV22MetadataParityBrowserTests::test_hover_freeze_click_persists_then_restores_the_mobile_home",
    "tests/test_home_v22_browser.py::HomeV22MetadataParityBrowserTests::test_hover_freeze_zh_cn_datetime_and_restore_at_320px",
]
FULL_ADDITIONAL_TESTS = [
    "tests/test_home_chart_pulse.py",
    "tests/test_home_v22_topbar_layout.py",
    "tests/test_ui_assurance_brand_inventory.py",
    "tests/test_home_v22_browser.py::HomeV22BrowserTests::test_anonymous_filters_window_and_pulse_share_one_request_state",
]


def _run(*command: str, env_overrides: dict[str, str] | None = None) -> None:
    environment = None
    if env_overrides:
        environment = {**os.environ, **env_overrides}
    subprocess.run(command, cwd=ROOT, check=True, env=environment)


def _run_json(*command: str) -> dict[str, object]:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{command[1]} did not return JSON") from error
    if not isinstance(payload, dict):
        raise TypeError(f"{command[1]} returned a non-object result")
    return payload


def _require_candidate_performance_args(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> None:
    if args.scope != "candidate":
        return
    if not args.candidate_revision:
        parser.error("--candidate-revision is required for candidate scope")
    performance_values = {
        "--performance-state-home": args.performance_state_home,
        "--performance-runtime": args.performance_runtime,
        "--performance-target-revision": args.performance_target_revision,
        "--performance-installed-package-commit": args.performance_installed_package_commit,
        "--performance-data-source-identity": args.performance_data_source_identity,
        "--performance-data-source-kind": args.performance_data_source_kind,
        "--performance-declaration": args.performance_declaration,
    }
    missing = [name for name, value in performance_values.items() if not value]
    if missing:
        parser.error("candidate performance gate requires: " + ", ".join(missing))
    if args.performance_data_source_kind == "fixture" and not args.performance_fixture_digest:
        parser.error("fixture performance gates require --performance-fixture-digest")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=("affected", "candidate"), required=True)
    parser.add_argument("--candidate-revision")
    parser.add_argument("--bridgewright", default="bridgewright")
    parser.add_argument("--performance-state-home")
    parser.add_argument("--performance-runtime")
    parser.add_argument("--performance-target-revision")
    parser.add_argument("--performance-installed-package-commit")
    parser.add_argument("--performance-data-source-identity")
    parser.add_argument("--performance-data-source-kind", choices=("fixture", "environment"))
    parser.add_argument("--performance-fixture-digest")
    parser.add_argument("--performance-declaration")
    args = parser.parse_args(argv)
    _require_candidate_performance_args(args, parser)

    _run(args.bridgewright, "assurance-validate", "--project-root", str(ROOT))
    _run(args.bridgewright, "assurance-prescribe", "--project-root", str(ROOT))
    performance_declaration = (
        args.performance_declaration
        if args.scope == "candidate"
        else "tests/fixtures/performance_assurance/declaration.json"
    )
    _run(
        args.bridgewright,
        "performance-validate",
        "--project-root",
        str(ROOT),
        "--declaration",
        performance_declaration,
    )
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
        performance_run = _run_json(
            args.bridgewright,
            "performance-run",
            "--project-root",
            str(ROOT),
            "--state-home",
            args.performance_state_home,
            "--runtime",
            args.performance_runtime,
            "--target-revision",
            args.performance_target_revision,
            "--installed-package-commit",
            args.performance_installed_package_commit,
            "--data-source-identity",
            args.performance_data_source_identity,
            "--data-source-kind",
            args.performance_data_source_kind,
            "--declaration",
            args.performance_declaration,
            *((["--fixture-digest", args.performance_fixture_digest]) if args.performance_fixture_digest else []),
        )
        attempt_id = performance_run.get("attempt_id")
        if not isinstance(attempt_id, str) or not attempt_id:
            raise RuntimeError("performance-run did not return an attempt_id")
        performance_result = _run_json(
            args.bridgewright,
            "performance-result",
            "--state-home",
            args.performance_state_home,
            "--attempt-id",
            attempt_id,
        )
        if performance_result.get("attempt_id") != attempt_id:
            raise RuntimeError("performance-result did not return the performance-run attempt")
        if performance_result.get("status") != "clean":
            raise RuntimeError("performance-result was not clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
