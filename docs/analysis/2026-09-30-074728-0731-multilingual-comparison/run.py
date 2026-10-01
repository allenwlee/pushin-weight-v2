"""Matched classification-only diagnostic. No application imports or DB access."""
import argparse
import base64
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import statistics
import subprocess
import sys
from unittest.mock import patch
import zlib

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
JEV = HERE.parent / "2026-09-30-070427-jev-multilingual-classification"
OLD = HERE.parent / "2026-09-30-063633-0731-matched-primary-comparison"
SERVICE = "crn-da7vrdqd0e5s739uvcs0"
MODEL = "deepseek-ai/DeepSeek-V4-Flash-0731"


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


sys.path.insert(0, str(JEV))
jev = module("jev_multi_frozen", JEV / "run.py")
previous = module("previous_0731_frozen", OLD / "run.py")
remote = module("remote_0731_multi", HERE / "remote.py")
encode, now, file_sha = jev.encode, jev.now, jev.file_digest


def sha(value):
    return hashlib.sha256(encode(value)).hexdigest()


def read(name):
    return json.loads((HERE / name).read_text())


def save(name, value):
    path = HERE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def strict_object(pairs):
    value = {}
    for key, child in pairs:
        if key in value:
            raise ValueError("duplicate_json_key")
        value[key] = child
    return value


def decode(data, questions):
    issues = []
    try:
        choice = data["choices"][0]
        assert data["model"] == MODEL and choice["finish_reason"] == "stop"
        content = json.loads(choice["message"]["content"], object_pairs_hook=strict_object)
        assert isinstance(content, dict) and isinstance(content.get("answers"), dict)
        answers = content["answers"]
        if set(content) != {"answers"}:
            issues.append("extra_root_keys")
    except (KeyError, ValueError, AssertionError, IndexError, TypeError):
        answers = {}
        issues.append("invalid_response_envelope")
    parsed = {}
    for field, question in questions.items():
        try:
            parsed[field] = previous.parse_answer(answers.get(field), question, "B_probabilities")
        except (KeyError, ValueError, TypeError):
            parsed[field] = {"assigned": None, "valid": False, "label_valid": False}
    extra = sorted(set(answers) - set(questions))
    return parsed, extra, issues


def selfcheck():
    jev.selfcheck()
    qs = {"binary": {"type": "noul"}, "scalar": {"type": "choice", "criteria": {"a": "", "b": ""}}}
    valid = {"binary": {"label": True, "probabilities": {"true": .5, "false": .5}},
             "scalar": {"label": "a", "probabilities": {"a": .6, "b": .4}}}
    envelope = lambda text: {"model": MODEL, "choices": [{"finish_reason": "stop", "message": {"content": text}}]}
    parsed, extra, issues = decode(envelope(json.dumps({"answers": valid})), qs)
    assert all(row["valid"] for row in parsed.values()) and not extra and not issues
    valid["scalar"]["label"] = "b"
    parsed, _, _ = decode(envelope(json.dumps({"answers": valid})), qs)
    assert parsed["binary"]["valid"] and not parsed["scalar"]["valid"]
    parsed, _, _ = decode(envelope('{"answers":{},"answers":{}}'), qs)
    assert not any(row["valid"] for row in parsed.values())
    parsed, _, _ = decode(envelope(json.dumps({"answers": {"binary": valid["binary"]}})), qs)
    assert parsed["binary"]["valid"] and not parsed["scalar"]["valid"]
    packet = {"profile": {"model": MODEL, "temperature": 1.0, "top_p": 1.0,
        "seed": 42, "reasoning_effort": "none", "max_tokens": 4096},
        "system": "offline fixture only", "questions": qs, "items": []}
    fixture_item = {"id": "fixture", "state": {"source_text": "offline fixture"}}
    fixture_item["sha256"] = sha(remote.request_for(packet, fixture_item))
    packet["items"] = [dict(fixture_item, id=str(n)) for n in range(185)]
    captured, events = [], []
    class FakeConnection:
        def __init__(self, host, timeout):
            assert host == "api.deepinfra.com" and timeout == 45
        def request(self, method, path, body, headers):
            assert method == "POST" and path == "/v1/openai/chat/completions"
            assert headers["Authorization"] == "Bearer fixture-not-a-secret"
            captured.append(json.loads(body))
        def getresponse(self):
            return self
        status = 200
        def read(self, size):
            return encode({"model": MODEL, "usage": {"prompt_tokens": 1, "completion_tokens": 1, "estimated_cost": 0}})
        def close(self):
            pass
    with patch.object(remote.http.client, "HTTPSConnection", FakeConnection):
        remote.run_packet(packet, "fixture-not-a-secret", lambda k, v: events.append((k, v)))
    assert len(captured) == 185 and all(r == remote.request_for(packet, fixture_item) for r in captured)
    assert len(events) == 372 and events[-1][1]["calls"] == 185


def prepare():
    jev.verify()
    selfcheck()
    originals = json.loads((JEV / "requests.json").read_text())
    profile = json.loads((OLD / "requests.json").read_text())[0]["request"]
    profile = {k: profile[k] for k in ("model", "temperature", "top_p", "seed", "reasoning_effort")}
    profile["max_tokens"] = 4096
    packet = {"profile": profile, "system": previous.COMMON + previous.OUTPUT["B_probabilities"],
        "questions": originals[0]["request"]["questions"], "items": []}
    requests = []
    for original in originals:
        assert original["request"]["questions"] == packet["questions"]
        item = {"id": original["request_id"], "state": original["request"]["state"]}
        request = remote.request_for(packet, item)
        user = {k: original["request"][k] for k in ("state", "questions")}
        assert json.loads(request["messages"][1]["content"]) == user
        item["sha256"] = sha(request)
        packet["items"].append(item)
        requests.append({**{k: original[k] for k in ("request_id", "case_id", "language", "stratum", "arm")},
            "request": request, "sha256": item["sha256"], "matched_input_sha256": sha(user)})
    assert len(requests) == 185 and len({r["case_id"] for r in requests}) == 117
    save("requests.json", requests)
    save("packet.json", packet)
    names = ("contract.md", "run.py", "remote.py", "requests.json", "packet.json")
    deps = {str(Path(p).relative_to(REPO)): file_sha(Path(p)) for p in
        (JEV / "run.py", JEV / "questions.py", JEV / "frozen.json", JEV / "requests.json",
         JEV / "references.json", JEV / "reference_rows.json", JEV / "scores.json",
         JEV / "cohort.json", JEV / "contract.md", OLD / "run.py", OLD / "requests.json",
         Path(jev.prior.__file__), Path(previous.jev.__file__))}
    save("frozen.json", {"at": now(), "max_calls": 185, "max_model_usd": ".50",
        "service": SERVICE, "files": {n: file_sha(HERE / n) for n in names}, "dependencies": deps,
        "protected_files": {n: file_sha(REPO / n) for n in (*jev.PROTECTED, "x_monitor/deepinfra.py")},
        "provider_calls": 0, "selfcheck_passed": True, "input_parity_verified": True})
    packed_bytes = len(base64.b64encode(zlib.compress(encode(packet))))
    assert packed_bytes + (HERE / "remote.py").stat().st_size < 200000
    print(json.dumps({"prepared": True, "calls": len(requests), "fields": len(requests) * 38,
        "arms": dict(Counter(r["arm"] for r in requests)), "max_model_usd": ".50",
        "packed_payload_bytes": packed_bytes, "selfcheck_passed": True, "input_parity": True}))


def verify():
    frozen = read("frozen.json")
    for group, directory in (("files", HERE), ("dependencies", REPO), ("protected_files", REPO)):
        for name, value in frozen[group].items():
            assert file_sha(directory / name) == value, name
    jev.verify()


def objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from objects(child)


def command_json(command):
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise SystemExit("render_read_failed_no_submission")
    return json.loads(result.stdout)


def preflight():
    values = command_json(["render", "services", "--output", "json"])
    matches = [v for v in objects(values) if v.get("id") == SERVICE]
    assert len(matches) == 1
    service = matches[0]
    assert service["name"] == "pushinweight-staging-harvest" and service["type"] == "cron_job"
    assert service["suspended"] == "suspended"
    jobs = command_json(["render", "jobs", "list", SERVICE, "--output", "json"])
    assert all(j["status"] in {"succeeded", "failed", "canceled", "cancelled"} for j in jobs)
    return {"at": now(), "service": {k: service.get(k) for k in ("id", "name", "type", "suspended", "updatedAt")},
        "jobs": [{k: j.get(k) for k in ("id", "status", "createdAt", "finishedAt")} for j in jobs]}


def submit():
    verify()
    save("render-preflight.json", preflight())
    packed = base64.b64encode(zlib.compress(encode(read("packet.json")))).decode()
    program = "import base64,json,zlib;PACKET=json.loads(zlib.decompress(base64.b64decode(" + repr(packed) + ")));\n" + (HERE / "remote.py").read_text()
    assert len(program.encode()) < 200000
    save("submission-started.json", {"at": now(), "service": SERVICE, "max_calls": 185,
        "program_sha256": hashlib.sha256(program.encode()).hexdigest()})
    try:
        result = subprocess.run(["render", "jobs", "create", SERVICE, "--plan-id", "plan-crn-003",
            "--start-command", "python -c " + shlex.quote(program), "--output", "json", "--confirm"],
            capture_output=True, text=True, timeout=45)
    except subprocess.TimeoutExpired:
        save("submission-unknown.json", {"at": now(), "reason": "CLI timeout; inspect jobs; do not resubmit"})
        raise SystemExit("submission_uncertain_stop_no_resubmit") from None
    if result.returncode:
        save("submission-failed.json", {"at": now(), "returncode": result.returncode, "stderr": result.stderr})
        raise SystemExit("submission_failed_no_resubmit")
    job = json.loads(result.stdout)
    save("job.json", job)
    print(json.dumps({"job_id": job["id"], "status": job["status"], "max_calls": 185}))


def log_objects(raw):
    remaining = raw.strip()
    while remaining:
        row, end = json.JSONDecoder().raw_decode(remaining)
        yield from row if isinstance(row, list) else [row]
        remaining = remaining[end:].lstrip()


def collect():
    job = read("job.json")
    cursor = now().replace("+00:00", "Z")
    groups = {}
    attempt = datetime.now(timezone.utc).strftime("%H%M%S%f")
    required = {"preflight", "complete"} | {f"{kind}_{i}" for kind in ("started", "finished") for i in range(185)}
    for page in range(30):
        command = ["render", "logs", "--resources", job["id"], "--limit", "40", "--output", "json",
            "--direction", "backward", "--end", cursor]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        timeout = False
        try:
            stdout, stderr = process.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            timeout = True
            process.kill()
            stdout, stderr = process.communicate()
        save(f"log-pages/{attempt}-{page:02}.json", {"command": command, "timed_out": timeout,
            "returncode": process.returncode, "stdout": stdout, "stderr": stderr})
        logs = list(log_objects(stdout))
        for row in logs:
            for kind, part, count, chunk in re.findall(r"PW_0731_MULTI ([a-z0-9_]+):(\d+)/(\d+):([A-Za-z0-9+/=]+)", row.get("message", "")):
                group = groups.setdefault(kind, {"count": int(count), "parts": {}})
                assert group["count"] == int(count)
                if int(part) in group["parts"]:
                    assert group["parts"][int(part)] == chunk
                group["parts"][int(part)] = chunk
        for kind, group in groups.items():
            if set(group["parts"]) != set(range(1, group["count"] + 1)):
                continue
            blob = "".join(group["parts"][n] for n in range(1, group["count"] + 1))
            value = json.loads(zlib.decompress(base64.b64decode(blob)))
            assert value["kind"] == kind
            name = f"events/{kind}.json"
            if (HERE / name).exists():
                assert read(name) == value
            else:
                save(name, value)
        present = {p.stem for p in (HERE / "events").glob("*.json")}
        print(json.dumps({"page": page, "events": len(present),
            "responses": sum(p.startswith("finished_") for p in present), "complete": required <= present}), flush=True)
        if required <= present or not logs or "preflight" in groups:
            return
        next_cursor = min(row["timestamp"] for row in logs)
        if next_cursor >= cursor:
            raise SystemExit("no_log_pagination_progress")
        cursor = next_cursor
    raise SystemExit("bounded_log_page_limit_no_model_retry")


def score():
    verify()
    requests = read("requests.json")
    assert read("events/complete.json")["value"]["calls"] == 185
    assert read("events/preflight.json")["value"]["packet_sha256"] == sha(read("packet.json"))
    refs = json.loads((JEV / "references.json").read_text())["references"]
    rows, issues, receipts = [], [], []
    for index, item in enumerate(requests):
        start = read(f"events/started_{index}.json")["value"]
        response = read(f"events/finished_{index}.json")["value"]
        assert start["id"] == response["id"] == item["request_id"] and start["request_sha256"] == item["sha256"]
        assert response["http_status"] == 200
        data = json.loads(response["raw_body"])
        questions = json.loads(item["request"]["messages"][1]["content"])["questions"]
        answers, extra, envelope_issues = decode(data, questions)
        for field, answer in answers.items():
            expected = refs[item["case_id"]]["expected"][field]
            rows.append({k: item[k] for k in ("request_id", "case_id", "language", "stratum", "arm")} |
                {"field": field, "family": field.split(":")[0], "expected": expected, **answer,
                 "correct": answer["valid"] and answer["assigned"] == expected,
                 "semantic_correct": answer["label_valid"] and answer["assigned"] == expected})
        found = jev.consistency(answers) + envelope_issues
        if found or extra:
            issues.append({"request_id": item["request_id"], "issues": found, "extra_fields": extra})
        receipts.append({"request_id": item["request_id"], "arm": item["arm"], "elapsed_seconds": response["elapsed_seconds"],
            "usage": data["usage"], "finish_reason": data.get("choices", [{}])[0].get("finish_reason")})
    assert len(rows) == 7030
    assert len(list((HERE / "events").glob("started_*.json"))) == len(requests)
    assert len(list((HERE / "events").glob("finished_*.json"))) == len(requests)
    summary = {}
    for arm in ("raw", "translated"):
        part = [r for r in rows if r["arm"] == arm]
        summary[arm] = {"combined": jev.summarize(part),
            "languages": {lang: jev.summarize([r for r in part if r["language"] == lang]) for lang in sorted({r["language"] for r in part})},
            "families": {f: jev.summarize([r for r in part if r["family"] == f]) for f in sorted({r["family"] for r in part})},
            "strata": {s: jev.summarize([r for r in part if r["stratum"] == s]) for s in ("natural", "coverage")},
            "sensitivity": jev.summarize([r for r in part if jev.sensitivity_keep(r)]),
            "semantic_labels": jev.summarize([r | {"valid": r["label_valid"], "correct": r["semantic_correct"]} for r in part])}
    paired_ids = {r["case_id"] for r in rows if r["arm"] == "translated"}
    paired = {a: jev.summarize([r for r in rows if r["arm"] == a and r["case_id"] in paired_ids]) for a in summary}
    labels = {a: {field: jev.summarize([r for r in rows if r["arm"] == a and r["field"] == field])
        for field in questions} for a in summary}
    jev_rows = {(r["request_id"], r["field"]): r for r in json.loads((JEV / "scores.json").read_text())["rows"]}
    pairs = [{"request_id": r["request_id"], "case_id": r["case_id"], "language": r["language"], "arm": r["arm"],
        "field": r["field"], "expected": r["expected"], "jev": jev_rows[(r["request_id"], r["field"])]["assigned"],
        "0731": r["assigned"], "jev_correct": jev_rows[(r["request_id"], r["field"])]["correct"], "0731_correct": r["correct"]} for r in rows]
    cost = sum((Decimal(str(r["usage"]["estimated_cost"])) for r in receipts), Decimal(0))
    assert cost == Decimal(read("events/complete.json")["value"]["cost_usd"]) <= Decimal(".50")
    usage = {"calls": len(receipts), "input_tokens": sum(r["usage"]["prompt_tokens"] for r in receipts),
        "output_tokens": sum(r["usage"]["completion_tokens"] for r in receipts),
        "cached_input_tokens": sum(r["usage"].get("prompt_tokens_details", {}).get("cached_tokens", 0) for r in receipts),
        "estimated_usd": str(cost), "median_seconds": statistics.median(r["elapsed_seconds"] for r in receipts),
        "min_seconds": min(r["elapsed_seconds"] for r in receipts), "max_seconds": max(r["elapsed_seconds"] for r in receipts)}
    save("scores.json", {"summary": summary, "paired": paired, "label_results": labels, "rows": rows,
        "consistency_issues": issues, "usage": usage, "request_receipts": receipts,
        "audit": {"frozen_hashes_match": True, "input_parity": True, "protected_files_unchanged": True,
            "starts_responses_reconciled": True, "selfcheck_passed": True, "retry_calls": 0}})
    save("disagreements.json", [r for r in rows if not r["correct"]])
    save("model-pairs.json", pairs)
    print(json.dumps({"summary": {a: summary[a]["combined"] for a in summary}, "paired": paired,
        "consistency_responses": len(issues), "usage": usage}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "submit", "collect", "score", "selfcheck", "verify"))
    globals()[parser.parse_args().action]()
