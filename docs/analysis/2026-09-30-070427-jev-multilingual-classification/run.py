"""Append-only multilingual Jev diagnostic. No app imports or DB writes."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import http.client
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import statistics
import time

from questions import (
    TYPE_ALIASES, TOPIC_ALIASES, PRODUCT_ALIASES, build_questions,
)

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
MODEL = "jev-1.13.0"
PRICE = Decimal("0.042")
LIMIT = Decimal("0.50")
PROTECTED = (
    "config.yaml", "x_monitor/attribution.py", "x_monitor/classifier_0731_prompts.py",
    "tests/test_u18_runtime_0731.py", "tests/test_u18a_v4_classification_persistence.py",
)


def load(name):
    return json.loads((HERE / name).read_text())


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def file_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def save(name, value):
    path = HERE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


# Reuse the tested pure probability/Choice validator from the prior experiment.
spec = importlib.util.spec_from_file_location("jev_prior_pure", HERE.parent / "2026-09-30-060237-jev-primary-classifier/run.py")
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)


def decode(data, request):
    rows = {}
    answers = data.get("answers", {})
    if not isinstance(answers, dict):
        answers = {}
    for field, question in request["questions"].items():
        try:
            assert data.get("model") == MODEL
            raw = {"model": data["model"], "answers": {field: answers[field]}}
            parsed = prior.decode_answers(raw, {"questions": {field: question}})[field]
            rows[field] = {"valid": True, **parsed}
        except (AssertionError, KeyError, TypeError, ValueError):
            rows[field] = {"valid": False, "assigned": None, "error": "invalid_or_missing_field", "raw_answer": answers.get(field)}
    return rows, sorted(set(answers) - set(request["questions"]))


def references():
    questions = build_questions()
    result, excluded = {}, []
    for row in load("reference_rows.json"):
        assert len(row) == 10
        case, types, topics, products, sentiment, geo, cn, us, promotions, note = row
        assert case not in result
        if types == "EXCLUDE":
            excluded.append({"case_id": case, "reason": note})
            continue
        expected = {k: False for k, v in questions.items() if v["type"] == "noul"}
        expected.update(outcome="context_missing" if types == "MISSING" else "classified",
                        sentiment=sentiment, china_national_stance=cn, us_national_stance=us)
        for family, names, aliases in (("type", "" if types == "MISSING" else types, TYPE_ALIASES),
                                      ("topic", topics, TOPIC_ALIASES), ("product", products, PRODUCT_ALIASES)):
            for name in names.split():
                expected[family + ":" + aliases[name]] = True
        for family, names in (("geo", geo), ("promotion", promotions)):
            for name in names.split():
                expected[family + ":" + name] = True
        assert set(expected) == set(questions)
        for field, question in questions.items():
            if question["type"] == "choice":
                assert expected[field] in question["criteria"]
        result[case] = {"expected": expected, "note": note}
    return result, excluded


def catalog_for_case(case, catalog):
    # Keep every tracked brand/curated alias; include only source-visible product
    # candidates from the 1,804-row product catalog. No expected labels, human
    # target explanation, or English translation participates in this selector.
    normalize = lambda text: re.sub(r"[^\w]", "", str(text).casefold())
    visible = normalize(case["source_text"] + " " + " ".join(case["context"].values()))
    result = []
    for brand in catalog["brands"]:
        aliases = sorted({v.strip() for v in brand["names"] + brand["search_terms"] + brand["keywords"] if v and v.strip()})
        products = sorted({value for product in brand["products"] for value in (product["name"], product["repo_id"])
                           if value and len(normalize(value)) >= 4 and normalize(value) in visible})
        result.append({"brand_id": brand["brand_id"], "aliases": aliases,
                       "accounts": brand["accounts"], "hashtags": brand["hashtags"],
                       "source_matched_product_candidates": products})
    return result


def consistency(answers):
    value = lambda k: answers.get(k, {}).get("assigned")
    keys = [k for k in answers if value(k) is True]
    issues = []
    types = [k for k in keys if k.startswith("type:")]
    if "type:other" in types and len(types) > 1:
        issues.append("other_plus_specific_type")
    if value("outcome") == "classified" and not types:
        issues.append("classified_without_type")
    if value("outcome") == "context_missing" and any(k.startswith(("type:", "topic:", "product:", "geo:")) for k in keys):
        issues.append("missing_context_with_target_membership")
    if value("outcome") == "context_missing" and any(value(k) not in {"unknown", None} for k in ("sentiment", "china_national_stance", "us_national_stance")):
        issues.append("missing_context_with_assessed_scalar")
    if "promotion:general" in keys and any(k.startswith("promotion:") and k != "promotion:general" for k in keys):
        issues.append("general_plus_specific_promotion")
    directional = any(value(k) not in {"none", "unknown", None} for k in ("china_national_stance", "us_national_stance"))
    if directional and value("geo:nationalism") is not True:
        issues.append("directional_stance_without_nationalism")
    return issues


def selfcheck():
    prior.selfcheck()
    questions = build_questions()
    answers = {}
    for field, question in questions.items():
        if question["type"] == "noul":
            answers[field] = {"type": "noul", "noul": .49}
        else:
            choice = next(iter(question["criteria"]))
            answers[field] = {"type": "choice", "choice": choice, "confidence": 1,
                              "probabilities": {k: int(k == choice) for k in question["criteria"]}}
    data = {"model": MODEL, "answers": answers}
    parsed, extra = decode(data, {"questions": questions})
    assert len(parsed) == 38 and not extra and all(p["valid"] for p in parsed.values())
    data["answers"]["sentiment"]["choice"] = "negative"
    parsed, _ = decode(data, {"questions": questions})
    assert not parsed["sentiment"]["valid"] and sum(p["valid"] for p in parsed.values()) == 37
    assert consistency({"outcome": {"assigned": "classified"}}) == ["classified_without_type"]


def prepare():
    selfcheck()
    refs, excluded = references()
    cohort = load("cohort.json")
    envelope = load("catalog-render-result.json")["output"]
    catalog = next(json.loads(line) for line in envelope.split("\n") if line.startswith("{"))
    assert len(cohort["cases"]) == 120 and len(refs) == 117 and len(excluded) == 3
    assert {c["case_id"] for c in cohort["cases"]} == set(refs) | {e["case_id"] for e in excluded}
    questions = build_questions()
    requests = []
    for index, case in enumerate(cohort["cases"]):
        case_id = case["case_id"]
        if case_id not in refs:
            continue
        state = {"source_text": case["source_text"], "source_language": case["language"],
                 "context": case["context"], "author_handle": case["author_handle"],
                 "author_affiliations": case["author_affiliations"], "target_brand": case["target_brand"],
                 "tracked_brands": catalog_for_case(case, catalog)}
        arms = ["raw"]
        if case["language"] != "en" and case["english_translation"]:
            arms.append("translated")
        if index % 2:
            arms.reverse()
        for arm in arms:
            arm_state = dict(state)
            if arm == "translated":
                arm_state["english_translation"] = case["english_translation"]
            assert not {"case_id", "post_id", "expected", "note", "sampling_labels_not_gold", "stratum"} & set(arm_state)
            request = {"model": MODEL, "state": arm_state, "questions": questions}
            requests.append({"request_id": case_id + "_" + arm, "case_id": case_id,
                             "language": case["language"], "stratum": case["stratum"], "arm": arm,
                             "request": request, "sha256": digest(request)})
    assert len(requests) <= 240
    previous_ids = {c.get("post_id") for c in json.loads((HERE.parent / "2026-09-30-060237-jev-primary-classifier/cohort.json").read_text())["cases"]}
    overlap = [c["case_id"] for c in cohort["cases"] if c["post_id"] in previous_ids]
    save("references.json", {"references": refs, "excluded": excluded,
         "reviewer": "main agent; source review before model inference; not independent human adjudication"})
    save("requests.json", requests)
    names = ("scope.md", "contract.md", "questions.py", "run.py", "cohort.json", "selection.json",
             "reference_rows.json", "references.json", "requests.json", "prepare.py", "collect_db.py",
             "language-census.sql", "cohort-candidates.sql", "cohort-candidates-v2.sql",
             "language-census-render-result.json", "cohort-candidates-v2-render-result.json",
             "catalog.sql", "catalog-render-result.json")
    save("frozen.json", {"at": now(), "model": MODEL, "max_calls": 240, "planned_calls": len(requests),
         "max_usd": str(LIMIT), "price_per_million_input_usd": str(PRICE),
         "files": {n: file_digest(HERE / n) for n in names},
         "protected_files": {n: file_digest(REPO / n) for n in PROTECTED},
         "prior_validator_sha256": file_digest(Path(prior.__file__)),
         "selfcheck_passed": True, "provider_calls": 0, "previous_primary_case_overlap": overlap})
    print(json.dumps({"prepared": True, "cases": len(refs), "calls": len(requests), "fields_per_call": len(questions),
                      "arms": dict(Counter(r["arm"] for r in requests)), "max_usd": str(LIMIT),
                      "largest_state_bytes": max(len(encode(r["request"]["state"])) for r in requests),
                      "largest_request_bytes": max(len(encode(r["request"])) for r in requests), "prior_case_overlap": overlap}))


def verify():
    frozen = load("frozen.json")
    for name, sha in frozen["files"].items():
        assert file_digest(HERE / name) == sha, name
    for name, sha in frozen["protected_files"].items():
        assert file_digest(REPO / name) == sha, name
    assert file_digest(Path(prior.__file__)) == frozen["prior_validator_sha256"]
    return frozen


def run():
    frozen = verify()
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key:
        raise SystemExit("missing_typesafe_credential_no_calls")
    requests = load("requests.json")
    assert len(requests) == frozen["planned_calls"] <= 240
    save("run-started.json", {"at": now(), "frozen_sha256": file_digest(HERE / "frozen.json")})
    spent = Decimal(0)
    for index, item in enumerate(requests):
        body = encode(item["request"])
        assert digest(item["request"]) == item["sha256"]
        reserve = Decimal((len(body) + 4096) * 2) * PRICE / Decimal(1000000)
        if spent + reserve > LIMIT:
            raise SystemExit("budget_stop_no_retry")
        stem = "receipts/" + item["request_id"]
        save(stem + "-started.json", {"at": now(), "request_sha256": item["sha256"], "reservation_usd": str(reserve)})
        started = time.monotonic()
        connection = http.client.HTTPSConnection("api.typesafe.ai", timeout=30)
        try:
            connection.request("POST", "/v1/systemone", body=body,
                               headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
            response = connection.getresponse()
            raw = response.read(2000001).decode()
            assert len(raw) <= 2000000
            status = response.status
        except Exception as exc:
            save(stem + "-error.json", {"error_type": type(exc).__name__, "completion": "unknown", "retained_reservation_usd": str(reserve)})
            raise SystemExit("transport_error_stop_no_retry") from None
        finally:
            connection.close()
        elapsed = time.monotonic() - started
        save(stem + "-response.json", {"at": now(), "status": status, "elapsed_seconds": elapsed,
                                      "raw_body": raw.replace(key, "[REDACTED]")})
        if status != 200:
            raise SystemExit("provider_http_error_stop_no_retry")
        data = json.loads(raw)
        answers, extra = decode(data, item["request"])
        usage = data["usage"]
        for field in ("input_tokens", "output_tokens"):
            assert isinstance(usage[field], int) and not isinstance(usage[field], bool) and usage[field] >= 0
        cost = Decimal(usage["input_tokens"]) * PRICE / Decimal(1000000)
        assert cost <= reserve
        spent += cost
        save(stem + "-accounting.json", {"usage": usage, "estimated_usd": str(cost), "provider_invoice_usd": None,
             "invalid_fields": [k for k, v in answers.items() if not v["valid"]], "extra_fields": extra,
             "consistency_issues": consistency(answers)})
        if (index + 1) % 10 == 0 or index + 1 == len(requests):
            print(json.dumps({"completed": index + 1, "planned": len(requests), "estimated_usd": str(spent)}), flush=True)
    save("complete.json", {"at": now(), "calls": len(requests), "estimated_usd": str(spent)})


def summarize(rows):
    cases = sorted({r["case_id"] for r in rows})
    binary = [r for r in rows if isinstance(r["expected"], bool)]
    tp = sum(r["valid"] and r["assigned"] is True and r["expected"] for r in binary)
    fp = sum(r["valid"] and r["assigned"] is True and not r["expected"] for r in binary)
    fn = sum(r["expected"] and not (r["valid"] and r["assigned"] is True) for r in binary)
    tn = sum(r["valid"] and r["assigned"] is False and not r["expected"] for r in binary)
    ratio = lambda a, b: a / b if b else None
    return {"correct": sum(r["correct"] for r in rows), "total": len(rows),
            "agreement": ratio(sum(r["correct"] for r in rows), len(rows)), "cases": len(cases),
            "all_fields_correct": sum(all(r["correct"] for r in rows if r["case_id"] == case) for case in cases),
            "invalid": sum(not r["valid"] for r in rows),
            "positive_binary": {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
                                "precision": ratio(tp, tp + fp), "recall": ratio(tp, tp + fn),
                                "f1": ratio(2 * tp, 2 * tp + fp + fn)}}


def sensitivity_keep(row):
    if row["case_id"] == "es_14" and not row["field"].startswith("promotion:"):
        return False
    if row["case_id"] == "zh_cn_08" and row["field"] == "china_national_stance":
        return False
    if row["case_id"] == "tr_19" and (row["field"].startswith("geo:") or row["field"].endswith("national_stance")):
        return False
    return True


def score():
    frozen = verify()
    requests = load("requests.json")
    assert load("complete.json")["calls"] == len(requests)
    refs = load("references.json")["references"]
    rows, issues, durations = [], [], []
    input_tokens = output_tokens = 0
    for item in requests:
        receipt = load("receipts/" + item["request_id"] + "-response.json")
        assert receipt["status"] == 200
        data = json.loads(receipt["raw_body"])
        answers, extra = decode(data, item["request"])
        for field, answer in answers.items():
            expected = refs[item["case_id"]]["expected"][field]
            rows.append({k: item[k] for k in ("request_id", "case_id", "language", "stratum", "arm")} |
                        {"field": field, "family": field.split(":")[0], "expected": expected, **answer,
                         "correct": answer["valid"] and answer["assigned"] == expected})
        found = consistency(answers)
        if found or extra:
            issues.append({"request_id": item["request_id"], "issues": found, "extra_fields": extra})
        durations.append(receipt["elapsed_seconds"])
        input_tokens += data["usage"]["input_tokens"]
        output_tokens += data["usage"]["output_tokens"]
    assert len(rows) == len(requests) * 38
    assert len(list((HERE / "receipts").glob("*-started.json"))) == len(requests)
    cost = Decimal(input_tokens) * PRICE / Decimal(1000000)
    assert cost == Decimal(load("complete.json")["estimated_usd"]) <= LIMIT
    summary = {}
    for arm in ("raw", "translated"):
        subset = [r for r in rows if r["arm"] == arm]
        summary[arm] = {"combined": summarize(subset),
            "languages": {lang: summarize([r for r in subset if r["language"] == lang]) for lang in sorted({r["language"] for r in subset})},
            "families": {family: summarize([r for r in subset if r["family"] == family]) for family in sorted({r["family"] for r in subset})},
            "strata": {st: summarize([r for r in subset if r["stratum"] == st]) for st in ("natural", "coverage")},
            "sensitivity": summarize([r for r in subset if sensitivity_keep(r)])}
    paired_ids = {r["case_id"] for r in rows if r["arm"] == "translated"}
    paired = {arm: summarize([r for r in rows if r["arm"] == arm and r["case_id"] in paired_ids]) for arm in ("raw", "translated")}
    label_results = {arm: {field: summarize([r for r in rows if r["arm"] == arm and r["field"] == field])
                          for field in build_questions()} for arm in ("raw", "translated")}
    bins = {}
    for arm in ("raw", "translated"):
        bins[arm] = {}
        for low, high in ((0, .6), (.6, .8), (.8, .9), (.9, 1.000001)):
            subset = [r for r in rows if r["arm"] == arm and r["valid"] and low <= r["selected_probability"] < high]
            bins[arm][f"{low:.2f}-{min(high,1):.2f}"] = {"correct": sum(r["correct"] for r in subset), "total": len(subset)}
    result = {"summary": summary, "paired": paired, "label_results": label_results, "rows": rows,
              "consistency_issues": issues, "confidence_bins_descriptive_only": bins,
              "usage": {"calls": len(requests), "input_tokens": input_tokens, "output_tokens": output_tokens,
                        "estimated_usd": str(cost), "median_seconds": statistics.median(durations),
                        "min_seconds": min(durations), "max_seconds": max(durations)},
              "audit": {"frozen_hashes_match": True, "protected_files_unchanged": True, "starts_reconciled": True,
                        "fields_per_response": 38, "db_calls": len(list(HERE.glob("*-db-started.json"))),
                        "selfcheck_passed": frozen["selfcheck_passed"], "retry_calls": 0}}
    save("scores.json", result)
    save("disagreements.json", [r for r in rows if not r["correct"]])
    print(json.dumps({"summary": {a: summary[a]["combined"] for a in summary}, "paired": paired,
                      "consistency_responses": len(issues), "usage": result["usage"], "audit": result["audit"]}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run", "score", "selfcheck"))
    globals()[parser.parse_args().action]()
