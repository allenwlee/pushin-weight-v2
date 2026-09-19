"""Retired historical v18 candidate-blind review-model experiment.

This script reproduces the rejected v18 three-pass topology for historical
analysis only. It is not the production classifier, the active U18 evaluator,
or a release gate. The active runtime evaluator is
``scripts/u18_runtime_classifier_candidate.py`` and uses the R79
primary/candidate-aware-review/final trace.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
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
    _read_json,
    _sha256_file,
    _write_json,
)
from x_monitor.attribution import (
    _PRAGMATICS_REVIEW_PROMPT_VERSION,
    _PRAGMATICS_REVIEW_SYSTEM_PROMPT,
    _classify_stage1_batch,
    _Stage1RepairAllowance,
)
from x_monitor.translator import AnthropicClaudeClient

ROOT = Path(__file__).resolve().parents[1]

RETIRED_EXPERIMENT_MESSAGE = (
    "u18_runtime_review_model_probe is a retired historical v18 experiment; "
    "it is not the active U18 runtime evaluator"
)


class DirectAnthropicDelegate:
    """Call Anthropic directly while keeping the shared budget envelope."""

    def __init__(self, api_key: str, *, delegate: Any | None = None) -> None:
        self._delegate = delegate or AnthropicClaudeClient(
            api_key=api_key,
            base_url="https://api.anthropic.com",
        )
        self._base_url = "https://api.anthropic.com"

    def messages_create(self, **kwargs: Any) -> dict[str, Any]:
        request = dict(kwargs)
        request.pop("thinking", None)
        return self._delegate.messages_create(**request)


def _historical_candidate_row(
    source: Mapping[str, Any], result: Mapping[str, Any]
) -> dict[str, Any]:
    """Serialize the v18 experiment's single blind-review judgment as-is."""

    brand_id = source["brand_id"]
    classification = (result.get("by_brand") or {}).get(brand_id)
    if not result.get("valid") or not isinstance(classification, Mapping):
        raise RuntimeError(
            f"historical review model returned no valid row for {source['example_id']}"
        )
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


def _run_review_batches(
    tweets: list[dict[str, Any]],
    *,
    client: FrozenRuntimeClient,
    batch_size: int,
    max_workers: int,
) -> list[dict[str, Any]]:
    batches = [
        tweets[start : start + batch_size]
        for start in range(0, len(tweets), batch_size)
    ]
    allowance = _Stage1RepairAllowance(min(20, len(tweets)))

    def classify(batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return _classify_stage1_batch(
            batch,
            [],
            client,
            model=client.budget["model"],
            max_tokens=client.budget["max_tokens_per_attempt"],
            thinking={"type": "disabled"},
            deadline=None,
            telemetry_context={
                "stage": "u18_review_model_pilot",
                "classifier_pass": "review_model_pilot",
            },
            on_batch_error=None,
            repair_allowance=allowance,
            system_prompt=_PRAGMATICS_REVIEW_SYSTEM_PROMPT,
            prompt_version=_PRAGMATICS_REVIEW_PROMPT_VERSION,
        )

    if len(batches) == 1 or max_workers <= 1:
        return [row for batch in batches for row in classify(batch)]
    with ThreadPoolExecutor(
        max_workers=min(max_workers, 3, len(batches)),
        thread_name_prefix="classifier-review-model-pilot",
    ) as executor:
        return [
            row for batch_rows in executor.map(classify, batches) for row in batch_rows
        ]


def run(
    *,
    budget_path: Path,
    cohort_path: Path,
    output_path: Path,
    private_dir: Path,
    acknowledge_retired_v18_experiment: bool = False,
) -> None:
    if not acknowledge_retired_v18_experiment:
        raise RuntimeError(RETIRED_EXPERIMENT_MESSAGE)
    budget_document = _read_json(budget_path)
    lane = budget_document["lane"]
    cohort = _read_json(cohort_path)
    if _sha256_file(cohort_path) != budget_document["cohort"]["sha256"]:
        raise RuntimeError("cohort bytes differ from the frozen budget")
    rows = cohort.get("rows")
    if not isinstance(rows, list) or len(rows) != budget_document["cohort"]["rows"]:
        raise RuntimeError("cohort rows differ from the frozen budget")
    tracked = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if tracked:
        raise RuntimeError("commit tracked runtime changes before paid evaluation")
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    api_key_name = budget_document["credential_env"]
    api_key = os.environ.get(api_key_name)
    if not api_key:
        raise RuntimeError(f"{api_key_name} is required")
    client = FrozenRuntimeClient(
        budget_path=budget_path,
        lane=lane,
        private_dir=private_dir,
        delegate=DirectAnthropicDelegate(api_key),
    )
    tweets = [
        {
            **dict(row["input"]),
            "source_language": row["source_language"],
            "source_role": row["source_role"],
        }
        for row in rows
    ]
    results = _run_review_batches(
        tweets,
        client=client,
        batch_size=client.budget["batch_size"],
        max_workers=client.budget["max_concurrent_transport_calls"],
    )
    if len(results) != len(rows):
        raise RuntimeError("review-model pilot changed cohort cardinality")
    output = {
        "schema_version": 1,
        "provenance": {
            "kind": "candidate_output",
            "gold": False,
            "cohort_id": cohort["cohort_id"],
            "contract_version": CONTRACT_VERSION,
            "taxonomy_version": CANONICAL_TAXONOMY_VERSION,
            "prompt_version": CANONICAL_PROMPT_VERSION,
            "classifier_pass_prompt_version": _PRAGMATICS_REVIEW_PROMPT_VERSION,
            "model": client.budget["model"],
            "provider": "anthropic-direct",
            "source_revision": revision,
            "generated_at": datetime.now(UTC).isoformat(),
            "budget_sha256": _sha256_file(budget_path),
            "production_call_path": "_classify_stage1_batch",
            "batch_size": client.budget["batch_size"],
        },
        "rows": sorted(
            (
                _historical_candidate_row(source, result)
                for source, result in zip(rows, results)
            ),
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
    parser.add_argument("--acknowledge-retired-v18-experiment", action="store_true")
    args = parser.parse_args()
    run(
        budget_path=args.budget.resolve(),
        cohort_path=args.cohort.resolve(),
        output_path=args.output.resolve(),
        private_dir=args.private_dir.resolve(),
        acknowledge_retired_v18_experiment=args.acknowledge_retired_v18_experiment,
    )


if __name__ == "__main__":
    main()
