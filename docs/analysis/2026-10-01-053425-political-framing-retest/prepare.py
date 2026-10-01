"""Freeze shared retest inputs. No app imports, network calls, or old writes."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
JEV_BASE = HERE.parent / "2026-09-30-070427-jev-multilingual-classification"
DS_BASE = HERE.parent / "2026-09-30-074728-0731-multilingual-comparison"
FRAMEWORK_OLD = (
    "Does geopolitical mode framework apply? It explains/predicts relationships "
    "among states, policy, markets, security, national systems, or state actors. "
)
FRAMEWORK_NEW = (
    "Does political mode framework apply? Does the post explain or predict "
    "relationships between countries, or how governments and political systems "
    "shape policy, markets, or national security? "
    "The post itself must supply the political connection. Ordinary company "
    "competition, product comparisons, or technical discussion alone do not qualify. "
)
GEO_FIELDS = {"geo:reporting", "geo:framework", "geo:nationalism"}


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def load(name):
    return json.loads((HERE / name).read_text())


def save(name, value):
    with (HERE / name).open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def revised_questions(old):
    result = deepcopy(old)
    assert len(old) == 38
    for key in ("geo:reporting", "geo:nationalism"):
        text = result[key]["instructions"]
        assert text.count("geopolitical mode") == 1
        text = text.replace("geopolitical mode", "political mode")
        if key == "geo:reporting":
            assert text.count("a geopolitical claim") == 1
            text = text.replace("a geopolitical claim", "a political claim")
        result[key]["instructions"] = text
    text = result["geo:framework"]["instructions"]
    assert text.count(FRAMEWORK_OLD) == 1
    result["geo:framework"]["instructions"] = text.replace(FRAMEWORK_OLD, FRAMEWORK_NEW)
    assert {key for key in old if old[key] != result[key]} == GEO_FIELDS
    for key in GEO_FIELDS:
        assert old[key]["criteria"] == result[key]["criteria"]
        assert old[key]["type"] == result[key]["type"] == "noul"
    return result


def load_requests():
    requests = load("requests.json")
    assert len(requests) == 117
    assert len({r["request_id"] for r in requests}) == 117
    for item in requests:
        assert item["arm"] == "raw"
        assert digest(item["request"]) == item["sha256"]
        assert item["request"]["model"] == "jev-1.13.0"
        assert len(item["request"]["questions"]) == 38
    return requests


def verify():
    frozen = load("frozen.json")
    for name, expected in frozen["files"].items():
        assert file_digest(HERE / name) == expected, name
    for section in ("baseline_files", "protected_files"):
        for name, expected in frozen[section].items():
            assert file_digest(REPO / name) == expected, name
    load_requests()
    return frozen


def prepare():
    assert not (HERE / "frozen.json").exists(), "already prepared; do not overwrite"
    old = json.loads((JEV_BASE / "requests.json").read_text())
    raw = [r for r in old if r["arm"] == "raw"]
    assert len(raw) == 117 and len(old) == 185
    questions = revised_questions(raw[0]["request"]["questions"])
    requests = deepcopy(raw)
    for item, baseline in zip(requests, raw, strict=True):
        assert baseline["request"]["questions"] == raw[0]["request"]["questions"]
        assert digest(baseline["request"]) == baseline["sha256"]
        item["request"]["questions"] = deepcopy(questions)
        item["sha256"] = digest(item["request"])
        assert item["request"]["state"] == baseline["request"]["state"]
        assert item["request_id"] == baseline["request_id"]
    refs = json.loads((JEV_BASE / "references.json").read_text())
    assert set(refs["references"]) == {r["case_id"] for r in raw}
    assert all(set(refs["references"][r["case_id"]]["expected"]) == set(questions) for r in raw)
    save("questions.json", questions)
    save("requests.json", requests)
    with (HERE / "references.json").open("xb") as stream:
        stream.write((JEV_BASE / "references.json").read_bytes())
    save("prompt-diff.json", {k: {"before": raw[0]["request"]["questions"][k], "after": questions[k]} for k in sorted(GEO_FIELDS)})
    baselines = [JEV_BASE / n for n in ("requests.json", "references.json", "scores.json", "questions.py", "run.py", "frozen.json")]
    baselines += [DS_BASE / n for n in ("requests.json", "scores.json", "packet.json", "run.py", "remote.py", "frozen.json")]
    baseline_hashes = {str(p.relative_to(REPO)): file_digest(p) for p in baselines}
    protected = ("config.yaml", "render.yaml", "x_monitor/attribution.py", "x_monitor/classifier_0731_prompts.py", "x_monitor/deepinfra.py", "tests/test_u18_runtime_0731.py", "tests/test_u18a_v4_classification_persistence.py")
    save("frozen.json", {
        "at": now(), "cases": 117, "questions_per_case": 38,
        "changed_question_fields": sorted(GEO_FIELDS), "state_parity_verified": True,
        "unchanged_questions_per_case": 35, "reference_bytes_identical": True,
        "languages": dict(Counter(r["language"] for r in raw)),
        "max_calls_per_provider": 117, "max_combined_calls": 234,
        "max_usd_per_provider": "0.25", "max_combined_usd": "0.50",
        "concurrency_per_provider": 1, "retries": 0, "deadline_seconds_per_provider": 3600,
        "models": {"jev": "jev-1.13.0", "0731": "deepseek-ai/DeepSeek-V4-Flash-0731"},
        "files": {n: file_digest(HERE / n) for n in ("contract.md", "prepare.py", "questions.json", "requests.json", "references.json", "prompt-diff.json")},
        "baseline_files": baseline_hashes,
        "protected_files": {n: file_digest(REPO / n) for n in protected},
        "provider_calls_at_freeze": 0,
    })
    verify()
    print(json.dumps({"prepared": True, "cases": 117, "changed_fields": sorted(GEO_FIELDS), "state_parity": True, "provider_calls": 0, "manifest_sha256": file_digest(HERE / "frozen.json")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "verify"))
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    else:
        result = verify()
        print(json.dumps({"verified": True, "cases": result["cases"], "manifest_sha256": file_digest(HERE / "frozen.json")}))
