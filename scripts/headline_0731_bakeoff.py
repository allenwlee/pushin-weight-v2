"""Bounded, no-publication headline model evaluation.

This runner reuses the production packet builders, prompts, validators, and
finite evaluator. It deliberately has no lifecycle or publication imports.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")

import django

django.setup()

from monitor.trend_narrative_evaluation import (
    EvaluationManifest,
    build_synthetic_per_brand_snapshot,
    run_per_brand_evaluation,
)
from x_monitor.config import HeadlineNarrativeConfig, load_config
from x_monitor.deepinfra import DEEPSEEK_0731_MODEL

INCUMBENT_MODEL = "deepseek-v4-flash"
CANDIDATE_MODEL = DEEPSEEK_0731_MODEL
CANDIDATE_PROFILE = "headline_rank_v2/headline_editor_v2/headline_critic_v2"
CANDIDATE_INPUT_PRICE = Decimal("0.09")
CANDIDATE_OUTPUT_PRICE = Decimal("0.27")
INCUMBENT_INPUT_PRICE = Decimal("0.44")
INCUMBENT_OUTPUT_PRICE = Decimal("1.32")
CANDIDATE_TIMEOUT_SECONDS = 300


def _load_literal_env(path: Path) -> None:
    """Load only missing simple KEY=VALUE pairs without logging secret values."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value[:1] == value[-1:] and value[:1] in {"'", '"'}:
            value = value[1:-1]
        if key and value:
            os.environ.setdefault(key, value)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_frozen_live_snapshots(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not isinstance(payload.get("runs"), list):
        raise ValueError("frozen_production_shape_invalid")
    snapshots = []
    for run in payload["runs"]:
        if run.get("window_days") not in {1, 7} or not isinstance(
            run.get("snapshot"), dict
        ):
            raise ValueError("frozen_production_run_invalid")
        snapshots.append(run["snapshot"])
    if {int(row["window_days"]) for row in snapshots} != {1, 7}:
        raise ValueError("frozen_production_windows_incomplete")
    return snapshots


def _manifest(arm: str, *, concurrency: int = 1) -> EvaluationManifest:
    candidate = arm == "candidate"
    return EvaluationManifest.from_mapping(
        {
            "run_id": f"headline-0731-bakeoff-{arm}",
            "reviewer": "codex:headline-0731-bakeoff",
            # The production evaluator pins this logical prompt contract. The
            # candidate's actual provider/model identity is separately strict
            # in the adapter and retained in route_evidence.
            "model": CANDIDATE_MODEL if candidate else INCUMBENT_MODEL,
            "max_calls": 120,
            "input_token_budget": 4_000_000,
            "output_token_budget": 1_000_000,
            "dollar_budget": "2.00",
            "input_dollars_per_million_tokens": str(
                CANDIDATE_INPUT_PRICE if candidate else INCUMBENT_INPUT_PRICE
            ),
            "output_dollars_per_million_tokens": str(
                CANDIDATE_OUTPUT_PRICE if candidate else INCUMBENT_OUTPUT_PRICE
            ),
            "pricing_version": (
                "deepinfra-priority-0731-2026-09-24"
                if candidate
                else "deepseek-v4.1-flash-peak-2026-09-02"
            ),
            "pricing_checked_at": "2026-09-24T00:00:00+09:00",
            "context_window_tokens": 500_000,
            "brand_cap": 50,
            "concurrency": concurrency,
            # The all-brand rank path has no packet-byte cap; the 128 KiB
            # production bound applies to each editor packet. The untouched
            # holdout's 1-day rank packet is ~287 KiB. Bound both bakeoff arms
            # equally above that observed size without modifying its evidence.
            "max_packet_bytes": 384 * 1024,
        }
    )


def _candidate_actual_cost(receipts: list[dict[str, Any]]) -> Decimal | None:
    costs = [row.get("cost_usd") for row in receipts]
    if not costs or any(value is None for value in costs):
        return None
    return sum((Decimal(str(value)) for value in costs), Decimal(0))


def summarize(
    artifact: dict[str, Any],
    *,
    arm: str,
    frozen_input_sha256: str,
    receipts: list[dict[str, Any]],
) -> dict[str, Any]:
    calls = artifact.get("calls") or []
    outcomes = artifact.get("brand_outcomes") or []
    eligible = sum(
        1
        for snapshot in artifact.get("snapshots") or []
        for row in snapshot.get("dossiers") or []
        if row.get("outcome") == "narrative_eligible"
    )
    terminal = sum(
        row.get("outcome") in {"approve", "repair", "hold"} for row in outcomes
    )
    invalid_calls = sum(
        not bool((row.get("mechanical") or {}).get("valid")) for row in calls
    )
    missing_locale = 0
    for row in outcomes:
        narrative = row.get("narrative")
        if not isinstance(narrative, dict):
            continue
        if any(
            not str(narrative.get(field) or "").strip()
            for field in (
                "headline_en",
                "headline_zh_cn",
                "headline_ja",
                "secondary_en",
                "secondary_zh_cn",
                "secondary_ja",
            )
        ):
            missing_locale += 1
    calibration = artifact.get("critic_calibration") or {}
    execution = artifact.get("execution") or {}
    provider_cost = _candidate_actual_cost(receipts) if arm == "candidate" else None
    return {
        "arm": arm,
        "logical_prompt_model": CANDIDATE_MODEL if arm == "candidate" else INCUMBENT_MODEL,
        "actual_provider": "DeepInfra" if arm == "candidate" else "DeepSeek",
        "actual_model": CANDIDATE_MODEL if arm == "candidate" else INCUMBENT_MODEL,
        "frozen_input_sha256": frozen_input_sha256,
        "calls_used": int(execution.get("calls_used") or 0),
        "input_tokens": int(execution.get("accounted_input_tokens") or 0),
        "output_tokens": int(execution.get("accounted_output_tokens") or 0),
        "estimated_cost_usd": execution.get("accounted_cost_dollars"),
        "provider_reported_cost_usd": (
            str(provider_cost) if provider_cost is not None else None
        ),
        "total_provider_latency_ms": sum(
            int((row.get("usage") or {}).get("latency_ms") or 0) for row in calls
        ),
        "wall_ms": execution.get("wall_ms"),
        "window_timings": execution.get("window_timings") or [],
        "stop_reason": execution.get("stop_reason"),
        "eligible_brands": eligible,
        "terminal_brand_outcomes": terminal,
        "every_eligible_brand_decided": bool(
            (artifact.get("activation_assessment") or {}).get(
                "every_eligible_brand_decided"
            )
        ),
        "mechanically_valid_calls": len(calls) - invalid_calls,
        "mechanically_invalid_calls": invalid_calls,
        "missing_locale_outcomes": missing_locale,
        "unsupported_false_accepts": int(
            calibration.get("unsupported_false_accepts") or 0
        ),
        "supported_false_holds": int(calibration.get("supported_false_holds") or 0),
        "invalid_controls": int(calibration.get("invalid_controls") or 0),
        "complete_control_set": bool(calibration.get("complete_control_set")),
        "calibration_pass": bool(calibration.get("activation_pass")),
        "complete": bool((artifact.get("activation_assessment") or {}).get("complete")),
        "provider_receipt_count": len(receipts),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    _load_literal_env(Path(".env"))
    frozen = Path(args.frozen_input)
    snapshots = [build_synthetic_per_brand_snapshot(count) for count in (1, 3, 5)]
    if args.holdout_only:
        snapshots = load_frozen_live_snapshots(frozen)
    elif not args.synthetic_only:
        snapshots.extend(load_frozen_live_snapshots(frozen))
    include_controls = not args.holdout_only
    config = load_config(Path(args.config)).headline_narrative
    if args.arm == "candidate":
        candidate_values = config.model_dump()
        candidate_values.update(
            provider="deepinfra",
            base_url="https://api.deepinfra.com/v1/openai",
            model=CANDIDATE_MODEL,
            timeout_seconds=CANDIDATE_TIMEOUT_SECONDS,
            rank_max_tokens=7_000,
            editor_max_tokens=8_000,
            critic_max_tokens=8_000,
            rank_prompt_version="headline-rank-0731-v3",
            editor_prompt_version="headline-editor-0731-v3-ja",
            critic_prompt_version="headline-critic-0731-v3-ja",
            rank_request_profile="headline_rank_v2",
            editor_request_profile="headline_editor_v2",
            critic_request_profile="headline_critic_v2",
            per_brand_batch_size=2,
            per_brand_call_cap=41,
            per_brand_input_token_cap=1_600_000,
            per_brand_output_token_cap=350_000,
            per_brand_cost_cap_usd=Decimal("0.30"),
            per_brand_input_usd_per_million=CANDIDATE_INPUT_PRICE,
            per_brand_output_usd_per_million=CANDIDATE_OUTPUT_PRICE,
            per_brand_pricing_version="deepinfra-priority-0731-2026-09-24",
            per_brand_p95_latency_seconds=Decimal(120),
            per_brand_worker_concurrency=3,
        )
        config = HeadlineNarrativeConfig.model_validate(candidate_values)
    if args.preflight_only:
        from monitor.trend_narrative_evaluation import evaluation_preflight

        return evaluation_preflight(
            _manifest(args.arm, concurrency=3 if args.arm == "candidate" else 1),
            snapshots,
            config,
            include_calibration_controls=include_controls,
        )
    artifact = run_per_brand_evaluation(
        _manifest(args.arm, concurrency=3 if args.arm == "candidate" else 1),
        snapshots,
        config,
        include_calibration_controls=include_controls,
        api_key=os.environ.get(
            "DEEPINFRA_API_KEY" if args.arm == "candidate" else "DEEPSEEK_API_KEY"
        ),
    )
    receipts = [
        (call.get("usage") or {}).get("provider_usage") or {}
        for call in artifact.get("calls") or []
        if (call.get("usage") or {}).get("provider_usage")
    ]
    artifact["route_evidence"] = {
        "arm": args.arm,
        "logical_prompt_model": CANDIDATE_MODEL if args.arm == "candidate" else INCUMBENT_MODEL,
        "actual_provider": "DeepInfra" if args.arm == "candidate" else "DeepSeek",
        "actual_model": CANDIDATE_MODEL if args.arm == "candidate" else INCUMBENT_MODEL,
        "request_profile": CANDIDATE_PROFILE if args.arm == "candidate" else None,
        "reasoning": "disabled",
        "fallback": "none",
        "provider_receipts": receipts,
    }
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = output_dir / f"{args.arm}-artifact.json"
    artifact_path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    summary = summarize(
        artifact,
        arm=args.arm,
        frozen_input_sha256=_sha256(frozen),
        receipts=receipts,
    )
    summary["artifact_path"] = str(artifact_path)
    summary["artifact_sha256"] = _sha256(artifact_path)
    summary_path = output_dir / f"{args.arm}-summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", choices=("incumbent", "candidate"), required=True)
    parser.add_argument("--frozen-input", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--synthetic-only", action="store_true")
    parser.add_argument("--holdout-only", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    print(json.dumps(run(parse_args()), sort_keys=True))
