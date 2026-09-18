"""Provider-isolation experiments for DeepSeek V4 Flash 0731 on DeepInfra.

This helper replays the frozen classifier diagnostic24 and random100
translation/commentary contracts directly against DeepInfra. It records every
billable attempt and never imports Django settings or writes application data.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import fcntl
import importlib.util
import json
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import model_classifier_experiment as classifier
from scripts import u20_random100_live as random100
from scripts import u18_fresh40_v4_0731_reasoning as r122_normalizer
from x_monitor.literal_translation import translate_batch_literal_plaintext
from x_monitor.provider_telemetry import ProviderResponse, ProviderTextResponse
from x_monitor.synthesis import synthesize_post

TRANSPORT_PATH = ROOT / ".context/model-task-20260918/deepinfra-gemma4-commentary-tagged-runner.py"
CLASSIFIER_INPUT = ROOT / ".context/model-task-20260917/classifier-input.json"
RANDOM100 = ROOT / ".context/u20/random100-live-20260917-125626"
R122 = ROOT / ".context/u18/fresh45-v4-0731-best-r122-v1"
LEDGER = ROOT / ".context/model-task-20260917/portfolio-ledger.json"
LOCK = ROOT / ".context/model-task-20260917/.portfolio.lock"
MODEL = "deepseek-ai/DeepSeek-V4-Flash-0731"
TASK_KEY = "deepseek-ai/DeepSeek-V4-Flash-0731|direct"
INPUT_PRICE = 0.06
OUTPUT_PRICE = 0.18
MAX_ATTEMPTS = 3
WALL_SECONDS = 3600


def _load_transport() -> Any:
    spec = importlib.util.spec_from_file_location("direct_deepinfra_transport", TRANSPORT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("direct DeepInfra transport unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


transport = _load_transport()


def now() -> str:
    return datetime.now(UTC).isoformat()


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def strip_fence(text: str) -> str:
    matched = re.fullmatch(r"\s*```(?:json)?\s*\n?(.*?)\n?```\s*", text, re.DOTALL | re.IGNORECASE)
    return matched.group(1) if matched else text


def direct_request(original: dict[str, Any], *, json_mode: bool = False) -> dict[str, Any]:
    request: dict[str, Any] = {
        "model": MODEL,
        "messages": original["messages"],
        "max_tokens": min(int(original["max_tokens"]), 16_384),
        "temperature": float(original.get("temperature", 1.0)),
        "top_p": float(original.get("top_p", 1.0)),
        "seed": int(original.get("seed", 42)),
        "reasoning_effort": "none",
    }
    if json_mode:
        request["response_format"] = {"type": "json_object"}
    return request


def validate_response(response: Any) -> tuple[str, dict[str, Any]]:
    if not isinstance(response, dict) or response.get("model") != MODEL:
        raise ValueError("DeepInfra 0731 model identity mismatch")
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise ValueError("DeepInfra 0731 choices invalid")
    if choices[0].get("finish_reason") != "stop":
        raise ValueError("DeepInfra 0731 completion incomplete")
    message = choices[0].get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise ValueError("DeepInfra 0731 content missing")
    raw_usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
    usage = {
        "input_tokens": raw_usage.get("prompt_tokens"),
        "output_tokens": raw_usage.get("completion_tokens"),
        "total_tokens": raw_usage.get("total_tokens"),
        "cache_read_input_tokens": (raw_usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0),
        "reasoning_tokens": (raw_usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0),
        "cost_usd": raw_usage.get("estimated_cost"),
        "provider_request_id": response.get("id"),
        "provider": "DeepInfra",
        "model": response.get("model"),
        "selected_endpoint": "direct",
        "request_provider": "DeepInfra",
        "request_identity": "deepinfra-direct:deepseek-v4-flash-0731",
        "data_collection": "zero-retention-public-model",
        "service_tier": response.get("service_tier") or "standard",
    }
    if not all(isinstance(usage[key], int) for key in ("input_tokens", "output_tokens", "total_tokens")):
        raise ValueError("DeepInfra 0731 token receipt missing")
    if not isinstance(usage["cost_usd"], (int, float)):
        raise ValueError("DeepInfra 0731 cost receipt missing")
    return content, usage


def _request_matches(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    normalized = dict(actual)
    normalized["model"] = expected["model"]
    return normalized == expected


class DirectCaller:
    def __init__(self, original: list[dict[str, Any]], sender: Any, probe: dict[str, Any], *, json_mode: bool) -> None:
        self.original = original
        self.sender = sender
        self.probe = probe
        self.cursor = 0
        self.request_profile = "deepseek_0731"
        self.measurements: list[dict[str, Any]] = []
        self.json_mode = json_mode

    def _call(self, kwargs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        if self.cursor >= len(self.original):
            raise ValueError("caller exceeded frozen request count")
        expected = self.original[self.cursor]
        if not _request_matches(expected, kwargs):
            raise ValueError("caller request differs from frozen contract")
        request = direct_request(expected, json_mode=self.json_mode)
        started = time.monotonic()
        result = self.probe if self.cursor == 0 else self.sender.send(self.cursor, request)
        final = result["attempts"][-1]
        measurement: dict[str, Any] = {
            "sequence": self.cursor,
            "request_sha256": random100.digest(expected),
            "direct_request_sha256": transport.digest(request),
            "status": final["state"],
            "latency_ms": final.get("latency_ms", round((time.monotonic() - started) * 1000)),
        }
        self.cursor += 1
        if final["state"] != "received":
            self.measurements.append(measurement)
            raise ValueError("DeepInfra 0731 transport " + str(final["state"]))
        content, usage = validate_response(final["response"])
        measurement["usage"] = usage
        self.measurements.append(measurement)
        return content, usage

    def messages_create_text(self, **kwargs: Any) -> ProviderTextResponse:
        content, usage = self._call(dict(kwargs))
        return ProviderTextResponse(text=content, provider_usage=usage)

    def messages_create(self, **kwargs: Any) -> ProviderResponse:
        request = dict(kwargs)
        # The OpenRouter 0731 adapter injected these sampler controls after
        # the synthesis caller built its generic request. Preserve them when
        # matching and replaying the frozen request directly.
        request.update(temperature=1.0, top_p=1.0, seed=42)
        content, usage = self._call(request)
        try:
            value = json.loads(strip_fence(content))
        except (TypeError, ValueError) as exc:
            raise ValueError("DeepInfra 0731 commentary JSON invalid") from exc
        if not isinstance(value, dict):
            raise ValueError("DeepInfra 0731 commentary shape invalid")
        return ProviderResponse(value, usage=usage)


def reserve(trial: Path, task: str, requests: list[dict[str, Any]]) -> dict[str, Any]:
    input_bound = sum((len(transport.canonical(direct_request(item))) + 2) // 3 for item in requests)
    output_bound = sum(min(int(item["max_tokens"]), 16_384) for item in requests)
    amount = round((input_bound * INPUT_PRICE + output_bound * OUTPUT_PRICE) / 1_000_000 * MAX_ATTEMPTS, 8)
    with LOCK.open("a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        ledger = read(LEDGER)
        key = TASK_KEY + "|" + task
        task_row = ledger["attempts"].setdefault(key, {"profiles": {}, "reserved_usd": 0.0})
        if float(ledger["reserved_usd"]) + amount > 30 or float(task_row["reserved_usd"]) + amount > 3:
            raise ValueError("experiment reservation exceeds cap")
        reservations = ledger.setdefault("direct_provider_reservations", {})
        if trial.name in reservations:
            raise ValueError("trial already reserved")
        reservations[trial.name] = {"reserved_usd": amount, "model_task": key, "reason": "Delivery Exception 40 direct DeepInfra 0731", "created_at": now()}
        ledger["reserved_usd"] = float(ledger["reserved_usd"]) + amount
        task_row["reserved_usd"] = float(task_row["reserved_usd"]) + amount
        task_row["profiles"]["deepinfra_0731_direct_v1"] = 1
        write(LEDGER, ledger)
    receipt = {"reserved_usd": amount, "portfolio_after_usd": ledger["reserved_usd"], "task_after_usd": task_row["reserved_usd"]}
    write(trial / "reservation-check.json", receipt)
    return receipt


def classifier_entries() -> list[dict[str, Any]]:
    packet = read(CLASSIFIER_INPUT)
    rows = classifier._source_rows(packet, "diagnostic")
    profile = classifier._profile("deepseek_0731_classifier_current_v1")
    entries: list[dict[str, Any]] = []
    for source in rows:
        tweet = classifier._tweet(source)
        decisions, posts, envelope = classifier._slots([tweet])
        for role in ("content", "brand_interpretation"):
            original = classifier._request(envelope, role, profile)
            # The selected OpenRouter route injected these sampler controls at
            # transport time; freeze them explicitly for the direct route.
            original.update(temperature=1.0, top_p=1.0, seed=42)
            entries.append({
                "source_post_id": tweet["tweet_id"], "role": role,
                "source_evidence": [tweet], "decisions": decisions, "posts": posts,
                "original_request": original,
                "direct_request": direct_request(original),
            })
    if len(entries) != 48:
        raise ValueError("classifier diagnostic must contain 48 calls")
    return entries


def task_requests(task: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if task == "classification":
        entries = classifier_entries()
        return [entry["direct_request"] for entry in entries], entries
    if task == "classification_r122":
        packets = read(R122 / "packets.json")
        frozen = read(R122 / "requests.json")
        entries = []
        start = 0
        for batch_index, size in enumerate((20, 20, 5)):
            batch = packets[start:start + size]
            start += size
            for role in ("content", "brand"):
                original = frozen[role][batch_index]
                entries.append({
                    "batch_index": batch_index + 1,
                    "role": role,
                    "packets": batch,
                    "original_request": original,
                    "direct_request": direct_request(original),
                })
        return [entry["direct_request"] for entry in entries], entries
    contract = read(RANDOM100 / "contract.json")
    requests = read(RANDOM100 / ("translation-requests.json" if task == "translation" else "commentary-requests.json"))
    expected = contract["request_sha256"][task]
    if random100.digest(requests) != expected:
        raise ValueError("frozen random100 requests changed")
    return [direct_request(item) for item in requests], requests


def prepare(task: str, trial: Path) -> dict[str, Any]:
    if trial.exists():
        raise ValueError("trial directory exists")
    direct, source = task_requests(task)
    manifest = {
        "schema": "deepinfra-0731-direct/v1", "created_at": now(), "task": task,
        "route": {"provider": "DeepInfra", "endpoint": transport.ENDPOINT, "model": MODEL, "tier": "standard", "input_usd_per_million": INPUT_PRICE, "output_usd_per_million": OUTPUT_PRICE},
        "request_count": len(direct), "direct_requests_sha256": transport.digest(direct),
        "source_contract": str(CLASSIFIER_INPUT if task == "classification" else R122 / "contract.json" if task == "classification_r122" else RANDOM100 / "contract.json"),
        "source_request_sha256": transport.digest(source),
        "shape": {"reasoning_effort": "none", "temperature": 1.0, "top_p": 1.0, "seed": 42, "max_concurrency": 1, "max_attempts": MAX_ATTEMPTS},
        "safety": {"database_writes": False, "runtime_changes": False, "fallbacks": 0},
    }
    write(trial / "manifest.json", manifest)
    write(trial / "source-requests.json", source)
    write(trial / "direct-requests.json", direct)
    reserve(trial, task, [entry["original_request"] for entry in source] if task in {"classification", "classification_r122"} else source)
    return manifest


def probe(trial: Path) -> dict[str, Any]:
    manifest = read(trial / "manifest.json")
    requests = read(trial / "direct-requests.json")
    if transport.digest(requests) != manifest["direct_requests_sha256"]:
        raise ValueError("direct request signature mismatch")
    sender = transport.Sender(transport.secret_from_env_file("DEEPINFRA_API_KEY"), trial, time.monotonic() + WALL_SECONDS)
    result = sender.send(0, requests[0])
    final = result["attempts"][-1]
    output: dict[str, Any] = {"status": "failed_transport", "result": result}
    if final["state"] == "received":
        try:
            content, usage = validate_response(final["response"])
            if manifest["task"] == "classification":
                entry = read(trial / "source-requests.json")[0]
                value = json.loads(strip_fence(content), object_pairs_hook=classifier._no_duplicate_keys)
                parsed = classifier._parse(value, entry["decisions"], entry["posts"], entry["role"], profile_key="deepseek_0731_classifier_current_v1")
                if not parsed:
                    raise ValueError("classifier probe failed local contract")
            elif manifest["task"] == "classification_r122":
                entry = read(trial / "source-requests.json")[0]
                _parse_r122(final["response"], entry)
            elif manifest["task"] == "commentary":
                value = json.loads(strip_fence(content))
                expected = {"post_id", "commentary_en", "commentary_zh_cn", "commentary_ja"}
                if not isinstance(value, dict) or set(value) != expected:
                    raise ValueError("commentary probe failed local contract")
            output = {"status": "passed", "result": result, "usage": usage}
        except (TypeError, ValueError) as exc:
            output = {"status": "failed_validation", "result": result, "error": str(exc)}
    write(trial / "probe-result.json", output)
    return output


def run_classification(trial: Path, probe_result: dict[str, Any]) -> dict[str, Any]:
    entries = read(trial / "source-requests.json")
    sender = transport.Sender(transport.secret_from_env_file("DEEPINFRA_API_KEY"), trial, time.monotonic() + WALL_SECONDS)
    results = {0: probe_result["result"]}
    for index in range(1, len(entries)):
        records = sorted((trial / "attempt-records").glob(f"{index:04d}-attempt-*.json"))
        if records:
            results[index] = {
                "request_sha256": transport.digest(entries[index]["direct_request"]),
                "attempts": [read(path) for path in records],
            }
        elif list((trial / "consumed").glob(f"{index:04d}-attempt-*.json")):
            # A process interruption after the durable consumed marker but
            # before its response receipt is ambiguous and must not be retried.
            results[index] = {
                "request_sha256": transport.digest(entries[index]["direct_request"]),
                "attempts": [{"attempt": 1, "state": "operator_interrupted", "status_code": None, "error": "consumed_without_response_receipt"}],
            }
        else:
            results[index] = sender.send(index, entries[index]["direct_request"])
    outputs = []
    for index, entry in enumerate(entries):
        final = results[index]["attempts"][-1]
        row: dict[str, Any] = {"source_post_id": entry["source_post_id"], "role": entry["role"], "status": final["state"], "parsed": {}, "error": None}
        try:
            content, usage = validate_response(final.get("response"))
            value = json.loads(strip_fence(content), object_pairs_hook=classifier._no_duplicate_keys)
            row["parsed"] = classifier._parse(value, entry["decisions"], entry["posts"], entry["role"], profile_key="deepseek_0731_classifier_current_v1")
            if not row["parsed"]:
                raise ValueError("classifier response failed local contract")
            row["usage"] = usage
            row["structured_output"] = value
            row["status"] = "complete"
        except Exception as exc:  # Preserve paid malformed outputs without retry.
            row["error"] = str(exc)
        outputs.append(row)
    return finalize(trial, results, {"rows": outputs, "source_post_ids": sorted({row["source_post_id"] for row in outputs}), "complete_calls": sum(row["status"] == "complete" for row in outputs)})


def _parse_r122(response: dict[str, Any], entry: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    validate_response(response)
    # The retained parser validates the old OpenRouter envelope before parsing
    # model content. Supply only those attestation fields locally; raw direct
    # evidence remains unchanged in attempt-records.
    compatible = deepcopy(response)
    compatible["model"] = r122_normalizer.baseline.MODEL
    compatible["provider"] = r122_normalizer.baseline.PROVIDER
    compatible["openrouter_metadata"] = {"endpoints": {"available": [{"selected": True, "provider": r122_normalizer.baseline.PROVIDER}]}}
    return r122_normalizer.parse(compatible, entry["packets"], entry["role"])


def run_classification_r122(trial: Path, probe_result: dict[str, Any]) -> dict[str, Any]:
    entries = read(trial / "source-requests.json")
    sender = transport.Sender(transport.secret_from_env_file("DEEPINFRA_API_KEY"), trial, time.monotonic() + WALL_SECONDS)
    results = {0: probe_result["result"]}
    for index in range(1, len(entries)):
        results[index] = sender.send(index, entries[index]["direct_request"])
    roles: dict[str, list[dict[str, Any]]] = {"content": [], "brand": []}
    issues: list[dict[str, Any]] = []
    normalization: list[dict[str, Any]] = []
    failures = []
    calls = []
    for index, entry in enumerate(entries):
        final = results[index]["attempts"][-1]
        record = {"batch": entry["batch_index"], "role": entry["role"], "status": final["state"], "error": None}
        try:
            rows, raw_issues, changes = _parse_r122(final["response"], entry)
            roles[entry["role"]].extend(rows)
            issues.extend({"call": f'{entry["batch_index"]}-{entry["role"]}', **item} for item in raw_issues)
            normalization.extend({"call": f'{entry["batch_index"]}-{entry["role"]}', **item} for item in changes)
            record["status"] = "complete"
        except Exception as exc:
            record["error"] = str(exc)
            failures.append(record)
        calls.append(record)
    task_result = {"roles": roles, "calls": calls, "raw_issues": issues, "representation_normalization": normalization, "failures": failures}
    return finalize(trial, results, task_result)


def _context(row: dict[str, Any]) -> dict[str, str]:
    output = {"post": row["text"]}
    for item in row["context"]:
        if item.get("provenance") and item.get("text"):
            output[str(item["provenance"])] = str(item["text"])
    return output


def run_translation(trial: Path, probe_result: dict[str, Any]) -> dict[str, Any]:
    contract = read(RANDOM100 / "contract.json")
    original = read(trial / "source-requests.json")
    sender = transport.Sender(transport.secret_from_env_file("DEEPINFRA_API_KEY"), trial, time.monotonic() + WALL_SECONDS)
    caller = DirectCaller(original, sender, probe_result["result"], json_mode=False)
    cfg = SimpleNamespace(llm=SimpleNamespace(translator_model=MODEL, translator_base_url="https://api.deepinfra.com/v1/openai"))
    tweets = [{"tweet_id": row["post_id"], "text": row["text"], "source_language": row.get("source_language")} for row in contract["rows"]]
    rows = translate_batch_literal_plaintext(tweets, caller, cfg=cfg, max_workers=1, paragraph_tracking=True)
    if caller.cursor != len(original):
        raise ValueError("translation caller did not consume frozen requests")
    results = {0: probe_result["result"], **sender.results}
    return finalize(trial, results, {"rows": rows, "measurements": caller.measurements, "failed_rows": sum(bool(row.get("translation_failed")) for row in rows)})


def run_commentary(trial: Path, probe_result: dict[str, Any]) -> dict[str, Any]:
    contract = read(RANDOM100 / "contract.json")
    original = read(trial / "source-requests.json")
    sender = transport.Sender(transport.secret_from_env_file("DEEPINFRA_API_KEY"), trial, time.monotonic() + WALL_SECONDS)
    caller = DirectCaller(original, sender, probe_result["result"], json_mode=False)
    cfg = SimpleNamespace(model=MODEL, max_input_tokens_per_post=4_000, max_output_tokens_per_post=4_000, timeout_seconds=60)
    rows = []
    for source in contract["rows"]:
        try:
            value = synthesize_post(post_id=source["post_id"], context=_context(source), client=caller, config=cfg)
            rows.append({"post_id": source["post_id"], "status": "complete", "texts": value.texts, "input_tokens": value.input_tokens, "output_tokens": value.output_tokens, "latency_ms": value.latency_ms})
        except Exception as exc:
            rows.append({"post_id": source["post_id"], "status": "error", "error_type": type(exc).__name__, "error": str(exc)})
    if caller.cursor != len(original):
        raise ValueError("commentary caller did not consume frozen requests")
    results = {0: probe_result["result"], **sender.results}
    return finalize(trial, results, {"rows": rows, "measurements": caller.measurements, "failed_rows": sum(row["status"] != "complete" for row in rows), "precall_input_cap_rows": len(contract["precall_coverage_failures"]["synthesis_input_cap_rejections"])})


def finalize(trial: Path, results: dict[int, Any], task_result: dict[str, Any]) -> dict[str, Any]:
    finals = [value["attempts"][-1] for value in results.values()]
    received = [item for item in finals if item["state"] == "received"]
    usage = [item.get("usage") or {} for item in received]
    report = {
        "schema": "deepinfra-0731-direct/v1/run-report", "finished_at": now(),
        "manifest_sha256": transport.digest(read(trial / "manifest.json")),
        "task_result": task_result,
        "delivery": {"requested": len(results), "received": len(received), "retry_attempts": sum(len(value["attempts"]) - 1 for value in results.values()), "transport_failures": len(results) - len(received)},
        "usage": {"reported_cost_usd": round(sum(float(row.get("estimated_cost") or 0) for row in usage), 12), "input_tokens": sum(int(row.get("prompt_tokens") or 0) for row in usage), "output_tokens": sum(int(row.get("completion_tokens") or 0) for row in usage)},
        "safety": {"database_writes": False, "runtime_changes": False, "fallbacks": 0},
    }
    write(trial / "run-report.json", report)
    return report


def run(trial: Path) -> dict[str, Any]:
    manifest = read(trial / "manifest.json")
    probe_result = read(trial / "probe-result.json")
    if probe_result.get("status") != "passed":
        raise ValueError("probe did not pass")
    started = time.monotonic()
    task = manifest["task"]
    report = run_classification(trial, probe_result) if task == "classification" else run_classification_r122(trial, probe_result) if task == "classification_r122" else run_translation(trial, probe_result) if task == "translation" else run_commentary(trial, probe_result)
    report["wall_seconds"] = round(time.monotonic() - started, 3)
    write(trial / "run-report.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("task", choices=("classification", "classification_r122", "translation", "commentary"))
    prep.add_argument("trial", type=Path)
    for name in ("probe", "run"):
        command = sub.add_parser(name)
        command.add_argument("trial", type=Path)
    args = parser.parse_args()
    result = prepare(args.task, args.trial) if args.command == "prepare" else probe(args.trial) if args.command == "probe" else run(args.trial)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
