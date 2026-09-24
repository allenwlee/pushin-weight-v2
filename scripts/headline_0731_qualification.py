"""Join frozen generation, independent reviews and deployment evidence.

This is an evidence report, never deployment authority. Missing evidence fails
closed. No network calls, database writes, model comparison or retries.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

FIELDS = (
    "factual_support", "proportionality", "why_first_relevance",
    "secondary_usefulness", "translation_equivalence",
)
MODEL = "deepseek-ai/DeepSeek-V4-Flash-0731"
MEASUREMENT_POLICY = "final-output-severity-v2"


def mechanical_results(calls):
    """An invalid draft recovered by the existing critic is not a final failure."""
    valid_repairs = {c["batch_key"] for c in calls
                     if c["stage"] == "critic" and c["mechanical"]["valid"] is True}
    raw, recovered, unresolved = [], [], []
    for call in calls:
        if call["mechanical"]["valid"] is True:
            continue
        identity = f"{call['stage']}:{call['batch_key']}"
        raw.append(identity)
        target = recovered if call["stage"] == "editor" and call["batch_key"] in valid_repairs else unresolved
        target.append(identity)
    return raw, recovered, unresolved


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assess(artifact, reviews, manifest, operations):
    """Evaluate fixed gates; retain findings rather than averaging errors away."""
    gates = {f"SC{i}": False for i in range(1, 10)}
    calls = artifact["calls"]
    outcomes = artifact["brand_outcomes"]
    receipts = [call["usage"].get("provider_usage") or {} for call in calls]
    calibration = artifact["critic_calibration"]
    locale_fields = [f"{section}_{locale}" for section in ("headline", "secondary")
                     for locale in ("en", "zh_cn", "ja")]
    route_valid = all(r.get("model") == MODEL and r.get("provider") == "DeepInfra"
                      and r.get("service_tier") == "priority" and r.get("reasoning_tokens") == 0
                      and r.get("provider_request_id") for r in receipts)
    gates["SC1"] = bool(calls and route_valid
        and artifact["activation_assessment"]["complete"]
        and artifact["activation_assessment"]["every_eligible_brand_decided"]
        and len(calls) == artifact["preflight"]["planned_call_count"]
        and all(all(row["narrative"].get(f) for f in locale_fields)
                for row in outcomes if row.get("narrative"))
        and calibration["complete_control_set"]
        and not calibration["unsupported_false_accepts"]
        and not calibration["supported_false_holds"])
    cases = [case for review in reviews for case in review["review"]["cases"]]
    controls = [control for review in reviews for control in review["review"]["controls"]]
    expected_cases = {row["case_id"]: row for row in manifest["cases"]}
    assignments_valid = (len(reviews) == 3 and len({r["model"] for r in reviews}) == 3
        and {r["reviewer"] for r in reviews} == set(manifest["reviewers"])
        and len(cases) == 24 and Counter(c["case_id"] for c in cases) == Counter(expected_cases.keys())
        and all(len(r["review"]["cases"]) == 8
                and all(expected_cases[c["case_id"]]["reviewer"] == r["reviewer"] for c in r["review"]["cases"])
                for r in reviews))
    means = {field: sum(c[field] for c in cases) / len(cases) if cases else 0 for field in FIELDS}
    control_ids = [c["control"] for c in calibration["controls"]]
    # Imperfect wording is reported without turning every repaired control into
    # a release blocker. Fixture defects make that control inconclusive, never
    # a model failure or an automatically excluded success.
    controls_valid = (Counter(c["control_id"] for c in controls) == Counter(control_ids)
        and all(c["unsupported_claim_survives"] is False and c["new_material_error"] is False
                and c.get("fixture_defect", False) is False for c in controls))
    held = {(o["window_days"], o["brand_key"]) for o in outcomes if o["outcome"] == "hold"}
    false_holds = [c["case_id"] for c in cases
                  if (expected_cases[c["case_id"]]["window_days"], expected_cases[c["case_id"]]["brand_key"]) in held
                  and (c["why_first_relevance"] == 1 or c["secondary_usefulness"] == 1)]
    gates["SC2"] = bool(assignments_valid and controls_valid and not false_holds
                        and not any(c["critical_failure"] for c in cases)
                        and all(mean >= 4 for mean in means.values()))
    invalid, recovered, unresolved = mechanical_results(calls)
    gates["SC3"] = not unresolved
    costs = defaultdict(Decimal)
    tokens = defaultdict(lambda: [0, 0, 0])
    prices_complete = True
    for call, receipt in zip(calls, receipts, strict=True):
        if call["stage"] == "critic_calibration":
            continue
        window = str(call["envelope"]["analysis_packet"]["window_days"])
        try:
            cost = Decimal(str(receipt["cost_usd"]))
            if not cost.is_finite() or cost < 0:
                raise ValueError("invalid billed cost")
            costs[window] += cost
            for index, key in enumerate(("input_tokens", "output_tokens")):
                value = receipt[key]
                if type(value) is not int or value < 0:
                    raise ValueError("invalid tokens")
                tokens[window][index] += value
            tokens[window][2] += 1
        except (KeyError, ValueError, TypeError):
            prices_complete = False
    gates["SC5"] = (prices_complete and set(costs) == {"1", "7"}
                    and all(cost <= Decimal("0.30") for cost in costs.values())
                    and all(i <= 1_600_000 and o <= 350_000 and n <= 41 for i, o, n in tokens.values()))
    # Operational evidence must refer to this same locked generator and include
    # reproducible file receipts; the CLI verifies those hashes before assess.
    operational_match = operations.get("configuration_lock") == artifact["configuration_lock"]
    frequency = operations.get("observed_monthly_runs", {})
    monthly = (sum(costs[k] * Decimal(str(frequency[k])) for k in costs)
               if set(frequency) == {"1", "7"} else None)
    gates["SC5"] = bool(gates["SC5"] and operational_match and monthly is not None and monthly.is_finite() and monthly >= 0)
    timing = operations.get("timing", {})
    if operational_match and timing:
        gates["SC4"] = (timing.get("concurrency") == 3
            and 0 < timing.get("one_day_p95_seconds", 0) <= 720
            and 0 < timing.get("seven_day_p95_seconds", 0) <= 900
            and 0 <= timing.get("arrival_drain_utilization", 1) < .75)
    memory = operations.get("render_memory", {})
    if operational_match and memory:
        gates["SC6"] = (memory.get("worker_processes") == 3 and memory.get("bounded_queue") is True
            and 0 < memory.get("peak_bytes", 0) <= memory.get("limit_bytes", 0) * .75)
    for criterion in ("SC7", "SC8", "SC9"):
        gates[criterion] = operational_match and operations.get(criterion, {}).get("passed") is True
    return {
        "decision": "ready_0731" if all(gates.values()) else "improve_0731",
        "measurement_policy": MEASUREMENT_POLICY,
        "gates": gates, "unmet_success_criteria": [k for k, v in gates.items() if not v],
        "rubric_means": means, "critical_cases": [c for c in cases if c["critical_failure"]],
        "withheld_supported_cases": false_holds, "control_reviews": controls,
        "raw_mechanical_invalid": invalid, "normalized_mechanical_invalid": invalid,
        "critic_recovered_drafts": recovered, "final_mechanical_invalid": unresolved,
        "minor_case_issues": [{"case_id": c["case_id"], "issues": c["minor_issues"]}
                              for c in cases if c.get("minor_issues")],
        "fixture_defects": [c for c in controls if c.get("fixture_defect")],
        "representation_normalization": "none",
        "provider_billed_cost_by_window_usd": {k: str(v) for k, v in costs.items()},
        "input_output_calls_by_window": dict(tokens),
        "projected_monthly_headline_cost_usd": str(monthly) if monthly is not None else None,
        "operational_evidence_matches_configuration": operational_match,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--review-dir", type=Path, required=True)
    parser.add_argument("--operational-evidence", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest_path = args.review_dir / "manifest.json"
    artifact = json.loads(args.artifact.read_text())
    manifest = json.loads(manifest_path.read_text())
    summary_path = args.artifact.with_name("candidate-summary.json")
    summary = json.loads(summary_path.read_text())
    if (summary["artifact_sha256"] != sha256(args.artifact)
            or summary["frozen_input_sha256"] != manifest["source_sha256"]):
        raise ValueError("generation provenance mismatch")
    reviews = []
    files = [args.artifact, summary_path, manifest_path, args.review_dir / "rubric.md"]
    for reviewer in manifest["reviewers"]:
        path = args.review_dir / f"{reviewer}-scores.json"
        review = json.loads(path.read_text())
        if (review["artifact_sha256"] != sha256(args.artifact)
                or review["source_sha256"] != manifest["source_sha256"]
                or review["rubric_sha256"] != sha256(args.review_dir / "rubric.md")
                or review["input_sha256"] != sha256(args.review_dir / f"{reviewer}-blind-input.json")):
            raise ValueError("review provenance mismatch")
        files.extend([path, args.review_dir / f"{reviewer}-blind-input.json"])
        reviews.append(review)
    operations = {}
    if args.operational_evidence:
        operations = json.loads(args.operational_evidence.read_text())
        files.append(args.operational_evidence)
        if not operations.get("evidence_files"):
            raise ValueError("operational evidence needs file receipts")
        for path, expected_hash in operations["evidence_files"].items():
            if sha256(Path(path)) != expected_hash:
                raise ValueError("operational evidence file changed")
            files.append(Path(path))
    result = assess(artifact, reviews, manifest, operations)
    result["evidence_sha256"] = {str(p): sha256(p) for p in files}
    with args.output.open("x") as out:
        out.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"decision": result["decision"], "unmet_success_criteria": result["unmet_success_criteria"],
                      "report": str(args.output), "sha256": sha256(args.output)}))


if __name__ == "__main__":
    main()
