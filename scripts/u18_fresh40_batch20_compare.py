"""Compare Sol and DeepSeek on two production-sized batches of 20 U18 cases.

The model requests contain only the already-frozen evidence packets. Owner
answers are opened only by ``report``, after both model results are durable.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from scripts import u18_fresh45_deepseek_compare as deepseek
from scripts import u18_fresh45_sol_compare as sol
from scripts import u18_fresh45_deepseek_resume as deepseek_relaxed
from x_monitor.attribution import AnthropicClaudeClient
from x_monitor.provider_telemetry import normalize_usage


ROOT = sol.ROOT
PRIVATE = ROOT / ".context/u18/fresh40-batch20-r109-v1"
SOL_DIR = PRIVATE / "sol"
DEEPSEEK_DIR = PRIVATE / "deepseek"
CONTRACT = PRIVATE / "contract.json"
BATCH_SIZE = 20
CASE_COUNT = 40
EXPECTED_CASES = [f"L45-{number:02d}" for number in range(1, CASE_COUNT + 1)]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def batches(packets: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    return [packets[index:index + BATCH_SIZE] for index in range(0, len(packets), BATCH_SIZE)]


def verify_contract() -> dict[str, Any]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    for relative, expected in contract["source_sha256"].items():
        path = Path(relative)
        if not path.is_absolute():
            path = ROOT / path
        if sol.digest(path) != expected:
            raise ValueError("frozen source changed: " + relative)
    return contract


def prepare() -> None:
    if CONTRACT.exists():
        raise ValueError("contract already frozen")
    packets = sol.packets()[:CASE_COUNT]
    if [row["case_id"] for row in packets] != EXPECTED_CASES:
        raise ValueError("case order changed")
    packet_batches = batches(packets)
    sol_requests = {
        role: [sol.request(batch, role) for batch in packet_batches]
        for role in ("content", "brand")
    }
    deepseek_requests = {
        role: [deepseek.logical_request(batch, role) for batch in packet_batches]
        for role in ("content", "brand")
    }
    dump(PRIVATE / "packets.json", packets)
    dump(SOL_DIR / "requests.json", sol_requests)
    dump(DEEPSEEK_DIR / "requests.json", deepseek_requests)
    sources = [
        Path(__file__), Path(sol.__file__), Path(deepseek.__file__),
        sol.FROZEN_INPUTS, *sol.SIGNAL_EXPORTS, sol.TAXONOMY,
        ROOT / "config.yaml", PRIVATE / "packets.json",
        SOL_DIR / "requests.json", DEEPSEEK_DIR / "requests.json",
    ]
    contract = {
        "schema_version": "u18-fresh40-batch20-r109/v1",
        "frozen_at": now(),
        "purpose": "Measure Sol and DeepSeek V4.1 Flash on two production-sized 20-post batches.",
        "case_ids": EXPECTED_CASES,
        "excluded_case_ids": [f"L45-{number:02d}" for number in range(41, 46)],
        "cases": CASE_COUNT,
        "brand_reviews": sum(len(row["brand_ids"]) for row in packets),
        "batch_sizes": [len(batch) for batch in packet_batches],
        "roles": ["content", "brand"],
        "calls_per_model": 4,
        "role_execution": "Measured sequentially; the two disjoint roles may run concurrently in production.",
        "blindness": "No owner answers or comments appear in packets or requests. Report opens owner answers only after both result files exist.",
        "prompts": "Identical U18A role prompts and schemas used in R107/R108; only cohort size and batch boundaries differ.",
        "models": {
            "sol": {"request_model": sol.MODEL, "provider": "OpenAI through OpenRouter", "reasoning_effort": "low", "max_tokens": sol.MAX_TOKENS},
            "deepseek": {"request_model": deepseek.MODEL, "provider": "direct DeepSeek", "thinking": "disabled", "max_tokens": deepseek.MAX_TOKENS},
        },
        "caps": {"retries": 0, "repairs": 0, "fallbacks": 0},
        "scoring": "Exact field/set agreement on owner-reviewed controls only; owner blanks are excluded.",
        "limitations": "Purposefully enriched challenge set, not a prevalence-weighted sample or production-accuracy estimate. No media or browsing.",
        "source_sha256": {
            str(path if not path.is_relative_to(ROOT) else path.relative_to(ROOT)): sol.digest(path)
            for path in sources
        },
    }
    dump(CONTRACT, contract)
    print(json.dumps({"contract": str(CONTRACT), "batch_sizes": [20, 20], "calls_per_model": 4}))


def run_sol() -> None:
    contract = verify_contract()
    if (SOL_DIR / "result.json").exists():
        raise ValueError("Sol result already exists")
    packets = json.loads((PRIVATE / "packets.json").read_text(encoding="utf-8"))
    packet_batches = batches(packets)
    requests = json.loads((SOL_DIR / "requests.json").read_text(encoding="utf-8"))
    key = sol.shared.secret()
    output = {"schema_version": contract["schema_version"], "model": sol.MODEL, "provider": "OpenAI through OpenRouter", "started_at": now(), "measurements": [], "roles": {"content": [], "brand": []}}
    for index, batch in enumerate(packet_batches):
        for role in ("content", "brand"):
            name = f"{index + 1}-{role}"
            decoded, record = sol.shared.transport(requests[role][index], key, SOL_DIR, name)
            record.update({"batch": index + 1, "role": role, "case_count": len(batch)})
            if decoded is None:
                dump(SOL_DIR / "partial-result.json", output)
                raise RuntimeError(f"Sol transport failed: {name}")
            parsed = sol.parse(decoded, batch, role)
            dump(SOL_DIR / f"{name}-parsed.json", parsed)
            output["roles"][role].extend(parsed)
            output["measurements"].append(record)
            dump(SOL_DIR / "partial-result.json", output)
            print(json.dumps({"model": "sol", "call": name, "status": "valid", "seconds": record["latency_ms"] / 1000, "usage": record.get("usage")}), flush=True)
    output["completed_at"] = now()
    output["actual_billed_usd"] = str(sum(Decimal(str((row.get("usage") or {}).get("cost", 0))) for row in output["measurements"]))
    output["actual_billed_with_fee_usd"] = str(Decimal(output["actual_billed_usd"]) * sol.FEE_FACTOR)
    dump(SOL_DIR / "result.json", output)
    print(json.dumps({"result": str(SOL_DIR / "result.json"), "cost_usd": output["actual_billed_usd"], "calls": 4}))


def semantic_issues(rows: list[dict[str, Any]], role: str) -> list[dict[str, Any]]:
    if role != "brand":
        return []
    issues = []
    for row in rows:
        for brand in row["by_brand"]:
            if "nationalistic_stance" not in brand["geopolitical_modes"] and (
                brand["china_national_stance"] != "none" or brand["us_national_stance"] != "none"
            ):
                issues.append({"case_id": row["case_id"], "brand_id": brand["brand_id"], "issue": "national stance without nationalistic_stance mode"})
    return issues


def run_deepseek() -> None:
    contract = verify_contract()
    if (DEEPSEEK_DIR / "result.json").exists():
        raise ValueError("DeepSeek result already exists")
    packets = json.loads((PRIVATE / "packets.json").read_text(encoding="utf-8"))
    packet_batches = batches(packets)
    requests = json.loads((DEEPSEEK_DIR / "requests.json").read_text(encoding="utf-8"))
    client = AnthropicClaudeClient(api_key=deepseek.secret(), base_url=deepseek.BASE_URL)
    output = {"schema_version": contract["schema_version"], "model": "DeepSeek V4.1 Flash", "provider": "direct DeepSeek", "started_at": now(), "measurements": [], "roles": {"content": [], "brand": []}, "semantic_issues": []}
    for index, batch in enumerate(packet_batches):
        for role in ("content", "brand"):
            name = f"{index + 1}-{role}"
            body = requests[role][index]
            dump(DEEPSEEK_DIR / f"{name}-request.json", body)
            started = time.monotonic()
            response = client.messages_create(timeout=120, **body)
            usage_raw = getattr(response, "provider_usage", None)
            elapsed = round((time.monotonic() - started) * 1000)
            # Persist provider output before any local semantic validation.
            dump(DEEPSEEK_DIR / f"{name}-raw-response.json", {"response": dict(response), "usage": usage_raw})
            if not isinstance(usage_raw, dict) or usage_raw.get("provider") != "deepseek" or usage_raw.get("model") not in deepseek.RESPONSE_MODELS or not usage_raw.get("provider_request_id"):
                raise ValueError("DeepSeek provider/model attestation failed")
            parsed = deepseek_relaxed.validate_response(dict(response), batch, role)
            issues = semantic_issues(parsed, role)
            output["semantic_issues"].extend(issues)
            output["roles"][role].extend(parsed)
            usage = normalize_usage(usage_raw)
            measurement = {"call": name, "role": role, "batch": index + 1, "case_count": len(batch), "latency_ms": elapsed, "usage": usage, "semantic_issues": issues}
            output["measurements"].append(measurement)
            dump(DEEPSEEK_DIR / "partial-result.json", output)
            print(json.dumps({"model": "deepseek", "call": name, "status": "valid", "seconds": elapsed / 1000, "usage": usage, "semantic_issues": issues}), flush=True)
    output["completed_at"] = now()
    usage = {key: sum(int(row["usage"].get(key) or 0) for row in output["measurements"]) for key in ("input_tokens", "cache_read_input_tokens", "output_tokens")}
    output["usage"] = usage
    output["peak_cost_usd"] = str((Decimal(usage["input_tokens"]) * deepseek.PEAK_INPUT + Decimal(usage["cache_read_input_tokens"]) * deepseek.PEAK_CACHE + Decimal(usage["output_tokens"]) * deepseek.PEAK_OUTPUT) / Decimal(1_000_000))
    output["offpeak_cost_usd"] = str((Decimal(usage["input_tokens"]) * deepseek.OFFPEAK_INPUT + Decimal(usage["cache_read_input_tokens"]) * deepseek.OFFPEAK_CACHE + Decimal(usage["output_tokens"]) * deepseek.OFFPEAK_OUTPUT) / Decimal(1_000_000))
    dump(DEEPSEEK_DIR / "result.json", output)
    print(json.dumps({"result": str(DEEPSEEK_DIR / "result.json"), "peak_cost_usd": output["peak_cost_usd"], "offpeak_cost_usd": output["offpeak_cost_usd"], "calls": 4, "semantic_issues": len(output["semantic_issues"])}))


def same(left: Any, right: Any) -> bool:
    return set(left) == set(right) if isinstance(left, list) else left == right


def score(result: dict[str, Any], owner: dict[str, Any], case_ids: list[str]) -> dict[str, Any]:
    model = sol.merge_sol(result)
    fields = [*sol.BRAND_FIELDS, "untracked_brand_promotions"]
    by_field = {field: {"reviewed": 0, "matches": 0, "differences": 0} for field in fields}
    totals = {"reviewed": 0, "matches": 0, "differences": 0, "unreviewed": 0}
    for case_id in case_ids:
        owner_case = owner["cases"][case_id]
        for brand_id in owner_case["review_targets"]:
            for field in sol.BRAND_FIELDS:
                expected = owner_case["per_brand"][brand_id].get(field)
                actual = model[case_id]["per_brand"][brand_id][field]
                if not sol.reviewed(expected):
                    totals["unreviewed"] += 1
                    continue
                matched = same(expected, actual)
                totals["reviewed"] += 1
                totals["matches" if matched else "differences"] += 1
                by_field[field]["reviewed"] += 1
                by_field[field]["matches" if matched else "differences"] += 1
        expected = owner_case["post_level"].get("untracked_brand_promotions")
        actual = model[case_id]["post_level"]["untracked_brand_promotions"]
        if not sol.reviewed(expected):
            totals["unreviewed"] += 1
        else:
            matched = same(expected, actual)
            totals["reviewed"] += 1
            totals["matches" if matched else "differences"] += 1
            by_field["untracked_brand_promotions"]["reviewed"] += 1
            by_field["untracked_brand_promotions"]["matches" if matched else "differences"] += 1
    totals["agreement_pct"] = round(100 * totals["matches"] / totals["reviewed"], 1)
    for values in by_field.values():
        values["agreement_pct"] = round(100 * values["matches"] / values["reviewed"], 1) if values["reviewed"] else None
    return {"totals": totals, "by_field": by_field}


def stability(current: dict[str, Any], prior: dict[str, Any], case_ids: list[str]) -> dict[str, Any]:
    current_model, prior_model = sol.merge_sol(current), sol.merge_sol(prior)
    by_field = {field: {"compared": 0, "same": 0, "changed": 0} for field in [*sol.BRAND_FIELDS, "untracked_brand_promotions"]}
    for case_id in case_ids:
        for brand_id, values in current_model[case_id]["per_brand"].items():
            for field in sol.BRAND_FIELDS:
                matched = same(values[field], prior_model[case_id]["per_brand"][brand_id][field])
                by_field[field]["compared"] += 1
                by_field[field]["same" if matched else "changed"] += 1
        matched = same(current_model[case_id]["post_level"]["untracked_brand_promotions"], prior_model[case_id]["post_level"]["untracked_brand_promotions"])
        by_field["untracked_brand_promotions"]["compared"] += 1
        by_field["untracked_brand_promotions"]["same" if matched else "changed"] += 1
    total_compared = sum(row["compared"] for row in by_field.values())
    total_same = sum(row["same"] for row in by_field.values())
    for values in by_field.values():
        values["stability_pct"] = round(100 * values["same"] / values["compared"], 1)
    return {"totals": {"compared": total_compared, "same": total_same, "changed": total_compared - total_same, "stability_pct": round(100 * total_same / total_compared, 1)}, "by_field": by_field}


def timing(result: dict[str, Any]) -> dict[str, Any]:
    sequential_ms = sum(row["latency_ms"] for row in result["measurements"] if row.get("latency_ms") is not None)
    batches_by_id: dict[int, list[int]] = {}
    for row in result["measurements"]:
        if row.get("latency_ms") is not None:
            batches_by_id.setdefault(row["batch"], []).append(row["latency_ms"])
    parallel_roles_ms = sum(max(values) for values in batches_by_id.values())
    return {"measured_sequential_seconds": round(sequential_ms / 1000, 3), "estimated_parallel_role_seconds": round(parallel_roles_ms / 1000, 3)}


def report() -> None:
    sol_path, deepseek_path = SOL_DIR / "result.json", DEEPSEEK_DIR / "result.json"
    if not sol_path.exists() or not deepseek_path.exists():
        raise ValueError("both model results must exist before report")
    if sol.digest(sol.OWNER) != sol.OWNER_SHA256:
        raise ValueError("owner answer SHA changed")
    contract = verify_contract()
    owner = json.loads(sol.OWNER.read_text(encoding="utf-8"))
    current_sol = json.loads(sol_path.read_text(encoding="utf-8"))
    current_deepseek = json.loads(deepseek_path.read_text(encoding="utf-8"))
    prior_sol = json.loads((sol.PRIVATE / "result.json").read_text(encoding="utf-8"))
    prior_deepseek = json.loads((deepseek.PRIVATE / "result.json").read_text(encoding="utf-8"))
    case_ids = contract["case_ids"]
    artifact = {
        "schema_version": "u18-fresh40-batch20-model-comparison/v1",
        "created_at": now(),
        "contract_sha256": sol.digest(CONTRACT),
        "owner_source_sha256": sol.OWNER_SHA256,
        "cohort": {"cases": 40, "brand_reviews": contract["brand_reviews"], "batch_sizes": [20, 20], "excluded": contract["excluded_case_ids"]},
        "models": {
            "sol": {
                "score": score(current_sol, owner, case_ids),
                "stability_vs_15_post_batches": stability(current_sol, prior_sol, case_ids),
                "timing": timing(current_sol),
                "cost_usd": current_sol["actual_billed_usd"],
                "cost_with_openrouter_fee_usd": current_sol["actual_billed_with_fee_usd"],
            },
            "deepseek": {
                "score": score(current_deepseek, owner, case_ids),
                "stability_vs_15_post_batches": stability(current_deepseek, prior_deepseek, case_ids),
                "timing": timing(current_deepseek),
                "peak_cost_usd": current_deepseek["peak_cost_usd"],
                "offpeak_cost_usd": current_deepseek["offpeak_cost_usd"],
                "semantic_issues": current_deepseek["semantic_issues"],
            },
        },
    }
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    json_path = ROOT / "docs/analysis" / f"{stamp}-u18-fresh-40-batch-20-model-comparison.json"
    md_path = ROOT / "docs/analysis" / f"{stamp}-u18-fresh-40-batch-20-model-comparison.md"
    dump(json_path, artifact)
    lines = [
        "# U18 Fresh 40: production batch-size comparison",
        "",
        f"Generated: {artifact['created_at']}",
        "",
        "This rerun uses cases L45-01 through L45-40 as two batches of 20 posts. Cases L45-41 through L45-45 are excluded. Each model still uses two disjoint roles per batch, so each model made four calls. Owner blanks remain excluded from scoring.",
        "",
        "## Overall results",
        "",
        "| Model | Exact agreement | Matches / reviewed | Cost | Sequential time | Role-parallel estimate | Stability vs prior 15-post run |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, label in (("sol", "GPT-5.6 Sol"), ("deepseek", "DeepSeek V4.1 Flash")):
        data = artifact["models"][name]
        totals = data["score"]["totals"]
        stability_totals = data["stability_vs_15_post_batches"]["totals"]
        cost = f"${float(data['cost_usd']):.4f}" if name == "sol" else f"${float(data['peak_cost_usd']):.4f} peak / ${float(data['offpeak_cost_usd']):.4f} off-peak"
        lines.append(f"| {label} | {totals['agreement_pct']:.1f}% | {totals['matches']} / {totals['reviewed']} | {cost} | {data['timing']['measured_sequential_seconds']:.1f}s | {data['timing']['estimated_parallel_role_seconds']:.1f}s | {stability_totals['stability_pct']:.1f}% |")
    lines.extend(["", "## Exact agreement by axis", "", "| Axis | Sol | DeepSeek | Reviewed controls |", "|---|---:|---:|---:|"])
    for field in [*sol.BRAND_FIELDS, "untracked_brand_promotions"]:
        s = artifact["models"]["sol"]["score"]["by_field"][field]
        d = artifact["models"]["deepseek"]["score"]["by_field"][field]
        lines.append(f"| `{field}` | {s['agreement_pct']:.1f}% ({s['matches']}/{s['reviewed']}) | {d['agreement_pct']:.1f}% ({d['matches']}/{d['reviewed']}) | {s['reviewed']} |")
    lines.extend(["", "## Batch-size sensitivity", "", "This compares each model’s new 20-post outputs with its own earlier 15-post outputs for the same first 40 cases. A change is stochastic or batch-context sensitivity; it is not automatically an error.", "", "| Axis | Sol stability | DeepSeek stability |", "|---|---:|---:|"])
    for field in [*sol.BRAND_FIELDS, "untracked_brand_promotions"]:
        s = artifact["models"]["sol"]["stability_vs_15_post_batches"]["by_field"][field]
        d = artifact["models"]["deepseek"]["stability_vs_15_post_batches"]["by_field"][field]
        lines.append(f"| `{field}` | {s['stability_pct']:.1f}% ({s['same']}/{s['compared']}) | {d['stability_pct']:.1f}% ({d['same']}/{d['compared']}) |")
    issues = artifact["models"]["deepseek"]["semantic_issues"]
    lines.extend(["", "## Execution notes", "", f"- DeepSeek semantic invariant issues: {len(issues)}.", "- Both role calls were measured sequentially for clean per-call timing; the role-parallel estimate sums the slower call in each batch.", "- Exact agreement requires an entire multi-label set to match; one omitted or extra label makes that field different.", "- This challenge set and incomplete owner review cannot estimate live production accuracy.", ""])
    md_path.write_text("\n".join(lines), encoding="utf-8")
    dump(PRIVATE / "report-artifacts.json", {"markdown": str(md_path), "json": str(json_path)})
    print(json.dumps({"markdown": str(md_path), "json": str(json_path), "sol": artifact["models"]["sol"], "deepseek": artifact["models"]["deepseek"]}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "run-sol", "run-deepseek", "report"))
    args = parser.parse_args()
    {"prepare": prepare, "run-sol": run_sol, "run-deepseek": run_deepseek, "report": report}[args.command]()


if __name__ == "__main__":
    main()
