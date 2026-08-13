"""Headline-only provider adapter for one validated bilingual JSON response."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from x_monitor.config import HeadlineNarrativeConfig

_NARRATIVE_TYPES = (
    "leader",
    "handoff",
    "contested",
    "coverage_limited",
)
_URL_RE = re.compile(
    r"(?:\b[a-z][a-z0-9+.-]*://|www\.|\b[a-z0-9-]+\.(?:com|net|org)\b)",
    re.IGNORECASE,
)
_MARKUP_RE = re.compile(r"(?:<[^>]*>|\*\*|__|`|^\s*#|\[[^]]+\]\([^)]*\))")
_FORBIDDEN_INPUT_KEYS = frozenset(
    {"raw_text", "post_text", "tweet_text", "url", "urls"}
)


class HeadlineGenerationError(ValueError):
    """Safe failure category; provider bodies and credentials are omitted."""

    def __init__(self, code: str, *, transport_completed: bool = False):
        super().__init__(code)
        self.code = code[:64]
        self.transport_completed = transport_completed


class _OutputContractError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class _GenerationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body_en: str = Field(min_length=12)
    body_zh_hans: str = Field(min_length=8)
    narrative_type: Literal["leader", "handoff", "contested", "coverage_limited"]
    mentioned_brand_keys: list[str] = Field(min_length=1, max_length=2)

    @field_validator("body_en", "body_zh_hans")
    @classmethod
    def _safe_plain_text(cls, value: str) -> str:
        if value != value.strip() or "\n" in value or "\r" in value:
            raise ValueError("headline bodies must be one trimmed line")
        if _URL_RE.search(value) or _MARKUP_RE.search(value):
            raise ValueError("headline bodies cannot contain URLs or markup")
        if any(unicodedata.category(character) in {"Cc", "Cf"} for character in value):
            raise ValueError("headline bodies cannot contain controls")
        return value

    @field_validator("body_zh_hans")
    @classmethod
    def _requires_simplified_chinese_prose(cls, value: str) -> str:
        cjk_count = sum("\u4e00" <= character <= "\u9fff" for character in value)
        if cjk_count < 4:
            raise ValueError("zh-Hans body must contain Chinese prose")
        return value

    @field_validator("mentioned_brand_keys")
    @classmethod
    def _unique_brand_keys(cls, value: list[str]) -> list[str]:
        if any(not key or key != key.strip() for key in value):
            raise ValueError("mentioned brand keys must be nonempty")
        if len(value) != len(set(value)):
            raise ValueError("mentioned brand keys must be unique")
        return value


@dataclass(frozen=True, slots=True)
class GeneratedTrendNarrative:
    body_en: str
    body_zh_hans: str
    narrative_type: str
    mentioned_brand_keys: tuple[str, ...]
    semantic_fingerprint: str
    output_hash: str
    provider: str
    provider_host: str
    model_name: str
    prompt_version: str
    publication_epoch: int
    input_tokens: int
    output_tokens: int
    latency_ms: int


def generation_fingerprint(
    facts: dict[str, Any],
    config: HeadlineNarrativeConfig,
) -> str:
    contract = {
        "semantic_facts": _semantic_fact_projection(facts),
        "provider": config.provider,
        "base_url": config.base_url,
        "model": config.model,
        "prompt_version": config.prompt_version,
        "publication_epoch": config.publication_epoch,
    }
    encoded = json.dumps(
        contract,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _semantic_fact_projection(facts: dict[str, Any]) -> dict[str, Any]:
    """Exclude exact counts/timestamps that do not change the prose contract."""

    def brand_identity(field: str) -> dict[str, str] | None:
        value = facts.get(field)
        if not isinstance(value, dict) or not value.get("key"):
            return None
        return {
            "key": str(value["key"]),
            "name_en": str(value.get("display_name_en") or value["key"]),
            "name_zh_hans": str(value.get("display_name_zh_hans") or value["key"]),
        }

    return {
        "schema_version": facts.get("schema_version"),
        "window_days": facts.get("window_days"),
        "narrative_type": facts.get("narrative_type"),
        "coverage_state": (facts.get("coverage") or {}).get("state"),
        "primary_brand": brand_identity("primary_brand"),
        "secondary_brand": brand_identity("secondary_brand"),
        "earlier_leader": (
            brand_identity("earlier_leader")
            if facts.get("narrative_type") == "handoff"
            else None
        ),
        "momentum": facts.get("momentum"),
    }


def generate_trend_narrative(
    facts: dict[str, Any],
    config: HeadlineNarrativeConfig,
    *,
    api_key: str | None = None,
    client_factory: Callable[..., Any] | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> GeneratedTrendNarrative:
    """Make exactly one provider request and accept both locales or neither."""
    _validate_fact_input(facts)
    expected_brands = _expected_brands(facts)
    credential = api_key or _resolve_provider_credential(config)
    if not credential:
        raise HeadlineGenerationError("headline_credential_unavailable")
    factory = client_factory or _anthropic_client
    client = factory(
        api_key=credential,
        base_url=config.base_url,
        timeout=float(config.timeout_seconds),
        max_retries=0,
    )
    request = _request_payload(facts, config, expected_brands)
    started = monotonic()
    try:
        message = client.messages.create(**request)
    except Exception as exc:
        raise HeadlineGenerationError("headline_provider_request_failed") from exc
    elapsed_ms = max(0, round((monotonic() - started) * 1000))
    try:
        raw = _message_text(message)
    except ValueError:
        raise HeadlineGenerationError(
            "headline_output_text_missing", transport_completed=True
        ) from None
    try:
        raw = _normalize_json_envelope(raw)
    except ValueError:
        raise HeadlineGenerationError(
            "headline_output_envelope_invalid", transport_completed=True
        ) from None
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        raise HeadlineGenerationError(
            "headline_output_json_invalid", transport_completed=True
        ) from None
    try:
        output = _GenerationOutput.model_validate(parsed)
    except ValidationError:
        raise HeadlineGenerationError(
            "headline_output_schema_invalid", transport_completed=True
        ) from None
    try:
        _validate_output(output, facts, expected_brands, config)
    except _OutputContractError as exc:
        raise HeadlineGenerationError(exc.code, transport_completed=True) from None

    canonical_output = json.dumps(
        output.model_dump(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    usage = getattr(message, "usage", None)
    return GeneratedTrendNarrative(
        body_en=output.body_en,
        body_zh_hans=output.body_zh_hans,
        narrative_type=output.narrative_type,
        mentioned_brand_keys=tuple(output.mentioned_brand_keys),
        semantic_fingerprint=generation_fingerprint(facts, config),
        output_hash=hashlib.sha256(canonical_output.encode("utf-8")).hexdigest(),
        provider=config.provider,
        provider_host=urlsplit(config.base_url).hostname or "",
        model_name=config.model,
        prompt_version=config.prompt_version,
        publication_epoch=config.publication_epoch,
        input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
        output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        latency_ms=elapsed_ms,
    )


def _anthropic_client(**kwargs):
    import anthropic

    return anthropic.Anthropic(**kwargs)


def _resolve_provider_credential(config: HeadlineNarrativeConfig) -> str | None:
    """Resolve the credential for the pinned headline provider route."""
    if config.provider == "deepseek":
        return os.environ.get("DEEPSEEK_API_KEY") or os.environ.get(
            "DEEPSEEK_API_TOKEN"
        )
    if config.provider == "minimax":
        return os.environ.get("MINIMAX_API_TOKEN")
    return os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_KEY")


def _request_payload(
    facts: dict[str, Any],
    config: HeadlineNarrativeConfig,
    expected_brands: list[dict[str, str]],
) -> dict[str, Any]:
    brand_contract = [brand["key"] for brand in expected_brands]
    system = (
        "You write a concise market-trend headline from a closed aggregate fact "
        "packet. Return raw JSON with exactly four keys: body_en, body_zh_hans, "
        "narrative_type, and mentioned_brand_keys. Do not add a code fence or "
        "any other key. Write natural English and Simplified Chinese in one "
        "sentence each. Mention exactly the supplied brands and narrative type. "
        "Do not use digits, URLs, markup, causal claims, or facts outside the "
        "packet."
    )
    output_contract = {
        "body_en": "one English sentence",
        "body_zh_hans": "one Simplified Chinese sentence",
        "narrative_type": facts["narrative_type"],
        "mentioned_brand_keys": brand_contract,
    }
    user = (
        "Required output contract: "
        f"{json.dumps(output_contract, ensure_ascii=False, separators=(',', ':'))}\n"
        "Allowed brand identities: "
        f"{json.dumps(expected_brands, ensure_ascii=False, separators=(',', ':'))}\n"
        "Aggregate semantic facts: "
        f"{json.dumps(_provider_fact_projection(facts), ensure_ascii=False, sort_keys=True, separators=(',', ':'))}"
    )
    return {
        "model": config.model,
        "max_tokens": 320,
        "temperature": 0,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }


def _message_text(message: Any) -> str:
    parts = [
        str(block.text)
        for block in getattr(message, "content", [])
        if getattr(block, "text", None) is not None
    ]
    if not parts:
        raise ValueError("provider returned no text block")
    return "".join(parts).strip()


def _provider_fact_projection(facts: dict[str, Any]) -> dict[str, Any]:
    semantic = _semantic_fact_projection(facts)
    return {
        "narrative_type": semantic["narrative_type"],
        "coverage_state": semantic["coverage_state"],
        "primary_brand": semantic["primary_brand"],
        "secondary_brand": semantic["secondary_brand"],
        "earlier_leader": semantic["earlier_leader"],
        "momentum": semantic["momentum"],
    }


def _normalize_json_envelope(raw: str) -> str:
    """Unwrap one complete JSON code fence while keeping parsing strict."""
    stripped = raw.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if (
        len(lines) < 3
        or lines[0].strip().casefold() not in {"```", "```json"}
        or lines[-1].strip() != "```"
    ):
        raise ValueError("invalid JSON code fence")
    return "\n".join(lines[1:-1]).strip()


def _validate_fact_input(facts: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "window_days",
        "as_of",
        "coverage",
        "narrative_type",
        "primary_brand",
        "secondary_brand",
        "earlier_leader",
        "momentum",
    }
    if not isinstance(facts, dict) or not required.issubset(facts):
        raise HeadlineGenerationError("headline_fact_contract_invalid")
    if facts["window_days"] not in {1, 7, 30, 365}:
        raise HeadlineGenerationError("headline_fact_window_invalid")
    if facts["narrative_type"] not in _NARRATIVE_TYPES:
        raise HeadlineGenerationError("headline_fact_type_not_generatable")
    if _contains_forbidden_input_key(facts):
        raise HeadlineGenerationError("headline_fact_payload_not_aggregate_only")


def _contains_forbidden_input_key(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            str(key).casefold() in _FORBIDDEN_INPUT_KEYS
            or _contains_forbidden_input_key(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_input_key(child) for child in value)
    return False


def _expected_brands(facts: dict[str, Any]) -> list[dict[str, str]]:
    values = [facts.get("primary_brand")]
    if facts["narrative_type"] == "contested":
        values.append(facts.get("secondary_brand"))
    elif facts["narrative_type"] == "handoff":
        values.append(facts.get("earlier_leader"))
    brands = [value for value in values if isinstance(value, dict) and value.get("key")]
    if not brands or len(brands) != len(values):
        raise HeadlineGenerationError("headline_fact_brand_contract_invalid")
    return [
        {
            "key": str(brand["key"]),
            "name_en": str(brand.get("display_name_en") or brand["key"]),
            "name_zh_hans": str(brand.get("display_name_zh_hans") or brand["key"]),
        }
        for brand in brands
    ]


def _validate_output(
    output: _GenerationOutput,
    facts: dict[str, Any],
    expected_brands: list[dict[str, str]],
    config: HeadlineNarrativeConfig,
) -> None:
    if output.narrative_type != facts["narrative_type"]:
        raise _OutputContractError("headline_output_type_mismatch")
    expected_keys = [brand["key"] for brand in expected_brands]
    if output.mentioned_brand_keys != expected_keys:
        raise _OutputContractError("headline_output_brand_keys_mismatch")
    if len(output.body_en) > config.max_body_en_chars:
        raise _OutputContractError("headline_output_en_too_long")
    if len(output.body_zh_hans) > config.max_body_zh_hans_chars:
        raise _OutputContractError("headline_output_zh_too_long")
    english_names: set[str] = set()
    chinese_names: set[str] = set()
    for brand in expected_brands:
        brand_english_names = {brand["key"], brand["name_en"]}
        brand_chinese_names = {brand["key"], brand["name_zh_hans"]}
        english_names.update(brand_english_names)
        chinese_names.update(brand_chinese_names)
        if not any(
            _mentions_brand(output.body_en, name) for name in brand_english_names
        ):
            raise _OutputContractError("headline_output_en_brand_missing")
        if not any(
            _mentions_brand(output.body_zh_hans, name) for name in brand_chinese_names
        ):
            raise _OutputContractError("headline_output_zh_brand_missing")
    if _has_unsupported_digits(output.body_en, english_names):
        raise _OutputContractError("headline_output_en_digits")
    if _has_unsupported_digits(output.body_zh_hans, chinese_names):
        raise _OutputContractError("headline_output_zh_digits")
    _reject_unsupported_brand_tokens(output.body_en, english_names)
    _reject_unsupported_brand_tokens(output.body_zh_hans, chinese_names)


def _mentions_brand(body: str, name: str) -> bool:
    if not name:
        return False
    escaped = re.escape(name)
    if name.isascii() and name.isalnum():
        return (
            re.search(
                rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])",
                body,
                re.IGNORECASE,
            )
            is not None
        )
    return name.casefold() in body.casefold()


def _has_unsupported_digits(body: str, allowed_brand_names: set[str]) -> bool:
    remainder = body
    for name in sorted(allowed_brand_names, key=len, reverse=True):
        if any(character.isdigit() for character in name):
            remainder = re.sub(re.escape(name), "", remainder, flags=re.IGNORECASE)
    return any(character.isdigit() for character in remainder)


_COMMON_BRAND_ALIASES = frozenset(
    {
        "anthropic",
        "claude",
        "deepseek",
        "gemini",
        "glm",
        "google",
        "kimi",
        "llama",
        "minimax",
        "mistral",
        "moonshot",
        "openai",
        "qwen",
        "yi",
    }
)


def _reject_unsupported_brand_tokens(
    body: str,
    allowed_brand_names: set[str],
) -> None:
    """Reject recognizable extra brand names without parsing free prose.

    The provider receives a closed fact packet, so a second brand is never
    needed for a valid headline.  Exact aliases catch common unsupported
    brands; the internal-capital check catches novel forms such as OpenAI
    without rejecting ordinary sentence-initial words.
    """
    remainder = body
    for name in sorted(allowed_brand_names, key=len, reverse=True):
        remainder = re.sub(re.escape(name), " ", remainder, flags=re.IGNORECASE)
    for token in re.findall(r"(?<![A-Za-z])[A-Za-z][A-Za-z0-9.-]*", remainder):
        folded = token.casefold().rstrip(".")
        if folded in _COMMON_BRAND_ALIASES:
            raise _OutputContractError("headline_output_extra_brand")
        if re.search(r"[a-z][A-Z]", token):
            raise _OutputContractError("headline_output_extra_brand")
