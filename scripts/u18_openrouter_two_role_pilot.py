"""Provider-boundary runner for the U18 R95--R97 two-role comparison.

This module is intentionally an evaluator, rather than a production caller.  It
builds a public-X-only packet from the owner study, runs the two disjoint role
requests for each 20/20/5 batch, and writes secret-free measurements.  Raw
requests and responses, when explicitly requested, live only below
``.context/u18/openrouter-two-role-pilot-v1``.

The default commands (``dry-run`` and ``preflight``) never construct a client.
Transport is supplied to :class:`TwoRolePilot` as a factory so tests and replay
can prove the complete call topology without credentials or network access.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import threading
import time
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from core.classification_contract import (
    CANONICAL_POST_TYPE_KEYS,
    CANONICAL_PRODUCT_LABEL_KEYS,
    NATIONALISM_KEYS,
    OUTCOMES,
    SENTIMENT_KEYS,
    parse_stage1_classifications,
)
from x_monitor.attribution import (
    _TWO_ROLE_BRAND_SYSTEM_PROMPT,
    _TWO_ROLE_CONTENT_SYSTEM_PROMPT,
    AnthropicCompatiblePermanentError,
    AnthropicCompatibleRetryableError,
    _two_role_fingerprint,
    _two_role_parse,
    _two_role_payload,
)
from x_monitor.openrouter import OpenRouterPermanentError, OpenRouterRetryableError
from x_monitor.provider_telemetry import ProviderResponse, normalize_usage

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / ".context/u18/human-ambiguity-study-v1/selection-manifest.json"
DEFAULT_REFERENCE = ROOT / ".context/u18/human-ambiguity-study-v1/owner-accepted-reference.json"
DEFAULT_PRIVATE_DIR = ROOT / ".context/u18/openrouter-two-role-pilot-v1"
DEFAULT_R98_PRIVATE_DIR = ROOT / ".context/u18/openrouter-two-role-pilot-r98-control-fallback-v1"
DEFAULT_BUDGET: Path | None = None

PILOT_ID = "u18-openrouter-two-role-pilot-v1"
BATCH_SIZE = 20
BATCH_SIZES = (20, 20, 5)
ROLE_NAMES = ("content", "brand_interpretation")
CONTENT_FIELDS = ("outcome", "post_types")
BRAND_FIELDS = (
    "product_labels",
    "sentiment",
    "china_nationalism",
    "us_nationalism",
)
MAX_CONCURRENT_TRANSPORTS = 3
DEFAULT_MAX_TRANSPORT_ATTEMPTS = 3
PILOT_MAX_TRANSPORT_ATTEMPTS = 2
MAX_LOGICAL_REQUESTS = 18

# These are the identities selected in the U18 plan.  The route controls are
# data, so preflight can inspect them without reading OPENROUTER_API_KEY.
# Candidate identities, route policies, prices, and endpoint aliases are read
# from the frozen budget artifact.  Keeping this empty prevents a convenient
# fallback to a stale model or data policy.
CANDIDATES: tuple[dict[str, Any], ...] = ()


def _pilot_id(document: Mapping[str, Any]) -> str:
    value = document.get("pilot_id")
    if isinstance(value, str) and value:
        return value
    schema = str(document.get("schema_version", ""))
    return "u18-r98-direct-control-fallback-pilot-v1" if schema.startswith("u18-r98-") else PILOT_ID

# Compact, shared-prefix prompts are part of the candidate identity.  They
# contain no study IDs, examples, owner answers, or account metadata.
CONTENT_SYSTEM_PROMPT = _TWO_ROLE_CONTENT_SYSTEM_PROMPT
BRAND_SYSTEM_PROMPT = _TWO_ROLE_BRAND_SYSTEM_PROMPT
ROLE_PROMPTS = {"content": CONTENT_SYSTEM_PROMPT, "brand_interpretation": BRAND_SYSTEM_PROMPT}


class PilotInputError(ValueError):
    """Input, policy, or semantic output violates the frozen pilot contract."""


class PilotCapExceeded(RuntimeError):
    """A request would exceed a frozen cap and is refused before transport."""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PilotInputError(f"cannot read JSON artifact: {path}") from exc
    if not isinstance(value, dict):
        raise PilotInputError(f"JSON artifact must be an object: {path}")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _public_context(value: Any) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise PilotInputError("source context must be an array")
    result = []
    for item in value:
        if not isinstance(item, Mapping) or not isinstance(item.get("text"), str):
            raise PilotInputError("source context contains a non-visible entry")
        # Kind is a useful visible-context marker, while indices/provenance and
        # all source IDs stay local.
        kind = item.get("kind", "context")
        kind = kind if isinstance(kind, str) else "context"
        if any(term in kind.casefold() for term in ("private", "owner", "comment", "database", "db-only")):
            raise PilotInputError("source context contains private or database-only material")
        result.append({"kind": kind, "text": item["text"]})
    return result


def _row_key(*, brand_id: str, source_language: str, text: str, context: Sequence[Mapping[str, str]]) -> str:
    return _sha({"brand": brand_id, "language": source_language, "text": text, "context": list(context)})[:32]


def build_public_packets(manifest: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Return ordered transport packets and local key-to-reference metadata.

    The packet intentionally has no ``case_id``, example/tweet ID, author
    handle/name, selection evidence, owner answer, or database-only fact.
    """
    rows = manifest.get("rows")
    if not isinstance(rows, list) or len(rows) != 45:
        raise PilotInputError("U18 manifest must contain exactly 45 rows")
    packets: list[dict[str, Any]] = []
    local: dict[str, dict[str, Any]] = {}
    for selected in rows:
        if not isinstance(selected, Mapping):
            raise PilotInputError("manifest row is not an object")
        source = selected.get("source_row")
        if not isinstance(source, Mapping):
            raise PilotInputError("manifest row lacks source_row")
        brand = selected.get("brand_id")
        language = selected.get("source_language")
        source_input = source.get("input")
        text = source_input.get("text") if isinstance(source_input, Mapping) else None
        if not all(isinstance(v, str) and v for v in (brand, language, text)):
            raise PilotInputError("manifest row lacks brand, language, or source text")
        context = _public_context(source_input.get("context", []))
        tweet_id = source_input.get("tweet_id")
        if not isinstance(tweet_id, str) or not tweet_id:
            raise PilotInputError("source row lacks public tweet_id")
        role = source.get("source_role")
        affiliations = ([{"brand_id": brand, "role": role, "reviewed": True}] if role in {"official", "staff"} else [])
        # This is the exact production input envelope.  The public post ID is
        # required for stable response joining; study IDs and account identity
        # fields are intentionally absent.
        source_packet = {
            # Production's stable join key is retained, but the public X ID is
            # one-way hashed so the pilot transports no study/source ID.
            "tweet_id": hashlib.sha256(tweet_id.encode("utf-8")).hexdigest(),
            "text": text,
            "context": context,
            "brand_ids": [brand],
            "affiliations": affiliations,
            "source_language": language,
        }
        key = _two_role_fingerprint(source_packet)
        if key in local:
            raise PilotInputError("duplicate public row key")
        packets.append(source_packet)
        local[key] = {
            "example_id": selected.get("example_id"),
            "brand_id": brand,
            "source_language": language,
            "source_role": source.get("source_role"),
            "source_hint": source.get("source_hint"),
            "stratum": source.get("stratum"),
            "context": [item.get("kind", "context") for item in context],
        }
    return packets, local


def batches(packets: Sequence[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    if len(packets) != 45:
        raise PilotInputError("pilot requires exactly 45 packets")
    result = [list(packets[index:index + BATCH_SIZE]) for index in range(0, len(packets), BATCH_SIZE)]
    if tuple(map(len, result)) != BATCH_SIZES:
        raise PilotInputError("pilot batches must be 20/20/5")
    return result


@dataclass
class FrozenCaps:
    maximum_logical_requests: int = MAX_LOGICAL_REQUESTS
    maximum_transport_attempts: int = 36
    maximum_input_tokens: int = 2_000_000
    maximum_output_tokens: int = 600_000
    maximum_reasoning_tokens: int = 0
    maximum_spend_usd: Decimal = Decimal("3.00")
    maximum_cost_per_1000_posts_usd: Decimal = Decimal("3.00")
    per_model: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)


def load_budget(path: Path) -> tuple[FrozenCaps, tuple[dict[str, Any], ...], int]:
    """Load all identities and caps from one immutable, machine-readable file."""
    document = _read_json(path)
    raw_caps = document.get("caps") or document.get("global_caps")
    raw_candidates = document.get("candidates")
    tokens = document.get("token_budget", {})
    if raw_caps is None and isinstance(document.get("request_schedule"), Mapping):
        tokens = document.get("token_budget", {})
        spend = document.get("spend_budget", {})
        reserved = tokens.get("per_candidate_reserved_input_tokens", {})
        max_input = sum(int(value) for value in reserved.values())
        max_output = sum(int(tokens.get("per_candidate_reserved_output_tokens", 0)) for _ in (raw_candidates or []))
        hard_caps = spend.get("per_candidate_hard_cap_usd_with_one_retry_each", {})
        total_raw = spend.get("total_trial_hard_cap_usd", "0")
        total_cap = total_raw.get("current_offers", "0") if isinstance(total_raw, Mapping) else total_raw
        n_candidates = len(raw_candidates) if isinstance(raw_candidates, list) else 0
        raw_caps = {"maximum_logical_requests": n_candidates * 6, "maximum_transport_attempts": n_candidates * 12, "maximum_input_tokens": max_input or 1, "maximum_output_tokens": max_output or 1, "maximum_reasoning_tokens": 0, "maximum_spend_usd": total_cap, "maximum_cost_per_1000_posts_usd": max((Decimal(str(value)) for value in spend.get("per_1000_source_posts_projection_usd", {}).values() if isinstance(value, Mapping) for value in value.values() if value not in {"0", "unavailable_for_free_endpoint"}), default=Decimal(0)), "maximum_transport_attempts_per_role": 2}
        raw_caps["per_model"] = {str(item.get("model_id")): {"maximum_logical_requests": 6, "maximum_transport_attempts": 12, "maximum_input_tokens": int(reserved.get(item.get("candidate_key"), max_input)), "maximum_output_tokens": int(tokens.get("per_candidate_reserved_output_tokens", 0)), "maximum_reasoning_tokens": 0, "maximum_spend_usd": str(hard_caps.get(item.get("candidate_key"), total_cap))} for item in raw_candidates if isinstance(item, Mapping) and item.get("model_id")}
    if not isinstance(raw_caps, Mapping) or not isinstance(raw_candidates, list) or not 3 <= len(raw_candidates) <= 5:
        raise PilotInputError("budget must define caps and 3..5 candidates")
    caps = FrozenCaps(
        maximum_logical_requests=int(raw_caps["maximum_logical_requests"]),
        maximum_transport_attempts=int(raw_caps.get("maximum_transport_attempts", 36)),
        maximum_input_tokens=int(raw_caps["maximum_input_tokens"]),
        maximum_output_tokens=int(raw_caps["maximum_output_tokens"]),
        maximum_reasoning_tokens=int(raw_caps.get("maximum_reasoning_tokens", 0)),
        maximum_spend_usd=Decimal(str(raw_caps["maximum_spend_usd"])),
        maximum_cost_per_1000_posts_usd=Decimal(str(raw_caps.get("maximum_cost_per_1000_posts_usd", raw_caps["maximum_spend_usd"]))),
        per_model=raw_caps.get("per_model", {}),
    )
    max_attempts = int(raw_caps.get("maximum_transport_attempts_per_role", PILOT_MAX_TRANSPORT_ATTEMPTS))
    candidates: list[dict[str, Any]] = []
    for item in raw_candidates:
        if not isinstance(item, Mapping):
            raise PilotInputError("budget candidate is not an object")
        candidate = dict(item)
        if "candidate_key" in candidate:
            candidate = {
                **candidate,
                "candidate_id": candidate["candidate_key"],
                "model": candidate.get("model_id"),
                "provider": candidate.get("provider_slug"),
                "response_provider": candidate.get("provider_response_name"),
                "response_model": candidate.get("endpoint_model_alias"),
                "endpoint_aliases": candidate.get("endpoint_aliases") or [candidate.get("provider_response_name"), candidate.get("endpoint_model_alias")],
                "input_usd_per_million": candidate.get("input_usd_per_million", "0"),
                "output_usd_per_million": candidate.get("output_usd_per_million", "0"),
                "max_input_price": candidate.get("input_usd_per_million", "0"),
                "max_output_price": candidate.get("output_usd_per_million", "0"),
                "allow_fallbacks": False,
            }
            # The frozen candidate entry carries the measured/conservative
            # *combined* input bound for each 20/20/5 batch.  Do not infer
            # tokens from UTF-8 bytes here: Qwen uses its chat tokenizer and
            # Gemma's byte fallback is deliberately already framed (+32 for
            # the two role requests) in the durable artifact.
            candidate["input_tokens_by_batch"] = candidate.get("combined_input_tokens_by_batch")
        candidate.setdefault("allow_fallbacks", False)
        # R98 adds an explicit transport kind.  Leave it absent for R97
        # candidates so their previously signed request identities replay
        # byte-for-byte; callers use openrouter as the compatibility default.
        if "transport_kind" in item:
            candidate["transport_kind"] = item["transport_kind"]
        if isinstance(document.get("spend_budget"), Mapping):
            hard_caps = document["spend_budget"].get("per_candidate_hard_cap_usd_with_one_retry_each", {})
            if isinstance(hard_caps, Mapping) and candidate.get("candidate_id") in hard_caps:
                candidate["maximum_spend_usd"] = str(hard_caps[candidate["candidate_id"]])
        for key in ("candidate_id", "model", "provider", "response_provider", "quantization", "data_collection", "zdr", "allow_fallbacks", "input_usd_per_million", "output_usd_per_million"):
            if key not in candidate:
                raise PilotInputError(f"budget candidate lacks {key}")
        if not isinstance(candidate.get("endpoint_aliases"), list) or not candidate["endpoint_aliases"]:
            raise PilotInputError("budget candidate lacks endpoint aliases")
        aliases_to_add = (candidate.get("endpoint_tag"), candidate.get("provider")) if "transport_kind" in item else ()
        candidate["endpoint_aliases"] = list(dict.fromkeys(
            alias for alias in (
                *candidate["endpoint_aliases"],
                candidate.get("response_provider"),
                candidate.get("response_model"),
                *aliases_to_add,
            ) if isinstance(alias, str) and alias
        ))
        input_bounds = candidate.get("input_tokens_by_batch")
        if not isinstance(input_bounds, list) or len(input_bounds) != 3 or any(not isinstance(value, int) or value <= 0 for value in input_bounds):
            raise PilotInputError("budget candidate lacks three frozen combined input bounds")
        model_cap = caps.per_model.get(str(candidate["model"]))
        if not isinstance(model_cap, Mapping) or sum(input_bounds) * 2 != int(model_cap.get("maximum_input_tokens", -1)):
            raise PilotInputError("candidate input bounds do not equal its retry-envelope input cap")
        candidate["maximum_spend_usd"] = str(model_cap["maximum_spend_usd"])
        if candidate.get("transport_kind") == "direct_deepseek_anthropic":
            if candidate.get("provider") != "deepseek" or candidate.get("model") != "deepseek-v4-flash":
                raise PilotInputError("direct DeepSeek candidate identity is not frozen")
            if candidate.get("endpoint_tag") is not None or candidate.get("service_tier") is not None:
                raise PilotInputError("direct DeepSeek candidate cannot use router endpoint or service tier")
        elif candidate.get("transport_kind", "openrouter") != "openrouter":
            raise PilotInputError("unknown candidate transport kind")
        if candidate.get("service_tier") not in {None, "flex"}:
            raise PilotInputError("unsupported service tier")
        if candidate.get("service_tier") == "flex" and not candidate.get("endpoint_tag"):
            raise PilotInputError("Flex candidate lacks endpoint tag")
        candidates.append(candidate)
    model_caps = [caps.per_model.get(str(candidate["model"])) for candidate in candidates]
    if any(not isinstance(item, Mapping) for item in model_caps):
        raise PilotInputError("every candidate must have a per-model cap")
    if sum(int(item["maximum_logical_requests"]) for item in model_caps) != caps.maximum_logical_requests or sum(int(item["maximum_transport_attempts"]) for item in model_caps) != caps.maximum_transport_attempts or sum(int(item["maximum_input_tokens"]) for item in model_caps) != caps.maximum_input_tokens or sum(int(item["maximum_output_tokens"]) for item in model_caps) != caps.maximum_output_tokens or sum(Decimal(str(item["maximum_spend_usd"])) for item in model_caps) != caps.maximum_spend_usd:
        raise PilotInputError("global caps do not equal the sum of frozen candidate caps")
    return caps, tuple(candidates), max_attempts


@dataclass
class BudgetLedger:
    caps: FrozenCaps
    logical_requests: int = 0
    transport_attempts: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    spend_usd: Decimal = Decimal(0)
    reserved_attempts: int = 0
    reserved_input_tokens: int = 0
    reserved_output_tokens: int = 0
    reserved_spend_usd: Decimal = Decimal(0)
    model_usage: dict[str, dict[str, Any]] = field(default_factory=dict)
    model_reserved: dict[str, dict[str, Any]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def reserve_pair(self, *, estimated_input_tokens: int, max_output_tokens: int, max_attempts: int, estimated_spend: Decimal, model_id: str | None = None) -> None:
        """Reserve both roles' entire retry envelopes before either dispatch.

        ``estimated_input_tokens`` is the frozen combined bound for the pair
        of role requests.  ``max_output_tokens`` remains the per-role output
        cap, while ``estimated_spend`` is already the combined pair cost.
        """
        with self._lock:
            projected_logical = self.logical_requests + 2
            projected_attempts = self.transport_attempts + self.reserved_attempts + (2 * max_attempts)
            projected_input = self.input_tokens + self.reserved_input_tokens + (estimated_input_tokens * max_attempts)
            projected_output = self.output_tokens + self.reserved_output_tokens + (2 * max_output_tokens * max_attempts)
            projected_spend = self.spend_usd + self.reserved_spend_usd + (estimated_spend * max_attempts)
            if projected_logical > self.caps.maximum_logical_requests:
                raise PilotCapExceeded("logical request cap exceeded before dispatch")
            if projected_attempts > self.caps.maximum_transport_attempts:
                raise PilotCapExceeded("transport retry envelope exceeds cap before dispatch")
            if projected_input > self.caps.maximum_input_tokens:
                raise PilotCapExceeded("input token cap exceeded before dispatch")
            if projected_output > self.caps.maximum_output_tokens:
                raise PilotCapExceeded("output token cap exceeded before dispatch")
            if projected_spend > self.caps.maximum_spend_usd:
                raise PilotCapExceeded("spend cap exceeded before dispatch")
            if model_id in self.caps.per_model:
                limit = self.caps.per_model[model_id]
                state = self.model_usage.setdefault(model_id, {"logical_requests": 0, "transport_attempts": 0, "input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "spend_usd": Decimal(0)})
                reserved = self.model_reserved.setdefault(model_id, {"transport_attempts": 0, "input_tokens": 0, "output_tokens": 0, "spend_usd": Decimal(0)})
                if state["logical_requests"] + 2 > int(limit.get("maximum_logical_requests", 6)) or state["transport_attempts"] + reserved["transport_attempts"] + 2 * max_attempts > int(limit.get("maximum_transport_attempts", 12)) or state["input_tokens"] + reserved["input_tokens"] + estimated_input_tokens * max_attempts > int(limit.get("maximum_input_tokens", self.caps.maximum_input_tokens)) or state["output_tokens"] + reserved["output_tokens"] + 2 * max_output_tokens * max_attempts > int(limit.get("maximum_output_tokens", self.caps.maximum_output_tokens)) or state["spend_usd"] + reserved["spend_usd"] + estimated_spend * max_attempts > Decimal(str(limit.get("maximum_spend_usd", self.caps.maximum_spend_usd))):
                    raise PilotCapExceeded("per-model cap exceeded before dispatch")
                state["logical_requests"] += 2
                reserved["transport_attempts"] += 2 * max_attempts
                reserved["input_tokens"] += estimated_input_tokens * max_attempts
                reserved["output_tokens"] += 2 * max_output_tokens * max_attempts
                reserved["spend_usd"] += estimated_spend * max_attempts
            self.logical_requests += 2
            self.reserved_attempts += 2 * max_attempts
            self.reserved_input_tokens += estimated_input_tokens * max_attempts
            self.reserved_output_tokens += 2 * max_output_tokens * max_attempts
            self.reserved_spend_usd += estimated_spend * max_attempts

    def release_reservation(self, attempts: int, *, input_tokens: int = 0, output_tokens: int = 0, spend_usd: Decimal = Decimal(0), max_attempts: int | None = None, model_id: str | None = None) -> None:
        with self._lock:
            self.reserved_attempts = max(0, self.reserved_attempts - attempts)
            if max_attempts is not None:
                self.reserved_input_tokens = max(0, self.reserved_input_tokens - input_tokens * max_attempts)
                self.reserved_output_tokens = max(0, self.reserved_output_tokens - 2 * output_tokens * max_attempts)
                self.reserved_spend_usd = max(Decimal(0), self.reserved_spend_usd - spend_usd * max_attempts)
                if model_id in self.model_reserved:
                    reserved = self.model_reserved[model_id]
                    reserved["transport_attempts"] = max(0, reserved["transport_attempts"] - 2 * max_attempts)
                    reserved["input_tokens"] = max(0, reserved["input_tokens"] - input_tokens * max_attempts)
                    reserved["output_tokens"] = max(0, reserved["output_tokens"] - 2 * output_tokens * max_attempts)
                    reserved["spend_usd"] = max(Decimal(0), reserved["spend_usd"] - spend_usd * max_attempts)

    def record_attempt(self, usage: Mapping[str, Any] | None, *, cost: Decimal = Decimal(0), model_id: str | None = None) -> None:
        normalized = normalize_usage(usage)
        with self._lock:
            self.transport_attempts += 1
            self.input_tokens += int(normalized["input_tokens"] or 0)
            self.output_tokens += int(normalized["output_tokens"] or 0)
            self.reasoning_tokens += int(normalized["reasoning_tokens"] or 0)
            self.spend_usd += cost
            if model_id in self.caps.per_model:
                state = self.model_usage.setdefault(model_id, {"logical_requests": 0, "transport_attempts": 0, "input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "spend_usd": Decimal(0)})
                state["transport_attempts"] += 1
                state["input_tokens"] += int(normalized["input_tokens"] or 0)
                state["output_tokens"] += int(normalized["output_tokens"] or 0)
                state["reasoning_tokens"] += int(normalized["reasoning_tokens"] or 0)
                state["spend_usd"] += cost
                limit = self.caps.per_model[model_id]
                if state["transport_attempts"] > int(limit.get("maximum_transport_attempts", 12)) or state["input_tokens"] > int(limit.get("maximum_input_tokens", self.caps.maximum_input_tokens)) or state["output_tokens"] > int(limit.get("maximum_output_tokens", self.caps.maximum_output_tokens)) or state["reasoning_tokens"] > int(limit.get("maximum_reasoning_tokens", self.caps.maximum_reasoning_tokens)) or state["spend_usd"] > Decimal(str(limit.get("maximum_spend_usd", self.caps.maximum_spend_usd))):
                    raise PilotCapExceeded("observed usage exceeded per-model cap")
            if self.transport_attempts > self.caps.maximum_transport_attempts or self.input_tokens > self.caps.maximum_input_tokens or self.output_tokens > self.caps.maximum_output_tokens or self.reasoning_tokens > self.caps.maximum_reasoning_tokens or self.spend_usd > self.caps.maximum_spend_usd:
                raise PilotCapExceeded("observed usage exceeded frozen cap")

    def snapshot(self) -> dict[str, Any]:
        """Take an aggregate counter snapshot without exposing reservations."""
        with self._lock:
            return {
                "logical_requests": self.logical_requests,
                "transport_attempts": self.transport_attempts,
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "reasoning_tokens": self.reasoning_tokens,
                "spend_usd": self.spend_usd,
            }

    def delta(self, start: Mapping[str, Any]) -> dict[str, Any]:
        """Return counters consumed since ``start`` for per-candidate reports."""
        end = self.snapshot()
        return {
            key: str(end[key] - start.get(key, 0)) if key == "spend_usd" else end[key] - start.get(key, 0)
            for key in end
        }


def _estimate_tokens(packet: Sequence[Mapping[str, Any]], prompt: str) -> int:
    return max(1, math.ceil((len(prompt.encode("utf-8")) + len(_json(packet).encode("utf-8"))) / 4))


def _price(candidate: Mapping[str, Any], input_tokens: int, output_tokens: int) -> Decimal:
    return (Decimal(str(candidate["input_usd_per_million"])) * input_tokens + Decimal(str(candidate["output_usd_per_million"])) * output_tokens) / Decimal(1_000_000)


def merge_role_rows(content: Any, brand: Any, packets: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], set[str]]:
    """Assemble disjoint role fields; invalid or missing pairs are failures."""
    # Use the exact production parser and merge shape.  A malformed response
    # returns an empty parsed map, making every affected row a coverage failure.
    left_payload = _two_role_payload([dict(packet) for packet in packets], "content")
    right_payload = _two_role_payload([dict(packet) for packet in packets], "brand_interpretation")
    left = _two_role_parse(content if isinstance(content, Mapping) else {}, left_payload, "content")
    right = _two_role_parse(brand if isinstance(brand, Mapping) else {}, right_payload, "brand_interpretation")
    failures: set[str] = set()
    merged: list[dict[str, Any]] = []
    for packet in packets:
        tweet_id = str(packet["tweet_id"])
        key = _two_role_fingerprint(dict(packet))
        lrow, rrow = left.get(tweet_id), right.get(tweet_id)
        for brand_id in packet.get("brand_ids") or []:
            if not lrow or not rrow or brand_id not in lrow.get("by_brand", {}) or brand_id not in rrow.get("by_brand", {}):
                failures.add(f"{key}:{brand_id}")
                continue
            row = {**lrow["by_brand"][brand_id], **rrow["by_brand"][brand_id]}
            parsed = parse_stage1_classifications([{**row, "brand_id": brand_id}], [brand_id])
            if parsed is None:
                failures.add(f"{key}:{brand_id}")
            else:
                merged.append({"row_key": key, "target_brand": brand_id, **parsed[brand_id]})
    return merged, failures


def attest_provider(response: Any, candidate: Mapping[str, Any], endpoint_aliases: Sequence[str] | None = None) -> dict[str, Any]:
    """Require provider/model/request identity before accepting a response."""
    usage = normalize_usage(getattr(response, "provider_usage", None))
    raw = getattr(response, "provider_usage", None)
    if not isinstance(raw, Mapping):
        raise PilotInputError("provider attestation is missing")
    provider = raw.get("provider")
    model = raw.get("model")
    request_id = usage.get("provider_request_id")
    expected_provider = candidate.get("response_provider", candidate["provider"])
    expected_models = {candidate["model"], *(value for value in (candidate.get("response_model"),) if value)}
    if provider not in {expected_provider, candidate["provider"]} or model not in expected_models or not request_id:
        raise PilotInputError("provider/model/request attestation mismatch")
    # The adapter's normalized usage carries the exact selected router
    # provider/model; endpoint display aliases are frozen budget metadata.
    endpoint = raw.get("selected_endpoint") or raw.get("endpoint") or expected_provider
    if not isinstance(endpoint, str) or not endpoint:
        raise PilotInputError("selected provider attestation is missing")
    aliases = tuple(endpoint_aliases or candidate.get("endpoint_aliases") or (candidate["provider"],))
    if endpoint not in aliases and provider not in aliases:
        raise PilotInputError("selected endpoint is outside the frozen aliases")
    expected_tier = candidate.get("service_tier")
    observed_tier = raw.get("service_tier")
    if expected_tier is not None and observed_tier != expected_tier:
        raise PilotInputError("service tier attestation mismatch")
    if expected_tier is None and observed_tier not in {None, ""}:
        # A paid Flex marker on a regular candidate would make its price
        # projection and route identity false.
        raise PilotInputError("unexpected service tier attestation")
    return {"provider": provider, "model": model, "provider_request_id": request_id, "selected_endpoint": endpoint, "service_tier": observed_tier, "usage": usage}


def request_signature(*, candidate: Mapping[str, Any], role: str, packets: Sequence[Mapping[str, Any]], max_tokens: int) -> str:
    # Keep the old R97 identity exactly intact. New route fields are included
    # only for R98 candidates, so old response artifacts remain replayable.
    identity_keys = ("candidate_id", "model", "provider", "response_provider", "response_model", "endpoint_aliases", "quantization", "data_collection", "zdr", "reasoning_enabled", "allow_fallbacks", "max_input_price", "max_output_price")
    identity = {key: candidate.get(key) for key in identity_keys}
    if "transport_kind" in candidate:
        identity.update({key: candidate.get(key) for key in ("transport_kind", "route", "endpoint_tag", "service_tier")})
    return _sha({"candidate": identity, "role": role, "prompt": ROLE_PROMPTS[role], "packets": list(packets), "max_tokens": max_tokens})


@dataclass
class TwoRolePilot:
    candidate: Mapping[str, Any]
    private_dir: Path = DEFAULT_PRIVATE_DIR
    caps: FrozenCaps = field(default_factory=FrozenCaps)
    max_transport_attempts_per_role: int = PILOT_MAX_TRANSPORT_ATTEMPTS
    max_tokens: int = 4096
    max_concurrent_transports: int = MAX_CONCURRENT_TRANSPORTS
    endpoint_aliases: Sequence[str] | None = None
    ledger: BudgetLedger | None = None
    measurements: list[dict[str, Any]] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self.private_dir = Path(self.private_dir)
        if self.max_transport_attempts_per_role < 1 or self.max_transport_attempts_per_role > DEFAULT_MAX_TRANSPORT_ATTEMPTS:
            raise PilotInputError("max transport attempts per role must be 1..3")
        if self.candidate.get("allow_fallbacks") is not False or self.candidate.get("reasoning_enabled") not in {False, None}:
            raise PilotInputError("candidate route is not strictly pinned")
        if self.ledger is None:
            self.ledger = BudgetLedger(self.caps)

    def _call(self, *, role: str, packets: Sequence[Mapping[str, Any]], client: Any, replay: bool = False) -> Any:
        payload = _two_role_payload([dict(packet) for packet in packets], role)
        signature = request_signature(candidate=self.candidate, role=role, packets=payload, max_tokens=self.max_tokens)
        response_path = self.private_dir / "responses" / f"{signature}.json"
        if replay:
            if not response_path.exists():
                raise PilotInputError(f"replay response missing: {signature}")
            saved = _read_json(response_path)
            if saved.get("signature") != signature or not isinstance(saved.get("response"), Mapping):
                raise PilotInputError("replay response signature mismatch")
            response = ProviderResponse(saved["response"], usage=saved.get("usage"))
            attestation = attest_provider(response, self.candidate, self.endpoint_aliases)
            self.measurements.append({"role": role, "signature": signature, "attempt": 0, "retry": False, "replay": True, "latency_ms": 0, "attestation": {key: value for key, value in attestation.items() if key != "usage"}, "usage": attestation["usage"]})
            return response
        direct = self.candidate.get("transport_kind") == "direct_deepseek_anthropic"
        kwargs = {"model": self.candidate["model"], "max_tokens": self.max_tokens, "temperature": 0, "timeout": 90, "system": ROLE_PROMPTS[role], "messages": [{"role": "user", "content": _json(payload)}]}
        if not direct:
            kwargs["provider"] = self.candidate["provider"]
            if self.candidate.get("service_tier") is not None:
                kwargs["service_tier"] = self.candidate["service_tier"]
        elif self.candidate.get("reasoning_enabled") is False:
            # DeepSeek V4 enables thinking by default on its Anthropic route;
            # the control contract pins it off for the measured two-role shape.
            kwargs["thinking"] = {"type": "disabled"}
        if not direct and self.candidate.get("reasoning_enabled") is not None:
            kwargs["reasoning"] = {"enabled": self.candidate["reasoning_enabled"]}
        last_error: Exception | None = None
        if client is None:
            raise PilotInputError("OpenRouter client unavailable; no transport dispatched")
        estimated_input = _estimate_tokens(payload, ROLE_PROMPTS[role])
        for attempt in range(1, self.max_transport_attempts_per_role + 1):
            started = time.monotonic()
            try:
                response = client.messages_create(**kwargs)
                try:
                    attestation = attest_provider(response, self.candidate, self.endpoint_aliases)
                except PilotInputError:
                    # A completed response is a billable transport even when
                    # its route identity is unsafe. Record it before failing
                    # closed, using provider usage where available and the
                    # frozen input bound as the conservative fallback.
                    raw_usage = getattr(response, "provider_usage", None)
                    observed = normalize_usage(raw_usage)
                    observed_input = int(observed.get("input_tokens") or estimated_input)
                    observed_output = int(observed.get("output_tokens") or 0)
                    observed_cost = Decimal(str(observed.get("cost_usd") or _price(self.candidate, observed_input, observed_output)))
                    assert self.ledger is not None
                    self.ledger.record_attempt(raw_usage or {"input_tokens": observed_input}, cost=observed_cost, model_id=self.candidate["model"])
                    self.measurements.append({
                        "role": role,
                        "signature": signature,
                        "attempt": attempt,
                        "retry": attempt > 1,
                        "latency_ms": round((time.monotonic() - started) * 1000),
                        "failure_code": "provider_attestation_failed",
                        "usage": normalize_usage(raw_usage or {"input_tokens": observed_input}),
                    })
                    raise
                usage = attestation["usage"]
                cost = Decimal(str(usage.get("cost_usd") or _price(self.candidate, int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0))))
                assert self.ledger is not None
                self.ledger.record_attempt(getattr(response, "provider_usage", None), cost=cost, model_id=self.candidate["model"])
                decoded = dict(response) if isinstance(response, Mapping) else response
                if not isinstance(decoded, Mapping):
                    raise PilotInputError("provider response is not JSON object")
                # Raw data is private and never copied into the durable report.
                persisted_usage = {**usage, "provider": attestation["provider"], "model": attestation["model"], "selected_endpoint": attestation["selected_endpoint"]}
                _write_json(response_path, {"response": decoded, "attestation": {key: value for key, value in attestation.items() if key != "usage"}, "usage": persisted_usage, "signature": signature})
                self.measurements.append({"role": role, "signature": signature, "attempt": attempt, "retry": attempt > 1, "latency_ms": round((time.monotonic() - started) * 1000), "attestation": {key: value for key, value in attestation.items() if key != "usage"}, "usage": usage})
                return decoded
            except (OpenRouterRetryableError, AnthropicCompatibleRetryableError, TimeoutError, OSError) as exc:
                last_error = exc
                self.ledger.record_attempt({"input_tokens": estimated_input}, cost=_price(self.candidate, estimated_input, 0), model_id=self.candidate["model"])
                if attempt == self.max_transport_attempts_per_role:
                    break
            except (OpenRouterPermanentError, AnthropicCompatiblePermanentError) as exc:
                usage = getattr(exc, "provider_usage", None) or {"input_tokens": estimated_input}
                cost = Decimal(str(
                    usage.get("cost_usd")
                    or _price(
                        self.candidate,
                        int(usage.get("input_tokens") or estimated_input),
                        int(usage.get("output_tokens") or 0),
                    )
                ))
                self.ledger.record_attempt(usage, cost=cost, model_id=self.candidate["model"])
                normalized = normalize_usage(usage)
                self.measurements.append({
                    "role": role,
                    "signature": signature,
                    "attempt": attempt,
                    "retry": attempt > 1,
                    "latency_ms": round((time.monotonic() - started) * 1000),
                    "failure_code": str(exc),
                    "usage": normalized,
                })
                raise
            except PilotInputError:
                raise
        raise PilotInputError(f"transport failed after {self.max_transport_attempts_per_role} attempts") from last_error

    def run_candidate(self, packets: Sequence[dict[str, Any]], client_factory: Callable[[Mapping[str, Any]], Any] | None = None, *, replay: bool = False) -> dict[str, Any]:
        assert self.ledger is not None
        all_batches = batches(packets)
        ledger_start = self.ledger.snapshot()
        responses: list[dict[str, Any]] = []
        complete_latencies: list[int] = []
        limiter = threading.BoundedSemaphore(self.max_concurrent_transports)
        for batch_index, batch in enumerate(all_batches):
            content_payload = _two_role_payload([dict(packet) for packet in batch], "content")
            brand_payload = _two_role_payload([dict(packet) for packet in batch], "brand_interpretation")
            frozen_input = self.candidate.get("input_tokens_by_batch")
            estimated_input = (int(frozen_input[batch_index]) if isinstance(frozen_input, list) and batch_index < len(frozen_input) else _estimate_tokens(content_payload, CONTENT_SYSTEM_PROMPT) + _estimate_tokens(brand_payload, BRAND_SYSTEM_PROMPT))
            estimated_spend = _price(self.candidate, estimated_input, self.max_tokens * 2)
            self.ledger.reserve_pair(estimated_input_tokens=estimated_input, max_output_tokens=self.max_tokens, max_attempts=self.max_transport_attempts_per_role, estimated_spend=estimated_spend, model_id=self.candidate["model"])
            def invoke(role: str, current_batch: Sequence[Mapping[str, Any]] = batch) -> Any:
                with limiter:
                    if replay:
                        return self._call(role=role, packets=current_batch, client=None, replay=True)
                    if client_factory is None:
                        raise PilotInputError("provider client factory required for frozen-run")
                    return self._call(role=role, packets=current_batch, client=client_factory(self.candidate))
            try:
                batch_started = time.monotonic()
                with ThreadPoolExecutor(max_workers=2) as pool:
                    content_future = pool.submit(invoke, "content")
                    brand_future = pool.submit(invoke, "brand_interpretation")
                    content, brand = content_future.result(), brand_future.result()
            finally:
                self.ledger.release_reservation(2 * self.max_transport_attempts_per_role, input_tokens=estimated_input, output_tokens=self.max_tokens, spend_usd=estimated_spend, max_attempts=self.max_transport_attempts_per_role, model_id=self.candidate["model"])
            merged, failures = merge_role_rows(content, brand, batch)
            complete_latencies.append(round((time.monotonic() - batch_started) * 1000))
            responses.append({"batch_index": batch_index, "batch_size": len(batch), "merged": merged, "failed_row_keys": sorted(failures)})
        return {"candidate_id": self.candidate["candidate_id"], "batches": responses, "measurements": list(self.measurements), "complete_result_latencies_ms": complete_latencies, "ledger": self.ledger.delta(ledger_start)}


def score_candidate(
    result: Mapping[str, Any],
    reference: Mapping[str, Any],
    local: Mapping[str, Mapping[str, Any]],
    floors: Mapping[str, Any] | None = None,
    unsupported_floor_paths: Sequence[str] = (),
) -> dict[str, Any]:
    expected = {(str(row.get("example_id")), str(row.get("brand_id"))): row for row in reference.get("rows", []) if isinstance(row, Mapping)}
    actual: dict[tuple[str, str], Mapping[str, Any]] = {}
    failures = 0
    for batch in result.get("batches", []):
        for row in batch.get("merged", []):
            if not isinstance(row, Mapping):
                continue
            key = local.get(str(row.get("row_key")))
            if key:
                actual[(str(key.get("example_id")), str(key.get("brand_id")))] = row
    dimensions = ("outcome", "post_types", "product_labels", "sentiment", "china_nationalism", "us_nationalism")
    exact = 0
    dimension_matches = {dimension: 0 for dimension in dimensions}
    for pair, expected_row in expected.items():
        truth = expected_row.get("classification") if isinstance(expected_row, Mapping) else None
        candidate = actual.get(pair)
        if not isinstance(truth, Mapping) or not isinstance(candidate, Mapping):
            failures += 1
            continue
        matches = True
        for dimension in dimensions:
            if candidate.get(dimension) == truth.get(dimension):
                dimension_matches[dimension] += 1
            else:
                matches = False
        if matches:
            exact += 1
    valid_pairs = [
        (actual.get(pair, {}), row.get("classification", {}))
        for pair, row in expected.items()
        if isinstance(row.get("classification"), Mapping)
    ]

    def set_f1(family: str, label: str | None = None) -> float | None:
        tp = fp = fn = 0
        for candidate_row, truth_row in valid_pairs:
            predicted = set(candidate_row.get(family, []))
            truth = set(truth_row.get(family, []))
            if label is not None:
                predicted = predicted & {label}
                truth = truth & {label}
            tp += len(predicted & truth)
            fp += len(predicted - truth)
            fn += len(truth - predicted)
        return 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else None

    quality: dict[str, Any] = {
        "outcome": {"accuracy": dimension_matches["outcome"] / len(expected) if expected else 0.0},
        "sentiment": {"accuracy": dimension_matches["sentiment"] / len(expected) if expected else 0.0},
        "china_nationalism": {"accuracy": dimension_matches["china_nationalism"] / len(expected) if expected else 0.0},
        "us_nationalism": {"accuracy": dimension_matches["us_nationalism"] / len(expected) if expected else 0.0},
    }
    quality["post_types"] = {
        "exact_set_accuracy": {"value": sum(set(a.get("post_types", [])) == set(t.get("post_types", [])) for a, t in valid_pairs) / len(expected) if expected else 0.0},
        "micro": {"f1": set_f1("post_types")},
        "labels": {label: {"f1": set_f1("post_types", label)} for label in CANONICAL_POST_TYPE_KEYS},
    }
    quality["product_labels"] = {
        "exact_set_accuracy": {"value": sum(set(a.get("product_labels", [])) == set(t.get("product_labels", [])) for a, t in valid_pairs) / len(expected) if expected else 0.0},
        "empty_set_accuracy": {"value": sum(bool(a.get("product_labels")) == bool(t.get("product_labels")) for a, t in valid_pairs) / len(expected) if expected else 0.0},
        "micro": {"f1": set_f1("product_labels")},
        "labels": {label: {"f1": set_f1("product_labels", label)} for label in CANONICAL_PRODUCT_LABEL_KEYS},
    }
    for family, labels in (("outcome", OUTCOMES), ("sentiment", SENTIMENT_KEYS), ("china_nationalism", NATIONALISM_KEYS), ("us_nationalism", NATIONALISM_KEYS)):
        quality[family]["classes"] = {}
        for label in labels:
            support = sum(truth.get(family) == label for _, truth in valid_pairs)
            quality[family]["classes"][label] = {"recall": sum(candidate.get(family) == label and truth.get(family) == label for candidate, truth in valid_pairs) / support if support else None}
        unknown_support = sum(truth.get(family) is None for _, truth in valid_pairs)
        quality[family]["classes"]["unknown"] = {"recall": sum(candidate.get(family) is None and truth.get(family) is None for candidate, truth in valid_pairs) / unknown_support if unknown_support else None}
    slices: dict[str, dict[str, dict[str, int]]] = {}
    for slice_name in ("source_language", "source_role", "source_hint", "stratum"):
        values: dict[str, dict[str, int]] = {}
        for pair, expected_value in expected.items():
            key = next((item for item in local.values() if (str(item.get("example_id")), str(item.get("brand_id"))) == pair), None)
            label = str((key or {}).get(slice_name) or "unknown")
            bucket = values.setdefault(label, {"rows": 0, "exact_rows": 0, "coverage_failures": 0})
            bucket["rows"] += 1
            if pair in actual:
                candidate = actual[pair]
                truth = expected_value.get("classification", {})
                if all(candidate.get(dimension) == truth.get(dimension) for dimension in dimensions):
                    bucket["exact_rows"] += 1
            else:
                bucket["coverage_failures"] += 1
        slices[slice_name] = values
    pair_local = {
        (str(item.get("example_id")), str(item.get("brand_id"))): item
        for item in local.values()
    }
    for slice_name in ("source_language", "source_role", "source_hint", "stratum"):
        for label, bucket in slices[slice_name].items():
            selected_pairs = [pair for pair in expected if str(pair_local.get(pair, {}).get(slice_name) or "unknown") == label]
            count = len(selected_pairs)
            bucket["outcome"] = {"accuracy": sum(pair in actual and actual[pair].get("outcome") == expected[pair].get("classification", {}).get("outcome") for pair in selected_pairs) / count if count else 0.0}
            bucket["post_types"] = {"exact_set_accuracy": {"value": sum(pair in actual and set(actual[pair].get("post_types", [])) == set(expected[pair].get("classification", {}).get("post_types", [])) for pair in selected_pairs) / count if count else 0.0}}
            bucket["product_labels"] = {"exact_set_accuracy": {"value": sum(pair in actual and set(actual[pair].get("product_labels", [])) == set(expected[pair].get("classification", {}).get("product_labels", [])) for pair in selected_pairs) / count if count else 0.0}}
            bucket["sentiment"] = {"accuracy": sum(pair in actual and actual[pair].get("sentiment") == expected[pair].get("classification", {}).get("sentiment") for pair in selected_pairs) / count if count else 0.0}
    context_values: dict[str, dict[str, Any]] = {}
    for pair, expected_value in expected.items():
        metadata = pair_local.get(pair, {})
        context_labels = metadata.get("context") or []
        label = str(context_labels[0] if context_labels else "none")
        bucket = context_values.setdefault(label, {"rows": 0, "exact_rows": 0, "coverage_failures": 0, "_dimensions": {dimension: 0 for dimension in dimensions}})
        bucket["rows"] += 1
        candidate = actual.get(pair)
        truth = expected_value.get("classification", {})
        if candidate is None:
            bucket["coverage_failures"] += 1
        else:
            if all(candidate.get(dimension) == truth.get(dimension) for dimension in dimensions):
                bucket["exact_rows"] += 1
            for dimension in dimensions:
                bucket["_dimensions"][dimension] += int(candidate.get(dimension) == truth.get(dimension))
    for label, bucket in context_values.items():
        count = bucket["rows"]
        dimension_counts = bucket.pop("_dimensions")
        for dimension in dimensions:
            bucket[dimension] = {"accuracy": dimension_counts[dimension] / count if count else 0.0}
        selected_pairs = [
            pair for pair, item in pair_local.items()
            if str((item.get("context") or ["none"])[0]) == label
        ]
        bucket["post_types"] = {"exact_set_accuracy": {"value": sum(pair in actual and set(actual[pair].get("post_types", [])) == set(expected[pair].get("classification", {}).get("post_types", [])) for pair in selected_pairs) / count if count else 0.0}}
        bucket["product_labels"] = {"exact_set_accuracy": {"value": sum(pair in actual and set(actual[pair].get("product_labels", [])) == set(expected[pair].get("classification", {}).get("product_labels", [])) for pair in selected_pairs) / count if count else 0.0}}
    slices["context"] = context_values
    coverage = (len(expected) - failures) / len(expected) if expected else 0.0
    score = {"source_posts": len(expected), "post_brand_rows": len(expected), "rows": len(expected), "complete_rows": len(actual), "coverage_failures": failures, "coverage": coverage, "exact_rows": exact, "dimension_matches": dimension_matches, "agreement": exact / len(expected) if expected else 0.0, "micro_f1": quality["post_types"]["micro"]["f1"], "quality": quality, "by_language": slices["source_language"], "by_context": slices["context"], "human_gold": False, "assessment": "owner_reference_agreement_only"}
    score["floor_gate"] = _floor_report(score, floors, unsupported_floor_paths)
    return score


def _floor_report(
    score: Mapping[str, Any],
    floors: Mapping[str, Any] | None,
    unsupported_floor_paths: Sequence[str] = (),
) -> dict[str, Any]:
    floors = floors or {}
    unsupported = set(unsupported_floor_paths)
    checks: dict[str, Any] = {}
    quality = score.get("quality", {})
    for name, minimum in floors.items():
        path = name.replace("all.", "overall.", 1)
        if path.startswith("by_context."):
            parts = path.split(".")
            value = score.get("by_context", {}).get(parts[1]) if len(parts) > 1 else None
            for part in parts[2:]:
                value = value.get(part) if isinstance(value, Mapping) else None
        elif path.startswith("by_language."):
            parts = path.split(".")
            value = score.get("by_language", {}).get(parts[1]) if len(parts) > 1 else None
            for part in parts[2:]:
                value = value.get(part) if isinstance(value, Mapping) else None
        else:
            value = quality
            for part in path.removeprefix("overall.").split("."):
                value = value.get(part) if isinstance(value, Mapping) else None
        if value is None:
            is_unsupported = name in unsupported
            checks[name] = {
                "observed": None,
                "minimum": minimum,
                "status": "unmeasured" if is_unsupported else "missing",
                "passed": is_unsupported,
            }
        else:
            checks[name] = {"observed": value, "minimum": minimum, "passed": float(value) >= float(minimum)}
    if not floors:
        checks["floors_declared"] = {"observed": False, "status": "missing", "passed": False}
    return {"checks": checks, "passed": bool(checks) and all(item["passed"] for item in checks.values())}


def _verify_source_receipts(document: Mapping[str, Any]) -> dict[str, str]:
    receipts = document.get("source_receipts")
    if not isinstance(receipts, Mapping):
        return {}
    verified: dict[str, str] = {}
    for name, receipt in receipts.items():
        if not isinstance(receipt, Mapping):
            continue
        pairs = [(receipt.get("path"), receipt.get("sha256"))]
        pairs.extend(
            (value, receipt.get(f"{key.removesuffix('_path')}_sha256"))
            for key, value in receipt.items()
            if isinstance(key, str) and key.endswith("_path")
        )
        for raw_path, expected_sha in pairs:
            if not isinstance(raw_path, str) or not isinstance(expected_sha, str):
                continue
            source_path = ROOT / raw_path
            try:
                actual_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()
            except OSError as exc:
                raise PilotInputError(f"frozen source receipt is unreadable: {name}") from exc
            if actual_sha != expected_sha:
                raise PilotInputError(f"frozen source receipt hash mismatch: {name}")
            verified[raw_path] = actual_sha
    return verified


def catalog_preflight(
    candidates: Sequence[Mapping[str, Any]],
    fetch: Callable[[str], Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Re-attest every exact endpoint immediately before paid transport."""
    def fetch_json(url: str) -> Mapping[str, Any]:
        with urllib.request.urlopen(url, timeout=30) as response:
            decoded = json.loads(response.read())
        if not isinstance(decoded, Mapping):
            raise PilotInputError("endpoint catalog response is not an object")
        return decoded

    loader = fetch or fetch_json
    results = []
    for candidate in candidates:
        if candidate.get("transport_kind", "openrouter") == "direct_deepseek_anthropic":
            route = str(candidate.get("route", ""))
            expected_route = "https://api.deepseek.com/anthropic/v1/messages"
            checks = {
                "transport": True,
                "provider": candidate.get("provider") == "deepseek",
                "model": candidate.get("model") == "deepseek-v4-flash",
                "route": route == expected_route,
                "thinking_disabled": candidate.get("reasoning_enabled") is False,
                "service_tier_omitted": candidate.get("service_tier") is None,
            }
            if not all(checks.values()):
                failed = ",".join(key for key, passed in checks.items() if not passed)
                raise PilotInputError(f"direct DeepSeek preflight failed:{failed}")
            results.append({
                "candidate_id": candidate["candidate_id"],
                "provider": candidate["response_provider"],
                "endpoint_tag": None,
                "endpoint_name": "direct DeepSeek Anthropic-compatible endpoint",
                "catalog_sha256": None,
                "checks": checks,
            })
            continue
        url = candidate.get("endpoint_receipt")
        if not isinstance(url, str) or not url.startswith("https://openrouter.ai/"):
            raise PilotInputError("candidate endpoint receipt is not a frozen OpenRouter URL")
        document = loader(url)
        data = document.get("data")
        if not isinstance(data, Mapping) or data.get("id") != candidate["model"]:
            raise PilotInputError("endpoint catalog model mismatch")
        endpoints = data.get("endpoints")
        matches = [item for item in endpoints or [] if isinstance(item, Mapping) and (
            item.get("provider_name") == candidate["response_provider"]
            or item.get("provider_slug") == candidate["provider"]
        )]
        if candidate.get("endpoint_tag") is not None:
            matches = [item for item in matches if (
                item.get("tag") == candidate["endpoint_tag"]
                or item.get("endpoint_tag") == candidate["endpoint_tag"]
                or item.get("provider_slug") == candidate["endpoint_tag"]
            )]
        if len(matches) != 1:
            raise PilotInputError("endpoint catalog provider route is not unique")
        endpoint = matches[0]
        pricing = endpoint.get("pricing") if isinstance(endpoint.get("pricing"), Mapping) else {}
        prompt_per_million = Decimal(str(pricing.get("prompt"))) * Decimal(1_000_000)
        completion_per_million = Decimal(str(pricing.get("completion"))) * Decimal(1_000_000)
        required_parameters = {"max_tokens", "response_format", "temperature"}
        if candidate.get("reasoning_enabled") is not None:
            required_parameters.add("reasoning")
        supported_parameters = set(endpoint.get("supported_parameters") or [])
        response_model = candidate.get("response_model")
        observed_tag = endpoint.get("tag") or endpoint.get("endpoint_tag") or endpoint.get("provider_slug")
        checks = {
            "model": endpoint.get("model_id") == candidate["model"],
            "model_alias": isinstance(response_model, str) and response_model in str(endpoint.get("name", "")),
            "quantization": candidate.get("quantization") in {None, "unknown"} or endpoint.get("quantization") == candidate.get("quantization"),
            "prompt_price": prompt_per_million == Decimal(str(candidate["input_usd_per_million"])),
            "completion_price": completion_per_million == Decimal(str(candidate["output_usd_per_million"])),
            "parameters": required_parameters <= supported_parameters,
            "completion_limit": int(endpoint.get("max_completion_tokens") or 0) >= 4096,
            "context_limit": int(endpoint.get("context_length") or 0) >= max(candidate["input_tokens_by_batch"]) + 4096,
            "available": endpoint.get("status") == 0,
        }
        if candidate.get("endpoint_tag") is not None:
            checks["endpoint_tag"] = observed_tag == candidate["endpoint_tag"]
        if candidate.get("service_tier") is not None:
            checks["service_tier"] = endpoint.get("service_tier") == candidate["service_tier"] or observed_tag == candidate.get("endpoint_tag")
        if not all(checks.values()):
            failed = ",".join(key for key, passed in checks.items() if not passed)
            raise PilotInputError(f"endpoint catalog preflight failed: {candidate['candidate_id']}:{failed}")
        results.append({
            "candidate_id": candidate["candidate_id"],
            "provider": candidate["response_provider"],
            "endpoint_tag": observed_tag,
            "endpoint_name": endpoint.get("name"),
            "catalog_sha256": _sha(document),
            "checks": checks,
        })
    return results


def preflight(manifest_path: Path = DEFAULT_MANIFEST, reference_path: Path = DEFAULT_REFERENCE, budget_path: Path | None = DEFAULT_BUDGET) -> dict[str, Any]:
    manifest, reference = _read_json(manifest_path), _read_json(reference_path)
    packets, local = build_public_packets(manifest)
    if reference.get("human_grounded") is not False or reference.get("human_gate_status") != "waived_by_owner":
        raise PilotInputError("reference must remain explicitly unblinded/non-human-grounded")
    if len(reference.get("rows", [])) != 45:
        raise PilotInputError("owner reference must contain exactly 45 rows")
    if budget_path is None:
        raise PilotInputError("--budget is required; candidate policies are never implicit")
    budget_document = _read_json(budget_path)
    verified_receipts = _verify_source_receipts(budget_document)
    caps, candidates, max_attempts = load_budget(budget_path)
    adaptive = budget_document.get("adaptive_execution")
    if isinstance(adaptive, Mapping):
        execution = adaptive.get("execution_order")
        selection = adaptive.get("selection_order")
        candidate_ids = {str(candidate["candidate_id"]) for candidate in candidates}
        if not isinstance(execution, list) or not isinstance(selection, list) or set(execution) != candidate_ids or set(selection) != candidate_ids:
            raise PilotInputError("adaptive ladder orders do not exactly match frozen candidates")
        if not execution or execution[0] != adaptive.get("control_candidate_id"):
            raise PilotInputError("adaptive ladder must execute the frozen control first")
    expected_logical = len(candidates) * len(BATCH_SIZES) * len(ROLE_NAMES)
    expected_attempts = expected_logical * max_attempts
    if caps.maximum_logical_requests != expected_logical or caps.maximum_transport_attempts != expected_attempts or max_attempts != PILOT_MAX_TRANSPORT_ATTEMPTS:
        raise PilotInputError("budget does not preserve its frozen candidate retry envelope")
    expected_manifest = budget_document.get("source_receipts", {}).get("selection_manifest", {}).get("sha256")
    expected_reference = budget_document.get("source_receipts", {}).get("owner_reference", {}).get("sha256")
    actual_manifest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    actual_reference = hashlib.sha256(reference_path.read_bytes()).hexdigest()
    if expected_manifest and actual_manifest != expected_manifest:
        raise PilotInputError("selected manifest does not match frozen receipt")
    if expected_reference and actual_reference != expected_reference:
        raise PilotInputError("owner reference does not match frozen receipt")
    return {"pilot_id": _pilot_id(budget_document), "rows": len(packets), "source_posts": 45, "post_brand_rows": 45, "batches": list(BATCH_SIZES), "initial_logical_requests": expected_logical, "max_transport_attempts_per_role": max_attempts, "candidates": [{key: value for key, value in candidate.items() if key not in {"input_usd_per_million", "output_usd_per_million"}} for candidate in candidates], "manifest_sha256": actual_manifest, "reference_sha256": actual_reference, "budget_sha256": hashlib.sha256(budget_path.read_bytes()).hexdigest(), "packet_sha256": _sha(packets), "local_rows": len(local), "verified_source_receipts": verified_receipts}


def _result_path(private_dir: Path, candidate_id: str) -> Path:
    return private_dir / "candidates" / f"{candidate_id}.json"


def _report_path(private_dir: Path, candidate_id: str) -> Path:
    return private_dir / "reports" / f"{candidate_id}.json"


def _metric_number(value: Any) -> float | None:
    """Read a recorded decimal or ``n/d=value`` baseline metric."""
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    text = value.rsplit("=", 1)[-1].strip()
    try:
        return float(text)
    except ValueError:
        return None


def _quality_release_gates(score: Mapping[str, Any], budget: Mapping[str, Any]) -> dict[str, Any]:
    quality = score.get("quality", {})
    axes = {
        "all.post_types.exact_set_accuracy.value": quality.get("post_types", {}).get("exact_set_accuracy", {}).get("value"),
        "all.product_labels.exact_set_accuracy.value": quality.get("product_labels", {}).get("exact_set_accuracy", {}).get("value"),
        "all.outcome.accuracy": quality.get("outcome", {}).get("accuracy"),
        "all.sentiment.accuracy": quality.get("sentiment", {}).get("accuracy"),
        "all.china_nationalism.accuracy": quality.get("china_nationalism", {}).get("accuracy"),
        "all.us_nationalism.accuracy": quality.get("us_nationalism", {}).get("accuracy"),
    }
    baseline = (budget.get("baseline_metrics", {}) or {}).get("overall", {})
    baseline_keys = {
        "all.post_types.exact_set_accuracy.value": "post_types_exact_set",
        "all.product_labels.exact_set_accuracy.value": "product_labels_exact_set",
        "all.outcome.accuracy": "outcome_accuracy",
        "all.sentiment.accuracy": "sentiment_accuracy",
        "all.china_nationalism.accuracy": "china_nationalism_accuracy",
        "all.us_nationalism.accuracy": "us_nationalism_accuracy",
    }
    baseline_axes = {path: _metric_number(baseline.get(key)) for path, key in baseline_keys.items()}
    observed = [float(value) for value in axes.values() if isinstance(value, (int, float))]
    baseline_values = [value for value in baseline_axes.values() if value is not None]
    observed_mean = sum(observed) / len(observed) if len(observed) == len(axes) else None
    baseline_mean = _metric_number((budget.get("acceptance_gates", {}) or {}).get("baseline_composite_mean"))
    minimum_mean = _metric_number((budget.get("acceptance_gates", {}) or {}).get("minimum_composite_mean"))
    if baseline_mean is None and len(baseline_values) == len(axes):
        baseline_mean = sum(baseline_values) / len(baseline_values)
    if minimum_mean is None and baseline_mean is not None:
        minimum_mean = baseline_mean + 0.02
    composite = {
        "observed": observed_mean,
        "baseline": baseline_mean,
        "minimum": minimum_mean,
        "passed": observed_mean is not None and minimum_mean is not None and observed_mean >= minimum_mean,
    }
    axis_checks = {}
    for path, value in axes.items():
        base = baseline_axes.get(path)
        minimum = base - (1 / 45) if base is not None else None
        axis_checks[path] = {"observed": value, "baseline": base, "minimum": minimum, "passed": isinstance(value, (int, float)) and minimum is not None and value >= minimum}
    axis_regression = {"checks": axis_checks, "passed": bool(axis_checks) and all(item["passed"] for item in axis_checks.values())}

    baseline_labels = (budget.get("baseline_metrics", {}) or {}).get("per_label_support_and_f1", {})
    floor_checks = (score.get("floor_gate", {}) or {}).get("checks", {})
    label_checks: dict[str, Any] = {}
    for family, labels in baseline_labels.items():
        if not isinstance(labels, Mapping):
            continue
        observed_labels = quality.get(family, {}).get("labels", {})
        for label, data in labels.items():
            support, base_f1 = (data + [None, None])[:2] if isinstance(data, list) else (None, None)
            path = f"all.{family}.labels.{label}.f1"
            observed_f1 = observed_labels.get(label, {}).get("f1")
            floor = floor_checks.get(path)
            if support == 0:
                label_checks[path] = {"support": support, "status": "unmeasured", "passed": True}
                continue
            floor_passed = floor.get("passed") if isinstance(floor, Mapping) else False
            if support == 1:
                label_checks[path] = {"support": support, "observed": observed_f1, "baseline": base_f1, "status": "support_one_floor", "passed": bool(floor_passed)}
            else:
                minimum = float(base_f1) - 0.10 if isinstance(base_f1, (int, float)) else None
                label_checks[path] = {"support": support, "observed": observed_f1, "baseline": base_f1, "minimum": minimum, "passed": isinstance(observed_f1, (int, float)) and minimum is not None and observed_f1 >= minimum and bool(floor_passed)}
    per_label = {"checks": label_checks, "passed": bool(label_checks) and all(item["passed"] for item in label_checks.values())}
    return {"improvement_composite": composite, "axis_regression": axis_regression, "per_label_regression": per_label}


def _durable_report(result: Mapping[str, Any], score: Mapping[str, Any], candidate: Mapping[str, Any], budget_path: Path) -> dict[str, Any]:
    ledger = result.get("ledger", {})
    cost_per_1000 = (Decimal(str(ledger.get("spend_usd", "0"))) * Decimal(1000) / Decimal(45))
    latencies = [int(item) for item in result.get("complete_result_latencies_ms", []) if isinstance(item, int)]
    p95 = sorted(latencies)[min(len(latencies) - 1, math.ceil(len(latencies) * .95) - 1)] if latencies else None
    hard_cap = Decimal(str(candidate.get("maximum_spend_usd", "Infinity")))
    latency_limit_ms = 180_000
    regular_input_value = candidate.get("regular_input_usd_per_million")
    regular_output_value = candidate.get("regular_output_usd_per_million")
    regular_input = Decimal(str(regular_input_value or "0"))
    regular_output = Decimal(str(regular_output_value or "0"))
    regular_cost = (regular_input * int(ledger.get("input_tokens", 0)) + regular_output * int(ledger.get("output_tokens", 0))) / Decimal(1_000_000)
    budget = _read_json(budget_path)
    quality_gates = _quality_release_gates(score, budget)
    candidate_cost_cap = hard_cap * Decimal(1000) / Decimal(45) if hard_cap.is_finite() else Decimal("Infinity")
    budget_document = _read_json(budget_path)
    report_schema = "u18-r98-direct-control-fallback-report-v1" if str(budget_document.get("schema_version", "")).startswith("u18-r98-") else "u18-openrouter-two-role-report-v1"
    return {"schema_version": report_schema, "pilot_id": _pilot_id(budget_document), "candidate_id": candidate["candidate_id"], "model": candidate["model"], "request_provider": candidate["provider"], "response_provider": candidate.get("response_provider"), "endpoint_tag": candidate.get("endpoint_tag"), "service_tier": candidate.get("service_tier"), "transport_kind": candidate.get("transport_kind", "openrouter"), "endpoint_aliases": candidate.get("endpoint_aliases", []), "quantization": candidate.get("quantization"), "budget_sha256": hashlib.sha256(budget_path.read_bytes()).hexdigest(), "source_posts": 45, "post_brand_rows": 45, "initial_logical_requests": int(ledger.get("logical_requests", 0)), "failure_code": result.get("failure_code"), "measurements": result.get("measurements", []), "ledger": ledger, "cost_per_1000_source_posts_usd": str(cost_per_1000), "regular_rate_cost_usd": str(regular_cost), "regular_rate_available": regular_input_value is not None and regular_output_value is not None, "complete_result_latency_p95_ms": p95, "gates": {"coverage_100_percent": score.get("coverage") == 1.0, "cost_within_candidate_cap": Decimal(str(ledger.get("spend_usd", "0"))) <= hard_cap, "cost_per_1000_within_candidate_cap": cost_per_1000 <= candidate_cost_cap, "complete_result_latency_p95_within_180s": p95 is not None and p95 <= latency_limit_ms, "quality_floors": score.get("floor_gate", {}), **quality_gates}, "score": score, "raw_outputs_persisted_under": "private responses directory only"}


def direct_deepseek_anthropic_client_factory(candidate: Mapping[str, Any] | None = None) -> Any:
    """Build the production direct DeepSeek Anthropic-compatible client."""
    if candidate is not None and candidate.get("route") not in {None, "https://api.deepseek.com/anthropic/v1/messages"}:
        raise PilotInputError("direct DeepSeek candidate route mismatch")
    from x_monitor.reattribute import build_anthropic_client_from_env

    client = build_anthropic_client_from_env()
    if client is None:
        raise PilotInputError("direct DeepSeek client unavailable")
    expected_base = "https://api.deepseek.com/anthropic"
    if str(getattr(client, "_base_url", "")).rstrip("/") != expected_base:
        raise PilotInputError("direct DeepSeek client route mismatch")
    return client


def _client_factory(candidate: Mapping[str, Any]) -> Any:
    if candidate.get("transport_kind") == "direct_deepseek_anthropic":
        # This branch is never reached by dry-run, preflight,
        # catalog-preflight, score, or replay.
        return direct_deepseek_anthropic_client_factory(candidate)
    from x_monitor.openrouter import OpenRouterChatCompletionsClient
    request_quantizations = candidate.get("request_quantizations")
    if request_quantizations is None and candidate.get("quantization") not in {None, "unknown", "undisclosed"}:
        request_quantizations = [candidate["quantization"]]
    return OpenRouterChatCompletionsClient.from_config(
        model=candidate["model"], provider=candidate["provider"],
        response_provider=candidate.get("response_provider"), response_model=candidate.get("response_model"),
        data_collection=candidate["data_collection"], zdr=bool(candidate["zdr"]),
        reasoning_enabled=candidate.get("reasoning_enabled"),
        quantizations=request_quantizations,
        endpoint_tag=candidate.get("endpoint_tag"),
        service_tier=candidate.get("service_tier"),
        max_input_price=float(candidate["max_input_price"]) if candidate.get("max_input_price") is not None else None,
        max_output_price=float(candidate["max_output_price"]) if candidate.get("max_output_price") is not None else None,
    )


def _report_passes(report: Mapping[str, Any]) -> bool:
    gates = report.get("gates")
    if not isinstance(gates, Mapping):
        return False
    required = (
        "coverage_100_percent", "cost_within_candidate_cap",
        "cost_per_1000_within_candidate_cap", "complete_result_latency_p95_within_180s",
        "quality_floors", "improvement_composite", "axis_regression", "per_label_regression",
    )
    for name in required:
        value = gates.get(name)
        if isinstance(value, Mapping):
            value = value.get("passed")
        if value is not True:
            return False
    return True


def _adaptive_candidates(candidates: Sequence[Mapping[str, Any]], budget: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    plan = budget.get("adaptive_execution")
    if not isinstance(plan, Mapping):
        return tuple(dict(candidate) for candidate in candidates)
    by_id = {str(candidate["candidate_id"]): dict(candidate) for candidate in candidates}
    execution = plan.get("execution_order")
    selection = plan.get("selection_order")
    if not isinstance(execution, list) or not isinstance(selection, list):
        raise PilotInputError("adaptive ladder lacks frozen execution and selection order")
    if not set(by_id) <= set(execution) or not set(by_id) <= set(selection):
        raise PilotInputError("adaptive ladder order does not match candidates")
    return tuple(by_id[candidate_id] for candidate_id in execution if candidate_id in by_id)


def _adaptive_decision(reports: Mapping[str, Mapping[str, Any]], selection_order: Sequence[str], attempted: Sequence[str]) -> dict[str, Any]:
    """Return the frozen ladder decision from terminal candidate reports."""
    selected: str | None = None
    for candidate_id in selection_order:
        if candidate_id in reports and _report_passes(reports[candidate_id]):
            rank = selection_order.index(candidate_id)
            if all(item in reports for item in selection_order[:rank]):
                selected = candidate_id
                break
    skipped = [candidate_id for candidate_id in selection_order if candidate_id not in reports]
    return {
        "selected_candidate_id": selected,
        "attempted_candidate_ids": list(attempted),
        "skipped_candidate_ids": skipped if selected is not None else [],
        "skipped_reason": "more_expensive_than_selected" if selected is not None and skipped else None,
        "status": "selected" if selected is not None else "no-selection",
    }


def _adaptive_catalog_preflight(candidates: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], set[str]]:
    """Attest routes independently so one catalog mismatch blocks one rung."""
    evidence: list[dict[str, Any]] = []
    blocked: set[str] = set()
    for candidate in candidates:
        candidate_id = str(candidate["candidate_id"])
        try:
            rows = catalog_preflight([candidate])
            evidence.extend(dict(row, status="passed") for row in rows)
        except PilotInputError as exc:
            blocked.add(candidate_id)
            evidence.append({
                "candidate_id": candidate_id,
                "provider": candidate.get("response_provider"),
                "endpoint_tag": candidate.get("endpoint_tag"),
                "status": "blocked",
                "failure_code": str(exc)[:200],
                "checks": {},
            })
    return evidence, blocked


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("dry-run", "preflight", "catalog-preflight", "frozen-run", "adaptive-ladder", "replay", "score", "report"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--private-dir", type=Path, default=None)
    parser.add_argument("--budget", type=Path, required=True)
    parser.add_argument("--max-transport-attempts-per-role", type=int, default=PILOT_MAX_TRANSPORT_ATTEMPTS)
    parser.add_argument("--candidate-id", action="append", help="Run only this frozen candidate; repeat for a subset resume")
    args = parser.parse_args(argv)
    if args.mode in {"dry-run", "preflight"}:
        result = preflight(args.manifest, args.reference, args.budget)
        if args.mode == "dry-run":
            result["transport"] = "disabled"
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    caps, candidates, max_attempts = load_budget(args.budget)
    if args.candidate_id:
        if args.mode == "adaptive-ladder":
            parser.error("adaptive-ladder requires the complete frozen candidate set")
        selected_ids = set(args.candidate_id)
        known_ids = {candidate["candidate_id"] for candidate in candidates}
        unknown_ids = selected_ids - known_ids
        if unknown_ids:
            parser.error(f"unknown frozen candidate: {','.join(sorted(unknown_ids))}")
        candidates_to_run = tuple(candidate for candidate in candidates if candidate["candidate_id"] in selected_ids)
    else:
        candidates_to_run = candidates
    budget_document = _read_json(args.budget)
    private_dir = args.private_dir or (DEFAULT_R98_PRIVATE_DIR if str(budget_document.get("schema_version", "")).startswith("u18-r98-") else DEFAULT_PRIVATE_DIR)
    if args.mode == "frozen-run" and isinstance(budget_document.get("adaptive_execution"), Mapping):
        parser.error("R98 adaptive budget requires adaptive-ladder mode")
    floor_values = budget_document.get("floors") or (budget_document.get("quality_floors", {}) or {}).get("floors", {})
    unsupported_floor_paths = (budget_document.get("baseline_metrics", {}).get("per_label_support_and_f1", {}).get("unsupported", []))
    manifest = _read_json(args.manifest)
    reference = _read_json(args.reference)
    packets, local = build_public_packets(manifest)
    if args.mode == "catalog-preflight":
        print(json.dumps({"endpoints": catalog_preflight(candidates)}, ensure_ascii=False, sort_keys=True))
        return 0
    if args.mode in {"frozen-run", "adaptive-ladder"} and any(candidate.get("transport_kind", "openrouter") == "openrouter" for candidate in candidates_to_run) and not os.environ.get("OPENROUTER_API_KEY"):
        parser.error(f"{args.mode} requires OPENROUTER_API_KEY; use replay for provider-free execution")
    if args.mode in {"frozen-run", "adaptive-ladder", "replay"}:
        all_reports = []
        global_ledger = BudgetLedger(caps)
        run_candidates = _adaptive_candidates(candidates_to_run, budget_document) if args.mode == "adaptive-ladder" else tuple(candidates_to_run)
        catalog_blocked: set[str] = set()
        if args.mode == "frozen-run":
            endpoint_receipt = catalog_preflight(candidates)
            _write_json(private_dir / "catalog-preflight.json", {"endpoints": endpoint_receipt})
        elif args.mode == "adaptive-ladder":
            endpoint_receipt, catalog_blocked = _adaptive_catalog_preflight(run_candidates)
            _write_json(private_dir / "catalog-preflight.json", {
                "pilot_id": _pilot_id(budget_document),
                "endpoints": endpoint_receipt,
                "blocked_candidate_ids": sorted(catalog_blocked),
            })
        selected_set = {str(candidate["candidate_id"]) for candidate in candidates_to_run}
        selection_order = [str(value) for value in (budget_document.get("adaptive_execution", {}) or {}).get("selection_order", []) if str(value) in selected_set] if args.mode == "adaptive-ladder" else []
        reports_by_id: dict[str, dict[str, Any]] = {}
        for candidate in run_candidates:
            ledger_start = global_ledger.snapshot()
            if candidate["candidate_id"] in catalog_blocked:
                result = {
                    "candidate_id": candidate["candidate_id"],
                    "batches": [],
                    "measurements": [],
                    "complete_result_latencies_ms": [],
                    "ledger": global_ledger.delta(ledger_start),
                    "failure_code": "catalog_preflight_blocked",
                }
            else:
                pilot = TwoRolePilot(candidate, private_dir=private_dir, caps=caps, ledger=global_ledger, max_transport_attempts_per_role=min(args.max_transport_attempts_per_role, max_attempts), endpoint_aliases=candidate.get("endpoint_aliases"))
                try:
                    result = pilot.run_candidate(packets, _client_factory if args.mode in {"frozen-run", "adaptive-ladder"} else None, replay=args.mode == "replay")
                except (OpenRouterPermanentError, AnthropicCompatiblePermanentError, PilotInputError) as exc:
                    result = {
                        "candidate_id": candidate["candidate_id"],
                        "batches": [],
                        "measurements": list(pilot.measurements),
                        "complete_result_latencies_ms": [],
                        "ledger": global_ledger.delta(ledger_start),
                        "failure_code": str(exc),
                    }
            score = score_candidate(result, reference, local, floor_values, unsupported_floor_paths)
            report = _durable_report(result, score, candidate, args.budget)
            _write_json(_result_path(private_dir, candidate["candidate_id"]), result)
            _write_json(_report_path(private_dir, candidate["candidate_id"]), report)
            all_reports.append(report)
            reports_by_id[candidate["candidate_id"]] = report
            if args.mode == "adaptive-ladder":
                attempted = [str(item["candidate_id"]) for item in run_candidates if item["candidate_id"] in reports_by_id]
                decision = _adaptive_decision(reports_by_id, selection_order, attempted)
                if decision["selected_candidate_id"] is not None:
                    break
        output: dict[str, Any] = {"reports": all_reports}
        if args.mode == "adaptive-ladder":
            attempted = [str(candidate["candidate_id"]) for candidate in run_candidates if candidate["candidate_id"] in reports_by_id]
            output["adaptive_decision"] = _adaptive_decision(reports_by_id, selection_order, attempted)
        print(json.dumps(output, ensure_ascii=False, sort_keys=True))
        return 0
    if args.mode == "score":
        reports = []
        for candidate in candidates_to_run:
            result = _read_json(_result_path(private_dir, candidate["candidate_id"]))
            score = score_candidate(result, reference, local, floor_values, unsupported_floor_paths)
            reports.append(_durable_report(result, score, candidate, args.budget))
        print(json.dumps({"reports": reports}, ensure_ascii=False, sort_keys=True))
        return 0
    if args.mode == "report":
        reports = [_read_json(_report_path(private_dir, candidate["candidate_id"])) for candidate in candidates_to_run]
        print(json.dumps({"reports": reports}, ensure_ascii=False, sort_keys=True))
        return 0
    # Transport construction is deliberately left to an operator integration;
    # this command cannot guess a secret, route, or endpoint.
    parser.error(f"{args.mode} requires an explicit provider/replay integration")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
