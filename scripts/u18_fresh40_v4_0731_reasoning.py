"""Isolate high reasoning on the frozen R116 V4 0731 two-role workload."""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from scripts import u18_fresh40_batch20_compare as control
from scripts import u18_fresh40_v4_0731_compare as first_attempt
from scripts import u18_fresh40_v4_0731_deepinfra as baseline
from scripts import u18_fresh40_v4_0731_five_post_resume as relaxed
from scripts import u18_fresh45_sol_compare as sol


ROOT = sol.ROOT
PRIVATE = ROOT / ".context/u18/fresh40-v4-0731-reasoning-r117-v1"
CONTRACT = PRIVATE / "contract.json"
FEE_FACTOR = Decimal("1.055")
HARD_CAP = Decimal("0.05")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def prepare() -> None:
    if CONTRACT.exists():
        raise ValueError("contract already exists")
    packets = json.loads((baseline.PRIVATE / "packets.json").read_text(encoding="utf-8"))
    original = json.loads((baseline.PRIVATE / "requests.json").read_text(encoding="utf-8"))
    requests = deepcopy(original)
    for values in requests.values():
        for body in values:
            if body.get("reasoning") != {"enabled": False, "exclude": True}:
                raise ValueError("R116 reasoning baseline changed")
            body["reasoning"] = {"effort": "high", "exclude": True}
    reservation = Decimal("0")
    for values in requests.values():
        for body in values:
            input_bound = Decimal(len(json.dumps(body, ensure_ascii=False).encode()) + 2048)
            reservation += (input_bound * baseline.INPUT_PRICE + Decimal(body["max_tokens"]) * baseline.OUTPUT_PRICE) / Decimal(1_000_000) * FEE_FACTOR
    if reservation >= HARD_CAP:
        raise ValueError("reservation exceeds hard cap")
    dump(PRIVATE / "packets.json", packets)
    dump(PRIVATE / "requests.json", requests)
    dump(PRIVATE / "endpoint-receipt.json", baseline.endpoint_receipt())
    sources = [
        Path(__file__), Path(relaxed.__file__), Path(baseline.__file__), Path(sol.__file__),
        baseline.CONTRACT, baseline.PRIVATE / "packets.json", baseline.PRIVATE / "requests.json",
        PRIVATE / "packets.json", PRIVATE / "requests.json", PRIVATE / "endpoint-receipt.json",
    ]
    contract = {
        "schema_version": "u18-fresh40-v4-0731-reasoning-r117/v1",
        "frozen_at": now(),
        "purpose": "Isolate whether enabling the model's default high reasoning improves V4 Flash 0731 on the same two-role, 20-post DeepInfra workload.",
        "model": baseline.MODEL,
        "provider": baseline.PROVIDER,
        "endpoint_tag": baseline.ENDPOINT_TAG,
        "cases": 40,
        "batch_sizes": [20, 20],
        "roles": ["content", "brand"],
        "calls": 4,
        "only_inference_change_from_r116": "reasoning changes from disabled to effort=high; exclude=true. All prompts, inputs, batches, max_tokens, temperature, top_p, seed, route, and prices remain byte-equivalent otherwise.",
        "caps": {"retries": 0, "repairs_by_llm": 0, "fallbacks": 0, "reserved_usd_with_fee": str(reservation), "hard_cap_usd": str(HARD_CAP)},
        "scoring": "Report raw output compliance and exact owner agreement after the same deterministic fence/sentinel normalization applied diagnostically to R116.",
        "blindness": "Owner answers and comments are absent from packets and requests; scoring opens them only after result.json exists.",
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


def parse(decoded: dict[str, Any], batch: list[dict[str, Any]], role: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if decoded.get("model") != baseline.MODEL or decoded.get("provider") != baseline.PROVIDER:
        raise ValueError("model/provider identity mismatch")
    selected = [row for row in ((((decoded.get("openrouter_metadata") or {}).get("endpoints") or {}).get("available") or [])) if row.get("selected") is True]
    if len(selected) != 1 or selected[0].get("provider") != baseline.PROVIDER:
        raise ValueError("selected endpoint attestation failed")
    choice = decoded.get("choices", [{}])[0]
    if choice.get("finish_reason") != "stop":
        raise ValueError("incomplete response")
    content = choice.get("message", {}).get("content", "").strip()
    compliance: list[dict[str, Any]] = []
    if content.startswith("```json\n") and content.endswith("```"):
        compliance.append({"issue": "markdown_json_fence"})
        content = content[len("```json\n"):-len("```")].strip()
    normalized = deepcopy(decoded)
    normalized["provider"] = first_attempt.PROVIDER
    normalized["choices"][0]["message"]["content"] = content
    rows, semantic = relaxed.soft_parse(normalized, batch, role)
    representation: list[dict[str, Any]] = []
    if role == "content":
        for row in rows:
            for brand in row["by_brand"]:
                if brand["audience_topics"] == []:
                    value = ["unavailable"] if brand["outcome"] == "context_missing" else ["none"]
                    brand["audience_topics"] = value
                    representation.append({"case_id": row["case_id"], "brand_id": brand["brand_id"], "field": "audience_topics", "to": value})
                if brand["post_types"] == [] and brand["outcome"] == "classified":
                    brand["post_types"] = ["other"]
                    representation.append({"case_id": row["case_id"], "brand_id": brand["brand_id"], "field": "post_types", "to": ["other"]})
            if row["untracked_brand_promotions"] == []:
                row["untracked_brand_promotions"] = ["none"]
                representation.append({"case_id": row["case_id"], "field": "untracked_brand_promotions", "to": ["none"]})
    return rows, compliance + semantic, representation


def run_one(name: str, body: dict[str, Any], batch: list[dict[str, Any]], role: str, key: str) -> dict[str, Any]:
    decoded, measurement = sol.shared.transport(body, key, PRIVATE, name)
    measurement.update({"role": role, "case_count": len(batch)})
    if decoded is None:
        return {"measurement": measurement, "error": "transport failed"}
    try:
        rows, raw_issues, normalization = parse(decoded, batch, role)
    except Exception as exc:
        return {"measurement": measurement, "error": type(exc).__name__ + ": " + str(exc)}
    dump(PRIVATE / f"{name}-parsed-normalized.json", rows)
    return {"measurement": measurement, "rows": rows, "raw_issues": raw_issues, "normalization": normalization}


def run() -> None:
    contract = verify()
    packets = json.loads((PRIVATE / "packets.json").read_text(encoding="utf-8"))
    requests = json.loads((PRIVATE / "requests.json").read_text(encoding="utf-8"))
    result: dict[str, Any] = {
        "schema_version": contract["schema_version"], "model": baseline.MODEL, "provider": baseline.PROVIDER,
        "started_at": now(), "roles": {"content": [], "brand": []}, "measurements": [],
        "raw_compliance_and_semantic_issues": [], "representation_normalization": [], "failures": [],
    }
    key = sol.shared.secret()
    for index, batch in enumerate(control.batches(packets)):
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {role: executor.submit(run_one, f"{index + 1}-{role}", requests[role][index], batch, role, key) for role in ("content", "brand")}
            outcomes = {role: futures[role].result() for role in ("content", "brand")}
        for role, outcome in outcomes.items():
            measurement = outcome["measurement"]
            measurement["batch"] = index + 1
            result["measurements"].append(measurement)
            name = f"{index + 1}-{role}"
            if "error" in outcome:
                result["failures"].append({"call": name, "error": outcome["error"]})
            else:
                result["roles"][role].extend(outcome["rows"])
                result["raw_compliance_and_semantic_issues"].extend({"call": name, **issue} for issue in outcome["raw_issues"])
                result["representation_normalization"].extend({"call": name, **change} for change in outcome["normalization"])
            print(json.dumps({"call": name, "status": "failed" if "error" in outcome else "valid", "seconds": measurement["latency_ms"] / 1000, "usage": measurement.get("usage"), "raw_issues": len(outcome.get("raw_issues", [])), "normalizations": len(outcome.get("normalization", [])), "error": outcome.get("error")}), flush=True)
        dump(PRIVATE / "partial-result.json", result)
    if result["failures"] or any(len(result["roles"][role]) != 40 for role in ("content", "brand")):
        raise RuntimeError("reasoning arm structurally incomplete; raw evidence preserved")
    result["completed_at"] = now()
    result["actual_billed_usd"] = str(sum(Decimal(str((row.get("usage") or {}).get("cost", 0))) for row in result["measurements"]))
    result["actual_billed_with_fee_usd"] = str(Decimal(result["actual_billed_usd"]) * FEE_FACTOR)
    result["semantic_issues"] = []
    dump(PRIVATE / "result.json", result)
    print(json.dumps({"result": str(PRIVATE / "result.json"), "cost_with_fee_usd": result["actual_billed_with_fee_usd"], "raw_issues": len(result["raw_compliance_and_semantic_issues"]), "normalizations": len(result["representation_normalization"])}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "run"))
    args = parser.parse_args()
    {"prepare": prepare, "run": run}[args.command]()


if __name__ == "__main__":
    main()
