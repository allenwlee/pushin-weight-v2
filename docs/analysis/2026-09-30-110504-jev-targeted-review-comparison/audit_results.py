"""Provider-free integrity, coverage, and accounting checks for this one run."""
from collections import Counter
from copy import deepcopy
from decimal import Decimal
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("frozen_experiment", HERE / "run.py")
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)

preflight = run.read("preflight.json")
assert hashlib.sha256((HERE / "run.py").read_bytes()).hexdigest() == preflight["run_sha256"]
assert hashlib.sha256((HERE / "contract.md").read_bytes()).hexdigest() == preflight["contract_sha256"]
assert run.sha(run.read("cohort.json")) == preflight["cohort_sha256"]
assert all(hashlib.sha256((run.REPO / p).read_bytes()).hexdigest() == digest
           for p, digest in preflight["source_sha256"].items())
requests = run.read("deepseek-requests.json")
assert run.sha(requests) == preflight["requests_sha256"]
parsed = run.read("deepseek-parsed.json")
cases, contracts = run.payload_parts()
normalizations = []
for item in requests:
    contract = contracts[item["role"]]
    for slot, (post_id, brand) in contract[1].items():
        if post_id not in parsed["parsed_by_role"][item["id"]]:
            continue
        raw = parsed["raw_by_role"][item["id"]]["decisions"][slot]
        accepted = parsed["parsed_by_role"][item["id"]][post_id]["by_brand"][brand]
        if raw != accepted:
            normalizations.append({"request_id": item["id"], "slot": slot,
                                   "raw": raw, "accepted": accepted})

reviews = run.read("jev-requests.json")
coverage = run.read("partial-coverage.json")
assert run.sha(reviews) == coverage["requests_sha256"]
assert hashlib.sha256((HERE / "partial-comparison.md").read_bytes()).hexdigest() == coverage["deviation_sha256"]
assert len(reviews) == 16 and len(coverage["omitted"]) == 8
assert Counter(r["arm"] for r in reviews) == {"A_label_only": 8, "B_basis_visible": 4, "C_basis_hidden": 4}
for case in cases:
    if case["issue"] != "geopolitics":
        continue
    b = next(r for r in reviews if r["case_id"] == case["case_id"] and r["arm"] == "B_basis_visible")
    c = next(r for r in reviews if r["case_id"] == case["case_id"] and r["arm"] == "C_basis_hidden")
    clean = deepcopy(b["request"])
    clean["state"].pop("decision_basis")
    assert clean == c["request"]
for item in reviews:
    assert run.sha(item["request"]) == item["sha256"]
    assert set(item["request"]["state"]) <= {"source", "target_brand", "candidate_assignment", "decision_basis"}
    assert set(item["request"]["state"]["source"]) == {
        "source_text", "source_language", "english_translation", "context", "author_handle", "author_affiliations"}

scores = run.read("scores.json")
assert len(scores["rows"]) == 58
assert len({(r["case_id"], r["arm"], r["field"]) for r in scores["rows"]}) == 58
for row in scores["rows"]:
    item = next(r for r in reviews if r["case_id"] == row["case_id"] and r["arm"] == row["arm"])
    receipt = run.read(f"jev/{item['id']}-attempt-1-response.json")
    probability = json.loads(receipt["raw_body"])["answers"][row["field"]]["noul"]
    assert probability == row["p_correct"]
    expected_verdict = "approve" if probability >= .8 else "reject" if probability <= .2 else "uncertain"
    assert expected_verdict == row["verdict"]
    assert row["candidate_correct"] == (row["expected"] == row["assigned"])

costs = {}
ds_total = Decimal(0)
for index, item in enumerate(requests):
    receipt = run.read(f"deepseek-events/finished_{index}.json")["value"]
    data = json.loads(receipt["raw_body"])
    assert receipt["http_status"] == 200 and data["model"] == run.DS_MODEL
    usage = data["usage"]
    assert usage["completion_tokens_details"]["reasoning_tokens"] == 0
    cost = Decimal(str(usage["estimated_cost"]))
    ds_total += cost
    row = costs.setdefault(item["arm"], {"calls": 0, "input_tokens": 0, "output_tokens": 0,
                                        "provider_reported_estimated_cost_usd": Decimal(0), "serial_elapsed_seconds": 0})
    row["calls"] += 1
    row["input_tokens"] += usage["prompt_tokens"]
    row["output_tokens"] += usage["completion_tokens"]
    row["provider_reported_estimated_cost_usd"] += cost
    row["serial_elapsed_seconds"] += receipt["elapsed_seconds"]
assert ds_total == Decimal(run.read("deepseek-events/complete.json")["value"]["cost_usd"])
for value in costs.values():
    value["provider_reported_estimated_cost_usd"] = str(value["provider_reported_estimated_cost_usd"])
jv_total = Decimal(0)
jv_times = []
jv_by_arm = {}
question_count = 0
for item in reviews:
    receipt = run.read(f"jev/{item['id']}-attempt-1-response.json")
    data = json.loads(receipt["raw_body"])
    assert receipt["http_status"] == 200 and data["model"] == run.JV_MODEL
    assert set(data["answers"]) == set(item["request"]["questions"])
    account = run.read(f"jev/{item['id']}-attempt-1-accounting.json")
    jv_total += Decimal(account["list_price_estimate_usd"])
    jv_times.append(receipt["elapsed_seconds"])
    row = jv_by_arm.setdefault(item["arm"], {"calls": 0, "input_tokens": 0, "output_tokens": 0})
    row["calls"] += 1
    row["input_tokens"] += data["usage"]["input_tokens"]
    row["output_tokens"] += data["usage"]["output_tokens"]
    question_count += len(data["answers"])
assert jv_total == Decimal(run.read("jev-complete.json")["estimated_cost_plus_failed_reservations_usd"])
assert len(list((HERE / "jev").glob("*-started.json"))) == 16
assert len(list((HERE / "deepseek-events").glob("started_*.json"))) == 4
assert ds_total + jv_total < Decimal(1)

planned_summary = deepcopy(scores["summary"])
for arm, groups in planned_summary.items():
    for issue, result in groups.items():
        result["planned_fields"] = 18 if issue == "geopolitics" else 4
        result["unavailable_before_review"] = result["planned_fields"] - result["fields"]
run.save("audit.json", {"status": "partial_comparison_complete_no_more_calls", "audited_at": run.now(),
    "frozen_inputs_runner_and_application_sources_unchanged": True,
    "paired_geo_requests_differ_only_by_basis": True,
    "raw_decision_normalizations": normalizations,
    "planned_field_summary_including_unavailable": planned_summary,
    "real_posts": 7, "synthetic_posts": 1, "physical_model_calls": 20,
    "jev_questions_answered": question_count, "scored_field_reviews": len(scores["rows"]),
    "deepseek_by_arm": costs, "jev_by_arm": jv_by_arm,
    "deepseek_provider_reported_estimated_usd": str(ds_total),
    "jev_list_price_estimate_usd": str(jv_total),
    "combined_estimated_model_cost_usd": str(ds_total+jv_total),
    "jev_latency_seconds": {"min": min(jv_times), "median": statistics.median(jv_times), "max": max(jv_times)}})
print(json.dumps(run.read("audit.json"), indent=2))
