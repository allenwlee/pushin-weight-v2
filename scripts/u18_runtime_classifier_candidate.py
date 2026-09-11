"""Run the exact Stage 1 runtime classifier against a frozen U18 cohort.

The provider client reserves request, token, and dollar capacity before every
transport attempt. Successful raw responses are cached by prompt occurrence,
so an interrupted run can replay completed requests without spending again.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import threading
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from core.classification_contract import (
    CANONICAL_PROMPT_VERSION,
    CANONICAL_TAXONOMY_VERSION,
    CONTRACT_VERSION,
)
from x_monitor.attribution import classify_batch_pragmatics_full
from x_monitor.provider_telemetry import normalize_usage
from x_monitor.translator import AnthropicClaudeClient


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUDGET = (
    ROOT / "docs/analysis/2026-09-11-153500-u18-runtime-v11-development-budget.json"
)
DEFAULT_COHORT = ROOT / ".context/u18/cohort-source.json"
DEFAULT_OUTPUT = ROOT / ".context/u18/candidate-v11-runtime-development.json"
DEFAULT_PRIVATE = ROOT / ".context/u18/runtime-v11-development"


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


class FrozenRuntimeClient:
    """Anthropic-compatible client with a preregistered, persistent cap."""

    def __init__(
        self,
        *,
        budget_path: Path,
        lane: str,
        private_dir: Path,
        delegate: Any | None = None,
    ) -> None:
        document = _read_json(budget_path)
        self.budget_path = budget_path
        self.budget = document["lanes"][lane]
        self.lane = lane
        self.private_dir = private_dir
        self.response_dir = private_dir / "responses"
        self.state_path = private_dir / "usage.json"
        self._lock = threading.Lock()
        self._occurrences: dict[str, int] = {}
        self._active: dict[str, str] = {}
        self.state = (
            _read_json(self.state_path)
            if self.state_path.exists()
            else {
                "lane": lane,
                "budget_sha256": _sha256_file(budget_path),
                "logical_request_ids": [],
                "attempts_by_request": {},
                "transport_attempts": 0,
                "reserved_input_tokens": 0,
                "reserved_output_tokens": 0,
                "observed_input_tokens": 0,
                "observed_output_tokens": 0,
                "errors": [],
            }
        )
        if self.state.get("budget_sha256") != _sha256_file(budget_path):
            raise RuntimeError("runtime budget changed after usage began")
        if delegate is None:
            api_key = os.environ.get("DEEPSEEK_API_KEY")
            if not api_key:
                raise RuntimeError("DEEPSEEK_API_KEY is required")
            delegate = AnthropicClaudeClient(
                api_key=api_key,
                base_url="https://api.deepseek.com/anthropic",
            )
        self._delegate = delegate
        self._base_url = getattr(delegate, "_base_url", None)

    def _persist(self) -> None:
        self.state["updated_at"] = datetime.now(UTC).isoformat()
        _write_json(self.state_path, self.state)

    @staticmethod
    def _signature(kwargs: Mapping[str, Any]) -> str:
        canonical = json.dumps(
            kwargs,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            default=str,
        ).encode("utf-8")
        return _sha256_bytes(canonical)

    def _request_id(self, signature: str) -> str:
        active = self._active.get(signature)
        if active is not None:
            attempts = self.state["attempts_by_request"].get(active, 0)
            if attempts < 1 + self.budget["maximum_retries_per_request"]:
                return active
            self._active.pop(signature, None)
            self._occurrences[signature] = self._occurrences.get(signature, 0) + 1
        occurrence = self._occurrences.get(signature, 0)
        request_id = f"{signature}:{occurrence:02d}"
        self._active[signature] = request_id
        return request_id

    def _complete(self, signature: str) -> None:
        self._active.pop(signature, None)
        self._occurrences[signature] = self._occurrences.get(signature, 0) + 1

    def _validate_call(self, kwargs: Mapping[str, Any]) -> tuple[str, str]:
        if kwargs.get("model") != self.budget["model"]:
            raise RuntimeError("runtime model differs from frozen budget")
        if kwargs.get("max_tokens") != self.budget["max_tokens_per_attempt"]:
            raise RuntimeError("runtime output cap differs from frozen budget")
        if kwargs.get("temperature") != self.budget["temperature"]:
            raise RuntimeError("runtime temperature differs from frozen budget")
        if kwargs.get("thinking") != {"type": "disabled"}:
            raise RuntimeError("runtime thinking mode differs from frozen budget")
        system = kwargs.get("system")
        messages = kwargs.get("messages")
        if not isinstance(system, str) or not isinstance(messages, list):
            raise RuntimeError("runtime request has an invalid message envelope")
        if len(messages) != 1 or messages[0].get("role") != "user":
            raise RuntimeError("runtime request must contain one user message")
        user = messages[0].get("content")
        if not isinstance(user, str):
            raise RuntimeError("runtime user message must be text")
        system_hash = _sha256_bytes(system.encode("utf-8"))
        if system_hash not in self.budget["allowed_system_sha256"]:
            raise RuntimeError("runtime system prompt is outside the frozen budget")
        return system, user

    def _reserve(self, request_id: str, *, system: str, user: str) -> None:
        logical_ids = self.state["logical_request_ids"]
        is_new = request_id not in logical_ids
        if is_new and len(logical_ids) >= self.budget["maximum_requests"]:
            raise RuntimeError("runtime logical request cap exhausted")
        if self.state["transport_attempts"] >= self.budget["maximum_transport_attempts"]:
            raise RuntimeError("runtime transport attempt cap exhausted")
        attempts = self.state["attempts_by_request"].get(request_id, 0)
        if attempts >= 1 + self.budget["maximum_retries_per_request"]:
            raise RuntimeError("runtime per-request retry cap exhausted")
        reserved_input = math.ceil(
            (len(system.encode("utf-8")) + len(user.encode("utf-8"))) / 2
        )
        next_input = self.state["reserved_input_tokens"] + reserved_input
        next_output = (
            self.state["reserved_output_tokens"]
            + self.budget["max_tokens_per_attempt"]
        )
        if next_input > self.budget["maximum_input_tokens"]:
            raise RuntimeError("runtime input-token cap exhausted")
        if next_output > self.budget["maximum_output_tokens"]:
            raise RuntimeError("runtime output-token cap exhausted")
        maximum_cost = (
            Decimal(next_input) * Decimal(self.budget["input_usd_per_million"])
            + Decimal(next_output) * Decimal(self.budget["output_usd_per_million"])
        ) / Decimal(1_000_000)
        if maximum_cost > Decimal(self.budget["maximum_cost_usd"]):
            raise RuntimeError("runtime dollar cap exhausted")
        if is_new:
            logical_ids.append(request_id)
        self.state["attempts_by_request"][request_id] = attempts + 1
        self.state["transport_attempts"] += 1
        self.state["reserved_input_tokens"] = next_input
        self.state["reserved_output_tokens"] = next_output
        self._persist()

    def messages_create(self, **kwargs: Any) -> dict[str, Any]:
        system, user = self._validate_call(kwargs)
        signature = self._signature(kwargs)
        with self._lock:
            request_id = self._request_id(signature)
            response_path = self.response_dir / f"{request_id.replace(':', '_')}.json"
            if response_path.exists():
                response = _read_json(response_path)
                self._complete(signature)
                return response
            self._reserve(request_id, system=system, user=user)
        try:
            response = self._delegate.messages_create(**kwargs)
        except Exception as exc:
            with self._lock:
                self.state["errors"].append(
                    {"request_id": request_id, "type": type(exc).__name__}
                )
                self._persist()
            raise
        usage = normalize_usage(getattr(response, "provider_usage", None))
        with self._lock:
            self.state["observed_input_tokens"] += usage["input_tokens"] or 0
            self.state["observed_output_tokens"] += usage["output_tokens"] or 0
            _write_json(response_path, dict(response))
            self._complete(signature)
            self._persist()
        return dict(response)


def _candidate_row(source: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    brand_id = source["brand_id"]
    classification = (result.get("by_brand") or {}).get(brand_id)
    if not result.get("valid") or not isinstance(classification, Mapping):
        raise RuntimeError(f"runtime classifier returned no valid row for {source['example_id']}")
    return {
        **{
            key: source[key]
            for key in (
                "example_id",
                "brand_id",
                "source_language",
                "context_provenance",
                "input_context_fingerprint",
                "stratum",
                "source_role",
                "source_hint",
            )
        },
        "classification": dict(classification),
    }


def run(*, budget_path: Path, cohort_path: Path, output_path: Path, private_dir: Path) -> None:
    budget_document = _read_json(budget_path)
    lane = budget_document["lane"]
    cohort = _read_json(cohort_path)
    if _sha256_file(cohort_path) != budget_document["cohort"]["sha256"]:
        raise RuntimeError("cohort bytes differ from the frozen budget")
    rows = cohort.get("rows")
    if not isinstance(rows, list) or len(rows) != budget_document["cohort"]["rows"]:
        raise RuntimeError("cohort rows differ from the frozen budget")
    tracked_changes = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if tracked_changes:
        raise RuntimeError("commit tracked runtime changes before paid evaluation")
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    client = FrozenRuntimeClient(
        budget_path=budget_path,
        lane=lane,
        private_dir=private_dir,
    )
    results = classify_batch_pragmatics_full(
        [dict(row["input"]) for row in rows],
        [],
        client,
        model=client.budget["model"],
        max_tokens=client.budget["max_tokens_per_attempt"],
        thinking={"type": "disabled"},
        max_workers=3,
        telemetry_context={"stage": "u18_runtime_development"},
    )
    if len(results) != len(rows):
        raise RuntimeError("runtime classifier changed cohort cardinality")
    output = {
        "schema_version": 1,
        "provenance": {
            "kind": "candidate_output",
            "gold": False,
            "cohort_id": cohort["cohort_id"],
            "contract_version": CONTRACT_VERSION,
            "taxonomy_version": CANONICAL_TAXONOMY_VERSION,
            "prompt_version": CANONICAL_PROMPT_VERSION,
            "model": client.budget["model"],
            "source_revision": revision,
            "generated_at": datetime.now(UTC).isoformat(),
            "budget_sha256": _sha256_file(budget_path),
            "production_call_path": "classify_batch_pragmatics_full",
        },
        "rows": sorted(
            (_candidate_row(source, result) for source, result in zip(rows, results)),
            key=lambda row: (row["example_id"], row["brand_id"]),
        ),
    }
    _write_json(output_path, output)
    print(
        json.dumps(
            {
                "candidate": str(output_path),
                "candidate_sha256": _sha256_file(output_path),
                "rows": len(output["rows"]),
                "transport_attempts": client.state["transport_attempts"],
                "observed_input_tokens": client.state["observed_input_tokens"],
                "observed_output_tokens": client.state["observed_output_tokens"],
            },
            sort_keys=True,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget", type=Path, default=DEFAULT_BUDGET)
    parser.add_argument("--cohort", type=Path, default=DEFAULT_COHORT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--private-dir", type=Path, default=DEFAULT_PRIVATE)
    args = parser.parse_args()
    run(
        budget_path=args.budget.resolve(),
        cohort_path=args.cohort.resolve(),
        output_path=args.output.resolve(),
        private_dir=args.private_dir.resolve(),
    )


if __name__ == "__main__":
    main()
