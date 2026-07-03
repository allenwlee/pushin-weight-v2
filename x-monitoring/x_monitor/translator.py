# {{AGENT_ATTRIBUTION}}
"""LLM-driven translation pass for x-monitor v1.7.

v1.7's fetch returns 2 calls/cycle (Call A: list-based fan-in; Call B:
paren-grouped brand-wide). Both calls return tweets in mixed
English/Simplified Chinese (and occasionally other languages — the
plan explicitly rejects `lang:` filtering to keep cross-language
coverage).

The dashboard needs to render idiomatically in either en or zh-CN
without relying on browser-side translation (which produces poor
output for short, technical, name-laden tweets). Server-side LLM
translation runs AFTER the per-model relevance filter, so cost
scales with the kept set, not the raw API return volume.

Architecture:
  - `translate_batch(tweets, target_locales, client, dry_run=False)`
    sends up to 20 tweets per LLM call (amortizes round-trips), parses
    the structured response, and returns one row per input tweet.
  - The LLM is expected to return JSON of the form:
        {"results": [{"tweet_id", "lang_detected", "text_en",
                      "text_zh_cn", "noop_en", "noop_zh"}, ...]}
    with `noop_<locale>: true` set when the source already matches the
    target locale (translation is a no-op in that case).
  - On 5xx / 429 / network errors, retries 3 times with exponential
    backoff. Final failure marks the affected tweet(s) as
    `translation_failed: True` with NULL text columns.
  - `dry_run=True` skips the LLM and returns a stub row per tweet
    (used for the `--dry-run` CLI mode and for unit tests).
  - Prompt template instructs the LLM to preserve URLs, @mentions,
    and brand/model names verbatim. The brand-name list is sourced
    from `data/queries/<m>.yaml` brand_tokens and passed in via the
    `brand_names` kwarg.

Cost (Decision 6 in the plan): ~$0.005 per 1,000 kept posts for both
locales at Claude Haiku 4.5 pricing. At the typical 200 kept posts
per cycle, this is $0.001/cycle — trivial. Failures are non-fatal;
the dashboard falls back to source `text` and shows a "translation
pending" badge, and the `x-monitor translate` backfill subcommand
retries.

See docs/plans/2026-06-17-001-refactor-two-call-wide-net-translation-plan.md
§"Translation is LLM-driven via Claude Haiku" (Decision 6).
"""

from __future__ import annotations

import json
import time
from typing import Any, Protocol


# Maximum tweets per LLM call. The plan's Decision 6 specifies 20.
_TRANSLATION_BATCH_SIZE = 20

# Retry policy: 3 attempts with exponential backoff (1s, 2s, 4s).
_MAX_RETRIES = 3
_BACKOFF_BASE_SECONDS = 1.0


class ClaudeClient(Protocol):
    """The translator's interface to the LLM.

    The real client is implemented in this same module (see
    `AnthropicClaudeClient` below). Tests inject `FakeClaudeClient`
    to verify behavior without hitting the real API.

    The translator calls `client.messages_create(model=..., ...)` and
    expects a dict response. Implementations should:
      - Send the request to the Anthropic API
      - Parse the structured output (the prompt asks for JSON)
      - Return the parsed dict (or raise on hard error)
    """
    def messages_create(self, **kwargs) -> dict[str, Any]: ...


def build_translation_prompt(
    tweets: list[dict[str, Any]],
    target_locales: list[str],
    brand_names: list[str] | None = None,
) -> str:
    """Build the LLM prompt for a batch of tweets.

    The prompt instructs the model to:
      1. Detect the source language of each tweet
      2. Translate each tweet into each target locale
      3. Preserve URLs, @mentions, and brand/model names verbatim
      4. Return structured JSON of the form:
         {"results": [{"tweet_id", "lang_detected", "text_en",
                       "text_zh_cn", "noop_en", "noop_zh"}, ...]}
      5. Set `noop_<locale>: true` when the source already matches
         the target locale (no translation needed; text_<locale>
         should equal the source).
    """
    locale_list = ", ".join(target_locales)
    brand_block = ""
    if brand_names:
        brand_block = (
            "\n\nBrand and model names to preserve verbatim "
            "(do not translate, transliterate, or paraphrase):\n"
            + "\n".join(f"  - {name}" for name in brand_names)
        )

    # Embed the tweets as a JSON array so the LLM can reference them
    # by tweet_id. Each tweet is {tweet_id, text, brand_id?}.
    tweet_payload = json.dumps(
        [{"tweet_id": t.get("tweet_id") or t.get("id"),
          "text": t.get("text", ""),
          "brand_id": t.get("brand_id")}
         for t in tweets],
        ensure_ascii=False,
    )

    return (
        f"You are a tweet translator. Translate each tweet into these "
        f"target locales: {locale_list}.\n\n"
        f"Rules:\n"
        f"1. Detect the source language of each tweet (lang_detected; "
        f"use ISO 639-1 + script, e.g. 'zh-Hans', 'en', 'ja').\n"
        f"2. Translate the text into each target locale. Preserve URLs "
        f"and @mentions VERBATIM. Never translate a URL or a @mention.\n"
        f"3. If the source text is already in the target locale, set "
        f"text_<locale> equal to the source AND set noop_<locale>: true.\n"
        f"4. Return ONLY a JSON object with this exact shape:\n"
        f'   {{"results": [{{"tweet_id": str, "lang_detected": str, '
        f'"text_en": str, "text_zh_cn": str, "noop_en": bool, '
        f'"noop_zh": bool}}, ...]}}\n'
        f"   One result per input tweet, in the same order.\n"
        f"5. Do not include any prose, explanation, or code fences.\n"
        f"6. If a tweet is empty, return empty strings for text_<locale> "
        f"and set noop_<locale>: true for both.\n"
        f"{brand_block}\n\n"
        f"Tweets (JSON array):\n{tweet_payload}"
    )


def _parse_response(
    response: dict[str, Any],
    tweets: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    """Parse the LLM's structured response.

    Returns a list of result dicts, one per input tweet, in input
    order. Returns None if the response is malformed (caller treats
    as a parse failure for the whole batch).
    """
    if not isinstance(response, dict):
        return None
    results = response.get("results")
    if not isinstance(results, list):
        return None
    if len(results) != len(tweets):
        # Length mismatch is a parse failure (the LLM dropped or
        # duplicated a row). Reject and let the caller retry/fail.
        return None
    return results


def _call_with_retry(
    client: ClaudeClient,
    prompt: str,
) -> dict[str, Any]:
    """Call the LLM with exponential-backoff retry on transient errors.

    Raises the LAST exception if all retries fail. The translator
    catches and marks the batch as failed.
    """
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            return client.messages_create(
                model="claude-haiku-4-5",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as e:
            last_exc = e
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_BACKOFF_BASE_SECONDS * (2 ** attempt))
    # All retries failed.
    assert last_exc is not None
    raise last_exc


def _empty_row(tweet: dict[str, Any], failed: bool = False,
               dry_run: bool = False) -> dict[str, Any]:
    """Build a result row for a tweet that the translator cannot fill
    (failed LLM call, malformed response, or dry-run stub)."""
    row: dict[str, Any] = {
        "tweet_id": str(tweet.get("tweet_id") or tweet.get("id")),
        "brand_id": tweet.get("brand_id"),
        "text_en": None,
        "text_zh_cn": None,
        "lang_detected": None,
    }
    if failed:
        row["translation_failed"] = True
    if dry_run:
        row["dry_run"] = True
    return row


def translate_batch(
    tweets: list[dict[str, Any]],
    target_locales: list[str],
    client: ClaudeClient,
    *,
    brand_names: list[str] | None = None,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Translate a batch of tweets into the target locales.

    Args:
        tweets: list of dicts with at least `tweet_id` and `text`.
            May also include `brand_id` (used in the prompt context).
        target_locales: list of locale codes (e.g. ["en", "zh_cn"]).
            The columns filled in the output are `text_<locale>`.
        client: an object implementing the `ClaudeClient` protocol
            (`messages_create(**kwargs) -> dict`). The real client
            is `AnthropicClaudeClient`; tests inject `FakeClaudeClient`.
        brand_names: optional list of brand/model names to preserve
            verbatim in translations. Sourced from
            `data/queries/<m>.yaml::brand_tokens` per brand.
        dry_run: if True, skip the LLM and return stub rows. Used for
            the `x-monitor translate --dry-run` mode and unit tests.

    Returns:
        A list of dicts, one per input tweet (same order). Each dict
        has: `tweet_id`, `brand_id`, `text_en`, `text_zh_cn`,
        `lang_detected`, plus optional `translation_failed` (bool)
        or `dry_run` (bool). On failure, text_en/text_zh_cn are NULL.
    """
    if not tweets:
        return []

    if dry_run:
        return [_empty_row(t, dry_run=True) for t in tweets]

    out: list[dict[str, Any]] = []
    for start in range(0, len(tweets), _TRANSLATION_BATCH_SIZE):
        batch = tweets[start : start + _TRANSLATION_BATCH_SIZE]
        prompt = build_translation_prompt(
            batch, target_locales, brand_names=brand_names
        )
        try:
            response = _call_with_retry(client, prompt)
        except Exception:
            # All retries exhausted. Mark this batch's tweets as
            # failed and continue with the next batch (failures are
            # non-fatal per Decision 6).
            for t in batch:
                out.append(_empty_row(t, failed=True))
            continue
        parsed = _parse_response(response, batch)
        if parsed is None:
            # Malformed response. Mark this batch's tweets as failed.
            for t in batch:
                out.append(_empty_row(t, failed=True))
            continue
        for t, p in zip(batch, parsed):
            out.append({
                "tweet_id": str(p.get("tweet_id") or t.get("tweet_id") or t.get("id")),
                "brand_id": t.get("brand_id"),
                "text_en": p.get("text_en"),
                "text_zh_cn": p.get("text_zh_cn"),
                "lang_detected": p.get("lang_detected"),
                "noop_en": p.get("noop_en", False),
                "noop_zh": p.get("noop_zh", False),
            })
    return out


# --- U3: pragmatics translation prompt (research §5.1) -----------------
#
# The v1.7 prompt asked for plain text_en / text_zh_cn. The U3
# upgrade asks for the four-pronged YAML contract from research
# §5.1 so Chinese-vendor readers can tell hype from dunk from
# 抽象 without losing the literal translation. The prompt also
# accepts optional few-shot examples (research §3.10) that anchor
# each of the 9 discourse_roles to a verified live X post.


# Maximum tweets per LLM call. The plan's Decision 6 specifies 20.
_TRANSLATION_BATCH_SIZE = 20

# Retry policy: 3 attempts with exponential backoff (1s, 2s, 4s).
_MAX_RETRIES = 3
_BACKOFF_BASE_SECONDS = 1.0

# U3: the 9-way discourse_role vocabulary (mirrors discourse_keys
# migration 026). Coerce unknown keys to `uncategorized` per KTD5.
_DISCOURSE_ROLES: frozenset[str] = frozenset({
    "genuine_hype", "sarcasm", "dunk_yingyang", "self_deprecation",
    "cope", "fud", "distillation_accusation", "ai_slop_critique",
    "absurdist_meme",
})
_DISCOURSE_UNCATEGORIZED: str = "uncategorized"


def _is_english_family(lang: str) -> bool:
    """True when `lang` (lowercase) identifies as English.

    Handles ISO-639 with optional script/region (e.g. "en",
    "en-US", "en_GB", "EN"). Anything else is NOT English and
    text_en should be populated with a best-interpretation.
    """
    if not lang:
        return False
    # Strip region tag (en-US, en_GB) — match on the bare lang.
    bare = lang.split("-")[0].split("_")[0].strip().lower()
    return bare == "en"


def _is_simplified_chinese_family(lang: str) -> bool:
    """True when `lang` identifies as Simplified Chinese.

    Matches "zh-Hans", "zh-CN", "zh_CN_Hans", and bare "zh"
    (default to Simplified — most common case). Traditional
    Chinese (zh-Hant, zh-TW, zh-HK) is NOT Simplified — the
    translator should still emit a Simplified rendering for those.
    """
    if not lang:
        return False
    # Normalize to hyphen-separated form for token checks.
    lang_norm = lang.lower().replace("_", "-")
    # Explicit Traditional markers — never match.
    for marker in ("hant", "-tw", "-hk"):
        if marker in lang_norm:
            return False
    bare = lang_norm.split("-")[0]
    return bare == "zh"

# U3: the fixed-translation dictionary from research §4.5 — these are
# proper nouns in the Chinese AI circle and don't need annotation when
# they appear in source text. Used by apply_friction_judge.
_FIXED_ZH_TRANSLATIONS: dict[str, str] = {
    "vibe coding": "氛围编程",
    "vibe coder": "氛围码农",
    "sycophancy": "舔狗",
    "distillation": "蒸馏",
    "wrapper": "套壳",
    "fine-tune": "微调",
    "skin-swapping": "换皮",
    "open-weight": "开放权重",
    "open-source": "真开源",
    "roast": "毒舌",
    "based": "敢说真话",
}


_PRAGMATICS_SYSTEM_PROMPT: str = (
    "You are a 'bilingual pragmatic analyst' specializing in English X "
    "(Twitter) AI/LLM-sphere discourse → Chinese AI-sphere discourse. "
    "Your audience is product managers and market intelligence personnel "
    "at Chinese-mainland LLM vendors.\n\n"
    "You understand English X expressions such as meme / slang / irony / "
    "dunk / FUD / 抽象 / 翻车, and you understand Chinese parallel "
    "expressions such as 阴阳怪气 / 抽象话 / 套壳 / 蒸馏 / 舔狗 / 翻车 / 整活.\n\n"
    "For each input tweet, output exactly 4 fields in this YAML shape:\n"
    "  literal_zh:       Simplified Chinese literal translation. Preserve\n"
    "                    the original slang — do NOT smooth it out. "
    "Mixed Chinese/English is permitted (e.g. 'Sora 2', 'DeepSeek-V4').\n"
    "                    @mentions, URLs, and emojis stay verbatim.\n"
    "  text_en:          English text. Always populate with the best "
    "interpretation\n"
    "                    of the source (English posts get the source "
    "verbatim;\n"
    "                    non-English posts get a literal translation). "
    "Server-side\n"
    "                    will NULL this column if the post's "
    "`lang_detected` is\n"
    "                    English (no English text needs re-storing).\n"
    "  lang_detected:    ISO 639-1 + script (e.g. 'en', 'zh-Hans').\n"
    "  discourse_role:   EXACTLY one of: genuine_hype, sarcasm, "
    "dunk_yingyang,\n"
    "                    self_deprecation, cope, fud, "
    "distillation_accusation,\n"
    "                    ai_slop_critique, absurdist_meme, other.\n"
    "  cn_equivalent:    A 'how would Chinese netizens on Weibo/Zhihu/"
    "Bilibili\n"
    "                    say the same thing' rendering. Use 'N/A' if "
    "no equivalent.\n"
    "  literal_zh:       Best-interpretation Simplified Chinese rendering. "
    "Always\n"
    "                    populate — server-side will NULL the zh-CN column\n"
    "                    if `lang_detected` is already Simplified "
    "Chinese.\n"
    "  annotation:       A 1-3 sentence cultural-background annotation. "
    "ONLY when\n"
    "                    the post contains F2 or F3 friction (meme origin, "
    "named\n"
    "                    event, brand-specific slur). Otherwise leave empty.\n"
    "  noop_en:          (optional hint) true if the source is already "
    "English.\n"
    "  noop_zh:          true if source is already Simplified Chinese. "
    "The\n"
    "                    server-side translator may use this as a hint but\n"
    "                    ultimately decides via `lang_detected`.\n\n"
    "Fixed-translation dictionary — use these for the literal_zh field "
    "WITHOUT annotation:\n"
    "  vibe coding → 氛围编程;  sycophancy → 舔狗;  distillation → 蒸馏;\n"
    "  wrapper → 套壳;  fine-tune → 微调;  open-weight → 开放权重;\n"
    "  roast → 毒舌;  based → 敢说真话.\n\n"
    "Rules:\n"
    "1. Return ONLY a JSON object of the form:\n"
    '   {"results": [{"tweet_id": str, "text_en": str, "literal_zh": str, '
    '"lang_detected": str, "discourse_role": str, "cn_equivalent": str, '
    '"annotation": str, "noop_en": bool, "noop_zh": bool}, ...]}\n'
    "2. One result per input tweet, in the same order.\n"
    "3. Total output per post ≤ 280 characters (excluding tweet_id).\n"
    "4. Model names, brand names, personal names, @mentions, URLs, and "
    "emojis stay verbatim.\n"
    "5. Do not include any prose, explanation, or code fences outside "
    "the JSON.\n"
)


def _load_few_shot_examples() -> list[dict[str, Any]]:
    """Load the §3.10 few-shot examples from disk (research).

    The fixture lives at `x_monitor/data/few_shot_pragmatics.jsonl`
    (created when this module is first installed). On missing-file
    or parse-error, fall back to an empty list so the prompt is
    still sent (just without the anchoring examples).

    The loader is intentionally tolerant: it never raises, so a
    broken fixture file degrades to "no few-shot" rather than
    breaking the live cycle.
    """
    try:
        from pathlib import Path as _P
        path = (
            _P(__file__).parent / "data" / "few_shot_pragmatics.jsonl"
        )
        if not path.exists():
            return []
        out: list[dict[str, Any]] = []
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if isinstance(row, dict):
                    out.append(row)
        return out
    except Exception:
        return []


def build_pragmatics_translation_prompt(
    tweets: list[dict[str, Any]],
    target_locales: list[str],
    brand_names: list[str] | None = None,
    few_shot_examples: list[dict[str, Any]] | None = None,
) -> str:
    """Build the U3 §5.1 pragmatics-aware translation prompt."""
    locale_list = ", ".join(target_locales)
    brand_block = ""
    if brand_names:
        brand_block = (
            "\n\nBrand and model names to preserve verbatim "
            "(do not translate, transliterate, or paraphrase):\n"
            + "\n".join(f"  - {name}" for name in brand_names)
        )

    if few_shot_examples is None:
        few_shot_examples = _load_few_shot_examples()
    few_shot_block = ""
    if few_shot_examples:
        few_shot_block = (
            "\n\nFew-shot examples (one per discourse_role; verified "
            "live X posts from 2026-06-26):\n"
            + "\n".join(
                f"  Input: {ex.get('input', '')!r}\n"
                f"  Output: {json.dumps(ex.get('output', {}), ensure_ascii=False)}"
                for ex in few_shot_examples
            )
        )

    tweet_payload = json.dumps(
        [{"tweet_id": t.get("tweet_id") or t.get("id"),
          "text": t.get("text", ""),
          "brand_id": t.get("brand_id")}
         for t in tweets],
        ensure_ascii=False,
    )

    return (
        _PRAGMATICS_SYSTEM_PROMPT
        + f"\n\nTarget locales for text_en: {locale_list}"
        + brand_block
        + few_shot_block
        + f"\n\nTweets (JSON array):\n{tweet_payload}"
    )


def apply_friction_judge(
    post: dict[str, Any], llm_yaml: dict[str, Any]
) -> dict[str, Any]:
    """Apply the F0–F3 friction-level judgment (research §6.5)."""
    text = (post.get("text") or "").lower()
    raw_role = llm_yaml.get("discourse_role") or ""
    role = raw_role if raw_role in _DISCOURSE_ROLES else _DISCOURSE_UNCATEGORIZED
    raw_annotation = (llm_yaml.get("annotation") or "").strip()

    f0_roles = {
        "genuine_hype", "fud", "ai_slop_critique",
        "distillation_accusation",
    }
    if role in f0_roles:
        annotation = ""
    elif any(token in text for token in _FIXED_ZH_TRANSLATIONS):
        annotation = ""
    elif any(
        marker in text
        for marker in (
            "theranos", "quibi", "shrimp jesus", "this is fine",
        )
    ):
        annotation = raw_annotation[:280]
    elif any(slang in text for slang in ("no cap", " mid ", "based")):
        annotation = raw_annotation[:140]
    else:
        annotation = ""

    return {
        **llm_yaml,
        "discourse_role": role,
        "annotation": annotation,
    }


def _empty_pragmatics_row(
    tweet: dict[str, Any], failed: bool = False, dry_run: bool = False
) -> dict[str, Any]:
    """U3: empty-row shape for the four-pronged contract."""
    row: dict[str, Any] = {
        "tweet_id": str(tweet.get("tweet_id") or tweet.get("id")),
        "brand_id": tweet.get("brand_id"),
        "text_en": None,
        "text_zh_cn": None,
        "literal_zh": None,
        "lang_detected": None,
        "discourse_role": _DISCOURSE_UNCATEGORIZED,
        "cn_equivalent": None,
        "annotation": None,
    }
    if failed:
        row["translation_failed"] = True
    if dry_run:
        row["dry_run"] = True
    return row


def _parse_pragmatics_response(
    response: dict[str, Any],
    tweets: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    """U3: parse the LLM's structured YAML/JSON response."""
    if not isinstance(response, dict):
        return None
    results = response.get("results")
    if not isinstance(results, list):
        return None
    if len(results) != len(tweets):
        return None
    return results


def translate_batch_pragmatics(
    tweets: list[dict[str, Any]],
    target_locales: list[str],
    client: "ClaudeClient",
    *,
    brand_names: list[str] | None = None,
    few_shot_examples: list[dict[str, Any]] | None = None,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """U3: translate a batch of tweets with the §5.1 four-pronged contract."""
    if not tweets:
        return []

    if dry_run:
        return [_empty_pragmatics_row(t, dry_run=True) for t in tweets]

    out: list[dict[str, Any]] = []
    for start in range(0, len(tweets), _TRANSLATION_BATCH_SIZE):
        batch = tweets[start: start + _TRANSLATION_BATCH_SIZE]
        prompt = build_pragmatics_translation_prompt(
            batch,
            target_locales,
            brand_names=brand_names,
            few_shot_examples=few_shot_examples,
        )
        try:
            response = _call_with_retry(client, prompt)
        except Exception:
            for t in batch:
                out.append(_empty_pragmatics_row(t, failed=True))
            continue
        parsed = _parse_pragmatics_response(response, batch)
        if parsed is None:
            for t in batch:
                out.append(_empty_pragmatics_row(t, failed=True))
            continue
        for t, p in zip(batch, parsed):
            judged = apply_friction_judge(t, p)
            # Server-side noop logic is deterministic and based
            # on `lang_detected`, NOT the LLM's noop_* flags (the
            # LLM is a sloppy noop reporter — it echoes the source
            # into the locale column anyway, and the shape contract
            # is "the locale column is NULL when the source is
            # already in that locale").
            #
            # text_en: NULL when lang is in the English family
            #   (en, en-US, en-GB, ...). The source `text` is
            #   already the English version.
            #
            # text_zh_cn: populated for ALL non-zh-Hans sources.
            #   The LLM's output is treated as a best-interpretation
            #   rendering with nuance (idioms / memes annotated
            #   via cn_equivalent + annotation), NOT a literal
            #   word-for-word translation. When the source IS
            #   already Simplified Chinese, the column stays NULL
            #   (source serves).
            #
            # The LLM's `noop_en` / `noop_zh` flags are surfaced
            # for downstream consumers (dashboard badges) but
            # are NOT trusted for column population.
            lang = (judged.get("lang_detected") or "").lower()
            text_en = None if _is_english_family(lang) else judged.get("text_en")
            is_already_zh = _is_simplified_chinese_family(lang)
            literal_zh_raw = (
                None if is_already_zh
                else (judged.get("literal_zh") or p.get("text_zh_cn"))
            )
            text_zh_cn = None if is_already_zh else literal_zh_raw
            out.append({
                "tweet_id": str(
                    p.get("tweet_id") or t.get("tweet_id") or t.get("id")
                ),
                "brand_id": t.get("brand_id"),
                "text_en": text_en,
                "text_zh_cn": text_zh_cn,
                "lang_detected": lang or None,
                "noop_en": text_en is None,
                "noop_zh": text_zh_cn is None,
                "literal_zh": literal_zh_raw,
                "discourse_role": judged.get("discourse_role"),
                "cn_equivalent": judged.get("cn_equivalent"),
                "annotation": judged.get("annotation"),
            })
    return out


# --- v1.8 (Unit 4): registry-row translation extension -----------------
#
# Extends translate_batch to cover the per-locale columns on the
# registry tables (brands.display_name_en/_zh_cn, companies same,
# accounts.bio_en/_zh_cn). Same shape: batch size 20, exponential
# backoff, idempotent UPDATE, dry-run mode. Adds prompt rule 7:
# preserve proper nouns (brand/company/model names) verbatim.


def build_registry_translation_prompt(
    rows: list[dict[str, Any]],
    target_locales: list[str],
    column_label: str,
    brand_names: list[str] | None = None,
) -> str:
    """Build the LLM prompt for translating registry rows.

    Args:
        rows: list of dicts with at least `pk` and `source`. The
            source is the existing column value (e.g. brands.display_name
            or accounts.bio).
        target_locales: list of locale codes (e.g. ["en", "zh_cn"]).
        column_label: human-readable name of the column for the prompt
            context (e.g. "brand display name" or "account bio").
        brand_names: optional list of proper-noun strings to preserve
            verbatim across all translations.

    The prompt asks the model for a JSON object of the form:
        {"results": [{"pk": ..., "col_en": ..., "col_zh_cn": ...}, ...]}
    with `noop_<locale>: true` set when the source already matches.
    """
    locale_list = ", ".join(target_locales)
    brand_block = ""
    if brand_names:
        brand_block = (
            "\n\nProper nouns to preserve VERBATIM across all translations "
            "(do not translate, transliterate, or paraphrase these — "
            "translate any surrounding descriptor but keep the noun "
            "in its canonical form, e.g. keep 'MiniMax AI' verbatim "
            "even in a Chinese translation):\n"
            + "\n".join(f"  - {name}" for name in brand_names)
        )

    payload = json.dumps(
        [{"pk": r.get("pk"), "source": r.get("source", "")} for r in rows],
        ensure_ascii=False,
    )

    return (
        f"You are translating {column_label} entries into these target "
        f"locales: {locale_list}.\n\n"
        f"Rules:\n"
        f"1. Detect the source language of each entry.\n"
        f"2. Translate into each target locale. Preserve URLs and "
        f"@mentions VERBATIM.\n"
        f"3. If the source is already in the target locale, set "
        f"col_<locale> equal to the source AND set noop_<locale>: true.\n"
        f"4. Return ONLY a JSON object with this exact shape:\n"
        f'   {{"results": [{{"pk": str, "col_en": str, "col_zh_cn": str, '
        f'"noop_en": bool, "noop_zh": bool}}, ...]}}\n'
        f"   One result per input row, in the same order.\n"
        f"5. Do not include any prose, explanation, or code fences.\n"
        f"6. If a row is empty, return empty strings for col_<locale> "
        f"and set noop_<locale>: true for both.\n"
        f"7. Preserve proper nouns (brand names, company names, model "
        f"names) VERBATIM — translate any surrounding descriptor but "
        f"keep the canonical noun form (e.g. keep 'MiniMax AI' verbatim "
        f"even in Chinese).\n"
        f"{brand_block}\n\n"
        f"Rows (JSON array):\n{payload}"
    )


def _parse_registry_response(
    response: dict[str, Any],
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    """Parse the LLM's structured response for a registry translation batch.

    Returns a list of result dicts, one per input row, in input order.
    Returns None if the response is malformed (caller treats as a
    parse failure for the whole batch).
    """
    if not isinstance(response, dict):
        return None
    results = response.get("results")
    if not isinstance(results, list):
        return None
    if len(results) != len(rows):
        return None
    return results


def _empty_registry_row(
    row: dict[str, Any],
    failed: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Build a result row for a registry entry that the translator
    cannot fill (failed LLM call, malformed response, or dry-run stub).
    """
    out: dict[str, Any] = {
        "pk": str(row.get("pk")),
        "col_en": None,
        "col_zh_cn": None,
    }
    if failed:
        out["translation_failed"] = True
    if dry_run:
        out["dry_run"] = True
    return out


def translate_registry_rows(
    rows: list[dict[str, Any]],
    target_locales: list[str],
    client: "ClaudeClient",
    *,
    column_label: str = "registry entry",
    brand_names: list[str] | None = None,
    batch_size: int = _TRANSLATION_BATCH_SIZE,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Translate a batch of registry rows into the target locales.

    Args:
        rows: list of dicts with at least `pk` and `source`.
        target_locales: list of locale codes (e.g. ["en", "zh_cn"]).
        client: an object implementing the `ClaudeClient` protocol.
        column_label: human-readable name of the column for the prompt
            context (e.g. "brand display name"). Defaults to a generic
            "registry entry" so tests don't have to set it.
        brand_names: optional list of proper-noun strings to preserve
            verbatim across all translations.
        batch_size: rows per LLM call (default 20).
        dry_run: if True, skip the LLM and return stub rows.

    Returns:
        A list of dicts, one per input row (same order). Each dict has:
            `pk`, `col_en`, `col_zh_cn`, plus optional
            `translation_failed` (bool) or `dry_run` (bool).
            On failure, col_en / col_zh_cn are NULL.
    """
    if not rows:
        return []

    if dry_run:
        return [_empty_registry_row(r, dry_run=True) for r in rows]

    out: list[dict[str, Any]] = []
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        prompt = build_registry_translation_prompt(
            batch, target_locales, column_label,
            brand_names=brand_names,
        )
        try:
            response = _call_with_retry(client, prompt)
        except Exception:
            for r in batch:
                out.append(_empty_registry_row(r, failed=True))
            continue
        parsed = _parse_registry_response(response, batch)
        if parsed is None:
            for r in batch:
                out.append(_empty_registry_row(r, failed=True))
            continue
        for r, p in zip(batch, parsed):
            out.append({
                "pk": str(p.get("pk") or r.get("pk")),
                "col_en": p.get("col_en"),
                "col_zh_cn": p.get("col_zh_cn"),
                "noop_en": p.get("noop_en", False),
                "noop_zh": p.get("noop_zh", False),
            })
    return out


# --- Real client (imports anthropic lazily so test envs without the
#     package installed can still import this module) -------------------


class AnthropicClaudeClient:
    """Production Claude client using the Anthropic SDK.

    Imports `anthropic` lazily (only when an instance is constructed)
    so test environments without the SDK installed can still import
    this module and use FakeClaudeClient. The fuchitalee gateway's
    `ANTHROPIC_API_KEY` env var is the credential.
    """

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        try:
            import anthropic  # type: ignore
        except ImportError as e:
            raise ImportError(
                "AnthropicClaudeClient requires the 'anthropic' package. "
                "Install with `pip install anthropic`. Tests can use "
                "FakeClaudeClient instead."
            ) from e
        kwargs: dict[str, Any] = {}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        self._client = anthropic.Anthropic(**kwargs)

    def messages_create(self, **kwargs) -> dict[str, Any]:
        """Send a messages.create request and return the parsed JSON.

        The translator's prompt asks for raw JSON output. The
        Anthropic SDK returns a Message object with content blocks;
        we extract the first text block and json.loads() it. If the
        model returns non-JSON (e.g., wrapped in code fences), we
        attempt to strip the fences before parsing.
        """
        import json as _json
        msg = self._client.messages.create(**kwargs)
        # Concatenate all text blocks (the model may emit multiple).
        text_parts = []
        for block in msg.content:
            if hasattr(block, "text"):
                text_parts.append(block.text)
        raw = "\n".join(text_parts).strip()
        # Strip code fences if present.
        if raw.startswith("```"):
            lines = raw.splitlines()
            # Drop first (```json) and last (```) lines.
            inner = "\n".join(lines[1:-1]) if lines[-1].strip().startswith("```") else "\n".join(lines[1:])
            raw = inner.strip()
        return _json.loads(raw)
