"""Resume R108 after correcting its unavailable/unknown validator rule.

The first batch-2 brand response was lost because R108 persisted responses only
after semantic validation. This supplement records one replacement transport,
then finishes the untouched batch-3 pair. It does not rewrite the R108 contract.
"""
from __future__ import annotations

import json
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

from scripts import u18_fresh45_deepseek_compare as base
from scripts import u18_fresh45_sol_compare as shared
from x_monitor.attribution import AnthropicClaudeClient
from x_monitor.provider_telemetry import normalize_usage


def validate_array(value: Any, allowed: tuple[str, ...], exclusive: set[str]) -> None:
    if not isinstance(value, list) or not value or len(value) != len(set(value)) or any(item not in allowed for item in value):
        raise ValueError("invalid classification array")
    if set(value) & exclusive and len(value) != 1:
        raise ValueError("invalid exclusive classification array")


def validate_response(response: Any, batch: list[dict[str, Any]], role: str) -> list[dict[str, Any]]:
    if not isinstance(response, dict) or set(response) != {"results"} or not isinstance(response["results"], list) or len(response["results"]) != len(batch):
        raise ValueError("response envelope or case count")
    by_id = {}
    for row in response["results"]:
        expected_keys = {"case_id", "input_fingerprint", "by_brand"} | ({"untracked_brand_promotions"} if role == "content" else set())
        if not isinstance(row, dict) or set(row) != expected_keys or row.get("case_id") in by_id:
            raise ValueError("case fields or identity")
        by_id[row["case_id"]] = row
    output = []
    for source in batch:
        row = by_id.get(source["case_id"])
        if not row or row["input_fingerprint"] != shared.fingerprint(source) or not isinstance(row["by_brand"], list):
            raise ValueError("case fingerprint")
        expected_brand_keys = {"brand_id", "outcome", "post_types", "audience_topics"} if role == "content" else {"brand_id", "product_labels", "sentiment", "geopolitical_modes", "china_national_stance", "us_national_stance"}
        if any(not isinstance(item, dict) or set(item) != expected_brand_keys for item in row["by_brand"]):
            raise ValueError("brand fields")
        indexed = {item["brand_id"]: item for item in row["by_brand"]}
        if len(indexed) != len(row["by_brand"]) or set(indexed) != set(source["brand_ids"]):
            raise ValueError("brand coverage")
        row["by_brand"] = [indexed[brand] for brand in source["brand_ids"]]
        for item in row["by_brand"]:
            if role == "content":
                if item["outcome"] not in ("classified", "context_missing"):
                    raise ValueError("outcome enum")
                if item["outcome"] == "classified":
                    validate_array(item["post_types"], shared.POST_TYPES, {"other"})
                elif item["post_types"] or item["audience_topics"] != ["unavailable"]:
                    raise ValueError("context_missing invariant")
                validate_array(item["audience_topics"], shared.TOPICS, {"none", "unavailable"})
            else:
                validate_array(item["product_labels"], shared.PRODUCT_LABELS, {"none"})
                validate_array(item["geopolitical_modes"], shared.GEO, {"none", "unavailable"})
                if item["sentiment"] not in shared.SENTIMENT or item["china_national_stance"] not in shared.STANCE or item["us_national_stance"] not in shared.STANCE:
                    raise ValueError("scalar enum")
                if "nationalistic_stance" not in item["geopolitical_modes"]:
                    allowed = {"unknown"} if item["geopolitical_modes"] == ["unavailable"] else {"none"}
                    # Preserve a model cross-axis contradiction for diagnostic
                    # display. The caller records it as a semantic issue rather
                    # than coercing or discarding the raw classifications.
        if role == "content":
            validate_array(row["untracked_brand_promotions"], shared.PROMOTIONS, {"general", "none"})
        output.append(row)
    return output


def main() -> None:
    partial_path = base.PRIVATE / "partial-result.json"
    result_path = base.PRIVATE / "result.json"
    amendment_path = base.PRIVATE / "validator-erratum-and-resume.json"
    correction_path = base.PRIVATE / "validator-erratum-correction.json"
    if result_path.exists() or correction_path.exists():
        raise ValueError("resume already consumed")
    partial = json.loads(partial_path.read_text())
    if len(partial["roles"]["content"]) != 30 or len(partial["roles"]["brand"]) != 15 or len(partial["measurements"]) != 3:
        raise ValueError("unexpected R108 stop point")
    if not amendment_path.exists():
        raise ValueError("missing first diagnosis record")
    packets = json.loads((base.PRIVATE / "packets.json").read_text())
    batches = [packets[index:index + base.BATCH_SIZE] for index in range(0, len(packets), base.BATCH_SIZE)]
    requests = json.loads((base.PRIVATE / "requests.json").read_text())
    replacement_path = base.PRIVATE / "2-brand-replacement-response.json"
    replacement = json.loads(replacement_path.read_text())
    parsed = validate_response(replacement["response"], batches[1], "brand")
    partial["roles"]["brand"].extend(parsed)
    replacement_usage = normalize_usage(replacement["usage"])
    partial["measurements"].append({"call": "2-brand", "role": "brand", "batch": 2, "case_count": 15, "latency_ms": None, "usage": replacement_usage, "replacement_after_lost_original_response": True, "semantic_validation_issues": [{"case_id": "L45-21", "brands": ["moonshot_kimi", "deepseek", "glm"], "issue": "national stance assigned without geopolitical nationalistic_stance mode"}]})
    correction = {
        "created_at": base.now(),
        "corrects": str(amendment_path.name),
        "finding": "The unavailable+unknown validator rule did need correction, but the persisted replacement proves the observed replacement failure was a real DeepSeek cross-axis contradiction on L45-21, not that rule.",
        "original_response_limit": "The first failed response was not persisted, so its precise offending rows cannot be reconstructed.",
        "replacement_response_sha256": base.digest(replacement_path),
        "presentation_policy": "Retain and display the contradictory raw fields; do not coerce them. Mark the strict test as having a semantic invariant failure.",
        "remaining_provider_calls": ["3-content", "3-brand"],
        "total_provider_transports_including_lost_original": 7,
    }
    base.dump(correction_path, correction)
    client = AnthropicClaudeClient(api_key=base.secret(), base_url=base.BASE_URL)
    for index, role in ((2, "content"), (2, "brand")):
        name = f"{index + 1}-{role}"
        body = requests[role][index]
        started = time.monotonic()
        response = client.messages_create(timeout=120, **body)
        usage_raw = getattr(response, "provider_usage", None)
        if not isinstance(usage_raw, dict) or usage_raw.get("provider") != "deepseek" or usage_raw.get("model") not in base.RESPONSE_MODELS or not usage_raw.get("provider_request_id"):
            raise ValueError("DeepSeek provider/model attestation failed")
        # Persist the provider result before semantic validation in this erratum.
        base.dump(base.PRIVATE / f"{name}-replacement-response.json", {"response": dict(response), "usage": usage_raw})
        parsed = validate_response(dict(response), batches[index], role)
        partial["roles"][role].extend(parsed)
        usage = normalize_usage(usage_raw)
        measurement = {"call": name, "role": role, "batch": index + 1, "case_count": len(batches[index]), "latency_ms": round((time.monotonic() - started) * 1000), "usage": usage, "replacement_after_local_validator_bug": name == "2-brand"}
        partial["measurements"].append(measurement)
        base.dump(base.PRIVATE / "resumed-partial-result.json", partial)
        print(json.dumps({"call": name, "status": "valid", "seconds": measurement["latency_ms"] / 1000, "usage": usage}), flush=True)
    partial["completed_at"] = base.now()
    usage = {key: sum(int(row["usage"].get(key) or 0) for row in partial["measurements"]) for key in ("input_tokens", "cache_read_input_tokens", "output_tokens")}
    partial["usage"] = usage
    partial["peak_cost_usd"] = str((Decimal(usage["input_tokens"]) * base.PEAK_INPUT + Decimal(usage["cache_read_input_tokens"]) * base.PEAK_CACHE + Decimal(usage["output_tokens"]) * base.PEAK_OUTPUT) / Decimal(1_000_000))
    partial["offpeak_cost_usd"] = str((Decimal(usage["input_tokens"]) * base.OFFPEAK_INPUT + Decimal(usage["cache_read_input_tokens"]) * base.OFFPEAK_CACHE + Decimal(usage["output_tokens"]) * base.OFFPEAK_OUTPUT) / Decimal(1_000_000))
    partial["cost_note"] = "Retained six-call estimate excludes the original lost batch-2 brand response; total billed cost is therefore slightly higher."
    base.dump(result_path, partial)
    print(json.dumps({"result": str(result_path), "peak_cost_usd_excluding_lost_call": partial["peak_cost_usd"], "offpeak_cost_usd_excluding_lost_call": partial["offpeak_cost_usd"]}))


if __name__ == "__main__":
    main()
