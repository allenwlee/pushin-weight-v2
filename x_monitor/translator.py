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
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any, Callable, Protocol

from ._json_parser import parse_llm_response

if TYPE_CHECKING:
    from .config import Config

logger = logging.getLogger(__name__)


# Maximum tweets per LLM call. The plan's Decision 6 specifies 20.
_TRANSLATION_BATCH_SIZE = 20

# Retry policy: 3 attempts with exponential backoff (1s, 2s, 4s).
_MAX_RETRIES = 3


def _max_tokens_for_batch_size(n: int) -> int:
    """Per-batch output budget for the translator's messages_create call.

    Mirrors the classifier-swap recipe (plan 2026-07-15-002 KTD4):
    budget sized to batch size with a cap, so larger batches are not
    truncated by an undersized output budget and runaway batches
    cannot cost a fortune.

    The coefficient (1000 tokens/tweet) reflects the translator's
    proven worst-case output density, not the classifier's. On
    2026-08-05 a prod-typical 20-post rich-content batch consumed
    19,554 output tokens at DeepSeek V4 Pro (~977 tokens/post);
    with classification per-tweet overhead (text_en + literal_zh +
    en_equivalent + cn_equivalent + annotation + JSON framing) the budget must
    scale as O(n) with a high per-post coefficient. Bilingual commentary now
    uses 1500 tokens/post to preserve meaningful headroom over that probe.

    The hard cap is 65536 — DeepSeek's documented max output. The
    earlier 8192 cap was based on an outdated "DS V4 beta max"
    assumption; live API calls accept and require up to 65k for
    rich-content batches (see plan 2026-08-05-003 U1).

    Notes on prior values:
      * 2026-08-04 02953d6: 16384 (lifted after M3 truncation first
        observed). M3 proxy-side cap cannot be raised via max_tokens.
      * 2026-08-04 4d3db60: 8192 (incorrectly assumed to match DS V4
        beta max). Caused ~25% of prod batches to truncate mid-JSON.
      * 2026-08-05 3/1 (this): 65536 cap, 1000 tokens/post coefficient.

    Args:
        n: number of tweets in the batch.

    Returns:
        max_tokens value to pass to messages_create.
    """
    if n < 1:
        return 16384
    # The original 1000 tokens/post covered the 2026-08-05 prod probe
    # (19,554 tokens on 20 posts). Bilingual commentary adds a second
    # synthesis field, so retain 50% structural headroom. Floor of 16384
    # defends against tiny-batch edge cases
    # (1-2 tweet batches still need room for framing + cn_equivalent).
    return min(65536, max(16384, 1500 * n))


# n_tweets is now passed directly to _call_with_retry
# (no prompt parsing; the caller knows the batch size).
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
    client: "ClaudeClient",
    prompt: str,
    *,
    n_tweets: int = 0,
    cfg: "Config | None" = None,
    deadline: Any | None = None,
) -> dict[str, Any]:
    """Call the LLM with exponential-backoff retry on transient errors.

    Raises the LAST exception if all retries fail. The translator
    catches and marks the batch as failed.

    Pass `cfg` to thread cfg.llm.translator_model + cfg.llm.translator_base_url
    into the model/thinking resolution. Without cfg, resolution falls back
    to env inference (ANTHROPIC_BASE_URL / X_MONITOR_TRANSLATOR_BASE_URL
    substring) which can pick the wrong model when the env-group still
    points at api.minimax.io/anthropic while the cron override routes
    through api.deepseek.com/anthropic. This is the missing call-site
    wire-up for the swap-translator plan 2026-08-04-001; commit a46d2de
    fixed `_resolve_translator_model` but missed this call site.
    """
    last_exc: Exception | None = None
    from .attribution import _resolve_thinking_default
    from .attribution import _resolve_translator_model as _resolve_model
    # cfg-threaded resolution: cfg.llm.translator_model is canonical
    # when provided; env inference is the fallback.
    model = _resolve_model(cfg)
    # Plan 2026-08-04-001: thinking kwarg follows the base URL the
    # call is actually routing to, not the operator's other env config.
    # The helper reads X_MONITOR_TRANSLATOR_BASE_URL first (per-role
    # override) when role="translator", else ANTHROPIC_BASE_URL.
    thinking = _resolve_thinking_default(role="translator")
    # Plan 2026-08-04-001: per-batch output budget sized by
    # _max_tokens_for_batch_size. The prior 4096 was too tight for
    # 20-tweet M3 batches (proxy-side cap truncated responses
    # mid-JSON at ~9-12K bytes per prod observation on 2026-08-04,
    # commit 02953d6 bumped to 16384 but the M3 proxy cap cannot be
    # lifted via max_tokens). DS V4 on the new code path handles
    # 4096 tokens cleanly at batch_size=20 with 50% headroom (per
    # classifier-swap probe data, plan 2026-07-15-002 KTD4).
    max_tokens = _max_tokens_for_batch_size(n_tweets)
    for attempt in range(_MAX_RETRIES):
        request_timeout: float | None = None
        if deadline is not None:
            request_timeout = float(deadline.request_timeout())
            if request_timeout <= 0:
                raise TimeoutError("enrichment_attempt_deadline_exhausted")
        try:
            kwargs: dict = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }
            if thinking is not None:
                kwargs["thinking"] = thinking
            if request_timeout is not None:
                kwargs["timeout"] = request_timeout
            return client.messages_create(**kwargs)
        except Exception as e:
            last_exc = e
            if attempt < _MAX_RETRIES - 1:
                backoff = _BACKOFF_BASE_SECONDS * (2 ** attempt)
                if deadline is not None and deadline.remaining() <= backoff:
                    raise TimeoutError(
                        "enrichment_attempt_deadline_exhausted"
                    ) from e
                time.sleep(backoff)
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
    cfg: "Config | None" = None,
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
            response = _call_with_retry(client, prompt, n_tweets=len(batch), cfg=cfg)
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
# §5.1 so Chinese-vendor readers can tell literal translation
# apart from netizen-flavored rephrasing without losing either.
# Note: `discourse_role` was REMOVED from the translator contract
# in plan 2026-07-06-001 — pragmatic register is now exclusively
# the classifier's output (per-brand, written to
# `posts_brands_discourse`), not the translator's (post-level,
# never persisted). The translator returns translation + netizen
# voice + friction annotation; nothing about the post's tone.


# Maximum tweets per LLM call. The plan's Decision 6 specifies 20.
_TRANSLATION_BATCH_SIZE = 20

# Retry policy: 3 attempts with exponential backoff (1s, 2s, 4s).
_MAX_RETRIES = 3
_BACKOFF_BASE_SECONDS = 1.0


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



# Plan 2026-08-10-004: closed allowlist for pragmatics lang_detected.
LANG_DETECTED_ALLOWLIST: frozenset[str] = frozenset(
    {"en", "zh-Hans", "zh-Hant", "ja", "ko", "other"}
)

# Registered ISO 639-1 primary language subtags. Keeping this boundary local
# avoids accepting reserved/undetermined values such as ``und``, ``qaa``,
# ``xx``, or ``zz`` merely because they resemble language tags.
_ISO_639_1_PRIMARY_CODES: frozenset[str] = frozenset(
    """
    aa ab ae af ak am an ar as av ay az ba be bg bh bi bm bn bo br bs ca ce
    ch co cr cs cu cv cy da de dv dz ee el en eo es et eu fa ff fi fj fo fr
    fy ga gd gl gn gu gv ha he hi ho hr ht hu hy hz ia id ie ig ii ik io is
    it iu ja jv ka kg ki kj kk kl km kn ko kr ks ku kv kw ky la lb lg li ln
    lo lt lu lv mg mh mi mk ml mn mr ms mt my na nb nd ne ng nl nn no nr nv
    ny oc oj om or os pa pi pl ps pt qu rm rn ro ru rw sa sc sd se sg si sk
    sl sm sn so sq sr ss st su sv sw ta te tg th ti tk tl tn to tr ts tt tw
    ty ug uk ur uz ve vi vo wa wo xh yi yo za zh zu
    """.split()
)

# Synonym map: bare / region tags → allowlist form (after lower+hyphen normalize).
_LANG_SYNONYMS: dict[str, str] = {
    "en": "en",
    "eng": "en",
    "zh": "zh-Hans",
    "zho": "zh-Hans",
    "chi": "zh-Hans",
    "zh-cn": "zh-Hans",
    "zh-hans": "zh-Hans",
    "zh-sg": "zh-Hans",
    "zh-tw": "zh-Hant",
    "zh-hk": "zh-Hant",
    "zh-hant": "zh-Hant",
    "zh-mo": "zh-Hant",
    "ja": "ja",
    "jpn": "ja",
    "jp": "ja",
    "ko": "ko",
    "kor": "ko",
    "kr": "ko",
    "other": "other",
}


def normalize_lang_detected(raw: object) -> str | None:
    """Map raw LLM lang_detected to an allowlist form, or None if invalid."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        raw = str(raw)
    s = raw.strip().lower().replace("_", "-")
    if not s:
        return None
    # Exact synonym table first.
    if s in _LANG_SYNONYMS:
        return _LANG_SYNONYMS[s]
    # en-US / en-gb → en
    bare = s.split("-")[0]
    if bare == "en":
        return "en"
    if bare == "ja":
        return "ja"
    if bare == "ko":
        return "ko"
    # zh-* traditional markers
    if bare == "zh":
        for marker in ("hant", "tw", "hk", "mo"):
            if marker in s:
                return "zh-Hant"
        return "zh-Hans"
    if s in LANG_DETECTED_ALLOWLIST:
        return s
    # The persisted vocabulary groups every real language outside the named
    # EN/ZH/JA/KO families into ``other``. Providers commonly return the more
    # precise registered language tag (for example ``fr`` or ``es-MX``) even
    # when the prompt requests that bucket. Accept an ISO 639-1 primary code
    # with conservative region/script subtags; free-form, reserved, private,
    # and undetermined values still take the bounded repair path.
    parts = s.split("-")
    if parts[0] in _ISO_639_1_PRIMARY_CODES and all(
        2 <= len(part) <= 8 and part.isascii() and part.isalnum()
        for part in parts[1:]
    ):
        return "other"
    # Case-sensitive allowlist members already covered; reject freeform.
    return None


def validate_lang_detected(raw: object) -> bool:
    """True when raw normalizes to an allowlisted lang_detected value."""
    return normalize_lang_detected(raw) is not None

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


# Translator output column naming — see docs/reference/translator-output.md
#
#   `literal_zh` (post translator, _PRAGMATICS_SYSTEM_PROMPT below) and
#   `text_zh_cn` (registry translator, _REGISTRY_*_PROMPT further down)
#   end up writing to the same `posts` columns but reflect TWO different
#   rendering styles — lossless-with-slang for X / Twitter posts vs.
#   formal / named-entity-preserving for lookup tables. The naming
#   convention makes the translator stage obvious from the column name.
#
#   `cn_equivalent` is NOT a translation — it's the "how would Chinese
#   netizens on Weibo/Zhihu/Bilibili say this" free rendering. Distinct
#   from `literal_zh`.

_PRAGMATICS_SYSTEM_PROMPT: str = (
    "You are a 'bilingual pragmatic analyst' specializing in English X "
    "(Twitter) AI/LLM-sphere discourse → Chinese AI-sphere discourse. "
    "Your audience is product managers and market intelligence personnel "
    "at Chinese-mainland LLM vendors.\n\n"
    "You understand English X expressions such as meme / slang / irony / "
    "dunk / FUD / 抽象 / 翻车, and you understand Chinese parallel "
    "expressions such as 阴阳怪气 / 抽象话 / 套壳 / 蒸馏 / 舔狗 / 翻车 / 整活.\n\n"
    "For EACH input tweet, set fields in this order. "
    "`lang_detected` is REQUIRED and must never be omitted.\n\n"
    "  lang_detected:    REQUIRED. One of: en | zh-Hans | zh-Hant | ja | ko | other. "
    "Detect from the tweet text (not optional). Use `other` when none of the "
    "named codes fit. Never leave blank.\n"
    "  text_en:          English text. Best interpretation of the source "
    "(English posts may echo source; non-English get a translation).\n"
    "  literal_zh:       Best-interpretation Simplified Chinese rendering. "
    "Preserve slang; mixed Chinese/English OK for model names. "
    "@mentions, URLs, and emojis stay verbatim. Simplified Chinese posts may "
    "echo the source.\n"
    "  en_equivalent:    REQUIRED English-language analyst commentary: a "
    "concise synthesis of what the post means and why it matters. Never use "
    "'N/A' or an empty string. It must not copy the source or text_en. For an "
    "emoji-only post, explain the expressed reaction.\n"
    "  cn_equivalent:    REQUIRED Simplified Chinese analyst commentary in "
    "the natural voice of Chinese netizens on Weibo/Zhihu/Bilibili. Never "
    "use 'N/A' or an empty string. It must not copy the source or literal_zh. "
    "For an emoji-only post, explain the expressed reaction.\n"
    "  annotation:       Optional 1-3 sentence cultural note ONLY for F2/F3 "
    "friction (meme origin, named event). Otherwise empty string.\n"
    "  noop_en:          Optional hint: true if source is already English.\n"
    "  noop_zh:          Optional hint: true if source is already Simplified "
    "Chinese. Server decides columns via lang_detected.\n\n"
    "Fixed-translation dictionary — use these for literal_zh WITHOUT "
    "annotation:\n"
    "  vibe coding → 氛围编程;  sycophancy → 舔狗;  distillation → 蒸馏;\n"
    "  wrapper → 套壳;  fine-tune → 微调;  open-weight → 开放权重;\n"
    "  roast → 毒舌;  based → 敢说真话.\n\n"
    "Rules:\n"
    "1. Return ONLY a JSON object of the form:\n"
    '   {"results": [{"tweet_id": str, "lang_detected": str, '
    '"text_en": str, "literal_zh": str, "en_equivalent": str, '
    '"cn_equivalent": str, '
    '"annotation": str, "noop_en": bool, "noop_zh": bool}, ...]}\n'
    "2. One result per input tweet, in the same order. "
    "lang_detected first on every object.\n"
    "3. Model names, brand names, personal names, @mentions, URLs, and "
    "emojis stay verbatim.\n"
    "4. Do not include any prose, explanation, or code fences outside "
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
            "\n\nFew-shot examples (verified live X posts from 2026-06-26):\n"
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
    """Apply the F0–F3 friction-level judgment (research §6.5).

    Picks an annotation tier based on the post's text content and
    sets `annotation` accordingly. Other fields pass through from
    `llm_yaml` unchanged.

    Note (plan 2026-07-06-001): previously this function also
    coerced the translator's post-level `discourse_role` to the
    9-key vocabulary (mirroring the classifier's per-brand role).
    With `discourse_role` removed from the translator contract,
    the F0 role-set check is also gone — F0 roles are no longer
    distinguished here. The classifier's role taxonomy (per-brand)
    remains authoritative.
    """
    text = (post.get("text") or "").lower()
    raw_annotation = (llm_yaml.get("annotation") or "").strip()

    if any(token in text for token in _FIXED_ZH_TRANSLATIONS):
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
        "annotation": annotation,
    }


def _empty_pragmatics_row(
    tweet: dict[str, Any], failed: bool = False, dry_run: bool = False
) -> dict[str, Any]:
    """Empty-row shape for translation, bilingual commentary, and annotation."""
    row: dict[str, Any] = {
        "tweet_id": str(tweet.get("tweet_id") or tweet.get("id")),
        "brand_id": tweet.get("brand_id"),
        "text_en": None,
        "text_zh_cn": None,
        "literal_zh": None,
        "lang_detected": None,
        "en_equivalent": None,
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


def _is_source_echo(value: object, source_text: object) -> bool:
    """True when a generated value is only the source text repeated verbatim."""
    return (
        isinstance(value, str)
        and isinstance(source_text, str)
        and value.strip() == source_text.strip()
    )


def _finalize_pragmatics_row(
    tweet: dict[str, Any],
    parsed: dict[str, Any],
    *,
    lang_canonical: str,
) -> dict[str, Any]:
    """Apply friction judge + server-side EN/ZH noop for a validated lang."""
    judged = apply_friction_judge(tweet, parsed)
    # Prefer canonical allowlist form for storage and noop checks.
    lang = lang_canonical
    lang_for_family = lang.lower()
    is_already_zh = _is_simplified_chinese_family(lang_for_family)
    is_already_en = _is_english_family(lang_for_family)
    _raw_en = judged.get("text_en")
    _source_text = (tweet.get("text") or "").strip()
    _en_is_echo = not is_already_en and _is_source_echo(_raw_en, _source_text)
    text_en = None if is_already_en or _en_is_echo else _raw_en
    literal_zh_raw = (
        None if is_already_zh
        else (judged.get("literal_zh") or parsed.get("text_zh_cn"))
    )
    text_zh_cn = None if is_already_zh else literal_zh_raw
    return {
        "tweet_id": str(
            parsed.get("tweet_id") or tweet.get("tweet_id") or tweet.get("id")
        ),
        "brand_id": tweet.get("brand_id"),
        "text_en": text_en,
        "text_zh_cn": text_zh_cn,
        "lang_detected": lang_canonical,
        "noop_en": text_en is None,
        "noop_zh": text_zh_cn is None,
        "literal_zh": literal_zh_raw,
        "en_equivalent": judged.get("en_equivalent"),
        "cn_equivalent": judged.get("cn_equivalent"),
        "annotation": judged.get("annotation"),
    }


def _merge_repair_row(
    first: dict[str, Any],
    repair: dict[str, Any],
) -> dict[str, Any]:
    """Merge repair into first-pass row: lang from repair; keep first texts if repair empty."""
    merged = dict(first)
    for key in (
        "lang_detected",
        "text_en",
        "literal_zh",
        "text_zh_cn",
        "en_equivalent",
        "cn_equivalent",
        "annotation",
        "noop_en",
        "noop_zh",
    ):
        if key not in repair:
            continue
        val = repair.get(key)
        if key == "lang_detected":
            merged[key] = val
            continue
        if val is None:
            continue
        if isinstance(val, str) and not val.strip():
            continue
        merged[key] = val
    return merged


def _usable_output(value: object) -> str | None:
    """Return a normalized required output, rejecting blank sentinels."""
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized or normalized.casefold() in {"n/a", "na"}:
        return None
    return normalized


def _commentary_is_distinct(value: object, *source_values: object) -> bool:
    commentary = _usable_output(value)
    if commentary is None:
        return False
    folded = commentary.casefold()
    return all(
        folded != source.casefold()
        for candidate in source_values
        if (source := _usable_output(candidate)) is not None
    )


def missing_pragmatics_outputs(
    tweet: dict[str, Any], row: dict[str, Any]
) -> tuple[str, ...]:
    """Name missing persistence-bearing outputs for one translator row."""
    missing: list[str] = []
    lang = normalize_lang_detected(row.get("lang_detected"))
    if lang is None:
        missing.append("lang_detected")

    source_text = tweet.get("text")
    text_en = row.get("text_en")
    literal_zh = row.get("literal_zh") or row.get("text_zh_cn")
    if (
        lang is not None
        and lang != "en"
        and (
            _usable_output(text_en) is None
            or _is_source_echo(text_en, source_text)
        )
    ):
        missing.append("text_en")
    if lang is not None and lang != "zh-Hans" and _usable_output(literal_zh) is None:
        missing.append("literal_zh")
    if not _commentary_is_distinct(
        row.get("en_equivalent"), source_text, text_en, literal_zh
    ):
        missing.append("en_equivalent")
    if not _commentary_is_distinct(
        row.get("cn_equivalent"), source_text, text_en, literal_zh
    ):
        missing.append("cn_equivalent")
    return tuple(missing)


def _build_pragmatics_repair_prompt(
    tweets: list[dict[str, Any]],
    target_locales: list[str],
    brand_names: list[str] | None = None,
) -> str:
    """Short repair prompt requesting every required persistence output."""
    base = build_pragmatics_translation_prompt(
        tweets,
        target_locales,
        brand_names=brand_names,
        few_shot_examples=[],  # no few-shot on repair — keep small
    )
    addendum = (
        "\n\nREPAIR: A previous response omitted, blanked, used N/A for, "
        "or copied a required output. For EVERY tweet below, return the full "
        "results array again, including distinct non-empty en_equivalent and "
        "cn_equivalent commentary. lang_detected is REQUIRED and must be one of: "
        "en | zh-Hans | zh-Hant | ja | ko | other. Put lang_detected "
        "first on each object. Do not omit it."
    )
    return base + addendum


def translate_batch_pragmatics(
    tweets: list[dict[str, Any]],
    target_locales: list[str],
    client: "ClaudeClient",
    *,
    brand_names: list[str] | None = None,
    few_shot_examples: list[dict[str, Any]] | None = None,
    dry_run: bool = False,
    on_batch_error: "Callable[[list[dict[str, Any]], Exception], None] | None" = None,
    cfg: "Config | None" = None,
    deadline: Any | None = None,
    max_workers: int = 1,
) -> list[dict[str, Any]]:
    """Translate a batch with required bilingual commentary and translations.
    Pass cfg to thread through to model resolution (per swap-translator plan).

    After parse, each row must have an allowlisted language, required target
    translations, and distinct non-empty bilingual commentary. Incomplete rows
    get at most one repair LLM call (bad ids only); residual incomplete output
    becomes a failed empty row.

    on_batch_error (U7): optional callback invoked per-batch when the
    LLM call raised (after retries exhausted) OR the response failed
    to parse. Receives the input batch and the exception (for parse
    failures a synthetic `ValueError("parse failure")` is passed).
    Used by the smoketest to attribute failures to specific tweet_ids.
    """
    if not tweets:
        return []

    if dry_run:
        return [_empty_pragmatics_row(t, dry_run=True) for t in tweets]

    # Independent LLM batches have no data dependency. Running them in stable,
    # bounded parallelism prevents one slow 20-row response from consuming the
    # entire enrichment-stage deadline before the later batches can start.
    # Results are flattened in submission order, preserving the public
    # index-alignment contract. Single-batch callers keep the original path.
    if len(tweets) > _TRANSLATION_BATCH_SIZE and max_workers > 1:
        batches = [
            tweets[start: start + _TRANSLATION_BATCH_SIZE]
            for start in range(0, len(tweets), _TRANSLATION_BATCH_SIZE)
        ]
        callback_lock = threading.Lock()

        def serialized_batch_error(
            batch: list[dict[str, Any]], exc: Exception
        ) -> None:
            if on_batch_error is None:
                return
            with callback_lock:
                on_batch_error(batch, exc)

        with ThreadPoolExecutor(
            max_workers=min(max_workers, len(batches)),
            thread_name_prefix="translator-batch",
        ) as executor:
            futures = [
                executor.submit(
                    translate_batch_pragmatics,
                    batch,
                    target_locales,
                    client,
                    brand_names=brand_names,
                    few_shot_examples=few_shot_examples,
                    on_batch_error=serialized_batch_error,
                    cfg=cfg,
                    deadline=deadline,
                    max_workers=1,
                )
                for batch in batches
            ]
            return [row for future in futures for row in future.result()]

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
            response = _call_with_retry(
                client,
                prompt,
                n_tweets=len(batch),
                cfg=cfg,
                deadline=deadline,
            )
        except Exception as exc:
            logger.warning(
                "translator_batch_failed",
                exc_info=True,
                extra={"batch_size": len(batch), "error_type": type(exc).__name__},
            )
            for t in batch:
                out.append(_empty_pragmatics_row(t, failed=True))
            if on_batch_error is not None:
                on_batch_error(batch, exc)
            continue
        parsed = _parse_pragmatics_response(response, batch)
        if parsed is None:
            logger.warning(
                "translator_batch_failed",
                extra={"batch_size": len(batch), "error_type": "ParseFailure"},
            )
            for t in batch:
                out.append(_empty_pragmatics_row(t, failed=True))
            if on_batch_error is not None:
                on_batch_error(batch, ValueError("parse failure"))
            continue

        # Index first-pass rows by tweet_id (and by position as fallback).
        first_by_tid: dict[str, dict[str, Any]] = {}
        order_tids: list[str] = []
        for t, p in zip(batch, parsed):
            tid = str(p.get("tweet_id") or t.get("tweet_id") or t.get("id") or "")
            order_tids.append(tid)
            first_by_tid[tid] = dict(p)
            first_by_tid[tid]["_tweet"] = t

        incomplete_tids = [
            tid for tid in order_tids
            if missing_pragmatics_outputs(
                first_by_tid[tid]["_tweet"], first_by_tid[tid]
            )
        ]

        if incomplete_tids:
            bad_tweets = [first_by_tid[tid]["_tweet"] for tid in incomplete_tids]
            repair_prompt = _build_pragmatics_repair_prompt(
                bad_tweets, target_locales, brand_names=brand_names
            )
            try:
                repair_resp = _call_with_retry(
                    client,
                    repair_prompt,
                    n_tweets=len(bad_tweets),
                    cfg=cfg,
                    deadline=deadline,
                )
                repair_parsed = _parse_pragmatics_response(repair_resp, bad_tweets)
            except Exception as exc:
                logger.warning(
                    "translator_lang_repair_failed",
                    exc_info=True,
                    extra={"n_incomplete": len(incomplete_tids), "error_type": type(exc).__name__},
                )
                repair_parsed = None
                if on_batch_error is not None:
                    on_batch_error(bad_tweets, exc)

            if repair_parsed is not None:
                for t, rp in zip(bad_tweets, repair_parsed):
                    tid = str(
                        rp.get("tweet_id") or t.get("tweet_id") or t.get("id") or ""
                    )
                    if tid not in first_by_tid:
                        # Map by position if id drift
                        continue
                    first_by_tid[tid] = _merge_repair_row(first_by_tid[tid], rp)
                    first_by_tid[tid]["_tweet"] = t
                logger.info(
                    "translator_output_repair_attempted n_incomplete=%d",
                    len(incomplete_tids),
                )
            else:
                logger.warning(
                    "translator_output_repair_parse_failed n_incomplete=%d",
                    len(incomplete_tids),
                )

        for tid in order_tids:
            row0 = first_by_tid[tid]
            t = row0.get("_tweet") or {"tweet_id": tid}
            canonical = normalize_lang_detected(row0.get("lang_detected"))
            if canonical is None:
                logger.warning(
                    "translator_lang_missing tweet_id=%s after_repair",
                    tid,
                )
                out.append(_empty_pragmatics_row(t, failed=True))
                continue
            missing_outputs = missing_pragmatics_outputs(t, row0)
            if missing_outputs:
                logger.warning(
                    "translator_output_incomplete tweet_id=%s after_repair missing=%s",
                    tid,
                    ",".join(missing_outputs),
                )
                out.append(_empty_pragmatics_row(t, failed=True))
                continue
            # Strip internal bookkeeping before finalize
            clean = {k: v for k, v in row0.items() if k != "_tweet"}
            clean["lang_detected"] = canonical
            out.append(_finalize_pragmatics_row(t, clean, lang_canonical=canonical))
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
    cfg: "Config | None" = None,
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
            response = _call_with_retry(client, prompt, n_tweets=len(batch), cfg=cfg)
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
        # 2026-07-22: explicit timeout + retry to fix the ~37% SSL read hang
        # failure rate. The Anthropic SDK defaults to 600s timeout with no
        # retries; a hung SSL connection ties up a batch for 10 minutes
        # before failing. Bumped from 60s -> 120s on 2026-08-04 (plan
        # 2026-08-04-001 KTD4): DS V4 at batch_size=20 with rich
        # translation fields takes ~20s but can hit 60s on rich
        # batches; 120s gives 6x headroom. 2 retries with jitter
        # gives the hung batch a fresh connection on retry.
        kwargs.setdefault("timeout", 120.0)
        # Retry ownership belongs to _call_with_retry, where the shared
        # enrichment-attempt deadline can stop further work deterministically.
        kwargs.setdefault("max_retries", 0)
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
        # Trailing-prose-tolerant parser (plan 2026-08-04-001).
        # Replaces the inline json.loads() that raised on trailing prose.
        # Soft-fails to {"results": []} on parse failure; the consumer
        # (translate_batch -> _parse_response) handles empty results
        # by marking the batch as translation_failed=True.
        return parse_llm_response(
            raw,
            logger_name="x_monitor.translator",
            fallback={"results": []},
        )
