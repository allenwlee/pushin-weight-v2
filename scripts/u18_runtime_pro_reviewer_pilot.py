"""Build and run the bounded U18 v27 DeepSeek Pro reviewer pilot.

The pilot is deliberately separate from the production candidate runner.  It
reviews a saved fallible classification, then scores the review against the
owner accepted unblinded reference.  The reference is an owner override and
is never represented as human gold.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import threading
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from core.classification_contract import (
    CANONICAL_POST_TYPE_KEYS,
    CANONICAL_TAXONOMY_VERSION,
    CLASSIFICATION_FIELDS,
    CONTRACT_VERSION,
    PRODUCT_LABEL_KEYS,
    parse_stage1_classifications,
)
from x_monitor.attribution import (
    _PRAGMATICS_COMPLETENESS_REVIEW_PROMPT_VERSION,
    _PRAGMATICS_COMPLETENESS_REVIEW_SYSTEM_PROMPT,
    _partition_completeness_review_response,
)
from x_monitor.provider_telemetry import normalize_usage
from x_monitor.translator import AnthropicClaudeClient

ROOT = Path(__file__).resolve().parents[1]
STUDY_DIR = ROOT / ".context/u18/human-ambiguity-study-v1"
DEFAULT_SOURCE = ROOT / ".context/u18/thinking-probe-cohort.json"
DEFAULT_MANIFEST = STUDY_DIR / "selection-manifest.json"
DEFAULT_CANDIDATE = ROOT / ".context/u18/candidate-v26-exhaustive-verdict-review.json"
DEFAULT_REFERENCE = STUDY_DIR / "owner-accepted-reference.json"
DEFAULT_RUN_DIR = ROOT / ".context/u18/u18-owner-accepted-v27-pro-review-pilot-v1"
DEFAULT_COHORT = DEFAULT_RUN_DIR / "cohort.json"
DEFAULT_REFERENCE_SUBSET = DEFAULT_RUN_DIR / "owner-reference.json"
DEFAULT_CANDIDATE_OUTPUT = DEFAULT_RUN_DIR / "candidate.json"
DEFAULT_DIAGNOSTIC = DEFAULT_RUN_DIR / "evaluation.json"

PILOT_ID = "u18-owner-accepted-v27-pro-review-pilot-v1"
PILOT_LANE = "runtime_v27_deepseek_pro_owner_accepted_reviewer_pilot"
PILOT_BATCH_SIZE = 5
PILOT_MAX_WORKERS = 3
PILOT_REVIEW_RETRIES = 1
PILOT_MAX_REQUESTS = 6
PILOT_MAX_TRANSPORT_ATTEMPTS = 12
PILOT_MAX_INPUT_TOKENS = 150_000
PILOT_MAX_OUTPUT_TOKENS = 49_152
PILOT_MAX_COST_USD = Decimal("0.42")
INPUT_USD_PER_MILLION = Decimal("1.32")
OUTPUT_USD_PER_MILLION = Decimal("3.96")
PROMPT_SHA256 = hashlib.sha256(
    _PRAGMATICS_COMPLETENESS_REVIEW_SYSTEM_PROMPT.encode("utf-8")
).hexdigest()
HARD_BUCKETS = frozenset({"stable_model_vs_gold", "model_run_conflict"})
EXPECTED_CLASSIFICATION_FIELDS = frozenset(CLASSIFICATION_FIELDS) - {"brand_id"}


class PilotInputError(ValueError):
    """A cohort, reference, or candidate violates the pilot contract."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PilotInputError(f"could not read JSON artifact: {path}") from exc
    if not isinstance(value, dict):
        raise PilotInputError(f"JSON artifact must be an object: {path}")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_rows(path: Path) -> dict[str, dict[str, Any]]:
    document = _read_json(path)
    rows = document.get("rows")
    if not isinstance(rows, list):
        raise PilotInputError("source cohort rows must be an array")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("example_id"), str):
            raise PilotInputError("source cohort contains an invalid row")
        if row["example_id"] in result:
            raise PilotInputError(f"duplicate source example_id: {row['example_id']}")
        if not isinstance(row.get("input"), dict):
            raise PilotInputError(f"source row lacks input: {row['example_id']}")
        result[row["example_id"]] = row
    return result


def _rows_by_pair(rows: Any, label: str) -> dict[tuple[str, str], dict[str, Any]]:
    if not isinstance(rows, list):
        raise PilotInputError(f"{label} rows must be an array")
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("example_id"), str)
            or not isinstance(row.get("brand_id"), str)
        ):
            raise PilotInputError(f"{label} contains an invalid row")
        pair = (row["example_id"], row["brand_id"])
        if pair in result:
            raise PilotInputError(f"{label} contains duplicate pair: {pair}")
        result[pair] = row
    return result


def _rows_by_example_id(
    rows: Mapping[tuple[str, str], dict[str, Any]], label: str
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows.values():
        example_id = row["example_id"]
        if example_id in result:
            raise PilotInputError(f"{label} contains duplicate example_id: {example_id}")
        result[example_id] = row
    return result


def _classification(value: Any, brand_id: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise PilotInputError(f"classification is not an object for {brand_id}")
    row = dict(value)
    if set(row) != EXPECTED_CLASSIFICATION_FIELDS:
        raise PilotInputError(f"classification fields differ for {brand_id}")
    parsed = parse_stage1_classifications([{"brand_id": brand_id, **row}], [brand_id])
    if parsed is None:
        raise PilotInputError(
            f"classification violates the closed contract for {brand_id}"
        )
    return parsed[brand_id]


def _build_rows(
    *,
    source_path: Path,
    manifest_path: Path,
    candidate_path: Path,
    reference_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    source = _source_rows(source_path)
    manifest = _read_json(manifest_path)
    manifest_rows = manifest.get("rows")
    if not isinstance(manifest_rows, list):
        raise PilotInputError("selection manifest rows must be an array")
    candidate = _read_json(candidate_path)
    candidate_rows = candidate.get("rows")
    if not isinstance(candidate_rows, list):
        raise PilotInputError("candidate rows must be an array")
    candidate_by_pair = _rows_by_pair(candidate_rows, "candidate")
    candidate_by_id = _rows_by_example_id(candidate_by_pair, "candidate")
    reference = _read_json(reference_path)
    if reference.get("status") != "owner_accepted_unblinded":
        raise PilotInputError("reference is not the owner accepted unblinded artifact")
    if reference.get("human_grounded") is not False:
        raise PilotInputError(
            "owner reference must explicitly remain non-human-grounded"
        )
    reference_rows = reference.get("rows")
    if not isinstance(reference_rows, list):
        raise PilotInputError("owner reference rows must be an array")
    reference_by_pair = _rows_by_pair(reference_rows, "owner reference")
    reference_by_id = _rows_by_example_id(reference_by_pair, "owner reference")

    selected = sorted(
        (
            row
            for row in manifest_rows
            if isinstance(row, dict) and row.get("selection_bucket") in HARD_BUCKETS
        ),
        key=lambda row: (str(row.get("source_language")), str(row.get("case_id"))),
    )
    if len(selected) != 30:
        raise PilotInputError(
            f"hard-case selection contains {len(selected)} rows, expected 30"
        )
    if Counter(row.get("source_language") for row in selected) != Counter(
            {"en": 10, "ja": 10, "zh-cn": 10}
    ):
        raise PilotInputError("hard-case selection must contain 10 rows per language")
    if len({row.get("example_id") for row in selected}) != len(selected):
        raise PilotInputError("hard-case selection contains duplicate example_id")

    rows: list[dict[str, Any]] = []
    reference_subset: list[dict[str, Any]] = []
    for selected_row in selected:
        example_id = selected_row.get("example_id")
        brand_id = selected_row.get("brand_id")
        if not isinstance(example_id, str) or not isinstance(brand_id, str):
            raise PilotInputError("manifest row lacks example_id or brand_id")
        source_row = source.get(example_id)
        candidate_row = candidate_by_id.get(example_id)
        reference_row = reference_by_id.get(example_id)
        if source_row is None or candidate_row is None or reference_row is None:
            raise PilotInputError(f"missing linked artifact row: {example_id}")
        if (
            source_row.get("brand_id") != brand_id
            or candidate_row.get("brand_id") != brand_id
        ):
            raise PilotInputError(f"brand identity mismatch: {example_id}")
        if reference_row.get("brand_id") != brand_id:
            raise PilotInputError(f"reference brand identity mismatch: {example_id}")
        if source_row.get("source_language") != selected_row.get("source_language"):
            raise PilotInputError(f"source language mismatch: {example_id}")
        primary = _classification(candidate_row.get("classification"), brand_id)
        accepted = _classification(reference_row.get("classification"), brand_id)
        input_value = source_row["input"]
        if not isinstance(source_row.get("input_context_fingerprint"), str):
            raise PilotInputError(f"source row lacks context fingerprint: {example_id}")
        rows.append(
            {
                "case_id": selected_row["case_id"],
                "example_id": example_id,
                "brand_id": brand_id,
                "source_language": selected_row["source_language"],
                "context_provenance": source_row.get("context_provenance", []),
                "input_context_fingerprint": source_row.get(
                    "input_context_fingerprint"
                ),
                "input": input_value,
                "primary": primary,
            }
        )
        reference_subset.append(
            {
                "case_id": selected_row["case_id"],
                "example_id": example_id,
                "brand_id": brand_id,
                "source_language": selected_row["source_language"],
                "classification": accepted,
            }
        )

    cohort = {
        "schema_version": 1,
        "cohort_id": PILOT_ID,
        "development_only": True,
        "selection": {
            "source_manifest_sha256": _sha256_file(manifest_path),
            "source_cohort_sha256": _sha256_file(source_path),
            "candidate_input_sha256": _sha256_file(candidate_path),
            "owner_reference_sha256": _sha256_file(reference_path),
            "hard_case_buckets": sorted(HARD_BUCKETS),
            "rows_per_language": 10,
            "controls_excluded": True,
        },
        "rows": rows,
    }
    reference_subset_document = {
        "schema_version": 1,
        "study_id": reference.get("study_id"),
        "status": reference["status"],
        "human_grounded": False,
        "owner_responsibility_assumed": reference.get("owner_responsibility_assumed"),
        "source_reference_sha256": _sha256_file(reference_path),
        "source_reference_path": str(reference_path),
        "rows": reference_subset,
    }
    return cohort, reference_subset_document


def build_inputs(
    *,
    source_path: Path = DEFAULT_SOURCE,
    manifest_path: Path = DEFAULT_MANIFEST,
    candidate_path: Path = DEFAULT_CANDIDATE,
    reference_path: Path = DEFAULT_REFERENCE,
    cohort_path: Path = DEFAULT_COHORT,
    reference_subset_path: Path = DEFAULT_REFERENCE_SUBSET,
) -> None:
    cohort, reference_subset = _build_rows(
        source_path=source_path,
        manifest_path=manifest_path,
        candidate_path=candidate_path,
        reference_path=reference_path,
    )
    _write_json(cohort_path, cohort)
    _write_json(reference_subset_path, reference_subset)
    print(
        json.dumps(
            {
                "cohort": str(cohort_path),
                "cohort_sha256": _sha256_file(cohort_path),
                "reference_subset": str(reference_subset_path),
                "reference_subset_sha256": _sha256_file(reference_subset_path),
                "rows": len(cohort["rows"]),
            },
            sort_keys=True,
        )
    )


class BudgetedPilotClient:
    """DeepSeek transport with a persistent, non-transferable hard cap."""

    def __init__(
        self, *, budget_path: Path, private_dir: Path, delegate: Any | None = None
    ):
        document = _read_json(budget_path)
        if document.get("lane") != PILOT_LANE:
            raise PilotInputError(
                "budget lane does not identify the v27 Pro reviewer pilot"
            )
        self.budget = document["lanes"][PILOT_LANE]
        expected_budget = {
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "temperature": 0,
            "thinking": {"type": "disabled"},
            "batch_size": PILOT_BATCH_SIZE,
            "maximum_requests": PILOT_MAX_REQUESTS,
            "maximum_retries_per_request": PILOT_REVIEW_RETRIES,
            "maximum_transport_attempts": PILOT_MAX_TRANSPORT_ATTEMPTS,
            "maximum_input_tokens": PILOT_MAX_INPUT_TOKENS,
            "maximum_output_tokens": PILOT_MAX_OUTPUT_TOKENS,
            "maximum_cost_usd": str(PILOT_MAX_COST_USD),
            "max_concurrent_transport_calls": PILOT_MAX_WORKERS,
        }
        for key, expected in expected_budget.items():
            if self.budget.get(key) != expected:
                raise PilotInputError(f"budget cap differs from frozen pilot: {key}")
        self.budget_path = budget_path
        self.private_dir = private_dir
        self.response_dir = private_dir / "responses" / PILOT_LANE
        self.state_path = private_dir / "usage.json"
        self.lock = threading.Lock()
        self.state = (
            _read_json(self.state_path)
            if self.state_path.exists()
            else {
                "lane": PILOT_LANE,
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
            raise PilotInputError("budget changed after pilot usage began")
        if delegate is None:
            api_key = os.environ.get(self.budget["credential_env"])
            if not api_key:
                raise PilotInputError(f"{self.budget['credential_env']} is required")
            delegate = AnthropicClaudeClient(
                api_key=api_key,
                base_url=self.budget["base_url"],
            )
        self.delegate = delegate

    def _persist(self) -> None:
        self.state["updated_at"] = datetime.now(UTC).isoformat()
        _write_json(self.state_path, self.state)

    def _reserve(self, request_id: str, system: str, user: str) -> int:
        with self.lock:
            attempts = self.state["attempts_by_request"].get(request_id, 0)
            if request_id not in self.state["logical_request_ids"]:
                if (
                    len(self.state["logical_request_ids"])
                    >= self.budget["maximum_requests"]
                ):
                    raise RuntimeError("pilot logical request cap exhausted")
                self.state["logical_request_ids"].append(request_id)
            if (
                self.state["transport_attempts"]
                >= self.budget["maximum_transport_attempts"]
            ):
                raise RuntimeError("pilot transport attempt cap exhausted")
            if attempts > self.budget["maximum_retries_per_request"]:
                raise RuntimeError("pilot per-request retry cap exhausted")
            input_tokens = math.ceil(
                (len(system.encode("utf-8")) + len(user.encode("utf-8"))) / 2
            )
            next_input = self.state["reserved_input_tokens"] + input_tokens
            next_output = (
                self.state["reserved_output_tokens"]
                + self.budget["max_tokens_per_attempt"]
            )
            if next_input > self.budget["maximum_input_tokens"]:
                raise RuntimeError("pilot input-token cap exhausted")
            if next_output > self.budget["maximum_output_tokens"]:
                raise RuntimeError("pilot output-token cap exhausted")
            cost = (
                Decimal(next_input) * Decimal(self.budget["input_usd_per_million"])
                + Decimal(next_output) * Decimal(self.budget["output_usd_per_million"])
            ) / Decimal(1_000_000)
            if cost > Decimal(self.budget["maximum_cost_usd"]):
                raise RuntimeError("pilot dollar cap exhausted")
            self.state["attempts_by_request"][request_id] = attempts + 1
            self.state["transport_attempts"] += 1
            self.state["reserved_input_tokens"] = next_input
            self.state["reserved_output_tokens"] = next_output
            self._persist()
            return attempts + 1

    def call(self, request_id: str, *, system: str, user: str) -> dict[str, Any]:
        if hashlib.sha256(system.encode("utf-8")).hexdigest() != PROMPT_SHA256:
            raise PilotInputError("review prompt differs from the frozen v27 prompt")
        if PROMPT_SHA256 not in self.budget["allowed_system_sha256"]:
            raise PilotInputError("frozen budget does not authorize the v27 review prompt")
        last_error: Exception | None = None
        for attempt in range(1 + self.budget["maximum_retries_per_request"]):
            try:
                persisted_attempt = self._reserve(request_id, system, user)
                response = self.delegate.messages_create(
                    model=self.budget["model"],
                    max_tokens=self.budget["max_tokens_per_attempt"],
                    temperature=self.budget["temperature"],
                    thinking={"type": "disabled"},
                    system=system,
                    messages=[{"role": "user", "content": user}],
                    timeout=120,
                )
                usage = normalize_usage(getattr(response, "provider_usage", None))
                with self.lock:
                    self.state["observed_input_tokens"] += usage["input_tokens"] or 0
                    self.state["observed_output_tokens"] += usage["output_tokens"] or 0
                    self._persist()
                _write_json(
                    self.response_dir / f"{request_id}-{persisted_attempt}.json",
                    dict(response),
                )
                return dict(response)
            except Exception as exc:  # noqa: BLE001 - bounded transport boundary
                last_error = exc
                with self.lock:
                    self.state["errors"].append(
                        {
                            "request_id": request_id,
                            "attempt": attempt + 1,
                            "type": type(exc).__name__,
                        }
                    )
                    self._persist()
                if attempt < self.budget["maximum_retries_per_request"]:
                    time.sleep(1)
        assert last_error is not None
        raise last_error


def _packets(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    packets = []
    for row in rows:
        source = row.get("input")
        if not isinstance(source, Mapping):
            raise PilotInputError(f"row lacks source input: {row.get('example_id')}")
        packets.append(
            {
                "example_id": row["example_id"],
                "brand_id": row["brand_id"],
                "source_language": row["source_language"],
                "source": {
                    "tweet_id": row["example_id"],
                    "text": source.get("text", ""),
                    "context": list(source.get("context") or []),
                },
                "primary": row["primary"],
            }
        )
    return packets


def _review_batch(
    batch: Sequence[Mapping[str, Any]], client: BudgetedPilotClient
) -> list[dict[str, Any]]:
    packets = _packets(batch)
    user = json.dumps(
        packets, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    request_id = f"review-{batch[0]['example_id']}-{batch[-1]['example_id']}"
    response = client.call(
        request_id,
        system=_PRAGMATICS_COMPLETENESS_REVIEW_SYSTEM_PROMPT,
        user=user,
    )
    parsed, invalid, error = _partition_completeness_review_response(response, packets)
    if error is not None or invalid:
        # A malformed response is retried once by the client.  A second
        # malformed response fails closed; no semantic repair is permitted in
        # this small pilot because it would change the preregistered envelope.
        response = client.call(
            request_id,
            system=_PRAGMATICS_COMPLETENESS_REVIEW_SYSTEM_PROMPT,
            user=user,
        )
        parsed, invalid, error = _partition_completeness_review_response(
            response, packets
        )
    if error is not None or invalid or len(parsed) != len(packets):
        raise PilotInputError(
            f"review batch failed closed: {error or 'invalid or missing review rows'}"
        )
    return [
        {
            "example_id": packet["example_id"],
            "brand_id": packet["brand_id"],
            "classification": parsed[(packet["example_id"], packet["brand_id"])][
                "classification"
            ],
            "review": {
                key: parsed[(packet["example_id"], packet["brand_id"])][key]
                for key in (
                    "decision",
                    "change_reasons",
                    "evidence",
                    "post_type_verdicts",
                    "product_label_verdicts",
                )
            },
        }
        for packet in packets
    ]


def _assert_clean_worktree() -> str:
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if status:
        raise RuntimeError("commit tracked runtime changes before paid evaluation")
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def run_pilot(
    *,
    budget_path: Path,
    cohort_path: Path,
    reference_path: Path,
    output_path: Path,
    diagnostic_path: Path,
    private_dir: Path,
    delegate: Any | None = None,
) -> dict[str, Any]:
    budget = _read_json(budget_path)
    cohort = _read_json(cohort_path)
    if _sha256_file(cohort_path) != budget["cohort"]["sha256"]:
        raise PilotInputError("cohort differs from frozen budget")
    rows = cohort.get("rows")
    if (
        cohort.get("cohort_id") != PILOT_ID
        or not isinstance(rows, list)
        or len(rows) != 30
    ):
        raise PilotInputError("pilot cohort must contain exactly 30 rows")
    reference = _read_json(reference_path)
    if (
        reference.get("status") != "owner_accepted_unblinded"
        or reference.get("human_grounded") is not False
    ):
        raise PilotInputError(
            "pilot reference must remain owner accepted and unblinded"
        )
    reference_provenance_sha = reference.get("source_reference_sha256")
    if not isinstance(reference_provenance_sha, str):
        reference_provenance_sha = _sha256_file(reference_path)
    budget_reference = budget.get("reference")
    if not isinstance(budget_reference, Mapping) or not isinstance(
        budget_reference.get("sha256"), str
    ):
        raise PilotInputError("budget lacks reference provenance")
    if reference_provenance_sha != budget_reference["sha256"]:
        raise PilotInputError("reference differs from frozen budget provenance")
    reference_by_pair = _rows_by_pair(reference.get("rows"), "owner reference")
    cohort_by_pair = _rows_by_pair(rows, "pilot cohort")
    if set(cohort_by_pair) != set(reference_by_pair):
        raise PilotInputError("cohort/reference pair sets differ")
    for row in rows:
        pair = (row.get("example_id"), row.get("brand_id"))
        if pair not in reference_by_pair:
            raise PilotInputError(f"reference is missing pilot row: {pair}")
        _classification(row.get("primary"), row["brand_id"])
    revision = _assert_clean_worktree()
    client = BudgetedPilotClient(
        budget_path=budget_path, private_dir=private_dir, delegate=delegate
    )
    batches = [
        rows[index : index + PILOT_BATCH_SIZE]
        for index in range(0, len(rows), PILOT_BATCH_SIZE)
    ]
    with ThreadPoolExecutor(
        max_workers=min(PILOT_MAX_WORKERS, len(batches))
    ) as executor:
        batch_results = list(
            executor.map(lambda batch: _review_batch(batch, client), batches)
        )
    reviewed_rows = [item for batch in batch_results for item in batch]
    output = {
        "schema_version": 1,
        "provenance": {
            "kind": "candidate_output",
            "gold": False,
            "human_grounded": False,
            "owner_reference": True,
            "cohort_id": cohort["cohort_id"],
            "contract_version": CONTRACT_VERSION,
            "taxonomy_version": CANONICAL_TAXONOMY_VERSION,
            "prompt_version": _PRAGMATICS_COMPLETENESS_REVIEW_PROMPT_VERSION,
            "model": client.budget["model"],
            "provider": client.budget["provider"],
            "provider_role": "classifier_completeness_review",
            "source_revision": revision,
            "generated_at": datetime.now(UTC).isoformat(),
            "budget_sha256": _sha256_file(budget_path),
            "reference_sha256": _sha256_file(reference_path),
            "production_call_path": "v27_completeness_review_only",
        },
        "rows": sorted(
            reviewed_rows, key=lambda row: (row["example_id"], row["brand_id"])
        ),
    }
    _write_json(output_path, output)
    diagnostic = evaluate_owner_reference(
        output,
        reference,
        budget=budget,
        budget_sha256=_sha256_file(budget_path),
    )
    _write_json(diagnostic_path, diagnostic)
    print(
        json.dumps(
            {
                "candidate": str(output_path),
                "evaluation": str(diagnostic_path),
                **diagnostic["summary"],
            },
            sort_keys=True,
        )
    )
    return diagnostic


def _binary_metrics(
    gold_sets: Sequence[set[str]],
    predicted_sets: Sequence[set[str]],
    labels: Sequence[str],
) -> dict[str, Any]:
    exact = sum(
        gold == predicted
        for gold, predicted in zip(gold_sets, predicted_sets, strict=True)
    )
    counts: dict[str, dict[str, int]] = {}
    for label in labels:
        tp = sum(
            label in gold and label in predicted
            for gold, predicted in zip(gold_sets, predicted_sets, strict=True)
        )
        fp = sum(
            label not in gold and label in predicted
            for gold, predicted in zip(gold_sets, predicted_sets, strict=True)
        )
        fn = sum(
            label in gold and label not in predicted
            for gold, predicted in zip(gold_sets, predicted_sets, strict=True)
        )
        counts[label] = {
            "support": tp + fn,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "f1": (2 * tp / (2 * tp + fp + fn)) if 2 * tp + fp + fn else None,
        }
    return {
        "exact_set_accuracy": {
            "correct": exact,
            "denominator": len(gold_sets),
            "value": exact / len(gold_sets) if gold_sets else None,
        },
        "labels": counts,
    }


def evaluate_owner_reference(
    candidate: Mapping[str, Any],
    reference: Mapping[str, Any],
    *,
    budget: Mapping[str, Any],
    budget_sha256: str | None = None,
) -> dict[str, Any]:
    if (
        reference.get("status") != "owner_accepted_unblinded"
        or reference.get("human_grounded") is not False
    ):
        raise PilotInputError("owner reference provenance is invalid")
    candidate_rows = candidate.get("rows")
    reference_rows = reference.get("rows")
    if not isinstance(candidate_rows, list) or not isinstance(reference_rows, list):
        raise PilotInputError("candidate/reference rows must be arrays")
    candidate_by_pair = _rows_by_pair(candidate_rows, "candidate")
    reference_by_pair = _rows_by_pair(reference_rows, "owner reference")
    pairs = sorted(reference_by_pair)
    if set(candidate_by_pair) != set(reference_by_pair):
        raise PilotInputError("candidate/reference pair sets differ")
    gold_classes = []
    predicted_classes = []
    languages: dict[str, list[int]] = {"en": [], "ja": [], "zh-cn": []}
    for index, pair in enumerate(pairs):
        gold = _classification(reference_by_pair[pair]["classification"], pair[1])
        predicted = _classification(candidate_by_pair[pair]["classification"], pair[1])
        gold_classes.append(gold)
        predicted_classes.append(predicted)
        language = reference_by_pair[pair].get("source_language")
        if language in languages:
            languages[language].append(index)
    post = _binary_metrics(
        [set(row["post_types"]) for row in gold_classes],
        [set(row["post_types"]) for row in predicted_classes],
        CANONICAL_POST_TYPE_KEYS,
    )
    products = _binary_metrics(
        [set(row["product_labels"]) for row in gold_classes],
        [set(row["product_labels"]) for row in predicted_classes],
        PRODUCT_LABEL_KEYS,
    )
    outcome_correct = sum(
        a["outcome"] == b["outcome"]
        for a, b in zip(gold_classes, predicted_classes, strict=True)
    )
    sentiment_correct = sum(
        a["sentiment"] == b["sentiment"]
        for a, b in zip(gold_classes, predicted_classes, strict=True)
    )
    by_language = {}
    for language, indices in languages.items():
        by_language[language] = {
            "rows": len(indices),
            "post_type_exact": sum(
                gold_classes[i]["post_types"] == predicted_classes[i]["post_types"]
                for i in indices
            )
            / len(indices)
            if indices
            else None,
            "outcome_accuracy": sum(
                gold_classes[i]["outcome"] == predicted_classes[i]["outcome"]
                for i in indices
            )
            / len(indices)
            if indices
            else None,
        }
    summary = {
        "rows": len(pairs),
        "post_type_exact": post["exact_set_accuracy"]["value"],
        "product_label_exact": products["exact_set_accuracy"]["value"],
        "outcome_accuracy": outcome_correct / len(pairs) if pairs else None,
        "sentiment_accuracy": sentiment_correct / len(pairs) if pairs else None,
        "transport_attempts": None,
    }
    thresholds = {
        "post_type_exact_min": 0.70,
        "product_label_exact_min": 0.85,
        "outcome_accuracy_min": 0.90,
    }
    checks = {
        key: {
            "actual": summary[key.removesuffix("_min")],
            "minimum": value,
            "pass": summary[key.removesuffix("_min")] is not None
            and summary[key.removesuffix("_min")] >= value,
        }
        for key, value in thresholds.items()
    }
    return {
        "schema_version": "u18-owner-accepted-review-evaluation/v1",
        "status": "ok",
        "assessment": {
            "status": "owner_override_diagnostic",
            "release_quality_claim_authorized": False,
            "human_gold": False,
            "checks": checks,
        },
        "provenance": {
            "candidate_kind": candidate.get("provenance", {}).get("kind"),
            "reference_status": reference["status"],
            "reference_human_grounded": False,
            "budget_sha256": budget_sha256,
        },
        "summary": summary,
        "metrics": {
            "post_types": post,
            "product_labels": products,
            "by_language": by_language,
        },
        "limitations": [
            "The reference was owner accepted after model judgments were visible.",
            "This is an owner-conformity diagnostic, not human-grounded accuracy or release evidence.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    build.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    build.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    build.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    build.add_argument("--cohort", type=Path, default=DEFAULT_COHORT)
    build.add_argument(
        "--reference-subset", type=Path, default=DEFAULT_REFERENCE_SUBSET
    )
    run = subparsers.add_parser("run")
    run.add_argument("--budget", type=Path, required=True)
    run.add_argument("--cohort", type=Path, default=DEFAULT_COHORT)
    run.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE_SUBSET)
    run.add_argument("--output", type=Path, default=DEFAULT_CANDIDATE_OUTPUT)
    run.add_argument("--evaluation", type=Path, default=DEFAULT_DIAGNOSTIC)
    run.add_argument("--private-dir", type=Path, default=DEFAULT_RUN_DIR)
    args = parser.parse_args()
    if args.command == "build":
        build_inputs(
            source_path=args.source,
            manifest_path=args.manifest,
            candidate_path=args.candidate,
            reference_path=args.reference,
            cohort_path=args.cohort,
            reference_subset_path=args.reference_subset,
        )
    else:
        run_pilot(
            budget_path=args.budget.resolve(),
            cohort_path=args.cohort.resolve(),
            reference_path=args.reference.resolve(),
            output_path=args.output.resolve(),
            diagnostic_path=args.evaluation.resolve(),
            private_dir=args.private_dir.resolve(),
        )


if __name__ == "__main__":
    main()
