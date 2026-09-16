"""Prepare a bounded, artifact-only U20 translation/synthesis comparison.

``prepare`` calls the real prompt builders through capture clients, but never
opens a provider connection or writes Django rows. There is intentionally no
execution/transport path yet; this script only prepares private artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from x_monitor.synthesis import build_synthesis_prompt, synthesize_post
from x_monitor.translator import translate_batch_literal

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / ".context/u18-final/cohort-source.json"
TARGET_MODEL = "deepseek/deepseek-v4-flash-0731"
TARGET_PROVIDER = "DeepInfra"
TARGET_RESPONSE_MODEL = "deepseek/deepseek-v4-flash-20260731"
TARGET_ENDPOINT = "deepinfra/fp8"
INPUT_PRICE = Decimal("0.44")
OUTPUT_PRICE = Decimal("1.32")
HARD_ARM_CAP = Decimal("0.50")
SYNTHESIS_MAX_OUTPUT_TOKENS = 4_000
LANGS = ("en", "zh-cn", "ja")


def _json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(_json(value)).hexdigest()


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_corpus() -> list[dict[str, Any]]:
    rows = json.loads(CORPUS.read_text(encoding="utf-8"))["rows"]
    selected: list[dict[str, Any]] = []
    for language in LANGS:
        candidates = sorted(
            (row for row in rows if row.get("source_language") == language),
            key=lambda row: (len(str((row.get("input") or {}).get("text") or "")), str(row.get("example_id", ""))),
        )
        candidates = [
            row for row in candidates
            if len(build_synthesis_prompt(
                post_id=str((row.get("input") or {}).get("tweet_id") or row.get("example_id") or ""),
                context=_synthesis_context({
                    "text": str((row.get("input") or {}).get("text") or ""),
                    "context": list((row.get("input") or {}).get("context") or []),
                }),
            )) <= 4000
        ]
        if len(candidates) < 15:
            raise ValueError(f"corpus has fewer than 15 {language} rows")
        third = len(candidates) // 3
        buckets = (candidates[:third], candidates[third:2 * third], candidates[2 * third:])
        chosen = []
        for bucket in buckets:
            chosen.extend(sorted(bucket, key=lambda row: hashlib.sha256(str(row.get("example_id", "")).encode()).hexdigest())[:5])
        for row in sorted(chosen, key=lambda row: str(row.get("example_id", ""))):
            source = row.get("input") or {}
            selected.append({
                "post_id": str(source.get("tweet_id") or row.get("example_id") or ""),
                "source_language": language,
                "text": str(source.get("text") or ""),
                "context": list(source.get("context") or []),
            })
    if len(selected) != 45 or len({row["post_id"] for row in selected}) != 45:
        raise ValueError("corpus selection is not exactly 45 unique posts")
    return selected


class CaptureClient:
    """Capture exact true-caller requests without transport."""
    def __init__(self, model: str):
        self.model = model
        self.requests: list[dict[str, Any]] = []

    def messages_create(self, **kwargs: Any) -> dict[str, Any]:
        request = dict(kwargs)
        request["model"] = self.model
        if self.model == TARGET_MODEL:
            request.update(temperature=1.0, top_p=1.0, seed=42)
        # Literal translation retries are deliberately represented once in the
        # frozen logical request set; run-time transport still remains bounded.
        identity = digest(request)
        if not any(digest(existing) == identity for existing in self.requests):
            self.requests.append(request)
        # Malformed response stops the true caller after this one captured
        # logical request; no retry or provider transport is involved.
        return {}


def _translation_inputs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"tweet_id": row["post_id"], "text": row["text"]} for row in rows]


def _synthesis_context(row: dict[str, Any]) -> dict[str, str]:
    context = {"post": row["text"]}
    for item in row["context"]:
        if isinstance(item, dict) and item.get("provenance") and item.get("text"):
            context[str(item["provenance"])] = str(item["text"])
    return context


def capture_requests(rows: list[dict[str, Any]], model: str) -> dict[str, list[dict[str, Any]]]:
    """Exercise both true callers and return their exact provider payloads."""
    client = CaptureClient(model)
    base_url = "https://api.deepseek.com/anthropic" if model == "deepseek-v4-flash" else "https://openrouter.ai/api/v1"
    cfg = type("Cfg", (), {"llm": type("Llm", (), {"translator_model": model, "translator_base_url": base_url})()})()
    translate_batch_literal(_translation_inputs(rows), client, cfg=cfg)
    translation = list(client.requests)
    synthesis = []
    synth_cfg = type("Synthesis", (), {
        "model": model, "max_input_tokens_per_post": 4000,
        "max_output_tokens_per_post": SYNTHESIS_MAX_OUTPUT_TOKENS, "timeout_seconds": 60,
    })()
    for row in rows:
        try:
            synthesize_post(post_id=row["post_id"], context=_synthesis_context(row), client=client, config=synth_cfg)
        except Exception:
            pass
    synthesis = client.requests[len(translation):]
    return {"translation": translation, "synthesis": synthesis}


def prepare(directory: Path) -> dict[str, Any]:
    if directory.exists():
        raise ValueError("run directory exists; refusing to overwrite frozen artifacts")
    rows = load_corpus()
    requests = {
        "incumbent": capture_requests(rows, "deepseek-v4-flash"),
        "0731": capture_requests(rows, TARGET_MODEL),
    }
    for arm, values in requests.items():
        if len(values["translation"]) != 3 or len(values["synthesis"]) != 45:
            raise ValueError(f"{arm} request count capture incomplete")
    # The prompt body is identical by role; only the pinned transport/model
    # fields may differ between arms.
    for role in ("translation", "synthesis"):
        incumbent_prompts = [request["messages"] for request in requests["incumbent"][role]]
        target_prompts = [request["messages"] for request in requests["0731"][role]]
        if incumbent_prompts != target_prompts:
            raise ValueError("model comparison changed a prompt")
    bounds = {}
    for arm, values in requests.items():
        flat = [request for role in ("translation", "synthesis") for request in values[role]]
        bounds[arm] = {
            "input_bytes": sum(len(_json(request)) + 2048 for request in flat),
            "output_tokens": sum(int(request.get("max_tokens", 0)) for request in flat),
            "roles": {
                role: {
                    "requests": len(role_requests),
                    "input_bytes": sum(len(_json(request)) + 2048 for request in role_requests),
                    "output_tokens": sum(int(request.get("max_tokens", 0)) for request in role_requests),
                }
                for role, role_requests in values.items()
            },
        }
        bounds[arm]["reserved_cost_usd"] = str((Decimal(bounds[arm]["input_bytes"]) * INPUT_PRICE + Decimal(bounds[arm]["output_tokens"]) * OUTPUT_PRICE) / Decimal(1_000_000))
        if Decimal(bounds[arm]["reserved_cost_usd"]) > HARD_ARM_CAP:
            raise ValueError(f"{arm} planning ceiling exceeds hard cap")
    contract = {
        "schema": "u20-translation-synthesis-compare/v1", "created_at": datetime.now(timezone.utc).isoformat(),
        "source_corpus": str(CORPUS.relative_to(ROOT)) if CORPUS.is_relative_to(ROOT) else str(CORPUS), "source_sha256": hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
        "implementation_sha256": {
            relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            for relative in ("scripts/u20_translation_synthesis_compare.py", "x_monitor/translator.py", "x_monitor/synthesis.py")
        },
        "selection_rule": "Per source language, discard rows whose actual build_synthesis_prompt exceeds the 4,000-character caller guard; divide remaining rows by sorted text length into three strata; choose five rows per stratum by SHA-256(example_id), then order by example_id.",
        "languages": {language: 15 for language in LANGS}, "rows": rows, "rows_sha256": digest(rows),
        "models": {"incumbent": {"model": "deepseek-v4-flash", "base_url": "https://api.deepseek.com/anthropic"}, "0731": {"model": TARGET_MODEL, "provider": TARGET_PROVIDER, "response_model": TARGET_RESPONSE_MODEL, "endpoint": TARGET_ENDPOINT, "temperature": 1.0, "top_p": 1.0, "seed": 42}},
        "requests_per_arm": {"literal_translation": 3, "synthesis": 45}, "max_transport_attempts_per_arm": 48,
        "bounds": bounds, "hard_cost_cap_usd_per_arm": str(HARD_ARM_CAP),
        "pricing_note": "Planning ceilings only; live endpoint pricing is not verified by prepare.",
        "transport_not_authorized": True, "semantic_evaluation_pending": True,
        "quality_rubric": {"entities_numbers_urls_negation_preservation": "100%", "critical_meaning_inversions": 0, "fidelity_readability_per_target_locale": ">=90%", "synthesis_completeness_and_meaning": "scored independently"},
        "evaluator_must_be_blinded_to_provider": True,
        "no_database_writes": True, "no_classifier_call": True, "semantic_pass_claim": False,
        "requests_sha256": {arm: digest(values) for arm, values in requests.items()},
    }
    write(directory / "contract.json", contract)
    write(directory / "requests.json", requests)
    return contract


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare",))
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    result = prepare(args.directory)
    print(json.dumps({"directory": str(args.directory), "rows": 45, "reserved_cost_usd": {arm: value["reserved_cost_usd"] for arm, value in result["bounds"].items()}}, indent=2))


if __name__ == "__main__":
    main()
