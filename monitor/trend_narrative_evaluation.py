"""Finite, synthetic evaluation and read-only materiality calibration.

This module deliberately has no publication, queue, or harvest dependency.  A
caller must opt into provider transport and supply finite budgets first.
"""

from __future__ import annotations

import json
import math
import time
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from django.db import connection, transaction

from monitor.trend_narrative_candidates import (
    DEFAULT_EVIDENCE_SELECTION_POLICY,
    canonical_snapshot_json,
)
from monitor.trend_narrative_facts import aggregate_trend_family_facts
from monitor.trend_narrative_generation import (
    HeadlineGenerationError,
    build_trend_narrative_request,
    generate_trend_narrative,
)
from x_monitor.config import HeadlineNarrativeConfig

DIMENSIONS = (
    "quantity",
    "rate",
    "mix",
    "content",
    "evidence_strength",
    "shape",
    "data_quality",
    "candidate_competition",
)
EVIDENCE_BUDGETS = (4, 12, 24, 48)
DENSITY_EXCERPT_CHARACTERS = (250, 500, 750, 1_000)
MAX_OUTPUT_TOKENS = 1_600
REQUIRED_MODEL = "deepseek-v4-pro"
RUBRIC_FIELDS = (
    "leader_selection",
    "supported_why",
    "materiality",
    "quantitative_accuracy",
    "mix_driver",
    "sentiment_use",
    "evidentiary_confidence",
    "bilingual_parity",
    "unsupported_claims",
)
RUBRIC_VERDICTS = frozenset({"pass", "fail", "not_applicable"})
METADATA_FAMILIES = (
    "post_type",
    "discourse",
    "sentiment",
    "china_nationalism",
    "us_nationalism",
)


class EvaluationConfigurationError(ValueError):
    """The run is unsafe or cannot be reproduced."""


@dataclass(frozen=True, slots=True)
class EvaluationManifest:
    run_id: str
    model: str
    max_calls: int
    input_token_budget: int
    dollar_budget: Decimal
    input_dollars_per_million_tokens: Decimal
    output_dollars_per_million_tokens: Decimal
    pricing_checked_at: str
    context_window_tokens: int
    concurrency: int = 1
    max_output_tokens: int = MAX_OUTPUT_TOKENS
    max_packet_bytes: int = DEFAULT_EVIDENCE_SELECTION_POLICY.provider_packet_bytes

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> EvaluationManifest:
        required = (
            "run_id",
            "model",
            "max_calls",
            "input_token_budget",
            "dollar_budget",
            "input_dollars_per_million_tokens",
            "output_dollars_per_million_tokens",
            "pricing_checked_at",
            "context_window_tokens",
        )
        missing = [key for key in required if value.get(key) in (None, "")]
        if missing:
            raise EvaluationConfigurationError(
                "evaluation_manifest_missing:" + ",".join(missing)
            )
        try:
            manifest = cls(
                run_id=str(value["run_id"]),
                model=str(value["model"]),
                max_calls=int(value["max_calls"]),
                input_token_budget=int(value["input_token_budget"]),
                dollar_budget=Decimal(str(value["dollar_budget"])),
                input_dollars_per_million_tokens=Decimal(
                    str(value["input_dollars_per_million_tokens"])
                ),
                output_dollars_per_million_tokens=Decimal(
                    str(value["output_dollars_per_million_tokens"])
                ),
                pricing_checked_at=str(value["pricing_checked_at"]),
                context_window_tokens=int(value["context_window_tokens"]),
                concurrency=int(value.get("concurrency", 1)),
                max_output_tokens=int(
                    value.get("max_output_tokens", MAX_OUTPUT_TOKENS)
                ),
                max_packet_bytes=int(
                    value.get(
                        "max_packet_bytes",
                        DEFAULT_EVIDENCE_SELECTION_POLICY.provider_packet_bytes,
                    )
                ),
            )
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise EvaluationConfigurationError("evaluation_manifest_invalid") from exc
        manifest.validate()
        return manifest

    @classmethod
    def from_path(cls, path: Path) -> EvaluationManifest:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EvaluationConfigurationError(
                "evaluation_manifest_unreadable"
            ) from exc
        if not isinstance(value, dict):
            raise EvaluationConfigurationError("evaluation_manifest_invalid")
        return cls.from_mapping(value)

    def validate(self) -> None:
        if self.model != REQUIRED_MODEL:
            raise EvaluationConfigurationError("evaluation_model_must_be_explicit")
        if self.concurrency != 1:
            raise EvaluationConfigurationError("evaluation_concurrency_must_be_one")
        if self.max_output_tokens != MAX_OUTPUT_TOKENS:
            raise EvaluationConfigurationError("evaluation_output_cap_must_be_fixed")
        decimal_budgets = (
            self.dollar_budget,
            self.input_dollars_per_million_tokens,
            self.output_dollars_per_million_tokens,
        )
        if (
            self.max_calls <= 0
            or self.input_token_budget <= 0
            or any(not value.is_finite() or value <= 0 for value in decimal_budgets)
            or self.context_window_tokens <= self.max_output_tokens
            or self.max_packet_bytes <= 0
        ):
            raise EvaluationConfigurationError("evaluation_budgets_must_be_finite")
        try:
            pricing_checked_at = datetime.fromisoformat(self.pricing_checked_at)
        except ValueError as exc:
            raise EvaluationConfigurationError(
                "evaluation_pricing_timestamp_invalid"
            ) from exc
        if pricing_checked_at.tzinfo is None:
            raise EvaluationConfigurationError("evaluation_pricing_timestamp_invalid")

    def as_json(self) -> dict[str, Any]:
        value = asdict(self)
        for key in (
            "dollar_budget",
            "input_dollars_per_million_tokens",
            "output_dollars_per_million_tokens",
        ):
            value[key] = format(value[key], "f")
        return value


@dataclass(frozen=True, slots=True)
class EvaluationCall:
    call_id: str
    scenario_id: str
    sweep: str
    evidence_budget: int
    excerpt_characters: int
    dimensions: dict[str, str]


def load_evaluation_scenarios(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaluationConfigurationError("evaluation_scenarios_unreadable") from exc
    scenarios = payload.get("scenarios") if isinstance(payload, dict) else None
    if not isinstance(scenarios, list) or not scenarios:
        raise EvaluationConfigurationError("evaluation_scenarios_invalid")
    ids: set[str] = set()
    normalized = []
    for raw in scenarios:
        if not isinstance(raw, dict):
            raise EvaluationConfigurationError("evaluation_scenarios_invalid")
        scenario_id = str(raw.get("scenario_id") or "")
        dimensions = raw.get("dimensions")
        if (
            not scenario_id
            or scenario_id in ids
            or not isinstance(dimensions, dict)
            or set(dimensions) != set(DIMENSIONS)
            or any(str(dimensions[key]) not in {"low", "high"} for key in DIMENSIONS)
        ):
            raise EvaluationConfigurationError("evaluation_scenarios_invalid")
        ids.add(scenario_id)
        normalized.append(
            {
                "scenario_id": scenario_id,
                "sentinel": bool(raw.get("sentinel")),
                "dimensions": {key: str(dimensions[key]) for key in DIMENSIONS},
            }
        )
    missing = missing_pairwise_combinations(normalized)
    if missing:
        raise EvaluationConfigurationError("evaluation_pairwise_coverage_incomplete")
    return normalized


def missing_pairwise_combinations(
    scenarios: Sequence[Mapping[str, Any]],
) -> list[tuple[str, str, str, str]]:
    missing = []
    for left_index, left in enumerate(DIMENSIONS):
        for right in DIMENSIONS[left_index + 1 :]:
            observed = {
                (
                    str(scenario["dimensions"][left]),
                    str(scenario["dimensions"][right]),
                )
                for scenario in scenarios
            }
            for left_value in ("low", "high"):
                for right_value in ("low", "high"):
                    if (left_value, right_value) not in observed:
                        missing.append((left, left_value, right, right_value))
    return missing


def build_evaluation_calls(
    scenarios: Sequence[Mapping[str, Any]],
) -> list[EvaluationCall]:
    calls = []
    for index, scenario in enumerate(scenarios):
        budget = EVIDENCE_BUDGETS[index % len(EVIDENCE_BUDGETS)]
        calls.append(
            _call(scenario, sweep="pairwise", budget=budget, excerpt_chars=1_000)
        )
    sentinels = [scenario for scenario in scenarios if scenario.get("sentinel")]
    if not sentinels:
        raise EvaluationConfigurationError("evaluation_sentinel_missing")
    for scenario in sentinels:
        for budget in EVIDENCE_BUDGETS:
            calls.append(
                _call(
                    scenario,
                    sweep="evidence_count",
                    budget=budget,
                    excerpt_chars=1_000,
                )
            )
    density_sentinel = sentinels[0]
    for excerpt_chars in DENSITY_EXCERPT_CHARACTERS:
        calls.append(
            _call(
                density_sentinel,
                sweep="excerpt_density",
                budget=24,
                excerpt_chars=excerpt_chars,
            )
        )
    return calls


def _call(
    scenario: Mapping[str, Any],
    *,
    sweep: str,
    budget: int,
    excerpt_chars: int,
) -> EvaluationCall:
    return EvaluationCall(
        call_id=(f"{sweep}:{scenario['scenario_id']}:e{budget}:c{excerpt_chars}"),
        scenario_id=str(scenario["scenario_id"]),
        sweep=sweep,
        evidence_budget=budget,
        excerpt_characters=excerpt_chars,
        dimensions={key: str(scenario["dimensions"][key]) for key in DIMENSIONS},
    )


def build_synthetic_snapshot(call: EvaluationCall) -> dict[str, Any]:
    """Build a deterministic closed snapshot; budget variants are supersets."""
    dimensions = call.dimensions
    selected_count = 1_500 if dimensions["quantity"] == "high" else 1_001
    prior_count = 1_000
    change = "50.000000" if selected_count == 1_500 else "0.100000"
    if dimensions["rate"] == "high":
        series = [6, 7, 8, 9, 11, 15, 28, 66]
    elif dimensions["shape"] == "high":
        series = [8, 9, 10, 36, 12, 9, 8, 8]
    else:
        series = [12, 13, 12, 13, 12, 13, 12, 13]
    series = _scaled_series(series, selected_count)
    lead = _synthetic_candidate(
        candidate_id="deepseek:full_window",
        brand_key="deepseek",
        display_name="DeepSeek",
        post_counts=series,
        selected_count=selected_count,
        prior_count=prior_count,
        change=change,
        dimensions=dimensions,
        evidence_budget=call.evidence_budget,
        excerpt_characters=call.excerpt_characters,
        lead=True,
    )
    comparison_change = (
        "45.000000" if dimensions["candidate_competition"] == "high" else "0.000000"
    )
    comparison = _synthetic_candidate(
        candidate_id="minimax:full_window",
        brand_key="minimax",
        display_name="MiniMax",
        post_counts=[12, 12, 13, 13, 12, 13, 12, 13],
        selected_count=(
            1_000 if dimensions["candidate_competition"] == "low" else 1_450
        ),
        prior_count=1_000,
        change=comparison_change,
        dimensions={**dimensions, "content": "low", "evidence_strength": "low"},
        evidence_budget=4,
        excerpt_characters=call.excerpt_characters,
        lead=False,
    )
    coverage_ratio = (
        "1.000000" if dimensions["data_quality"] == "high" else "0.800000"
    )
    return {
        "snapshot_schema_version": 1,
        "window_days": 7,
        "as_of": "2026-08-14T00:00:00Z",
        "coverage": {
            "selected": {
                "state": "sufficient",
                "ratio": coverage_ratio,
            },
            "prior": {
                "state": "sufficient",
                "ratio": coverage_ratio,
            },
        },
        "unresolved_backlog_intervals": [],
        "comparison_suppressed_reasons": [],
        "comparison_allowed": True,
        "thresholds": {"minimum_coverage": "0.750000", "episode_peak_ratio": "3.0"},
        "evidence_policy": {
            "version": "synthetic-evaluation-v1",
            "lead_ceiling": call.evidence_budget,
            "excerpt_characters": call.excerpt_characters,
        },
        "series_axis": {
            "coarse": {"bucket_count": 8, "bucket_seconds": 75_600},
            "fine": {"bucket_count": 0, "bucket_seconds": 3_600},
        },
        "selection": {"candidate_count": 2},
        "candidates": [lead, comparison],
    }


def _scaled_series(values: Sequence[int], total: int) -> list[int]:
    raw_total = sum(values)
    scaled = [math.floor(value * total / raw_total) for value in values]
    for index in range(total - sum(scaled)):
        scaled[index % len(scaled)] += 1
    return scaled


def _synthetic_candidate(
    *,
    candidate_id: str,
    brand_key: str,
    display_name: str,
    post_counts: list[int],
    selected_count: int,
    prior_count: int,
    change: str,
    dimensions: Mapping[str, str],
    evidence_budget: int,
    excerpt_characters: int,
    lead: bool,
) -> dict[str, Any]:
    mix_shift = dimensions["mix"] == "high" and lead
    coverage = (
        "1.000000" if dimensions["data_quality"] == "high" else "0.800000"
    )
    engagement_changed = (
        dimensions["quantity"] == "high" or dimensions["rate"] == "high"
    ) and lead
    labels = {
        "post_type": ("hands_on", 160, 100),
        "discourse": ("technical_analysis", 180, 120),
        "sentiment": ("positive", 300, 200),
        "china_nationalism": ("neutral", 40, 40),
        "us_nationalism": ("neutral", 40, 40),
    }
    family_facts: dict[str, Any] = {
        "volume": {
            "selected_count": selected_count,
            "selected_authors": max(10, selected_count // 3),
            "prior_count": prior_count,
            "prior_authors": max(10, prior_count // 3),
            "change_pct": change,
            "comparison_state": "available",
        },
        "engagement": {
            "selected": {
                "eligible_count": selected_count,
                "intensity": "5.000000" if engagement_changed else "4.000000",
            },
            "prior": {"eligible_count": prior_count, "intensity": "4.000000"},
            "intensity_change_pct": (
                "25.000000" if engagement_changed else "0.000000"
            ),
        },
    }
    for family, (key, shifted_selected, prior) in labels.items():
        selected = (
            shifted_selected
            if mix_shift and family in {"post_type", "discourse", "sentiment"}
            else round(prior * selected_count / prior_count)
        )
        brand_change_pp = (
            Decimal(selected) / Decimal(selected_count)
            - Decimal(prior) / Decimal(prior_count)
        ) * 100
        family_facts[family] = {
            "selected_coverage_ratio": coverage,
            "prior_coverage_ratio": coverage,
            "labels": [
                {
                    "key": key,
                    "selected_count": selected,
                    "prior_count": prior,
                    "selected_basis_count": selected_count,
                    "prior_basis_count": prior_count,
                    "brand_change_pp": _decimal_json(brand_change_pp),
                }
            ],
        }
    evidence = [
        _synthetic_evidence(
            index,
            recurring=dimensions["content"] == "high" and lead,
            independent=dimensions["evidence_strength"] == "high" and lead,
            excerpt_characters=excerpt_characters,
            brand=display_name,
            brand_key=brand_key,
        )
        for index in range(evidence_budget)
    ]
    sources = {item["source_cluster_id"] for item in evidence}
    authors = {item["author_group_id"] for item in evidence}
    return {
        "candidate_id": candidate_id,
        "brand_key": brand_key,
        "display_name_en": display_name,
        "display_name_zh_cn": display_name,
        "kind": "full_window",
        "start_at": "2026-08-07T00:00:00Z",
        "end_at": "2026-08-14T00:00:00Z",
        "signals": [
            {"family": "post_type" if mix_shift else "volume", "rank": 1 if lead else 2}
        ],
        "family_facts": family_facts,
        "metadata_trajectories": {},
        "episodes": [],
        "series": {
            "coarse": {
                "post_counts": post_counts,
                "author_counts": [max(1, value // 3) for value in post_counts],
                "engagement": {
                    "eligible_counts": post_counts,
                    "missing_counts": [0] * len(post_counts),
                    "coverage_ratios": [coverage] * len(post_counts),
                    "interactions": [value * 5 for value in post_counts],
                    "intensities": ["5.000000"] * len(post_counts),
                    "concentrations": ["0.200000"] * len(post_counts),
                    "post_kinds": {},
                },
            }
        },
        "evidence_allocation": {
            "role": "lead" if lead else "comparison",
            "selected_count": len(evidence),
        },
        "evidence_support": {
            "official_source_count": 0,
            "distinct_author_group_count": len(authors),
            "distinct_source_cluster_count": len(sources),
            "event_claim_may_be_supported": len(sources) >= 2,
            "evidence_only_entity_may_be_supported": False,
        },
        "evidence": evidence,
    }


def _synthetic_evidence(
    index: int,
    *,
    recurring: bool,
    independent: bool,
    excerpt_characters: int,
    brand: str,
    brand_key: str,
) -> dict[str, Any]:
    if recurring and independent:
        reason = (
            f"A user reported downloading {brand} more often and described "
            f"improved intelligence in hands-on work; independent report {index + 1}. "
        )
    elif recurring and index == 0:
        reason = (
            f"One user reported downloading {brand} more often and described "
            "improved intelligence in hands-on work. "
        )
    elif recurring:
        reason = (
            f"The same source repeated its report about downloading {brand} more "
            "often and improved intelligence in hands-on work. "
        )
    elif index == 0:
        reason = f"One post speculated that {brand} intelligence had improved. "
    else:
        reason = f"A general post mentioned {brand} without a recurring reason. "
    filler = "Synthetic evaluation detail remains untrusted evidence. " * 30
    excerpt = (reason + filler)[:excerpt_characters]
    source_number = index if independent else 0
    return {
        "evidence_id": f"{brand_key}_ev_{index + 1:02d}",
        "source_cluster_id": f"{brand_key}_source_{source_number + 1:02d}",
        "theme_cluster_id": f"{brand_key}_downloads_intelligence"
        if recurring
        else f"{brand_key}_generic_{index:02d}",
        "author_group_id": f"{brand_key}_author_{source_number + 1:02d}",
        "excerpt": excerpt,
        "roles": ["recurring_theme" if recurring else "top_engaged_original"],
        "source_flags": {
            "official": False,
            "post_kind": "source_post",
            "metrics_observed": True,
            "occurrence_source": "original_post",
        },
        "post_type_keys": ["hands_on" if recurring else "buzz_release"],
        "discourse_keys": ["technical_analysis"],
        "sentiment_keys": ["positive" if recurring else "neutral"],
    }


def estimate_request_input_tokens(request: Mapping[str, Any]) -> int:
    """Use UTF-8 bytes as a conservative token upper bound."""
    return len(_canonical_json(request).encode("utf-8"))


def estimate_cost(
    *,
    input_tokens: int,
    output_tokens: int,
    manifest: EvaluationManifest,
) -> Decimal:
    million = Decimal(1_000_000)
    return (
        Decimal(input_tokens) * manifest.input_dollars_per_million_tokens
        + Decimal(output_tokens) * manifest.output_dollars_per_million_tokens
    ) / million


def evaluation_preflight(
    manifest: EvaluationManifest,
    scenarios: Sequence[Mapping[str, Any]],
    config: HeadlineNarrativeConfig,
) -> dict[str, Any]:
    manifest.validate()
    if config.model != manifest.model:
        raise EvaluationConfigurationError("evaluation_config_model_mismatch")
    calls = build_evaluation_calls(scenarios)
    estimates = []
    for call in calls:
        snapshot = build_synthetic_snapshot(call)
        packet, request = build_trend_narrative_request(snapshot, config)
        quantitative_fact_count = sum(
            len(candidate.get("quantitative_facts", []))
            for candidate in packet.get("candidates", [])
        )
        if quantitative_fact_count < len(packet.get("candidates", [])):
            raise EvaluationConfigurationError(
                "evaluation_quantitative_facts_missing"
            )
        packet_bytes = len(canonical_snapshot_json(packet).encode("utf-8"))
        if packet_bytes > manifest.max_packet_bytes:
            raise EvaluationConfigurationError("evaluation_packet_limit_exceeded")
        estimated_input = estimate_request_input_tokens(request)
        if (
            estimated_input + manifest.max_output_tokens
            > manifest.context_window_tokens
        ):
            raise EvaluationConfigurationError("evaluation_context_limit_exceeded")
        estimates.append(
            {
                "call_id": call.call_id,
                "packet_bytes": packet_bytes,
                "quantitative_fact_count": quantitative_fact_count,
                "estimated_input_tokens": estimated_input,
                "reserved_cost_dollars": _decimal_json(
                    estimate_cost(
                        input_tokens=estimated_input,
                        output_tokens=manifest.max_output_tokens,
                        manifest=manifest,
                    )
                ),
            }
        )
    return {
        "manifest": manifest.as_json(),
        "transport_enabled": False,
        "planned_call_count": len(calls),
        "planned_calls_fit_call_cap": len(calls) <= manifest.max_calls,
        "concurrency": 1,
        "headline_quantitative_fact_required": True,
        "evidence_budgets": list(EVIDENCE_BUDGETS),
        "density_excerpt_characters": list(DENSITY_EXCERPT_CHARACTERS),
        "estimates": estimates,
        "estimated_input_tokens_total": sum(
            item["estimated_input_tokens"] for item in estimates
        ),
        "estimated_reserved_cost_dollars_total": _decimal_json(
            sum(Decimal(item["reserved_cost_dollars"]) for item in estimates)
        ),
    }


def run_synthetic_evaluation(
    manifest: EvaluationManifest,
    scenarios: Sequence[Mapping[str, Any]],
    config: HeadlineNarrativeConfig,
    *,
    api_key: str | None = None,
    client_factory: Callable[..., Any] | None = None,
    cancellation_path: Path | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Run sequentially through production request and validation contracts."""
    preflight = evaluation_preflight(manifest, scenarios, config)
    calls = build_evaluation_calls(scenarios)
    results = []
    calls_used = 0
    accounted_input = 0
    accounted_cost = Decimal(0)
    stop_reason = "completed"
    for call in calls:
        if cancellation_path is not None and cancellation_path.exists():
            stop_reason = "cancelled"
            break
        snapshot = build_synthetic_snapshot(call)
        packet, request = build_trend_narrative_request(snapshot, config)
        packet_bytes = len(canonical_snapshot_json(packet).encode("utf-8"))
        estimated_input = estimate_request_input_tokens(request)
        reserved_cost = estimate_cost(
            input_tokens=estimated_input,
            output_tokens=manifest.max_output_tokens,
            manifest=manifest,
        )
        if calls_used + 1 > manifest.max_calls:
            stop_reason = "call_budget_exhausted"
            break
        if accounted_input + estimated_input > manifest.input_token_budget:
            stop_reason = "input_token_budget_exhausted"
            break
        if accounted_cost + reserved_cost > manifest.dollar_budget:
            stop_reason = "dollar_budget_exhausted"
            break

        capture: dict[str, Any] = {"raw_output": "", "latency_ms": None}

        def observe(
            message: Any,
            latency_ms: int,
            sink: dict[str, Any] = capture,
        ) -> None:
            sink["raw_output"] = _provider_message_text(message)
            sink["latency_ms"] = latency_ms
            usage = getattr(message, "usage", None)
            sink["input_tokens"] = int(getattr(usage, "input_tokens", 0) or 0)
            sink["output_tokens"] = int(getattr(usage, "output_tokens", 0) or 0)

        started = clock()
        generated = None
        validator_valid = False
        validator_error = ""
        try:
            generated = generate_trend_narrative(
                snapshot,
                config,
                api_key=api_key,
                client_factory=client_factory,
                monotonic=clock,
                response_observer=observe,
            )
            validator_valid = True
        except HeadlineGenerationError as exc:
            validator_error = exc.code
        elapsed_ms = max(0, round((clock() - started) * 1_000))
        calls_used += 1
        actual_input = int(capture.get("input_tokens", 0) or 0)
        actual_output = int(capture.get("output_tokens", 0) or 0)
        usage_reported = actual_input > 0 or actual_output > 0
        charged_input = actual_input if usage_reported else estimated_input
        charged_output = actual_output if usage_reported else manifest.max_output_tokens
        actual_cost = estimate_cost(
            input_tokens=charged_input,
            output_tokens=charged_output,
            manifest=manifest,
        )
        accounted_input += charged_input
        accounted_cost += actual_cost
        raw_output = str(capture.get("raw_output") or "")
        parsed = _parse_bilingual(raw_output)
        if generated is not None:
            headline_claim = next(
                (
                    claim
                    for claim in generated.claims
                    if isinstance(claim, Mapping)
                    and claim.get("observation_index") == -1
                ),
                None,
            )
            fact_ids = (
                headline_claim.get("quantitative_fact_ids", [])
                if headline_claim is not None
                else []
            )
            headline_quantitative_fact_ids = (
                [str(fact_id) for fact_id in fact_ids]
                if isinstance(fact_ids, list)
                else []
            )
        else:
            headline_quantitative_fact_ids = _headline_quantitative_fact_ids(raw_output)
        results.append(
            {
                "call_id": call.call_id,
                "scenario_id": call.scenario_id,
                "sweep": call.sweep,
                "dimensions": call.dimensions,
                "evidence_budget": call.evidence_budget,
                "excerpt_characters": call.excerpt_characters,
                "model": config.model,
                "packet_bytes": packet_bytes,
                "quantitative_fact_count": sum(
                    len(candidate.get("quantitative_facts", []))
                    for candidate in packet.get("candidates", [])
                ),
                "headline_quantitative_fact_ids": headline_quantitative_fact_ids,
                "estimated_input_tokens": estimated_input,
                "reserved_cost_dollars": _decimal_json(reserved_cost),
                "provider_usage": {
                    "reported": usage_reported,
                    "input_tokens": actual_input,
                    "output_tokens": actual_output,
                },
                "accounted_cost_dollars": _decimal_json(actual_cost),
                "latency_ms": capture.get("latency_ms", elapsed_ms),
                "raw_output": raw_output,
                "bilingual_output": parsed,
                "validator": {
                    "valid": validator_valid,
                    "error_code": validator_error,
                },
                "generated_output_hash": (
                    generated.output_hash if generated is not None else ""
                ),
                "rubric": blank_editorial_rubric(),
            }
        )
    return {
        "artifact_schema_version": 1,
        "manifest": manifest.as_json(),
        "preflight": preflight,
        "transport_enabled": True,
        "execution": {
            "concurrency": 1,
            "calls_used": calls_used,
            "accounted_input_tokens": accounted_input,
            "accounted_cost_dollars": _decimal_json(accounted_cost),
            "stop_reason": stop_reason,
        },
        "results": results,
    }


def blank_editorial_rubric() -> dict[str, dict[str, str]]:
    return {
        field: {
            "verdict": "not_applicable",
            "notes": "Pending human bilingual editorial review.",
        }
        for field in RUBRIC_FIELDS
    }


def validate_editorial_rubric(value: Mapping[str, Any]) -> None:
    if set(value) != set(RUBRIC_FIELDS):
        raise EvaluationConfigurationError("evaluation_rubric_fields_invalid")
    for item in value.values():
        if (
            not isinstance(item, Mapping)
            or item.get("verdict") not in RUBRIC_VERDICTS
            or not isinstance(item.get("notes"), str)
        ):
            raise EvaluationConfigurationError("evaluation_rubric_value_invalid")


def _provider_message_text(message: Any) -> str:
    return "".join(
        str(block.text)
        for block in getattr(message, "content", [])
        if getattr(block, "text", None) is not None
    ).strip()


def _parse_bilingual(raw: str) -> dict[str, str]:
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {"body_en": "", "body_zh_cn": ""}
    if not isinstance(parsed, dict):
        return {"body_en": "", "body_zh_cn": ""}
    return {
        "body_en": str(parsed.get("body_en") or ""),
        "body_zh_cn": str(parsed.get("body_zh_cn") or ""),
    }


def _headline_quantitative_fact_ids(raw: str) -> list[str]:
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(parsed, Mapping):
        return []
    claims = parsed.get("claims")
    if not isinstance(claims, list):
        return []
    for claim in claims:
        if isinstance(claim, Mapping) and claim.get("observation_index") == -1:
            fact_ids = claim.get("quantitative_fact_ids")
            if isinstance(fact_ids, list):
                return [str(fact_id) for fact_id in fact_ids]
    return []


def materiality_samples_from_facts(
    facts: Mapping[str, Any],
    *,
    anchor: str,
) -> list[dict[str, Any]]:
    if not facts.get("comparison_allowed"):
        return []
    samples = []
    window_days = int(facts["window_days"])
    for candidate in facts.get("candidates", []):
        family_facts = candidate.get("family_facts", {})
        _append_sample(
            samples,
            window_days=window_days,
            family="volume",
            anchor=anchor,
            value=family_facts.get("volume", {}).get("change_pct"),
        )
        _append_sample(
            samples,
            window_days=window_days,
            family="engagement",
            anchor=anchor,
            value=family_facts.get("engagement", {}).get("intensity_change_pct"),
        )
        for family in METADATA_FAMILIES:
            family_fact = family_facts.get(family, {})
            for label in family_fact.get("labels", []):
                _append_sample(
                    samples,
                    window_days=window_days,
                    family=family,
                    anchor=anchor,
                    value=label.get("brand_change_pp"),
                )
    return samples


def _append_sample(
    samples: list[dict[str, Any]],
    *,
    window_days: int,
    family: str,
    anchor: str,
    value: Any,
) -> None:
    try:
        decimal = abs(Decimal(str(value)))
    except (InvalidOperation, TypeError):
        return
    if decimal.is_finite():
        samples.append(
            {
                "window_days": window_days,
                "family": family,
                "anchor": anchor,
                "absolute_change": format(decimal, "f"),
            }
        )


def propose_materiality_bands(
    samples: Sequence[Mapping[str, Any]],
    *,
    expected_anchors: Mapping[int, int],
    minimum_samples: int,
    epsilon: Decimal,
) -> dict[str, Any]:
    grouped: dict[tuple[int, str], list[Mapping[str, Any]]] = defaultdict(list)
    for sample in samples:
        grouped[(int(sample["window_days"]), str(sample["family"]))].append(sample)
    groups = []
    windows = sorted(expected_anchors)
    families = ("volume", "engagement", *METADATA_FAMILIES)
    for window_days in windows:
        for family in families:
            rows = grouped.get((window_days, family), [])
            values = sorted(Decimal(str(row["absolute_change"])) for row in rows)
            usable_anchors = len({str(row["anchor"]) for row in rows})
            expected = expected_anchors[window_days]
            coverage = (
                Decimal(usable_anchors) / Decimal(expected) if expected else Decimal(0)
            )
            item: dict[str, Any] = {
                "window_days": window_days,
                "family": family,
                "sample_count": len(values),
                "usable_anchor_count": usable_anchors,
                "expected_anchor_count": expected,
                "anchor_coverage": _decimal_json(coverage),
                "epsilon": _decimal_json(epsilon),
            }
            if len(values) < minimum_samples:
                item.update(
                    status="insufficient_samples", distribution={}, proposed_bands={}
                )
            else:
                p50 = _percentile(values, Decimal("0.50"))
                p75 = _percentile(values, Decimal("0.75"))
                p90 = _percentile(values, Decimal("0.90"))
                item.update(
                    status="proposed",
                    distribution={
                        "p50": _decimal_json(p50),
                        "p75": _decimal_json(p75),
                        "p90": _decimal_json(p90),
                    },
                    proposed_bands={
                        "flat_max": _decimal_json(epsilon),
                        "small_max": _decimal_json(max(epsilon, p50)),
                        "meaningful_max": _decimal_json(max(epsilon, p75)),
                        "sharp_min": _decimal_json(max(epsilon, p90)),
                    },
                )
            groups.append(item)
    return {
        "calibration_schema_version": 1,
        "minimum_samples": minimum_samples,
        "epsilon": _decimal_json(epsilon),
        "groups": groups,
    }


def calibrate_historical_materiality(
    *,
    anchors: Sequence[datetime],
    windows: Sequence[int] = (1, 7, 30, 365),
    minimum_samples: int = 20,
    epsilon: Decimal = Decimal("0.1"),
    facts_loader: Callable[[int, datetime], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    if not anchors or len(anchors) > 64:
        raise EvaluationConfigurationError("calibration_anchor_bound_invalid")
    if any(window not in {1, 7, 30, 365} for window in windows):
        raise EvaluationConfigurationError("calibration_window_invalid")
    if minimum_samples <= 0 or epsilon < 0:
        raise EvaluationConfigurationError("calibration_policy_invalid")
    loader = facts_loader or _read_only_facts
    samples = []
    expected = {window: len(anchors) for window in windows}
    anchor_reports = []
    for window in windows:
        for anchor in anchors:
            normalized = anchor.astimezone(UTC)
            facts = loader(window, normalized)
            extracted = materiality_samples_from_facts(
                facts,
                anchor=normalized.isoformat().replace("+00:00", "Z"),
            )
            samples.extend(extracted)
            anchor_reports.append(
                {
                    "window_days": window,
                    "anchor": normalized.isoformat().replace("+00:00", "Z"),
                    "comparison_allowed": bool(facts.get("comparison_allowed")),
                    "sample_count": len(extracted),
                }
            )
    return {
        **propose_materiality_bands(
            samples,
            expected_anchors=expected,
            minimum_samples=minimum_samples,
            epsilon=epsilon,
        ),
        "anchors": anchor_reports,
        "read_only": True,
        "config_written": False,
    }


def _read_only_facts(window_days: int, as_of: datetime) -> Mapping[str, Any]:
    if connection.vendor != "postgresql":
        raise EvaluationConfigurationError("calibration_requires_postgresql")
    if connection.in_atomic_block:
        raise EvaluationConfigurationError("calibration_requires_fresh_transaction")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        return aggregate_trend_family_facts(window_days, as_of=as_of)


def calibration_anchors(
    *,
    as_of: datetime,
    count: int,
    step_days: int,
) -> list[datetime]:
    if count <= 0 or count > 64 or step_days <= 0:
        raise EvaluationConfigurationError("calibration_anchor_bound_invalid")
    normalized = as_of.astimezone(UTC)
    return [normalized - timedelta(days=index * step_days) for index in range(count)]


def write_evaluation_artifacts(
    artifact: Mapping[str, Any],
    *,
    output_dir: Path,
    stem: str,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{stem}.json"
    markdown_path = output_dir / f"{stem}.md"
    json_path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    execution = artifact.get("execution", {})
    markdown = (
        "# Why-first headline evaluation\n\n"
        f"- Run: `{artifact.get('manifest', {}).get('run_id', '')}`\n"
        f"- Model: `{artifact.get('manifest', {}).get('model', '')}`\n"
        f"- Calls used: {execution.get('calls_used', 0)}\n"
        f"- Stop reason: `{execution.get('stop_reason', 'preflight')}`\n"
        f"- Accounted input tokens: {execution.get('accounted_input_tokens', 0)}\n"
        f"- Accounted cost: ${execution.get('accounted_cost_dollars', '0')}\n\n"
        "The JSON sibling is the reproducible machine record. Editorial rubric "
        "entries remain `not_applicable` until a reviewer records a verdict.\n"
    )
    markdown_path.write_text(markdown, encoding="utf-8")
    return json_path, markdown_path


def _percentile(values: Sequence[Decimal], fraction: Decimal) -> Decimal:
    if not values:
        raise ValueError("percentile requires values")
    position = fraction * Decimal(len(values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - Decimal(lower)
    return values[lower] + (values[upper] - values[lower]) * weight


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _decimal_json(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000001")), "f")


def fake_provider_message(
    payload: Mapping[str, Any], *, input_tokens: int, output_tokens: int
) -> Any:
    """Small public test helper; never performs transport."""
    return SimpleNamespace(
        content=[SimpleNamespace(text=json.dumps(payload, ensure_ascii=False))],
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        ),
    )
