"""Run and score the frozen R94A U18A audit against the selected classifier.

The candidate-blind evaluator artifact must exist before this command runs.
This command reads that immutable expectation packet, makes exactly one normal
two-role classification attempt per 20-case family, and writes a separate
candidate/comparator receipt. It never writes application data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from x_monitor.attribution import BrandRow, classify_batch_pragmatics_full
from x_monitor.deepinfra import (
    DEEPSEEK_0731_MODEL,
    DeepInfraChatCompletionsClient,
)


INPUT_USD_PER_MILLION = Decimal("0.06")
OUTPUT_USD_PER_MILLION = Decimal("0.18")
EXPECTED_FAMILIES = (
    "local_inference",
    "cost_performance",
    "model_distillation",
    "evals_benchmarks",
    "openness_license",
    "agents_tools",
    "api_developer_surface",
    "news_reporting",
    "investigate_claim",
    "geopolitical",
    "untracked_brand_promotions",
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256_bytes(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    )


@dataclass
class RecordingClient:
    client: DeepInfraChatCompletionsClient
    calls: list[dict[str, Any]] = field(default_factory=list)

    @property
    def request_profile(self) -> str | None:
        return self.client.request_profile

    @property
    def request_identity(self) -> str:
        return self.client.request_identity

    @property
    def model(self) -> str:
        return self.client.model

    @property
    def _base_url(self) -> str:
        return self.client._base_url

    def messages_create(self, **kwargs: Any) -> Any:
        started = time.monotonic()
        try:
            response = self.client.messages_create(**kwargs)
        except Exception as exc:
            self.calls.append(
                {
                    "outcome": "error",
                    "error_type": type(exc).__name__,
                    "error_code": str(exc),
                    "latency_ms": round((time.monotonic() - started) * 1000),
                    "request_sha256": _sha256_json(
                        self.client.build_request(**kwargs)
                    ),
                }
            )
            raise
        usage = dict(getattr(response, "provider_usage", None) or {})
        self.calls.append(
            {
                "outcome": "success",
                "latency_ms": round((time.monotonic() - started) * 1000),
                "request_sha256": _sha256_json(
                    self.client.build_request(**kwargs)
                ),
                "usage": usage,
            }
        )
        return response


def _cases(family: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [
        *family.get("positive_cases", []),
        *family.get("negative_or_boundary_cases", []),
    ]
    if len(rows) != 20:
        raise ValueError("every R94A family must contain exactly 20 cases")
    if len({row.get("case_id") for row in rows}) != 20:
        raise ValueError("R94A case IDs must be unique within a family")
    return rows


def _tweet(case: dict[str, Any]) -> dict[str, Any]:
    packet = case["packet"]
    context = list(packet.get("context") or [])
    context.append(
        {
            "kind": "audit_source_reference",
            "source_ref": case.get("source_ref", {}),
            "author": {
                "handle": packet.get("author_handle") or "",
                "role": packet.get("source_role") or "unknown",
            },
        }
    )
    return {
        "tweet_id": case["case_id"],
        "text": packet["text"],
        "context": context,
        "brand_ids": list(packet["brand_ids"]),
        "affiliations": list(packet.get("author_affiliations") or []),
        "source_language": packet.get("source_language") or "unknown",
        "created_at": packet.get("created_at") or "",
        "english_translation": packet.get("english_translation") or "",
        "tracked_brand_catalog": [
            {
                "brand_id": brand_id,
                "aliases": [brand_id],
                "handles": [],
                "domains": [],
                "products": [],
                "keywords": [],
                "hashtags": [],
                "accounts": [],
            }
            for brand_id in packet["brand_ids"]
        ],
    }


def _registry(cases: list[dict[str, Any]]) -> list[BrandRow]:
    brand_ids = sorted(
        {
            brand_id
            for case in cases
            for brand_id in case["packet"]["brand_ids"]
        }
    )
    return [
        BrandRow(
            brand_id=brand_id,
            display_name=brand_id.replace("_", " ").title(),
            accent_color="#111111",
            is_sentinel=False,
        )
        for brand_id in brand_ids
    ]


def _score_case(
    family_key: str, case: dict[str, Any], result: dict[str, Any]
) -> dict[str, Any]:
    brand_id = case["packet"]["brand_ids"][0]
    classification = (result.get("by_brand") or {}).get(brand_id, {})
    expected = case["expected"]
    reasons: list[str] = []
    if not result.get("valid"):
        reasons.append("candidate_result_incomplete")
    elif family_key in EXPECTED_FAMILIES[:7]:
        actual = classification.get("audience_topics", [])
        expected_values = expected["audience_topics"]
        should_include = family_key in expected_values
        if (family_key in actual) != should_include:
            reasons.append("audience_topic_boundary_mismatch")
    elif family_key == "news_reporting":
        actual = classification.get("post_types", [])
        should_include = "news_reporting" in expected["post_types"]
        if ("news_reporting" in actual) != should_include:
            reasons.append("news_reporting_boundary_mismatch")
    elif family_key == "investigate_claim":
        actual = classification.get("product_labels", [])
        should_include = "investigate_claim" in expected["product_labels"]
        if ("investigate_claim" in actual) != should_include:
            reasons.append("investigate_claim_boundary_mismatch")
    elif family_key == "geopolitical":
        for key in (
            "geopolitical_modes",
            "china_national_stance",
            "us_national_stance",
        ):
            if classification.get(key) != expected[key]:
                reasons.append(f"{key}_mismatch")
    elif family_key == "untracked_brand_promotions":
        actual_promotions = result.get("untracked_brand_promotions", [])
        expected_promotions = expected["post_promotions"]
        normalized_expected = [] if expected_promotions == ["none"] else expected_promotions
        if actual_promotions != normalized_expected:
            reasons.append("post_promotions_mismatch")
        expected_subjects = expected.get("promoted_subjects") or []
        actual_subjects = result.get("promoted_subjects") or []
        for subject in expected_subjects:
            if not any(
                actual.get("name", "").casefold() == subject["name"].casefold()
                and actual.get("evidence") == subject["evidence"]
                for actual in actual_subjects
            ):
                reasons.append("promoted_subject_mismatch")
                break
    else:
        raise ValueError(f"unknown R94A family: {family_key}")
    return {
        "case_id": case["case_id"],
        "boundary": case["expected_boundary"],
        "supported": not reasons,
        "reasons": reasons,
        "expected": expected,
        "candidate": {
            "valid": bool(result.get("valid")),
            "classification": classification,
            "untracked_brand_promotions": result.get(
                "untracked_brand_promotions", []
            ),
            "promoted_subjects": result.get("promoted_subjects", []),
        },
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# U18A R94A candidate comparison",
        "",
        f"- Candidate: `{report['candidate']['model']}` via direct DeepInfra",
        f"- Evaluator artifact: `{report['evaluator_artifact']['path']}`",
        f"- Evaluator SHA-256: `{report['evaluator_artifact']['sha256']}`",
        f"- Candidate output SHA-256: `{report['candidate']['output_sha256']}`",
        f"- Calls: {report['usage']['calls']} successful, {report['usage']['errors']} errors",
        f"- Tokens: {report['usage']['input_tokens']} input, {report['usage']['output_tokens']} output",
        f"- Calculated cost: ${report['usage']['calculated_cost_usd']:.8f}",
        f"- Wall time: {report['usage']['wall_seconds']:.3f}s",
        "",
        "| Family/concept | Positive unsupported | Negative/boundary unsupported | Decision |",
        "| --- | ---: | ---: | --- |",
    ]
    for key in EXPECTED_FAMILIES:
        row = report["families"][key]
        lines.append(
            f"| `{key}` | {row['positive_unsupported']} / 10 | "
            f"{row['negative_or_boundary_unsupported']} / 10 | `{row['decision']}` |"
        )
    lines.extend(
        [
            "",
            "The R94A floor permits at most one unsupported assignment in each set. "
            "A shadow-only decision keeps the family unavailable to user-facing filters while retaining shadow evidence.",
            "",
            "## Unsupported cases",
            "",
        ]
    )
    for key in EXPECTED_FAMILIES:
        failures = [
            case for case in report["families"][key]["cases"] if not case["supported"]
        ]
        if not failures:
            continue
        lines.append(f"### `{key}`")
        lines.append("")
        for case in failures:
            lines.append(
                f"- `{case['case_id']}` ({case['boundary']}): "
                + ", ".join(case["reasons"])
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("audit", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument("--max-cost-usd", type=Decimal, default=Decimal("0.10"))
    args = parser.parse_args()

    audit_bytes = args.audit.read_bytes()
    audit = json.loads(audit_bytes)
    if tuple(audit.get("families", {})) != EXPECTED_FAMILIES:
        raise ValueError("R94A family inventory/order mismatch")
    if audit["candidate_and_comparator"].get("candidate_output_hash") is not None:
        raise ValueError("evaluator artifact is not candidate-blind")
    # Twenty-two role calls at 4,096 output tokens reserve $0.01622016 of
    # output. Even an intentionally conservative one-million-token aggregate
    # input bound keeps this one-shot audit below the owner's $0.10 ceiling.
    reserved_cost = (
        Decimal("1000000") * INPUT_USD_PER_MILLION
        + Decimal(22 * 4096) * OUTPUT_USD_PER_MILLION
    ) / Decimal("1000000")
    if reserved_cost > args.max_cost_usd:
        raise ValueError("R94A conservative reservation exceeds cap")
    api_key = os.environ.get("DEEPINFRA_API_KEY")
    if not api_key:
        raise ValueError("DEEPINFRA_API_KEY is required")

    base = DeepInfraChatCompletionsClient(
        api_key=api_key,
        model=DEEPSEEK_0731_MODEL,
        request_profile="deepseek_0731",
    )
    client = RecordingClient(base)
    started = time.monotonic()
    family_reports: dict[str, Any] = {}
    all_candidate_rows: list[dict[str, Any]] = []
    for family_key in EXPECTED_FAMILIES:
        cases = _cases(audit["families"][family_key])
        tweets = [_tweet(case) for case in cases]
        errors: list[str] = []
        results = classify_batch_pragmatics_full(
            tweets,
            _registry(cases),
            client,
            model=DEEPSEEK_0731_MODEL,
            max_tokens=4096,
            max_workers=2,
            on_batch_error=lambda _batch, exc: errors.append(
                f"{type(exc).__name__}:{exc}"
            ),
            telemetry_context={"audit": "u18a-r94a", "family": family_key},
        )
        scored = [
            _score_case(family_key, case, result)
            for case, result in zip(cases, results, strict=True)
        ]
        positives = [row for row in scored if row["boundary"] == "positive"]
        negatives = [
            row
            for row in scored
            if row["boundary"] == "matched_negative_or_boundary"
        ]
        positive_unsupported = sum(not row["supported"] for row in positives)
        negative_unsupported = sum(not row["supported"] for row in negatives)
        family_reports[family_key] = {
            "decision": (
                "enabled"
                if positive_unsupported <= 1 and negative_unsupported <= 1
                else "shadow_only"
            ),
            "positive_unsupported": positive_unsupported,
            "negative_or_boundary_unsupported": negative_unsupported,
            "batch_errors": errors,
            "cases": scored,
        }
        all_candidate_rows.extend(
            {"family": family_key, "case_id": case["case_id"], "result": result}
            for case, result in zip(cases, results, strict=True)
        )

    usage_rows = [
        row.get("usage", {}) for row in client.calls if row["outcome"] == "success"
    ]
    input_tokens = sum(int(row.get("input_tokens") or 0) for row in usage_rows)
    output_tokens = sum(int(row.get("output_tokens") or 0) for row in usage_rows)
    calculated_cost = (
        Decimal(input_tokens) * INPUT_USD_PER_MILLION
        + Decimal(output_tokens) * OUTPUT_USD_PER_MILLION
    ) / Decimal(1_000_000)
    if calculated_cost > args.max_cost_usd:
        raise ValueError("R94A measured cost exceeded cap")
    candidate_hash = _sha256_json(all_candidate_rows)
    report = {
        "artifact_type": "u18a_r94a_candidate_comparison",
        "artifact_version": "v1",
        "created_at": datetime.now(UTC).isoformat(),
        "evaluator_artifact": {
            "path": str(args.audit),
            "sha256": _sha256_bytes(audit_bytes),
        },
        "candidate": {
            "provider": "DeepInfra",
            "endpoint": "direct",
            "model": DEEPSEEK_0731_MODEL,
            "request_profile": "deepseek_0731",
            "batch_size": 20,
            "roles_per_batch": 2,
            "output_sha256": candidate_hash,
            "rows": all_candidate_rows,
        },
        "comparator": {
            "identity": audit["candidate_and_comparator"]["comparator_identity"],
            "sha256": audit["candidate_and_comparator"]["comparator_sha256"],
            "floor": "at most one unsupported assignment in each positive and negative/boundary set",
        },
        "families": family_reports,
        "usage": {
            "calls": sum(row["outcome"] == "success" for row in client.calls),
            "errors": sum(row["outcome"] == "error" for row in client.calls),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "calculated_cost_usd": float(calculated_cost),
            "response_reported_cost_usd": float(
                sum(Decimal(str(row.get("cost_usd") or 0)) for row in usage_rows)
            ),
            "wall_seconds": round(time.monotonic() - started, 3),
            "max_cost_usd": float(args.max_cost_usd),
            "reserved_cost_usd": float(reserved_cost),
            "attempts": client.calls,
        },
        "limitations": audit["limitations"],
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    args.output_json.with_suffix(".md").write_text(_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output_json),
                "candidate_sha256": candidate_hash,
                "enabled": [
                    key
                    for key, row in family_reports.items()
                    if row["decision"] == "enabled"
                ],
                "shadow_only": [
                    key
                    for key, row in family_reports.items()
                    if row["decision"] == "shadow_only"
                ],
                "usage": report["usage"],
            },
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
