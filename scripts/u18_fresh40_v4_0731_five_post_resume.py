"""Resume R113 while preserving enum/cross-field errors as scored failures."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from typing import Any

from scripts import u18_fresh40_v4_0731_five_post as base
from scripts import u18_fresh40_v4_0731_adapted as adapted
from scripts import u18_fresh40_v4_0731_compare as first_attempt
from scripts import u18_fresh45_sol_compare as sol


def soft_array(value: Any, allowed: tuple[str, ...], exclusive: set[str], path: str, issues: list[dict[str, Any]]) -> None:
    if not isinstance(value, list):
        raise ValueError(path + " is not an array")
    if not value:
        issues.append({"path": path, "issue": "empty classification array"})
    if len(value) != len(set(map(str, value))):
        issues.append({"path": path, "issue": "duplicate label"})
    for label in value:
        if not isinstance(label, str) or label not in allowed:
            issues.append({"path": path, "issue": "invalid label", "value": label})
    if set(label for label in value if isinstance(label, str)) & exclusive and len(value) != 1:
        issues.append({"path": path, "issue": "exclusive sentinel combined with another label"})


def soft_parse(decoded: dict[str, Any], batch: list[dict[str, Any]], role: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
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
            raise ValueError(slot + " decision is not object")
        if role == "content":
            if set(value) != {"outcome", "post_types", "audience_topics"}:
                raise ValueError(slot + " content fields")
            if value["outcome"] not in ("classified", "context_missing"):
                issues.append({"path": slot + ".outcome", "issue": "invalid label", "value": value["outcome"]})
            soft_array(value["post_types"], sol.POST_TYPES, {"other"}, slot + ".post_types", issues)
            soft_array(value["audience_topics"], sol.TOPICS, {"none", "unavailable"}, slot + ".audience_topics", issues)
            if value["outcome"] == "classified" and not value["post_types"]:
                issues.append({"path": slot, "issue": "classified with no post type"})
            if value["outcome"] == "context_missing" and (value["post_types"] or value["audience_topics"] != ["unavailable"]):
                issues.append({"path": slot, "issue": "context_missing invariant"})
        else:
            expected = {"product_labels", "sentiment", "geopolitical_modes", "china_national_stance", "us_national_stance"}
            if set(value) != expected:
                raise ValueError(slot + " brand fields")
            soft_array(value["product_labels"], sol.PRODUCT_LABELS, {"none"}, slot + ".product_labels", issues)
            soft_array(value["geopolitical_modes"], sol.GEO, {"none", "unavailable"}, slot + ".geopolitical_modes", issues)
            for field, allowed in (("sentiment", sol.SENTIMENT), ("china_national_stance", sol.STANCE), ("us_national_stance", sol.STANCE)):
                if not isinstance(value[field], str) or value[field] not in allowed:
                    issues.append({"path": slot + "." + field, "issue": "invalid label", "value": value[field]})
            if "nationalistic_stance" not in value["geopolitical_modes"] and (value["china_national_stance"] != "none" or value["us_national_stance"] != "none"):
                issues.append({"path": slot, "issue": "national stance without nationalistic_stance mode"})
    if role == "content":
        for slot, value in parsed["post_promotions"].items():
            soft_array(value, sol.PROMOTIONS, {"general", "none"}, slot + ".post_promotions", issues)
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


def run_one(name: str, body: dict[str, Any], batch: list[dict[str, Any]], role: str, key: str) -> dict[str, Any]:
    decoded, measurement = sol.shared.transport(body, key, base.PRIVATE, name)
    measurement.update({"role": role, "case_count": len(batch)})
    if decoded is None:
        return {"name": name, "measurement": measurement, "error": "transport failed"}
    try:
        rows, issues = soft_parse(decoded, batch, role)
    except Exception as exc:
        return {"name": name, "measurement": measurement, "error": type(exc).__name__ + ": " + str(exc)}
    base.dump(base.PRIVATE / f"{name}-parsed.json", rows)
    measurement["semantic_issues"] = issues
    return {"name": name, "measurement": measurement, "rows": rows, "issues": issues}


def main() -> None:
    contract = base.verify()
    result_path = base.PRIVATE / "result.json"
    if result_path.exists():
        raise ValueError("result already exists")
    partial_path = base.PRIVATE / "partial-result.json"
    result = json.loads(partial_path.read_text(encoding="utf-8"))
    if len(result["roles"]["content"]) != 10 or len(result["roles"]["brand"]) != 15 or len(result["measurements"]) != 6:
        raise ValueError("unexpected R113 stop point")
    packets = json.loads((base.PRIVATE / "packets.json").read_text(encoding="utf-8"))
    packet_batches = base.batches(packets)
    requests = json.loads((base.PRIVATE / "requests.json").read_text(encoding="utf-8"))
    failed_raw = json.loads((base.PRIVATE / "3-content-raw-response.json").read_text(encoding="utf-8"))
    restored_rows, restored_issues = soft_parse(failed_raw, packet_batches[2], "content")
    base.dump(base.PRIVATE / "3-content-parsed-with-preserved-errors.json", restored_rows)
    result["roles"]["content"].extend(restored_rows)
    result["semantic_issues"].extend({"call": "3-content", **issue} for issue in restored_issues)
    for measurement in result["measurements"]:
        if measurement.get("batch") == 3 and measurement.get("role") == "content":
            measurement["semantic_issues"] = restored_issues
            measurement["accepted_for_diagnostic_scoring"] = True
    result["diagnostic_failures_preserved"] = result.pop("failures", [])
    key = sol.shared.secret()
    for index in range(3, len(packet_batches)):
        batch = packet_batches[index]
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {role: executor.submit(run_one, f"{index + 1}-{role}", requests[role][index], batch, role, key) for role in ("content", "brand")}
            outcomes = {role: futures[role].result() for role in ("content", "brand")}
        for role, outcome in outcomes.items():
            measurement = outcome["measurement"]
            measurement["batch"] = index + 1
            result["measurements"].append(measurement)
            if "error" in outcome:
                result.setdefault("failures", []).append({"call": outcome["name"], "error": outcome["error"]})
            else:
                result["roles"][role].extend(outcome["rows"])
                result["semantic_issues"].extend({"call": outcome["name"], **issue} for issue in outcome["issues"])
            print(json.dumps({"call": outcome["name"], "status": "failed" if "error" in outcome else "valid", "seconds": measurement["latency_ms"] / 1000, "usage": measurement.get("usage"), "semantic_issues": len(outcome.get("issues", [])), "error": outcome.get("error")}), flush=True)
        base.dump(partial_path, result)
        if result.get("failures"):
            raise RuntimeError("structural failure in resumed run")
    if len(result["roles"]["content"]) != 40 or len(result["roles"]["brand"]) != 40 or len(result["measurements"]) != 16:
        raise ValueError("completed result shape mismatch")
    result["completed_at"] = base.now()
    result["actual_billed_usd"] = str(sum(Decimal(str((row.get("usage") or {}).get("cost", 0))) for row in result["measurements"]))
    result["actual_billed_with_fee_usd"] = str(Decimal(result["actual_billed_usd"]) * base.FEE_FACTOR)
    rejected = sum(Decimal(str(row["cost_usd"])) for row in contract["rejected_calls_before_this_arm"])
    result["total_experiment_cost_with_rejected_calls_and_fee_usd"] = str((Decimal(result["actual_billed_usd"]) + rejected) * base.FEE_FACTOR)
    result["scoring_policy"] = "Preserve invalid enum and cross-field values as model output and score them as differences; never coerce or retry. Structural omissions still fail."
    base.dump(result_path, result)
    print(json.dumps({"result": str(result_path), "cost_usd": result["actual_billed_usd"], "cost_with_fee_usd": result["actual_billed_with_fee_usd"], "semantic_issues": len(result["semantic_issues"]), "calls": len(result["measurements"])}))


if __name__ == "__main__":
    main()
