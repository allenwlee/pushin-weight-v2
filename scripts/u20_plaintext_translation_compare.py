"""Freeze and execute the bounded U20 literal-translation comparison.

``prepare`` is provider-free: it drives the real plaintext caller through a
fake ``messages_create_text`` transport and freezes every resulting request.
``execute`` runs one model arm serially.  A request marker is written before a
provider call, so an ambiguous failure is evidence, never permission to retry.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import threading
import time
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

try:  # Supports both ``python scripts/...`` and package imports in tests.
    from scripts.u20_translation_synthesis_execute import (
        HARD_ARM_CAP,
        INPUT_CEILING_PER_M,
        OUTPUT_CEILING_PER_M,
        TARGET_MODEL,
        build_client,
        credential,
        price_preflight,
    )
except ModuleNotFoundError as exc:
    if exc.name != "scripts":
        raise
    from u20_translation_synthesis_execute import (  # type: ignore[no-redef]
        HARD_ARM_CAP,
        INPUT_CEILING_PER_M,
        OUTPUT_CEILING_PER_M,
        TARGET_MODEL,
        build_client,
        credential,
        price_preflight,
    )
from x_monitor.literal_translation import (
    LITERAL_TRANSLATION_PROMPT_VERSION,
    PARAGRAPH_TRANSLATION_PROMPT_VERSION,
    translate_batch_literal_plaintext,
)
from x_monitor.provider_telemetry import ProviderTextResponse

ROOT = Path(__file__).resolve().parents[1]
INPUT_CONTRACT = ROOT / ".context/u20/translation-synthesis-prepare-20260916-v4/contract.json"
SCHEMA = "u20-plaintext-translation-compare/v1"
INPUT_SCHEMA = "u20-translation-synthesis-compare/v1"
ARMS = {
    "incumbent": {
        "model": "deepseek-v4-flash",
        "base_url": "https://api.deepseek.com/anthropic",
        "request_profile": None,
    },
    "0731": {
        "model": TARGET_MODEL,
        "base_url": "https://openrouter.ai/api/v1",
        "request_profile": "deepseek_0731",
    },
}
EXPECTED_LANGUAGES = {"en": 15, "zh-cn": 15, "ja": 15}
REQUEST_OVERHEAD_BYTES = 2_048
SOCKET_IDLE_TIMEOUT_SECONDS = 180


class ConsumedRequestError(RuntimeError):
    """A request is no longer safe to send to a provider."""


class ExecutionFailure(RuntimeError):
    """The result artifact contains a provider or caller failure."""


def encoded(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(encoded(value)).hexdigest()


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read(path: Path) -> Any:
    if not path.is_file():
        raise ValueError("required artifact is missing or not a file: " + str(path))
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    if not path.is_file():
        raise ValueError("required source is missing or not a file: " + str(path))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes() -> dict[str, str]:
    return {
        relative: sha(ROOT / relative)
        for relative in (
            "scripts/u20_plaintext_translation_compare.py",
            "scripts/u20_translation_synthesis_execute.py",
            "x_monitor/literal_translation.py",
            "x_monitor/translator.py",
            "x_monitor/attribution.py",
            "x_monitor/openrouter.py",
            "x_monitor/provider_telemetry.py",
        )
    }


def load_frozen_rows() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    contract = read(INPUT_CONTRACT)
    if contract.get("schema") != INPUT_SCHEMA:
        raise ValueError("frozen input contract schema mismatch")
    rows = contract.get("rows")
    if not isinstance(rows, list) or digest(rows) != contract.get("rows_sha256"):
        raise ValueError("frozen input rows hash mismatch")
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("post_id"), str):
            raise TypeError("frozen input row shape mismatch")
        if not isinstance(row.get("text"), str):
            raise TypeError("frozen input row text missing")
        counts[str(row.get("source_language"))] += 1
    if len(rows) != 45 or dict(counts) != EXPECTED_LANGUAGES:
        raise ValueError("frozen input must contain the 45 EN/ZH/JA rows")
    return contract, rows


def translation_inputs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "tweet_id": row["post_id"],
            "text": row["text"],
            "source_language": row["source_language"],
        }
        for row in rows
    ]


def caller_config(model_arm: str) -> Any:
    route = ARMS[model_arm]
    return SimpleNamespace(
        llm=SimpleNamespace(
            translator_model=route["model"], translator_base_url=route["base_url"]
        )
    )


class CaptureTextClient:
    """Provider-free recorder that exposes the selected-route sampler shape."""

    def __init__(self, model_arm: str, *, paragraph_tracking: bool = False) -> None:
        self.paragraph_tracking = paragraph_tracking
        self.request_profile = ARMS[model_arm]["request_profile"]
        self.requests: list[dict[str, Any]] = []

    def messages_create_text(self, **kwargs: Any) -> ProviderTextResponse:
        self.requests.append(dict(kwargs))
        content = kwargs["messages"][0]["content"]
        text = content.split("SOURCE:\n", 1)[1] if self.paragraph_tracking else "captured literal text"
        return ProviderTextResponse(text, provider_usage={})


def capture_requests(rows: list[dict[str, Any]], model_arm: str, *, paragraph_tracking: bool = False) -> list[dict[str, Any]]:
    """Capture all requests from the production plaintext caller, offline."""
    if model_arm not in ARMS:
        raise ValueError("unknown model arm")
    client = CaptureTextClient(model_arm, paragraph_tracking=paragraph_tracking)
    output = translate_batch_literal_plaintext(
        translation_inputs(rows), client, cfg=caller_config(model_arm), max_workers=1,
        paragraph_tracking=paragraph_tracking
    )
    if len(output) != len(rows) or any(row.get("translation_failed") for row in output):
        raise ValueError("provider-free caller capture failed")
    return client.requests


def request_bounds(requests: list[dict[str, Any]]) -> dict[str, Any]:
    input_bytes = sum(len(encoded(request)) + REQUEST_OVERHEAD_BYTES for request in requests)
    output_tokens = sum(int(request.get("max_tokens", 0)) for request in requests)
    if any(
        not isinstance(request.get("max_tokens"), int)
        or not 1 <= request["max_tokens"] <= 8_192
        for request in requests
    ):
        raise ValueError("plaintext caller output ceiling drift")
    reserved = (
        Decimal(input_bytes) * INPUT_CEILING_PER_M
        + Decimal(output_tokens) * OUTPUT_CEILING_PER_M
    ) / Decimal(1_000_000)
    if reserved > HARD_ARM_CAP:
        raise ValueError("plaintext arm planning ceiling exceeds hard cap")
    return {
        "calls": len(requests),
        "input_bytes": input_bytes,
        "output_tokens": output_tokens,
        "max_tokens_per_request": max(request["max_tokens"] for request in requests),
        "reserved_cost_usd": str(reserved),
    }


def select_rows(rows: list[dict[str, Any]], post_ids: list[str] | None) -> list[dict[str, Any]]:
    if post_ids is None:
        return rows
    if not post_ids or len(set(post_ids)) != len(post_ids) or not set(post_ids).issubset({r["post_id"] for r in rows}):
        raise ValueError("invalid source post selection")
    return [row for row in rows if row["post_id"] in post_ids]


def prompt_version(paragraph_tracking: bool) -> str:
    return PARAGRAPH_TRANSLATION_PROMPT_VERSION if paragraph_tracking else LITERAL_TRANSLATION_PROMPT_VERSION


def prepare(directory: Path, *, paragraph_tracking: bool = False, post_ids: list[str] | None = None) -> dict[str, Any]:
    """Create one immutable, provider-free execution contract."""
    if directory.exists():
        raise ValueError("run directory exists; refusing to overwrite frozen artifacts")
    source_contract, rows = load_frozen_rows()
    rows = select_rows(rows, post_ids)
    requests = {model_arm: capture_requests(rows, model_arm, paragraph_tracking=paragraph_tracking) for model_arm in ARMS}
    for model_arm, values in requests.items():
        if len(values) != 2 * len(rows):
            raise ValueError(f"{model_arm} caller capture must contain exactly two requests per source")
        if model_arm == "0731" and any(
            request.get("temperature") != 1.0
            or request.get("top_p") != 1.0
            or request.get("seed") != 42
            for request in values
        ):
            raise ValueError("0731 plaintext sampler request drift")
    prompt_sets = {
        model_arm: [request["messages"] for request in values]
        for model_arm, values in requests.items()
    }
    if prompt_sets["incumbent"] != prompt_sets["0731"]:
        raise ValueError("model arms changed the plaintext caller prompts")
    bounds = {model_arm: request_bounds(values) for model_arm, values in requests.items()}
    contract = {
        "schema": SCHEMA,
        "created_at": datetime.now(UTC).isoformat(),
        "input_contract": str(INPUT_CONTRACT),
        "input_contract_sha256": sha(INPUT_CONTRACT),
        "input_rows_sha256": digest(rows),
        "rows": rows,
        "rows_sha256": digest(rows),
        "source_contract_metadata": {
            "created_at": source_contract.get("created_at"),
            "source_corpus": source_contract.get("source_corpus"),
            "source_sha256": source_contract.get("source_sha256"),
        },
        "implementation_sha256": source_hashes(),
        "literal_translation_prompt_version": prompt_version(paragraph_tracking),
        "paragraph_tracking": paragraph_tracking,
        "selected_post_ids": post_ids,
        "routes": ARMS,
        "requests_sha256": {model_arm: digest(values) for model_arm, values in requests.items()},
        "bounds": bounds,
        "limits": {
            "calls_per_arm": 2 * len(rows),
            "maximum_concurrency_within_arm": 1,
            "maximum_output_tokens_per_request": 8_192,
            "socket_idle_timeout_seconds": SOCKET_IDLE_TIMEOUT_SECONDS,
            "hard_cost_cap_usd_per_arm": str(HARD_ARM_CAP),
            "transport_retries": 0,
        },
        "safety": {
            "provider_calls_in_prepare": False,
            "database_reads": False,
            "database_writes": False,
            "each_request_consumed_before_provider": True,
            "semantic_accuracy_claim": False,
        },
    }
    write(directory / "contract.json", contract)
    write(directory / "requests.json", requests)
    return contract


def load_execution(
    directory: Path,
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    contract, requests = read(directory / "contract.json"), read(directory / "requests.json")
    if contract.get("schema") != SCHEMA:
        raise ValueError("plaintext execution contract schema mismatch")
    if sha(INPUT_CONTRACT) != contract.get("input_contract_sha256"):
        raise ValueError("frozen input contract changed after prepare")
    _source, rows = load_frozen_rows()
    rows = select_rows(rows, contract.get("selected_post_ids"))
    if digest(rows) != contract.get("rows_sha256") or contract.get("rows") != rows:
        raise ValueError("frozen source rows changed after prepare")
    if source_hashes() != contract.get("implementation_sha256"):
        raise ValueError("plaintext caller or harness source changed after prepare")
    if contract.get("literal_translation_prompt_version") != prompt_version(contract.get("paragraph_tracking", False)):
        raise ValueError("literal translation prompt version changed after prepare")
    if set(requests) != set(ARMS):
        raise ValueError("frozen model arms changed")
    for model_arm, values in requests.items():
        if not isinstance(values, list) or len(values) != contract["limits"]["calls_per_arm"]:
            raise ValueError("frozen request count changed")
        if digest(values) != contract.get("requests_sha256", {}).get(model_arm):
            raise ValueError("frozen request content changed")
        if request_bounds(values) != contract.get("bounds", {}).get(model_arm):
            raise ValueError("frozen request bounds changed")
    return contract, requests


@contextlib.contextmanager
def model_arm_lock(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".run.lock").open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ConsumedRequestError("model arm is already running") from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class FrozenPlaintextTransport:
    """Allow only frozen raw-text requests and record all terminal evidence."""

    def __init__(
        self,
        delegate: Any,
        expected: list[dict[str, Any]],
        artifact_directory: Path,
        *,
        socket_idle_timeout_seconds: int = SOCKET_IDLE_TIMEOUT_SECONDS,
    ) -> None:
        self.delegate = delegate
        self.request_profile = getattr(delegate, "request_profile", None)
        self.expected: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for request in expected:
            self.expected[digest(request)].append(request)
        self.artifact_directory = artifact_directory
        self.socket_idle_timeout_seconds = socket_idle_timeout_seconds
        self.artifact_directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.measurements: list[dict[str, Any]] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self.delegate, name)

    def _marker(self, identity: str) -> tuple[Path, int]:
        markers = self.artifact_directory / "consumed"
        markers.mkdir(parents=True, exist_ok=True)
        for sequence in range(len(self.expected[identity])):
            marker = markers / f"{identity}-{sequence:03}.json"
            try:
                with marker.open("x", encoding="utf-8") as file:
                    json.dump(
                        {
                            "request_sha256": identity,
                            "sequence": sequence,
                            "consumed_at": datetime.now(UTC).isoformat(),
                        },
                        file,
                        ensure_ascii=False,
                    )
                return marker, sequence
            except FileExistsError:
                continue
        raise ConsumedRequestError("request_already_consumed")

    def _reject(self, identity: str, request: dict[str, Any], reason: str) -> None:
        evidence = {
            "status": "rejected",
            "request_sha256": identity,
            "reason": reason,
            "request": request,
        }
        write(self.artifact_directory / "rejected" / f"{identity}.json", evidence)
        self.measurements.append(evidence)
        raise ConsumedRequestError(reason)

    def messages_create_text(self, **kwargs: Any) -> ProviderTextResponse:
        request = dict(kwargs)
        identity = digest(request)
        with self.lock:
            if identity not in self.expected:
                self._reject(identity, request, "caller_request_not_frozen")
            marker, sequence = self._marker(identity)
            marker.write_text(
                json.dumps(
                    {
                        "request_sha256": identity,
                        "sequence": sequence,
                        "consumed_at": datetime.now(UTC).isoformat(),
                        "request": request,
                    },
                    ensure_ascii=False,
                    indent=2,
                ) + "\n",
                encoding="utf-8",
            )
        started = time.monotonic()
        measurement: dict[str, Any] = {
            "request_sha256": identity,
            "sequence": sequence,
            "request": request,
            "status": "started",
        }
        try:
            provider_request = dict(request)
            provider_request.setdefault("timeout", self.socket_idle_timeout_seconds)
            measurement["socket_idle_timeout_seconds"] = provider_request["timeout"]
            response = self.delegate.messages_create_text(**provider_request)
            text = getattr(response, "text", None)
            if not isinstance(text, str):
                raise TypeError("provider_text_response_missing_text")
            measurement.update(status="received", usage=getattr(response, "provider_usage", None))
            write(
                self.artifact_directory / "responses" / f"{identity}-{sequence:03}.json",
                {
                    **measurement,
                    "provider_request": provider_request,
                    "raw_text": text,
                    "raw_text_code_fence": "```text\n" + text + "\n```",
                },
            )
            return response
        except Exception as exc:
            measurement.update(
                status="error",
                error_type=type(exc).__name__,
                error=str(exc),
                usage=getattr(exc, "provider_usage", None),
            )
            write(self.artifact_directory / "errors" / f"{identity}-{sequence:03}.json", measurement)
            raise
        finally:
            measurement["latency_ms"] = round((time.monotonic() - started) * 1_000)
            write(self.artifact_directory / "measurements" / f"{identity}-{sequence:03}.json", measurement)
            with self.lock:
                self.measurements.append(measurement)


def usage_summary(measurements: list[dict[str, Any]]) -> dict[str, Any]:
    totals = {"input_tokens": 0, "output_tokens": 0, "cost_usd": Decimal(0)}
    complete = bool(measurements)
    for measurement in measurements:
        usage = measurement.get("usage")
        if not isinstance(usage, dict):
            complete = False
            continue
        for key in ("input_tokens", "output_tokens"):
            value = usage.get(key)
            if isinstance(value, int) and value >= 0:
                totals[key] += value
            else:
                complete = False
        value = usage.get("cost_usd")
        if value is None:
            complete = False
        else:
            try:
                totals["cost_usd"] += Decimal(str(value))
            except (ArithmeticError, ValueError):
                complete = False
    return {
        "input_tokens": totals["input_tokens"],
        "output_tokens": totals["output_tokens"],
        "reported_cost_usd": str(totals["cost_usd"]),
        "reported_cost_complete": complete,
    }


def source_copy_evidence(rows: list[dict[str, Any]], output: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {str(row.get("tweet_id")): row for row in output}
    field_for_language = {"en": "text_en", "zh-cn": "text_zh_cn", "ja": "text_ja"}
    evidence = []
    for source in rows:
        field = field_for_language[source["source_language"]]
        produced = by_id.get(source["post_id"], {})
        evidence.append(
            {
                "post_id": source["post_id"],
                "source_language": source["source_language"],
                "source_text": source["text"],
                "native_field": field,
                "native_copy": produced.get(field),
                "byte_exact": produced.get(field) == source["text"],
            }
        )
    return evidence


def require_price_preflight(model_arm: str, preflight: dict[str, Any]) -> None:
    """Fail closed when the selected arm lacks its required pricing evidence."""
    if model_arm == "0731" and preflight.get("cost_gate_ready") is not True:
        raise ValueError("0731 price preflight is not ready")
    if model_arm == "incumbent" and preflight.get("retrieval") != "ok":
        raise ValueError("incumbent price preflight was not retrieved")


def run_arm(directory: Path, model_arm: str) -> dict[str, Any]:
    if model_arm not in ARMS:
        raise ValueError("model arm must be incumbent or 0731")
    contract, requests = load_execution(directory)
    arm_directory = directory / "arms" / model_arm
    with model_arm_lock(arm_directory):
        marker = arm_directory / "run.started"
        if marker.exists():
            raise ConsumedRequestError("model arm already started; no replay command exists")
        preflight = price_preflight(model_arm)
        if not isinstance(preflight, dict):
            raise TypeError("price preflight response shape invalid")
        require_price_preflight(model_arm, preflight)
        api_key = credential(model_arm)
        with marker.open("x", encoding="utf-8") as file:
            file.write(datetime.now(UTC).isoformat())
        transport = FrozenPlaintextTransport(
            build_client(model_arm, api_key),
            requests[model_arm],
            arm_directory,
            socket_idle_timeout_seconds=SOCKET_IDLE_TIMEOUT_SECONDS,
        )
        started = time.monotonic()
        output = translate_batch_literal_plaintext(
            translation_inputs(contract["rows"]),
            transport,
            cfg=caller_config(model_arm),
            max_workers=1,
            paragraph_tracking=contract.get("paragraph_tracking", False),
        )
        copies = source_copy_evidence(contract["rows"], output)
        errors = [item for item in transport.measurements if item["status"] in {"error", "rejected"}]
        usage = usage_summary(transport.measurements)
        report = {
            "schema": SCHEMA,
            "contract_sha256": sha(directory / "contract.json"),
            "model_arm": model_arm,
            "preflight": preflight,
            "elapsed_ms": round((time.monotonic() - started) * 1_000),
            "requests": {
                "frozen": len(requests[model_arm]),
                "consumed": sum(item["status"] != "rejected" for item in transport.measurements),
                "received": sum(item["status"] == "received" for item in transport.measurements),
                "errors": len(errors),
            },
            "usage": usage,
            "failures": sum(bool(row.get("translation_failed")) for row in output),
            "rows": output,
            "source_copies": copies,
            "measurements": transport.measurements,
            "semantic_accuracy_claim": False,
        }
        report["summary"] = {
            "elapsed_ms": report["elapsed_ms"],
            "input_tokens": usage["input_tokens"],
            "output_tokens": usage["output_tokens"],
            "reported_cost_usd": usage["reported_cost_usd"],
            "reported_cost_complete": usage["reported_cost_complete"],
            "planning_reserved_cost_usd": contract["bounds"][model_arm]["reserved_cost_usd"],
            "cost_basis": "provider-reported usage when available; otherwise the frozen $0.44/M input and $1.32/M output upper bound",
            "provider_errors": len(errors),
            "failures": report["failures"],
        }
        write(arm_directory / "result.json", report)
        if errors or report["failures"] or not all(item["byte_exact"] for item in copies):
            raise ExecutionFailure("plaintext arm completed with explicit failures; inspect result.json")
        return report


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="action", required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("directory", type=Path)
    prepare_parser.add_argument("--paragraph-tracking", action="store_true")
    prepare_parser.add_argument("--post-id", action="append", dest="post_ids")
    execute_parser = commands.add_parser("execute")
    execute_parser.add_argument("directory", type=Path)
    execute_parser.add_argument("--model-arm", choices=tuple(ARMS), required=True)
    args = parser.parse_args()
    result = prepare(args.directory, paragraph_tracking=args.paragraph_tracking, post_ids=args.post_ids) if args.action == "prepare" else run_arm(args.directory, args.model_arm)
    print(
        json.dumps(
            {
                "action": args.action,
                "directory": str(args.directory),
                "model_arm": getattr(args, "model_arm", None),
                "requests": result.get("requests", {}).get("consumed"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
