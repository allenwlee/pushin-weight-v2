"""Blind DeepSeek V4.1 Flash comparison on the fresh U18 45-case cohort."""
from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from scripts import u18_fresh45_sol_compare as shared
from x_monitor.attribution import AnthropicClaudeClient
from x_monitor.provider_telemetry import normalize_usage


ROOT = shared.ROOT
PRIVATE = ROOT / ".context/u18/fresh45-deepseek-comparison-r108-v1"
MODEL = "deepseek-v4-flash"
RESPONSE_MODELS = {MODEL, "deepseek-flash"}
BASE_URL = "https://api.deepseek.com/anthropic"
MAX_TOKENS = 6000
BATCH_SIZE = 15
PEAK_INPUT = Decimal("0.30")
PEAK_CACHE = Decimal("0.006")
PEAK_OUTPUT = Decimal("1.20")
OFFPEAK_INPUT = Decimal("0.15")
OFFPEAK_CACHE = Decimal("0.003")
OFFPEAK_OUTPUT = Decimal("0.60")
HARD_CAP = Decimal("0.25")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def secret() -> str:
    value = None
    for line in Path("/Users/fuchitalee/.env.secrets").read_text().splitlines():
        if "=" not in line:
            continue
        key, raw = line.split("=", 1)
        if key.replace("export", "").strip() == "DEEPSEEK_API_KEY":
            parts = shlex.split(raw, comments=True)
            if len(parts) != 1:
                raise ValueError("DEEPSEEK_API_KEY must be one literal value")
            value = parts[0]
    if not value:
        raise ValueError("DEEPSEEK_API_KEY is missing")
    return value


def logical_request(batch: list[dict[str, Any]], role: str) -> dict[str, Any]:
    prompt = shared.CONTENT_PROMPT if role == "content" else shared.BRAND_PROMPT
    schema = shared.response_schema(batch, role)
    system = prompt + "\n\nOUTPUT CONTRACT: Return one JSON object that validates exactly against this schema. Do not wrap it in Markdown or add prose.\n" + json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
    payload = [{**row, "input_fingerprint": shared.fingerprint(row), "tracked_brands": shared.tracked_brands()} for row in batch]
    return {"model": MODEL, "max_tokens": MAX_TOKENS, "temperature": 0, "thinking": {"type": "disabled"}, "system": system, "messages": [{"role": "user", "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}]}


def token_reservation(requests: dict[str, list[dict[str, Any]]]) -> Decimal:
    # UTF-8 bytes overestimate input tokens; full max output is also reserved.
    total = Decimal("0")
    for bodies in requests.values():
        for body in bodies:
            input_bound = len(json.dumps(body, ensure_ascii=False).encode()) + 2048
            total += (Decimal(input_bound) * PEAK_INPUT + Decimal(MAX_TOKENS) * PEAK_OUTPUT) / Decimal(1_000_000)
    return total


def prepare() -> None:
    if (PRIVATE / "contract.json").exists():
        raise ValueError("contract already frozen")
    packets = shared.packets()
    batches = [packets[index:index + BATCH_SIZE] for index in range(0, len(packets), BATCH_SIZE)]
    requests = {role: [logical_request(batch, role) for batch in batches] for role in ("content", "brand")}
    reserved = token_reservation(requests)
    if reserved >= HARD_CAP:
        raise ValueError("reservation exceeds hard cap")
    dump(PRIVATE / "packets.json", packets)
    dump(PRIVATE / "requests.json", requests)
    sol_packets = shared.PRIVATE / "packets.json"
    if not sol_packets.exists() or json.loads(sol_packets.read_text()) != packets:
        raise ValueError("DeepSeek and Sol evidence packets differ")
    sources = [Path(__file__), Path(shared.__file__), shared.FROZEN_INPUTS, *shared.SIGNAL_EXPORTS, shared.TAXONOMY, ROOT / "config.yaml", PRIVATE / "packets.json", PRIVATE / "requests.json"]
    contract = {
        "schema_version": "u18-fresh45-deepseek-comparison-r108/v1", "frozen_at": now(),
        "purpose": "Run incumbent DeepSeek V4.1 Flash on the identical fresh-45 evidence and U18A two-role semantics used for Sol.",
        "blindness": "Owner answers and comments are excluded from packets, requests, contract sources, and inference. compare opens them only after result.json exists.",
        "model_request": MODEL, "provider": "direct DeepSeek Anthropic-compatible API", "response_model_aliases": sorted(RESPONSE_MODELS),
        "provider_adaptation": "Direct DeepSeek lacks the OpenAI response_format used by Sol, so the identical strict JSON schema is appended to the system prompt and the same semantic validator is applied after response parsing.",
        "roles": ["content", "brand"], "batch_sizes": [15, 15, 15], "cases": 45, "brand_reviews": 57,
        "caps": {"requests": 6, "retries": 0, "repairs": 0, "fallbacks": 0, "max_tokens_per_request": MAX_TOKENS, "hard_cap_usd": str(HARD_CAP), "peak_reserved_usd": str(reserved), "timeout_seconds": 120},
        "pricing_per_million": {"peak_input": str(PEAK_INPUT), "peak_cache_read": str(PEAK_CACHE), "peak_output": str(PEAK_OUTPUT), "offpeak_input": str(OFFPEAK_INPUT), "offpeak_cache_read": str(OFFPEAK_CACHE), "offpeak_output": str(OFFPEAK_OUTPUT)},
        "owner_scoring_policy": "Only nonblank owner radio values and nonempty checkbox arrays are benchmark judgments. Explicit none/unavailable/unknown values count; blanks are unreviewed and excluded.",
        "limitations": "Purposefully enriched challenge set, not a prevalence-weighted sample or production-accuracy estimate. No media or web browsing.",
        "source_sha256": {str(path if not path.is_relative_to(ROOT) else path.relative_to(ROOT)): digest(path) for path in sources},
    }
    dump(PRIVATE / "contract.json", contract)
    print(json.dumps({"contract": str(PRIVATE / "contract.json"), "requests": 6, "peak_reserved_usd": str(reserved)}))


def validate_response(response: Any, batch: list[dict[str, Any]], role: str) -> list[dict[str, Any]]:
    if not isinstance(response, dict):
        raise ValueError("response is not JSON object")
    wrapped = {"model": shared.MODEL, "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(response, ensure_ascii=False)}}]}
    return shared.parse(wrapped, batch, role)


def run() -> None:
    contract = json.loads((PRIVATE / "contract.json").read_text())
    for relative, expected in contract["source_sha256"].items():
        path = Path(relative)
        if not path.is_absolute():
            path = ROOT / path
        if digest(path) != expected:
            raise ValueError("frozen source changed: " + relative)
    client = AnthropicClaudeClient(api_key=secret(), base_url=BASE_URL)
    packets = json.loads((PRIVATE / "packets.json").read_text())
    batches = [packets[index:index + BATCH_SIZE] for index in range(0, len(packets), BATCH_SIZE)]
    requests = json.loads((PRIVATE / "requests.json").read_text())
    result = {"schema_version": contract["schema_version"], "model": "DeepSeek V4.1 Flash", "provider": "direct DeepSeek", "started_at": now(), "measurements": [], "roles": {"content": [], "brand": []}}
    for index, batch in enumerate(batches):
        for role in ("content", "brand"):
            name = f"{index + 1}-{role}"
            body = requests[role][index]
            dump(PRIVATE / f"{name}-request.json", body)
            started = time.monotonic()
            response = client.messages_create(timeout=120, **body)
            usage_raw = getattr(response, "provider_usage", None)
            usage = normalize_usage(usage_raw)
            if not isinstance(usage_raw, dict) or usage_raw.get("provider") != "deepseek" or usage_raw.get("model") not in RESPONSE_MODELS or not usage_raw.get("provider_request_id"):
                raise ValueError("DeepSeek provider/model attestation failed")
            parsed = validate_response(dict(response), batch, role)
            dump(PRIVATE / f"{name}-response.json", {"response": dict(response), "usage": usage_raw})
            result["roles"][role].extend(parsed)
            measurement = {"call": name, "role": role, "batch": index + 1, "case_count": len(batch), "latency_ms": round((time.monotonic() - started) * 1000), "usage": usage}
            result["measurements"].append(measurement)
            dump(PRIVATE / "partial-result.json", result)
            print(json.dumps({"call": name, "status": "valid", "seconds": measurement["latency_ms"] / 1000, "usage": usage}), flush=True)
    result["completed_at"] = now()
    usage = {key: sum(int(row["usage"].get(key) or 0) for row in result["measurements"]) for key in ("input_tokens", "cache_read_input_tokens", "output_tokens")}
    result["usage"] = usage
    result["peak_cost_usd"] = str((Decimal(usage["input_tokens"]) * PEAK_INPUT + Decimal(usage["cache_read_input_tokens"]) * PEAK_CACHE + Decimal(usage["output_tokens"]) * PEAK_OUTPUT) / Decimal(1_000_000))
    result["offpeak_cost_usd"] = str((Decimal(usage["input_tokens"]) * OFFPEAK_INPUT + Decimal(usage["cache_read_input_tokens"]) * OFFPEAK_CACHE + Decimal(usage["output_tokens"]) * OFFPEAK_OUTPUT) / Decimal(1_000_000))
    dump(PRIVATE / "result.json", result)
    print(json.dumps({"result": str(PRIVATE / "result.json"), "peak_cost_usd": result["peak_cost_usd"], "offpeak_cost_usd": result["offpeak_cost_usd"]}))


def compare() -> None:
    if not (PRIVATE / "result.json").exists():
        raise ValueError("DeepSeek result must be frozen before owner answers are opened")
    if digest(shared.OWNER) != shared.OWNER_SHA256:
        raise ValueError("owner answer SHA changed")
    owner = json.loads(shared.OWNER.read_text())
    result = json.loads((PRIVATE / "result.json").read_text())
    model = shared.merge_sol(result)
    sources = {row["case_id"]: row for row in json.loads(shared.FROZEN_INPUTS.read_text())}
    comparisons = {}
    counts = {"reviewed": 0, "matches": 0, "differences": 0, "unreviewed": 0}
    field_counts: dict[str, dict[str, int]] = {}
    for case_id, owner_case in owner["cases"].items():
        case = {"per_brand": {}, "post_level": {}}
        for brand in owner_case["review_targets"]:
            fields = {}
            for field in shared.BRAND_FIELDS:
                oval = owner_case["per_brand"][brand].get(field)
                value = model[case_id]["per_brand"][brand][field]
                is_reviewed = shared.reviewed(oval)
                status = "match" if is_reviewed and (set(oval) == set(value) if isinstance(oval, list) else oval == value) else "different" if is_reviewed else "owner_unreviewed"
                fields[field] = {"owner": oval, "deepseek": value, "status": status}
                counts["reviewed" if is_reviewed else "unreviewed"] += 1
                if is_reviewed:
                    counts["matches" if status == "match" else "differences"] += 1
                bucket = field_counts.setdefault(field, {"reviewed": 0, "matches": 0, "differences": 0, "unreviewed": 0})
                bucket["reviewed" if is_reviewed else "unreviewed"] += 1
                if is_reviewed:
                    bucket["matches" if status == "match" else "differences"] += 1
            case["per_brand"][brand] = {"fields": fields, "owner_notes": {key: value for key, value in owner_case["per_brand"][brand].items() if key not in shared.BRAND_FIELDS and value}}
        oval = owner_case["post_level"].get("untracked_brand_promotions")
        value = model[case_id]["post_level"]["untracked_brand_promotions"]
        is_reviewed = shared.reviewed(oval)
        status = "match" if is_reviewed and set(oval) == set(value) else "different" if is_reviewed else "owner_unreviewed"
        case["post_level"]["untracked_brand_promotions"] = {"owner": oval, "deepseek": value, "status": status}
        counts["reviewed" if is_reviewed else "unreviewed"] += 1
        if is_reviewed:
            counts["matches" if status == "match" else "differences"] += 1
        notes = {key: owner_case["post_level"].get(key) for key in ("untracked_brand_promotions_explanation", "post_comments") if owner_case["post_level"].get(key)}
        if notes:
            case["post_level"]["owner_notes"] = notes
        comparisons[case_id] = case
    artifact = {"schema_version": "u18-fresh45-owner-deepseek-comparison/v1", "created_at": now(), "owner_source_sha256": shared.OWNER_SHA256, "deepseek_result_sha256": digest(PRIVATE / "result.json"), "scoring_policy": "Only nonblank owner controls scored; explicit sentinels count; blanks are unreviewed.", "counts": counts, "field_counts": field_counts, "peak_cost_usd": result["peak_cost_usd"], "offpeak_cost_usd": result["offpeak_cost_usd"], "cases": comparisons}
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    json_path = ROOT / "docs/analysis" / f"{stamp}-u18-fresh-45-owner-deepseek-comparison.json"
    html_path = ROOT / "docs/analysis" / f"{stamp}-u18-fresh-45-owner-deepseek-comparison.html"
    dump(json_path, artifact)
    # Reuse the verified tabbed renderer by translating only its model-facing keys and labels.
    renderer_artifact = json.loads(json.dumps(artifact))
    for case in renderer_artifact["cases"].values():
        for brand in case["per_brand"].values():
            for field in brand["fields"].values():
                field["sol"] = field.pop("deepseek")
        promotion = case["post_level"]["untracked_brand_promotions"]
        promotion["sol"] = promotion.pop("deepseek")
    renderer_result = {"actual_billed_usd": result["peak_cost_usd"]}
    page = shared.render_html(renderer_artifact, owner, sources, renderer_result)
    page = page.replace("Owner vs Sol", "Owner vs DeepSeek V4.1 Flash").replace("owner review vs GPT-5.6 Sol", "owner review vs DeepSeek V4.1 Flash").replace("Sol answers are always red", "DeepSeek answers are always red").replace("Red = Sol", "Red = DeepSeek V4.1 Flash").replace("<small>SOL</small>", "<small>DEEPSEEK V4.1 FLASH</small>").replace("Sol API cost", "DeepSeek peak-rate estimate")
    page = page.replace('<div class="legend">', '<p><strong>Strict-run issue:</strong> DeepSeek assigned China national stance without the required nationalistic_stance mode on L45-21. The page preserves those contradictory raw fields. The shown cost excludes one original response lost before persistence during diagnosis.</p><div class="legend">', 1)
    html_path.write_text(page, encoding="utf-8")
    dump(PRIVATE / "comparison-artifacts.json", {"html": str(html_path), "json": str(json_path)})
    print(json.dumps({"html": str(html_path), "json": str(json_path), "counts": counts, "peak_cost_usd": result["peak_cost_usd"], "offpeak_cost_usd": result["offpeak_cost_usd"]}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "run", "compare"))
    args = parser.parse_args()
    {"prepare": prepare, "run": run, "compare": compare}[args.command]()


if __name__ == "__main__":
    main()
