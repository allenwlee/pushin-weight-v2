"""Prepare only independently valid arms; preserve every excluded case/error."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("frozen_experiment", HERE / "run.py")
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)
from x_monitor.attribution import _two_role_parse_fixed_slots

cases, contracts = run.payload_parts()
parsed = {}
bases = {}
raw_decisions = {}
issues = []
invalid_rows = []
for index, item in enumerate(run.read("deepseek-requests.json")):
    receipt = run.read(f"deepseek-events/finished_{index}.json")["value"]
    assert receipt["http_status"] == 200
    response = json.loads(receipt["raw_body"])
    assert response["model"] == run.DS_MODEL
    choice = response["choices"][0]
    assert choice["finish_reason"] == "stop"
    content = choice["message"]["content"].strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content)
    value = json.loads(content)
    explanation = value.pop("decision_basis", None)
    role = item["role"]
    contract = contracts[role]
    raw_decisions[item["id"]] = deepcopy(value)
    rows = _two_role_parse_fixed_slots(value, contract, role, request_profile="deepseek_0731")
    parsed[item["id"]] = rows
    for case in cases:
        if case["post_id"] not in rows:
            invalid_rows.append({"request_id": item["id"], "case_id": case["case_id"]})
    if item["arm"] == "baseline":
        assert explanation is None and len(rows) == len(cases)
        continue
    required = {"advertising_marketing"} if role == "content" else {
        "geopolitical_modes", "china_national_stance", "us_national_stance"}
    assert isinstance(explanation, dict) and set(explanation) == set(contract[1])
    bases[role] = {}
    for slot, (post_id, _) in contract[1].items():
        case = next(c for c in cases if c["post_id"] == post_id)
        fields = explanation[slot]
        visible = [case["source_text"], case["english_translation"]] + [c.get("text", "") for c in case["context"]]
        bad = []
        if not isinstance(fields, dict) or set(fields) != required:
            bad.append("field_coverage")
        else:
            for field, record in fields.items():
                if not isinstance(record, dict) or set(record) != {"claim", "evidence"}:
                    bad.append(field + ":shape")
                    continue
                if not isinstance(record["claim"], str) or not record["claim"].strip() or len(record["claim"].split()) > 35:
                    bad.append(field + ":claim")
                if not isinstance(record["evidence"], list) or len(record["evidence"]) > 2:
                    bad.append(field + ":evidence_shape")
                    continue
                for quote in record["evidence"]:
                    if not isinstance(quote, str) or not quote or len(quote) > 240 or not any(quote in text for text in visible):
                        bad.append(field + ":nonverbatim_quote")
        if bad:
            issues.append({"case_id": case["case_id"], "role": role, "errors": bad})
        else:
            bases[role][post_id] = fields

decisions = {arm: {} for arm in ("baseline", "justified")}
for arm in decisions:
    for case in cases:
        post_id = case["post_id"]
        brand = case["brand_ids"][0]
        content = parsed[f"{arm}_content"].get(post_id)
        geo = parsed[f"{arm}_brand_interpretation"].get(post_id)
        if content and geo:
            decisions[arm][case["case_id"]] = {**content["by_brand"][brand], **geo["by_brand"][brand]}
run.save("deepseek-parsed.json", {"decisions": decisions, "basis_by_role": bases,
         "basis_issues": issues, "invalid_rows": invalid_rows,
         "parsed_by_role": parsed, "raw_by_role": raw_decisions})

manifest = []
omitted = []
for index, case in enumerate(cases):
    order = run.ARMS[index % 3:] + run.ARMS[:index % 3]
    for arm in order:
        if arm != "A_label_only":
            if case["issue"] == "promotion":
                omitted.append({"case_id": case["case_id"], "arm": arm,
                                "reason": "promotion_basis_invalid_paired_comparison_unavailable"})
                continue
            if case["case_id"] not in decisions["justified"] or case["post_id"] not in bases["brand_interpretation"]:
                omitted.append({"case_id": case["case_id"], "arm": arm,
                                "reason": "geo_decision_or_basis_invalid"})
                continue
        candidate = decisions["baseline" if arm == "A_label_only" else "justified"][case["case_id"]]
        state = {"source": {k: case[k] for k in ("source_text", "source_language", "english_translation", "context", "author_handle", "author_affiliations")},
                 "target_brand": case["brand_ids"][0], "candidate_assignment": candidate}
        if arm == "B_basis_visible":
            state["decision_basis"] = bases["brand_interpretation"][case["post_id"]]
        body = {"model": run.JV_MODEL, "state": state, "questions": run.questions(case, candidate)}
        manifest.append({"id": case["case_id"] + "_" + arm, "case_id": case["case_id"], "arm": arm,
                         "request": body, "sha256": run.sha(body)})
for case in cases:
    b = next((m for m in manifest if m["case_id"] == case["case_id"] and m["arm"] == "B_basis_visible"), None)
    if b:
        c = next(m for m in manifest if m["case_id"] == case["case_id"] and m["arm"] == "C_basis_hidden")
        clean = deepcopy(b["request"])
        clean["state"].pop("decision_basis")
        assert clean == c["request"]
assert len(manifest) <= 16 and len(manifest) + len(omitted) == 24
run.save("jev-requests.json", manifest)
run.save("partial-coverage.json", {"prepared_at": run.now(), "planned_case_arms": 24,
         "available_case_arms": len(manifest), "omitted": omitted,
         "basis_issues": issues, "invalid_rows": invalid_rows,
         "new_call_cap": 32, "planned_physical_calls": 4 + len(manifest),
         "deviation_sha256": hashlib.sha256((HERE / "partial-comparison.md").read_bytes()).hexdigest(),
         "requests_sha256": run.sha(manifest)})
print(json.dumps({"available_requests": len(manifest), "omitted": omitted, "invalid_rows": invalid_rows,
                  "basis_errors": len(issues)}, indent=2))
