"""Frozen U18A label-owner candidate check through the selected classifier.

`prepare` is provider-free. `run-live --execute-live` is the only path that
constructs a credentialed client. It never writes application database rows.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from typing import Any

from x_monitor.attribution import BrandRow, classify_batch_pragmatics_full
from x_monitor.config import load_config
from x_monitor.deepinfra import (
    DEEPSEEK_0731_MODEL,
    DeepInfraChatCompletionsClient,
    DeepInfraPermanentError,
    DeepInfraRetryableError,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/u18a_label_owner_regressions_v1.json"
MANIFEST = ROOT / "docs/analysis/2026-09-28-023934-u18a-label-owner-repair-manifest.json"
SOURCE_PATHS = (
    Path(__file__), FIXTURE, MANIFEST, ROOT / "config.yaml",
    ROOT / "x_monitor/attribution.py", ROOT / "x_monitor/classifier_0731_prompts.py",
    ROOT / "x_monitor/deepinfra.py", ROOT / "core/classification_contract.py",
)
MODEL = DEEPSEEK_0731_MODEL
PROFILE = "deepseek_0731"
MAX_TOKENS_PER_REQUEST = 4096
# One unintended translator request earlier in this quality sweep reported
# 2,083 input and 269 output tokens. Reserve one request and $0.05 of the
# owner's aggregate 40-request/$10 allowance rather than spending it twice.
MAX_LOGICAL_REQUESTS = 39
MAX_PHYSICAL_REQUESTS = 39
MAX_INPUT_TOKENS = 247_917
MAX_OUTPUT_TOKENS = 99_731
MAX_PHYSICAL_ATTEMPTS_PER_LOGICAL = 2
MAX_COST_USD = Decimal("9.95")
# Deliberately high budget reservation, not a claim about today's provider
# price. A live operator must verify the route's rates are no higher.
RESERVATION_PRICE_USD_PER_MILLION = Decimal("20")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _encoded(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_encoded(value)).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any, *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x" if exclusive else "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")


def _source_hashes() -> dict[str, str]:
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in SOURCE_PATHS
    }


def _packet(case: dict[str, Any]) -> dict[str, Any]:
    # Source-visible evaluation packet, not the stored enrichment packet. Its
    # fingerprint must never be used for production publication.
    aliases = {
        "deepseek": ["DeepSeek"], "glm": ["GLM", "Zhipu", "Z.ai"],
        "hunyuan": ["Hunyuan", "Tencent Hunyuan"],
        "llama": ["Llama", "Meta Llama"], "qwen": ["Qwen"],
    }
    return {
        "tweet_id": case["post_id"],
        "text": case["source_text"],
        "brand_ids": list(case["brand_ids"]),
        "author_handle": case["author_handle"],
        "source_language": "en",
        "context": [],
        "tracked_brand_catalog": [
            {
                "brand_id": brand_id,
                "aliases": [brand_id, *aliases.get(brand_id, [])],
                "handles": [], "domains": [], "products": [],
                "keywords": [], "hashtags": [], "accounts": [],
            }
            for brand_id in case["brand_ids"]
        ],
    }


def _registry(cases: list[dict[str, Any]]) -> list[BrandRow]:
    display = {
        "deepseek": "DeepSeek", "glm": "Zhipu", "hunyuan": "Hunyuan",
        "llama": "Llama", "qwen": "Qwen",
    }
    return [
        BrandRow(brand_id=brand_id, display_name=display[brand_id], accent_color="#111111", is_sentinel=False)
        for brand_id in sorted({brand_id for case in cases for brand_id in case["brand_ids"]})
    ]


def _invoke(packet: dict[str, Any], registry: list[BrandRow], client: Any) -> dict[str, Any]:
    rows = classify_batch_pragmatics_full(
        [packet], registry, client, model=MODEL,
        max_tokens=MAX_TOKENS_PER_REQUEST,
        max_workers=1,
        thinking={"type": "disabled"},
    )
    if len(rows) != 1:
        raise ValueError("selected classifier returned unexpected row count")
    return rows[0]


class CaptureTransport:
    """Build selected requests without calling a network transport."""

    def __init__(self) -> None:
        self.delegate = DeepInfraChatCompletionsClient(
            api_key="offline-capture-only", model=MODEL, request_profile=PROFILE,
            transport=lambda _body, _timeout: (_ for _ in ()).throw(
                AssertionError("capture must not reach transport")
            ),
        )
        self.requests: list[dict[str, Any]] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self.delegate, name)

    def messages_create(self, **kwargs: Any) -> Any:
        self.requests.append(self.delegate.build_request(**kwargs))
        raise DeepInfraPermanentError("offline_request_capture")


def _reserve_cost(input_tokens: int, output_tokens: int) -> Decimal:
    return (
        Decimal(input_tokens + output_tokens)
        * RESERVATION_PRICE_USD_PER_MILLION / Decimal(1_000_000)
    )


def _request_input_bound(request: dict[str, Any]) -> int:
    # A byte-level upper bound plus protocol overhead. Token usage above this
    # fails closed after the response and is not treated as a known cost.
    return len(_encoded(request)) + 2048


def prepare(directory: Path) -> dict[str, Any]:
    fixture = _read_json(FIXTURE)
    manifest = _read_json(MANIFEST)
    cases = fixture["cases"]
    repair_cases = {case["post_id"]: case for case in cases if case["kind"] == "repair"}
    if set(repair_cases) != set(manifest["posts"]):
        raise ValueError("frozen repair cohort mismatch")
    for post_id, case in repair_cases.items():
        for key in ("by_brand", "untracked_brand_promotions", "promoted_subjects"):
            if case["expected"][key] != manifest["posts"][post_id][key]:
                raise ValueError(f"frozen repair target mismatch: {post_id}/{key}")
    registry = _registry(cases)
    prepared_cases = []
    for case in cases:
        capture = CaptureTransport()
        _invoke(_packet(case), registry, capture)
        if len(capture.requests) != 2:
            raise ValueError(f"{case['case_id']}: expected two selected role requests")
        request_hashes = [_digest(request) for request in capture.requests]
        if len(set(request_hashes)) != 2:
            raise ValueError(f"{case['case_id']}: duplicate role request")
        prepared_cases.append({
            "case_id": case["case_id"],
            "request_hashes": request_hashes,
            "input_bounds": [_request_input_bound(request) for request in capture.requests],
            "max_output_tokens": [request["max_tokens"] for request in capture.requests],
        })
    reserved_input = sum(sum(case["input_bounds"]) for case in prepared_cases)
    reserved_output = sum(sum(case["max_output_tokens"]) for case in prepared_cases)
    reserved_cost = _reserve_cost(reserved_input, reserved_output)
    if (
        len(prepared_cases) * 2 > MAX_LOGICAL_REQUESTS
        or reserved_input > MAX_INPUT_TOKENS
        or reserved_output > MAX_OUTPUT_TOKENS
        or reserved_cost > MAX_COST_USD
    ):
        raise ValueError("frozen baseline exceeds live ceilings")
    contract = {
        "schema_version": "u18a-label-owner-candidate-eval/v1",
        "prepared_at_utc": _utc_now(),
        "fixture_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
        "manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
        "sources": _source_hashes(),
        "route": {"provider": "DeepInfra", "model": MODEL, "request_profile": PROFILE},
        "caps": {
            "cost_usd": str(MAX_COST_USD),
            "logical_requests": MAX_LOGICAL_REQUESTS,
            "physical_requests": MAX_PHYSICAL_REQUESTS,
            "input_tokens": MAX_INPUT_TOKENS,
            "output_tokens": MAX_OUTPUT_TOKENS,
            "physical_attempts_per_logical": MAX_PHYSICAL_ATTEMPTS_PER_LOGICAL,
            "reservation_price_usd_per_million": str(RESERVATION_PRICE_USD_PER_MILLION),
        },
        "baseline_reservation": {
            "logical_requests": len(prepared_cases) * 2,
            "input_tokens": reserved_input,
            "output_tokens": reserved_output,
            "cost_usd": str(reserved_cost),
        },
        "cases": prepared_cases,
        "production_database_mutation": False,
    }
    directory.mkdir(parents=True, exist_ok=False)
    _write_json(directory / "contract.json", contract, exclusive=True)
    return contract


def _validated_usage(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("missing provider usage")
    for key in ("input_tokens", "output_tokens"):
        if not isinstance(value.get(key), int) or isinstance(value[key], bool) or value[key] < 0:
            raise ValueError(f"missing or invalid provider usage: {key}")
    if (
        value.get("provider") != "DeepInfra"
        or value.get("model") != MODEL
        or not isinstance(value.get("provider_request_id"), str)
        or not value["provider_request_id"]
    ):
        raise ValueError("provider receipt identity missing or mismatched")
    try:
        cost = Decimal(str(value["cost_usd"]))
    except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("missing provider cost usage") from exc
    if not cost.is_finite() or cost < 0:
        raise ValueError("invalid provider cost usage")
    return {"input_tokens": value["input_tokens"], "output_tokens": value["output_tokens"],
            "cost_usd": str(cost), "provider_request_id": value["provider_request_id"],
            "provider": value["provider"], "model": value["model"]}


class BudgetTransport:
    """Sequential selected-client wrapper with pre-call reservations."""

    def __init__(self, delegate: DeepInfraChatCompletionsClient, receipts: Path) -> None:
        if delegate.model != MODEL or delegate.request_profile != PROFILE:
            raise ValueError("selected direct DeepInfra route required")
        self.delegate = delegate
        self.receipts = receipts
        self.logical_requests = 0
        self.physical_attempts = 0
        self.reserved_input = 0
        self.reserved_output = 0
        self.reserved_cost = Decimal(0)
        self.reported_input = 0
        self.reported_output = 0
        self.reported_cost = Decimal(0)
        self.uncertain_usage = False
        self.blocked_reason: str | None = None
        self.case_id = ""
        self.allowed: set[str] = set()
        self.seen: set[str] = set()
        self.retry_hash: str | None = None
        self.attempts_for_hash = 0
        self.attempts: list[dict[str, Any]] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self.delegate, name)

    def start_case(self, case_id: str, request_hashes: list[str]) -> None:
        if self.blocked_reason or self.uncertain_usage:
            raise ValueError("budget transport cannot start another case")
        self.case_id = case_id
        self.allowed = set(request_hashes)
        self.seen = set()
        self.retry_hash = None
        self.attempts_for_hash = 0

    def _block(self, reason: str) -> None:
        self.blocked_reason = reason

    def messages_create(self, **kwargs: Any) -> Any:
        if self.blocked_reason:
            raise DeepInfraPermanentError(self.blocked_reason)
        request = self.delegate.build_request(**kwargs)
        identity = _digest(request)
        if identity not in self.allowed:
            self._block("request_not_frozen")
            raise DeepInfraPermanentError("request_not_frozen")
        retry = identity == self.retry_hash
        if identity in self.seen and not retry:
            self._block("request_repeated_outside_retry")
            raise DeepInfraPermanentError("request_repeated_outside_retry")
        logical_increment = 0 if retry else 1
        attempts_for_hash = self.attempts_for_hash + 1 if retry else 1
        input_bound = _request_input_bound(request)
        output_bound = request["max_tokens"]
        cost_bound = _reserve_cost(input_bound, output_bound)
        if (
            self.logical_requests + logical_increment > MAX_LOGICAL_REQUESTS
            or self.physical_attempts + 1 > MAX_PHYSICAL_REQUESTS
            or self.reserved_input + input_bound > MAX_INPUT_TOKENS
            or self.reserved_output + output_bound > MAX_OUTPUT_TOKENS
            or self.reserved_cost + cost_bound > MAX_COST_USD
            or attempts_for_hash > MAX_PHYSICAL_ATTEMPTS_PER_LOGICAL
        ):
            self._block("evaluation_ceiling_reached")
            raise DeepInfraPermanentError("evaluation_ceiling_reached")
        self.logical_requests += logical_increment
        self.physical_attempts += 1
        self.reserved_input += input_bound
        self.reserved_output += output_bound
        self.reserved_cost += cost_bound
        self.seen.add(identity)
        self.retry_hash = identity
        self.attempts_for_hash = attempts_for_hash
        record = {
            "case_id": self.case_id, "request_sha256": identity,
            "logical_request": self.logical_requests,
            "physical_attempt": self.physical_attempts,
            "attempt_for_logical": attempts_for_hash,
            "started_at_utc": _utc_now(),
            "reservation": {"input_tokens": input_bound, "output_tokens": output_bound, "cost_usd": str(cost_bound)},
        }
        marker = self.receipts / f"attempt-{self.physical_attempts:03d}.started.json"
        _write_json(marker, record, exclusive=True)
        try:
            response = self.delegate.messages_create(**kwargs)
            usage = _validated_usage(getattr(response, "provider_usage", None))
            self._record_usage(usage, input_bound, output_bound, cost_bound)
            record.update(status="received", usage=usage)
            self.retry_hash = None
            return response
        except DeepInfraRetryableError as exc:
            raw = getattr(exc, "provider_usage", None)
            if raw is not None:
                try:
                    usage = _validated_usage(raw)
                    self._record_usage(usage, input_bound, output_bound, cost_bound)
                    record["usage"] = usage
                except ValueError:
                    self.uncertain_usage = True
            else:
                self.uncertain_usage = True
            record.update(status="retryable_error", error=str(exc))
            if self.uncertain_usage:
                self._block("missing_provider_usage_on_error")
                raise DeepInfraPermanentError("missing_provider_usage_on_error") from exc
            if attempts_for_hash >= MAX_PHYSICAL_ATTEMPTS_PER_LOGICAL:
                self._block("retry_ceiling_reached")
                raise DeepInfraPermanentError("retry_ceiling_reached") from exc
            raise
        except Exception as exc:
            raw = getattr(exc, "provider_usage", None)
            if raw is not None:
                try:
                    usage = _validated_usage(raw)
                    self._record_usage(usage, input_bound, output_bound, cost_bound)
                    record["usage"] = usage
                except ValueError:
                    self.uncertain_usage = True
            else:
                self.uncertain_usage = True
            if isinstance(exc, ValueError):
                self._block(str(exc))
            record.update(status="error", error_type=type(exc).__name__, error=str(exc))
            raise DeepInfraPermanentError(str(exc)) from exc
        finally:
            record["finished_at_utc"] = _utc_now()
            self.attempts.append(record)
            _write_json(self.receipts / f"attempt-{self.physical_attempts:03d}.result.json", record, exclusive=True)

    def _record_usage(self, usage: dict[str, Any], input_bound: int, output_bound: int, cost_bound: Decimal) -> None:
        cost = Decimal(usage["cost_usd"])
        self.reported_input += usage["input_tokens"]
        self.reported_output += usage["output_tokens"]
        self.reported_cost += cost
        if (
            usage["input_tokens"] > input_bound
            or usage["output_tokens"] > output_bound
            or cost > cost_bound
            or self.reported_input > MAX_INPUT_TOKENS
            or self.reported_output > MAX_OUTPUT_TOKENS
            or self.reported_cost > MAX_COST_USD
        ):
            self._block("provider_usage_exceeded_reservation")
            raise ValueError("provider usage exceeded reservation")


def _compare(expected: dict[str, Any], result: dict[str, Any], target_brand: str) -> dict[str, Any]:
    actual = {
        "by_brand": result.get("by_brand"),
        "untracked_brand_promotions": result.get("untracked_brand_promotions"),
        "promoted_subjects": result.get("promoted_subjects"),
    }
    expected_brand = expected["by_brand"][target_brand]
    actual_brand = (actual["by_brand"] or {}).get(target_brand) or {}
    expected_subjects = {subject["name"].casefold() for subject in expected["promoted_subjects"]}
    actual_subjects = {
        subject["name"].casefold()
        for subject in (actual["promoted_subjects"] or [])
        if isinstance(subject, dict) and isinstance(subject.get("name"), str)
    }
    ownership = {
        "tracked_advertising_expected": "advertising_marketing" in expected_brand["post_types"],
        "tracked_advertising_actual": "advertising_marketing" in actual_brand.get("post_types", []),
        "untracked_promotions_expected": expected["untracked_brand_promotions"],
        "untracked_promotions_actual": actual["untracked_brand_promotions"],
        "promoted_subjects_expected": sorted(expected_subjects),
        "promoted_subjects_actual": sorted(actual_subjects),
    }
    ownership_match = (
        ownership["tracked_advertising_expected"] == ownership["tracked_advertising_actual"]
        and ownership["untracked_promotions_expected"] == ownership["untracked_promotions_actual"]
        and ownership["promoted_subjects_expected"] == ownership["promoted_subjects_actual"]
    )
    return {
        "valid": bool(result.get("valid")),
        "full_result_match": bool(result.get("valid")) and actual == expected,
        "ownership_boundary_match": bool(result.get("valid")) and ownership_match,
        "ownership": ownership,
        "expected": expected,
        "actual": actual,
    }


def run_live(directory: Path, *, execute_live: bool = False) -> dict[str, Any]:
    if not execute_live:
        raise ValueError("run-live requires --execute-live")
    contract = _read_json(directory / "contract.json")
    if contract.get("sources") != _source_hashes():
        raise ValueError("frozen source changed; prepare a new contract")
    if contract.get("route") != {"provider": "DeepInfra", "model": MODEL, "request_profile": PROFILE}:
        raise ValueError("selected route drift")
    cfg = load_config(ROOT / "config.yaml")
    if (
        cfg.llm.classifier_provider != "deepinfra"
        or cfg.llm.classifier_model != MODEL
        or cfg.llm.classifier_deepinfra_request_profile != PROFILE
    ):
        raise ValueError("configured classifier route drift")
    # Credentialed client construction is deliberately after all offline
    # contract checks and the explicit live flag.
    from x_monitor.reattribute import build_classifier_client_from_env

    client = build_classifier_client_from_env(cfg)
    if not isinstance(client, DeepInfraChatCompletionsClient):
        raise ValueError("direct DeepInfra classifier client unavailable")
    fixture = _read_json(FIXTURE)
    cases = fixture["cases"]
    if len(cases) != len(contract["cases"]):
        raise ValueError("frozen case count drift")
    live_dir = directory / "live-run"
    live_dir.mkdir(exist_ok=False)
    _write_json(live_dir / "run.started.json", {"started_at_utc": _utc_now()}, exclusive=True)
    budget = BudgetTransport(client, live_dir / "attempts")
    registry = _registry(cases)
    comparisons = []
    for case, prepared in zip(cases, contract["cases"], strict=True):
        if case["case_id"] != prepared["case_id"]:
            raise ValueError("frozen case order drift")
        budget.start_case(case["case_id"], prepared["request_hashes"])
        result = _invoke(_packet(case), registry, budget)
        comparison = _compare(case["expected"], result, case["tracked_brand_id"])
        row = {"case_id": case["case_id"], "post_id": case["post_id"], "kind": case["kind"],
               "comparison": comparison, "candidate_result": result}
        comparisons.append(row)
        _write_json(live_dir / f"case-{len(comparisons):02d}.json", row, exclusive=True)
        if budget.blocked_reason or budget.uncertain_usage or not result.get("valid"):
            break
    complete = len(comparisons) == len(cases) and not budget.blocked_reason and not budget.uncertain_usage
    receipt = {
        "schema_version": "u18a-label-owner-candidate-eval-receipt/v1",
        "finished_at_utc": _utc_now(), "status": "complete" if complete else "incomplete",
        "candidate_pass": complete and all(row["comparison"]["full_result_match"] for row in comparisons),
        "ownership_pass": complete and all(row["comparison"]["ownership_boundary_match"] for row in comparisons),
        "cases_planned": len(cases), "cases_evaluated": len(comparisons),
        "logical_requests": budget.logical_requests,
        "physical_attempts": budget.physical_attempts,
        "usage_complete": not budget.uncertain_usage,
        "blocked_reason": budget.blocked_reason,
        "reserved": {"input_tokens": budget.reserved_input, "output_tokens": budget.reserved_output,
                     "cost_usd": str(budget.reserved_cost)},
        "reported": {"input_tokens": budget.reported_input, "output_tokens": budget.reported_output,
                     "cost_usd": str(budget.reported_cost)},
        "comparisons": comparisons,
        "provider_request_ids": [
            row["usage"]["provider_request_id"]
            for row in budget.attempts if isinstance(row.get("usage"), dict)
        ],
        "production_database_mutation": False,
    }
    _write_json(live_dir / "receipt.json", receipt, exclusive=True)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run-live"))
    parser.add_argument("directory", type=Path)
    parser.add_argument("--execute-live", action="store_true")
    args = parser.parse_args()
    if args.action == "prepare" and args.execute_live:
        parser.error("--execute-live is valid only with run-live")
    result = prepare(args.directory) if args.action == "prepare" else run_live(
        args.directory, execute_live=args.execute_live
    )
    summary = {
        "directory": str(args.directory), "action": args.action,
        "status": result.get("status", "prepared"),
        "logical_requests": result.get("logical_requests", result.get("baseline_reservation", {}).get("logical_requests")),
        "cost_usd": result.get("reported", {}).get("cost_usd", result.get("baseline_reservation", {}).get("cost_usd")),
    }
    if args.action == "run-live":
        summary.update({
            "candidate_pass": result["candidate_pass"],
            "ownership_pass": result["ownership_pass"],
            "cases_evaluated": result["cases_evaluated"],
            "physical_attempts": result["physical_attempts"],
            "usage_complete": result["usage_complete"],
            "blocked_reason": result["blocked_reason"],
            "provider_request_ids": result["provider_request_ids"],
            "case_results": [
                {
                    "case_id": row["case_id"],
                    "full_result_match": row["comparison"]["full_result_match"],
                    "ownership_boundary_match": row["comparison"]["ownership_boundary_match"],
                }
                for row in result["comparisons"]
            ],
        })
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
