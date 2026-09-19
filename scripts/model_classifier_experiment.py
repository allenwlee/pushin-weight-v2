"""Bounded Qwen trial of the current two-role fixed-slot classifier contract.

This is an operator tool, not a production classifier.  It only reads the
frozen private source packet, writes an immutable prepared contract, and (when
explicitly invoked) makes the two required OpenRouter calls for each batch.
It deliberately has no retry, fallback, database, or owner-reference path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

# ``python scripts/model_classifier_experiment.py`` otherwise puts only the
# scripts directory on sys.path, while the documented command is run at repo root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from x_monitor.attribution import AnthropicClaudeClient
from x_monitor.openrouter import OpenRouterChatCompletionsClient
from scripts import model_classifier_trial_contract as taxonomy
from scripts.model_task_profiles import ModelTaskProfile, get_profile, profile_manifest
from scripts.u20_translation_synthesis_execute import credential

SCHEMA = "model-classifier-experiment/v1"
# Compatibility aliases for the first frozen Qwen contract and capture tests.
MODEL = "qwen/qwen3.7-flash"
RESPONSE_MODEL = "qwen/qwen3.7-flash-20260727"
PROVIDER = "Alibaba"
INPUT_PRICE_PER_MILLION = 0.03
OUTPUT_PRICE_PER_MILLION = 0.13
MAX_ATTEMPTS = 3
MAX_QWEN_CLASSIFIER_CONFIGS = 6
MAX_TASK_USD = 3.0
MAX_PORTFOLIO_USD = 30.0
MAX_CONCURRENCY = 3
BATCH_SIZE = 5
MAX_TOKENS = 4096
QWEN_MAX_INPUT_REQUEST_BYTES = 32_000
DEEPSEEK_0731_MODEL = "deepseek/deepseek-v4-flash-0731"
DEEPSEEK_V41_DIRECT_MODEL = "deepseek-v4-flash"
DEEPSEEK_V41_RESPONSE_ALIASES = frozenset({"deepseek-v4-flash", "deepseek-flash"})
DEEPSEEK_DIRECT_BASE_URL = "https://api.deepseek.com/anthropic"


def _profile(key: str) -> ModelTaskProfile:
    """Return a classifier-only view of a saved route profile.

    Classifier profiles live here because their response grammar is generated
    from fixed decision slots.  The base profile remains the source of route,
    price, tier, timeout, and accepted parameter facts.
    """
    if key == "qwen_classifier_v1":
        return replace(get_profile("qwen_commentary_v1"), key=key, task="classification")
    if key == "qwen_classifier_v2":
        return replace(get_profile("qwen_commentary_v1"), key=key, task="classification", representation="raw_text")
    if key == "qwen_classifier_v3":
        # The existing v2 Qwen route profile is the saved bounded-thinking
        # variant.  Its prompt style is still caller, unlike translation v3.
        return replace(get_profile("qwen_translation_v2"), key=key, task="classification", representation="raw_text")
    if key == "qwen_classifier_v4":
        return replace(get_profile("qwen_commentary_v1"), key=key, task="classification", representation="raw_text")
    if key == "qwen_classifier_v5":
        return replace(get_profile("qwen_commentary_v1"), key=key, task="classification", representation="raw_text")
    if key == "qwen_classifier_v6":
        return replace(get_profile("qwen_commentary_v1"), key=key, task="classification", representation="raw_text")
    if key == "deepseek_v41_incumbent_classifier_v1":
        # Direct DeepSeek uses the legacy request alias. The provider may report
        # either this alias or ``deepseek-flash``; neither is a pinned checkpoint.
        return ModelTaskProfile(
            key=key, model=DEEPSEEK_V41_DIRECT_MODEL, task="classification",
            provider_only="direct-deepseek-anthropic", provider_name="DeepSeek (direct)",
            endpoint_tag="api.deepseek.com/anthropic", service_tier=None,
            upstream_model="deepseek-flash|deepseek-v4-flash",
            input_usd_per_million=Decimal("0"), output_usd_per_million=Decimal("0"),
            max_output_tokens=4096, timeout_seconds=120, representation="raw_text",
            allowed_parameters=frozenset({"model", "max_tokens", "system", "messages", "thinking"}),
            settings={"thinking": {"type": "disabled"}},
            omitted_parameters=frozenset({"temperature", "top_p", "response_format", "provider"}),
        )
    if key == "deepseek_0731_classifier_current_v1":
        # Reuse only route facts established by the pinned 0731 runtime
        # acceptance harness; classifier response grammar remains local.
        return ModelTaskProfile(
            key=key, model=DEEPSEEK_0731_MODEL, task="classification",
            provider_only="deepinfra/fp8", provider_name="DeepInfra", endpoint_tag="deepinfra/fp8",
            service_tier=None, upstream_model="deepseek/deepseek-v4-flash-20260731",
            input_usd_per_million=Decimal("0.06"), output_usd_per_million=Decimal("0.18"),
            max_output_tokens=6000, timeout_seconds=180, representation="raw_text",
            allowed_parameters=frozenset({"reasoning", "max_tokens", "response_format", "temperature", "top_p", "seed"}),
            settings={"reasoning": {"enabled": False, "exclude": True}, "temperature": 1.0, "top_p": 1.0, "seed": 42},
            omitted_parameters=frozenset({"presence_penalty", "structured_outputs", "include_reasoning"}),
        )
    if key == "gemini_flex_classifier_v1":
        return replace(get_profile("gemini_flex_commentary_v1"), key=key, task="classification")
    if key == "gemini_flex_classifier_v2":
        # v1 transferred labels across multiple targets and made one
        # content/brand availability contradiction. v2 isolates a source and
        # restores explicit independent-axis/state checks without changing the
        # proven Flex route, schema, or disabled-thinking setting.
        return replace(get_profile("gemini_flex_commentary_v1"), key=key, task="classification")
    raise ValueError("unknown frozen classifier profile: " + key)


def _base_profile_key(key: str) -> str:
    return {
        "qwen_classifier_v1": "qwen_commentary_v1",
        "qwen_classifier_v2": "qwen_commentary_v1",
        "qwen_classifier_v3": "qwen_translation_v2",
        "qwen_classifier_v4": "qwen_commentary_v1",
        "qwen_classifier_v5": "qwen_commentary_v1",
        "qwen_classifier_v6": "qwen_commentary_v1",
        "deepseek_v41_incumbent_classifier_v1": "u20_direct_deepseek_v41_incumbent",
        "deepseek_0731_classifier_current_v1": "runtime_0731_deepinfra_fp8",
        "gemini_flex_classifier_v1": "gemini_flex_commentary_v1",
        "gemini_flex_classifier_v2": "gemini_flex_commentary_v1",
    }[key]


def _configuration_cap(profile: ModelTaskProfile) -> int:
    """Exception 29 extends only Qwen classifier configuration selection."""
    return MAX_QWEN_CLASSIFIER_CONFIGS if profile.model == MODEL else MAX_ATTEMPTS


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(_json(value)).hexdigest()


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@contextmanager
def _lock(path: Path):
    import fcntl
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("classifier portfolio is already running") from exc
        yield


def _source_rows(packet: dict[str, Any], suite: str) -> list[dict[str, Any]]:
    key = {"smoke": "smoke_8_source_post_ids", "diagnostic": "diagnostic_24_source_post_ids", "regression": "regression_90_source_post_ids"}.get(suite)
    if key is None:
        raise ValueError("suite must be smoke, diagnostic, or regression")
    wanted = packet.get("suites", {}).get(key)
    rows = packet.get("rows")
    if not isinstance(wanted, list) or not isinstance(rows, list):
        raise ValueError("invalid frozen classifier source packet")
    by_id = {row.get("trial_id"): row for row in rows if isinstance(row, dict)}
    if len(by_id) != len(rows) or any(identifier not in by_id for identifier in wanted):
        raise ValueError("frozen suite does not have exactly one source row per ID")
    return [by_id[identifier] for identifier in wanted]


def _tweet(row: dict[str, Any]) -> dict[str, Any]:
    source = row.get("source_packet")
    if not isinstance(source, dict):
        raise ValueError("source packet missing")
    text = source.get("text", source.get("source_text"))
    context = source.get("context", [])
    affiliations = source.get("affiliations", source.get("author_affiliations", []))
    brands = row.get("target_brand_ids", source.get("brand_ids"))
    if not isinstance(text, str) or not isinstance(context, (list, dict)) or not isinstance(affiliations, list) or not isinstance(brands, list) or not brands:
        raise ValueError("source packet has invalid visible evidence")
    # IDs are local adapter inputs only; the selected slot payload never emits
    # them to the provider.  Do not substitute translations or inferred facts.
    return {"tweet_id": str(row["trial_id"]), "source_text": text, "context": context,
            "author_affiliations": affiliations, "brand_ids": brands,
            "source_language": str(row.get("source_language", source.get("source_language", "")))}


def _slots(batch: list[dict[str, Any]]) -> tuple[dict[str, tuple[str, str]], dict[str, str], dict[str, Any]]:
    decisions: dict[str, tuple[str, str]] = {}; posts: dict[str, str] = {}; cases: dict[str, Any] = {}
    for post_number, tweet in enumerate(batch, 1):
        post_slot = f"P{post_number:02d}"; posts[post_slot] = tweet["tweet_id"]
        decision_slots = {}
        for brand_id in tweet["brand_ids"]:
            slot = f"D{len(decisions) + 1:02d}"; decisions[slot] = (tweet["tweet_id"], brand_id); decision_slots[slot] = brand_id
        # Deliberately omit trial/case/tweet identities from the provider wire.
        cases[post_slot] = {"brand_decision_slots": decision_slots, "evidence": {key: tweet[key] for key in ("source_language", "source_text", "context", "author_affiliations")}}
    return decisions, posts, {"tracked_brands": taxonomy.compact_catalog(), "cases": cases}


def _prompt(role: str, profile: ModelTaskProfile) -> str:
    prompt = taxonomy.CONTENT_PROMPT if role == "content" else taxonomy.BRAND_PROMPT
    axis_check = ""
    if profile.key in {"qwen_classifier_v2", "qwen_classifier_v3", "qwen_classifier_v4", "qwen_classifier_v5", "qwen_classifier_v6", "deepseek_v41_incumbent_classifier_v1", "gemini_flex_classifier_v2"}:
        if role == "content":
            axis_check = """

INDEPENDENT-AXIS CHECK:
- Evaluate every post type independently. A broad reporting label never excludes a separately supported
  opinion, business, research, result, event, or opportunity label.
- Evaluate every Audience Topic independently after post types. If visible evidence says local/self-hosted
  operation, cost/performance, openness, distillation, evaluation, agents/tools, or API/developer surface,
  include every matching topic; use none only when none match.
"""
        else:
            axis_check = """

STATE CONSISTENCY CHECK (perform this before emitting every D slot):
1. Select geopolitical_modes independently from product labels and sentiment.
2. If geopolitical_modes is ["unavailable"], set both country stances to "unknown".
3. If geopolitical_modes does not include "nationalism", set both country stances to "none". This applies
   to ["none"], ["reporting"], ["framework"], and ["reporting","framework"].
4. Only if geopolitical_modes includes "nationalism" may a country stance be mild_pro, pro,
   constructive_critical, anti, or mixed. A country without a directional judgment remains "none".
5. Do not use "unknown" for an assessable non-nationalism judgment.
"""
        prompt += axis_check
    if profile.key == "gemini_flex_classifier_v2":
        if role == "brand_interpretation":
            prompt += """

DIRECT EVIDENCE AVAILABILITY CHECK:
- Mark geopolitical_modes ["unavailable"] only when all supplied source text and context lack
  brand-specific evidence. A named product vulnerability, behavior, version, use, complaint, release,
  or comparison is assessable evidence; choose its labels and non-unavailable state from that evidence.
- Do not transfer a factual claim, role, sentiment, product feature, or national stance between listed
  brands. Re-check the visible name and surrounding words for every D slot before emitting it.
"""
        else:
            prompt += """

BRAND-BOUND CHECK:
- Re-check every D slot against its own visible brand evidence. A named company or product elsewhere in
  the same source is not evidence for this D slot. Do not use a post-level roundup to copy a personnel,
  business, release, or opinion label across brands.
"""
    if profile.key == "qwen_classifier_v3":
        prompt = prompt.split("FIXED OUTPUT MAP:", 1)[0] + axis_check + _dense_output_contract(role)
    elif profile.key in {"qwen_classifier_v4", "qwen_classifier_v5"}:
        prompt = prompt.split("FIXED OUTPUT MAP:", 1)[0] + axis_check + _bit_output_contract(role)
    elif profile.key in {"qwen_classifier_v6", "deepseek_v41_incumbent_classifier_v1"}:
        # The semantic definitions remain the canonical U18A rules.  Replace
        # only its legacy output map with one short, named-field contract.
        prompt = prompt.split("FIXED OUTPUT MAP:", 1)[0] + axis_check + _named_output_contract(role)
    return prompt


def _dense_output_contract(role: str) -> str:
    """Ask Qwen to decide every axis instead of emitting a sparse label list."""
    if role == "content":
        return f"""
FIXED DENSE OUTPUT MAP:
- Return one JSON object with exactly decisions, post_promotion_flags, and promoted_subjects.
- For each supplied D slot, decisions[slot] has exactly outcome, post_type_flags, audience_topic_flags.
- post_type_flags is an object with every key exactly once: {', '.join(taxonomy.POST_TYPES)}. Every value is
  a JSON boolean. audience_topic_flags is an object with every key exactly once: {', '.join(taxonomy.TOPICS)}.
  Every value is a JSON boolean. Evaluate every key independently before output.
- For each supplied P slot, post_promotion_flags[slot] has every key exactly once: {', '.join(taxonomy.PROMOTIONS)};
  every value is a JSON boolean. promoted_subjects[slot] is an array; each subject has exactly name, handle,
  domain, account_handle, evidence, with nonempty strings for name/evidence and null or a nonempty string
  for each other field.
- A classified decision has at least one true post_type flag. A context_missing decision has all post_type
  flags false and only unavailable true in audience_topic_flags. For any assessed decision, exactly one of
  none and unavailable is true only when no substantive topic applies.
- Return no Markdown, case IDs, tweet IDs, brand IDs, explanations, or extra keys.
"""
    return f"""
FIXED DENSE OUTPUT MAP:
- Return one JSON object with exactly decisions.
- For each supplied D slot, decisions[slot] has exactly product_label_flags, sentiment,
  geopolitical_mode_flags, china_national_stance, us_national_stance.
- product_label_flags has every key exactly once: {', '.join(taxonomy.PRODUCT_LABELS)}. geopolitical_mode_flags
  has every key exactly once: {', '.join(taxonomy.GEO)}. Every flag is a JSON boolean. Evaluate every key
  independently before output. sentiment and the two country stances use their existing exact enum spellings.
- `none` and `unavailable` are exclusive in their respective flag maps. If nationalism is false, both
  country stances must be none. If unavailable is true, both country stances must be unknown. Directional
  country stances require nationalism=true.
- Return no Markdown, case IDs, tweet IDs, brand IDs, explanations, or extra keys.
"""


def _bit_output_contract(role: str) -> str:
    """A compact exhaustive shape that avoids sparse arrays and dense-map drift."""
    describe = lambda keys: 'a string of "0" and "1" characters, in this exact order: ' + ", ".join(keys)
    topics = tuple(key for key in taxonomy.TOPICS if key != "none")
    promotions = tuple(key for key in taxonomy.PROMOTIONS if key != "none")
    products = tuple(key for key in taxonomy.PRODUCT_LABELS if key != "none")
    geo = ("reporting", "framework", "unavailable")
    if role == "content":
        return f"""
FIXED BIT-VECTOR OUTPUT MAP:
- Return one JSON object with exactly decisions, post_promotion_bits, and promoted_subjects.
- decisions has exactly the supplied D slot keys. Each value has exactly outcome, post_type_bits, audience_topic_bits.
- post_type_bits is {describe(taxonomy.POST_TYPES)}. audience_topic_bits is {describe(topics)}.
- post_promotion_bits has exactly the supplied P slot keys; each value is {describe(promotions)}.
- promoted_subjects has exactly the supplied P slot keys. Each subject has exactly name, handle, domain,
  account_handle, evidence, with nonempty name/evidence and null or nonempty strings for other fields.
- A classified result needs a 1 in post_type_bits. A context_missing result has all-zero post_type_bits and
  exactly the unavailable Audience Topic bit set. A zero audience_topic_bits vector means ["none"]
  deterministically; this is an encoding rule, not permission to omit an axis. An unavailable bit cannot
  coexist with another 1.
- Return no Markdown, case IDs, tweet IDs, brand IDs, explanations, or extra keys.
"""
    return f"""
FIXED BIT-VECTOR OUTPUT MAP:
- Return one JSON object with exactly decisions. decisions has exactly the supplied D slot keys.
- Each decision has exactly product_label_bits, sentiment, geopolitical_mode_bits, nationalism.
- product_label_bits is {describe(products)}. A zero vector means ["none"] deterministically.
  geopolitical_mode_bits is {describe(geo)}. A zero vector means ["none"] deterministically.
- nationalism is either null or an object with exactly china, us, other_nation. china and us use the existing
  country-stance enum; other_nation is a JSON boolean. null means nationalism is absent and both country
  stances are deterministically none. The object means nationalism is present and contributes its supplied
  China/U.S. stances; use other_nation=true if adopted nationalism concerns a different country.
- unavailable cannot coexist with reporting, framework, or a non-null nationalism object. Unknown country
  stances occur only with unavailable, whose nationalism value must be null.
- Return no Markdown, case IDs, tweet IDs, brand IDs, explanations, or extra keys.
"""


def _named_output_contract(role: str) -> str:
    """Readable canonical fields for the final singleton Qwen shape trial."""
    if role == "content":
        return f"""
FIXED NAMED OUTPUT MAP:
- Return one JSON object with exactly decisions, post_promotions, promoted_subjects.
- decisions has exactly the supplied D slot keys. Each value has exactly outcome, post_types,
  audience_topics. outcome is classified or context_missing; post_types is a nonempty array using only:
  {', '.join(taxonomy.POST_TYPES)}. audience_topics is a nonempty array using only:
  {', '.join(taxonomy.TOPICS)}. Do not encode a label by position, bits, booleans, or an object.
- post_promotions has exactly the supplied P slot keys. Each value is a nonempty array using only:
  {', '.join(taxonomy.PROMOTIONS)}. promoted_subjects has exactly those P keys; each value is an array.
  Every subject has exactly name, handle, domain, account_handle, evidence; name/evidence are nonempty
  strings and the three identifier fields are null or nonempty strings.
- Use ["none"] only when that entire label axis has no substantive value. For context_missing use an
  empty post_types array only if the canonical rules explicitly require it; otherwise follow the supplied
  outcome definition exactly.
- Return no Markdown, case IDs, tweet IDs, brand IDs, explanations, or extra keys.
"""
    return f"""
FIXED NAMED OUTPUT MAP:
- Return one JSON object with exactly decisions. decisions has exactly the supplied D slot keys.
- Each decision has exactly product_labels, sentiment, geopolitical_modes, china_national_stance,
  us_national_stance. product_labels is a nonempty array using only: {', '.join(taxonomy.PRODUCT_LABELS)}.
  geopolitical_modes is a nonempty array using only: {', '.join(taxonomy.GEO)}. sentiment and both country
  stances use their exact existing enum spellings. Do not encode a label by position, bits, booleans, or an object.
- Use ["none"] only when that entire label axis has no substantive value. Apply the state-consistency
  table above before every decision.
- Return no Markdown, case IDs, tweet IDs, brand IDs, explanations, or extra keys.
"""


def _classifier_schema(envelope: dict[str, Any], role: str) -> dict[str, Any]:
    """Strict Gemini schema equivalent to the local fixed-slot parser."""
    slots = [key for case in envelope["cases"].values() for key in case["brand_decision_slots"]]
    posts = list(envelope["cases"])
    array = lambda values: {"type": "array", "items": {"type": "string", "enum": list(values)}, "minItems": 1, "uniqueItems": True}
    if role == "content":
        decision = {"type": "object", "additionalProperties": False, "required": ["outcome", "post_types", "audience_topics"], "properties": {"outcome": {"type": "string", "enum": ["classified", "context_missing"]}, "post_types": array(taxonomy.POST_TYPES), "audience_topics": array(taxonomy.TOPICS)}}
        subject = {"type": "object", "additionalProperties": False, "required": ["name", "handle", "domain", "account_handle", "evidence"], "properties": {"name": {"type": "string", "minLength": 1}, "handle": {"type": ["string", "null"]}, "domain": {"type": ["string", "null"]}, "account_handle": {"type": ["string", "null"]}, "evidence": {"type": "string", "minLength": 1}}}
        return {"type": "object", "additionalProperties": False, "required": ["decisions", "post_promotions", "promoted_subjects"], "properties": {"decisions": {"type": "object", "additionalProperties": False, "required": slots, "properties": {slot: decision for slot in slots}}, "post_promotions": {"type": "object", "additionalProperties": False, "required": posts, "properties": {slot: array(taxonomy.PROMOTIONS) for slot in posts}}, "promoted_subjects": {"type": "object", "additionalProperties": False, "required": posts, "properties": {slot: {"type": "array", "items": subject} for slot in posts}}}}
    decision = {"type": "object", "additionalProperties": False, "required": ["product_labels", "sentiment", "geopolitical_modes", "china_national_stance", "us_national_stance"], "properties": {"product_labels": array(taxonomy.PRODUCT_LABELS), "sentiment": {"type": "string", "enum": list(taxonomy.SENTIMENT)}, "geopolitical_modes": array(taxonomy.GEO), "china_national_stance": {"type": "string", "enum": list(taxonomy.STANCE)}, "us_national_stance": {"type": "string", "enum": list(taxonomy.STANCE)}}}
    return {"type": "object", "additionalProperties": False, "required": ["decisions"], "properties": {"decisions": {"type": "object", "additionalProperties": False, "required": slots, "properties": {slot: decision for slot in slots}}}}


def _request(envelope: dict[str, Any], role: str, profile: ModelTaskProfile) -> dict[str, Any]:
    prompt = _prompt(role, profile)
    slots = [key for case in envelope["cases"].values() for key in case["brand_decision_slots"]]
    prompt = prompt.replace("{{DECISION_SLOT_KEYS}}", ", ".join(slots)).replace("{{POST_SLOT_KEYS}}", ", ".join(envelope["cases"]))
    if profile.key == "deepseek_v41_incumbent_classifier_v1":
        # The verified direct endpoint is Anthropic-compatible. This retains
        # the readable v6 fixed-slot grammar without Qwen bit vectors.
        return {
            "model": profile.model, "max_tokens": profile.max_output_tokens,
            "thinking": {"type": "disabled"}, "system": prompt,
            "messages": [{"role": "user", "content": json.dumps(envelope, ensure_ascii=False, separators=(",", ":"))}],
        }
    request = profile.apply({
        "model": profile.model, "max_tokens": profile.max_output_tokens,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(envelope, ensure_ascii=False, separators=(",", ":"))},
        ],
    })
    if profile.representation == "json_schema":
        request["response_format"] = {"type": "json_schema", "json_schema": {"name": "classifier_slots", "strict": True, "schema": _classifier_schema(envelope, role)}}
    return request


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise ValueError("duplicate JSON key")
        output[key] = value
    return output


def _flags(value: Any, keys: tuple[str, ...]) -> list[str] | None:
    if not isinstance(value, dict) or set(value) != set(keys) or any(not isinstance(value[key], bool) for key in keys):
        return None
    return [key for key in keys if value[key]]


def _bits(value: Any, keys: tuple[str, ...]) -> list[str] | None:
    if not isinstance(value, str) or len(value) != len(keys) or set(value) - {"0", "1"}:
        return None
    return [key for key, bit in zip(keys, value) if bit == "1"]


def _parse_canonical_rows(response: dict[str, Any], decisions: dict[str, tuple[str, str]], posts: dict[str, str], role: str, *, isolate: bool) -> dict[str, Any]:
    if not isolate:
        return taxonomy.parse(response, decisions, posts, role)
    parsed: dict[str, Any] = {}
    for post_slot, tweet in posts.items():
        local_decisions = {slot: item for slot, item in decisions.items() if item[0] == tweet}
        local_posts = {post_slot: tweet}
        if role == "content":
            local_response = {"decisions": {slot: response["decisions"][slot] for slot in local_decisions}, "post_promotions": {post_slot: response["post_promotions"][post_slot]}, "promoted_subjects": {post_slot: response["promoted_subjects"][post_slot]}}
        else:
            local_response = {"decisions": {slot: response["decisions"][slot] for slot in local_decisions}}
        parsed.update(taxonomy.parse(local_response, local_decisions, local_posts, role))
    return parsed


def _parse_bits(response: Any, decisions: dict[str, tuple[str, str]], posts: dict[str, str], role: str, *, normalize_empty: bool = True, isolate: bool = True) -> dict[str, Any]:
    """Decode a complete fixed-order bit vector; never fill missing bits or slots."""
    topics = tuple(key for key in taxonomy.TOPICS if key != "none")
    promotions = tuple(key for key in taxonomy.PROMOTIONS if key != "none")
    products = tuple(key for key in taxonomy.PRODUCT_LABELS if key != "none")
    geo = ("reporting", "framework", "unavailable")
    if role == "content":
        if not isinstance(response, dict) or set(response) != {"decisions", "post_promotion_bits", "promoted_subjects"}:
            return {}
        raw_decisions = response.get("decisions"); raw_promotions = response.get("post_promotion_bits"); subjects = response.get("promoted_subjects")
        if not isinstance(raw_decisions, dict) or set(raw_decisions) != set(decisions) or not isinstance(raw_promotions, dict) or set(raw_promotions) != set(posts) or not isinstance(subjects, dict) or set(subjects) != set(posts):
            return {}
        subjects = dict(subjects)
        if normalize_empty:
            for slot, bits in raw_promotions.items():
                if subjects[slot] is None and _bits(bits, promotions) == []:
                    subjects[slot] = []
        converted: dict[str, Any] = {"decisions": {}, "post_promotions": {}, "promoted_subjects": subjects}
        for slot, value in raw_decisions.items():
            if not isinstance(value, dict) or set(value) != {"outcome", "post_type_bits", "audience_topic_bits"}:
                return {}
            post_types = _bits(value["post_type_bits"], taxonomy.POST_TYPES); selected_topics = _bits(value["audience_topic_bits"], topics)
            if post_types is None or selected_topics is None:
                return {}
            converted["decisions"][slot] = {"outcome": value.get("outcome"), "post_types": post_types, "audience_topics": selected_topics or ["none"]}
        for slot, value in raw_promotions.items():
            selected_promotions = _bits(value, promotions)
            if selected_promotions is None:
                return {}
            converted["post_promotions"][slot] = selected_promotions or ["none"]
        return _parse_canonical_rows(converted, decisions, posts, role, isolate=isolate)
    if not isinstance(response, dict) or set(response) != {"decisions"} or not isinstance(response.get("decisions"), dict) or set(response["decisions"]) != set(decisions):
        return {}
    converted = {"decisions": {}}
    for slot, value in response["decisions"].items():
        if not isinstance(value, dict) or set(value) != {"product_label_bits", "sentiment", "geopolitical_mode_bits", "nationalism"}:
            return {}
        selected_products = _bits(value["product_label_bits"], products); modes = _bits(value["geopolitical_mode_bits"], geo)
        nationalism = value["nationalism"]
        if selected_products is None or modes is None:
            return {}
        if normalize_empty and isinstance(nationalism, dict) and nationalism == {"china": "none", "us": "none", "other_nation": False}:
            nationalism = None
        if nationalism is None:
            china, us = ("unknown", "unknown") if modes == ["unavailable"] else ("none", "none")
        elif isinstance(nationalism, dict) and set(nationalism) == {"china", "us", "other_nation"} and isinstance(nationalism["other_nation"], bool):
            china, us = nationalism["china"], nationalism["us"]
            modes.append("nationalism")
        else:
            return {}
        converted["decisions"][slot] = {"product_labels": selected_products or ["none"], "sentiment": value.get("sentiment"), "geopolitical_modes": modes or ["none"], "china_national_stance": china, "us_national_stance": us}
    return _parse_canonical_rows(converted, decisions, posts, role, isolate=isolate)


def _parse_dense(response: Any, decisions: dict[str, tuple[str, str]], posts: dict[str, str], role: str) -> dict[str, Any]:
    """Mechanically unfold dense boolean maps, without repairing their meaning."""
    if role == "content":
        if not isinstance(response, dict) or set(response) != {"decisions", "post_promotion_flags", "promoted_subjects"}:
            return {}
        raw_decisions = response.get("decisions")
        raw_promotions = response.get("post_promotion_flags")
        subjects = response.get("promoted_subjects")
        if not isinstance(raw_decisions, dict) or set(raw_decisions) != set(decisions) or not isinstance(raw_promotions, dict) or set(raw_promotions) != set(posts) or not isinstance(subjects, dict) or set(subjects) != set(posts):
            return {}
        converted: dict[str, Any] = {"decisions": {}, "post_promotions": {}, "promoted_subjects": subjects}
        for slot, value in raw_decisions.items():
            if not isinstance(value, dict) or set(value) != {"outcome", "post_type_flags", "audience_topic_flags"}:
                return {}
            post_types = _flags(value["post_type_flags"], taxonomy.POST_TYPES)
            topics = _flags(value["audience_topic_flags"], taxonomy.TOPICS)
            if post_types is None or topics is None:
                return {}
            converted["decisions"][slot] = {"outcome": value.get("outcome"), "post_types": post_types, "audience_topics": topics}
        for slot, flags in raw_promotions.items():
            values = _flags(flags, taxonomy.PROMOTIONS)
            if values is None:
                return {}
            converted["post_promotions"][slot] = values
        return taxonomy.parse(converted, decisions, posts, role)
    if not isinstance(response, dict) or set(response) != {"decisions"} or not isinstance(response.get("decisions"), dict) or set(response["decisions"]) != set(decisions):
        return {}
    converted = {"decisions": {}}
    for slot, value in response["decisions"].items():
        if not isinstance(value, dict) or set(value) != {"product_label_flags", "sentiment", "geopolitical_mode_flags", "china_national_stance", "us_national_stance"}:
            return {}
        products = _flags(value["product_label_flags"], taxonomy.PRODUCT_LABELS)
        modes = _flags(value["geopolitical_mode_flags"], taxonomy.GEO)
        if products is None or modes is None:
            return {}
        converted["decisions"][slot] = {"product_labels": products, "sentiment": value.get("sentiment"), "geopolitical_modes": modes, "china_national_stance": value.get("china_national_stance"), "us_national_stance": value.get("us_national_stance")}
    return taxonomy.parse(converted, decisions, posts, role)


def _parse_named(response: Any, decisions: dict[str, tuple[str, str]], posts: dict[str, str], role: str, *, normalize_bare_brand_decisions: bool = False, normalize_singleton_brand_keys: bool = False) -> dict[str, Any]:
    """Parse canonical named arrays, with an opt-in lossless v6 replay.

    Some saved v6 brand replies emitted the exact D-slot mapping but omitted
    its required ``decisions`` envelope.  Wrapping that complete mapping is a
    representation-only replay; it never maps a brand name to a slot, fills a
    missing decision, or changes labels.  Live v6 acceptance remains strict.
    """
    if normalize_bare_brand_decisions and role == "brand_interpretation" and isinstance(response, dict) and set(response) == set(decisions):
        response = {"decisions": response}
    if normalize_singleton_brand_keys and len(posts) == 1 and isinstance(response, dict):
        # This admits only a complete bijection from the expected canonical
        # target IDs to the fixed slots.  Aliases, unknown IDs, duplicate
        # brands, missing decisions, and any multi-source response stay
        # strict failures.
        expected = {brand for _, brand in decisions.values()}
        if len(expected) == len(decisions):
            raw_decisions = response.get("decisions")
            if role == "brand_interpretation" and raw_decisions is None and set(response) == expected:
                raw_decisions = response
                response = {"decisions": raw_decisions}
            if isinstance(raw_decisions, dict) and set(raw_decisions) == expected:
                response = dict(response)
                response["decisions"] = {slot: raw_decisions[brand] for slot, (_, brand) in decisions.items()}
    return taxonomy.parse(response, decisions, posts, role)


def _parse(response: Any, decisions: dict[str, tuple[str, str]], posts: dict[str, str], role: str, *, profile_key: str | None = None) -> dict[str, Any]:
    if profile_key == "qwen_classifier_v3":
        return _parse_dense(response, decisions, posts, role)
    if profile_key == "qwen_classifier_v4":
        return _parse_bits(response, decisions, posts, role)
    if profile_key == "qwen_classifier_v5":
        return _parse_bits(response, decisions, posts, role)
    if profile_key == "qwen_classifier_v6":
        return _parse_named(response, decisions, posts, role)
    if profile_key == "qwen_classifier_v6_normalized":
        return _parse_named(response, decisions, posts, role, normalize_bare_brand_decisions=True)
    if profile_key == "qwen_classifier_v6_normalized_brand_keys":
        return _parse_named(response, decisions, posts, role, normalize_bare_brand_decisions=True, normalize_singleton_brand_keys=True)
    if profile_key == "qwen_classifier_v4_strict":
        return _parse_bits(response, decisions, posts, role, normalize_empty=False, isolate=False)
    return taxonomy.parse(response, decisions, posts, role)


def _is_direct_deepseek(profile: ModelTaskProfile) -> bool:
    return profile.key == "deepseek_v41_incumbent_classifier_v1"


def _profile_record(profile: ModelTaskProfile) -> dict[str, Any]:
    record = profile_manifest(profile)
    if _is_direct_deepseek(profile):
        # ModelTaskProfile requires decimals. Zero is never presented as a
        # direct price because no matching saved direct-price snapshot exists.
        record["price_usd_per_million"] = {"input": None, "output": None}
    return record


def prepare(input_path: Path, directory: Path, *, suite: str = "smoke", profile_key: str = "qwen_classifier_v1") -> dict[str, Any]:
    if directory.exists() and any(directory.iterdir()):
        raise ValueError("experiment directory already exists")
    profile = _profile(profile_key)
    packet = read(input_path)
    rows = _source_rows(packet, suite)
    tweets = [_tweet(row) for row in rows]
    batch_size = 1 if profile.key in {"qwen_classifier_v6", "deepseek_v41_incumbent_classifier_v1", "gemini_flex_classifier_v2"} else BATCH_SIZE
    batches = []
    for index in range(0, len(tweets), batch_size):
        batch = tweets[index:index + batch_size]
        roles = []
        for role in ("content", "brand_interpretation"):
            _, _, envelope = _slots(batch)
            request = _request(envelope, role, profile)
            if profile.model == MODEL and len(_json(request)) > QWEN_MAX_INPUT_REQUEST_BYTES:
                raise ValueError("Qwen request exceeds the frozen 32,000-byte input bound")
            roles.append({"role": role, "request": request, "request_sha256": digest(request)})
        batches.append({"source_post_ids": [tweet["tweet_id"] for tweet in batch], "source_evidence": batch, "roles": roles})
    # Conservative maximum: raw bytes are an upper bound on tokens for this
    # purpose; reserve both response caps before any network activity.
    direct = _is_direct_deepseek(profile)
    reserved = MAX_TASK_USD if direct else sum((len(_json(role["request"])) * float(profile.input_usd_per_million) + int(role["request"]["max_tokens"]) * float(profile.output_usd_per_million)) / 1_000_000 for batch in batches for role in batch["roles"])
    if reserved > MAX_TASK_USD:
        raise ValueError("frozen task reservation exceeds $3")
    snapshot = ROOT / "docs/research/2026-09-17-143812-openrouter-pricing-snapshot/manifest.json"
    pricing = ({"status": "direct_route_price_unavailable", "billing_cost_usd": None,
                "saved_reference_only": {"snapshot": str(snapshot), "endpoint": "DeepSeek | deepseek/deepseek-v4.1-flash-20260910", "caveat": "OpenRouter provider pricing is not direct DeepSeek account pricing."}}
               if direct else {"snapshot": profile.snapshot_path, "input_per_million_usd": str(profile.input_usd_per_million), "output_per_million_usd": str(profile.output_usd_per_million)})
    contract = {"schema": SCHEMA, "created_at": _now(), "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(), "snapshot_manifest_sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
                "suite": suite, "source_post_ids": [tweet["tweet_id"] for tweet in tweets], "batches": batches,
                "profile": {**_profile_record(profile), "base_profile": _base_profile_key(profile_key), "prompt_profile": "u18a-two-role-taxonomy-v3-readable-singleton", "parser": "local_fixed_slot"},
                "pricing": pricing,
                "reserved_cost_usd": reserved, "reservation_kind": "task_budget_allocation_without_direct_price_estimate" if direct else "snapshot_price_ceiling", "limits": {"attempts": _configuration_cap(profile), "task_usd": MAX_TASK_USD, "portfolio_usd": MAX_PORTFOLIO_USD, "max_concurrency": MAX_CONCURRENCY, "calls_per_batch": 2, "batch_size": batch_size, "qwen_max_input_request_bytes": QWEN_MAX_INPUT_REQUEST_BYTES if profile.model == MODEL else None},
                "quality": {"acceptance": "candidate must equal or beat direct DeepSeek V4.1 on the same cohort, supplied context, and current taxonomy under an independent rubric", "full_source_review_required": True, "disagreement_policy": "a model-versus-incumbent disagreement is not itself an error", "coverage_policy": "review coverage and missing labels separately", "historical_owner_answers": "not exposed", "historical_taxonomy_quality": "unreviewed; current taxonomy semantics require separate labelled evaluation"}}
    contract["contract_sha256"] = digest(contract)
    write(directory / "contract.json", contract)
    return contract


def _client(profile: ModelTaskProfile) -> Any:
    if _is_direct_deepseek(profile):
        return AnthropicClaudeClient(api_key=credential("incumbent"), base_url=DEEPSEEK_DIRECT_BASE_URL)
    key = credential("0731")
    route = {"endpoint_tag": profile.endpoint_tag}
    if profile.endpoint_tag.endswith("/fp8"):
        route["quantizations"] = ["fp8"]
    if profile.key == "deepseek_0731_classifier_current_v1":
        route["request_profile"] = "deepseek_0731"
    return OpenRouterChatCompletionsClient(api_key=key, model=profile.model, provider=profile.provider_name, response_provider=profile.provider_name,
        response_model=profile.upstream_model, data_collection="allow", max_input_price=float(profile.input_usd_per_million),
        max_output_price=float(profile.output_usd_per_million), reasoning_enabled=bool(profile.settings.get("reasoning", {}).get("enabled")), service_tier=profile.service_tier, **route)


def _reserve(directory: Path, contract: dict[str, Any], attempt: int) -> None:
    marker = directory / f"attempt-{attempt}.consumed.json"
    if marker.exists():
        raise ValueError("attempt already consumed")
    ledger_path = directory.parent / "portfolio-ledger.json"
    ledger = read(ledger_path) if ledger_path.exists() else {"attempts": {}, "reserved_usd": 0.0}
    key = str(contract["profile"]["profile"])
    task_key = str(contract["profile"]["model"]) + "|classification"
    task = ledger["attempts"].get(task_key, {"profiles": {}, "reserved_usd": 0.0})
    if key not in task["profiles"] and len(task["profiles"]) >= int(contract["limits"]["attempts"]):
        raise ValueError("task attempt limit reached")
    reserved = float(contract["reserved_cost_usd"])
    if float(task["reserved_usd"]) + reserved > MAX_TASK_USD or float(ledger.get("reserved_usd", 0.0)) + reserved > MAX_PORTFOLIO_USD:
        raise ValueError("portfolio reservation limit reached")
    task["profiles"][key] = int(task["profiles"].get(key, 0)) + 1
    task["reserved_usd"] += reserved
    ledger["attempts"][task_key] = task
    ledger["reserved_usd"] = float(ledger.get("reserved_usd", 0.0)) + reserved
    write(ledger_path, ledger)
    # Persist before the first provider call.  A crashed process remains a
    # consumed attempt rather than silently paying for an unrecorded retry.
    write(marker, {"schema": SCHEMA + "/attempt", "attempt": attempt, "consumed_at": _now(), "status": "started", "contract_sha256": contract["contract_sha256"], "reserved_cost_usd": reserved, "rows": []})


def run(directory: Path, *, attempt: int = 1) -> dict[str, Any]:
    contract = read(directory / "contract.json")
    if not 1 <= attempt <= int(contract.get("limits", {}).get("attempts", 0)):
        raise ValueError("attempt exceeds limit")
    frozen = dict(contract); signature = frozen.pop("contract_sha256", None)
    if contract.get("schema") != SCHEMA or signature != digest(frozen):
        raise ValueError("frozen contract changed")
    snapshot = ROOT / "docs/research/2026-09-17-143812-openrouter-pricing-snapshot/manifest.json"
    if contract.get("snapshot_manifest_sha256") != hashlib.sha256(snapshot.read_bytes()).hexdigest():
        raise ValueError("frozen pricing snapshot changed")
    if any(digest(item["request"]) != item["request_sha256"] for batch in contract["batches"] for item in batch["roles"]):
        raise ValueError("frozen request or prompt changed")
    profile = _profile(str(contract["profile"].get("profile")))
    if _profile_record(profile) != {key: contract["profile"][key] for key in _profile_record(profile)}:
        raise ValueError("frozen profile changed")
    if profile.model == MODEL and any(len(_json(item["request"])) > QWEN_MAX_INPUT_REQUEST_BYTES for batch in contract["batches"] for item in batch["roles"]):
        raise ValueError("Qwen request exceeds the frozen 32,000-byte input bound")
    with _lock(directory.parent / ".portfolio.lock"):
        _reserve(directory, contract, attempt)
        marker = directory / f"attempt-{attempt}.consumed.json"
        client = _client(profile)
        output_rows = []
        for batch in contract["batches"]:
            tweets = batch["source_evidence"]
            parsed_by_role: dict[str, Any] = {}
            for item in batch["roles"]:  # deliberately sequential: no more than one call in flight
                raw: Any = None; error = None; usage = {}; parsed_json = None; strict_parsed = {}; started = time.monotonic()
                try:
                    request = item["request"]
                # Keep the provider's complete raw envelope.  Calling the
                # adapter's sender directly avoids discarding it during JSON
                # decoding; this runner still supplies the same pinned body.
                    if _is_direct_deepseek(profile):
                        direct_response = client.messages_create_text(timeout=profile.timeout_seconds, **request)
                        usage = getattr(direct_response, "provider_usage", None) or {}
                        if (not isinstance(usage, dict) or usage.get("provider") != "deepseek"
                                or usage.get("model") not in DEEPSEEK_V41_RESPONSE_ALIASES
                                or not usage.get("provider_request_id")):
                            raise ValueError("direct DeepSeek provider/model attestation failed")
                        content = direct_response.text
                        raw = {"content": content, "provider_usage": usage}
                    else:
                        raw = client._send_request(request, timeout=60)
                        usage, choice = client._validated_response(raw)
                        if choice.get("finish_reason") != "stop": raise ValueError("incomplete response")
                        content = client._choice_content(choice, usage)
                    parsed_json = json.loads(content, object_pairs_hook=_no_duplicate_keys)
                    decisions, posts, _ = _slots(tweets)
                    parsed_by_role[item["role"]] = _parse(parsed_json, decisions, posts, item["role"], profile_key=profile.key)
                    if profile.key in {"qwen_classifier_v4", "qwen_classifier_v5"}:
                        strict_parsed = _parse(parsed_json, decisions, posts, item["role"], profile_key="qwen_classifier_v4_strict")
                except Exception as exc:  # a paid malformed response must be retained, never retried
                    error = str(exc); usage = getattr(exc, "provider_usage", None) or usage
                    parsed_by_role[item["role"]] = {}
                output_rows.append({"source_post_ids": batch["source_post_ids"], "role": item["role"], "request_sha256": item["request_sha256"], "raw_response": raw, "structured_output": parsed_json, "usage": usage, "error": error, "parsed": parsed_by_role[item["role"]], "strict_parsed": strict_parsed, "latency_ms": round((time.monotonic()-started)*1000)})
                write(directory / f"attempt-{attempt}-calls.json", output_rows)
    errors = []
    for identifier in contract["source_post_ids"]:
        if not all(identifier in next((row["parsed"] for row in output_rows if row["role"] == role and identifier in row["source_post_ids"]), {}) for role in ("content", "brand_interpretation")):
            errors.append(identifier)
        else:
            content_rows = next(row["parsed"][identifier] for row in output_rows if row["role"] == "content" and identifier in row["parsed"])
            brand_rows = next(row["parsed"][identifier] for row in output_rows if row["role"] == "brand_interpretation" and identifier in row["parsed"])
            brands = {row["brand_id"]: row for row in brand_rows}
            for content_row in content_rows:
                brand = brands[content_row["brand_id"]]
                unavailable = brand["geopolitical_modes"] == ["unavailable"]
                missing = content_row["outcome"] == "context_missing"
                if missing != unavailable or (missing and (brand["product_labels"] != ["none"] or brand["sentiment"] != "unknown")):
                    errors.append(identifier)
                    break
    per_source = [{"source_post_id": identifier, "content": next((row for row in output_rows if row["role"] == "content" and identifier in row["source_post_ids"]), None), "brand_interpretation": next((row for row in output_rows if row["role"] == "brand_interpretation" and identifier in row["source_post_ids"]), None)} for identifier in contract["source_post_ids"]]
    report = {"schema": SCHEMA + "/report", "attempt": attempt, "finished_at": _now(), "profile": contract["profile"], "calls": output_rows, "rows": per_source,
              "source_post_errors": {"count": len(errors), "ids": errors, "denominator": len(contract["source_post_ids"]), "ceiling": 0.01, "status": "delivery_complete_semantics_unassessed" if not errors else "delivery_incomplete"},
              "quality": "unreviewed: no owner answers were exposed; historical labels cannot qualify current taxonomy semantics"}
    write(marker, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare"); prep.add_argument("input", type=Path); prep.add_argument("directory", type=Path); prep.add_argument("--suite", choices=("smoke", "diagnostic", "regression"), default="smoke"); prep.add_argument("--profile", choices=("qwen_classifier_v1", "qwen_classifier_v2", "qwen_classifier_v3", "qwen_classifier_v4", "qwen_classifier_v5", "qwen_classifier_v6", "deepseek_v41_incumbent_classifier_v1", "deepseek_0731_classifier_current_v1", "gemini_flex_classifier_v1", "gemini_flex_classifier_v2"), default="qwen_classifier_v1")
    live = sub.add_parser("run"); live.add_argument("directory", type=Path); live.add_argument("--attempt", type=int, default=1)
    args = parser.parse_args()
    result = prepare(args.input, args.directory, suite=args.suite, profile_key=args.profile) if args.command == "prepare" else run(args.directory, attempt=args.attempt)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
