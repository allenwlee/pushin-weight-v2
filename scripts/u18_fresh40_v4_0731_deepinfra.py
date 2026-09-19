"""Run the frozen U18 fresh-40 benchmark on DeepInfra's V4 0731 endpoint.

This arm keeps the two production-sized 20-post batches and two disjoint
classifier roles. It removes API-native response_format, pins DeepInfra FP8,
and preserves semantic mistakes for scoring without repair or retry.
"""
from __future__ import annotations

import argparse
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from scripts import u18_fresh40_batch20_compare as control
from scripts import u18_fresh40_v4_0731_compare as first_attempt
from scripts import u18_fresh40_v4_0731_five_post as five_post
from scripts import u18_fresh40_v4_0731_five_post_resume as relaxed
from scripts import u18_fresh40_v4_0731_json_mode as json_mode
from scripts import u18_fresh45_sol_compare as sol


ROOT = sol.ROOT
PRIVATE = ROOT / ".context/u18/fresh40-v4-0731-deepinfra-r116-v1"
CONTRACT = PRIVATE / "contract.json"
MODEL = first_attempt.MODEL
PROVIDER = "DeepInfra"
ENDPOINT_TAG = "deepinfra/fp8"
QUANTIZATION = "fp8"
INPUT_PRICE = Decimal("0.06")
CACHE_PRICE = Decimal("0.015")
OUTPUT_PRICE = Decimal("0.18")
FEE_FACTOR = Decimal("1.055")
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
        raise ValueError("pinned DeepInfra endpoint missing or ambiguous")
    endpoint = matches[0]
    pricing = endpoint["pricing"]
    observed = {
        "input": Decimal(pricing["prompt"]) * Decimal(1_000_000),
        "cache_read": Decimal(pricing["input_cache_read"]) * Decimal(1_000_000),
        "output": Decimal(pricing["completion"]) * Decimal(1_000_000),
    }
    if endpoint.get("provider_name") != PROVIDER or endpoint.get("quantization") != QUANTIZATION or endpoint.get("status") != 0:
        raise ValueError("pinned DeepInfra endpoint identity or health changed")
    if observed != {"input": INPUT_PRICE, "cache_read": CACHE_PRICE, "output": OUTPUT_PRICE}:
        raise ValueError(f"pinned DeepInfra endpoint price changed: {observed}")
    required = {"max_tokens", "reasoning", "seed", "temperature", "top_p"}
    if not required.issubset(endpoint.get("supported_parameters") or []):
        raise ValueError("pinned DeepInfra endpoint lacks a requested parameter")
    return {"observed_at": now(), "source": url, "model_id": data["id"], "endpoint": endpoint}


def request(batch: list[dict[str, Any]], role: str) -> dict[str, Any]:
    body = json_mode.request(batch, role)
    body.pop("response_format", None)
    body["provider"] = {
        "only": [PROVIDER],
        "allow_fallbacks": False,
        "require_parameters": True,
        "data_collection": "allow",
        "zdr": False,
        "max_price": {"prompt": float(INPUT_PRICE), "completion": float(OUTPUT_PRICE)},
        "quantizations": [QUANTIZATION],
    }
    return body


def prepare() -> None:
    if CONTRACT.exists():
        raise ValueError("contract already exists")
    packets = json.loads((control.PRIVATE / "packets.json").read_text(encoding="utf-8"))
    if [row["case_id"] for row in packets] != control.EXPECTED_CASES:
        raise ValueError("frozen 40-case cohort changed")
    packet_batches = control.batches(packets)
    requests = {role: [request(batch, role) for batch in packet_batches] for role in ("content", "brand")}
    reservation = Decimal("0")
    for values in requests.values():
        for body in values:
            input_bound = Decimal(len(json.dumps(body, ensure_ascii=False).encode()) + 2048)
            reservation += (input_bound * INPUT_PRICE + Decimal(body["max_tokens"]) * OUTPUT_PRICE) / Decimal(1_000_000) * FEE_FACTOR
    if reservation >= HARD_CAP:
        raise ValueError("reservation exceeds experiment hard cap")
    receipt = endpoint_receipt()
    dump(PRIVATE / "packets.json", packets)
    dump(PRIVATE / "requests.json", requests)
    dump(PRIVATE / "endpoint-receipt.json", receipt)
    sources = [
        Path(__file__), Path(json_mode.__file__), Path(relaxed.__file__), Path(sol.__file__),
        Path(control.__file__), control.PRIVATE / "packets.json", PRIVATE / "packets.json",
        PRIVATE / "requests.json", PRIVATE / "endpoint-receipt.json",
    ]
    contract = {
        "schema_version": "u18-fresh40-v4-0731-deepinfra-r116/v1",
        "frozen_at": now(),
        "purpose": "Test whether V4 Flash 0731 can complete the full production-shaped 40-post workload when served by DeepInfra without native response_format.",
        "model": MODEL,
        "provider": PROVIDER,
        "endpoint_tag": ENDPOINT_TAG,
        "quantization": QUANTIZATION,
        "cases": 40,
        "brand_reviews": sum(len(row["brand_ids"]) for row in packets),
        "batch_sizes": [20, 20],
        "roles": ["content", "brand"],
        "calls": 4,
        "concurrency": "The two roles run concurrently within each batch; batches run in order.",
        "request_design": "R112 fixed slots and plain-text JSON contract; temperature=1.0, top_p=1.0, seed=42, non-thinking, 6000-token ceiling; response_format omitted.",
        "only_changes_from_r112": ["Pin DeepInfra FP8.", "Remove native response_format.", "Run the two independent roles concurrently."],
        "caps": {"retries": 0, "repairs": 0, "fallbacks": 0, "hard_cap_usd": str(HARD_CAP), "reserved_usd_with_fee": str(reservation)},
        "scoring": "Exact field/set agreement on owner-reviewed controls. Preserve invalid enum and cross-field output as scored differences; reject structural omissions.",
        "blindness": "Owner answers and comments are absent from packets and requests; report opens them only after result.json exists.",
        "limitations": "Purposefully enriched challenge set with incomplete owner controls; not a production accuracy estimate. No media or web retrieval during inference.",
        "source_sha256": {str(path if not path.is_relative_to(ROOT) else path.relative_to(ROOT)): sol.digest(path) for path in sources},
    }
    dump(CONTRACT, contract)
    print(json.dumps({"contract": str(CONTRACT), "calls": 4, "reserved_usd_with_fee": str(reservation)}))


def verify() -> dict[str, Any]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    for relative, expected in contract["source_sha256"].items():
        path = Path(relative)
        if not path.is_absolute():
            path = ROOT / path
        if sol.digest(path) != expected:
            raise ValueError("frozen source changed: " + relative)
    return contract


def attest(decoded: dict[str, Any]) -> None:
    if decoded.get("model") != MODEL or decoded.get("provider") != PROVIDER:
        raise ValueError("model/provider identity mismatch")
    available = (((decoded.get("openrouter_metadata") or {}).get("endpoints") or {}).get("available") or [])
    selected = [row for row in available if row.get("selected") is True]
    if len(selected) != 1 or selected[0].get("provider") != PROVIDER:
        raise ValueError("selected endpoint attestation failed")
    usage = decoded.get("usage") or {}
    if not isinstance(usage.get("prompt_tokens"), int) or not isinstance(usage.get("completion_tokens"), int):
        raise ValueError("token usage missing")
    if ((usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0) != 0:
        raise ValueError("unexpected reasoning tokens")


def parse(decoded: dict[str, Any], batch: list[dict[str, Any]], role: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    attest(decoded)
    # The reused semantic parser is provider-independent except for its initial
    # identity assertion. Identity was verified above, so normalize only that
    # top-level field before applying the frozen parser.
    normalized = dict(decoded)
    normalized["provider"] = first_attempt.PROVIDER
    return relaxed.soft_parse(normalized, batch, role)


def run_one(name: str, body: dict[str, Any], batch: list[dict[str, Any]], role: str, key: str) -> dict[str, Any]:
    decoded, measurement = sol.shared.transport(body, key, PRIVATE, name)
    measurement.update({"role": role, "case_count": len(batch)})
    if decoded is None:
        return {"name": name, "measurement": measurement, "error": "transport failed"}
    try:
        rows, issues = parse(decoded, batch, role)
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
    packet_batches = control.batches(packets)
    requests = json.loads((PRIVATE / "requests.json").read_text(encoding="utf-8"))
    result: dict[str, Any] = {
        "schema_version": contract["schema_version"], "model": MODEL, "provider": PROVIDER,
        "started_at": now(), "measurements": [], "roles": {"content": [], "brand": []},
        "semantic_issues": [], "failures": [],
    }
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
    if result["failures"] or len(result["roles"]["content"]) != 40 or len(result["roles"]["brand"]) != 40:
        raise RuntimeError("full result failed structural completeness; raw evidence preserved")
    result["completed_at"] = now()
    result["actual_billed_usd"] = str(sum(Decimal(str((row.get("usage") or {}).get("cost", 0))) for row in result["measurements"]))
    result["actual_billed_with_fee_usd"] = str(Decimal(result["actual_billed_usd"]) * FEE_FACTOR)
    result["scoring_policy"] = "Invalid enum and cross-field values are preserved and score as differences. No repair, retry, or fallback."
    dump(PRIVATE / "result.json", result)
    print(json.dumps({"result": str(PRIVATE / "result.json"), "cost_usd": result["actual_billed_usd"], "cost_with_fee_usd": result["actual_billed_with_fee_usd"], "semantic_issues": len(result["semantic_issues"]), "calls": len(result["measurements"])}))


def report() -> None:
    if not (PRIVATE / "result.json").exists():
        raise ValueError("result must exist")
    if sol.digest(sol.OWNER) != sol.OWNER_SHA256:
        raise ValueError("owner answer SHA changed")
    contract = verify()
    owner = json.loads(sol.OWNER.read_text(encoding="utf-8"))
    results = {
        "deepinfra": json.loads((PRIVATE / "result.json").read_text(encoding="utf-8")),
        "openinference": json.loads((five_post.PRIVATE / "result.json").read_text(encoding="utf-8")),
        "v4_1": json.loads((control.DEEPSEEK_DIR / "result.json").read_text(encoding="utf-8")),
        "sol": json.loads((control.SOL_DIR / "result.json").read_text(encoding="utf-8")),
    }
    labels = {
        "deepinfra": "V4 Flash 0731 / DeepInfra / 20-post",
        "openinference": "V4 Flash 0731 / OpenInference / 5-post",
        "v4_1": "V4.1 Flash direct / 20-post",
        "sol": "GPT-5.6 Sol / 20-post",
    }
    models: dict[str, Any] = {}
    for key, value in results.items():
        models[key] = {
            "label": labels[key],
            "score": control.score(value, owner, control.EXPECTED_CASES),
            "timing": control.timing(value),
            "semantic_issues": value.get("semantic_issues", []),
            "multi_label": {field: first_attempt.label_metrics(value, owner, field) for field in ("post_types", "product_labels", "audience_topics", "geopolitical_modes", "untracked_brand_promotions")},
        }
    models["deepinfra"]["cost_usd"] = results["deepinfra"]["actual_billed_usd"]
    models["deepinfra"]["cost_with_fee_usd"] = results["deepinfra"]["actual_billed_with_fee_usd"]
    models["openinference"]["cost_with_fee_usd"] = results["openinference"]["actual_billed_with_fee_usd"]
    models["v4_1"]["offpeak_cost_usd"] = results["v4_1"]["offpeak_cost_usd"]
    models["v4_1"]["peak_cost_usd"] = results["v4_1"]["peak_cost_usd"]
    models["sol"]["cost_with_fee_usd"] = results["sol"]["actual_billed_with_fee_usd"]
    artifact = {
        "schema_version": "u18-fresh40-v4-0731-deepinfra-comparison/v1", "created_at": now(),
        "contract_sha256": sol.digest(CONTRACT), "owner_sha256": sol.OWNER_SHA256, "models": models,
    }
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    json_path = ROOT / "docs/analysis" / f"{stamp}-u18-v4-0731-deepinfra-batch20-comparison.json"
    md_path = ROOT / "docs/analysis" / f"{stamp}-u18-v4-0731-deepinfra-batch20-comparison.md"
    dump(json_path, artifact)
    lines = [
        "# U18 V4 Flash 0731: DeepInfra 20-post comparison", "",
        "This run uses the frozen 40-post challenge cohort as two 20-post batches. Each batch makes one content call and one brand call concurrently. The DeepInfra arm omits native `response_format`; its full output shape is specified in the plain-text prompt and checked locally.", "",
        "## Results", "",
        "| Model and execution | Exact owner agreement | Matches / reviewed | Cost for 40 | Role-parallel time | Semantic issues |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for key in ("deepinfra", "openinference", "v4_1", "sol"):
        data = models[key]
        total = data["score"]["totals"]
        if key == "v4_1":
            cost = f"${float(data['offpeak_cost_usd']):.6f} off-peak / ${float(data['peak_cost_usd']):.6f} peak"
        else:
            cost = f"${float(data['cost_with_fee_usd']):.6f} with fee"
        lines.append(f"| {data['label']} | {total['agreement_pct']:.1f}% | {total['matches']} / {total['reviewed']} | {cost} | {data['timing']['estimated_parallel_role_seconds']:.1f}s | {len(data['semantic_issues'])} |")
    lines.extend(["", "## Agreement by axis", "", "| Axis | 0731 DeepInfra | 0731 OpenInference | V4.1 Flash | Sol |", "|---|---:|---:|---:|---:|"])
    for field in [*sol.BRAND_FIELDS, "untracked_brand_promotions"]:
        values = [models[key]["score"]["by_field"][field] for key in ("deepinfra", "openinference", "v4_1", "sol")]
        cells = [f"{value['agreement_pct']:.1f}% ({value['matches']}/{value['reviewed']})" for value in values]
        lines.append(f"| `{field}` | " + " | ".join(cells) + " |")
    lines.extend(["", "## Multi-label recovery", "", "| Axis | Model | Recall | Precision | Missing | Extra |", "|---|---|---:|---:|---:|---:|"])
    for field in ("post_types", "product_labels", "audience_topics", "geopolitical_modes", "untracked_brand_promotions"):
        for key in ("deepinfra", "openinference", "v4_1", "sol"):
            value = models[key]["multi_label"][field]
            lines.append(f"| `{field}` | {labels[key]} | {100 * value['recall']:.1f}% | {100 * value['precision']:.1f}% | {value['missing_labels']} | {value['extra_labels']} |")
    deep = models["deepinfra"]
    lines.extend([
        "", "## Interpretation", "",
        f"- DeepInfra returned all 40 content rows and all 40 brand rows across four calls, with {len(deep['semantic_issues'])} preserved semantic contract issues.",
        "- Provider speed and output transport are part of this arm: the weights are still V4 Flash 0731, while endpoint, batching, and omission of native response formatting differ from the five-post OpenInference arm.",
        "- No retries, output repairs, fallback providers, media fetching, or database writes were used.",
        "", "## Limits", "",
        "- Owner blanks are excluded from scoring, and selected checkbox sets may themselves be incomplete.",
        "- This enriched, already-consumed challenge set measures development agreement. It does not estimate live prevalence-weighted accuracy.",
        "- A single four-call run cannot establish operational reliability; it can only clear or fail this structural and semantic benchmark.", "",
    ])
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
