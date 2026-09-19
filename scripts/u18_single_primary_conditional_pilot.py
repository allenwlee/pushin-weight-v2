"""R101: one full primary call, then a conditional rare-type check.

This is an offline evaluation runner. It is not imported by the harvest path.
Prepare freezes everything before transport; run makes at most six sequential
DeepSeek requests and refuses to repeat a started experiment.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from core.classification_contract import parse_stage1_classifications
from scripts import u18_conditional_rare_type_pilot as rare
from scripts.u18_openrouter_two_role_pilot import (
    DEFAULT_MANIFEST, DEFAULT_REFERENCE, ROOT, _json, _quality_release_gates,
    _read_json, _sha, _write_json, attest_provider, build_public_packets,
    direct_deepseek_anthropic_client_factory, score_candidate,
)
from x_monitor.attribution import _PRAGMATICS_FULL_SYSTEM_PROMPT, _stage1_payload, _two_role_fingerprint
from x_monitor.provider_telemetry import normalize_usage

PRIVATE = ROOT / ".context/u18/single-primary-conditional-pilot-r101-v1"
FLOORS = ROOT / "docs/analysis/2026-09-11-002632-classification-quality-floors-v3.json"
BUDGET = ROOT / "docs/analysis/2026-09-14-213123-u18-r98-control-fallback-pilot-contract.json"
CANDIDATE = rare.CANDIDATE
PRIMARY_MAX = 6000
CONDITIONAL_MAX = rare.MAX_TOKENS
HARD_CAP = Decimal("0.20")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def primary_input(batch):
    return _stage1_payload(batch)


def primary_bound(batch):
    return len(_PRAGMATICS_FULL_SYSTEM_PROMPT.encode()) + len(_json(primary_input(batch)).encode()) + 1024


def cost(inputs: int, outputs: int) -> Decimal:
    return (Decimal(inputs) * Decimal("0.44") + Decimal(outputs) * Decimal("1.32")) / 1_000_000


def chunks(packets):
    return [packets[:20], packets[20:40], packets[40:]]


def parse_primary(response, batch):
    if not isinstance(response, dict) or set(response) != {"results"} or not isinstance(response["results"], list):
        raise ValueError("primary response shape")
    expected = {str(p["tweet_id"]): p for p in batch}
    if len(response["results"]) != len(expected):
        raise ValueError("primary response count")
    by_id = {}
    for item in response["results"]:
        if not isinstance(item, dict) or set(item) != {"tweet_id", "classifications", "unsanctioned_flags"}:
            raise ValueError("primary response fields")
        tweet_id = item["tweet_id"]
        if not isinstance(tweet_id, str) or tweet_id not in expected or tweet_id in by_id or not isinstance(item["unsanctioned_flags"], list):
            raise ValueError("primary response identity")
        parsed = parse_stage1_classifications(item["classifications"], expected[tweet_id]["brand_ids"])
        if parsed is None:
            raise ValueError("primary classifications invalid")
        by_id[tweet_id] = {"by_brand": parsed, "unsanctioned_flags": item["unsanctioned_flags"]}
    if set(by_id) != set(expected):
        raise ValueError("primary response incomplete")
    return by_id


def primary_result(batch, parsed, index):
    merged = []
    for packet in batch:
        tweet_id = str(packet["tweet_id"])
        key = _two_role_fingerprint(packet)
        for brand in packet["brand_ids"]:
            merged.append({"row_key": key, "target_brand": brand, **parsed[tweet_id]["by_brand"][brand]})
    return {"batch_index": index, "batch_size": len(batch), "merged": merged, "failed_row_keys": []}


def conditional_schedule(packets, primary):
    result, routing = [], []
    by_key = {_two_role_fingerprint(packet): packet for packet in packets}
    for batch in primary["batches"]:
        selected = []
        for classification in batch["merged"]:
            packet = by_key[classification["row_key"]]
            reasons = rare.routing_reasons(packet, classification)
            routing.append({"row_key": classification["row_key"], "reasons": reasons, "selected": bool(reasons)})
            if reasons:
                selected.append({"row_key": classification["row_key"], "target_brand": classification["target_brand"], "text": packet["text"], "context": packet["context"], "affiliations": packet["affiliations"], "source_language": packet["source_language"], "previous_post_types": classification["post_types"]})
        if len(selected) > 20:
            raise ValueError("conditional batch >20")
        if selected:
            result.append({"base_batch_index": batch["batch_index"], "rows": selected})
    return result, routing


def prepare(path: Path):
    if path.exists():
        raise ValueError("contract exists")
    packets, _ = build_public_packets(_read_json(DEFAULT_MANIFEST))
    batch_sizes = [len(b) for b in chunks(packets)]
    primary_inputs = sum(primary_bound(b) for b in chunks(packets))
    # Conditional routing depends on a paid primary output. Freeze an envelope
    # for all 45 rows in the same three original batches, not a gold-derived size.
    all_conditional = [{"base_batch_index": i, "rows": [{"row_key": _two_role_fingerprint(p), "target_brand": p["brand_ids"][0], "text": p["text"], "context": p["context"], "affiliations": p["affiliations"], "source_language": p["source_language"], "previous_post_types": []} for p in b]} for i, b in enumerate(chunks(packets))]
    conditional_inputs = sum(rare.input_bound(b["rows"]) for b in all_conditional)
    reserved = cost(primary_inputs + conditional_inputs, 3 * PRIMARY_MAX + 3 * CONDITIONAL_MAX)
    if reserved > HARD_CAP:
        raise ValueError("frozen envelope exceeds $0.20")
    sources = {"manifest": DEFAULT_MANIFEST, "owner_reference": DEFAULT_REFERENCE, "floors": FLOORS, "budget": BUDGET, "primary_prompt_source": ROOT / "x_monitor/attribution.py", "conditional_prompt_source": ROOT / "scripts/u18_conditional_rare_type_pilot.py", "runner": Path(__file__)}
    contract = {"schema_version": "u18-r101-single-primary-conditional/v1", "status": "frozen_before_inference", "frozen_at": now(),
        "scope": "One full production-shaped primary classifier call per 20/20/5 batch followed only by source/primary-screened rare-type checks. Owner calibration stays local. No runtime, database, or deployment changes.",
        "sources": {k: {"path": str(v.relative_to(ROOT)), "sha256": sha_path(v)} for k, v in sources.items()},
        "model": CANDIDATE, "primary_prompt_sha256": hashlib.sha256(_PRAGMATICS_FULL_SYSTEM_PROMPT.encode()).hexdigest(), "conditional_prompt_sha256": hashlib.sha256(rare.PROMPT.encode()).hexdigest(),
        "primary_batches": batch_sizes, "conditional_envelope_batches": batch_sizes,
        "caps": {"primary_logical_requests": 3, "conditional_logical_requests_max": 3, "transport_attempts_max": 6, "retries": 0, "concurrency": 1, "primary_max_tokens": PRIMARY_MAX, "conditional_max_tokens": CONDITIONAL_MAX, "input_tokens": primary_inputs + conditional_inputs, "output_tokens": 3 * PRIMARY_MAX + 3 * CONDITIONAL_MAX, "reserved_usd": str(reserved), "hard_cap_usd": str(HARD_CAP), "timeout_seconds": 90, "reasoning_tokens": 0},
        "routing": "After each valid primary response, route only classified rows where visible EN/CJK rare cues or a relevant primary type is present. Primary raw text alone remains sufficient; no owner labels or reference data influence routing.",
        "merge": "Primary owns all six current-v3 axes. Conditional can add only supported rare post types to primary classified rows and never removes/overwrites any primary result. A failed primary stops before conditional; a failed conditional preserves that primary batch. No retry or semantic repair.",
        "evaluation": "Compare the completed merged output with R98+R100 and the owner reference: all-axis scores, rare support/TP/FP/FN, screen misses, incremental cost, and latency. Selection requires all existing gates plus zero conditional false additions; this trial does not waive activation gates."}
    _write_json(path, contract)
    return {"primary_batches": batch_sizes, "maximum_calls": 6, "reserved_usd": str(reserved)}


def load(path):
    contract = _read_json(path)
    for source in contract["sources"].values():
        if sha_path(ROOT / source["path"]) != source["sha256"]:
            raise ValueError("frozen source changed")
    if contract["model"] != CANDIDATE or contract["primary_prompt_sha256"] != hashlib.sha256(_PRAGMATICS_FULL_SYSTEM_PROMPT.encode()).hexdigest() or contract["conditional_prompt_sha256"] != hashlib.sha256(rare.PROMPT.encode()).hexdigest():
        raise ValueError("identity changed")
    packets, local = build_public_packets(_read_json(DEFAULT_MANIFEST))
    return contract, packets, local


def invoke(client, system, payload, max_tokens):
    started = time.monotonic()
    response = client.messages_create(model=CANDIDATE["model"], max_tokens=max_tokens, temperature=0, timeout=90, thinking={"type": "disabled"}, system=system, messages=[{"role": "user", "content": _json(payload)}])
    usage = normalize_usage(getattr(response, "provider_usage", None))
    attest_provider(response, CANDIDATE)
    if usage["input_tokens"] is None or usage["output_tokens"] is None or usage["output_tokens"] > max_tokens or usage.get("reasoning_tokens") not in (None, 0):
        raise ValueError("usage exceeds contract")
    return response, {"latency_ms": round((time.monotonic() - started) * 1000), "usage": usage}


def run(path: Path, private=PRIVATE, client_factory=direct_deepseek_anthropic_client_factory):
    contract, packets, _ = load(path)
    private.mkdir(parents=True, exist_ok=True)
    with (private / "run-start.json").open("x") as handle:
        json.dump({"contract_sha256": sha_path(path), "started_at": now()}, handle)
    client = client_factory(CANDIDATE)
    result = {"contract_sha256": sha_path(path), "started_at": now(), "primary": {"batches": []}, "conditional": {"batches": [], "routing": []}, "measurements": [], "finished": False}
    for index, batch in enumerate(chunks(packets)):
        measurement = {"stage": "primary", "batch_index": index, "rows": len(batch), "status": "attempted", "started_at": now()}
        result["measurements"].append(measurement); _write_json(private / "result.json", result)
        try:
            response, observed = invoke(client, _PRAGMATICS_FULL_SYSTEM_PROMPT, primary_input(batch), PRIMARY_MAX)
            _write_json(private / f"primary-response-{index}.json", {"response": dict(response), "usage": getattr(response, "provider_usage", None)})
            parsed = parse_primary(response, batch)
            primary_batch = primary_result(batch, parsed, index)
            result["primary"]["batches"].append(primary_batch); measurement.update(observed, status="valid")
        except Exception as exc:
            measurement.update(status="failed", error_type=type(exc).__name__); break
        schedule, routing = conditional_schedule(batch, {"batches": [primary_batch]})
        result["conditional"]["routing"].extend(routing)
        if schedule:
            rows = schedule[0]["rows"]
            conditional = {"stage": "conditional", "batch_index": index, "rows": len(rows), "status": "attempted", "started_at": now()}
            result["measurements"].append(conditional); _write_json(private / "result.json", result)
            try:
                response, observed = invoke(client, rare.PROMPT, {"rows": rows}, CONDITIONAL_MAX)
                _write_json(private / f"conditional-response-{index}.json", {"response": dict(response), "usage": getattr(response, "provider_usage", None)})
                decisions = rare.validate_decisions(response, rows)
                result["conditional"]["batches"].append({"base_batch_index": index, "decisions": decisions})
                conditional.update(observed, status="valid")
            except Exception as exc:
                conditional.update(status="failed", error_type=type(exc).__name__); break
        _write_json(private / "result.json", result)
    result["finished"] = True; result["finished_at"] = now()
    decisions = {key: value for item in result["conditional"]["batches"] for key, value in item["decisions"].items()}
    primary = {"batches": result["primary"]["batches"]}
    result["merged"] = rare.merge_additions(primary, decisions)
    _write_json(private / "result.json", result)
    return {"calls": len(result["measurements"]), "primary_rows": sum(b["batch_size"] for b in result["primary"]["batches"]), "conditional_rows": len(decisions), "statuses": [m["status"] for m in result["measurements"]]}


def score(path: Path, private=PRIVATE):
    contract, _, local = load(path); result = _read_json(private / "result.json")
    if result["contract_sha256"] != sha_path(path) or not result["finished"]: raise ValueError("wrong or unfinished run")
    reference = _read_json(DEFAULT_REFERENCE); budget = _read_json(BUDGET); floors = _read_json(FLOORS)["floors"]
    unsupported = budget["baseline_metrics"]["per_label_support_and_f1"]["unsupported"]
    primary_score = score_candidate({"batches": result["primary"]["batches"]}, reference, local, floors, unsupported)
    merged_score = score_candidate(result["merged"], reference, local, floors, unsupported)
    truth = {(str(row["example_id"]), row["brand_id"]): set(row["classification"]["post_types"]) for row in reference["rows"]}
    actual = lambda result_: {(str(local[row["row_key"]]["example_id"]), row["target_brand"]): set(row["post_types"]) for batch in result_["batches"] for row in batch["merged"]}
    before, after = actual({"batches": result["primary"]["batches"]}), actual(result["merged"])
    rare_counts = {}
    selected = {row["row_key"] for item in result["conditional"]["routing"] if item["selected"] for row in []}
    selected = {item["row_key"] for item in result["conditional"]["routing"] if item["selected"]}
    for label in rare.RARE_TYPES:
        support = sum(label in values for values in truth.values()); btp = sum(label in before[p] and label in truth[p] for p in truth); atp = sum(label in after[p] and label in truth[p] for p in truth); afp = sum(label in after[p] and label not in truth[p] for p in truth)
        rare_counts[label] = {"support": support, "primary_tp": btp, "merged_tp": atp, "merged_fp": afp, "screen_misses": sum(label in truth[p] and next(row["row_key"] for row in result["primary"]["batches"] for row in row["merged"] if (str(local[row["row_key"]]["example_id"]), row["target_brand"]) == p) not in selected for p in truth), "merged_fn": sum(label in truth[p] and label not in after[p] for p in truth)}
    usage = {key: sum(int(m.get("usage", {}).get(key) or 0) for m in result["measurements"]) for key in ("input_tokens", "cache_read_input_tokens", "output_tokens")}
    conservative = cost(usage["input_tokens"] + usage["cache_read_input_tokens"], usage["output_tokens"])
    current = (Decimal(usage["input_tokens"]) * Decimal("0.15") + Decimal(usage["cache_read_input_tokens"]) * Decimal("0.003") + Decimal(usage["output_tokens"]) * Decimal("0.60")) / Decimal(1_000_000)
    return {"schema_version": "u18-r101-results/v1", "contract_sha256": sha_path(path), "private_result_sha256": sha_path(private / "result.json"), "primary_score": primary_score, "merged_score": merged_score, "full_quality_gates": _quality_release_gates(merged_score, budget), "rare_counts": rare_counts, "routing": {"selected_rows": len(selected), "total_rows": 45}, "measurements": result["measurements"], "usage": usage, "cost": {"conservative_usd": str(conservative), "current_off_peak_estimate_usd": str(current), "per_1000_current_off_peak_usd": str(current * 1000 / 45)}, "production_changed": False}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=("prepare", "run", "score")); parser.add_argument("--contract", type=Path, required=True); parser.add_argument("--report", type=Path); args = parser.parse_args()
    if args.command == "prepare": out = prepare(args.contract)
    elif args.command == "run": out = run(args.contract)
    else:
        if not args.report or args.report.exists(): parser.error("score requires new --report")
        report = score(args.contract); _write_json(args.report, report); out = {"report": str(args.report), "primary_exact": report["primary_score"]["quality"]["post_types"]["exact_set_accuracy"]["value"], "merged_exact": report["merged_score"]["quality"]["post_types"]["exact_set_accuracy"]["value"]}
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__": main()
