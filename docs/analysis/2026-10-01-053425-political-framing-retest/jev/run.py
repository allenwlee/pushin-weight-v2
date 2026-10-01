"""Single-pass TypeSafe Jev arm for the frozen political-framing retest."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import statistics
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
COMMON = HERE.parent
PRIOR_DIR = ROOT / "docs/analysis/2026-09-30-070427-jev-multilingual-classification"
VALIDATOR = ROOT / "docs/analysis/2026-09-30-060237-jev-primary-classifier/run.py"
MODEL = "jev-1.13.0"
PRICE_PER_MILLION_INPUT = Decimal("0.042")
MAX_CALLS = 117
MAX_SPEND = Decimal("0.25")
MAX_SECONDS = 3600
ENV_FILE = ROOT / ".env"


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode()


def sha(value):
    return hashlib.sha256(encode(value)).hexdigest()


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(path.read_text())


def save(name, value):
    path = HERE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    assert read(path) == value


def load_validator():
    spec = importlib.util.spec_from_file_location("jev_frozen_validator", VALIDATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def decode_response(data, request):
    validator = load_validator()
    answers = data.get("answers", {})
    if not isinstance(answers, dict):
        answers = {}
    rows = {}
    for field, question in request["questions"].items():
        try:
            if data.get("model") != MODEL or field not in answers:
                raise ValueError("model_or_field_missing")
            parsed = validator.decode_answers(
                {"model": data["model"], "answers": {field: answers[field]}},
                {"questions": {field: question}},
            )[field]
            rows[field] = {"valid": True, **parsed}
        except (AssertionError, KeyError, TypeError, ValueError):
            rows[field] = {"valid": False, "assigned": None,
                           "error": "invalid_or_missing_field",
                           "raw_answer": answers.get(field)}
    return rows, sorted(set(answers) - set(request["questions"]))


def plan_reservations(requests, cap=MAX_SPEND):
    # Match the prior Jev runner's conservative one-call reserve. Sequential
    # completed calls release this reserve into known usage; uncertain calls
    # retain it and stop the run.
    reservations = [Decimal((len(encode(item["request"])) + 4096) * 2)
                    * PRICE_PER_MILLION_INPUT / Decimal(1000000) for item in requests]
    total = sum(reservations, Decimal(0))
    if any(reservation > cap for reservation in reservations):
        raise ValueError("single_call_reservation_exceeded_no_calls")
    return reservations, total


def guard_budget(actual_spend, next_reservation, cap=MAX_SPEND):
    if actual_spend + next_reservation > cap:
        raise ValueError("spend_reservation_stop_no_retry")


def post_once(item, body, key, reservation, connection_factory,
              receipt_writer, error_writer):
    connection = connection_factory("api.typesafe.ai", timeout=25)
    started = time.monotonic()
    try:
        connection.request("POST", "/v1/systemone", body=body,
                           headers={"Authorization": "Bearer " + key,
                                    "Content-Type": "application/json"})
        response = connection.getresponse()
        raw = response.read(2000001).decode("utf-8")
        assert len(raw) <= 2000000
        status = response.status
    except Exception as exc:
        error_writer({"at": now(), "error_type": type(exc).__name__,
                      "completion": "unknown",
                      "retained_reservation_usd": str(reservation)})
        raise SystemExit("transport_error_stop_no_retry") from None
    finally:
        connection.close()
    receipt = {"at": now(), "status": status,
               "elapsed_seconds": time.monotonic() - started,
               "raw_body": raw.replace(key, "[REDACTED]")}
    receipt_writer(receipt)
    return receipt


def load_key():
    key = os.environ.get("TYPESAFE_API_KEY")
    if key:
        return key, "inherited environment"
    if not ENV_FILE.is_file():
        return None, "missing"
    for line in ENV_FILE.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        name, sep, value = stripped.partition("=")
        if sep and name.strip() == "TYPESAFE_API_KEY":
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            if value:
                return value, "authoritative app .env"
    return None, "missing"


def old_raw_requests():
    previous = read(PRIOR_DIR / "requests.json")
    return [item for item in previous if item["arm"] == "raw"]


def verify_common_manifest():
    spec = importlib.util.spec_from_file_location("political_retest_prepare", COMMON / "prepare.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.verify()


def validate_shared_inputs():
    frozen = verify_common_manifest()
    requests = read(COMMON / "requests.json")
    references = read(COMMON / "references.json")
    questions = read(COMMON / "questions.json")
    assert len(requests) == MAX_CALLS
    assert len(questions) == 38
    assert len(references["references"]) == MAX_CALLS
    assert all(item["arm"] == "raw" for item in requests)

    prior_frozen = read(PRIOR_DIR / "frozen.json")
    for name, digest in prior_frozen["files"].items():
        assert file_sha(PRIOR_DIR / name) == digest, f"prior_frozen:{name}"
    old_requests = old_raw_requests()
    assert len(old_requests) == MAX_CALLS
    assert len(old_requests) == len(requests)
    assert [i["case_id"] for i in old_requests] == [i["case_id"] for i in requests]
    assert [i["request"]["state"] for i in old_requests] == [i["request"]["state"] for i in requests]
    assert references == read(PRIOR_DIR / "references.json")

    for item in requests:
        req = item["request"]
        assert item["sha256"] == sha(req), f"request_digest:{item['request_id']}"
        assert req["model"] == MODEL
        assert set(req) == {"model", "state", "questions"}
        assert req["questions"] == questions
        assert len(req["questions"]) == 38
        assert "source_text" in req["state"]
        assert "english_translation" not in req["state"]

    return frozen, requests, references, questions


def verify():
    runner_frozen = read(HERE / "runner-frozen.json")
    for path, expected in runner_frozen["common_files"].items():
        assert file_sha(COMMON / path) == expected, f"common_file:{path}"
    for path, expected in runner_frozen["protected_files"].items():
        assert file_sha(ROOT / path) == expected, f"protected_file:{path}"
    for path, expected in runner_frozen["baseline_files"].items():
        assert file_sha(ROOT / path) == expected, f"baseline_file:{path}"
    assert file_sha(Path(__file__)) == runner_frozen["runner_sha256"]
    assert file_sha(VALIDATOR) == runner_frozen["validator_sha256"]
    frozen, requests, references, questions = validate_shared_inputs()
    assert file_sha(COMMON / "frozen.json") == runner_frozen["common_frozen_sha256"]
    assert sha(requests) == runner_frozen["requests_sha256"]
    assert sha(references) == runner_frozen["references_sha256"]
    assert sha(questions) == runner_frozen["questions_sha256"]
    assert frozen["models"]["jev"] == MODEL
    return runner_frozen, requests, references, questions


def freeze_runner():
    frozen, requests, references, questions = validate_shared_inputs()
    manifest = {
        "created_at": now(),
        "model": MODEL,
        "endpoint": "https://api.typesafe.ai/v1/systemone",
        "max_physical_calls": MAX_CALLS,
        "max_spend_usd": str(MAX_SPEND),
        "max_duration_seconds": MAX_SECONDS,
        "concurrency": 1,
        "retry_policy": "none",
        "common_frozen_sha256": file_sha(COMMON / "frozen.json"),
        "common_files": {name: file_sha(COMMON / name) for name in
                          ("requests.json", "references.json", "questions.json", "frozen.json")},
        "requests_sha256": sha(requests),
        "references_sha256": sha(references),
        "questions_sha256": sha(questions),
        "protected_files": frozen["protected_files"],
        "baseline_files": frozen["baseline_files"],
        "runner_sha256": file_sha(Path(__file__)),
        "validator_sha256": file_sha(VALIDATOR),
        "planned_calls": len(requests),
        "fields_per_response": len(questions),
        "selfcheck_passed": selfcheck(),
        "credential_route": "inherited TYPESAFE_API_KEY or authoritative app .env",
        "provider_calls": 0,
    }
    save("runner-frozen.json", manifest)
    print(json.dumps({"frozen": True, "planned_calls": len(requests),
                      "fields_per_call": len(questions), "model": MODEL,
                      "request_sha256": manifest["requests_sha256"],
                      "credential_present": bool(load_key()[0]),
                      "credential_route": load_key()[1]}))


def selfcheck():
    validator = load_validator()
    validator.selfcheck()
    _, requests, _, questions = validate_shared_inputs()
    sample = requests[0]
    answers = {}
    for field, question in questions.items():
        if question["type"] == "noul":
            answers[field] = {"type": "noul", "noul": 0.5}
        else:
            selected = next(iter(question["criteria"]))
            answers[field] = {"type": "choice", "choice": selected,
                              "confidence": 1,
                              "probabilities": {key: int(key == selected)
                                                for key in question["criteria"]}}
    decoded, extra = decode_response({"model": MODEL, "answers": answers}, sample["request"])
    assert len(decoded) == 38
    assert not extra and all(decoded[field]["valid"] for field in decoded)
    broken = dict(answers)
    broken["china_national_stance"] = {"type": "choice", "choice": "bogus",
                                       "confidence": 1, "probabilities": {"bogus": 1}}
    try:
        parsed, _ = decode_response({"model": MODEL, "answers": broken}, sample["request"])
        assert parsed["china_national_stance"]["valid"] is False
        assert sum(row["valid"] for row in parsed.values()) == 37
    except (AssertionError, KeyError, TypeError, ValueError):
        raise
    # Fake a successful transport and make the raw receipt callback observable
    # before the parser consumes the provider body.
    class FakeResponse:
        status = 200

        def read(self, _limit):
            return encode({"model": MODEL, "answers": answers})

    class FakeConnection:
        def __init__(self, fail=False):
            self.calls = 0
            self.fail = fail

        def request(self, *_args, **_kwargs):
            self.calls += 1
            if self.fail:
                raise OSError("fixture_unknown_completion")

        def getresponse(self):
            return FakeResponse()

        def close(self):
            pass

    events = []
    conn = FakeConnection()
    receipt = post_once(sample, encode(sample["request"]), "fixture-key", Decimal("0.001"),
                        lambda *_args, **_kwargs: conn,
                        lambda record: events.append(("raw_receipt", record)),
                        lambda record: events.append(("error", record)))
    assert conn.calls == 1 and len(events) == 1 and events[0][0] == "raw_receipt"
    parsed, _ = decode_response(json.loads(receipt["raw_body"]), sample["request"])
    events.append(("parsed", parsed))
    assert [event[0] for event in events] == ["raw_receipt", "parsed"]

    # An uncertain transport result is recorded and cannot cause a retry.
    failed = FakeConnection(fail=True)
    failures = []
    try:
        post_once(sample, encode(sample["request"]), "fixture-key", Decimal("0.001"),
                  lambda *_args, **_kwargs: failed, lambda _record: None,
                  lambda record: failures.append(record))
    except SystemExit as exc:
        assert str(exc) == "transport_error_stop_no_retry"
    else:
        raise AssertionError("unknown_completion_did_not_stop")
    assert failed.calls == 1 and len(failures) == 1 and failures[0]["completion"] == "unknown"

    try:
        guard_budget(Decimal("0.249"), Decimal("0.002"))
    except ValueError as exc:
        assert str(exc) == "spend_reservation_stop_no_retry"
    else:
        raise AssertionError("next_call_budget_not_rejected")
    return True


def run():
    runner_frozen, requests, _, _ = verify()
    key, credential_route = load_key()
    if not key:
        raise SystemExit("missing_typesafe_credential_no_calls")
    assert runner_frozen["provider_calls"] == 0
    assert len(requests) <= MAX_CALLS
    assert not (HERE / "run-started.json").exists(), "run_marker_exists_never_resubmit"
    reservations, planned_reservation = plan_reservations(requests)
    save("run-started.json", {"at": now(),
                              "runner_frozen_sha256": file_sha(HERE / "runner-frozen.json"),
                              "planned_calls": len(requests),
                              "sum_of_sequential_reservations_usd": str(planned_reservation),
                              "credential_route": credential_route})
    started_all = time.monotonic()
    actual_spend = Decimal(0)
    input_tokens = output_tokens = 0
    durations = []
    for index, item in enumerate(requests):
        if time.monotonic() - started_all >= MAX_SECONDS:
            raise SystemExit("time_budget_stop_no_retry")
        stem = item["request_id"]
        started_path = HERE / "receipts" / f"{stem}-started.json"
        response_path = HERE / "receipts" / f"{stem}-response.json"
        assert not started_path.exists() and not response_path.exists(), "receipt_exists_never_resubmit"
        body = encode(item["request"])
        reservation = reservations[index]
        try:
            guard_budget(actual_spend, reservation)
        except ValueError as exc:
            raise SystemExit(str(exc)) from None
        save(f"receipts/{stem}-started.json", {
            "at": now(), "request_sha256": item["sha256"],
            "reservation_usd": str(reservation), "attempt": 1,
        })
        # The raw provider receipt is durably appended before parsing/scoring.
        receipt = post_once(item, body, key, reservation,
                            http.client.HTTPSConnection,
                            lambda record: save(f"receipts/{stem}-response.json", record),
                            lambda record: save(f"receipts/{stem}-error.json", record))
        status = receipt["status"]
        if status != 200:
            raise SystemExit("provider_http_error_stop_no_retry")
        data = json.loads(receipt["raw_body"])
        if data.get("model") != MODEL:
            raise SystemExit("unexpected_model_stop_no_retry")
        parsed, extra = decode_response(data, item["request"])
        usage = data["usage"]
        for token_field in ("input_tokens", "output_tokens"):
            amount = usage[token_field]
            assert isinstance(amount, int) and not isinstance(amount, bool) and amount >= 0
        cost = Decimal(usage["input_tokens"]) * PRICE_PER_MILLION_INPUT / Decimal(1000000)
        assert cost <= reservation
        input_tokens += usage["input_tokens"]
        output_tokens += usage["output_tokens"]
        durations.append(receipt["elapsed_seconds"])
        save(f"receipts/{stem}-accounting.json", {
            "usage": usage, "estimated_input_cost_usd": str(cost),
            "provider_invoice_usd": None,
            "invalid_fields": [field for field, row in parsed.items() if not row["valid"]],
            "valid_fields": len(parsed) - sum(not row["valid"] for row in parsed.values()),
            "extra_fields": extra,
        })
        actual = Decimal(input_tokens) * PRICE_PER_MILLION_INPUT / Decimal(1000000)
        if actual > MAX_SPEND:
            raise SystemExit("reported_spend_stop_no_retry")
        actual_spend = actual
        if (index + 1) % 10 == 0 or index + 1 == len(requests):
            print(json.dumps({"completed": index + 1, "planned": len(requests),
                              "estimated_input_cost_usd": str(actual),
                              "next_reservation_usd": str(reservations[index + 1]) if index + 1 < len(reservations) else None,
                              "elapsed_seconds": round(time.monotonic() - started_all, 2)}),
                  flush=True)
    save("complete.json", {
        "at": now(), "calls": len(requests), "estimated_input_cost_usd": str(
            Decimal(input_tokens) * PRICE_PER_MILLION_INPUT / Decimal(1000000)),
        "sum_of_sequential_reservations_usd": str(planned_reservation), "input_tokens": input_tokens,
        "output_tokens": output_tokens, "median_seconds": statistics.median(durations),
        "elapsed_seconds": time.monotonic() - started_all, "retry_calls": 0,
    })


def score():
    runner_frozen, requests, references, _ = verify()
    complete = read(HERE / "complete.json")
    assert complete["calls"] == len(requests)
    validator = load_validator()
    rows = []
    for item in requests:
        receipt = read(HERE / "receipts" / f"{item['request_id']}-response.json")
        assert receipt["status"] == 200
        data = json.loads(receipt["raw_body"])
        decoded, _ = decode_response(data, item["request"])
        expected = references["references"][item["case_id"]]["expected"]
        for field, answer in decoded.items():
            rows.append({"request_id": item["request_id"], "case_id": item["case_id"],
                         "language": item["language"], "stratum": item["stratum"],
                         "field": field, "family": field.split(":", 1)[0],
                         "expected": expected[field], **answer,
                         "correct": answer["valid"] and answer["assigned"] == expected[field]})
    assert len(rows) == MAX_CALLS * 38
    geo_fields = ("geo:reporting", "geo:framework", "geo:nationalism",
                  "china_national_stance", "us_national_stance")
    geo_mode_fields = geo_fields[:3]

    def summarize(subset):
        valid = [r for r in subset if r["valid"]]
        summary = {"fields": len(subset), "valid": len(valid), "invalid": len(subset) - len(valid),
                "correct_valid": sum(r["correct"] for r in valid),
                "accuracy_valid_only": sum(r["correct"] for r in valid) / len(valid) if valid else None,
                "accuracy_invalid_as_wrong": sum(r["correct"] for r in subset) / len(subset) if subset else None}
        if subset and isinstance(subset[0]["expected"], bool):
            tp = sum(r["valid"] and r["assigned"] is True and r["expected"] is True for r in subset)
            fp = sum(r["valid"] and r["assigned"] is True and r["expected"] is False for r in subset)
            fn = sum(r["expected"] is True and not (r["valid"] and r["assigned"] is True) for r in subset)
            tn = sum(r["valid"] and r["assigned"] is False and r["expected"] is False for r in subset)
            summary.update(tp=tp, fp=fp, fn_invalid_included=fn, tn=tn,
                           precision=tp / (tp + fp) if tp + fp else None,
                           recall_invalid_included=tp / (tp + fn) if tp + fn else None)
        return summary

    geo_rows = {field: summarize([r for r in rows if r["field"] == field]) for field in geo_fields}
    geo_mode_cases = []
    for case_id in sorted({r["case_id"] for r in rows}):
        case_rows = {r["field"]: r for r in rows if r["case_id"] == case_id}
        geo_mode_cases.append({"case_id": case_id,
                               "exact_three_mode_match": all(
                                   case_rows[field]["valid"] and case_rows[field]["correct"]
                                   for field in geo_mode_fields),
                               "invalid_modes": [field for field in geo_mode_fields
                                                 if not case_rows[field]["valid"]],
                               "wrong_valid_modes": [field for field in geo_mode_fields
                                                     if case_rows[field]["valid"] and not case_rows[field]["correct"]]})
    result = {
        "arm": "jev", "model": MODEL, "cases": MAX_CALLS,
        "all_fields": summarize(rows), "geo_fields": geo_rows,
        "geo_combined": summarize([r for r in rows if r["field"] in geo_fields]),
        "geo_three_mode_exact_match": {
            "exact_cases": sum(r["exact_three_mode_match"] for r in geo_mode_cases),
            "total_cases": len(geo_mode_cases),
            "cases": geo_mode_cases,
        },
        "output_failures": [r for r in rows if not r["valid"]],
        "valid_disagreements": [r for r in rows if r["valid"] and not r["correct"]],
        "rows": rows,
        "audit": {"frozen_inputs_verified": True, "protected_files_unchanged": True,
                  "baseline_files_unchanged": True, "raw_receipts_before_scoring": True,
                  "physical_calls": complete["calls"], "retry_calls": 0,
                  "max_physical_calls": runner_frozen["max_physical_calls"],
                  "max_spend_usd": runner_frozen["max_spend_usd"],
                  "estimated_input_cost_usd": complete["estimated_input_cost_usd"],
                  "provider_invoice_confirmed": False},
    }
    save("scores.json", result)
    save("disagreements.json", [row for row in rows if not row["correct"]])
    print(json.dumps({"all_fields": result["all_fields"], "geo_fields": geo_rows,
                      "geo_combined": result["geo_combined"],
                      "geo_three_mode_exact_match": {k: v for k, v in result["geo_three_mode_exact_match"].items() if k != "cases"},
                      "audit": result["audit"]}, indent=2))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("selfcheck", "freeze", "verify", "run", "score"))
    action = parser.parse_args().action
    if action == "selfcheck":
        print(json.dumps({"selfcheck_passed": selfcheck()}))
    elif action == "freeze":
        freeze_runner()
    elif action == "verify":
        print(json.dumps({"frozen_inputs_verified": bool(verify())}))
    else:
        globals()[action]()
