"""Complete V4 Flash 0731 evaluation using model-adapted five-post batches."""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from scripts import u18_fresh40_batch20_compare as control
from scripts import u18_fresh40_v4_0731_compare as first_attempt
from scripts import u18_fresh40_v4_0731_json_mode as json_mode
from scripts import u18_fresh40_v4_0731_adapted as strict_slots
from scripts import u18_fresh45_sol_compare as sol


ROOT = sol.ROOT
PRIVATE = ROOT / ".context/u18/fresh40-v4-0731-five-post-r113-v1"
CONTRACT = PRIVATE / "contract.json"
BATCH_SIZE = 5
FEE_FACTOR = Decimal("1.055")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def batches(packets: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    return [packets[index:index + BATCH_SIZE] for index in range(0, len(packets), BATCH_SIZE)]


def rejected_call(path: Path, arm: str, failure: str) -> dict[str, Any]:
    response = json.loads(path.read_text(encoding="utf-8"))
    return {"arm": arm, "artifact": str(path.relative_to(ROOT)), "cost_usd": response["usage"]["cost"], "failure": failure}


def prepare() -> None:
    if CONTRACT.exists():
        raise ValueError("contract already exists")
    packets = json.loads((control.PRIVATE / "packets.json").read_text(encoding="utf-8"))
    if [row["case_id"] for row in packets] != control.EXPECTED_CASES:
        raise ValueError("frozen cohort changed")
    packet_batches = batches(packets)
    requests = {role: [json_mode.request(batch, role) for batch in packet_batches] for role in ("content", "brand")}
    receipt = first_attempt.endpoint_receipt()
    dump(PRIVATE / "packets.json", packets)
    dump(PRIVATE / "requests.json", requests)
    dump(PRIVATE / "endpoint-receipt.json", receipt)
    sources = [Path(__file__), Path(json_mode.__file__), Path(strict_slots.__file__), Path(first_attempt.__file__), Path(sol.__file__), Path(control.__file__), control.PRIVATE / "packets.json", PRIVATE / "packets.json", PRIVATE / "requests.json", PRIVATE / "endpoint-receipt.json"]
    rejected = [
        rejected_call(first_attempt.PRIVATE / "1-content-raw-response.json", "R110 strict enum identity", "Repeated L45-01 for all 20 results."),
        rejected_call(strict_slots.PRIVATE / "1-content-raw-response.json", "R111 strict fixed slots", "All 27 decisions collapsed to the same contradictory value."),
        rejected_call(json_mode.PRIVATE / "1-content-raw-response.json", "R112 JSON mode, 20 posts", "Returned only 11/27 decision slots and 9/20 post slots."),
    ]
    contract = {
        "schema_version": "u18-fresh40-v4-0731-five-post-r113/v1", "frozen_at": now(),
        "purpose": "Measure V4 Flash 0731 after reducing model-specific cognitive load to five posts per call.",
        "model": first_attempt.MODEL, "provider": first_attempt.PROVIDER,
        "endpoint_tag": first_attempt.ENDPOINT_TAG, "quantization": first_attempt.QUANTIZATION,
        "cases": 40, "brand_reviews": sum(len(row["brand_ids"]) for row in packets),
        "batch_sizes": [len(batch) for batch in packet_batches], "roles": ["content", "brand"],
        "logical_calls": 16, "concurrency": 2,
        "request_design": "R112 fixed-slot JSON-object mode, official temperature=1.0/top_p=1.0, seed=42, non-thinking, 6000-token ceiling.",
        "reason_for_batch_size": "The R112 20-post content call returned valid, noncollapsed classifications but omitted 16/27 brand slots and 11/20 post slots.",
        "rejected_calls_before_this_arm": rejected,
        "caps": {"retries": 0, "repairs": 0, "fallbacks": 0},
        "blindness": "Owner answers and comments are absent from packets and requests; report opens them only after result.json exists.",
        "limitations": "This changes batch size relative to the 20-post controls because 0731 did not satisfy the 20-post completeness contract.",
        "source_sha256": {str(path if not path.is_relative_to(ROOT) else path.relative_to(ROOT)): sol.digest(path) for path in sources},
    }
    dump(CONTRACT, contract)
    print(json.dumps({"contract": str(CONTRACT), "batch_sizes": contract["batch_sizes"], "logical_calls": 16, "prior_failed_cost_usd": sum(row["cost_usd"] for row in rejected)}))


def verify() -> dict[str, Any]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    for relative, expected in contract["source_sha256"].items():
        path = Path(relative)
        if not path.is_absolute():
            path = ROOT / path
        if sol.digest(path) != expected:
            raise ValueError("frozen source changed: " + relative)
    first_attempt.endpoint_receipt()
    return contract


def run_one(name: str, body: dict[str, Any], batch: list[dict[str, Any]], role: str, key: str) -> dict[str, Any]:
    decoded, measurement = sol.shared.transport(body, key, PRIVATE, name)
    measurement.update({"role": role, "case_count": len(batch)})
    if decoded is None:
        return {"name": name, "measurement": measurement, "error": "transport failed"}
    try:
        rows, issues = json_mode.parse(decoded, batch, role)
    except Exception as exc:
        return {"name": name, "measurement": measurement, "error": type(exc).__name__ + ": " + str(exc)}
    dump(PRIVATE / f"{name}-parsed.json", rows)
    measurement["semantic_issues"] = issues
    return {"name": name, "measurement": measurement, "rows": rows, "issues": issues}


def run() -> None:
    contract = verify()
    if (PRIVATE / "result.json").exists():
        raise ValueError("result already exists")
    packets = json.loads((PRIVATE / "packets.json").read_text(encoding="utf-8"))
    packet_batches = batches(packets)
    requests = json.loads((PRIVATE / "requests.json").read_text(encoding="utf-8"))
    result = {"schema_version": contract["schema_version"], "model": first_attempt.MODEL, "provider": first_attempt.PROVIDER, "started_at": now(), "measurements": [], "roles": {"content": [], "brand": []}, "semantic_issues": [], "failures": []}
    key = sol.shared.secret()
    for index, batch in enumerate(packet_batches):
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                role: executor.submit(run_one, f"{index + 1}-{role}", requests[role][index], batch, role, key)
                for role in ("content", "brand")
            }
            outcomes = {role: futures[role].result() for role in ("content", "brand")}
        for role, outcome in outcomes.items():
            measurement = outcome["measurement"]
            measurement["batch"] = index + 1
            result["measurements"].append(measurement)
            if "error" in outcome:
                result["failures"].append({"call": outcome["name"], "error": outcome["error"]})
            else:
                result["roles"][role].extend(outcome["rows"])
                result["semantic_issues"].extend({"call": outcome["name"], **issue} for issue in outcome["issues"])
            print(json.dumps({"call": outcome["name"], "status": "failed" if "error" in outcome else "valid", "seconds": measurement["latency_ms"] / 1000, "usage": measurement.get("usage"), "semantic_issues": len(outcome.get("issues", [])), "error": outcome.get("error")}), flush=True)
        dump(PRIVATE / "partial-result.json", result)
        if result["failures"]:
            raise RuntimeError("five-post batch failed; raw evidence preserved")
    result["completed_at"] = now()
    result["actual_billed_usd"] = str(sum(Decimal(str((row.get("usage") or {}).get("cost", 0))) for row in result["measurements"]))
    result["actual_billed_with_fee_usd"] = str(Decimal(result["actual_billed_usd"]) * FEE_FACTOR)
    rejected = sum(Decimal(str(row["cost_usd"])) for row in contract["rejected_calls_before_this_arm"])
    result["total_experiment_cost_with_rejected_calls_and_fee_usd"] = str((Decimal(result["actual_billed_usd"]) + rejected) * FEE_FACTOR)
    dump(PRIVATE / "result.json", result)
    print(json.dumps({"result": str(PRIVATE / "result.json"), "cost_usd": result["actual_billed_usd"], "cost_with_fee_usd": result["actual_billed_with_fee_usd"], "semantic_issues": len(result["semantic_issues"]), "calls": len(result["measurements"])}))


def timing(result: dict[str, Any]) -> dict[str, Any]:
    per_batch: dict[int, list[int]] = {}
    for row in result["measurements"]:
        per_batch.setdefault(row["batch"], []).append(row["latency_ms"])
    return {"measured_sum_call_seconds": round(sum(row["latency_ms"] for row in result["measurements"]) / 1000, 3), "measured_two_role_wall_seconds": round(sum(max(values) for values in per_batch.values()) / 1000, 3)}


def report() -> None:
    if not (PRIVATE / "result.json").exists():
        raise ValueError("result must exist")
    if sol.digest(sol.OWNER) != sol.OWNER_SHA256:
        raise ValueError("owner answer SHA changed")
    contract = verify()
    owner = json.loads(sol.OWNER.read_text(encoding="utf-8"))
    results = {"v4_0731": json.loads((PRIVATE / "result.json").read_text(encoding="utf-8")), "v4_1": json.loads((control.DEEPSEEK_DIR / "result.json").read_text(encoding="utf-8")), "sol": json.loads((control.SOL_DIR / "result.json").read_text(encoding="utf-8"))}
    names = {"v4_0731": "V4 Flash 0731 (5-post)", "v4_1": "V4.1 Flash (20-post)", "sol": "GPT-5.6 Sol (20-post)"}
    models = {}
    for key, value in results.items():
        models[key] = {"name": names[key], "score": control.score(value, owner, control.EXPECTED_CASES), "timing": timing(value) if key == "v4_0731" else control.timing(value), "semantic_issues": value.get("semantic_issues", []), "multi_label": {field: first_attempt.label_metrics(value, owner, field) for field in ("post_types", "product_labels", "audience_topics")}}
    models["v4_0731"].update(cost_with_fee_usd=results["v4_0731"]["actual_billed_with_fee_usd"], all_experiment_cost_usd=results["v4_0731"]["total_experiment_cost_with_rejected_calls_and_fee_usd"])
    models["v4_1"].update(peak_cost_usd=results["v4_1"]["peak_cost_usd"], offpeak_cost_usd=results["v4_1"]["offpeak_cost_usd"])
    models["sol"].update(cost_with_fee_usd=results["sol"]["actual_billed_with_fee_usd"])
    artifact = {"schema_version": "u18-fresh40-v4-0731-five-post-comparison/v1", "created_at": now(), "contract_sha256": sol.digest(CONTRACT), "owner_sha256": sol.OWNER_SHA256, "rejected_calls": contract["rejected_calls_before_this_arm"], "models": models}
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    json_path = ROOT / "docs/analysis" / f"{stamp}-u18-v4-0731-five-post-comparison.json"
    md_path = ROOT / "docs/analysis" / f"{stamp}-u18-v4-0731-five-post-comparison.md"
    dump(json_path, artifact)
    lines = ["# U18 V4 Flash 0731 five-post comparison", "", "V4 Flash 0731 required five-post batches to satisfy completeness. Its two classifier roles ran concurrently within each batch. V4.1 and Sol retain their completed 20-post control runs.", "", "## Results", "", "| Model | Exact owner agreement | Matches / reviewed | Cost for 40 | Processing time | Semantic issues |", "|---|---:|---:|---:|---:|---:|"]
    for key in ("v4_0731", "v4_1", "sol"):
        data=models[key]; totals=data["score"]["totals"]
        if key == "v4_0731": cost=f"${float(data['cost_with_fee_usd']):.6f} with fee"; duration=f"{data['timing']['measured_two_role_wall_seconds']:.1f}s two-role wall"
        elif key == "v4_1": cost=f"${float(data['offpeak_cost_usd']):.6f} off-peak / ${float(data['peak_cost_usd']):.6f} peak"; duration=f"{data['timing']['estimated_parallel_role_seconds']:.1f}s estimated role-parallel"
        else: cost=f"${float(data['cost_with_fee_usd']):.6f} with fee"; duration=f"{data['timing']['estimated_parallel_role_seconds']:.1f}s estimated role-parallel"
        lines.append(f"| {data['name']} | {totals['agreement_pct']:.1f}% | {totals['matches']} / {totals['reviewed']} | {cost} | {duration} | {len(data['semantic_issues'])} |")
    lines.extend(["", "## Agreement by axis", "", "| Axis | V4 Flash 0731 | V4.1 Flash | GPT-5.6 Sol |", "|---|---:|---:|---:|"])
    for field in [*sol.BRAND_FIELDS, "untracked_brand_promotions"]:
        values=[models[key]["score"]["by_field"][field] for key in ("v4_0731", "v4_1", "sol")]
        lines.append(f"| `{field}` | {values[0]['agreement_pct']:.1f}% ({values[0]['matches']}/{values[0]['reviewed']}) | {values[1]['agreement_pct']:.1f}% ({values[1]['matches']}/{values[1]['reviewed']}) | {values[2]['agreement_pct']:.1f}% ({values[2]['matches']}/{values[2]['reviewed']}) |")
    lines.extend(["", "## Multi-label recovery", "", "| Axis | Model | Recall | Precision | Missing | Extra |", "|---|---|---:|---:|---:|---:|"])
    for field in ("post_types", "product_labels", "audience_topics"):
        for key in ("v4_0731", "v4_1", "sol"):
            value=models[key]["multi_label"][field]
            lines.append(f"| `{field}` | {models[key]['name']} | {100*value['recall']:.1f}% | {100*value['precision']:.1f}% | {value['missing_labels']} | {value['extra_labels']} |")
    rejected=sum(float(row["cost_usd"]) for row in contract["rejected_calls_before_this_arm"])
    lines.extend(["", "## Execution evidence", "", f"- Three rejected model-adaptation calls cost ${rejected:.6f} before the OpenRouter fee.", f"- Total 0731 experiment spend including those diagnostics: ${float(models['v4_0731']['all_experiment_cost_usd']):.6f} with the assumed fee.", "- No retries, repairs, fallbacks, media fetching, or database writes were used.", "", "## Limits", "", "- The 0731 model uses five-post batches while the controls use 20, so this measures each model under its viable execution shape rather than isolating model weights alone.", "- Owner blanks are excluded; selected checkbox sets may themselves be incomplete.", "- This consumed challenge set is not an estimate of production accuracy.", ""])
    md_path.write_text("\n".join(lines), encoding="utf-8")
    dump(PRIVATE / "report-artifacts.json", {"markdown": str(md_path), "json": str(json_path)})
    print(json.dumps({"markdown": str(md_path), "json": str(json_path), "models": models}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "run", "report"))
    args = parser.parse_args()
    {"prepare": prepare, "run": run, "report": report}[args.command]()


if __name__ == "__main__":
    main()
