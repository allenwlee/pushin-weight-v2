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
