"""Record invalid answers individually; never retry an existing physical attempt."""
from __future__ import annotations

import argparse
from decimal import Decimal
import http.client
import json
import os
import statistics
import time

import run as base


def decode_partial(data, request):
    assert data["model"] == base.MODEL
    assert set(data["answers"]) == set(request["questions"])
    result = {}
    for field, question in request["questions"].items():
        try:
            row = base.decode_answers(
                {"model": data["model"], "answers": {field: data["answers"][field]}},
                {"questions": {field: question}},
            )[field]
        except (AssertionError, KeyError, TypeError, ValueError):
            row = {"assigned": None, "valid": False,
                   "validation_error": "answer_violates_frozen_response_contract"}
        else:
            row["valid"] = True
        result[field] = row
    return result


def check_continuation():
    base.verify_frozen()
    frozen = base.read(base.HERE / "continuation-frozen.json")
    for name, digest in frozen["files"].items():
        assert base.file_sha(base.HERE / name) == digest


def prepare():
    base.verify_frozen()
    starts = sorted(p.stem.removesuffix("-started") for p in (base.HERE / "receipts").glob("*-started.json"))
    assert starts == ["G01", "G02", "G03"]
    requests = base.read(base.HERE / "requests.json")
    example = next(r for r in requests if r["case_id"] == "G03")
    raw = json.loads(base.read(base.HERE / "receipts/G03-response.json")["raw_body"])
    decoded = decode_partial(raw, example["request"])
    assert not decoded["us_national_stance"]["valid"]
    assert all(v["valid"] for k, v in decoded.items() if k != "us_national_stance")
    base.save("continuation-frozen.json", {
        "at": base.now(), "already_submitted": starts, "remaining_calls": 5,
        "files": {n: base.file_sha(base.HERE / n) for n in ("continuation.md", "continue_run.py")},
        "existing_receipts": {p.name: base.file_sha(p) for p in (base.HERE / "receipts").glob("*-response.json")},
        "field_local_validation_checked": True,
    })
    print(json.dumps({"continuation_prepared": True, "remaining_calls": 5, "total_call_cap": 8}))


def run():
    check_continuation()
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key:
        raise SystemExit("missing_typesafe_credential_no_calls")
    base.save("continuation-started.json", {"at": base.now()})
    spent = Decimal(0)
    requests = base.read(base.HERE / "requests.json")
    assert len(requests) == 8
    for item in requests:
        stem = "receipts/" + item["case_id"]
        response_path = base.HERE / (stem + "-response.json")
        if response_path.exists():
            receipt = base.read(response_path)
        else:
            # An existing start with no receipt is ambiguous; never send again.
            assert not (base.HERE / (stem + "-started.json")).exists()
            assert len(list((base.HERE / "receipts").glob("*-started.json"))) < 8
            body = base.encode(item["request"])
            assert base.sha(item["request"]) == item["sha256"]
            reserve = Decimal((len(body) + 4096) * 2) * base.PRICE / Decimal(1000000)
            assert spent + reserve <= base.LIMIT
            base.save(stem + "-started.json", {"at": base.now(), "request_sha256": item["sha256"], "reservation_usd": str(reserve)})
            started = time.monotonic()
            connection = http.client.HTTPSConnection("api.typesafe.ai", timeout=30)
            try:
                connection.request("POST", "/v1/systemone", body=body,
                                   headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
                response = connection.getresponse()
                raw = response.read(1000001).decode()
                assert len(raw) <= 1000000
                status = response.status
            except Exception as exc:
                base.save(stem + "-error.json", {"error_type": type(exc).__name__, "completion": "unknown", "retained_reservation_usd": str(reserve)})
                raise SystemExit("transport_error_stop_no_retry") from None
            finally:
                connection.close()
            receipt = {"at": base.now(), "status": status,
                       "elapsed_seconds": time.monotonic() - started,
                       "raw_body": raw.replace(key, "[REDACTED]")}
            base.save(stem + "-response.json", receipt)
        if receipt["status"] != 200:
            raise SystemExit("provider_http_error_stop_no_retry")
        data = json.loads(receipt["raw_body"])
        decoded = decode_partial(data, item["request"])
        usage = data["usage"]
        for field in ("input_tokens", "output_tokens"):
            assert isinstance(usage[field], int) and not isinstance(usage[field], bool) and usage[field] >= 0
        cost = Decimal(usage["input_tokens"]) * base.PRICE / Decimal(1000000)
        start_receipt = base.read(base.HERE / (stem + "-started.json"))
        assert cost <= Decimal(start_receipt["reservation_usd"])
        spent += cost
        assert spent <= base.LIMIT
        if not (base.HERE / (stem + "-accounting.json")).exists():
            base.save(stem + "-accounting.json", {"usage": usage, "estimated_usd": str(cost), "provider_invoice_usd": None})
        print(json.dumps({"completed": item["case_id"], "invalid_fields": [k for k, v in decoded.items() if not v["valid"]]}), flush=True)
    base.save("complete.json", {"at": base.now(), "calls": 8, "estimated_usd": str(spent), "continuation": "field_local_validation"})


def score():
    check_continuation()
    cases = {c["case_id"]: c for c in base.read(base.HERE / "cohort.json")["cases"]}
    rows, unscored, invalid, inconsistencies, times = [], [], [], [], []
    inputs = outputs = 0
    for item in base.read(base.HERE / "requests.json"):
        case = cases[item["case_id"]]
        receipt = base.read(base.HERE / ("receipts/" + case["case_id"] + "-response.json"))
        assert receipt["status"] == 200
        data = json.loads(receipt["raw_body"])
        answers = decode_partial(data, item["request"])
        times.append(receipt["elapsed_seconds"])
        inputs += data["usage"]["input_tokens"]
        outputs += data["usage"]["output_tokens"]
        for field, answer in answers.items():
            expected = base.expected_value(case, field)
            row = {"case_id": case["case_id"], "issue": case["issue"], "field": field,
                   "expected": expected, **answer,
                   "correct": answer["valid"] and answer["assigned"] == expected if expected is not None else None}
            (rows if expected is not None else unscored).append(row)
            if not answer["valid"]:
                invalid.append({"case_id": case["case_id"], "field": field, "scored": expected is not None,
                                "raw_answer": data["answers"][field]})
        if case["issue"] == "geopolitics":
            directional = any(answers[f]["valid"] and answers[f]["assigned"] not in {"none", "unknown"}
                              for f in ("china_national_stance", "us_national_stance"))
            if directional and answers["nationalism"]["valid"] and not answers["nationalism"]["assigned"]:
                inconsistencies.append({"case_id": case["case_id"], "problem": "directional_stance_without_nationalism"})
    assert len(rows) == 22 and len(unscored) == 2
    assert len(list((base.HERE / "receipts").glob("*-started.json"))) == 8
    assert len(list((base.HERE / "receipts").glob("*-response.json"))) == 8
    cost = Decimal(inputs) * base.PRICE / Decimal(1000000)
    assert cost == Decimal(base.read(base.HERE / "complete.json")["estimated_usd"]) <= base.LIMIT
    prior_receipts = base.read(base.HERE / "continuation-frozen.json")["existing_receipts"]
    for name, digest in prior_receipts.items():
        assert base.file_sha(base.HERE / "receipts" / name) == digest
    result = {
        "summary": base.summarize(rows), "rows": rows, "unscored": unscored,
        "invalid_answers": invalid, "inconsistencies": inconsistencies,
        "sensitivity_excluding_G03_stance_intensity": base.summarize([r for r in rows if not (r["case_id"] == "G03" and r["field"] == "china_national_stance")]),
        "usage": {"calls": 8, "input_tokens": inputs, "output_tokens": outputs,
                  "estimated_usd": str(cost), "median_seconds": statistics.median(times),
                  "min_seconds": min(times), "max_seconds": max(times)},
        "audit": {"frozen_hashes_match": True, "protected_files_unchanged": True,
                  "prior_experiment_unchanged": True, "existing_receipts_unchanged": True,
                  "calls_and_cost_within_limits": True, "retries": 0,
                  "valid_scored_answers": sum(r["valid"] for r in rows),
                  "invalid_unscored_answers": sum(not r["valid"] for r in unscored)},
    }
    base.save("scores.json", result)
    print(json.dumps({"summary": result["summary"], "errors": [r for r in rows if not r["correct"]],
                      "invalid_answers": invalid, "usage": result["usage"], "audit": result["audit"]}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run", "score"))
    globals()[parser.parse_args().action]()
