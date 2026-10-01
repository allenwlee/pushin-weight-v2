"""Prepare, preflight, recover, and score one frozen 0731 retest arm."""
import argparse
import base64
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import importlib.util
import json
import lzma
import math
from pathlib import Path
import re
import shlex
import statistics
import subprocess
import sys
import zlib
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPO = HERE.parents[3]
SERVICE = "crn-da7vrdqd0e5s739uvcs0"
MODEL = "deepseek-ai/DeepSeek-V4-Flash-0731"
LIMIT = Decimal("0.25")
MAX_CALLS = 117
PROFILE = {"model": MODEL, "temperature": 1.0, "top_p": 1.0, "seed": 42,
    "reasoning_effort": "none", "max_tokens": 4096}
OLD = REPO / "docs/analysis/2026-09-30-074728-0731-multilingual-comparison"
OLD_RUN = OLD / "run.py"
OLD_SPEC = importlib.util.spec_from_file_location("prior_0731_pure", OLD_RUN)
prior = importlib.util.module_from_spec(OLD_SPEC)
OLD_SPEC.loader.exec_module(prior)
REMOTE_SPEC = importlib.util.spec_from_file_location("political_0731_remote", HERE / "remote.py")
remote = importlib.util.module_from_spec(REMOTE_SPEC)
REMOTE_SPEC.loader.exec_module(remote)


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text())


def save(name, value):
    path = HERE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()


def shared_helper():
    spec = importlib.util.spec_from_file_location("political_shared_prepare", ROOT / "prepare.py")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    return helper


def decode_response(response, questions):
    issues = []
    try:
        if response.get("model") != MODEL:
            raise ValueError("wrong_model")
        choice = response["choices"][0]
        if choice["finish_reason"] != "stop":
            raise ValueError("non_stop_completion")
        body = json.loads(choice["message"]["content"], object_pairs_hook=strict_object)
        if not isinstance(body, dict) or not isinstance(body.get("answers"), dict):
            raise ValueError("invalid_answer_object")
        answers = body["answers"]
        if set(body) != {"answers"}:
            issues.append("extra_root_keys")
    except (KeyError, IndexError, TypeError, ValueError, AssertionError):
        return ({field: {"assigned": None, "valid": False, "label_valid": False,
                         "probabilities_valid": False, "error": "invalid_response_envelope"}
                 for field in questions}, [], ["invalid_response_envelope"])
    parsed = {}
    for field, question in questions.items():
        try:
            parsed[field] = prior.previous.parse_answer(answers.get(field), question, "B_probabilities")
        except (KeyError, TypeError, ValueError):
            parsed[field] = {"assigned": None, "valid": False, "label_valid": False,
                             "probabilities_valid": False, "error": "invalid_answer"}
    extra = sorted(set(answers) - set(questions))
    return parsed, extra, issues


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def selfcheck():
    assert prior.previous.parse_answer({"label": True, "probabilities": {"true": .5, "false": .5}},
                              {"type": "noul"}, "B_probabilities")["valid"]
    assert not prior.previous.parse_answer({"label": False, "probabilities": {"true": .9, "false": .1}},
                                  {"type": "noul"}, "B_probabilities")["valid"]
    choice = {"type": "choice", "criteria": {"a": "", "b": ""}}
    assert prior.previous.parse_answer({"label": "a", "probabilities": {"a": .6, "b": .4}},
                              choice, "B_probabilities")["valid"]
    qs = {"binary": {"type": "noul"}, "choice": choice}
    payload = {"model": MODEL, "choices": [{"finish_reason": "stop", "message": {
        "content": json.dumps({"answers": {
            "binary": {"label": True, "probabilities": {"true": .5, "false": .5}},
            "choice": {"label": "a", "probabilities": {"a": .6, "b": .4}}}})}}]}
    parsed, extra, issues = decode_response(payload, qs)
    assert all(r["valid"] for r in parsed.values()) and not extra and not issues
    dup = {"model": MODEL, "choices": [{"finish_reason": "stop", "message": {
        "content": '{"answers":{},"answers":{}}'}}]}
    assert not any(r["valid"] for r in decode_response(dup, qs)[0].values())
    fixture_item = {"request_id": "fixture", "state": {"source_text": "offline fixture"}}
    packet = {"profile": PROFILE, "system": "fixture only", "questions": qs,
              "items": [dict(fixture_item, request_id=str(i)) for i in range(MAX_CALLS)]}
    for item in packet["items"]:
        item["sha256"] = hashlib.sha256(encode(remote.request_for(packet, item))).hexdigest()
    sent, emitted = [], []

    class FakeConnection:
        def __init__(self, host, timeout):
            assert (host, timeout) == ("api.deepinfra.com", 45)

        def request(self, method, path, body, headers):
            assert (method, path) == ("POST", "/v1/openai/chat/completions")
            assert headers["Authorization"] == "Bearer fixture-not-a-secret"
            sent.append(json.loads(body))

        def getresponse(self):
            return self

        status = 200

        def read(self, size):
            return encode({"model": MODEL, "usage": {"prompt_tokens": 1,
                "completion_tokens": 1, "estimated_cost": 0}})

        def close(self):
            pass

    with patch.object(remote.http.client, "HTTPSConnection", FakeConnection):
        remote.run_packet(packet, "fixture-not-a-secret", lambda kind, value: emitted.append((kind, value)))
    assert len(sent) == MAX_CALLS and len(emitted) == 3 * MAX_CALLS + 2
    assert all(sent[i] == remote.request_for(packet, packet["items"][i]) for i in range(MAX_CALLS))
    assert emitted[-1][0] == "complete" and emitted[-1][1]["calls"] == MAX_CALLS

    oversized = {"profile": PROFILE, "system": "fixture only", "questions": qs, "items": []}
    for i in range(MAX_CALLS):
        item = {"request_id": str(i), "state": {"source_text": "x" * (2_200_000 if i == 0 else 1)}}
        item["sha256"] = hashlib.sha256(encode(remote.request_for(oversized, item))).hexdigest()
        oversized["items"].append(item)
    budget_events = []
    try:
        remote.run_packet(oversized, "fixture-not-a-secret",
            lambda kind, value: budget_events.append((kind, value)))
    except SystemExit as exc:
        assert str(exc) == "budget_or_deadline_no_retry"
    else:
        raise AssertionError("oversized input should stop before its first provider call")
    assert [kind for kind, _ in budget_events] == ["preflight", "stopped"]

    bounded_packet = {"profile": PROFILE, "system": "fixture only", "questions": qs, "items": []}
    for i in range(MAX_CALLS):
        item = {"request_id": str(i), "state": {"source_text": "x" * 70000}}
        item["sha256"] = hashlib.sha256(encode(remote.request_for(bounded_packet, item))).hexdigest()
        bounded_packet["items"].append(item)
    budget_sent, cumulative_events = [], []

    class BudgetConnection:
        status = 200

        def __init__(self, host, timeout):
            assert (host, timeout) == ("api.deepinfra.com", 45)

        def request(self, method, path, body, headers):
            assert (method, path) == ("POST", "/v1/openai/chat/completions")
            assert headers["Authorization"] == "Bearer fixture-not-a-secret"
            self.reservation = remote.reservation(body)
            budget_sent.append((len(body), str(self.reservation)))

        def getresponse(self):
            return self

        def read(self, size):
            return encode({"model": MODEL, "usage": {"prompt_tokens": 1,
                "completion_tokens": 1, "estimated_cost": str(self.reservation)}})

        def close(self):
            pass

    try:
        with patch.object(remote.http.client, "HTTPSConnection", BudgetConnection):
            remote.run_packet(bounded_packet, "fixture-not-a-secret",
                lambda kind, value: cumulative_events.append((kind, value)))
    except SystemExit as exc:
        assert str(exc) == "budget_or_deadline_no_retry"
    else:
        raise AssertionError("cumulative actual spend should stop at the next-call reserve")
    successful_cost = sum((Decimal(value["estimated_cost"]) for kind, value in cumulative_events
        if kind.startswith("accounting_")), Decimal(0))
    assert 0 < len(budget_sent) < MAX_CALLS
    assert cumulative_events[-1][0] == "stopped"
    assert Decimal(cumulative_events[-1][1]["cost_usd"]) == successful_cost <= remote.LIMIT

    class FailedConnection(FakeConnection):
        def request(self, method, path, body, headers):
            raise TimeoutError("offline transport fixture")

    failure_events = []
    with patch.object(remote.http.client, "HTTPSConnection", FailedConnection):
        try:
            remote.run_packet(packet, "fixture-not-a-secret",
                lambda kind, value: failure_events.append((kind, value)))
        except SystemExit as exc:
            assert str(exc) == "transport_error_stop_no_retry"
        else:
            raise AssertionError("transport failure must stop without retry")
    assert [kind for kind, _ in failure_events] == ["preflight", "started_0", "error_0"]
    print(json.dumps({"offline_selfcheck": "passed", "fake_calls": len(sent),
        "recorded_events": len(emitted), "budget_stop_fixture": "passed",
        "cumulative_budget_stop_after_fake_calls": len(budget_sent),
        "transport_stop_fixture": "passed", "provider_calls": 0}))


def prepare():
    helper = shared_helper()
    helper.verify()
    selfcheck()
    source = read(ROOT / "requests.json")
    questions = read(ROOT / "questions.json")
    references = read(ROOT / "references.json")
    assert len(source) == MAX_CALLS and len(references["references"]) == MAX_CALLS
    assert len(questions) == 38
    system = prior.previous.COMMON + prior.previous.OUTPUT["B_probabilities"]
    old_requests = read(OLD / "requests.json")
    old_raw = {item["case_id"]: item for item in old_requests if item["arm"] == "raw"}
    assert len(old_raw) == MAX_CALLS
    political_keys = set()
    for original in source:
        old = old_raw[original["case_id"]]
        old_input = json.loads(old["request"]["messages"][1]["content"])
        new_input = {"state": original["request"]["state"], "questions": questions}
        assert original["request_id"] == old["request_id"]
        assert original["language"] == old["language"] and original["stratum"] == old["stratum"]
        assert original["request"]["state"] == old_input["state"]
        assert {k: v for k, v in old["request"].items() if k != "messages"} == PROFILE
        old_questions = old_input["questions"]
        assert set(old_questions) == set(questions)
        changed = {field for field in questions if questions[field] != old_questions[field]}
        assert len(changed) == 3
        political_keys.update(changed)
        assert all(questions[field] == old_questions[field] for field in set(questions) - changed)
        assert old["request"]["messages"][0]["content"] == system
        assert set(new_input) == {"state", "questions"}
    assert len(political_keys) == 3
    items, requests = [], []
    for original in source:
        request = original["request"]
        assert request["questions"] == questions
        state = request["state"]
        item = {k: original[k] for k in ("request_id", "case_id", "language", "stratum", "arm")}
        assert item["arm"] == "raw"
        item["state"] = state
        payload = remote.request_for({"profile": PROFILE, "system": system,
            "questions": questions}, item)
        item["sha256"] = hashlib.sha256(encode(payload)).hexdigest()
        item["matched_input_sha256"] = digest({"state": state, "questions": questions})
        items.append(item)
        requests.append({**{k: item[k] for k in ("request_id", "case_id", "language", "stratum", "arm")},
            "request": payload, "sha256": item["sha256"],
            "matched_input_sha256": item["matched_input_sha256"]})
    assert len({i["case_id"] for i in items}) == MAX_CALLS
    packet = {"profile": PROFILE, "system": system, "questions": questions, "items": items}
    save("requests.json", requests)
    save("packet.json", packet)
    raw_packet = encode(packet)
    compressed = base64.b64encode(lzma.compress(raw_packet)).decode()
    program = "import base64,json,lzma;PACKET=json.loads(lzma.decompress(base64.b64decode(" + repr(compressed) + ")));\n" + (HERE / "remote.py").read_text()
    command = "python -c " + shlex.quote(program)
    reservations = [remote.reservation(encode(remote.request_for(packet, item))) for item in items]
    source_names = ("requests.json", "questions.json", "references.json", "frozen.json", "prepare.py")
    roots = {name: file_digest(ROOT / name) for name in source_names}
    own_names = ("run.py", "remote.py", "contract.md", "requests.json", "packet.json")
    save("frozen-local.json", {"at": now(), "service": SERVICE, "model": MODEL,
        "max_calls": MAX_CALLS, "max_model_usd": str(LIMIT), "profile": PROFILE,
        "files": {n: file_digest(HERE / n) for n in own_names},
        "shared_inputs": roots,
        "helper_sha256": file_digest(OLD_RUN),
        "transport": {"codec": "lzma+base64", "packet_sha256": hashlib.sha256(raw_packet).hexdigest(),
            "round_trip_verified": lzma.decompress(base64.b64decode(compressed)) == raw_packet,
            "start_command_bytes": len(command.encode())},
        "input_parity": {"matched_original_text_cases": MAX_CALLS,
            "unchanged_question_count": 35, "changed_question_ids": sorted(political_keys),
            "profile_and_system_unchanged": True, "state_unchanged": True},
        "reservation_preflight": {"per_request_usd": [str(value) for value in reservations],
            "total_worst_case_usd": str(sum(reservations, Decimal(0))),
            "max_single_request_usd": str(max(reservations))},
        "provider_calls": 0, "selfcheck_passed": True, "input_parity_verified": True})
    print(json.dumps({"prepared": True, "requests": len(requests), "questions": len(questions),
        "scored_fields": len(requests) * len(questions), "packet_bytes": len(raw_packet),
        "lzma_base64_bytes": len(compressed), "start_command_bytes": len(command.encode()),
        "start_command_within_limit": len(command.encode()) < 130000,
        "max_model_usd": str(LIMIT), "worst_case_total_reservation_usd": str(sum(reservations, Decimal(0))),
        "reservation_guard": "actual_spend_plus_next_request_reservation",
        "input_parity": {"same_raw_states": MAX_CALLS, "same_question_definitions": 35,
            "changed_question_ids": sorted(political_keys)},
        "shared_hashes_recorded": len(roots), "provider_calls": 0}))


def verify():
    helper = shared_helper()
    helper.verify()
    frozen = read(HERE / "frozen-local.json")
    for name, value in frozen["files"].items():
        assert file_digest(HERE / name) == value, name
    for name, value in frozen["shared_inputs"].items():
        assert file_digest(ROOT / name) == value, name
    assert file_digest(OLD_RUN) == frozen["helper_sha256"]
    assert len(read(HERE / "packet.json")["items"]) == MAX_CALLS


def transport_check():
    verify()
    packet = read(HERE / "packet.json")
    raw = encode(packet)
    compressed = base64.b64encode(lzma.compress(raw)).decode()
    assert lzma.decompress(base64.b64decode(compressed)) == raw
    program = "import base64,json,lzma;PACKET=json.loads(lzma.decompress(base64.b64decode(" + repr(compressed) + ")));\n" + (HERE / "remote.py").read_text()
    command = "python -c " + shlex.quote(program)
    reserves = [remote.reservation(encode(remote.request_for(packet, item))) for item in packet["items"]]
    print(json.dumps({"codec": "lzma+base64", "packet_sha256": hashlib.sha256(raw).hexdigest(),
        "packet_bytes": len(raw), "compressed_base64_bytes": len(compressed),
        "full_start_command_bytes": len(command.encode()), "command_limit_bytes": 130000,
        "within_command_limit": len(command.encode()) < 130000,
        "lossless_round_trip": True, "max_calls": len(reserves), "model_cost_cap_usd": str(LIMIT),
        "worst_case_total_reservation_usd": str(sum(reserves, Decimal(0))),
        "max_next_call_reservation_usd": str(max(reserves)),
        "reservation_guard": "actual_spend_plus_next_request_reservation"}))
    assert len(command.encode()) < 130000


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
    services = command_json(["render", "services", "--output", "json"])
    matches = [value for value in objects(services) if value.get("id") == SERVICE]
    service = matches[0] if len(matches) == 1 else {}
    jobs = command_json(["render", "jobs", "list", SERVICE, "--output", "json"])
    terminal = {"succeeded", "failed", "canceled", "cancelled"}
    identity_ok = (len(matches) == 1 and service.get("name") == "pushinweight-staging-harvest"
        and service.get("type") == "cron_job" and service.get("suspended") == "suspended")
    idle = all(job.get("status") in terminal for job in jobs)
    return {"at": now(), "service": {k: service.get(k) for k in
            ("id", "name", "type", "suspended", "updatedAt")},
        "jobs": [{k: job.get(k) for k in ("id", "status", "createdAt", "finishedAt")} for job in jobs],
        "eligible": identity_ok and idle,
        "blockers": ([] if identity_ok else ["service_identity_or_suspension_changed"])
            + ([] if idle else ["one_off_job_active_or_pending"])}


def refresh():
    verify()
    check = preflight()
    save("pre-call-refresh.json", {"at": now(), "provider_calls": 0,
        "shared_frozen_manifest_sha256": file_digest(ROOT / "frozen.json"),
        "local_frozen_manifest_sha256": file_digest(HERE / "frozen-local.json"),
        "source_hashes_verified": True, "service_preflight": check})
    print(json.dumps({"pre_call_refresh": "passed" if check["eligible"] else "blocked",
        "provider_calls": 0, "service": check["service"], "eligible": check["eligible"],
        "blockers": check["blockers"]}))
    if not check["eligible"]:
        raise SystemExit("render_preflight_blocked_no_submission")


def submit():
    verify()
    check = preflight()
    save("render-preflight.json", check)
    if not check["eligible"]:
        raise SystemExit("render_preflight_blocked_no_submission")
    packet_bytes = encode(read(HERE / "packet.json"))
    compressed = base64.b64encode(lzma.compress(packet_bytes)).decode()
    assert lzma.decompress(base64.b64decode(compressed)) == packet_bytes
    program = "import base64,json,lzma;PACKET=json.loads(lzma.decompress(base64.b64decode(" + repr(compressed) + ")));\n" + (HERE / "remote.py").read_text()
    command = "python -c " + shlex.quote(program)
    assert len(command.encode()) < 130000
    save("transport-frozen.json", {"at": now(), "codec": "lzma+base64",
        "packet_sha256": hashlib.sha256(packet_bytes).hexdigest(),
        "remote_sha256": file_digest(HERE / "remote.py"),
        "program_sha256": hashlib.sha256(program.encode()).hexdigest(),
        "start_command_bytes": len(command.encode()), "round_trip_verified": True,
        "provider_calls": 0})
    save("submission-started.json", {"at": now(), "service": SERVICE,
        "max_calls": MAX_CALLS, "max_model_usd": str(LIMIT),
        "program_sha256": hashlib.sha256(program.encode()).hexdigest()})
    try:
        result = subprocess.run(["render", "jobs", "create", SERVICE, "--plan-id", "plan-crn-003",
            "--start-command", command, "--output", "json", "--confirm"],
            capture_output=True, text=True, timeout=45)
    except subprocess.TimeoutExpired:
        save("submission-unknown.json", {"at": now(), "reason": "CLI timeout; inspect job; never resubmit"})
        raise SystemExit("submission_uncertain_stop_no_resubmit") from None
    if result.returncode:
        save("submission-failed.json", {"at": now(), "returncode": result.returncode,
            "stderr": result.stderr})
        raise SystemExit("submission_failed_no_resubmit")
    job = json.loads(result.stdout)
    save("job.json", {k: job.get(k) for k in ("id", "status", "createdAt", "finishedAt")})
    print(json.dumps({"job_id": job["id"], "status": job["status"],
        "max_calls": MAX_CALLS, "start_command_bytes": len(command.encode())}))


def log_objects(raw):
    remaining = raw.strip()
    while remaining:
        row, end = json.JSONDecoder().raw_decode(remaining)
        yield from row if isinstance(row, list) else [row]
        remaining = remaining[end:].lstrip()


def collect():
    verify()
    job = read(HERE / "job.json")
    cursor = now().replace("+00:00", "Z")
    groups = {}
    attempt = datetime.now(timezone.utc).strftime("%H%M%S%f")
    required = {"preflight", "complete"} | {f"{kind}_{i}" for kind in
        ("started", "finished", "accounting") for i in range(MAX_CALLS)}
    for page in range(60):
        command = ["render", "logs", "--resources", job["id"], "--limit", "40", "--output", "json",
            "--direction", "backward", "--end", cursor]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            stdout, stderr = process.communicate()
        save(f"log-pages/{attempt}-{page:02}.json", {"command": command, "timed_out": timed_out,
            "returncode": process.returncode, "stdout": stdout, "stderr": stderr})
        logs = list(log_objects(stdout))
        for row in logs:
            for kind, part, count, chunk in re.findall(
                r"PW_POLITICAL_0731 ([a-z0-9_]+):(\d+)/(\d+):([A-Za-z0-9+/=]+)", row.get("message", "")):
                group = groups.setdefault(kind, {"count": int(count), "parts": {}})
                assert group["count"] == int(count)
                old = group["parts"].get(int(part))
                assert old is None or old == chunk
                group["parts"][int(part)] = chunk
        for kind, group in groups.items():
            if set(group["parts"]) != set(range(1, group["count"] + 1)):
                continue
            value = json.loads(zlib.decompress(base64.b64decode("".join(
                group["parts"][n] for n in range(1, group["count"] + 1)))))
            assert value["kind"] == kind
            name = f"events/{kind}.json"
            if (HERE / name).exists():
                assert read(HERE / name) == value
            else:
                save(name, value)
        present = {p.stem for p in (HERE / "events").glob("*.json")}
        print(json.dumps({"page": page, "events": len(present),
            "finished": sum(s.startswith("finished_") for s in present), "complete": required <= present}), flush=True)
        if required <= present:
            return
        if not logs:
            raise SystemExit("logs_incomplete_no_model_retry")
        next_cursor = min(row["timestamp"] for row in logs)
        if next_cursor >= cursor:
            raise SystemExit("no_log_pagination_progress")
        cursor = next_cursor
    raise SystemExit("bounded_log_page_limit_no_model_retry")


def summarize(rows, correct_key="correct"):
    if not rows:
        return {"n": 0, "accuracy": None}
    return {"n": len(rows), "valid": sum(bool(r["valid"]) for r in rows),
        "invalid": sum(not bool(r["valid"]) for r in rows),
        "correct": sum(bool(r[correct_key]) for r in rows),
        "accuracy": sum(bool(r[correct_key]) for r in rows) / len(rows)}


def score():
    verify()
    assert read(HERE / "events/complete.json")["value"]["calls"] == MAX_CALLS
    packet = read(HERE / "packet.json")
    assert read(HERE / "events/preflight.json")["value"]["packet_sha256"] == digest(packet)
    refs = read(ROOT / "references.json")["references"]
    rows, issues, receipts = [], [], []
    for index, item in enumerate(packet["items"]):
        start = read(HERE / f"events/started_{index}.json")["value"]
        finish = read(HERE / f"events/finished_{index}.json")["value"]
        accounting = read(HERE / f"events/accounting_{index}.json")["value"]
        assert start["id"] == finish["id"] == item["request_id"]
        assert start["request_sha256"] == item["sha256"] and finish["http_status"] == 200
        response = json.loads(finish["raw_body"])
        assert accounting["id"] == item["request_id"] and accounting["status"] == "usage_present"
        assert accounting["estimated_cost"] == str(response["usage"]["estimated_cost"])
        answers, extra, envelope_issues = decode_response(response, packet["questions"])
        for field, answer in answers.items():
            expected = refs[item["case_id"]]["expected"][field]
            rows.append({k: item[k] for k in ("request_id", "case_id", "language", "stratum", "arm")} |
                {"field": field, "family": field.split(":")[0], "expected": expected, **answer,
                 "correct": answer["valid"] and answer["assigned"] == expected,
                 "semantic_correct": answer.get("label_valid", False) and answer["assigned"] == expected})
        found = envelope_issues + (["extra_answer_fields"] if extra else [])
        if found or any(not r["valid"] for r in answers.values()):
            issues.append({"request_id": item["request_id"], "issues": found,
                "invalid_fields": [f for f, r in answers.items() if not r["valid"]], "extra_fields": extra})
        usage = response.get("usage", {})
        receipts.append({"request_id": item["request_id"], "elapsed_seconds": finish["elapsed_seconds"],
            "usage": usage, "finish_reason": response.get("choices", [{}])[0].get("finish_reason")})
    assert len(rows) == MAX_CALLS * 38
    assert len(list((HERE / "events").glob("started_*.json"))) == MAX_CALLS
    assert len(list((HERE / "events").glob("finished_*.json"))) == MAX_CALLS
    assert len(list((HERE / "events").glob("accounting_*.json"))) == MAX_CALLS
    summary = {"overall": summarize(rows),
        "languages": {lang: summarize([r for r in rows if r["language"] == lang]) for lang in sorted({r["language"] for r in rows})},
        "families": {family: summarize([r for r in rows if r["family"] == family]) for family in sorted({r["family"] for r in rows})},
        "strata": {stratum: summarize([r for r in rows if r["stratum"] == stratum]) for stratum in sorted({r["stratum"] for r in rows})},
        "semantic_labels": summarize(rows, "semantic_correct")}
    cost = sum((Decimal(str(r["usage"]["estimated_cost"])) for r in receipts), Decimal(0))
    complete = Decimal(read(HERE / "events/complete.json")["value"]["cost_usd"])
    assert cost == complete <= LIMIT
    usage = {"calls": len(receipts), "input_tokens": sum(r["usage"]["prompt_tokens"] for r in receipts),
        "output_tokens": sum(r["usage"]["completion_tokens"] for r in receipts),
        "estimated_usd": str(cost),
        "median_seconds": statistics.median(r["elapsed_seconds"] for r in receipts),
        "min_seconds": min(r["elapsed_seconds"] for r in receipts),
        "max_seconds": max(r["elapsed_seconds"] for r in receipts)}
    result = {"summary": summary, "rows": rows, "consistency_and_invalid_outputs": issues,
        "usage": usage, "audit": {"frozen_hashes_match": True, "source_parity": True,
            "starts_and_finishes_reconciled": True, "physical_calls": MAX_CALLS, "retries": 0,
            "model_cost_cap_usd": str(LIMIT)}}
    save("scores.json", result)
    save("invalid-outputs.json", [issue for issue in issues if issue["invalid_fields"]])
    save("disagreements.json", [row for row in rows if not row["correct"]])
    print(json.dumps({"summary": summary, "issues": len(issues), "usage": usage,
        "audit": result["audit"]}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "selfcheck", "verify", "transport-check", "preflight", "refresh", "submit", "collect", "score"))
    action = parser.parse_args().action
    globals()[action.replace("-", "_")]()
