"""Frozen, bounded OpenRouter trials; `live` is the sole paid boundary."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import time
import threading
import re
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from scripts.model_task_profiles import ModelTaskProfile, SNAPSHOT, SNAPSHOT_SHA256, get_profile, profile_manifest, restore_translation_lines, translation_lines
from scripts.u20_translation_synthesis_execute import credential
from x_monitor.literal_translation import translate_batch_literal_plaintext
from x_monitor.openrouter import OpenRouterChatCompletionsClient, OpenRouterPermanentError, _no_duplicate_json_keys
from x_monitor.provider_telemetry import ProviderResponse, ProviderTextResponse
from x_monitor.synthesis import synthesize_post

SCHEMA = "model-task-experiment/v2"
MAX_ATTEMPTS_PER_MODEL_TASK, MAX_MODEL_TASK_USD, MAX_PORTFOLIO_USD, MAX_CONCURRENCY = 3, 3.0, 30.0, 3
ROOT = Path(__file__).resolve().parents[1]

def attempt_limit(model: str, task: str | None = None) -> int:
    # Owner's September 17 continuation is recorded in Delivery Exception 29.
    # The no-reasoning Gemini commentary control is the sole fourth-profile
    # exception; translation and every other model/task retain their limit.
    if model == "qwen/qwen3.7-flash":
        return 6
    if model == "google/gemini-2.5-flash-lite" and task == "commentary":
        return 4
    return 3

def _bytes(value: Any) -> bytes: return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
def digest(value: Any) -> str: return hashlib.sha256(_bytes(value)).hexdigest()
def read(path: Path) -> Any: return json.loads(path.read_text(encoding="utf-8"))
def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
def _caller_hashes() -> dict[str, str]:
    names = ("scripts/model_task_experiment.py", "scripts/model_task_profiles.py", "x_monitor/literal_translation.py", "x_monitor/synthesis.py", "x_monitor/openrouter.py")
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in names}

def _context(row: dict[str, Any]) -> dict[str, str]:
    """Exact U20 context-list conversion; do not invent a context object."""
    result = {"post": row["text"]}
    for item in row["context"]:
        if isinstance(item, dict) and item.get("provenance") and item.get("text"):
            result[str(item["provenance"])] = str(item["text"])
    return result

class ProfileCaptureClient:
    def __init__(self, profile: ModelTaskProfile) -> None: self.profile, self.requests = profile, []
    def _request(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        request = self.profile.apply(kwargs); self.requests.append(request); return request
    def messages_create_text(self, **kwargs: Any) -> ProviderTextResponse:
        request = self._request(kwargs)
        if self.profile.prompt_style in {"structured_translation_lines", "interpret_then_translate", "interpreted_translation_glossary", "luna_structured_source_bound_translation"}:
            original = kwargs["messages"][0]["content"]
            return ProviderTextResponse(restore_translation_lines(translation_lines(original)[1], original), {})
        return ProviderTextResponse(request["messages"][0]["content"].split("SOURCE:\n", 1)[-1], {})
    def messages_create(self, **kwargs: Any) -> dict[str, Any]:
        request = self._request(kwargs)
        payload = request["messages"][1]["content"] if self.profile.prompt_style in {"source_bound_commentary", "luna_source_bound_commentary", "luna_source_bound_commentary_v3"} else request["messages"][0]["content"].split(" Input: ", 1)[1]
        post_id = json.loads(payload)["post_id"]
        return {"post_id": post_id, "commentary_en": "English", "commentary_zh_cn": "中文", "commentary_ja": "日本語"}

def _rows(value: Any) -> list[dict[str, Any]]:
    rows = value.get("rows") if isinstance(value, dict) else value
    if not isinstance(rows, list) or not rows: raise ValueError("input must contain nonempty rows")
    normalized = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("post_id"), str) or not isinstance(row.get("text"), str): raise ValueError("each row needs string post_id and text")
        if not isinstance(row.get("context", []), list): raise ValueError("context must be the frozen context list")
        normalized.append({"post_id": row["post_id"], "text": row["text"], "source_language": row.get("source_language"), "context": row.get("context", [])})
    if len({row["post_id"] for row in normalized}) != len(normalized): raise ValueError("duplicate source post")
    return normalized

def capture_requests(profile: ModelTaskProfile, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    client = ProfileCaptureClient(profile)
    if profile.task == "translation":
        cfg = SimpleNamespace(llm=SimpleNamespace(translator_model=profile.model, translator_base_url="https://openrouter.ai/api/v1"))
        translate_batch_literal_plaintext([{"tweet_id": row["post_id"], "text": row["text"], "source_language": row["source_language"]} for row in rows], client, cfg=cfg, max_workers=1, paragraph_tracking=True)
    else:
        cfg = SimpleNamespace(model=profile.model, max_output_tokens_per_post=_visible_output_limit(profile), max_input_tokens_per_post=32_000, timeout_seconds=profile.timeout_seconds)
        for row in rows: synthesize_post(post_id=row["post_id"], context=_context(row), client=client, config=cfg)
    return client.requests


def _visible_output_limit(profile: ModelTaskProfile) -> int:
    """Keep a profile's documented reasoning reserve outside caller-visible output."""
    visible = profile.max_output_tokens - profile.reasoning_headroom_tokens
    if visible <= 0:
        raise ValueError("reasoning headroom leaves no visible output budget")
    return visible

def _reservation(profile: ModelTaskProfile, requests: list[dict[str, Any]]) -> float:
    return sum((len(_bytes(request)) * float(profile.input_usd_per_million) + int(request["max_tokens"]) * float(profile.output_usd_per_million)) / 1_000_000 for request in requests)

def prepare(input_path: Path, directory: Path, profile_key: str) -> dict[str, Any]:
    if directory.exists() and any(directory.iterdir()): raise ValueError("experiment directory already exists")
    profile, rows = get_profile(profile_key), _rows(read(input_path))
    if hashlib.sha256((Path(profile.snapshot_path) / "manifest.json").read_bytes()).hexdigest() != profile.snapshot_sha256: raise ValueError("saved pricing snapshot changed")
    if profile.task == "translation" and any(row["source_language"] not in {"en", "zh-Hans", "zh-Hant", "ja", "ko", "other"} for row in rows):
        raise ValueError("translation trials require a frozen allowlisted source_language; freeze detection separately")
    requests = capture_requests(profile, rows)
    if profile.model == "qwen/qwen3.7-flash" and any(len(_bytes(request["messages"])) >= 32000 for request in requests):
        raise ValueError("Qwen request exceeds conservative first-tier input bound; price a larger-tier profile")
    if not requests: raise ValueError("actual caller captured no requests")
    reserved = _reservation(profile, requests)
    if reserved > MAX_MODEL_TASK_USD: raise ValueError("frozen model/task reservation exceeds $3")
    contract = {"schema": SCHEMA, "created_at": datetime.now(UTC).isoformat(), "profile": profile_manifest(profile), "source_rows_sha256": digest(rows), "rows": rows, "caller_sha256": _caller_hashes(), "requests": requests, "request_sha256": digest(requests), "reserved_cost_usd": reserved, "limits": {"attempts_per_model_task": attempt_limit(profile.model, profile.task), "model_task_usd": 3, "portfolio_usd": 30, "max_concurrency": profile.max_concurrency, "min_request_interval_seconds": profile.min_request_interval_seconds}, "safety": {"no_retries_or_fallback": True, "consume_marker_before_send": True, "database_writes": False, "pricing": "saved_snapshot_only"}}
    contract["contract_sha256"] = digest(contract)
    write(directory / "contract.json", contract); return contract

@contextmanager
def _lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as handle:
        try: fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc: raise ValueError("experiment already running") from exc
        yield

def _load_contract(directory: Path) -> dict[str, Any]:
    contract = read(directory / "contract.json")
    signed = dict(contract); signature = signed.pop("contract_sha256", None)
    if signature != digest(signed): raise ValueError("frozen contract changed")
    if contract.get("schema") != SCHEMA or digest(contract.get("requests")) != contract.get("request_sha256") or digest(contract.get("rows")) != contract.get("source_rows_sha256") or contract.get("caller_sha256") != _caller_hashes(): raise ValueError("frozen contract changed")
    profile = get_profile(contract["profile"]["profile"])
    if contract["profile"].get("profile_sha256") != profile.profile_hash: raise ValueError("frozen profile changed")
    return contract

def _validate_offline(profile: ModelTaskProfile, value: Any) -> tuple[bool, str | None]:
    if profile.task == "translation": return isinstance(value, str) and bool(value.strip()), "missing_or_empty_translation"
    ok = isinstance(value, dict) and set(value) == {"post_id", "commentary_en", "commentary_zh_cn", "commentary_ja"} and all(isinstance(value.get(key), str) and value[key].strip() for key in ("commentary_en", "commentary_zh_cn", "commentary_ja"))
    return ok, None if ok else "commentary_schema_or_locale_incomplete"

def run(directory: Path, responses_path: Path, *, attempt: int = 1) -> dict[str, Any]:
    """Offline fixture replay only; it never reads credentials or transports."""
    with _lock(directory.parent / ".portfolio.lock"), _lock(directory / ".run.lock"):
        contract = _load_contract(directory)
        if not 1 <= attempt <= 3: raise ValueError("attempt exceeds per-model/task limit")
        marker = directory / f"attempt-{attempt}.offline.json"
        if marker.exists(): return read(marker)
        raw = read(responses_path)
        if not isinstance(raw, dict): raise ValueError("responses must map request sha256 to raw response")
        profile, requests = get_profile(contract["profile"]["profile"]), contract["requests"]; ids = [digest(request) for request in requests]
        if set(raw) - set(ids): raise ValueError("response not in frozen request set")
        outputs = []
        for identity in ids:
            ok, error = _validate_offline(profile, raw.get(identity)); outputs.append({"request_sha256": identity, "status": "delivered" if ok else "missing_output", "error": error, "raw_response": raw.get(identity)})
        report = {"schema": SCHEMA + "/offline-report", "attempt": attempt, "profile": contract["profile"], "request_count": len(outputs), "outputs": outputs, "delivery": {"missing_outputs": sum(item["status"] != "delivered" for item in outputs), "complete": all(item["status"] == "delivered" for item in outputs)}, "semantic": "unassessed", "quality_gate": {"status": "not_assessed_without_independent_semantic_and_structural_review"}, "errors": [item for item in outputs if item["error"]]}
        write(marker, report); return report

def _live_client(profile: ModelTaskProfile) -> OpenRouterChatCompletionsClient:
    return OpenRouterChatCompletionsClient(api_key=credential("0731"), model=profile.model, provider=profile.provider_name, response_provider=profile.provider_name, response_model=profile.upstream_model, endpoint_tag=profile.endpoint_tag, reasoning_enabled=False, data_collection="allow", max_input_price=float(profile.input_usd_per_million), max_output_price=float(profile.output_usd_per_million), service_tier=profile.service_tier)

class FrozenLiveTransport:
    """Exact caller protocol; every per-request file appears before its POST."""
    def __init__(self, profile: ModelTaskProfile, requests: list[dict[str, Any]], attempt_directory: Path, *, clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep) -> None:
        self.profile, self.requests, self.attempt_directory = profile, list(enumerate(requests)), attempt_directory; self.client = _live_client(profile); self.measurements: list[dict[str, Any]] = []; self.request_lock = threading.Lock(); self.clock, self.sleep = clock, sleep; self.pacing_lock = threading.Lock(); self.last_send_started_at: float | None = None
    def _next(self, kwargs: dict[str, Any], kind: str) -> tuple[dict[str, Any], str]:
        request = self.profile.apply(kwargs)
        with self.request_lock:
            position = next((i for i, (_, expected) in enumerate(self.requests) if request == expected), None)
            if position is None: raise ValueError("real caller request differs from frozen request")
            index, _ = self.requests.pop(position)
        payload_sha256 = digest(request); identity = f"{index:04d}-{payload_sha256}"; marker = self.attempt_directory / "requests" / f"{identity}.json"; marker.parent.mkdir(parents=True, exist_ok=True)
        try:
            with marker.open("x", encoding="utf-8") as handle: json.dump({"request_identity": identity, "request_sha256": payload_sha256, "kind": kind, "consumed_at": datetime.now(UTC).isoformat(), "state": "consumed_before_send"}, handle)
        except FileExistsError as exc: raise ValueError("request was already consumed") from exc
        return request, identity
    def _pace_send_start(self) -> tuple[float, int]:
        """Enforce a profile's start-to-start interval without retrying a request."""
        with self.pacing_lock:
            now = self.clock()
            wait = 0.0
            if self.last_send_started_at is not None:
                wait = max(0.0, self.profile.min_request_interval_seconds - (now - self.last_send_started_at))
                if wait:
                    self.sleep(wait)
                    now = self.clock()
            self.last_send_started_at = now
            return now, round(wait * 1000)
    def _send(self, request: dict[str, Any], identity: str) -> tuple[dict[str, Any], dict[str, Any], str]:
        marker = self.attempt_directory / "requests" / f"{identity}.json"; started, pacing_wait_ms = self._pace_send_start()
        try:
            wire = dict(request); timeout = wire.pop("timeout"); decoded = self.client._send_request(wire, timeout=timeout); usage, choice = self.client._validated_response(decoded); finish = choice.get("finish_reason")
            if self.profile.service_tier and usage.get("service_tier") != self.profile.service_tier:
                raise OpenRouterPermanentError("openrouter_response_service_tier_mismatch", provider_usage=usage)
            if finish != "stop": raise OpenRouterPermanentError("openrouter_response_incomplete", provider_usage=usage)
            content = self.client._choice_content(choice, usage); record = {"request_identity": identity, "request_sha256": identity.split("-", 1)[1], "state": "received", "raw_response": decoded, "usage": usage, "finish_reason": finish, "model": usage.get("model"), "provider": usage.get("provider"), "pacing_wait_ms": pacing_wait_ms, "latency_ms": round((self.clock() - started) * 1000)}; write(marker, record); self.measurements.append(record); return decoded, usage, content
        except Exception as exc:
            record = {"request_identity": identity, "request_sha256": identity.split("-", 1)[1], "state": "transport_error", "error_type": type(exc).__name__, "error": str(exc), "usage": getattr(exc, "provider_usage", None), "pacing_wait_ms": pacing_wait_ms, "latency_ms": round((self.clock() - started) * 1000)}
            if "decoded" in locals(): record["raw_response"] = decoded
            write(marker, record); self.measurements.append(record); raise
    def messages_create_text(self, **kwargs: Any) -> ProviderTextResponse:
        request, identity = self._next(kwargs, "text"); _, usage, content = self._send(request, identity)
        if self.profile.prompt_style in {"structured_translation_lines", "interpret_then_translate", "interpreted_translation_glossary", "luna_structured_source_bound_translation"}:
            try:
                value = json.loads(content, object_pairs_hook=_no_duplicate_json_keys)
                expected = {"source_reading", "lines"} if self.profile.prompt_style in {"interpret_then_translate", "interpreted_translation_glossary"} else {"lines"}
                if not isinstance(value, dict) or set(value) != expected:
                    raise ValueError("translation object has unexpected fields")
                if "source_reading" in expected and (not isinstance(value["source_reading"], str) or not value["source_reading"].strip()):
                    raise ValueError("source reading is missing")
                source_lines = translation_lines(kwargs["messages"][0]["content"])[1]
                if not isinstance(value["lines"], list) or len(value["lines"]) != len(source_lines):
                    raise ValueError("translation line count mismatch")
                for source, translated in zip(source_lines, value["lines"]):
                    if not isinstance(translated, str) or re.findall(r"\[\[PQ[^\]]+\]\]", source) != re.findall(r"\[\[PQ[^\]]+\]\]", translated):
                        raise ValueError("protected spans changed or moved between lines")
                content = restore_translation_lines(value["lines"], kwargs["messages"][0]["content"])
            except (TypeError, ValueError) as exc:
                raise OpenRouterPermanentError("translation_lines_invalid", provider_usage=usage) from exc
        if self.profile.normalize_marker_lines:
            content = normalize_marker_lines(content, request["messages"][0]["content"])
        return ProviderTextResponse(content, usage)
    def messages_create(self, **kwargs: Any) -> ProviderResponse:
        request, identity = self._next(kwargs, "json"); _, usage, content = self._send(request, identity)
        try: parsed = json.loads(content, object_pairs_hook=_no_duplicate_json_keys)
        except (TypeError, ValueError) as exc: raise OpenRouterPermanentError("openrouter_response_content_invalid", provider_usage=usage) from exc
        if not isinstance(parsed, dict): raise OpenRouterPermanentError("openrouter_response_content_shape_invalid", provider_usage=usage)
        return ProviderResponse(parsed, usage=usage)

def normalize_marker_lines(content: str, prompt: str) -> str:
    """Normalize whitespace around existing ordered markers; never add a marker."""
    payload = prompt.split("SOURCE:\n", 1)[-1]
    first = re.match(r"\[\[PW\d+:001\]\]", payload)
    if not first:
        return content
    prefix = first.group().split(":", 1)[0] + ":"
    pattern = re.escape(prefix) + r"(?:\d{3}|END)\]\]"
    expected = re.findall(pattern, payload)
    if re.findall(pattern, content) != expected or len(set(expected)) != len(expected):
        return content
    for marker in expected:
        content = re.sub(re.escape(marker) + r"[ \t]*(?:\r?\n)?", lambda m: marker + ("" if marker.endswith(":END]]") else "\n"), content, count=1)
    return content

def _begin_live_attempt(directory: Path, contract: dict[str, Any], attempt: int) -> Path:
    maximum = attempt_limit(contract["profile"]["model"], contract["profile"]["task"])
    if not 1 <= attempt <= maximum: raise ValueError("attempt exceeds per-model/task limit")
    destination = directory / f"attempt-{attempt}.live"
    if destination.exists(): raise ValueError("attempt already started; no retry command exists")
    ledger_path = directory.parent / "portfolio-ledger.json"; ledger = read(ledger_path) if ledger_path.exists() else {"attempts": {}, "reserved_usd": 0.0}; key = contract["profile"]["profile"]; task_key = f"{contract['profile']['model']}|{contract['profile']['task']}"; task = ledger["attempts"].get(task_key, {"profiles": {}, "reserved_usd": 0.0})
    if key not in task["profiles"] and len(task["profiles"]) >= maximum: raise ValueError("portfolio model/task attempt limit reached")
    if float(task["reserved_usd"]) + float(contract["reserved_cost_usd"]) > 3: raise ValueError("model/task reservation exceeds $3")
    if float(ledger["reserved_usd"]) + float(contract["reserved_cost_usd"]) > 30: raise ValueError("portfolio reservation exceeds $30")
    destination.mkdir(parents=True); write(destination / "started.json", {"attempt": attempt, "started_at": datetime.now(UTC).isoformat(), "state": "started_before_any_send", "reserved_usd": contract["reserved_cost_usd"]})
    task["profiles"][key] = int(task["profiles"].get(key, 0)) + 1; task["reserved_usd"] = float(task["reserved_usd"]) + float(contract["reserved_cost_usd"]); ledger["attempts"][task_key] = task; ledger["reserved_usd"] = float(ledger["reserved_usd"]) + float(contract["reserved_cost_usd"]); write(ledger_path, ledger); return destination

def live(directory: Path, *, attempt: int = 1) -> dict[str, Any]:
    """One paid attempt with at most three source posts in flight."""
    with _lock(directory.parent / ".portfolio.lock"), _lock(directory / ".run.lock"):
        contract = _load_contract(directory); attempt_directory = _begin_live_attempt(directory, contract, attempt); profile = get_profile(contract["profile"]["profile"]); transport = FrozenLiveTransport(profile, contract["requests"], attempt_directory); rows = contract["rows"]
        if profile.task == "translation":
            cfg = SimpleNamespace(llm=SimpleNamespace(translator_model=profile.model, translator_base_url="https://openrouter.ai/api/v1")); output = translate_batch_literal_plaintext([{"tweet_id": row["post_id"], "text": row["text"], "source_language": row["source_language"]} for row in rows], transport, cfg=cfg, max_workers=profile.max_concurrency, paragraph_tracking=True); row_results = {row["tweet_id"]: row for row in output}; structural = [row for row in output if row.get("translation_failed")]
        else:
            row_results, structural = {}, []; cfg = SimpleNamespace(model=profile.model, max_output_tokens_per_post=_visible_output_limit(profile), max_input_tokens_per_post=32_000, timeout_seconds=profile.timeout_seconds)
            def commentary(row):
                try:
                    value = synthesize_post(post_id=row["post_id"], context=_context(row), client=transport, config=cfg)
                    return row["post_id"], {"status": "complete", "texts": value.texts, "input_tokens": value.input_tokens, "output_tokens": value.output_tokens, "latency_ms": value.latency_ms}
                except Exception as exc:
                    return row["post_id"], {"status": "structural_error", "error_type": type(exc).__name__, "error": str(exc)}
            with ThreadPoolExecutor(max_workers=profile.max_concurrency) as pool:
                for post_id, record in pool.map(commentary, rows):
                    row_results[post_id] = record
                    if record["status"] != "complete":
                        structural.append({"post_id": post_id, **record})
        if transport.requests: raise ValueError("real caller did not consume every frozen request")
        transport_errors = [item for item in transport.measurements if item["state"] == "transport_error"]
        report = {"schema": SCHEMA + "/live-report", "attempt": attempt, "profile": contract["profile"], "request_count": len(contract["requests"]), "rows": row_results, "raw_responses": {item["request_identity"]: item for item in transport.measurements}, "errors": {"transport": transport_errors, "structural": structural}, "semantic": "unassessed", "safety": {"retries": 0, "fallbacks": 0, "database_touched": False}}
        write(attempt_directory / "report.json", report); return report

def main() -> None:
    parser = argparse.ArgumentParser(); sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare"); prep.add_argument("input", type=Path); prep.add_argument("directory", type=Path); prep.add_argument("--profile", required=True, choices=sorted(__import__("scripts.model_task_profiles", fromlist=["PROFILES"]).PROFILES))
    replay = sub.add_parser("run"); replay.add_argument("directory", type=Path); replay.add_argument("responses", type=Path); replay.add_argument("--attempt", type=int, default=1)
    sender = sub.add_parser("live"); sender.add_argument("directory", type=Path); sender.add_argument("--attempt", type=int, default=1)
    args = parser.parse_args(); result = prepare(args.input, args.directory, args.profile) if args.command == "prepare" else run(args.directory, args.responses, attempt=args.attempt) if args.command == "run" else live(args.directory, attempt=args.attempt); print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__": main()
