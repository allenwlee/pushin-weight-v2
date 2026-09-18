"""Evaluate OpenRouter DeepSeek V4 Flash 0731 on the frozen U18 fresh 40."""
from __future__ import annotations

import argparse
import json
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from scripts import u18_fresh40_batch20_compare as control
from scripts import u18_fresh45_deepseek_resume as relaxed
from scripts import u18_fresh45_sol_compare as sol
from x_monitor.openrouter import OpenRouterChatCompletionsClient


ROOT = sol.ROOT
PRIVATE = ROOT / ".context/u18/fresh40-v4-0731-r110-v1"
CONTRACT = PRIVATE / "contract.json"
MODEL = "deepseek/deepseek-v4-flash-0731"
PROVIDER = "OpenInference"
ENDPOINT_TAG = "open-inference/fp8"
QUANTIZATION = "fp8"
INPUT_PRICE = Decimal("0.04")
CACHE_PRICE = Decimal("0.01")
OUTPUT_PRICE = Decimal("0.10")
FEE_FACTOR = Decimal("1.055")
MAX_TOKENS = 6000
HARD_CAP = Decimal("0.05")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def endpoint_receipt() -> dict[str, Any]:
    url = f"https://openrouter.ai/api/v1/models/{MODEL}/endpoints"
    with urllib.request.urlopen(url, timeout=20) as response:
        data = json.load(response)["data"]
    matches = [row for row in data["endpoints"] if row.get("tag") == ENDPOINT_TAG]
    if len(matches) != 1:
        raise ValueError("pinned endpoint missing or ambiguous")
    endpoint = matches[0]
    pricing = endpoint["pricing"]
    observed = {
        "input": Decimal(pricing["prompt"]) * Decimal(1_000_000),
        "cache_read": Decimal(pricing["input_cache_read"]) * Decimal(1_000_000),
        "output": Decimal(pricing["completion"]) * Decimal(1_000_000),
    }
    if endpoint.get("provider_name") != PROVIDER or endpoint.get("quantization") != QUANTIZATION or endpoint.get("status") != 0:
        raise ValueError("pinned endpoint identity or health changed")
    if observed != {"input": INPUT_PRICE, "cache_read": CACHE_PRICE, "output": OUTPUT_PRICE}:
        raise ValueError("pinned endpoint price changed")
    required = {"max_tokens", "response_format", "structured_outputs", "reasoning"}
    if not required.issubset(endpoint.get("supported_parameters") or []):
        raise ValueError("pinned endpoint lacks required parameters")
    return {"observed_at": now(), "source": url, "model_id": data["id"], "endpoint": endpoint}


def request(batch: list[dict[str, Any]], role: str) -> dict[str, Any]:
    client = OpenRouterChatCompletionsClient(
        api_key="",
        model=MODEL,
        provider=PROVIDER,
        data_collection="allow",
        max_input_price=float(INPUT_PRICE),
        max_output_price=float(OUTPUT_PRICE),
        response_provider=PROVIDER,
        response_model=MODEL,
        endpoint_tag=ENDPOINT_TAG,
        reasoning_enabled=False,
        quantizations=[QUANTIZATION],
    )
    payload = [
        {**row, "input_fingerprint": sol.fingerprint(row), "tracked_brands": sol.tracked_brands()}
        for row in batch
    ]
    body = client.build_request(
        max_tokens=MAX_TOKENS,
        system=sol.CONTENT_PROMPT if role == "content" else sol.BRAND_PROMPT,
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}],
    )
    body["response_format"] = {
        "type": "json_schema",
        "json_schema": {
            "name": role + "_classification",
            "strict": True,
            "schema": sol.response_schema(batch, role),
        },
    }
    body["reasoning"] = {"enabled": False, "exclude": True}
    return body


def prepare() -> None:
    if CONTRACT.exists():
        raise ValueError("contract already exists")
    packets = json.loads((control.PRIVATE / "packets.json").read_text(encoding="utf-8"))
    if [row["case_id"] for row in packets] != control.EXPECTED_CASES:
        raise ValueError("frozen 40-case cohort changed")
    batches = control.batches(packets)
    requests = {role: [request(batch, role) for batch in batches] for role in ("content", "brand")}
    reservation = Decimal("0")
    for role_requests in requests.values():
        for body in role_requests:
            input_bound = Decimal(len(json.dumps(body, ensure_ascii=False).encode()) + 2048)
            reservation += (input_bound * INPUT_PRICE + Decimal(MAX_TOKENS) * OUTPUT_PRICE) / Decimal(1_000_000) * FEE_FACTOR
    if reservation >= HARD_CAP:
        raise ValueError("reservation exceeds hard cap")
    receipt = endpoint_receipt()
    dump(PRIVATE / "packets.json", packets)
    dump(PRIVATE / "requests.json", requests)
    dump(PRIVATE / "endpoint-receipt.json", receipt)
    sources = [
        Path(__file__), Path(sol.__file__), Path(control.__file__),
        control.PRIVATE / "packets.json", PRIVATE / "packets.json",
        PRIVATE / "requests.json", PRIVATE / "endpoint-receipt.json",
    ]
    contract = {
        "schema_version": "u18-fresh40-v4-0731-r110/v1",
        "frozen_at": now(),
        "purpose": "Compare DeepSeek V4 Flash 0731 with the completed Sol and V4.1 Flash 20/20 runs.",
        "model": MODEL,
        "provider": PROVIDER,
        "endpoint_tag": ENDPOINT_TAG,
        "quantization": QUANTIZATION,
        "reasoning": "disabled",
        "cases": 40,
        "brand_reviews": sum(len(row["brand_ids"]) for row in packets),
        "batch_sizes": [20, 20],
        "roles": ["content", "brand"],
        "calls": 4,
        "max_tokens_per_call": MAX_TOKENS,
        "pricing_per_million": {"input": str(INPUT_PRICE), "cache_read": str(CACHE_PRICE), "output": str(OUTPUT_PRICE)},
        "caps": {"retries": 0, "repairs": 0, "fallbacks": 0, "hard_cap_usd_including_fee": str(HARD_CAP), "reserved_usd_including_fee": str(reservation)},
        "blindness": "Owner answers and comments are absent from all inference packets and requests; report opens them only after result.json exists.",
        "controlled_changes": "Relative to the V4.1 run, only model weights, provider transport, and strict schema enforcement differ. Evidence, prompts, roles, batches, output ceiling, and disabled thinking are unchanged.",
        "limitations": "Purposefully enriched challenge set with incomplete owner controls; not a production accuracy estimate. No media or web browsing during inference.",
        "source_sha256": {str(path if not path.is_relative_to(ROOT) else path.relative_to(ROOT)): sol.digest(path) for path in sources},
    }
    dump(CONTRACT, contract)
    print(json.dumps({"contract": str(CONTRACT), "calls": 4, "reserved_usd_including_fee": str(reservation)}))


def verify_contract() -> dict[str, Any]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    for relative, expected in contract["source_sha256"].items():
        path = Path(relative)
        if not path.is_absolute():
            path = ROOT / path
        if sol.digest(path) != expected:
            raise ValueError("frozen source changed: " + relative)
    receipt = endpoint_receipt()
    dump(PRIVATE / "run-endpoint-receipt.json", receipt)
    return contract


def validate(decoded: dict[str, Any], batch: list[dict[str, Any]], role: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if decoded.get("model") != MODEL:
        raise ValueError("response model mismatch")
    if decoded.get("provider") != PROVIDER:
        raise ValueError("response provider mismatch")
    choice = decoded.get("choices", [{}])[0]
    if choice.get("finish_reason") != "stop":
        raise ValueError("response did not finish normally")
    parsed = json.loads(choice.get("message", {}).get("content", ""))
    rows = relaxed.validate_response(parsed, batch, role)
    return rows, control.semantic_issues(rows, role)


def run() -> None:
    contract = verify_contract()
    if (PRIVATE / "result.json").exists():
        raise ValueError("result already exists")
    packets = json.loads((PRIVATE / "packets.json").read_text(encoding="utf-8"))
    batches = control.batches(packets)
    requests = json.loads((PRIVATE / "requests.json").read_text(encoding="utf-8"))
    key = sol.shared.secret()
    result = {"schema_version": contract["schema_version"], "model": MODEL, "provider": PROVIDER, "started_at": now(), "measurements": [], "roles": {"content": [], "brand": []}, "semantic_issues": []}
    for index, batch in enumerate(batches):
        for role in ("content", "brand"):
            name = f"{index + 1}-{role}"
            decoded, measurement = sol.shared.transport(requests[role][index], key, PRIVATE, name)
            measurement.update({"batch": index + 1, "role": role, "case_count": len(batch)})
            result["measurements"].append(measurement)
            dump(PRIVATE / "partial-result.json", result)
            if decoded is None:
                raise RuntimeError(f"transport failed: {name}")
            rows, issues = validate(decoded, batch, role)
            dump(PRIVATE / f"{name}-parsed.json", rows)
            result["roles"][role].extend(rows)
            result["semantic_issues"].extend(issues)
            measurement["semantic_issues"] = issues
            dump(PRIVATE / "partial-result.json", result)
            print(json.dumps({"call": name, "status": "valid", "seconds": measurement["latency_ms"] / 1000, "usage": measurement.get("usage"), "semantic_issues": issues}), flush=True)
    result["completed_at"] = now()
    result["actual_billed_usd"] = str(sum(Decimal(str((row.get("usage") or {}).get("cost", 0))) for row in result["measurements"]))
    result["actual_billed_with_fee_usd"] = str(Decimal(result["actual_billed_usd"]) * FEE_FACTOR)
    dump(PRIVATE / "result.json", result)
    print(json.dumps({"result": str(PRIVATE / "result.json"), "cost_usd": result["actual_billed_usd"], "cost_with_fee_usd": result["actual_billed_with_fee_usd"], "semantic_issues": len(result["semantic_issues"])}))


def label_metrics(result: dict[str, Any], owner: dict[str, Any], field: str) -> dict[str, Any]:
    model = sol.merge_sol(result)
    tp = extra = missing = exact = reviewed = 0
    for case_id in control.EXPECTED_CASES:
        owner_case = owner["cases"][case_id]
        if field == "untracked_brand_promotions":
            pairs = [(owner_case["post_level"].get(field), model[case_id]["post_level"][field])]
        else:
            pairs = [(owner_case["per_brand"][brand].get(field), model[case_id]["per_brand"][brand][field]) for brand in owner_case["review_targets"]]
        for expected, actual in pairs:
            if not sol.reviewed(expected):
                continue
            reviewed += 1
            expected_set, actual_set = set(expected), set(actual)
            exact += expected_set == actual_set
            tp += len(expected_set & actual_set)
            extra += len(actual_set - expected_set)
            missing += len(expected_set - actual_set)
    return {
        "reviewed_sets": reviewed, "exact_sets": exact, "correct_labels": tp,
        "extra_labels": extra, "missing_labels": missing,
        "precision": round(tp / (tp + extra), 4) if tp + extra else None,
        "recall": round(tp / (tp + missing), 4) if tp + missing else None,
    }


def report() -> None:
    if not (PRIVATE / "result.json").exists():
        raise ValueError("result must be frozen before scoring")
    if sol.digest(sol.OWNER) != sol.OWNER_SHA256:
        raise ValueError("owner answer SHA changed")
    contract = verify_contract()
    owner = json.loads(sol.OWNER.read_text(encoding="utf-8"))
    results = {
        "v4_0731": json.loads((PRIVATE / "result.json").read_text(encoding="utf-8")),
        "v4_1": json.loads((control.DEEPSEEK_DIR / "result.json").read_text(encoding="utf-8")),
        "sol": json.loads((control.SOL_DIR / "result.json").read_text(encoding="utf-8")),
    }
    labels = {"v4_0731": "DeepSeek V4 Flash 0731", "v4_1": "DeepSeek V4.1 Flash", "sol": "GPT-5.6 Sol"}
    models = {}
    for key, result in results.items():
        models[key] = {
            "label": labels[key],
            "score": control.score(result, owner, control.EXPECTED_CASES),
            "timing": control.timing(result),
            "multi_label": {field: label_metrics(result, owner, field) for field in ("post_types", "product_labels", "audience_topics", "geopolitical_modes", "untracked_brand_promotions")},
            "semantic_issues": result.get("semantic_issues", []),
        }
    models["v4_0731"]["cost_usd"] = results["v4_0731"]["actual_billed_usd"]
    models["v4_0731"]["cost_with_openrouter_fee_usd"] = results["v4_0731"]["actual_billed_with_fee_usd"]
    models["v4_1"]["peak_cost_usd"] = results["v4_1"]["peak_cost_usd"]
    models["v4_1"]["offpeak_cost_usd"] = results["v4_1"]["offpeak_cost_usd"]
    models["sol"]["cost_usd"] = results["sol"]["actual_billed_usd"]
    models["sol"]["cost_with_openrouter_fee_usd"] = results["sol"]["actual_billed_with_fee_usd"]
    artifact = {
        "schema_version": "u18-fresh40-v4-0731-comparison/v1", "created_at": now(),
        "contract_sha256": sol.digest(CONTRACT), "owner_sha256": sol.OWNER_SHA256,
        "cohort": {"cases": 40, "brand_reviews": contract["brand_reviews"], "batch_sizes": [20, 20]},
        "models": models,
    }
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    json_path = ROOT / "docs/analysis" / f"{stamp}-u18-v4-0731-model-comparison.json"
    md_path = ROOT / "docs/analysis" / f"{stamp}-u18-v4-0731-model-comparison.md"
    dump(json_path, artifact)
    lines = [
        "# U18 DeepSeek V4 Flash 0731 comparison", "",
        f"Generated: {artifact['created_at']}", "",
        "All three models use the same first 40 fresh-review cases, two 20-post batches, two disjoint classifier roles, and the same owner-scoring policy. Owner blanks are excluded.", "",
        "## Overall results", "",
        "| Model | Exact owner agreement | Matches / reviewed | Cost for 40 | Sequential time | Role-parallel estimate | Semantic issues |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for key in ("v4_0731", "v4_1", "sol"):
        data = models[key]
        totals = data["score"]["totals"]
        if key == "v4_0731":
            cost = f"${float(data['cost_usd']):.6f} (${float(data['cost_with_openrouter_fee_usd']):.6f} with fee)"
        elif key == "v4_1":
            cost = f"${float(data['offpeak_cost_usd']):.6f} off-peak / ${float(data['peak_cost_usd']):.6f} peak"
        else:
            cost = f"${float(data['cost_with_openrouter_fee_usd']):.6f} with fee"
        lines.append(f"| {data['label']} | {totals['agreement_pct']:.1f}% | {totals['matches']} / {totals['reviewed']} | {cost} | {data['timing']['measured_sequential_seconds']:.1f}s | {data['timing']['estimated_parallel_role_seconds']:.1f}s | {len(data['semantic_issues'])} |")
    lines.extend(["", "## Exact agreement by axis", "", "| Axis | V4 Flash 0731 | V4.1 Flash | GPT-5.6 Sol |", "|---|---:|---:|---:|"])
    for field in [*sol.BRAND_FIELDS, "untracked_brand_promotions"]:
        values = [models[key]["score"]["by_field"][field] for key in ("v4_0731", "v4_1", "sol")]
        lines.append(f"| `{field}` | {values[0]['agreement_pct']:.1f}% ({values[0]['matches']}/{values[0]['reviewed']}) | {values[1]['agreement_pct']:.1f}% ({values[1]['matches']}/{values[1]['reviewed']}) | {values[2]['agreement_pct']:.1f}% ({values[2]['matches']}/{values[2]['reviewed']}) |")
    lines.extend(["", "## Multi-label recovery", "", "| Axis | Model | Recall | Precision | Missing | Extra |", "|---|---|---:|---:|---:|---:|"])
    for field in ("post_types", "product_labels", "audience_topics"):
        for key in ("v4_0731", "v4_1", "sol"):
            value = models[key]["multi_label"][field]
            lines.append(f"| `{field}` | {models[key]['label']} | {100 * value['recall']:.1f}% | {100 * value['precision']:.1f}% | {value['missing_labels']} | {value['extra_labels']} |")
    lines.extend(["", "## Limits", "", "- This is agreement with an incomplete, already-consumed owner review, not unseen production accuracy.", "- Exact-set agreement marks an entire multi-label axis different when only one label differs.", "- The 0731 route uses older model weights and strict OpenRouter JSON Schema; V4.1 uses DeepSeek's direct Anthropic-compatible API with local schema validation.", "- No retries, repairs, fallbacks, media fetching, or database writes were used.", ""])
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
