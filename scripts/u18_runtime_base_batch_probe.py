"""Measure one frozen base-prompt batch size on a development cohort.

This intentionally bypasses the composite selector.  It isolates whether
unrelated batch peers are the cause of the base pass's unstable labels while
retaining the exact production prompt, parser, fallback, and repair path.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import threading
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.classification_contract import (
    CANONICAL_PROMPT_VERSION,
    CANONICAL_TAXONOMY_VERSION,
    CONTRACT_VERSION,
)
from scripts.u18_runtime_classifier_candidate import (
    FrozenRuntimeClient,
    _candidate_row,
    _read_json,
    _sha256_file,
    _write_json,
)
from x_monitor.attribution import (
    _PRAGMATICS_BASE_PROMPT_VERSION,
    _classify_stage1_base_batch,
    _Stage1RepairAllowance,
)

ROOT = Path(__file__).resolve().parents[1]


def _run_base_batches(
    tweets: list[dict[str, Any]],
    *,
    client: FrozenRuntimeClient,
    batch_size: int,
    max_workers: int,
) -> list[dict[str, Any]]:
    """Run the production base pass at one preregistered batch size."""
    batches = [
        tweets[start : start + batch_size]
        for start in range(0, len(tweets), batch_size)
    ]
    allowance = _Stage1RepairAllowance(min(20, len(tweets)))
    errors: list[Exception] = []
    error_lock = threading.Lock()

    def on_error(_batch: list[dict[str, Any]], exc: Exception) -> None:
        with error_lock:
            errors.append(exc)

    def classify(batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return _classify_stage1_base_batch(
            batch,
            [],
            client,
            model=client.budget["model"],
            max_tokens=client.budget["max_tokens_per_attempt"],
            thinking={"type": "disabled"},
            deadline=None,
            telemetry_context={"stage": "u18_base_batch_pilot"},
            on_batch_error=on_error,
            repair_allowance=allowance,
        )

    if len(batches) == 1 or max_workers <= 1:
        results = [row for batch in batches for row in classify(batch)]
    else:
        with ThreadPoolExecutor(
            max_workers=min(max_workers, 3, len(batches)),
            thread_name_prefix="classifier-base-pilot",
        ) as executor:
            results = [
                row
                for batch_rows in executor.map(classify, batches)
                for row in batch_rows
            ]
    if errors:
        raise RuntimeError(f"base pilot used fallback after {len(errors)} batch errors")
    return results


def run(
    *,
    budget_path: Path,
    cohort_path: Path,
    output_path: Path,
    private_dir: Path,
) -> None:
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
    tweets = [
        {
            **dict(row["input"]),
            "source_language": row["source_language"],
            "source_role": row["source_role"],
        }
        for row in rows
    ]
    results = _run_base_batches(
        tweets,
        client=client,
        batch_size=client.budget["base_batch_size"],
        max_workers=client.budget["max_concurrent_transport_calls"],
    )
    if len(results) != len(rows):
        raise RuntimeError("base pilot changed cohort cardinality")
    output: Mapping[str, Any] = {
        "schema_version": 1,
        "provenance": {
            "kind": "candidate_output",
            "gold": False,
            "cohort_id": cohort["cohort_id"],
            "contract_version": CONTRACT_VERSION,
            "taxonomy_version": CANONICAL_TAXONOMY_VERSION,
            "prompt_version": CANONICAL_PROMPT_VERSION,
            "classifier_pass_prompt_version": _PRAGMATICS_BASE_PROMPT_VERSION,
            "model": client.budget["model"],
            "source_revision": revision,
            "generated_at": datetime.now(UTC).isoformat(),
            "budget_sha256": _sha256_file(budget_path),
            "production_call_path": "_classify_stage1_base_batch",
            "base_batch_size": client.budget["base_batch_size"],
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
    parser.add_argument("--budget", type=Path, required=True)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--private-dir", type=Path, required=True)
    args = parser.parse_args()
    run(
        budget_path=args.budget.resolve(),
        cohort_path=args.cohort.resolve(),
        output_path=args.output.resolve(),
        private_dir=args.private_dir.resolve(),
    )


if __name__ == "__main__":
    main()
