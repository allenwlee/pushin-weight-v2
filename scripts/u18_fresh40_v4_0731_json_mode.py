"""V4 Flash 0731 fixed-slot evaluation using model-friendly JSON mode."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from scripts import u18_fresh40_batch20_compare as control
from scripts import u18_fresh40_v4_0731_adapted as adapted
from scripts import u18_fresh40_v4_0731_compare as first_attempt
from scripts import u18_fresh45_sol_compare as sol
from x_monitor.openrouter import OpenRouterChatCompletionsClient


ROOT = sol.ROOT
PRIVATE = ROOT / ".context/u18/fresh40-v4-0731-json-r112-v1"
CONTRACT = PRIVATE / "contract.json"
MAX_TOKENS = 6000
FEE_FACTOR = Decimal("1.055")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def output_contract(batch: list[dict[str, Any]], role: str) -> str:
    decisions, posts = adapted.slot_map(batch)
    decision_keys = ", ".join(decisions)
    if role == "content":
        fields = '"outcome":"classified|context_missing","post_types":[...],"audience_topics":[...]'
        post_line = f' Root key post_promotions must be an object with exactly these keys: {", ".join(posts)}. Each value is an array of allowed promotion labels.'
        roots = "decisions and post_promotions"
    else:
        fields = '"product_labels":[...],"sentiment":"...","geopolitical_modes":[...],"china_national_stance":"...","us_national_stance":"..."'
        post_line = ""
        roots = "decisions"
    return f"""

JSON-OBJECT CONTRACT FOR THIS BATCH:
- Return one JSON object with exactly these root keys: {roots}.
- decisions must be an object with exactly these keys in this order: {decision_keys}.
- Each decision value must have exactly these fields: {{{fields}}}.
- Use only label spellings defined above. Arrays must contain every supported label, without duplicates.
- Use the fixed slot mapping in the input. Do not emit case IDs, fingerprints, brand IDs, explanations, Markdown, or extra keys.{post_line}
"""


def request(batch: list[dict[str, Any]], role: str) -> dict[str, Any]:
    client = OpenRouterChatCompletionsClient(
        api_key="", model=first_attempt.MODEL, provider=first_attempt.PROVIDER,
        data_collection="allow", max_input_price=float(first_attempt.INPUT_PRICE),
        max_output_price=float(first_attempt.OUTPUT_PRICE),
        response_provider=first_attempt.PROVIDER, response_model=first_attempt.MODEL,
        endpoint_tag=first_attempt.ENDPOINT_TAG, reasoning_enabled=False,
        quantizations=[first_attempt.QUANTIZATION],
    )
    body = client.build_request(
        max_tokens=MAX_TOKENS, temperature=1.0,
        system=(sol.CONTENT_PROMPT if role == "content" else sol.BRAND_PROMPT) + adapted.ADAPTATION + output_contract(batch, role),
        messages=[{"role": "user", "content": json.dumps(adapted.adapted_input(batch), ensure_ascii=False, separators=(",", ":"))}],
    )
    body["top_p"] = 1.0
    body["seed"] = 42
    body["reasoning"] = {"enabled": False, "exclude": True}
    # Keep the provider's response-format injection small. The previous strict
    # schemas dominated the prompt and produced enum/decision collapse.
    body["response_format"] = {"type": "json_object"}
    return body


def prepare() -> None:
    if CONTRACT.exists():
        raise ValueError("contract already exists")
    packets = json.loads((control.PRIVATE / "packets.json").read_text(encoding="utf-8"))
    if [row["case_id"] for row in packets] != control.EXPECTED_CASES:
        raise ValueError("frozen cohort changed")
    batches = control.batches(packets)
    requests = {role: [request(batch, role) for batch in batches] for role in ("content", "brand")}
    receipt = first_attempt.endpoint_receipt()
    dump(PRIVATE / "packets.json", packets)
    dump(PRIVATE / "requests.json", requests)
    dump(PRIVATE / "endpoint-receipt.json", receipt)
    r110 = json.loads((first_attempt.PRIVATE / "1-content-raw-response.json").read_text(encoding="utf-8"))
    r111 = json.loads((adapted.PRIVATE / "1-content-raw-response.json").read_text(encoding="utf-8"))
    sources = [Path(__file__), Path(adapted.__file__), Path(first_attempt.__file__), Path(sol.__file__), Path(control.__file__), control.PRIVATE / "packets.json", PRIVATE / "packets.json", PRIVATE / "requests.json", PRIVATE / "endpoint-receipt.json"]
    contract = {
        "schema_version": "u18-fresh40-v4-0731-json-r112/v1", "frozen_at": now(),
        "purpose": "Test V4 Flash 0731 with its official sampling and compact JSON-object output after two strict-schema failures.",
        "model": first_attempt.MODEL, "provider": first_attempt.PROVIDER,
        "endpoint_tag": first_attempt.ENDPOINT_TAG, "quantization": first_attempt.QUANTIZATION,
        "cases": 40, "brand_reviews": sum(len(row["brand_ids"]) for row in packets),
        "batch_sizes": [20, 20], "roles": ["content", "brand"], "calls": 4,
        "adaptations": [
            "Keep R111 fixed Pxx/Dxx slots and batch-level tracked-brand inventory.",
            "Replace provider-enforced JSON Schema with JSON-object mode plus a concise exact-shape instruction.",
            "Apply official temperature=1.0 and top_p=1.0 sampling, seed 42, and non-thinking mode.",
            "Validate shape and enums locally; preserve cross-field contradictions as model failures instead of coercing them.",
        ],
        "research": {
            "deepseek_model_card": "https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-0731",
            "deepseek_encoding": "https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-0731/blob/main/encoding/README.md",
            "openrouter_structured_outputs": "https://openrouter.ai/docs/guides/features/structured-outputs",
            "finding": "OpenRouter support means an endpoint accepts structured_outputs; it does not guarantee semantic fidelity for a complex schema. DeepSeek's template injects response_format into the system prompt.",
        },
        "rejected_calls_before_this_arm": [
            {"arm": "R110 enum identity", "cost_usd": r110["usage"]["cost"], "failure": "Repeated L45-01 for all 20 cases."},
            {"arm": "R111 fixed strict schema", "cost_usd": r111["usage"]["cost"], "failure": "All 27 brand decisions collapsed to the same contradictory value."},
        ],
        "caps": {"retries": 0, "repairs": 0, "fallbacks": 0, "max_tokens_per_call": MAX_TOKENS},
        "blindness": "Owner answers and comments are absent from packets and requests; report opens them only after result.json exists.",
        "limitations": "Purposefully enriched challenge set with incomplete owner controls; not a production accuracy estimate.",
        "source_sha256": {str(path if not path.is_relative_to(ROOT) else path.relative_to(ROOT)): sol.digest(path) for path in sources},
    }
    dump(CONTRACT, contract)
    sizes = {role: [len(json.dumps(body, ensure_ascii=False).encode()) for body in values] for role, values in requests.items()}
    print(json.dumps({"contract": str(CONTRACT), "calls": 4, "request_bytes": sizes}))


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


def validate_array(value: Any, allowed: tuple[str, ...], exclusive: set[str], path: str, issues: list[dict[str, Any]]) -> None:
    if not isinstance(value, list) or any(item not in allowed for item in value) or len(value) != len(set(value)):
        raise ValueError(path + " invalid array or enum")
    if set(value) & exclusive and len(value) != 1:
        issues.append({"path": path, "issue": "exclusive sentinel combined with another label"})


def parse(decoded: dict[str, Any], batch: list[dict[str, Any]], role: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if decoded.get("model") != first_attempt.MODEL or decoded.get("provider") != first_attempt.PROVIDER:
        raise ValueError("model/provider identity")
    choice = decoded.get("choices", [{}])[0]
    if choice.get("finish_reason") != "stop":
        raise ValueError("incomplete response")
    parsed = json.loads(choice.get("message", {}).get("content", ""))
    decisions, posts = adapted.slot_map(batch)
    expected_root = {"decisions", "post_promotions"} if role == "content" else {"decisions"}
    if not isinstance(parsed, dict) or set(parsed) != expected_root or not isinstance(parsed.get("decisions"), dict) or set(parsed["decisions"]) != set(decisions):
        raise ValueError("fixed decision slots missing or extra")
    if role == "content" and (not isinstance(parsed.get("post_promotions"), dict) or set(parsed["post_promotions"]) != set(posts)):
        raise ValueError("fixed post slots missing or extra")
    issues: list[dict[str, Any]] = []
    for slot, value in parsed["decisions"].items():
        if not isinstance(value, dict):
            raise ValueError("decision is not object")
        if role == "content":
            if set(value) != {"outcome", "post_types", "audience_topics"} or value["outcome"] not in ("classified", "context_missing"):
                raise ValueError("content decision shape or enum")
            validate_array(value["post_types"], sol.POST_TYPES, {"other"}, slot + ".post_types", issues)
            validate_array(value["audience_topics"], sol.TOPICS, {"none", "unavailable"}, slot + ".audience_topics", issues)
            if value["outcome"] == "classified" and not value["post_types"]:
                issues.append({"path": slot, "issue": "classified with no post type"})
            if value["outcome"] == "context_missing" and (value["post_types"] or value["audience_topics"] != ["unavailable"]):
                issues.append({"path": slot, "issue": "context_missing invariant"})
        else:
            expected = {"product_labels", "sentiment", "geopolitical_modes", "china_national_stance", "us_national_stance"}
            if set(value) != expected or value["sentiment"] not in sol.SENTIMENT or value["china_national_stance"] not in sol.STANCE or value["us_national_stance"] not in sol.STANCE:
                raise ValueError("brand decision shape or enum")
            validate_array(value["product_labels"], sol.PRODUCT_LABELS, {"none"}, slot + ".product_labels", issues)
            validate_array(value["geopolitical_modes"], sol.GEO, {"none", "unavailable"}, slot + ".geopolitical_modes", issues)
            if "nationalistic_stance" not in value["geopolitical_modes"] and (value["china_national_stance"] != "none" or value["us_national_stance"] != "none"):
                issues.append({"path": slot, "issue": "national stance without nationalistic_stance mode"})
    if role == "content":
        for slot, value in parsed["post_promotions"].items():
            validate_array(value, sol.PROMOTIONS, {"general", "none"}, slot + ".post_promotions", issues)
    output = []
    for post_slot, packet in posts.items():
        by_brand = []
        for decision_slot, (candidate, brand_id) in decisions.items():
            if candidate["case_id"] == packet["case_id"]:
                by_brand.append({"brand_id": brand_id, **parsed["decisions"][decision_slot]})
        row = {"case_id": packet["case_id"], "input_fingerprint": sol.fingerprint(packet), "by_brand": by_brand}
        if role == "content":
            row["untracked_brand_promotions"] = parsed["post_promotions"][post_slot]
        output.append(row)
    return output, issues


def run() -> None:
    contract = verify()
    if (PRIVATE / "result.json").exists():
        raise ValueError("result already exists")
    packets = json.loads((PRIVATE / "packets.json").read_text(encoding="utf-8"))
    batches = control.batches(packets)
    requests = json.loads((PRIVATE / "requests.json").read_text(encoding="utf-8"))
    result = {"schema_version": contract["schema_version"], "model": first_attempt.MODEL, "provider": first_attempt.PROVIDER, "started_at": now(), "measurements": [], "roles": {"content": [], "brand": []}, "semantic_issues": []}
    key = sol.shared.secret()
    for index, batch in enumerate(batches):
        for role in ("content", "brand"):
            name = f"{index + 1}-{role}"
            decoded, measurement = sol.shared.transport(requests[role][index], key, PRIVATE, name)
            measurement.update({"batch": index + 1, "role": role, "case_count": len(batch)})
            result["measurements"].append(measurement)
            dump(PRIVATE / "partial-result.json", result)
            if decoded is None:
                raise RuntimeError(f"transport failed: {name}")
            rows, issues = parse(decoded, batch, role)
            dump(PRIVATE / f"{name}-parsed.json", rows)
            result["roles"][role].extend(rows)
            result["semantic_issues"].extend({"call": name, **issue} for issue in issues)
            measurement["semantic_issues"] = issues
            dump(PRIVATE / "partial-result.json", result)
            print(json.dumps({"call": name, "status": "valid", "seconds": measurement["latency_ms"] / 1000, "usage": measurement.get("usage"), "semantic_issues": len(issues)}), flush=True)
    result["completed_at"] = now()
    result["actual_billed_usd"] = str(sum(Decimal(str((row.get("usage") or {}).get("cost", 0))) for row in result["measurements"]))
    result["actual_billed_with_fee_usd"] = str(Decimal(result["actual_billed_usd"]) * FEE_FACTOR)
    rejected = sum(Decimal(str(row["cost_usd"])) for row in contract["rejected_calls_before_this_arm"])
    result["total_experiment_cost_with_rejected_calls_and_fee_usd"] = str((Decimal(result["actual_billed_usd"]) + rejected) * FEE_FACTOR)
    dump(PRIVATE / "result.json", result)
    print(json.dumps({"result": str(PRIVATE / "result.json"), "cost_usd": result["actual_billed_usd"], "cost_with_fee_usd": result["actual_billed_with_fee_usd"], "semantic_issues": len(result["semantic_issues"])}))


def report() -> None:
    if not (PRIVATE / "result.json").exists():
        raise ValueError("result must exist")
    if sol.digest(sol.OWNER) != sol.OWNER_SHA256:
        raise ValueError("owner answer SHA changed")
    contract = verify()
    owner = json.loads(sol.OWNER.read_text(encoding="utf-8"))
    results = {"v4_0731": json.loads((PRIVATE / "result.json").read_text(encoding="utf-8")), "v4_1": json.loads((control.DEEPSEEK_DIR / "result.json").read_text(encoding="utf-8")), "sol": json.loads((control.SOL_DIR / "result.json").read_text(encoding="utf-8"))}
    names = {"v4_0731": "V4 Flash 0731 adapted", "v4_1": "V4.1 Flash", "sol": "GPT-5.6 Sol"}
    models = {}
    for key, value in results.items():
        models[key] = {"name": names[key], "score": control.score(value, owner, control.EXPECTED_CASES), "timing": control.timing(value), "semantic_issues": value.get("semantic_issues", []), "multi_label": {field: first_attempt.label_metrics(value, owner, field) for field in ("post_types", "product_labels", "audience_topics")}}
    models["v4_0731"].update(cost_with_fee_usd=results["v4_0731"]["actual_billed_with_fee_usd"], all_experiment_cost_usd=results["v4_0731"]["total_experiment_cost_with_rejected_calls_and_fee_usd"])
    models["v4_1"].update(peak_cost_usd=results["v4_1"]["peak_cost_usd"], offpeak_cost_usd=results["v4_1"]["offpeak_cost_usd"])
    models["sol"].update(cost_with_fee_usd=results["sol"]["actual_billed_with_fee_usd"])
    artifact = {"schema_version": "u18-fresh40-v4-0731-json-comparison/v1", "created_at": now(), "contract_sha256": sol.digest(CONTRACT), "owner_sha256": sol.OWNER_SHA256, "rejected_calls": contract["rejected_calls_before_this_arm"], "models": models}
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    json_path = ROOT / "docs/analysis" / f"{stamp}-u18-v4-0731-json-mode-comparison.json"
    md_path = ROOT / "docs/analysis" / f"{stamp}-u18-v4-0731-json-mode-comparison.md"
    dump(json_path, artifact)
    lines = ["# U18 V4 Flash 0731 model-adapted comparison", "", "V4 Flash 0731 uses fixed Pxx/Dxx slots, official temperature 1.0/top-p 1.0 sampling, non-thinking mode, and lightweight JSON-object output. The evidence, 20/20 batches, taxonomy definitions, and two classifier roles match the V4.1 and Sol controls.", "", "## Results", "", "| Model | Exact owner agreement | Matches / reviewed | Cost for 40 | Role-parallel estimate | Semantic issues |", "|---|---:|---:|---:|---:|---:|"]
    for key in ("v4_0731", "v4_1", "sol"):
        data = models[key]; totals = data["score"]["totals"]
        if key == "v4_0731": cost = f"${float(data['cost_with_fee_usd']):.6f} with fee"
        elif key == "v4_1": cost = f"${float(data['offpeak_cost_usd']):.6f} off-peak / ${float(data['peak_cost_usd']):.6f} peak"
        else: cost = f"${float(data['cost_with_fee_usd']):.6f} with fee"
        lines.append(f"| {data['name']} | {totals['agreement_pct']:.1f}% | {totals['matches']} / {totals['reviewed']} | {cost} | {data['timing']['estimated_parallel_role_seconds']:.1f}s | {len(data['semantic_issues'])} |")
    lines.extend(["", "## Agreement by axis", "", "| Axis | V4 Flash 0731 | V4.1 Flash | GPT-5.6 Sol |", "|---|---:|---:|---:|"])
    for field in [*sol.BRAND_FIELDS, "untracked_brand_promotions"]:
        values = [models[key]["score"]["by_field"][field] for key in ("v4_0731", "v4_1", "sol")]
        lines.append(f"| `{field}` | {values[0]['agreement_pct']:.1f}% ({values[0]['matches']}/{values[0]['reviewed']}) | {values[1]['agreement_pct']:.1f}% ({values[1]['matches']}/{values[1]['reviewed']}) | {values[2]['agreement_pct']:.1f}% ({values[2]['matches']}/{values[2]['reviewed']}) |")
    lines.extend(["", "## Multi-label recovery", "", "| Axis | Model | Recall | Precision | Missing | Extra |", "|---|---|---:|---:|---:|---:|"])
    for field in ("post_types", "product_labels", "audience_topics"):
        for key in ("v4_0731", "v4_1", "sol"):
            value=models[key]["multi_label"][field]
            lines.append(f"| `{field}` | {models[key]['name']} | {100*value['recall']:.1f}% | {100*value['precision']:.1f}% | {value['missing_labels']} | {value['extra_labels']} |")
    rejected = sum(float(row["cost_usd"]) for row in contract["rejected_calls_before_this_arm"])
    lines.extend(["", "## Execution evidence", "", f"- Two rejected strict-schema diagnostic calls cost ${rejected:.6f} before the OpenRouter fee.", f"- Total 0731 experiment spend, including those diagnostics: ${float(models['v4_0731']['all_experiment_cost_usd']):.6f} with the assumed fee.", f"- The completed JSON-mode run recorded {len(models['v4_0731']['semantic_issues'])} preserved cross-field contradictions.", "", "## Limits", "", "- Owner blanks are excluded; selected checkbox sets may themselves be incomplete.", "- This consumed challenge set is not an estimate of production accuracy.", "- The output transport is model-specific, while the taxonomy meanings and evidence remain the same.", ""])
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
