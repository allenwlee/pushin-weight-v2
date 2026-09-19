"""Frozen, bounded acceptance through the actual selected classifier caller.

Prepare captures exact production requests with a provider-free client. Run
allows each frozen request once, retains failures, and never writes the DB.
The original and owner-amended references remain separate scoring artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import threading
import time
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from scripts import u18_openrouter_two_role_pilot as pilot
from x_monitor.attribution import classify_batch_pragmatics_full, _two_role_fingerprint
from x_monitor.openrouter import OpenRouterChatCompletionsClient, OpenRouterPermanentError

ROOT = Path(__file__).resolve().parents[1]
MODEL = "deepseek/deepseek-v4-flash-0731"
INPUT_PRICE = Decimal("0.06")
OUTPUT_PRICE = Decimal("0.18")
MAX_TOKENS = 6000
HARD_CAP = Decimal("0.05")
REFERENCE = ROOT / ".context/u18/owner-reference-sol-six-additions-v1/owner-accepted-reference.json"
POLICY = ROOT / "docs/analysis/2026-09-14-213123-u18-r98-control-fallback-pilot-contract.json"
PROVEN_REPORT = ROOT / "docs/analysis/2026-09-16-061619-u18-prior-45-owner-v4-0731-comparison.json"
PROVEN_REQUESTS = ROOT / ".context/u18/prior45-v4-0731-r123-v1/requests.json"


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def client(key=""):
    return OpenRouterChatCompletionsClient(
        api_key=key, model=MODEL, provider="DeepInfra", response_provider="DeepInfra",
        response_model="deepseek/deepseek-v4-flash-20260731",
        endpoint_tag="deepinfra/fp8", quantizations=["fp8"],
        reasoning_enabled=False, data_collection="allow", zdr=False,
        max_input_price=float(INPUT_PRICE), max_output_price=float(OUTPUT_PRICE),
        request_profile="deepseek_0731",
    )


class CaptureTransport:
    def __init__(self, delegate):
        self.delegate = delegate
        self.requests = []
        self.lock = threading.Lock()

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def messages_create(self, **kwargs):
        with self.lock:
            self.requests.append(self.delegate.build_request(**kwargs))
        # A permanent response error exercises the caller without retries.
        raise OpenRouterPermanentError("provider_free_capture")


class FrozenTransport:
    """A persisted once-only transport entitlement for each frozen request."""
    def __init__(self, delegate, requests, directory):
        self.delegate = delegate
        self.allowed = {digest(body) for body in requests}
        if len(self.allowed) != len(requests):
            raise ValueError("duplicate frozen requests")
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.measurements = []
        self.lock = threading.Lock()

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def messages_create(self, **kwargs):
        body = self.delegate.build_request(**kwargs)
        identity = digest(body)
        if identity not in self.allowed:
            raise OpenRouterPermanentError("request_not_frozen")
        try:
            with (self.directory / (identity + ".started")).open("x") as handle:
                handle.write(datetime.now(timezone.utc).isoformat())
        except FileExistsError as exc:
            raise OpenRouterPermanentError("request_already_attempted") from exc
        started = time.monotonic()
        measurement = {"request_sha256": identity}
        try:
            response = self.delegate.messages_create(**kwargs)
            measurement["usage"] = getattr(response, "provider_usage", None)
            write(self.directory / (identity + ".response.json"), response)
            measurement["status"] = "received"
            return response
        except Exception as exc:
            measurement.update(status="failed", error_type=type(exc).__name__,
                               usage=getattr(exc, "provider_usage", None))
            # This evaluation has zero retries, including ambiguous timeouts.
            raise OpenRouterPermanentError("frozen_transport_failed",
                                           provider_usage=measurement["usage"]) from exc
        finally:
            measurement["elapsed_ms"] = round((time.monotonic() - started) * 1000)
            write(self.directory / (identity + ".measurement.json"), measurement)
            with self.lock:
                self.measurements.append(measurement)


def endpoint():
    url = f"https://openrouter.ai/api/v1/models/{MODEL}/endpoints"
    with urllib.request.urlopen(url, timeout=25) as response:
        data = json.load(response)["data"]
    rows = [row for row in data["endpoints"] if row.get("tag") == "deepinfra/fp8"]
    if len(rows) != 1:
        raise ValueError("pinned endpoint missing or ambiguous")
    row = rows[0]
    if (row.get("status") != 0 or row.get("provider_name") != "DeepInfra"
            or row.get("quantization") != "fp8"
            or Decimal(row["pricing"]["prompt"]) * 1_000_000 != INPUT_PRICE
            or Decimal(row["pricing"]["completion"]) * 1_000_000 != OUTPUT_PRICE):
        raise ValueError("pinned endpoint identity/health/price changed")
    if not {"temperature", "top_p", "seed", "reasoning", "max_tokens"}.issubset(row["supported_parameters"]):
        raise ValueError("pinned endpoint parameters unavailable")
    return {"url": url, "observed_at": datetime.now(timezone.utc).isoformat(), "endpoint": row}


def invoke(packets, transport):
    return classify_batch_pragmatics_full(packets, [], transport, model=MODEL,
                                         max_tokens=MAX_TOKENS, max_workers=3,
                                         thinking={"type": "disabled"})


def verify_proven_requests(requests, proven_requests, *, prompt_addition=""):
    """Retain proven bases; allow only the declared shared prompt addition."""
    expected = []
    for bodies in proven_requests.values():
        for original in bodies:
            body = json.loads(json.dumps(original))
            body["messages"][0]["content"] += prompt_addition
            body["provider"]["only"] = ["deepinfra/fp8"]
            payload = json.loads(body["messages"][1]["content"])
            for case in payload["cases"].values():
                case.pop("case_id_for_audit_only", None)
            body["messages"][1]["content"] = json.dumps(
                payload, ensure_ascii=False, separators=(",", ":")
            )
            expected.append(body)
    if sorted(map(digest, requests)) != sorted(map(digest, expected)):
        raise ValueError("restored_r123_request_drift")


def prepare(directory):
    if directory.exists():
        raise ValueError("run directory already exists; never overwrite a frozen run")
    packets, local = pilot.build_public_packets(pilot._read_json(pilot.DEFAULT_MANIFEST))
    capture = CaptureTransport(client())
    invoke(packets, capture)
    requests = sorted(capture.requests, key=digest)
    if len(requests) != 6:
        raise ValueError("expected exactly six production requests")
    from x_monitor.classifier_0731_prompts import SHARED_RELEVANCE_RULE
    verify_proven_requests(
        requests, pilot._read_json(PROVEN_REQUESTS),
        prompt_addition=SHARED_RELEVANCE_RULE,
    )
    input_bound = sum(len(encoded(body)) + 2048 for body in requests)
    reserved = (input_bound * INPUT_PRICE + 6 * MAX_TOKENS * OUTPUT_PRICE) / 1_000_000 * Decimal("1.055")
    if reserved > HARD_CAP:
        raise ValueError("worst-case reservation exceeds hard cap")
    receipt = endpoint()
    sources = [Path(__file__), ROOT / "x_monitor/attribution.py", ROOT / "x_monitor/openrouter.py",
               ROOT / "x_monitor/classifier_0731_prompts.py",
               ROOT / "x_monitor/provider_telemetry.py", ROOT / "x_monitor/reattribute.py",
               ROOT / "x_monitor/config.py", ROOT / "monitor/cycle.py",
               ROOT / "core/classification_contract.py", Path(pilot.__file__),
               pilot.DEFAULT_MANIFEST, pilot.DEFAULT_REFERENCE, REFERENCE, POLICY,
               PROVEN_REPORT, PROVEN_REQUESTS]
    contract = {
        "schema": "u18-runtime-0731-acceptance/v1", "created_at": datetime.now(timezone.utc).isoformat(),
        "scope": "45 original owner cases through actual v3 runtime; new U18A axes excluded; no DB publication",
        "request_count": 6, "retry_count": 0, "batch_sizes": [20, 20, 5],
        "input_tokens_max": input_bound, "output_tokens_max": 6 * MAX_TOKENS,
        "reserved_usd_with_fee": str(reserved), "hard_cap_usd": str(HARD_CAP),
        "reasoning_tokens_max": 0, "maximum_concurrency": 3, "complete_batch_latency_limit_ms": 180000,
        "request_timeout_seconds": 60,
        "model": MODEL, "request_profile": "deepseek_0731", "max_tokens_per_call": MAX_TOKENS,
        "reference_policy": "Score owner-approved six-additions reference; original immutable reference separately. Consumed unblinded development evidence, not population accuracy.",
        "replication_policy": "Keep proven R123 role prompts and cases/post_flags shape with exactly one shared brand-relevance addition. Omit historical audit-only case IDs; retain explicit DeepInfra FP8 endpoint pin, strict validation, and runtime concurrency. Compare original-reference matches to the prior 180/270 without claiming unchanged historical floors passed.",
        "declared_shared_prompt_addition": SHARED_RELEVANCE_RULE,
        "activation": "All applicable frozen floors, complete coverage, cost, capacity, invariant and latency gates required; this report alone never activates a lane.",
        "sources": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
        "packet_sha256": digest(packets), "requests_sha256": digest(requests), "local_sha256": digest(local),
    }
    for name, value in (("packets", packets), ("local", local), ("requests", requests),
                        ("endpoint", receipt), ("contract", contract)):
        write(directory / (name + ".json"), value)
    return contract


def run(directory):
    contract = json.loads((directory / "contract.json").read_text())
    for relative, expected in contract["sources"].items():
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
            raise ValueError("frozen source changed: " + relative)
    packets = json.loads((directory / "packets.json").read_text())
    requests = json.loads((directory / "requests.json").read_text())
    local = json.loads((directory / "local.json").read_text())
    for name, data in (("packet", packets), ("requests", requests), ("local", local)):
        if digest(data) != contract[name + "_sha256"]:
            raise ValueError("frozen " + name + " changed")
    endpoint()
    key = None
    for line in Path("/Users/fuchitalee/.env.secrets").read_text().splitlines():
        match = re.match(r"^\s*(?:export\s+)?OPENROUTER_API_KEY\s*=\s*(.*)$", line)
        if match:
            parts = shlex.split(match.group(1), comments=True)
            if len(parts) != 1:
                raise ValueError("OPENROUTER_API_KEY must be one literal value")
            key = parts[0]
    if not key:
        raise ValueError("OPENROUTER_API_KEY unavailable")
    with (directory / "run.started").open("x") as marker:
        marker.write(datetime.now(timezone.utc).isoformat())
    transport = FrozenTransport(client(key), requests, directory / "responses")
    started = time.monotonic()
    rows = invoke(packets, transport)
    elapsed_ms = round((time.monotonic() - started) * 1000)
    write(directory / "candidate.json", rows)
    merged = []
    for packet, row in zip(packets, rows, strict=True):
        if row.get("valid"):
            for brand, classification in row["by_brand"].items():
                merged.append({"row_key": _two_role_fingerprint(packet), "target_brand": brand, **classification})
    policy = pilot._read_json(POLICY)
    unsupported = policy["baseline_metrics"]["per_label_support_and_f1"]["unsupported"]
    result = {"batches": [{"merged": merged}]}
    scores = {name: pilot.score_candidate(result, pilot._read_json(path), local,
                                          policy["quality_floors"]["floors"], unsupported)
              for name, path in (("owner_amended", REFERENCE), ("original", pilot.DEFAULT_REFERENCE))}
    usages = [measurement.get("usage") or {} for measurement in transport.measurements]
    complete_cost = all(usage.get("cost_usd") is not None for usage in usages) and len(usages) == 6
    cost = sum(Decimal(str(usage.get("cost_usd") or 0)) for usage in usages)
    prior = pilot._read_json(PROVEN_REPORT)
    original_matches = scores["original"]["dimension_matches"]
    report = {"contract": contract, "elapsed_ms": elapsed_ms, "measurements": transport.measurements,
              "billed_cost_usd": str(cost), "fee_adjusted_cost_usd": str(cost * Decimal("1.055")),
              "cost_per_1000_source_posts_usd": str(cost * Decimal("1.055") * 1000 / len(packets)),
              "cost_complete": complete_cost, "scores": scores,
              "prior_configuration_comparison": {
                  "reference": str(PROVEN_REPORT.relative_to(ROOT)),
                  "prior_exact_fields": prior["counts"]["matches"],
                  "current_exact_fields": sum(original_matches.values()),
                  "total_fields": 6 * len(packets),
                  "per_axis": {
                      axis: {"prior": prior["field_counts"][axis]["matches"], "current": matches}
                      for axis, matches in original_matches.items()
                  },
              },
              "coverage_pass": scores["owner_amended"]["coverage"] == 1,
              "cost_pass": complete_cost and cost * Decimal("1.055") <= HARD_CAP,
              "reasoning_pass": all(usage.get("reasoning_tokens") == 0 for usage in usages) and len(usages) == 6,
              "latency_pass": elapsed_ms <= contract["complete_batch_latency_limit_ms"],
              "latency_gate_method": "Conservative: entire three-batch run must fit the single complete-batch limit.",
              "latency_note": "Whole-run wall time and per-call samples; three batches cannot establish production p95/capacity.",
              "activation_authorized": False}
    write(directory / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "run"))
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    result = prepare(args.directory) if args.action == "prepare" else run(args.directory)
    print(json.dumps({"directory": str(args.directory), "action": args.action,
                      "reserved_usd": result.get("reserved_usd_with_fee"),
                      "cost_usd": result.get("billed_cost_usd"),
                      "coverage_pass": result.get("coverage_pass")}, indent=2))
