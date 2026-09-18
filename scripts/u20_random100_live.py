"""Frozen, bounded live-100 translation and commentary evaluation.

This diagnostic reuses the current per-post plaintext literal translator and
the current synthesis caller.  It never imports Django settings or writes a
database row.  Every request is captured offline, hashed, consumed before its
one provider boundary, and retained with raw provider evidence.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import shutil
import threading
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from scripts import u20_plaintext_translation_compare as literal
from scripts import u20_translation_synthesis_execute as executor
from x_monitor.literal_translation import translate_batch_literal_plaintext
from x_monitor.provider_telemetry import ProviderTextResponse
from x_monitor.synthesis import synthesize_post

ROOT = Path(__file__).resolve().parents[1]
INPUT_SCHEMA = "u20-random100-live-input/v1"
PREPARED_SCHEMA = "u20-random100-live-prepared/v1"
TARGET_ARM = "0731"
MAX_POSTS = 100
MAX_TRANSPORTS = 500
MAX_CONCURRENCY = 3
OUTER_COST_CAP = Decimal("5.00")
SYNTHESIS_MAX_OUTPUT_TOKENS = 4_000
ARM_ROUTES = {
    "incumbent": {
        "model": "deepseek-v4-flash", "base_url": "https://api.deepseek.com/anthropic",
        "provider": "DeepSeek", "request_profile": None, "reasoning": "disabled",
        "sampler": None,
        "advertised_identity": "DeepSeek-V4.1-Flash (direct legacy deepseek-v4-flash request)",
        "response_identity": None,
    },
    "0731": {
        "model": executor.TARGET_MODEL, "base_url": "https://openrouter.ai/api/v1",
        "provider": "DeepInfra", "endpoint": executor.TARGET_ENDPOINT,
        "request_profile": "deepseek_0731", "reasoning": "disabled",
        "sampler": {"temperature": 1.0, "top_p": 1.0, "seed": 42},
        "advertised_identity": "deepseek/deepseek-v4-flash-0731",
        "response_identity": "deepseek/deepseek-v4-flash-20260731",
    },
}


def encoded(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(encoded(value)).hexdigest()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _source_hashes() -> dict[str, str]:
    names = (
        "scripts/u20_random100_live.py",
        "scripts/u20_plaintext_translation_compare.py",
        "scripts/u20_translation_synthesis_execute.py",
        "x_monitor/literal_translation.py",
        "x_monitor/translation_invariants.py",
        "x_monitor/translator.py",
        "x_monitor/synthesis.py",
        "x_monitor/openrouter.py",
        "x_monitor/provider_telemetry.py",
    )
    return {name: sha(ROOT / name) for name in names}


def freeze_input(selection: Path, output: Path, review_rubric: Path) -> dict[str, Any]:
    """Turn the read-only production selection into an immutable caller input."""
    if output.exists():
        raise ValueError("frozen input exists")
    selected = read(selection)
    if selected.get("selected_count") != MAX_POSTS or selected.get("transaction_read_only") != "on":
        raise ValueError("selection must be the 100-row read-only snapshot")
    rows = []
    for raw in selected.get("rows", []):
        if not isinstance(raw.get("post_id"), str) or not isinstance(raw.get("text"), str):
            raise ValueError("selection source row is incomplete")
        # Preserve raw values and let the real caller normalize its declared
        # language.  `other` is declared, rather than silently filtered.
        # CycleRunner passes `lang_detected or lang or ''` as source_language.
        # Preserve that current production precedence exactly.
        declared = raw.get("stored_detected_language") or raw.get("declared_language")
        context = []
        if raw.get("quoted_text"):
            context.append({"provenance": "stored_quote", "text": raw["quoted_text"]})
        if raw.get("parent_text"):
            context.append({"provenance": "local_parent", "text": raw["parent_text"]})
        rows.append({
            "post_id": raw["post_id"], "text": raw["text"], "source_language": declared,
            "declared_language": raw.get("declared_language"), "stored_detected_language": raw.get("stored_detected_language"),
            "timestamps": {"created_at": raw.get("created_at"), "fetched_at": raw.get("fetched_at")},
            "identifiers": {key: raw.get(key) for key in ("in_reply_to_id", "quoted_status_id", "conversation_id", "is_reply", "is_quote", "parent_post_id")},
            "context": context,
        })
    if len(rows) != MAX_POSTS or len({row["post_id"] for row in rows}) != MAX_POSTS:
        raise ValueError("selection must contain 100 unique posts")
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(review_rubric, output.parent / "review-rubric.txt")
    result = {
        "schema": INPUT_SCHEMA, "created_at": datetime.now(UTC).isoformat(),
        "selection_source": str(selection), "selection_source_sha256": sha(selection),
        "selection": {key: selected.get(key) for key in ("database_resource", "database_id", "transaction_read_only", "frozen_at", "window_start", "selection_query", "eligible_pool_count", "eligible_language_counts", "selected_count", "selected_language_counts")},
        "rows": rows, "rows_sha256": digest(rows),
        "review_rubric_sha256": sha(output.parent / "review-rubric.txt"),
        "unknown_language_policy": "Pass source_language unchanged to the current literal caller; if absent or unsupported, that caller performs its existing detection path. No row is excluded.",
    }
    write(output, result)
    return result


class CaptureJSONClient:
    def __init__(self, arm: str) -> None:
        self.requests: list[dict[str, Any]] = []
        self.arm = arm

    def messages_create(self, **kwargs: Any) -> dict[str, Any]:
        request = dict(kwargs)
        sampler = ARM_ROUTES[self.arm]["sampler"]
        if sampler:
            request.update(sampler)
        self.requests.append(request)
        return {}


class CaptureTextClient:
    """Capture current per-post requests while returning a valid source echo."""
    def __init__(self, arm: str) -> None:
        self.requests: list[dict[str, Any]] = []
        self.request_profile = ARM_ROUTES[arm]["request_profile"]

    def messages_create_text(self, **kwargs: Any) -> ProviderTextResponse:
        self.requests.append(dict(kwargs))
        prompt = kwargs["messages"][0]["content"]
        if prompt.startswith("Identify only the source language"):
            return ProviderTextResponse("other", {})
        # v13's exact source payload is also a valid protocol response: it
        # retains every marker and line for caller-side validation.
        return ProviderTextResponse(prompt.split("SOURCE:\n", 1)[1], {})


def _context(row: dict[str, Any]) -> dict[str, str]:
    output = {"post": row["text"]}
    for item in row["context"]:
        if item.get("provenance") and item.get("text"):
            output[str(item["provenance"])] = str(item["text"])
    return output


def _rows_for_literal(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # The capture wrapper accepts its own frozen-input shape.
    return [{"post_id": row["post_id"], "text": row["text"], "source_language": row.get("source_language")} for row in rows]


def _caller_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"tweet_id": row["post_id"], "text": row["text"], "source_language": row.get("source_language")} for row in rows]


def _capture_literal(rows: list[dict[str, Any]], arm: str) -> list[dict[str, Any]]:
    client = CaptureTextClient(arm)
    route = ARM_ROUTES[arm]
    cfg = SimpleNamespace(llm=SimpleNamespace(translator_model=route["model"], translator_base_url=route["base_url"]))
    output = translate_batch_literal_plaintext(_caller_rows(rows), client, cfg=cfg, max_workers=1, paragraph_tracking=True)
    if len(output) != len(rows):
        raise ValueError("literal caller capture incomplete")
    return client.requests


def _capture_synthesis(rows: list[dict[str, Any]], arm: str) -> tuple[list[dict[str, Any]], list[str]]:
    client = CaptureJSONClient(arm)
    cfg = SimpleNamespace(model=ARM_ROUTES[arm]["model"], max_input_tokens_per_post=4_000, max_output_tokens_per_post=SYNTHESIS_MAX_OUTPUT_TOKENS, timeout_seconds=60)
    capped = []
    for row in rows:
        try:
            synthesize_post(post_id=row["post_id"], context=_context(row), client=client, config=cfg)
        except ValueError as exc:
            if str(exc) == "synthesis_input_cap_exceeded":
                capped.append(row["post_id"])
            elif str(exc) != "synthesis_response_schema_invalid":
                raise
    return client.requests, capped


def _bounds(requests: list[dict[str, Any]]) -> dict[str, Any]:
    input_bytes = sum(len(encoded(request)) + 2_048 for request in requests)
    output_tokens = sum(int(request.get("max_tokens", 0)) for request in requests)
    reserve = (Decimal(input_bytes) * executor.INPUT_CEILING_PER_M + Decimal(output_tokens) * executor.OUTPUT_CEILING_PER_M) / Decimal(1_000_000)
    return {"calls": len(requests), "input_bytes": input_bytes, "output_tokens": output_tokens, "reservation_usd": str(reserve)}


def prepare(input_path: Path, directory: Path, arm: str = TARGET_ARM, captured_requests_path: Path | None = None) -> dict[str, Any]:
    if directory.exists():
        raise ValueError("prepared directory exists")
    source = read(input_path)
    rows = source.get("rows")
    if source.get("schema") != INPUT_SCHEMA or not isinstance(rows, list) or digest(rows) != source.get("rows_sha256"):
        raise ValueError("frozen live input changed")
    if arm not in ARM_ROUTES:
        raise ValueError("unknown arm")
    if captured_requests_path is None:
        literal_requests = _capture_literal(rows, arm)
        synthesis_requests, synthesis_input_cap_rejections = _capture_synthesis(rows, arm)
    else:
        captured = read(captured_requests_path)
        literal_requests = captured.get("translation")
        synthesis_requests = captured.get("commentary")
        synthesis_input_cap_rejections = captured.get("capped")
        if not all(isinstance(value, list) for value in (literal_requests, synthesis_requests, synthesis_input_cap_rejections)):
            raise ValueError("captured request bundle is incomplete")
    all_requests = literal_requests + synthesis_requests
    if len(all_requests) > MAX_TRANSPORTS:
        raise ValueError("maximum transport budget exceeded")
    bounds = {"translation": _bounds(literal_requests), "commentary": _bounds(synthesis_requests), "total": _bounds(all_requests)}
    if Decimal(bounds["total"]["reservation_usd"]) > OUTER_COST_CAP:
        raise ValueError("$5 outer reservation exceeded")
    contract = {
        "schema": PREPARED_SCHEMA, "created_at": datetime.now(UTC).isoformat(),
        "input_path": str(input_path), "input_sha256": sha(input_path), "rows_sha256": source["rows_sha256"], "rows": rows,
        "source_hashes": _source_hashes(), "arm": arm, "route": ARM_ROUTES[arm],
        "limits": {"maximum_total_in_flight": MAX_CONCURRENCY, "maximum_transports": MAX_TRANSPORTS, "transport_retries": 0, "translation_socket_idle_timeout_seconds": 180, "commentary_socket_idle_timeout_seconds": 60, "outer_cost_cap_usd": str(OUTER_COST_CAP)},
        "bounds": bounds, "request_sha256": {"translation": digest(literal_requests), "commentary": digest(synthesis_requests)},
        "precall_coverage_failures": {"synthesis_input_cap_rejections": synthesis_input_cap_rejections},
        "captured_requests_source": str(captured_requests_path) if captured_requests_path else None,
        "captured_requests_source_sha256": sha(captured_requests_path) if captured_requests_path else None,
        "safety": {"database_writes": False, "classifier_calls": False, "publication": False, "each_request_consumed_before_provider": True, "semantic_accuracy_claim": False},
    }
    write(directory / "contract.json", contract)
    write(directory / "translation-requests.json", literal_requests)
    write(directory / "commentary-requests.json", synthesis_requests)
    return contract


class SharedCapClient:
    def __init__(self, delegate: Any, gate: threading.BoundedSemaphore) -> None:
        self.delegate, self.gate = delegate, gate
        self.request_profile = getattr(delegate, "request_profile", None)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.delegate, name)

    def messages_create_text(self, **kwargs: Any) -> Any:
        with self.gate:
            return self.delegate.messages_create_text(**kwargs)

    def messages_create(self, **kwargs: Any) -> Any:
        with self.gate:
            return self.delegate.messages_create(**kwargs)


def _load(directory: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    contract = read(directory / "contract.json")
    if contract.get("schema") != PREPARED_SCHEMA or contract.get("source_hashes") != _source_hashes():
        raise ValueError("prepared harness or caller source drift")
    if sha(Path(contract["input_path"])) != contract["input_sha256"]:
        raise ValueError("frozen input drift")
    translation, commentary = read(directory / "translation-requests.json"), read(directory / "commentary-requests.json")
    if digest(translation) != contract["request_sha256"]["translation"] or digest(commentary) != contract["request_sha256"]["commentary"]:
        raise ValueError("frozen request drift")
    return contract, translation, commentary


def run(directory: Path, commentary_only: bool = False) -> dict[str, Any]:
    contract, translation_requests, commentary_requests = _load(directory)
    arm = contract.get("arm", TARGET_ARM)
    route = contract["route"]
    preflight = executor.price_preflight(arm)
    literal.require_price_preflight(arm, preflight)
    key = executor.credential(arm)
    try:
        with (directory / "run.started").open("x", encoding="utf-8") as marker:
            marker.write(datetime.now(UTC).isoformat())
    except FileExistsError as exc:
        raise executor.ConsumedRequestError("run already started; no retry command exists") from exc
    gate = threading.BoundedSemaphore(MAX_CONCURRENCY)
    client = SharedCapClient(executor.build_client(arm, key), gate)
    literal_transport = literal.FrozenPlaintextTransport(client, translation_requests, directory / "translation")
    commentary_transport = executor.FrozenTransport(client, arm, "commentary", commentary_requests, directory / "commentary" / "responses", directory / "commentary" / "ledger.json", {"calls": len(commentary_requests), "input_bytes": contract["bounds"]["commentary"]["input_bytes"], "output_tokens": contract["bounds"]["commentary"]["output_tokens"], "dollars": contract["bounds"]["commentary"]["reservation_usd"]}, socket_idle_timeout_seconds=60)
    started = time.monotonic()
    cfg = SimpleNamespace(llm=SimpleNamespace(translator_model=route["model"], translator_base_url=route["base_url"]))
    if commentary_only:
        frozen_translation = read(directory / "translation-result.json")
        if frozen_translation.get("expected_calls") != len(translation_requests) or frozen_translation.get("attempted_calls") != len(translation_requests):
            raise ValueError("commentary-only run requires a complete frozen translation result")
        translations = frozen_translation["rows"]
        literal_transport.measurements = frozen_translation["measurements"]
    else:
        translations = translate_batch_literal_plaintext(_caller_rows(contract["rows"]), literal_transport, cfg=cfg, max_workers=MAX_CONCURRENCY, paragraph_tracking=True)
        write(directory / "translation-result.json", {"rows": translations, "measurements": literal_transport.measurements, "usage": literal.usage_summary(literal_transport.measurements), "expected_calls": len(translation_requests), "attempted_calls": len(literal_transport.measurements)})
    synth_cfg = SimpleNamespace(model=route["model"], max_input_tokens_per_post=4_000, max_output_tokens_per_post=SYNTHESIS_MAX_OUTPUT_TOKENS, timeout_seconds=60)
    def one_commentary(row: dict[str, Any]) -> dict[str, Any]:
        try:
            value = synthesize_post(post_id=row["post_id"], context=_context(row), client=commentary_transport, config=synth_cfg)
            return {"post_id": row["post_id"], "status": "complete", "texts": value.texts, "input_tokens": value.input_tokens, "output_tokens": value.output_tokens, "latency_ms": value.latency_ms}
        except Exception as exc:
            return {"post_id": row["post_id"], "status": "error", "error_type": type(exc).__name__, "error": str(exc)}
    commentary = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as pool:
        futures = [pool.submit(one_commentary, row) for row in contract["rows"]]
        for future in concurrent.futures.as_completed(futures):
            commentary.append(future.result())
            write(directory / "commentary-partial.json", {"completed_rows": commentary, "completed_count": len(commentary), "expected_provider_calls": len(commentary_requests)})
    measurements = literal_transport.measurements + commentary_transport.measurements
    response_identities = sorted({str(usage[key]) for item in measurements if isinstance((usage := item.get("usage")), dict) for key in ("response_model", "model", "provider_model") if usage.get(key)})
    report = {"contract_sha256": sha(directory / "contract.json"), "arm": arm, "preflight": preflight, "identity": {"advertised": route["advertised_identity"], "response": response_identities or route["response_identity"]}, "elapsed_ms": round((time.monotonic() - started) * 1000), "translation": {"rows": translations, "measurements": literal_transport.measurements, "usage": literal.usage_summary(literal_transport.measurements)}, "commentary": {"rows": commentary, "measurements": commentary_transport.measurements, "usage": executor._usage_summary(commentary_transport.measurements)}, "denominators": {"sampled_posts": len(contract["rows"]), "translation_expected_calls": len(translation_requests), "translation_attempted_calls": len(literal_transport.measurements), "commentary_expected_calls": len(commentary_requests), "commentary_attempted_calls": len(commentary_transport.measurements)}, "semantic_accuracy_claim": False, "database_touched": False}
    report["structural_failures"] = {"translation_failed_rows": sum(bool(row.get("translation_failed")) for row in translations), "commentary_failed_rows": sum(row["status"] != "complete" for row in commentary), "commentary_pre_call_input_cap_rows": len(contract["precall_coverage_failures"]["synthesis_input_cap_rejections"]), "provider_transport_errors": sum(item.get("status") == "error" for item in literal_transport.measurements + commentary_transport.measurements)}
    write(directory / "result.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="action", required=True)
    frozen = commands.add_parser("freeze-input")
    frozen.add_argument("selection", type=Path); frozen.add_argument("output", type=Path); frozen.add_argument("review_rubric", type=Path)
    prepared = commands.add_parser("prepare")
    prepared.add_argument("input", type=Path); prepared.add_argument("directory", type=Path)
    prepared.add_argument("--arm", choices=tuple(ARM_ROUTES), default=TARGET_ARM)
    prepared.add_argument("--captured-requests", type=Path)
    runner = commands.add_parser("run")
    runner.add_argument("directory", type=Path)
    runner.add_argument("--commentary-only", action="store_true")
    args = parser.parse_args()
    result = freeze_input(args.selection, args.output, args.review_rubric) if args.action == "freeze-input" else prepare(args.input, args.directory, args.arm, args.captured_requests) if args.action == "prepare" else run(args.directory, args.commentary_only)
    print(json.dumps({"action": args.action, "rows": len(result.get("rows", [])), "reservation": result.get("bounds", {}).get("total", {}).get("reservation_usd")}, indent=2))


if __name__ == "__main__":
    main()
