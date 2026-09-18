"""Model-adapted V4 Flash 0731 evaluation with fixed positional output slots."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from scripts import u18_fresh40_batch20_compare as control
from scripts import u18_fresh40_v4_0731_compare as first_attempt
from scripts import u18_fresh45_sol_compare as sol
from x_monitor.openrouter import OpenRouterChatCompletionsClient


ROOT = sol.ROOT
PRIVATE = ROOT / ".context/u18/fresh40-v4-0731-adapted-r111-v1"
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


def enum(values: tuple[str, ...]) -> dict[str, Any]:
    return {"type": "string", "enum": list(values)}


def array(values: tuple[str, ...]) -> dict[str, Any]:
    return {"type": "array", "items": enum(values)}


def obj(properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def slot_map(batch: list[dict[str, Any]]) -> tuple[dict[str, tuple[dict[str, Any], str]], dict[str, dict[str, Any]]]:
    decisions: dict[str, tuple[dict[str, Any], str]] = {}
    posts: dict[str, dict[str, Any]] = {}
    decision_number = 1
    for post_number, packet in enumerate(batch, 1):
        post_slot = f"P{post_number:02d}"
        posts[post_slot] = packet
        for brand_id in packet["brand_ids"]:
            decisions[f"D{decision_number:02d}"] = (packet, brand_id)
            decision_number += 1
    return decisions, posts


def adapted_input(batch: list[dict[str, Any]]) -> dict[str, Any]:
    decisions, posts = slot_map(batch)
    cases = {}
    for post_slot, packet in posts.items():
        decision_slots = {
            decision_slot: brand_id
            for decision_slot, (candidate, brand_id) in decisions.items()
            if candidate["case_id"] == packet["case_id"]
        }
        evidence = {key: value for key, value in packet.items() if key not in {"case_id", "brand_ids"}}
        cases[post_slot] = {
            "case_id_for_audit_only": packet["case_id"],
            "brand_decision_slots": decision_slots,
            "evidence": evidence,
        }
    return {"tracked_brands": sol.tracked_brands(), "cases": cases}


def decision_schema(role: str) -> dict[str, Any]:
    if role == "content":
        return obj({
            "outcome": enum(("classified", "context_missing")),
            "post_types": array(sol.POST_TYPES),
            "audience_topics": array(sol.TOPICS),
        })
    return obj({
        "product_labels": array(sol.PRODUCT_LABELS),
        "sentiment": enum(sol.SENTIMENT),
        "geopolitical_modes": array(sol.GEO),
        "china_national_stance": enum(sol.STANCE),
        "us_national_stance": enum(sol.STANCE),
    })


def response_schema(batch: list[dict[str, Any]], role: str) -> dict[str, Any]:
    decisions, posts = slot_map(batch)
    properties = {
        "decisions": obj({slot: decision_schema(role) for slot in decisions}),
    }
    if role == "content":
        properties["post_promotions"] = obj({slot: array(sol.PROMOTIONS) for slot in posts})
    return obj(properties)


ADAPTATION = """\

MODEL-SPECIFIC OUTPUT MAP:
- The input uses fixed post slots P01, P02, ... and fixed brand-decision slots D01, D02, ... .
- The response schema already supplies every required slot as a fixed object key. Fill each fixed key exactly once.
- Do not copy, generate, or return case IDs, fingerprints, or brand IDs. The caller joins each decision by its fixed slot.
- Judge every D slot independently for the brand named beside that slot in the input.
- For every multi-label axis, select every supported label; do not stop after the most salient label.
- In the content role, post_promotions P slots are post-level and correspond to the same P slots in the input.
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
        max_tokens=MAX_TOKENS,
        temperature=1.0,
        system=(sol.CONTENT_PROMPT if role == "content" else sol.BRAND_PROMPT) + ADAPTATION,
        messages=[{"role": "user", "content": json.dumps(adapted_input(batch), ensure_ascii=False, separators=(",", ":"))}],
    )
    body["top_p"] = 1.0
    body["seed"] = 42
    body["reasoning"] = {"enabled": False, "exclude": True}
    body["response_format"] = {
        "type": "json_schema",
        "json_schema": {"name": role + "_fixed_slots", "strict": True, "schema": response_schema(batch, role)},
    }
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
    sources = [Path(__file__), Path(sol.__file__), Path(control.__file__), Path(first_attempt.__file__), control.PRIVATE / "packets.json", PRIVATE / "packets.json", PRIVATE / "requests.json", PRIVATE / "endpoint-receipt.json"]
    failed_raw = first_attempt.PRIVATE / "1-content-raw-response.json"
    failed_response = json.loads(failed_raw.read_text(encoding="utf-8"))
    contract = {
        "schema_version": "u18-fresh40-v4-0731-adapted-r111/v1", "frozen_at": now(),
        "purpose": "Evaluate a model-specific V4 Flash 0731 request after R110 repeated the first enum case ID twenty times.",
        "model": first_attempt.MODEL, "provider": first_attempt.PROVIDER,
        "endpoint_tag": first_attempt.ENDPOINT_TAG, "quantization": first_attempt.QUANTIZATION,
        "cases": 40, "brand_reviews": sum(len(row["brand_ids"]) for row in packets),
        "batch_sizes": [20, 20], "roles": ["content", "brand"], "calls": 4,
        "adaptations": [
            "Replace generated case/brand identity fields with fixed Pxx/Dxx output object keys.",
            "Move the tracked-brand inventory to one batch-level value instead of repeating it for every post.",
            "Use the official model-card sampling recommendation temperature=1.0 and top_p=1.0.",
            "Keep non-thinking mode, the 6000-token ceiling, evidence, labels, definitions, and two-role ownership unchanged.",
        ],
        "model_guidance_sources": [
            "https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-0731",
            "https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-0731/blob/main/encoding/README.md",
            "https://openrouter.ai/docs/guides/features/structured-outputs",
        ],
        "failed_first_attempt": {"artifact": str(failed_raw.relative_to(ROOT)), "cost_usd": failed_response["usage"]["cost"], "finding": "Strict schema produced 20 result objects but repeated enum value L45-01 for every case; no classification was accepted."},
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


def validate_decision(value: dict[str, Any], role: str) -> None:
    if role == "content":
        if set(value) != {"outcome", "post_types", "audience_topics"}:
            raise ValueError("content decision shape")
        if value["outcome"] not in ("classified", "context_missing"):
            raise ValueError("outcome enum")
        if value["outcome"] == "classified":
            relaxed.validate_array(value["post_types"], sol.POST_TYPES, {"other"})
        elif value["post_types"] or value["audience_topics"] != ["unavailable"]:
            raise ValueError("context_missing invariant")
        relaxed.validate_array(value["audience_topics"], sol.TOPICS, {"none", "unavailable"})
    else:
        if set(value) != {"product_labels", "sentiment", "geopolitical_modes", "china_national_stance", "us_national_stance"}:
            raise ValueError("brand decision shape")
        relaxed.validate_array(value["product_labels"], sol.PRODUCT_LABELS, {"none"})
        relaxed.validate_array(value["geopolitical_modes"], sol.GEO, {"none", "unavailable"})
        if value["sentiment"] not in sol.SENTIMENT or value["china_national_stance"] not in sol.STANCE or value["us_national_stance"] not in sol.STANCE:
            raise ValueError("brand scalar enum")


def parse(decoded: dict[str, Any], batch: list[dict[str, Any]], role: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if decoded.get("model") != first_attempt.MODEL or decoded.get("provider") != first_attempt.PROVIDER:
        raise ValueError("model/provider identity")
    choice = decoded.get("choices", [{}])[0]
    if choice.get("finish_reason") != "stop":
        raise ValueError("incomplete response")
    parsed = json.loads(choice.get("message", {}).get("content", ""))
    decisions, posts = slot_map(batch)
    expected_root = {"decisions", "post_promotions"} if role == "content" else {"decisions"}
    if not isinstance(parsed, dict) or set(parsed) != expected_root or not isinstance(parsed.get("decisions"), dict) or set(parsed["decisions"]) != set(decisions):
        raise ValueError("fixed decision slots missing or extra")
    if role == "content" and (not isinstance(parsed["post_promotions"], dict) or set(parsed["post_promotions"]) != set(posts)):
        raise ValueError("fixed post slots missing or extra")
    for value in parsed["decisions"].values():
        validate_decision(value, role)
    if role == "content":
        for value in parsed["post_promotions"].values():
            relaxed.validate_array(value, sol.PROMOTIONS, {"general", "none"})
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
    issues = control.semantic_issues(output, role)
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
            result["semantic_issues"].extend(issues)
            measurement["semantic_issues"] = issues
            dump(PRIVATE / "partial-result.json", result)
            print(json.dumps({"call": name, "status": "valid", "seconds": measurement["latency_ms"] / 1000, "usage": measurement.get("usage"), "semantic_issues": issues}), flush=True)
    result["completed_at"] = now()
    result["actual_billed_usd"] = str(sum(Decimal(str((row.get("usage") or {}).get("cost", 0))) for row in result["measurements"]))
    result["actual_billed_with_fee_usd"] = str(Decimal(result["actual_billed_usd"]) * FEE_FACTOR)
    result["total_experiment_cost_with_failed_first_attempt_usd"] = str((Decimal(result["actual_billed_usd"]) + Decimal(str(contract["failed_first_attempt"]["cost_usd"]))) * FEE_FACTOR)
    dump(PRIVATE / "result.json", result)
    print(json.dumps({"result": str(PRIVATE / "result.json"), "cost_usd": result["actual_billed_usd"], "cost_with_fee_usd": result["actual_billed_with_fee_usd"], "semantic_issues": len(result["semantic_issues"])}))


def report() -> None:
    if not (PRIVATE / "result.json").exists():
        raise ValueError("result must exist")
    if sol.digest(sol.OWNER) != sol.OWNER_SHA256:
        raise ValueError("owner answer SHA changed")
    contract = verify()
    owner = json.loads(sol.OWNER.read_text(encoding="utf-8"))
    results = {
        "v4_0731": json.loads((PRIVATE / "result.json").read_text(encoding="utf-8")),
        "v4_1": json.loads((control.DEEPSEEK_DIR / "result.json").read_text(encoding="utf-8")),
        "sol": json.loads((control.SOL_DIR / "result.json").read_text(encoding="utf-8")),
    }
    names = {"v4_0731": "V4 Flash 0731 adapted", "v4_1": "V4.1 Flash", "sol": "GPT-5.6 Sol"}
    models = {}
    for key, value in results.items():
        models[key] = {"name": names[key], "score": control.score(value, owner, control.EXPECTED_CASES), "timing": control.timing(value), "semantic_issues": value.get("semantic_issues", []), "multi_label": {field: first_attempt.label_metrics(value, owner, field) for field in ("post_types", "product_labels", "audience_topics")}}
    models["v4_0731"].update(cost_usd=results["v4_0731"]["actual_billed_usd"], cost_with_fee_usd=results["v4_0731"]["actual_billed_with_fee_usd"], experiment_cost_with_failed_first_attempt_usd=results["v4_0731"]["total_experiment_cost_with_failed_first_attempt_usd"])
    models["v4_1"].update(peak_cost_usd=results["v4_1"]["peak_cost_usd"], offpeak_cost_usd=results["v4_1"]["offpeak_cost_usd"])
    models["sol"].update(cost_with_fee_usd=results["sol"]["actual_billed_with_fee_usd"])
    artifact = {"schema_version": "u18-fresh40-v4-0731-adapted-comparison/v1", "created_at": now(), "contract_sha256": sol.digest(CONTRACT), "owner_sha256": sol.OWNER_SHA256, "failed_first_attempt": contract["failed_first_attempt"], "models": models}
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    json_path = ROOT / "docs/analysis" / f"{stamp}-u18-v4-0731-adapted-comparison.json"
    md_path = ROOT / "docs/analysis" / f"{stamp}-u18-v4-0731-adapted-comparison.md"
    dump(json_path, artifact)
    lines = ["# U18 V4 Flash 0731 adapted comparison", "", "The first enum-identity attempt was rejected after one call because it repeated L45-01 twenty times. The adapted run uses fixed output slots, official temperature 1.0/top-p 1.0 sampling, and the same 40 cases, prompts, roles, and owner-scoring policy as the V4.1 and Sol controls.", "", "## Results", "", "| Model | Exact owner agreement | Matches / reviewed | Cost for 40 | Role-parallel estimate | Semantic issues |", "|---|---:|---:|---:|---:|---:|"]
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
            value = models[key]["multi_label"][field]
            lines.append(f"| `{field}` | {models[key]['name']} | {100*value['recall']:.1f}% | {100*value['precision']:.1f}% | {value['missing_labels']} | {value['extra_labels']} |")
    lines.extend(["", "## Cost accounting", "", f"- Rejected first attempt: ${float(contract['failed_first_attempt']['cost_usd']):.6f} before the OpenRouter credit fee.", f"- Adapted four-call run plus rejected attempt: ${float(models['v4_0731']['experiment_cost_with_failed_first_attempt_usd']):.6f} including the assumed 5.5% fee.", "", "## Limits", "", "- Owner blanks are excluded; selected checkbox sets may themselves be incomplete.", "- This consumed challenge set is not an estimate of production accuracy.", "- The fixed-slot schema is a model-specific transport adaptation; it does not change taxonomy definitions.", ""])
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
