"""Execute one frozen U20 translation/synthesis arm without touching Django.

The companion ``u20_translation_synthesis_compare.py`` captures the exact
requests through the real callers.  This program only turns that prepared
artifact into a new execution contract, then spends a selected model/role arm
once.  A request marker is created *before* the provider boundary, so an
ambiguous timeout is consumed and cannot be replayed.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import shlex
import threading
import time
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from x_monitor.attribution import AnthropicClaudeClient
from x_monitor.openrouter import OpenRouterChatCompletionsClient
from x_monitor.synthesis import synthesize_post
from x_monitor.translator import translate_batch_literal

ROOT = Path(__file__).resolve().parents[1]
PREPARED_SCHEMA = "u20-translation-synthesis-compare/v1"
EXECUTION_SCHEMA = "u20-translation-synthesis-execution/v1"
INPUT_CEILING_PER_M = Decimal("0.44")
OUTPUT_CEILING_PER_M = Decimal("1.32")
HARD_ARM_CAP = Decimal("0.50")
TARGET_MODEL = "deepseek/deepseek-v4-flash-0731"
TARGET_ENDPOINT = "deepinfra/fp8"
ROLE_SOCKET_IDLE_TIMEOUT_SECONDS = {"translation": 180, "synthesis": 60}


def encoded(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(encoded(value)).hexdigest()


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class ConsumedRequestError(RuntimeError):
    """The request may have been billed, so it may never be replayed."""


class PriceCeilingError(ValueError):
    """A public endpoint price exceeded the ceiling frozen before a call."""


class EndpointPreflightError(ValueError):
    """The selected paid route no longer offers the frozen transport contract."""


def _capture(operation: Callable[[], Any]) -> dict[str, Any]:
    try:
        return {"ok": True, "value": operation()}
    except Exception as exc:  # intentionally turns test futures into data
        return {"ok": False, "error": type(exc).__name__}


def _read(path: Path) -> Any:
    if not path.is_file():
        raise ValueError("required artifact file is missing or is not a file: " + str(path))
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    if not path.is_file():
        raise ValueError("required artifact file is missing or is not a file: " + str(path))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _root_file(relative: str) -> Path:
    candidate = ROOT / relative
    try:
        candidate.resolve().relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ValueError("frozen source escapes repository root: " + relative) from exc
    if not candidate.is_file():
        raise ValueError("frozen source is missing or is not a file: " + relative)
    return candidate


def _execution_dependencies() -> dict[str, str]:
    """Provider code executes below the frozen true callers and is contract data."""
    return {
        relative: _sha(_root_file(relative))
        for relative in (
            "x_monitor/attribution.py",
            "x_monitor/openrouter.py",
            "x_monitor/provider_telemetry.py",
        )
    }


def _prepared_files(directory: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if not directory.is_dir():
        raise ValueError("prepared artifact directory is missing or is not a directory")
    contract, requests = _read(directory / "contract.json"), _read(directory / "requests.json")
    if contract.get("schema") != PREPARED_SCHEMA:
        raise ValueError("prepared contract schema mismatch")
    if any(digest(requests.get(model)) != expected for model, expected in contract.get("requests_sha256", {}).items()):
        raise ValueError("prepared request content does not match its contract")
    if digest(contract.get("rows")) != contract.get("rows_sha256"):
        raise ValueError("prepared source rows do not match their contract")
    return contract, requests


def _role_max_tokens(requests: dict[str, Any], model_arm: str, role: str) -> list[int]:
    """Return every frozen allowance for a role, in stable audit order."""
    values = sorted({int(request["max_tokens"]) for request in requests[model_arm][role]})
    if not values:
        raise ValueError("frozen role has no max_tokens values")
    return values


def _uniform_role_max_tokens(requests: dict[str, Any], model_arm: str, role: str) -> int:
    """Read a scalar caller configuration only from a uniform frozen role."""
    values = _role_max_tokens(requests, model_arm, role)
    if len(values) != 1:
        raise ValueError("frozen role requires a uniform max_tokens value: " + role)
    return values[0]


def prepare_execution(prepared_directory: Path, execution_directory: Path) -> dict[str, Any]:
    """Freeze a new execution receipt without changing the prepared artifact."""
    if execution_directory.exists():
        raise ValueError("execution directory exists; frozen artifacts are never overwritten")
    prepared, requests = _prepared_files(prepared_directory)
    for model in ("incumbent", "0731"):
        roles = requests.get(model, {})
        if set(roles) != {"translation", "synthesis"}:
            raise ValueError("prepared role set changed")
        expected = prepared["requests_per_arm"]
        if len(roles["translation"]) != expected["literal_translation"] or len(roles["synthesis"]) != expected["synthesis"]:
            raise ValueError("prepared request count changed")
        if Decimal(prepared["hard_cost_cap_usd_per_arm"]) != HARD_ARM_CAP:
            raise ValueError("prepared hard cost cap does not match execution cap")
    contract = {
        "schema": EXECUTION_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "prepared_directory": str(prepared_directory),
        "prepared_contract_sha256": _sha(prepared_directory / "contract.json"),
        "prepared_requests_sha256": _sha(prepared_directory / "requests.json"),
        "prepared_request_sets_sha256": prepared["requests_sha256"],
        "prepared_source_hashes": {
            "corpus": prepared.get("source_sha256"),
            "implementation": prepared.get("implementation_sha256", {}),
            "rows": prepared["rows_sha256"],
        },
        "execution_implementation_sha256": _sha(Path(__file__)),
        "execution_dependency_sha256": _execution_dependencies(),
        "routes": {
            "incumbent": {"model": "deepseek-v4-flash", "client": "AnthropicClaudeClient", "base_url": "https://api.deepseek.com/anthropic", "credential": "DEEPSEEK_API_KEY"},
            "0731": {"model": TARGET_MODEL, "client": "OpenRouterChatCompletionsClient", "provider": "DeepInfra", "endpoint": TARGET_ENDPOINT, "response_model": "deepseek/deepseek-v4-flash-20260731", "request_profile": "deepseek_0731", "temperature": 1.0, "top_p": 1.0, "seed": 42, "reasoning": "disabled", "native_json": "omitted", "credential": "OPENROUTER_API_KEY"},
        },
        "limits": {
            "maximum_concurrency": 1,
            "adapter_socket_idle_timeout_seconds": ROLE_SOCKET_IDLE_TIMEOUT_SECONDS,
            "adapter_timeout_note": "Socket idle timeout only; it is not a wall-clock deadline.",
            "transport_retries": 0,
            "model_arm": {
                model: {
                    "calls": sum(len(requests[model][role]) for role in ("translation", "synthesis")),
                    "input_bytes": prepared["bounds"][model]["input_bytes"],
                    "output_tokens": prepared["bounds"][model]["output_tokens"],
                    "dollars": str(HARD_ARM_CAP),
                    "planning_reservation_usd": prepared["bounds"][model]["reserved_cost_usd"],
                }
                for model in ("incumbent", "0731")
            },
            "role_max_tokens": {
                model: {role: _role_max_tokens(requests, model, role) for role in ("translation", "synthesis")}
                for model in ("incumbent", "0731")
            },
            "price_ceiling_usd_per_million": {"input": str(INPUT_CEILING_PER_M), "output": str(OUTPUT_CEILING_PER_M)},
        },
        "safety": {"database_reads": False, "database_writes": False, "runtime_config_changes": False, "classifier_calls": False, "publication": False, "semantic_accuracy_claims": False, "each_request_consumed_before_provider": True},
        "price_preflight_required": True,
        "price_preflight_note": "Unverified endpoint pricing leaves cost_gate_ready false; planning ceilings still bound the run.",
    }
    write(execution_directory / "execution-contract.json", contract)
    return contract


def load_execution(execution_directory: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    contract = _read(execution_directory / "execution-contract.json")
    if contract.get("schema") != EXECUTION_SCHEMA:
        raise ValueError("execution contract schema mismatch")
    if _sha(Path(__file__)) != contract["execution_implementation_sha256"]:
        raise ValueError("execution harness changed after execution freeze")
    if _execution_dependencies() != contract["execution_dependency_sha256"]:
        raise ValueError("execution provider dependency changed after execution freeze")
    prepared_directory = Path(contract["prepared_directory"])
    if _sha(prepared_directory / "contract.json") != contract["prepared_contract_sha256"]:
        raise ValueError("prepared contract changed after execution freeze")
    if _sha(prepared_directory / "requests.json") != contract["prepared_requests_sha256"]:
        raise ValueError("prepared requests changed after execution freeze")
    prepared, requests = _prepared_files(prepared_directory)
    for relative, expected in contract["prepared_source_hashes"]["implementation"].items():
        source = _root_file(relative)
        if _sha(source) != expected:
            raise ValueError("frozen source changed: " + relative)
    corpus = _root_file(prepared.get("source_corpus", ""))
    expected_corpus = contract["prepared_source_hashes"]["corpus"]
    if _sha(corpus) != expected_corpus:
        raise ValueError("frozen corpus changed")
    return contract, prepared, requests


def _ledger(path: Path) -> dict[str, Any]:
    if path.exists():
        return _read(path)
    return {"reserved": {"calls": 0, "input_bytes": 0, "output_tokens": 0, "dollars": "0"}, "requests": {}}


class FrozenTransport:
    """Matches a real caller request and makes its provider attempt once."""
    def __init__(self, delegate: Any, model_arm: str, role: str, expected: list[dict[str, Any]], response_directory: Path, ledger_path: Path, limits: dict[str, Any], *, socket_idle_timeout_seconds: int = 60):
        self.delegate, self.model_arm, self.role = delegate, model_arm, role
        self.expected = {digest(body): body for body in expected}
        if len(self.expected) != len(expected):
            raise ValueError("duplicate frozen requests")
        self.response_directory, self.ledger_path, self.limits = response_directory, ledger_path, limits
        self.socket_idle_timeout_seconds = socket_idle_timeout_seconds
        self.response_directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.measurements: list[dict[str, Any]] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self.delegate, name)

    def _canonical(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        request = dict(kwargs)
        if self.model_arm == "0731":
            for key, value in {"temperature": 1.0, "top_p": 1.0, "seed": 42}.items():
                if key in request and request[key] != value:
                    raise ValueError("0731 caller setting drift: " + key)
                request[key] = value
        return request

    def _reserve(self, identity: str, request: dict[str, Any]) -> None:
        with self.lock:
            ledger = _ledger(self.ledger_path)
            if identity in ledger["requests"]:
                raise ConsumedRequestError("request_already_consumed")
            addition = {"calls": 1, "input_bytes": len(encoded(request)) + 2048, "output_tokens": int(request.get("max_tokens", 0))}
            current = ledger["reserved"]
            prospective = {key: int(current[key]) + amount for key, amount in addition.items()}
            if any(prospective[key] > int(self.limits[key]) for key in addition):
                raise ConsumedRequestError("frozen_arm_ceiling_exceeded")
            # Money is limited by the frozen planning reservation for every consumed
            # request, not by a mutable estimate reported after the call.
            prospective_dollars = Decimal(current["dollars"]) + (
                Decimal(addition["input_bytes"]) * INPUT_CEILING_PER_M + Decimal(addition["output_tokens"]) * OUTPUT_CEILING_PER_M
            ) / Decimal(1_000_000)
            if prospective_dollars > Decimal(self.limits["dollars"]):
                raise ConsumedRequestError("frozen_dollar_ceiling_exceeded")
            ledger["reserved"] = {**prospective, "dollars": str(prospective_dollars)}
            ledger["requests"][identity] = {"role": self.role, "reserved": addition, "started_at": datetime.now(timezone.utc).isoformat()}
            write(self.ledger_path, ledger)

    def messages_create(self, **kwargs: Any) -> Any:
        request = self._canonical(kwargs)
        identity = digest(request)
        if identity not in self.expected:
            raise ConsumedRequestError("caller_request_not_frozen")
        marker = self.response_directory / f"{identity}.started"
        try:
            with marker.open("x", encoding="utf-8") as file:
                file.write(datetime.now(timezone.utc).isoformat())
        except FileExistsError as exc:
            raise ConsumedRequestError("request_already_attempted") from exc
        self._reserve(identity, request)
        started = time.monotonic()
        measurement: dict[str, Any] = {"request_sha256": identity, "role": self.role, "status": "started", "request": request}
        try:
            # Prepared translation kwargs intentionally omit timeout because
            # that is the true caller shape. Inject the role's frozen socket
            # idle timeout only after matching the request. It is not a wall
            # deadline: a provider that keeps the socket active can exceed it.
            delegate_request = dict(request)
            delegate_request.setdefault("timeout", self.socket_idle_timeout_seconds)
            measurement["socket_idle_timeout_seconds"] = delegate_request["timeout"]
            response = self.delegate.messages_create(**delegate_request)
            measurement["status"] = "received"
            measurement["usage"] = getattr(response, "provider_usage", None)
            write(self.response_directory / f"{identity}.response.json", response)
            return response
        except Exception as exc:
            measurement.update(status="error", error_type=type(exc).__name__, error=str(exc), usage=getattr(exc, "provider_usage", None))
            # The true translator retries ordinary exceptions. Returning an
            # intentionally invalid parsed response makes that caller mark the
            # batch failed immediately, with no 1s/2s backoff and no chance of
            # a second provider attempt. Synthesis then rejects the same empty
            # schema and records its per-post failure.
            measurement["caller_response"] = "empty_object_after_consumed_provider_error"
            return {}
        finally:
            measurement["latency_ms"] = round((time.monotonic() - started) * 1000)
            write(self.response_directory / f"{identity}.measurement.json", measurement)
            with self.lock:
                self.measurements.append(measurement)


def _secret(name: str) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    path = Path.home() / ".env.secrets"
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        matched = re.match(rf"^\s*(?:export\s+)?{re.escape(name)}\s*=\s*(.*)$", line)
        if matched:
            parts = shlex.split(matched.group(1), comments=True)
            if len(parts) == 1:
                return parts[0]
            raise ValueError(f"{name} must contain one literal value")
    return None


def credential(model_arm: str) -> str:
    name = "DEEPSEEK_API_KEY" if model_arm == "incumbent" else "OPENROUTER_API_KEY"
    value = _secret(name)
    if not value:
        raise ValueError(name + " unavailable")
    return value


def build_client(model_arm: str, api_key: str) -> Any:
    if model_arm == "incumbent":
        return AnthropicClaudeClient(api_key=api_key, base_url="https://api.deepseek.com/anthropic")
    return OpenRouterChatCompletionsClient(
        api_key=api_key, model=TARGET_MODEL, provider="DeepInfra", response_provider="DeepInfra",
        response_model="deepseek/deepseek-v4-flash-20260731", endpoint_tag=TARGET_ENDPOINT,
        quantizations=["fp8"], reasoning_enabled=False, data_collection="allow", zdr=False,
        max_input_price=float(INPUT_CEILING_PER_M), max_output_price=float(OUTPUT_CEILING_PER_M),
        request_profile="deepseek_0731",
    )


def price_preflight(model_arm: str) -> dict[str, Any]:
    """Capture a public price receipt; lack of a direct price never becomes a pass."""
    observed_at = datetime.now(timezone.utc).isoformat()
    if model_arm == "incumbent":
        url = "https://api-docs.deepseek.com/quick_start/pricing/"
        try:
            with urllib.request.urlopen(url, timeout=25) as response:
                body = response.read().decode("utf-8", errors="replace")
            # Current official Flash peak prices: cache-miss $0.30/M, output $1.20/M.
            found = re.search(r"(?:0[.,]30|0\.3).{0,120}(?:1[.,]20|1\.2)", body, re.IGNORECASE | re.DOTALL)
            result = {"url": url, "observed_at": observed_at, "retrieval": "ok", "model_identity": "DeepSeek-V4.1-Flash (legacy deepseek-v4-flash request retained)", "rates_usd_per_million": {"input_cache_miss": "0.30", "output": "1.20"}, "rate_table_machine_matched": bool(found), "cost_gate_ready": False}
            if found and (Decimal("0.30") > INPUT_CEILING_PER_M or Decimal("1.20") > OUTPUT_CEILING_PER_M):
                raise PriceCeilingError("advertised incumbent price exceeds execution ceiling")
            return result
        except PriceCeilingError:
            raise
        except Exception as exc:
            return {"url": url, "observed_at": observed_at, "retrieval": "unverified", "reason": type(exc).__name__, "cost_gate_ready": False}
    url = f"https://openrouter.ai/api/v1/models/{TARGET_MODEL}/endpoints"
    try:
        with urllib.request.urlopen(url, timeout=25) as response:
            rows = json.load(response).get("data", {}).get("endpoints", [])
        selected = [row for row in rows if row.get("tag") == TARGET_ENDPOINT and row.get("provider_name") == "DeepInfra"]
        if len(selected) != 1:
            raise EndpointPreflightError("pinned 0731 endpoint missing or ambiguous")
        endpoint = selected[0]
        parameters = endpoint.get("supported_parameters") or []
        if (
            endpoint.get("status") != 0
            or endpoint.get("quantization") != "fp8"
            or not {"temperature", "top_p", "seed", "reasoning", "max_tokens"}.issubset(parameters)
        ):
            raise EndpointPreflightError("pinned 0731 endpoint health, quantization, or parameters changed")
        pricing = endpoint.get("pricing") or {}
        input_rate, output_rate = Decimal(str(pricing["prompt"])) * 1_000_000, Decimal(str(pricing["completion"])) * 1_000_000
        if input_rate > INPUT_CEILING_PER_M or output_rate > OUTPUT_CEILING_PER_M:
            raise PriceCeilingError("advertised 0731 price exceeds execution ceiling")
        return {"url": url, "observed_at": observed_at, "retrieval": "ok", "endpoint": TARGET_ENDPOINT, "status": endpoint["status"], "quantization": endpoint["quantization"], "supported_parameters": sorted(parameters), "rates_usd_per_million": {"input": str(input_rate), "output": str(output_rate)}, "cost_gate_ready": True}
    except PriceCeilingError:
        raise
    except EndpointPreflightError:
        raise
    except Exception as exc:
        return {"url": url, "observed_at": observed_at, "retrieval": "unverified", "reason": type(exc).__name__, "cost_gate_ready": False}


def _translation_inputs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"tweet_id": row["post_id"], "text": row["text"]} for row in rows]


def _context(row: dict[str, Any]) -> dict[str, str]:
    result = {"post": row["text"]}
    for item in row.get("context", []):
        if isinstance(item, dict) and item.get("provenance") and item.get("text"):
            result[str(item["provenance"])] = str(item["text"])
    return result


def _usage_summary(measurements: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep reported provider usage even when caller-level validation fails."""
    keys = ("input_tokens", "output_tokens", "reasoning_tokens")
    totals = {key: 0 for key in keys}
    costs: list[Decimal] = []
    complete = len(measurements) > 0
    for measurement in measurements:
        usage = measurement.get("usage")
        if not isinstance(usage, dict):
            complete = False
            continue
        for key in keys:
            value = usage.get(key)
            if isinstance(value, int) and value >= 0:
                totals[key] += value
            elif value is not None:
                complete = False
        value = usage.get("cost_usd")
        if value is None:
            complete = False
        else:
            try:
                costs.append(Decimal(str(value)))
            except Exception:
                complete = False
    return {**totals, "billed_cost_usd": str(sum(costs, Decimal("0"))), "billed_cost_complete": complete}


@contextlib.contextmanager
def _model_arm_lock(directory: Path):
    """Serialize the two role commands across processes around one ledger."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ".run.lock"
    with path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ConsumedRequestError("model arm is already running") from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def run_arm(execution_directory: Path, model_arm: str, role: str) -> dict[str, Any]:
    if model_arm not in {"incumbent", "0731"} or role not in {"translation", "synthesis"}:
        raise ValueError("model arm and role must be selected explicitly")
    contract, prepared, requests = load_execution(execution_directory)
    arm_root = execution_directory / "arms" / model_arm
    with _model_arm_lock(arm_root):
        arm_directory = arm_root / role
        if (arm_directory / "run.started").exists():
            raise ConsumedRequestError("role arm already started; no replay command exists")
        preflight = price_preflight(model_arm)
        key = credential(model_arm)
        arm_directory.mkdir(parents=True, exist_ok=True)
        with (arm_directory / "run.started").open("x", encoding="utf-8") as marker:
            marker.write(datetime.now(timezone.utc).isoformat())
        transport = FrozenTransport(build_client(model_arm, key), model_arm, role, requests[model_arm][role], arm_directory / "responses", arm_root / "call-ledger.json", contract["limits"]["model_arm"][model_arm], socket_idle_timeout_seconds=contract["limits"]["adapter_socket_idle_timeout_seconds"][role])
        started = time.monotonic()
        if role == "translation":
            cfg = SimpleNamespace(llm=SimpleNamespace(translator_model=contract["routes"][model_arm]["model"], translator_base_url="https://api.deepseek.com/anthropic" if model_arm == "incumbent" else "https://openrouter.ai/api/v1"))
            output = translate_batch_literal(_translation_inputs(prepared["rows"]), transport, cfg=cfg, max_workers=1)
            completeness = {"rows": len(output), "complete_rows": sum(not row.get("translation_failed") for row in output)}
        else:
            config = SimpleNamespace(model=contract["routes"][model_arm]["model"], max_input_tokens_per_post=4000, max_output_tokens_per_post=_uniform_role_max_tokens(requests, model_arm, role), timeout_seconds=contract["limits"]["adapter_socket_idle_timeout_seconds"][role])
            output = []
            for row in prepared["rows"]:
                try:
                    result = synthesize_post(post_id=row["post_id"], context=_context(row), client=transport, config=config)
                    output.append({"post_id": row["post_id"], "status": "complete", "texts": result.texts, "input_tokens": result.input_tokens, "output_tokens": result.output_tokens, "latency_ms": result.latency_ms})
                except Exception as exc:
                    output.append({"post_id": row["post_id"], "status": "error", "error_type": type(exc).__name__})
            completeness = {"rows": len(output), "complete_rows": sum(row["status"] == "complete" for row in output)}
        report = {"execution_contract_sha256": _sha(execution_directory / "execution-contract.json"), "model_arm": model_arm, "role": role, "elapsed_ms": round((time.monotonic() - started) * 1000), "preflight": preflight, "measurements": transport.measurements, "billed_usage": _usage_summary(transport.measurements), "completeness": completeness, "output": output, "semantic_accuracy_claim": False, "database_touched": False, "classifier_called": False, "publication": False}
        write(arm_directory / "report.json", report)
        return report


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="action", required=True)
    prepare = commands.add_parser("prepare-execution")
    prepare.add_argument("prepared_directory", type=Path)
    prepare.add_argument("execution_directory", type=Path)
    run = commands.add_parser("run-arm")
    run.add_argument("execution_directory", type=Path)
    run.add_argument("model_arm", choices=("incumbent", "0731"))
    run.add_argument("role", choices=("translation", "synthesis"))
    args = parser.parse_args()
    result = prepare_execution(args.prepared_directory, args.execution_directory) if args.action == "prepare-execution" else run_arm(args.execution_directory, args.model_arm, args.role)
    print(json.dumps({"action": args.action, "result": {"schema": result.get("schema"), "model_arm": result.get("model_arm"), "role": result.get("role"), "complete_rows": result.get("completeness", {}).get("complete_rows")}}, indent=2))


if __name__ == "__main__":
    main()
