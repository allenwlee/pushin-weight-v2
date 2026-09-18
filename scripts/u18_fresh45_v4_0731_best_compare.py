"""Blind best-chance V4 Flash 0731 comparison on the fresh U18 45 cases."""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from scripts import u18_fresh40_v4_0731_deepinfra as route
from scripts import u18_fresh40_v4_0731_reasoning as normalizer
from scripts import u18_fresh45_sol_compare as sol


ROOT = sol.ROOT
PRIVATE = ROOT / ".context/u18/fresh45-v4-0731-best-r122-v1"
CONTRACT = PRIVATE / "contract.json"
BATCH_SIZE = 20
FEE_FACTOR = Decimal("1.055")
HARD_CAP = Decimal("0.05")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def batches(packets: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    return [packets[index:index + BATCH_SIZE] for index in range(0, len(packets), BATCH_SIZE)]


def prepare() -> None:
    if CONTRACT.exists():
        raise ValueError("contract already exists")
    packets = sol.packets()
    packet_batches = batches(packets)
    requests = {
        role: [route.request(batch, role) for batch in packet_batches]
        for role in ("content", "brand")
    }
    reservation = Decimal("0")
    for body in [body for values in requests.values() for body in values]:
        input_bound = Decimal(len(json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) + 2048)
        reservation += (
            input_bound * route.INPUT_PRICE + Decimal(body["max_tokens"]) * route.OUTPUT_PRICE
        ) / Decimal(1_000_000) * FEE_FACTOR
    if reservation >= HARD_CAP:
        raise ValueError("reservation exceeds hard cap")
    dump(PRIVATE / "packets.json", packets)
    dump(PRIVATE / "requests.json", requests)
    dump(PRIVATE / "endpoint-receipt.json", route.endpoint_receipt())
    sources = [
        Path(__file__), Path(route.__file__), Path(normalizer.__file__), Path(sol.__file__),
        sol.FROZEN_INPUTS, *sol.SIGNAL_EXPORTS, ROOT / "config.yaml",
        PRIVATE / "packets.json", PRIVATE / "requests.json", PRIVATE / "endpoint-receipt.json",
    ]
    contract = {
        "schema_version": "u18-fresh45-v4-0731-best-r122/v1",
        "frozen_at": now(),
        "purpose": "Give V4 Flash 0731 its best tested two-role configuration on the identical fresh-45 evidence and U18A axes used for Sol and V4.1.",
        "model": route.MODEL,
        "provider": route.PROVIDER,
        "endpoint_tag": route.ENDPOINT_TAG,
        "quantization": route.QUANTIZATION,
        "cases": len(packets),
        "brand_reviews": sum(len(packet["brand_ids"]) for packet in packets),
        "batch_sizes": [len(batch) for batch in packet_batches],
        "roles": ["content", "brand"],
        "calls": 6,
        "concurrency": "The two independent roles run concurrently within each batch; batches run in order.",
        "model_specific_configuration": [
            "Fixed Pxx post slots and Dxx brand-decision slots instead of generated identities.",
            "DeepInfra FP8 endpoint pinned with provider fallback disabled.",
            "Temperature 1.0, top_p 1.0, seed 42, and reasoning disabled.",
            "Plain fixed-slot JSON instructions without native response_format injection.",
            "Deterministic removal of one optional JSON fence and conversion of empty no-label arrays to explicit sentinels.",
        ],
        "invariants": "Same 45 posts, evidence, review targets, taxonomy definitions, and owner scoring policy as the Sol/V4.1 pages. Owner material is excluded until compare.",
        "normalization_boundary": "May standardize representation only; it may not add a substantive label, infer a missing row, repair a wrong brand, or consult owner answers.",
        "caps": {
            "requests": 6, "retries": 0, "llm_repairs": 0, "fallbacks": 0,
            "max_tokens_per_request": route.request(packet_batches[0], "content")["max_tokens"],
            "reserved_usd_with_fee": str(reservation), "hard_cap_usd": str(HARD_CAP),
        },
        "limitations": "Purposefully enriched challenge set with incomplete owner controls; not a prevalence-weighted production accuracy estimate. No media or web retrieval during inference.",
        "source_sha256": {
            str(path if not path.is_relative_to(ROOT) else path.relative_to(ROOT)): sol.digest(path)
            for path in sources
        },
    }
    dump(CONTRACT, contract)
    print(json.dumps({"contract": str(CONTRACT), "calls": 6, "reserved_usd_with_fee": str(reservation)}))


def verify() -> dict[str, Any]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    for relative, expected in contract["source_sha256"].items():
        path = Path(relative)
        if not path.is_absolute():
            path = ROOT / path
        if sol.digest(path) != expected:
            raise ValueError("frozen source changed: " + relative)
    return contract


def run_one(name: str, body: dict[str, Any], batch: list[dict[str, Any]], role: str, key: str) -> dict[str, Any]:
    decoded, measurement = sol.shared.transport(body, key, PRIVATE, name)
    measurement.update({"role": role, "case_count": len(batch)})
    if decoded is None:
        return {"measurement": measurement, "error": "transport failed"}
    try:
        rows, raw_issues, representation = normalizer.parse(decoded, batch, role)
    except Exception as exc:
        return {"measurement": measurement, "error": type(exc).__name__ + ": " + str(exc)}
    dump(PRIVATE / f"{name}-parsed-normalized.json", rows)
    return {
        "measurement": measurement,
        "rows": rows,
        "raw_issues": raw_issues,
        "representation": representation,
    }


def run() -> None:
    contract = verify()
    if (PRIVATE / "result.json").exists():
        raise ValueError("result already exists")
    packets = json.loads((PRIVATE / "packets.json").read_text(encoding="utf-8"))
    packet_batches = batches(packets)
    requests = json.loads((PRIVATE / "requests.json").read_text(encoding="utf-8"))
    result: dict[str, Any] = {
        "schema_version": contract["schema_version"], "model": route.MODEL, "provider": route.PROVIDER,
        "started_at": now(), "measurements": [], "roles": {"content": [], "brand": []},
        "raw_issues": [], "representation_normalization": [], "failures": [],
    }
    key = sol.shared.secret()
    for index, batch in enumerate(packet_batches, 1):
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                role: executor.submit(run_one, f"{index}-{role}", requests[role][index - 1], batch, role, key)
                for role in ("content", "brand")
            }
            outcomes = {role: futures[role].result() for role in ("content", "brand")}
        for role, outcome in outcomes.items():
            measurement = outcome["measurement"]
            measurement["batch"] = index
            result["measurements"].append(measurement)
            if "error" in outcome:
                result["failures"].append({"call": f"{index}-{role}", "error": outcome["error"]})
            else:
                result["roles"][role].extend(outcome["rows"])
                result["raw_issues"].extend({"call": f"{index}-{role}", **issue} for issue in outcome["raw_issues"])
                result["representation_normalization"].extend({"call": f"{index}-{role}", **change} for change in outcome["representation"])
            print(json.dumps({
                "call": f"{index}-{role}", "status": "failed" if "error" in outcome else "valid",
                "seconds": measurement["latency_ms"] / 1000, "usage": measurement.get("usage"),
                "raw_issues": len(outcome.get("raw_issues", [])),
                "normalizations": len(outcome.get("representation", [])), "error": outcome.get("error"),
            }), flush=True)
        dump(PRIVATE / "partial-result.json", result)
    if result["failures"] or any(len(result["roles"][role]) != 45 for role in ("content", "brand")):
        raise RuntimeError("fresh-45 result structurally incomplete; raw evidence preserved")
    result["completed_at"] = now()
    result["actual_billed_usd"] = str(sum(
        Decimal(str((measurement.get("usage") or {}).get("cost", 0)))
        for measurement in result["measurements"]
    ))
    result["actual_billed_with_fee_usd"] = str(Decimal(result["actual_billed_usd"]) * FEE_FACTOR)
    result["semantic_issues"] = []
    dump(PRIVATE / "result.json", result)
    print(json.dumps({
        "result": str(PRIVATE / "result.json"), "cost_with_fee_usd": result["actual_billed_with_fee_usd"],
        "raw_issues": len(result["raw_issues"]), "normalizations": len(result["representation_normalization"]),
    }))


def comparison_artifact(owner: dict[str, Any], result: dict[str, Any], result_sha256: str) -> dict[str, Any]:
    model = sol.merge_sol(result)
    comparisons: dict[str, Any] = {}
    counts = {"reviewed": 0, "matches": 0, "differences": 0, "unreviewed": 0}
    field_counts: dict[str, dict[str, int]] = {}
    for case_id, owner_case in owner["cases"].items():
        case: dict[str, Any] = {"per_brand": {}, "post_level": {}}
        for brand in owner_case["review_targets"]:
            fields = {}
            for field in sol.BRAND_FIELDS:
                expected = owner_case["per_brand"][brand].get(field)
                actual = model[case_id]["per_brand"][brand][field]
                is_reviewed = sol.reviewed(expected)
                same = set(expected) == set(actual) if isinstance(expected, list) else expected == actual
                status = "match" if is_reviewed and same else "different" if is_reviewed else "owner_unreviewed"
                fields[field] = {"owner": expected, "sol": actual, "status": status}
                counts["reviewed" if is_reviewed else "unreviewed"] += 1
                if is_reviewed:
                    counts["matches" if status == "match" else "differences"] += 1
                bucket = field_counts.setdefault(field, {"reviewed": 0, "matches": 0, "differences": 0, "unreviewed": 0})
                bucket["reviewed" if is_reviewed else "unreviewed"] += 1
                if is_reviewed:
                    bucket["matches" if status == "match" else "differences"] += 1
            case["per_brand"][brand] = {
                "fields": fields,
                "owner_notes": {key: value for key, value in owner_case["per_brand"][brand].items() if key not in sol.BRAND_FIELDS and value},
            }
        expected = owner_case["post_level"].get("untracked_brand_promotions")
        actual = model[case_id]["post_level"]["untracked_brand_promotions"]
        is_reviewed = sol.reviewed(expected)
        status = "match" if is_reviewed and set(expected) == set(actual) else "different" if is_reviewed else "owner_unreviewed"
        case["post_level"]["untracked_brand_promotions"] = {"owner": expected, "sol": actual, "status": status}
        counts["reviewed" if is_reviewed else "unreviewed"] += 1
        if is_reviewed:
            counts["matches" if status == "match" else "differences"] += 1
        notes = {
            key: owner_case["post_level"].get(key, "")
            for key in ("untracked_brand_promotions_explanation", "post_comments")
            if owner_case["post_level"].get(key)
        }
        if notes:
            case["post_level"]["owner_notes"] = notes
        comparisons[case_id] = case
    return {
        "schema_version": "u18-fresh45-owner-v4-0731-comparison/v1", "created_at": now(),
        "owner_source_sha256": sol.OWNER_SHA256, "model_result_sha256": result_sha256,
        "scoring_policy": "Only nonblank owner controls scored; explicit sentinels count; blanks are unreviewed.",
        "counts": counts, "field_counts": field_counts, "cases": comparisons,
    }


def compare() -> None:
    verify()
    if sol.digest(sol.OWNER) != sol.OWNER_SHA256:
        raise ValueError("owner answer SHA changed")
    result = json.loads((PRIVATE / "result.json").read_text(encoding="utf-8"))
    owner = json.loads(sol.OWNER.read_text(encoding="utf-8"))
    artifact = comparison_artifact(owner, result, sol.digest(PRIVATE / "result.json"))
    sources = {row["case_id"]: row for row in json.loads(sol.FROZEN_INPUTS.read_text(encoding="utf-8"))}
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    json_path = ROOT / "docs/analysis" / f"{stamp}-u18-fresh-45-owner-v4-0731-comparison.json"
    html_path = ROOT / "docs/analysis" / f"{stamp}-u18-fresh-45-owner-v4-0731-comparison.html"
    dump(json_path, artifact)
    rendered = sol.render_html(artifact, owner, sources, result)
    rendered = rendered.replace("GPT-5.6 Sol", "DeepSeek V4 Flash 0731").replace("Owner vs Sol", "Owner vs V4 Flash 0731").replace("owner review vs GPT-5.6 Sol", "owner review vs DeepSeek V4 Flash 0731").replace("SOL", "V4 FLASH 0731").replace("Sol", "V4 Flash 0731")
    html_path.write_text(rendered, encoding="utf-8")
    dump(PRIVATE / "comparison-artifacts.json", {"json": str(json_path), "html": str(html_path)})
    print(json.dumps({
        "html": str(html_path), "json": str(json_path), "counts": artifact["counts"],
        "field_counts": artifact["field_counts"], "cost_with_fee_usd": result["actual_billed_with_fee_usd"],
    }))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "run", "compare"))
    args = parser.parse_args()
    {"prepare": prepare, "run": run, "compare": compare}[args.command]()


if __name__ == "__main__":
    main()
