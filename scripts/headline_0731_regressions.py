"""Replay known factual failures through the production critic, without publishing.

Mechanical success is not semantic success. The artifact contains the frozen
source, incorrect draft and final output for a separate source-grounded review.
"""

from __future__ import annotations

import argparse
import json
import os
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
import django

django.setup()

from monitor.trend_narrative_evaluation import (
    EvaluationManifest,
    _EvaluationLedger,
    _execute_call,
)
from monitor.trend_narrative_generation import (
    HeadlineGenerationError,
    build_per_brand_critic_request,
    build_per_brand_editor_request,
    validate_per_brand_critic_response,
    validate_per_brand_editor_response,
)
from scripts.headline_0731_bakeoff import _load_literal_env, _sha256, configuration_lock
from x_monitor.config import HeadlineNarrativeConfig

FIXTURE = Path("tests/fixtures/headline_source_scope_regressions.json")


def regression_request(case, config):
    editor, _ = build_per_brand_editor_request(case["packet"], config)
    draft = {"editor_response_schema_version": 3, "packet_hash": editor["packet_hash"],
             "batch_key": editor["batch_key"], "brands": [case["incorrect_narrative"]]}
    raw = json.dumps(draft, ensure_ascii=False)
    try:
        parsed = validate_per_brand_editor_response(draft, editor)
    except HeadlineGenerationError as exc:
        diagnostics = {"status": "invalid", "error_codes": [exc.code]}
    else:
        diagnostics = {"status": "valid", "response": parsed}
    return build_per_brand_critic_request(editor, raw, diagnostics, config)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configuration-artifact", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--secret-env", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    args = parser.parse_args()
    config = HeadlineNarrativeConfig.model_validate(
        json.loads(args.configuration_artifact.read_text())["configuration"])
    if config.provider != "deepinfra" or not config.critic_prompt_version.startswith("headline-critic-finance-source-audit-"):
        raise ValueError("regression requires the pinned 0731 source-audit route")
    fixture = json.loads(args.fixture.read_text())
    case_ids = {c["case_id"] for c in fixture["cases"]}
    if (fixture.get("fixture_schema_version") != 2
            or not fixture["cases"] or len(case_ids) != len(fixture["cases"])
            or set(fixture.get("source_artifact_sha256_by_case", {})) != case_ids):
        raise ValueError("regression fixture must contain unique sourced failures")
    manifest = EvaluationManifest.from_mapping({
        "run_id": f"0731-known-source-scope-regressions-{args.fixture.stem}", "reviewer": "separate-review-required",
        "model": config.model, "max_calls": len(case_ids), "input_token_budget": 75_000 * len(case_ids),
        "output_token_budget": 8_000 * len(case_ids), "dollar_budget": str(Decimal("0.05") * len(case_ids)),
        "input_dollars_per_million_tokens": "0.09", "output_dollars_per_million_tokens": "0.27",
        "pricing_version": "deepinfra-priority-0731-2026-09-24",
        "pricing_checked_at": "2026-09-24T00:00:00+09:00", "context_window_tokens": 500_000,
        "brand_cap": 2, "concurrency": 1, "max_packet_bytes": 384 * 1024,
    })
    # Exclusive creation means a rerun cannot silently repeat paid entitlements.
    args.output_dir.mkdir(parents=True, exist_ok=False)
    _load_literal_env(args.secret_env)
    ledger, calls, results = _EvaluationLedger(manifest), [], []
    artifact = {"configuration_lock": configuration_lock(config),
                "fixture_sha256": _sha256(args.fixture), "runner_sha256": _sha256(Path(__file__)),
                "cases": results, "calls": calls}
    for case in fixture["cases"]:
        envelope, request = regression_request(case, config)
        try:
            row = _execute_call("critic", envelope, request, config, ledger, calls,
                                api_key=os.environ.get("DEEPINFRA_API_KEY"), client_factory=None,
                                cancellation_path=None)
        finally:
            # Retain an accepted transport's receipt even if parsing fails or
            # the provider raises; a later invocation uses a new directory.
            (args.output_dir / "artifact.json").write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n")
        result = {"case_id": case["case_id"], "acceptance": case["acceptance"],
                  "source": case["packet"], "incorrect_narrative": case["incorrect_narrative"]}
        try:
            parsed = validate_per_brand_critic_response(json.loads(row["raw_response"]), envelope)
            row["mechanical"] = {"valid": True}
            result["final"] = parsed["decisions"][0]
        except (HeadlineGenerationError, ValueError) as exc:
            row["mechanical"] = {"valid": False, "error_code": getattr(exc, "code", "invalid_json")}
            result["final"] = None
        results.append(result)
        (args.output_dir / "artifact.json").write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"cases": len(results), "mechanical_valid": sum(c["mechanical"]["valid"] for c in calls),
                      "semantic_status": "independent_review_required", "artifact": str(args.output_dir / "artifact.json")}))


if __name__ == "__main__":
    main()
