# {{AGENT_ATTRIBUTION}}
"""Multi-brand call-path attribution pipeline for x-monitor v1.8.

Companion to `x_monitor.intent_classifier` (v1.7 single-brand). v1.8
replaces first-match-wins with all-matches-wins: a single tweet may
attribute to multiple brands, and every detected brand gets its own
row in `posts_brands`, `posts_brands_mentions`, and `posts_brands_signals`.

Four extraction sources (Decision 6 in the schema plan):
  - `user_mention`   - `entities.user_mentions[].id` resolves via
                       `brands_accounts` (numeric X user id -> brand_id).
  - `hashtag`         - `entities.hashtags[].tag` resolves via
                       `brand_hashtags` (case-insensitive, no '#').
  - `body_keyword`    - `post.text` scanned once with a precompiled
                       alternation regex over all brand_keywords.
  - `search_term`     - `posts.source_query_id` joined to
                       `search_queries.query_id` for the keywords[].

Plus:
  - `compute_post_brands` consolidates per-source MentionRows into
    one row per distinct brand with fractional weight (Decision 9).
  - `classify_post(text, brand_ids)` asks Claude Haiku for a per-brand
    (post_type, sentiment) decomposition; hallucinates brand_ids are
    dropped (R8). U9 replaces the legacy 6-signal taxonomy.

This module has zero side effects on import. The Store writes happen
in `x_monitor.store.Store.insert_posts` (Unit 2). This module is pure:
extract, consolidate, classify.

See docs/plans/2026-06-19-004-feat-call-path-attribution-pipeline-plan.md
section "Unit 1: New x_monitor/attribution.py module" (R1-R8).
"""

from __future__ import annotations

import json
import logging
import re
import time

from ._json_parser import parse_llm_response
from .llm_budget import LlmBudgetExhausted
from dataclasses import dataclass
from typing import Any, Literal, Protocol


logger = logging.getLogger(__name__)


# --- Type aliases --------------------------------------------------------


Source = Literal[
    "author_account", "user_mention", "hashtag", "body_keyword", "search_term"
]


# Alias for tests / external callers that prefer the explicit type name.
# Kept identical to `Source` so callers can use either.
SourceType = Source


# Source-confidence priority (R2). user_mention + hashtag are higher
# confidence than body_keyword + search_term because they are explicit
# brand signals (someone typed the handle or hashtag). Mixed signals
# take the MAX confidence across contributing sources.
BRAND_SOURCE_PRIORITY: dict[Source, float] = {
    "author_account": 1.0,
    "user_mention":  1.0,
    "hashtag":       0.9,
    "body_keyword":  0.7,
    "search_term":   0.6,
}


# Sentinel brand id (Decision 15). When a post has no detected brand
# from any source, the consolidator emits a `_unattributed` row so the
# post is still queryable. The treemap/dashboard filter excludes this
# sentinel at the read side (posts_brands_signals has a CHECK constraint
# blocking the sentinel entirely).
UNATTRIBUTED_BRAND_ID: str = "_unattributed"


# --- MentionRow (Decision 13 raw_token format) ---------------------------


def validate_raw_token(source: Source, raw_token: str) -> None:
    """Validate a raw_token matches Decision 13's per-source format.

    Raises:
        ValueError: when raw_token doesn't match the expected format.

    Format contract:
      - `user_mention`  must start with '@'; non-empty handle after the @
      - `hashtag`       must start with '#'; non-empty tag after the #
      - `body_keyword`  bare substring (no prefix, no surrounding
                        whitespace); must be the matched substring;
                        non-empty
      - `search_term`   ALLOWS empty string (R6 sentinel row) — empty
                        raw_token is legitimate when no search keyword
                        matched and the extractor emits a provenance
                        placeholder. Any non-empty string is accepted
                        as-is (the keyword from `brand_search_terms`).
    """
    # Type check always fires. Empty check fires for sources where
    # empty raw_token would indicate malformed input — NOT for
    # `search_term`, where R6 explicitly allows empty as a sentinel
    # value (see below).
    if not isinstance(raw_token, str):
        raise ValueError(
            f"raw_token for {source!r} must be a string; "
            f"got {type(raw_token).__name__}"
        )
    if source != "search_term" and not raw_token:
        raise ValueError(
            f"raw_token for {source!r} must be a non-empty string; "
            f"got {raw_token!r}"
        )
    if source == "user_mention":
        if not raw_token.startswith("@"):
            raise ValueError(
                f"user_mention raw_token must start with '@'; "
                f"got {raw_token!r}"
            )
        handle = raw_token[1:]
        if not handle:
            raise ValueError(
                f"user_mention raw_token has empty handle: {raw_token!r}"
            )
        if len(handle) > 15:
            raise ValueError(
                f"user_mention handle too long (>15 chars): {raw_token!r}"
            )
    elif source == "hashtag":
        if not raw_token.startswith("#"):
            raise ValueError(
                f"hashtag raw_token must start with '#'; "
                f"got {raw_token!r}"
            )
        if len(raw_token) <= 1:
            raise ValueError(
                f"hashtag raw_token has empty tag: {raw_token!r}"
            )
    elif source == "body_keyword":
        if raw_token.startswith("@") or raw_token.startswith("#"):
            raise ValueError(
                f"body_keyword raw_token must be bare substring "
                f"(no '@' or '#' prefix); got {raw_token!r}"
            )
        if raw_token != raw_token.strip():
            raise ValueError(
                f"body_keyword raw_token must not have surrounding "
                f"whitespace; got {raw_token!r}"
            )
    elif source == "author_account":
        # Stable author ID plus membership/role provenance, assembled by
        # monitor.cycle after current list membership and role resolution.
        pass
    elif source == "search_term":
        # R6: when no search keyword matches the registry, the
        # extractor still emits a sentinel MentionRow with
        # brand_id=None and raw_token="" so the search provenance
        # ("post entered the pipeline via Call X but we can't link
        # it to a brand") is preserved for later backfill. Empty
        # raw_token is legitimate for search_term ONLY — the other
        # 3 sources still reject empty (it would mean malformed
        # input, not "no match").
        pass
    else:
        raise ValueError(f"unknown source: {source!r}")


@dataclass(frozen=True)
class MentionRow:
    """A single (post, brand, source) triple to be written to posts_brands_mentions.

    Fields:
        post_id:       the tweet_id (string)
        brand_id:      resolved brand_id (or None for un-attributed
                       user_mentions we want to preserve for later
                       backfill; NULL brand_id is allowed by the PK)
        source:        one of user_mention/hashtag/body_keyword/search_term
        raw_token:     per-source format (see validate_raw_token)
        mentioned_at:  ISO-8601 UTC timestamp; denormalized from
                       posts.created_at so posts_brands_mentions is queryable
                       without a JOIN to posts.
    """

    post_id: str
    brand_id: str | None
    source: Source
    raw_token: str
    mentioned_at: str

    def __post_init__(self) -> None:
        # Decision 13: enforce raw_token format at construction time.
        validate_raw_token(self.source, self.raw_token)


@dataclass(frozen=True)
class BrandRow:
    """A row from the `brands` table (per R12 / migration 004)."""

    brand_id: str
    display_name: str
    accent_color: str
    is_sentinel: bool


# --- Entity normalization helpers ----------------------------------------


def _is_cjk(token: str) -> bool:
    """Return True if the token contains any CJK Unified Ideograph.

    Mirrors `intent_classifier._is_cjk`. Used by `compile_keyword_index`
    to decide whether to wrap a bare-substring pattern with a \\b word
    boundary (ASCII tokens) or use substring match (CJK tokens, where
    Python's \\b doesn't anchor correctly between CJK and non-CJK).
    """
    return any("一" <= ch <= "鿿" for ch in token)


def _normalize_entities(entities: Any) -> dict[str, Any]:
    """Coerce `entities` to a dict, handling JSON strings and None.

    TwitterAPI.io returns `entities` either as a parsed dict or as a
    JSON-encoded string. The migrator occasionally stores the literal
    string 'null' (which is valid JSON for None). All three cases are
    handled here so the extractors can iterate without type checks.
    """
    if entities is None:
        return {}
    if isinstance(entities, dict):
        return entities
    if isinstance(entities, str):
        if entities.strip().lower() in ("null", ""):
            return {}
        try:
            parsed = json.loads(entities)
        except (ValueError, TypeError):
            logger.warning(
                "attribution: entities is a non-JSON string; "
                "treating as empty dict: %r",
                entities[:120],
            )
            return {}
        if parsed is None:
            return {}
        if isinstance(parsed, dict):
            return parsed
        logger.warning(
            "attribution: entities JSON is not a dict (type=%s); "
            "treating as empty",
            type(parsed).__name__,
        )
        return {}
    logger.warning(
        "attribution: entities is unexpected type %s; treating as empty",
        type(entities).__name__,
    )
    return {}


# --- Extractor 1: user_mentions (R3) -------------------------------------


def extract_user_mentions(
    post: dict[str, Any],
    brands_accounts: dict[str, str],
    entities: Any,
) -> list[MentionRow]:
    """Emit one MentionRow per @handle in `entities.user_mentions[]`.

    The numeric X user id (entities.user_mentions[].id) is the FK into
    `brands_accounts.author_id`. Unknown handles are preserved with
    brand_id=None so the raw `@handle` token survives for backfill.

    Args:
        post:            a post dict with at least `tweet_id` (or `id`)
                         and `created_at`
        brands_accounts:  {author_id (str): brand_id} map (numeric id
                         keyed; TwitterAPI.io returns id as str via
                         JSON but it's semantically numeric)
        entities:        post["entities"], may be dict/str/None

    Returns:
        List of MentionRow with source='user_mention'. May be empty
        when entities has no user_mentions[] or when post lacks
        tweet_id/created_at.
    """
    post_id = str(post.get("tweet_id") or post.get("id") or "")
    mentioned_at = str(post.get("created_at") or "")
    if not post_id or not mentioned_at:
        return []

    ents = _normalize_entities(entities)
    mentions = ents.get("user_mentions")
    if not isinstance(mentions, list):
        return []

    out: list[MentionRow] = []
    for m in mentions:
        if not isinstance(m, dict):
            continue
        author_id = m.get("id")
        username = m.get("username") or m.get("screen_name")
        if not author_id or not username:
            continue
        author_id_str = str(author_id)
        brand_id = brands_accounts.get(author_id_str)
        raw_token = f"@{username}"
        out.append(MentionRow(
            post_id=post_id,
            brand_id=brand_id,
            source="user_mention",
            raw_token=raw_token,
            mentioned_at=mentioned_at,
        ))
    return out


# --- Extractor 2: hashtags (R4) -----------------------------------------


def extract_hashtag_mentions(
    post: dict[str, Any],
    brand_hashtags: dict[str, str],
    entities: Any,
) -> list[MentionRow]:
    """Emit one MentionRow per #tag in `entities.hashtags[]`.

    Hashtags are case-insensitive and stored without '#' in the
    `brand_hashtags` table (per R4). Unknown hashtags produce NO row
    (they're considered noise; the raw_token isn't preserved).

    Args:
        post:            a post dict with at least `tweet_id` and
                         `created_at`
        brand_hashtags:  {tag (str, lowercase): brand_id} map
        entities:        post["entities"], may be dict/str/None

    Returns:
        List of MentionRow with source='hashtag'. Empty when entities
        has no hashtags[] or when none match.
    """
    post_id = str(post.get("tweet_id") or post.get("id") or "")
    mentioned_at = str(post.get("created_at") or "")
    if not post_id or not mentioned_at:
        return []

    ents = _normalize_entities(entities)
    tags = ents.get("hashtags")
    if not isinstance(tags, list):
        return []

    out: list[MentionRow] = []
    for t in tags:
        if not isinstance(t, dict):
            continue
        tag = t.get("tag")
        if not tag:
            continue
        tag_lower = str(tag).lower().lstrip("#")
        if not tag_lower:
            continue
        brand_id = brand_hashtags.get(tag_lower)
        if brand_id is None:
            # Unknown hashtag: silently dropped (R4: noise is not
            # preserved in posts_brands_mentions for the hashtag source).
            continue
        raw_token = f"#{tag_lower}"
        out.append(MentionRow(
            post_id=post_id,
            brand_id=brand_id,
            source="hashtag",
            raw_token=raw_token,
            mentioned_at=mentioned_at,
        ))
    return out


# --- Extractor 3: body keywords (R5) ------------------------------------


def compile_keyword_index(
    brand_keywords: list[tuple[str, str, bool]],
) -> tuple[re.Pattern[str] | None, dict[str, str]]:
    """Compile all `brand_keywords` into a single alternation regex.

    Mirrors the v1.7 `build_compiled_brand_pattern` from
    `x_monitor.intent_classifier` (Decision 3 in the v1.7 plan) but
    extended for the multi-brand case.

    CJK tokens use substring match (no \\b) because the Python re
    engine treats CJK as \\W and \\b does not anchor correctly at
    CJK/non-CJK boundaries. ASCII tokens use word-boundary to avoid
    matching "Kimi" inside "Kimimania". Regex patterns are used
    verbatim (caller is responsible for their correctness).

    Args:
        brand_keywords: list of (brand_id, pattern, is_regex) tuples
                        loaded from `Store.read_brand_keywords()`. The
                        `is_regex` flag distinguishes "bare substring"
                        patterns (wrapped with \\b for ASCII, no \\b
                        for CJK) from "regex" patterns (used verbatim).

    Returns:
        (compiled_pattern, token_to_brand) tuple. `token_to_brand`
        maps the LITERAL matched substring (after escape) back to its
        brand_id. For regex patterns, the key is the raw pattern
        string (NOT the matched substring). `extract_body_keywords`
        handles the regex-pattern case by checking which brand owns
        the matched substring via a casefold scan of the pattern
        keys. Returns (None, {}) when brand_keywords is empty.
    """
    parts: list[str] = []
    token_to_brand: dict[str, str] = {}
    for brand_id, pattern, is_regex in brand_keywords:
        if not pattern:
            continue
        if is_regex:
            try:
                re.compile(f"({pattern})", re.IGNORECASE)
            except re.error as e:
                logger.warning(
                    "compile_keyword_index: skipping invalid regex "
                    "%r for brand %r: %s",
                    pattern, brand_id, e,
                )
                continue
            parts.append(f"({pattern})")
            # Key by the raw pattern (NOT the matched substring). The
            # matched text varies per post, so extract_body_keywords
            # falls through to per-pattern re-test to identify the
            # owner brand. First-seen wins (matches v1.7 contract).
            if pattern not in token_to_brand:
                token_to_brand[pattern] = brand_id
        else:
            esc = re.escape(pattern)
            if _is_cjk(pattern):
                # CJK: substring, no \b (Python \b doesn't anchor
                # correctly at CJK/non-CJK boundaries).
                parts.append(f"({esc})")
                if esc not in token_to_brand:
                    token_to_brand[esc] = brand_id
            else:
                parts.append(r"\b(" + esc + r")\b")
                if esc not in token_to_brand:
                    token_to_brand[esc] = brand_id
    if not parts:
        return None, {}
    compiled = re.compile("|".join(parts), re.IGNORECASE)
    return compiled, token_to_brand


def detect_brand_mentions(
    text: str,
    compiled_keyword_index: tuple[re.Pattern[str] | None, dict[str, str]],
) -> list[str]:
    """Return deduplicated brand_ids mentioned in `text`.

    Companion to `extract_body_keywords` for the U4 post-fetch
    path: instead of emitting a MentionRow per match, return the
    SET of brand_ids found (so the LLM classifier can iterate
    deterministically across them). Reuses the same regex
    resolution as the body-keyword path.

    The order is "first-seen wins" (matches v1.7 contract) — useful
    for downstream rank/weight heuristics.

    Args:
        text: the post text to scan
        compiled_keyword_index: (pattern, token_to_brand) tuple from
                                `compile_keyword_index()`

    Returns:
        A list of deduplicated brand_id slugs. Empty when no
        pattern, no text, or no matches.
    """
    pattern, token_to_brand = compiled_keyword_index
    if pattern is None or not token_to_brand or not text:
        return []
    regex_keys = [k for k in token_to_brand if any(
        c in k for c in "()[]{}.*+?\\^$|"
    )]
    seen: set[str] = set()
    out: list[str] = []
    for m in pattern.finditer(text):
        raw_token = m.group(0)
        brand_id: str | None = None
        # 1. Literal lookup.
        brand_id = token_to_brand.get(raw_token)
        if brand_id is None:
            cf = raw_token.casefold()
            for tok, b in token_to_brand.items():
                if tok.casefold() == cf:
                    brand_id = b
                    break
        # 2. Regex-pattern re-test.
        if brand_id is None and regex_keys:
            for pat_str in regex_keys:
                try:
                    if re.fullmatch(pat_str, raw_token, re.IGNORECASE):
                        brand_id = token_to_brand[pat_str]
                        break
                except re.error:
                    continue
        if brand_id is None or brand_id == UNATTRIBUTED_BRAND_ID:
            continue
        if brand_id not in seen:
            seen.add(brand_id)
            out.append(brand_id)
    return out


def extract_body_keywords(
    post: dict[str, Any],
    compiled_keyword_index: tuple[re.Pattern[str] | None, dict[str, str]],
) -> list[MentionRow]:
    """Emit one MentionRow per match of `compiled_keyword_index` in text.

    Single `re.finditer` scan over the union pattern. Each match
    becomes a MentionRow with `raw_token=<match.group(0)>` (Decision
    13: bare substring for body_keyword source). Matches resolving
    to `_unattributed` are filtered out (R5).

    For regex-pattern entries (`is_regex=True`), the matched substring
    is NOT a key in `token_to_brand` (the key is the raw pattern).
    To resolve the brand_id, we re-test each regex-pattern candidate
    against the matched substring via `fullmatch`. First regex wins,
    matching the v1.7 first-match-wins contract.

    Args:
        post:                   a post dict with at least `tweet_id`,
                                `created_at`, and `text`
        compiled_keyword_index: (pattern, token_to_brand) tuple from
                                `compile_keyword_index()`

    Returns:
        List of MentionRow with source='body_keyword'. Empty when
        no pattern, no text, or no matches.
    """
    post_id = str(post.get("tweet_id") or post.get("id") or "")
    mentioned_at = str(post.get("created_at") or "")
    text = post.get("text") or ""
    if not post_id or not mentioned_at or not text:
        return []

    pattern, token_to_brand = compiled_keyword_index
    if pattern is None or not token_to_brand:
        return []

    # Pre-compile per-regex candidates so we can re-test the matched
    # substring to identify the owner brand. Only entries whose key
    # contains regex metacharacters are tested this way; literal
    # entries hit the token_to_brand.get path on the first try.
    regex_keys = [k for k in token_to_brand if any(
        c in k for c in "()[]{}.*+?\\^$|"
    )]

    out: list[MentionRow] = []
    for m in pattern.finditer(text):
        raw_token = m.group(0)
        brand_id: str | None = None
        # 1. Try literal-token lookup first.
        brand_id = token_to_brand.get(raw_token)
        if brand_id is None:
            cf = raw_token.casefold()
            for tok, b in token_to_brand.items():
                if tok.casefold() == cf:
                    brand_id = b
                    break
        # 2. Fall back to per-regex re-test. Re-compile on the fly;
        #    the index is built once per cycle so this is amortized.
        if brand_id is None and regex_keys:
            for pat_str in regex_keys:
                try:
                    if re.fullmatch(pat_str, raw_token, re.IGNORECASE):
                        brand_id = token_to_brand[pat_str]
                        break
                except re.error:
                    continue
        if brand_id is None:
            continue
        if brand_id == UNATTRIBUTED_BRAND_ID:
            # R5: filter out sentinel matches.
            continue
        out.append(MentionRow(
            post_id=post_id,
            brand_id=brand_id,
            source="body_keyword",
            raw_token=raw_token,
            mentioned_at=mentioned_at,
        ))
    return out


# --- Extractor 4: search terms (R6) -------------------------------------


def extract_search_term_match(
    post: dict[str, Any],
    search_query: list[str],
    brand_search_terms: dict[str, str],
) -> list[MentionRow]:
    """Emit one MentionRow per matching `(brand_id, term)` pair.

    The search-term source records "why this post entered the
    pipeline" (the keywords that matched on the TwitterAPI.io side).
    If no keyword matches, emits ONE row with brand_id=None so the
    search provenance is preserved for later backfill (R6: "Always
    emits at least one row per post").

    Args:
        post:              a post dict with at least `tweet_id` and
                           `created_at`
        search_query:      the keywords[] array from search_queries
                           (looked up via source_query_id)
        brand_search_terms: {term: brand_id} map

    Returns:
        List of MentionRow with source='search_term'. Always has
        at least one entry (possibly with brand_id=None).
    """
    post_id = str(post.get("tweet_id") or post.get("id") or "")
    mentioned_at = str(post.get("created_at") or "")
    if not post_id or not mentioned_at:
        return []

    out: list[MentionRow] = []
    matched_any = False
    if search_query:
        for term in search_query:
            if not term:
                continue
            brand_id = brand_search_terms.get(term)
            if brand_id is None:
                cf = term.casefold()
                for k, v in brand_search_terms.items():
                    if k.casefold() == cf:
                        brand_id = v
                        break
            if brand_id is None:
                continue
            out.append(MentionRow(
                post_id=post_id,
                brand_id=brand_id,
                source="search_term",
                raw_token=term,
                mentioned_at=mentioned_at,
            ))
            matched_any = True
    if not matched_any:
        # R6: preserve the search provenance even when no keyword
        # matched (the post was returned by the API call but we
        # can't link it to a brand via the search-term path).
        out.append(MentionRow(
            post_id=post_id,
            brand_id=None,
            source="search_term",
            raw_token="",
            mentioned_at=mentioned_at,
        ))
    return out


# --- compute_post_brands (R7) -------------------------------------------


def compute_post_brands(
    post: dict[str, Any],
    all_mentions: list[MentionRow],
) -> list[tuple[str, float]]:
    """Consolidate all_mentions into per-brand fractional weights.

    Union of non-NULL brand_ids across all_mentions. Each distinct
    brand gets weight = 1.0 / N (Decision 9). Empty union returns
    `[('_unattributed', 1.0)]` so the post is still queryable.

    Args:
        post:         the post dict (unused except for shape consistency)
        all_mentions: the combined MentionRow list from the 4 extractors

    Returns:
        List of `(brand_id, weight)` tuples. Weights sum to 1.0
        (or are `[('_unattributed', 1.0)]` when no brand was found).
    """
    seen: list[str] = []
    for m in all_mentions:
        if m.brand_id and m.brand_id not in seen:
            seen.append(m.brand_id)
    if not seen:
        return [("_unattributed", 1.0)]
    weight = 1.0 / len(seen)
    # Stable sort by brand_id so callers get a deterministic order
    # (tests assert a specific ordering on the returned list).
    seen_sorted = sorted(seen)
    return [(b, weight) for b in seen_sorted]


# --- Top-level attribute_to_brands (R2) ---------------------------------


def attribute_to_brands(
    post: dict[str, Any],
    brands_accounts: dict[str, str],
    brand_hashtags: dict[str, str],
    compiled_keyword_index: tuple[re.Pattern[str] | None, dict[str, str]],
    search_query: list[str],
    brand_search_terms: dict[str, str],
) -> list[MentionRow]:
    """End-to-end: 4 extractors -> consolidated MentionRow list.

    Runs all 4 extractors (R3-R6) and returns the union as a
    `list[MentionRow]`, deduped by `(brand_id, source)`. The list is
    directly consumable by `compute_post_brands(post, mentions)` to
    derive fractional weights, or by callers that need the per-row
    provenance.

    Per-brand confidence (R2) is derivable per row via
    `BRAND_SOURCE_PRIORITY[m.source]`; the highest source priority
    contributing to a brand gives the per-brand confidence.

    Args:
        post:                   the post dict
        brands_accounts:         {author_id: brand_id}
        brand_hashtags:         {tag: brand_id} (lowercase keys)
        compiled_keyword_index: (pattern, token_to_brand) from
                                `compile_keyword_index`
        search_query:           keywords[] for this post's
                                source_query_id
        brand_search_terms:     {term: brand_id}

    Returns:
        List of MentionRow (one per `(brand_id, source)` dedup).
        When no brand is found, returns a single sentinel MentionRow
        with brand_id=UNATTRIBUTED_BRAND_ID so the consolidator still
        produces a `(UNATTRIBUTED_BRAND_ID, 1.0)` weight.
    """
    entities = post.get("entities")
    mentions: list[MentionRow] = []
    mentions.extend(extract_user_mentions(post, brands_accounts, entities))
    mentions.extend(extract_hashtag_mentions(post, brand_hashtags, entities))
    mentions.extend(extract_body_keywords(post, compiled_keyword_index))
    mentions.extend(extract_search_term_match(post, search_query, brand_search_terms))

    # Dedup by (brand_id, source). user_mention + hashtag share source
    # values with body_keyword + search_term but they're independent
    # extraction paths, so dedup keeps the first-seen row. Rows with
    # brand_id=None (the search-term sentinel) are filtered here so
    # the returned list represents only *detected* brands — callers
    # like `compute_post_brands` then operate on a clean union.
    seen: set[tuple[str | None, str]] = set()
    deduped: list[MentionRow] = []
    for m in mentions:
        if m.brand_id is None:
            continue
        key = (m.brand_id, m.source)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(m)
    return deduped


# --- classify_post (R8, U9) ---------------------------------------------
# U9: replaces the legacy `classify_signal` (6-bucket single-string
# signal taxonomy) with a per-brand (post_type, sentiment) tuple
# classification. The legacy signals table was dropped in migration 022;
# the new `post_type_keys` + `sentiment_keys` tables are the source of
# truth.


class ClaudeClient(Protocol):
    """The minimal interface for the per-brand signal classifier.

    Mirrors `x_monitor.translator.ClaudeClient`. The real impl is
    `AnthropicClaudeClient` below; tests inject `FakeClaudeClient`.
    """

    def messages_create(self, **kwargs: Any) -> dict[str, Any]: ...


def _resolve_signal_model(cfg: "Config | None" = None) -> str:
    """Return the model id for signal classification.

    Resolution order (plan 2026-08-01-002 U2):
      1. `cfg.llm.signal_model` when cfg is provided (single source of truth).
      2. X_MONITOR_CLASSIFIER_MODEL env var (classifier-specific override)
      3. ANTHROPIC_MODEL env var (set by the operator's shell / wrapper)
      4. "MiniMax-M3.0" if classifier base URL routes through api.minimax.io
      5. "deepseek-v4-pro" if classifier base URL routes through api.deepseek.com
      6. "claude-haiku-4-5" default (when talking to api.anthropic.com directly)
    """
    import os
    if cfg is not None and getattr(cfg.llm, "signal_model", None):
        return cfg.llm.signal_model
    explicit = os.environ.get("X_MONITOR_CLASSIFIER_MODEL") or os.environ.get("ANTHROPIC_MODEL")
    if explicit:
        return explicit
    base_url = os.environ.get(
        "X_MONITOR_CLASSIFIER_BASE_URL",
        os.environ.get("ANTHROPIC_BASE_URL", ""),
    )
    if "minimax.io" in base_url:
        return "MiniMax-M3.0"
    if "deepseek.com" in base_url:
        return "deepseek-v4-pro"
    return "claude-haiku-4-5"


def _resolve_thinking_default(base_url: str = "", *, role: str = "classifier") -> "dict | None":
    """Return the `thinking` kwarg for the Anthropic SDK messages.create call.

    When routing through the DeepSeek V4 Pro endpoint, the model is a
    reasoning model that would consume the entire output budget on
    internal deliberation unless `thinking={"type": "disabled"}` is
    passed. The MiniMax M3 path and direct Anthropic path do not need
    this — return `None` so the parameter is omitted from the SDK call
    and behavior is unchanged from the pre-swap state.

    Args:
        base_url: the actual base URL the call will be made against.
                  Caller passes the resolved URL (not the operator's
                  other env config). Empty string falls back to the
                  per-role override + ANTHROPIC_BASE_URL.
        role: "classifier" (default) or "translator". Determines
              which per-role override env var is read when base_url
              is empty: "classifier" -> X_MONITOR_CLASSIFIER_BASE_URL,
              "translator" -> X_MONITOR_TRANSLATOR_BASE_URL.

    Returns:
        {"type": "disabled"} for the DeepSeek path, else None.
    """
    import os
    if not base_url:
        if role == "translator":
            base_url = os.environ.get(
                "X_MONITOR_TRANSLATOR_BASE_URL",
                os.environ.get("ANTHROPIC_BASE_URL", ""),
            )
        else:
            base_url = os.environ.get(
                "X_MONITOR_CLASSIFIER_BASE_URL",
                os.environ.get("ANTHROPIC_BASE_URL", ""),
            )
    if "deepseek.com" in base_url:
        return {"type": "disabled"}
    return None


def _resolve_translator_model(cfg: "Config | None" = None) -> str:
    """Return the model name for the translator.

    Resolution order:
      1. `cfg.llm.translator_model` when cfg is provided (single source of truth).
      2. ANTHROPIC_MODEL env var (operator shell / wrapper override).
      3. Otherwise infer from the base URL the call will actually route
         to. The translator has a per-role override env var
         (X_MONITOR_TRANSLATOR_BASE_URL) that takes priority over the
         process-wide ANTHROPIC_BASE_URL — without this, the inference
         path would see the env-group's stale ANTHROPIC_BASE_URL
         (api.minimax.io) and return the legacy "MiniMax-M3.0" even
         though the actual translator client is calling DeepSeek.
         Mirrors the role-aware resolution in
         _resolve_thinking_default(role="translator").

    Inference rules:
      - "deepseek.com" in base_url -> "deepseek-v4-pro"
      - "minimax.io"   in base_url -> "MiniMax-M3.0"
      - otherwise                  -> "claude-haiku-4-5"
    """
    import os
    if cfg is not None and getattr(cfg.llm, "translator_model", None):
        return cfg.llm.translator_model
    explicit = os.environ.get("ANTHROPIC_MODEL")
    if explicit:
        return explicit
    # Read the role-specific override FIRST, then fall back to the
    # process-wide ANTHROPIC_BASE_URL. This is the parallel fix to
    # commit f77cb90 which fixed the same precedence rule on the
    # base-URL path; the model-name inference was reading the
    # env-group's stale ANTHROPIC_BASE_URL and selecting MiniMax-M3.0
    # even when X_MONITOR_TRANSLATOR_BASE_URL routed to DeepSeek.
    base_url = os.environ.get(
        "X_MONITOR_TRANSLATOR_BASE_URL",
        os.environ.get("ANTHROPIC_BASE_URL", ""),
    )
    if "deepseek.com" in base_url:
        return "deepseek-v4-pro"
    if "minimax.io" in base_url:
        return "MiniMax-M3.0"
    return "claude-haiku-4-5"


_TRANSLATOR_MODEL = _resolve_translator_model()
_SIGNAL_MODEL = _resolve_signal_model()
_MAX_RETRIES = 3
_BACKOFF_BASE_SECONDS = 1.0


def build_signal_prompt(text: str, brand_ids: list[str]) -> str:
    """Build the LLM prompt for per-brand (post_type, sentiment) classification.

    U9 (replaces the legacy 6-bucket single-string signal taxonomy with
    a (post_type × sentiment) decomposition):

      post_type (4 buckets — what KIND of post):
        - buzz_releases           (brand announced something new)
        - hands_on_usage          (user is using / showing the brand)
        - performance_comparisons (benchmark / eval / head-to-head)
        - feedback_questions      (user asking how-to / help / complaint)

      sentiment (4 values — the VALENCE):
        - positive                (praise, enthusiasm)
        - negative                (criticism, disappointment)
        - neutral                 (informational / question)
        - mixed                   (multiple valences in one post)

    The prompt asks for one (post_type, sentiment) tuple per brand_id.
    The model is told to OMIT brands where the tweet isn't actually
    about that brand.
    """
    brand_list = ", ".join(brand_ids) if brand_ids else "(none)"
    return (
        "You classify a tweet's relationship to a list of brands.\n\n"
        "Tweet text:\n"
        f"\"\"\"\n{text}\n\"\"\"\n\n"
        f"Brands (in order): {brand_list}\n\n"
        "For each brand, return a (post_type, sentiment) tuple from these "
        "exact sets:\n\n"
        "post_type:\n"
        "  - buzz_releases           (brand announced something new)\n"
        "  - hands_on_usage          (user is using / showing the brand)\n"
        "  - performance_comparisons (benchmark / eval / head-to-head)\n"
        "  - feedback_questions      (user asking how-to / help / complaint)\n\n"
        "sentiment:\n"
        "  - positive                (praise, enthusiasm)\n"
        "  - negative                (criticism, disappointment)\n"
        "  - neutral                 (informational / question)\n"
        "  - mixed                   (multiple valences in one post)\n\n"
        "Rules:\n"
        "1. Return ONLY a JSON object: {\"classifications\": "
        "[{\"brand_id\": str, \"post_type\": str, \"sentiment\": str}, ...]}\n"
        "2. One entry per brand you classify (you may OMIT brands "
        "that don't apply).\n"
        "3. Use the EXACT brand_id strings from the list above.\n"
        "4. If the tweet is off-topic for all brands, return "
        "{\"classifications\": []}.\n"
        "5. No prose, no explanation, no code fences.\n"
    )


def _parse_signal_response(
    response: dict[str, Any],
    brand_ids: list[str],
    brand_registry_ids: set[str],
) -> dict[str, tuple[str, str]]:
    """Parse the LLM response, validate brand_ids, drop hallucinations.

    U9: returns {brand_id: (post_type, sentiment)} tuples.

    Args:
        response:           the LLM response dict (already JSON-decoded)
        brand_ids:          the list of brand_ids we asked about
        brand_registry_ids: set of valid brand_ids (from BrandRow list)

    Returns:
        {brand_id: (post_type, sentiment)} dict. Hallucinated
        brand_ids are dropped. Unknown post_type or sentiment values
        are coerced to ('hands_on_usage', 'neutral') (the 019/022
        fallback values).
    """
    valid_post_types = {
        "buzz_releases", "hands_on_usage",
        "performance_comparisons", "feedback_questions",
    }
    valid_sentiments = {"positive", "negative", "neutral", "mixed"}
    if not isinstance(response, dict):
        return {}
    results = response.get("classifications")
    if not isinstance(results, list):
        return {}
    out: dict[str, tuple[str, str]] = {}
    asked_set = set(brand_ids)
    for item in results:
        if not isinstance(item, dict):
            continue
        b = item.get("brand_id")
        pt = item.get("post_type")
        sent = item.get("sentiment")
        if not isinstance(b, str) or not isinstance(pt, str) or not isinstance(sent, str):
            continue
        # Drop hallucinations (R8).
        if b not in brand_registry_ids:
            continue
        if b not in asked_set:
            logger.debug(
                "classify_post: LLM added brand %r not in asked set",
                b,
            )
        post_type = pt if pt in valid_post_types else "hands_on_usage"
        sentiment = sent if sent in valid_sentiments else "neutral"
        out[b] = (post_type, sentiment)
    return out


def _call_signal_with_retry(
    client: ClaudeClient,
    prompt: str,
    *,
    max_tokens: int = 4096,
    thinking: "dict | None" = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Call the LLM with exponential backoff (mirrors translator).

    `max_tokens` defaults to 4096. This is enough for single-post paths
    (~250-400 output tokens) and for the batched path at batch_size=20
    (~3000 tokens of structured JSON output). Lower values (the old 1024
    default) cause mid-JSON truncation ("Unterminated string" at ~col 32xx)
    exactly as seen in production on 2026-07-15 for N=20 batches.

    `thinking` defaults to None (parameter omitted from the SDK call) for
    backward compatibility with the M3 and direct-Anthropic paths. When
    routing through the DeepSeek V4 Pro endpoint, the caller passes
    `thinking={"type": "disabled"}` (resolved via
    `_resolve_thinking_default()`) to prevent the reasoning model from
    consuming the entire output budget on internal deliberation.
    """
    last_exc: Exception | None = None
    create_kwargs: dict[str, Any] = {
        "model": model or _SIGNAL_MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if thinking is not None:
        create_kwargs["thinking"] = thinking
    for attempt in range(_MAX_RETRIES):
        try:
            return client.messages_create(**create_kwargs)
        except LlmBudgetExhausted:
            raise
        except Exception as e:
            last_exc = e
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_BACKOFF_BASE_SECONDS * (2 ** attempt))
    assert last_exc is not None
    raise last_exc


def classify_post(
    text: str,
    brand_ids: list[str],
    brand_registry: list[BrandRow],
    anthropic_client: ClaudeClient | None = None,
) -> dict[str, tuple[str, str]]:
    """Per-brand (post_type, sentiment) classification via Claude Haiku.

    U9 (replaces the legacy `classify_signal` 6-bucket single-string
    taxonomy with a (post_type, sentiment) decomposition). Builds the
    prompt, calls the LLM, parses the per-brand dict, validates every
    brand_id against `brand_registry`, and drops hallucinations.
    Returns `{}` on LLM failure (logged as WARN).

    Args:
        text:            the post text (the original `posts.text`,
                         not the translation)
        brand_ids:       list of brand_ids to classify against
        brand_registry:  list of BrandRow (the `Store.read_brands()`
                         result); used to validate LLM output
        anthropic_client: a ClaudeClient-protocol object. When None,
                         returns {} immediately (used in tests and
                         for offline operation).

    Returns:
        {brand_id: (post_type, sentiment)} dict. Empty dict on LLM
        failure or when brand_ids is empty.
    """
    if not brand_ids or not text:
        return {}
    if anthropic_client is None:
        return {}
    registry_ids = {b.brand_id for b in brand_registry}
    prompt = build_signal_prompt(text, brand_ids)
    try:
        response = _call_signal_with_retry(anthropic_client, prompt)
    except LlmBudgetExhausted:
        raise
    except Exception as e:
        logger.warning(
            "classify_post: LLM call failed after %d retries: %s",
            _MAX_RETRIES,
            e,
        )
        return {}
    parsed = _parse_signal_response(response, brand_ids, registry_ids)
    if not parsed:
        logger.warning(
            "classify_post returned no classifications for text=%r brand_ids=%r",
            text[:80],
            brand_ids,
        )
    return parsed


# --- U4: classify_pragmatics_full (merged per-post classifier) ----------
#
# KTD1: a SINGLE batched LLM call per 20-post batch returns ALL FIVE
# prongs (post_type, sentiment, discourse_role, china_nationalism,
# us_nationalism) per attributed brand.

# Plan 2026-07-13-001 (timeout investigation): the system prompt body
# (rules + worked examples + taxonomy lists) is byte-identical between
# the per-post and batch paths. Factor it into a module-level constant
# so Anthropic's prompt-cache stays warm across calls — the cache key
# is a function of the prefix bytes, so reusing the same prefix lets
# both the single-post `classify_pragmatics_full` and the batch
# `classify_batch_pragmatics_full` ride the same cache entry.
_CLASSIFY_BATCH_SIZE: int = 20


_VALID_DISCOURSE: frozenset[str] = frozenset({
    "genuine_hype", "sarcasm", "dunk_yingyang", "self_deprecation",
    "cope", "fud", "distillation_accusation", "ai_slop_critique",
    "absurdist_meme",
    # U2a: extended by migration 027 + plan 2026-07-03-003.
    # NOTE: hyphenated, not underscored — see plan KTD7.
    "advertising-marketing",
})
_VALID_NATIONALISM: frozenset[str] = frozenset({
    "none", "mild_pro", "pro", "constructive_critical", "anti", "mixed",
})
_VALID_POST_TYPES = {
    "buzz_releases", "hands_on_usage",
    "performance_comparisons", "feedback_questions",
    # U2a: extended by migration 027 + plan 2026-07-03-003.
    "advertising_marketing", "event_announcement",
}
_VALID_SENTIMENTS = {"positive", "negative", "neutral", "mixed"}

# U2a: top-level unsanctioned flag allow-list. Values outside this set
# are filtered out at the parser (KTD2 / R14).
_VALID_UNSANCTIONED_FLAGS: frozenset[str] = frozenset({
    "marketing_spam", "scam", "crypto", "unauthorized",
})

# U2b: hard cap on LLM-emitted array lengths. The prompt instructs
# max 3 of each per brand; the parser enforces 6 as a defensive ceiling
# against LLM-emitted 100-element arrays (security F2).
_ARRAY_HARD_CAP = 6


def build_pragmatics_full_prompt(text: str, brand_ids: list[str]) -> str:
    """Build the §5.1 + U9 + U3a merged per-post classifier prompt.

    U3a extends this prompt with:
      - 2 new post_type values (advertising_marketing, event_announcement)
      - 1 new discourse_role value (advertising-marketing, hyphenated)
      - The per-brand row now emits `post_types: [str]` and
        `discourse_roles: [str]` arrays (max 3 each) instead of
        scalar `post_type` / `discourse_role`.
      - A top-level `unsanctioned_flags: [str]` field for
        marketing_spam / scam / crypto / unauthorized.

    For multi-post classification, prefer `classify_batch_pragmatics_full`
    (~20× LLM cost reduction at 20 posts/cycle). The single-post
    variant delegates to the same `_PRAGMATICS_FULL_SYSTEM_PROMPT`
    prefix the batch path uses, so Anthropic's prompt-cache stays
    warm across call kinds.
    """
    brand_list = ", ".join(brand_ids) if brand_ids else "(none)"
    return (
        _PRAGMATICS_FULL_SYSTEM_PROMPT
        + f"\n\nTweet text:\n{text}\n\n"
        f"Brands (in order): {brand_list}\n\n"
        f"(Apply the rules and worked examples to this single tweet. "
        f"Return ONE entry in `results` whose `tweet_id` is "
        f"`_single_`.)"
    )


# Plan 2026-07-13-001 (timeout investigation): the system prompt body
# (rules + worked examples + taxonomy lists) is byte-identical between
# the per-post and batch paths. Factor it into a module-level constant
# so Anthropic's prompt-cache stays warm across calls — the cache key
# is a function of the prefix bytes, so reusing the same prefix lets
# both the single-post `classify_pragmatics_full` and the batch
# `classify_batch_pragmatics_full` ride the same cache entry.
_CLASSIFY_BATCH_SIZE: int = 20


def _max_tokens_for_batch(batch_size: int) -> int:
    """Compute the LLM `max_tokens` budget for a batched classifier call.

    The DeepSeek V4 Pro endpoint returns valid JSON for batch_size=20 in
    ~1975 output tokens (probe at data/runs/dsv4-probe-20260715T071331Z.json)
    and for batch_size=40 with max_tokens=8192 in ~4310 output tokens.
    The 200-tokens-per-tweet linear coefficient is conservative: the
    empirical usage at batch_size=20 was 99 tokens/tweet; at batch_size=40
    with max_tokens=8192 it was 108 tokens/tweet. The 200 coefficient
    gives 100% headroom for any 2x growth from multi-brand or
    unsanctioned-flags-heavy tweets.

    The min(8192, ...) cap prevents unbounded budgets on misconfigured
    large batches (KTD7 confirmed 8192 is empirically reachable on DS V4).
    The max(4096, ...) floor ensures even single-post calls get the
    headroom the M3 path needed (per
    docs/debug/2026-07-15-max-tokens-not-threaded-into-classify-batch.md).
    """
    return min(8192, max(4096, 200 * batch_size))


_PRAGMATICS_FULL_SYSTEM_PROMPT: str = (
    "You classify one or more tweets about their relationship to a "
    "list of brands, across FIVE dimensions per brand: post_types "
    "(array), sentiment (scalar), discourse_roles (array), "
    "china_nationalism (scalar), us_nationalism (scalar). You also "
    "emit a top-level `unsanctioned_flags: [str]` per tweet for "
    "marketing_spam / scam / crypto / unauthorized signals.\n\n"
    "For each brand in each tweet, return FIVE fields from these "
    "exact sets:\n\n"
    "post_types (6 buckets — what KIND of post; ARRAY, max 3):\n"
    "  - buzz_releases            (brand announced something new)\n"
    "  - hands_on_usage           (user is using / showing the brand)\n"
    "  - performance_comparisons  (benchmark / eval / head-to-head)\n"
    "  - feedback_questions       (user asking how-to / help / complaint)\n"
    "  - advertising_marketing    (CTA, promo, wrapper, free-credit pitch)\n"
    "  - event_announcement       (official event / community meetup)\n\n"
    "sentiment (4 values — the VALENCE; scalar):\n"
    "  - positive                 (praise, enthusiasm)\n"
    "  - negative                 (criticism, disappointment)\n"
    "  - neutral                  (informational / question; also when "
    "the brand is mentioned only as a COMPARISON POINT and not directly "
    "evaluated — 'X is better than Y' is positive for X, neutral for Y)\n"
    "  - mixed                    (multiple valences in one post)\n\n"
    "discourse_roles (10 keys — pragmatic register, §2; ARRAY, max 3):\n"
    "  - genuine_hype             (straight praise)\n"
    "  - sarcasm                  (English verbal irony)\n"
    "  - dunk_yingyang            (阴阳怪气 / passive-aggressive dunk)\n"
    "  - self_deprecation         (自嘲 / self-mockery)\n"
    "  - cope                     (嘴硬 / stubborn denial)\n"
    "  - fud                      (唱衰 / spreading doom)\n"
    "  - distillation_accusation  (套壳 / 蒸馏指控)\n"
    "  - ai_slop_critique         (AI content-garbage accusation)\n"
    "  - absurdist_meme           (抽象整活 / absurdist antics)\n"
    "  - advertising-marketing    (salesy, CTA-heavy marketing speak — "
    "NOTE: hyphenated, not underscored)\n"
    "  - uncategorized            (catch-all when none of the above fit)\n\n"
    "unsanctioned_flags (per tweet; ARRAY, top-level — omit when no "
    "signal applies):\n"
    "  - marketing_spam           (promotional CTA on a brand — usually "
    "paired with post_type=advertising_marketing AND "
    "discourse_role=advertising-marketing; includes referral-link "
    "pitches, 'try it now', 'FREE access' wrappers, third-party "
    "aggregator lists with explicit CTAs)\n"
    "  - scam                     (impersonation of an official brand "
    "account + asks for payment, credentials, or wallet seed)\n"
    "  - crypto                   (token ticker / airdrop / wallet claim "
    "tied to a brand — 'claim your $X airdrop', 'swap Y for brand "
    "token', 'join the liquidity pool')\n"
    "  - unauthorized             (brand appears in a third-party post "
    "without authorization — giveaway, 'official AI' impersonation, "
    "fake partner announcement)\n\n"
    "Cross-reference rules (these are HARD — emit consistently):\n"
    "  - If post_type=advertising_marketing OR "
    "discourse_role=advertising-marketing, the post MUST also carry "
    "unsanctioned_flags: [\"marketing_spam\"]. The marketing signal is "
    "one signal; it shows up in three places.\n"
    "  - Comparative mention is NOT negative sentiment. When a post "
    "ranks models ('X is better than Y') and does NOT explicitly call "
    "Y bad, emit sentiment=neutral for Y. Only emit "
    "sentiment=negative when the post contains direct evaluative "
    "criticism of the brand (not when it merely ranks another brand "
    "above it).\n"
    "  - lang_detected is REQUIRED on every tweet. Source-language "
    "English posts emit lang_detected='en' with text_en=source text "
    "and text_zh_cn=Chinese translation. Source-language Chinese "
    "posts emit lang_detected='zh' with text_zh_cn=source text and "
    "text_en=English translation. Other languages: emit lang_detected "
    "with the source language and populate both translation fields.\n\n"
    "china_nationalism (6-step scale, §4.4; scalar):\n"
    "  - none                     (no China-nationalism layer)\n"
    "  - mild_pro                 (温和亲华 — subtle positive)\n"
    "  - pro                      (亲华 — open positive)\n"
    "  - constructive_critical   (建设性批评 — pro-CN criticism)\n"
    "  - anti                     (反华 — hostile)\n"
    "  - mixed                    (mixed modes in one post)\n\n"
    "us_nationalism (6-step scale, same as china_nationalism but\n"
    "applied to the US axis — anti = 反美, etc.; scalar):\n"
    "  - none / mild_pro / pro / constructive_critical / anti / mixed\n\n"
    "Rules:\n"
    "1. Return ONLY a JSON object matching this shape:\n"
    "   {\n"
    "     \"results\": [\n"
    "       {\n"
    "         \"tweet_id\": str,\n"
    "         \"classifications\": [\n"
    "           {\n"
    "             \"brand_id\": str,\n"
    "             \"post_types\": [str],         // ARRAY, max 3\n"
    "             \"sentiment\": str,             // scalar\n"
    "             \"discourse_roles\": [str],     // ARRAY, max 3\n"
    "             \"china_nationalism\": str,     // scalar\n"
    "             \"us_nationalism\": str         // scalar\n"
    "           }, ...\n"
    "         ],\n"
    "         \"unsanctioned_flags\": [str]      // ARRAY, top-level\n"
    "       }, ...\n"
    "     ]\n"
    "   }\n"
    "2. ONE result per input tweet, IN THE SAME ORDER as the input.\n"
    "3. Per tweet, RETURN ONE OBJECT PER BRAND LISTED. The brand list "
    "is what the keyword detector found in the text — if a "
    "brand name appears, you MUST produce an object. Cross-brand "
    "comparison posts (\"GLM 5.2 vs Kimi K2.7\"), reply chains "
    "where the brand is mentioned, posts sharing screenshots "
    "with the brand name — ALL count. Only skip a brand if "
    "the post text contains ZERO mention of it (this should be "
    "impossible given how the brand list was derived).\n"
    "4. Use the EXACT brand_id strings from each tweet's brand list.\n"
    "5. Most posts have exactly 1 post_type and 1 discourse_role. "
    "Multi-value is allowed when a post legitimately has more than "
    "one (e.g., a benchmark write-up that is also a "
    "`performance_comparisons` AND `feedback_questions` because it "
    "asks 'am I running behind?'). MAXIMUM 3 of each per brand.\n"
    "6. nationalism is ORTHOGONAL to post_types × sentiment × "
    "discourse_roles — a single post can be e.g. "
    "([perf_compare, feedback], positive, [genuine_hype], none, "
    "constructive_critical).\n"
    "7. If a tweet is off-topic for all brands (shouldn't "
    "happen if the brand list is non-empty), return "
    "{\"tweet_id\": \"<id>\", \"classifications\": [], "
    "\"unsanctioned_flags\": []}.\n"
    "8. genuine_hype is incompatible with explicit call-to-action. "
    "If the post contains a CTA (URL + verb like 'try', 'sign up', "
    "'join', 'get', 'limited-time', 'free access', 限时免费, 立即体验, "
    "注册, 点击), discount offer, or wrapper/promo language "
    "('one API key', 'OpenAI-compatible gateway', 'free credit no card'), "
    "prefer discourse_role `advertising-marketing` over `genuine_hype`. "
    "If both genuine praise AND a CTA coexist, emit BOTH "
    "discourse_roles values — let downstream consumers decide.\n"
    "9. No prose, no explanation, no code fences.\n"
    "\n"
    "10. sent=neutral for launch announcements with no evaluative "
    "language. A post that says only 'X is generally available', "
    "'Y launched today', 'Z shipped v3.2', or 'W is now in beta' "
    "(without praise/criticism) is INFORMATIONAL. emit sent=neutral "
    "regardless of whether the brand would benefit from the "
    "announcement. Optimistic framing like 'now available for "
    "everyone' is still neutral (vendor announcement voice, not "
    "user praise).\n"
    "11. sent=positive for long analytical / investment posts "
    "with explicit positive framing. If the post says 'the model "
    "is strategically positive for X's cloud multiple', "
    "'increasingly important as a strategic asset', 'supports the "
    "valuation narrative', or similar investment-grade positive "
    "language, that IS positive sentiment — do not water it down "
    "to sent=mixed because there are also caveats in the post. "
    "Caveats and positive framing coexist; positive framing wins.\n"
    "12. sent=neutral for multi-brand state-of-market posts that "
    "are factual updates per brand ('X climbed 20 spots to #138, "
    "'Y price dropped 8.2%', 'Z was degraded for 45 min'). emit "
    "sent=neutral for each brand UNLESS a specific positive/"
    "negative evaluative claim is made about that brand in the "
    "same post.\n"
    "13. pt=event_announcement for one-line 'X is generally "
    "available / Y launched / Z shipped' posts. NOT hands_on_usage "
    "(the user isn't using the brand — the brand is announcing). "
    "NOT buzz_releases (that's a brand-side press release; this "
    "rule covers third-party reshares of an announcement too).\n"
    "14. pt=performance_comparisons for any post mentioning TTFT "
    "(time-to-first-token), latency, benchmark, ranking, '#N "
    "ranking', 'N spots climbed/dropped', 'side-by-side race', "
    "'vs <other model>'. The LLM Drag Race write-up ('races GPT-"
    "4o-mini vs Llama 3.3 70B side-by-side, measure TTFT') is the "
    "canonical example.\n"
    "15. pt=performance_comparisons OR pt=feedback_questions for "
    "pure analytical commentary (price/perf framing, model "
    "governance framing, 'should I switch?' framing). NOT "
    "hands_on_usage — the author is analyzing, not using.\n"
    "16. Nationalism requires explicit US-China relational framing. "
    "Do not infer `china_nationalism` or `us_nationalism` from "
    "generic anti-vendor dunk on a Chinese (or US) brand's product "
    "failure, benchmark miss, or release reception. A post dunking "
    "on Qwen for a benchmark miss is `sentiment=anti-Qwen` and "
    "`nationalism=neutral`, NOT `us_nationalism=anti`. The "
    "nationalism axes measure US-China framing, not anti-vendor "
    "hostility.\n"
    "17. Trap-language handling. When the post text contains "
    "\"trap\", \"gotcha\", \"embarrassing\", \"fumbled\", or "
    "\"翻车\" AND the subject is a Chinese-vendor product failure, "
    "the post's `discourse_roles` should include `dunk_yingyang` "
    "if the tone is passive-aggressive, or `fud` if the tone is "
    "doom-spreading. The post's `us_nationalism` should remain "
    "`none` per rule 16 — trap-language is surface vocabulary, "
    "not a US-China framing signal.\n"
    "18. Superlative praise (`fastest`, `best`, `strongest`, "
    "`first to ship`, `most powerful`) describes the brand being "
    "praised, NOT a US-China framing. The post is "
    "`discourse_roles=[genuine_hype]` for the brand being praised "
    "— NOT `us_nationalism=pro/anti` based on which country the "
    "praised brand is from. 'Qwen is the fastest model' is hype, "
    "not a nationalism statement about China.\n"
    "19. Qwen-vendor-not-US distinction. Posts critiquing a "
    "Chinese-vendor's product behavior (Qwen, GLM, DeepSeek, Kimi) "
    "do not carry `us_nationalism` valence by default. Even when "
    "the critique is harsh (\"Qwen faded\", \"DeepSeek shipped a "
    "broken model\"), the axis measures US-China framing, not "
    "anti-Chinese-vendor sentiment. emit `us_nationalism=none` "
    "unless the post explicitly invokes US-China framing.\n"
    "\n"
    "Worked examples (reference cases; match these patterns):\n"
    "  A. 'Kimi K2.7 Code is generally available in GitHub Copilot'\n"
    "     → per brand: pt=[event_announcement], sent=neutral,\n"
    "       discourse_roles=[uncategorized].\n"
    "  B. 'K2.7 Code climbed 20 spots to #138; Deepseek V4 price "
    "dropped 8.2%'\n"
    "     → per brand: pt=[hands_on_usage], sent=neutral for both,\n"
    "       discourse_roles=[uncategorized]. (factual updates, no\n"
    "       aggregate judgment.)\n"
    "  C. 'Alibaba's Qwen franchise is increasingly important as a\n"
    "strategic cloud and platform asset... strategically positive "
    "for BABA's cloud multiple'\n"
    "     → qwen: pt=[performance_comparisons],\n"
    "       sent=positive, discourse_roles=[genuine_hype].\n"
    "       other brands mentioned in same post without explicit\n"
    "       positive framing: sent=neutral.\n"
    "  D. 'I built LLM Drag Race: races GPT-4o-mini vs Llama 3.3 "
    "70B, measure TTFT'\n"
    "     → brands present: pt=[performance_comparisons],\n"
    "       sent=neutral (showcase, no evaluative claim).\n"
    "  E. 'This changes how GitHub routes coding tasks — model "
    "picker vs single assistant' (price/perf analytical piece)\n"
    "     → pt=[performance_comparisons] OR\n"
    "       [feedback_questions] (user implicitly asking 'where "
    "does this leave me?'), NOT hands_on_usage.\n"
    "  F. 'Kimi K2.7 Code makes Copilot a model marketplace' "
    "(rhetorical questions + analytical commentary)\n"
    "     → pt=[feedback_questions] (asks 4 rhetorical "
    "performance/pricing questions), NOT hands_on_usage.\n"
    "  G. 'DeepSeek shipping a benchmark trap — gotcha benchmarks "
    "that nobody can reproduce' (anti-vendor dunk on Chinese-vendor "
    "product failure)\n"
    "     → deepseek: pt=[performance_comparisons], sent=negative,\n"
    "       discourse_roles=[dunk_yingyang], cn_nationalism=none,\n"
    "       us_nationalism=none. (per rules 16, 17: dunk tone is\n"
    "       surface vocabulary, NOT US-China framing.)\n"
    "  H. 'Qwen is the fastest model I've benchmarked this month, "
    "scored 89% on MMLU'\n"
    "     → qwen: pt=[performance_comparisons], sent=positive,\n"
    "       discourse_roles=[genuine_hype], cn_nationalism=none,\n"
    "       us_nationalism=none. (per rule 18: superlative praise\n"
    "       is hype, not a US-China statement.)\n"
    "  I. 'GLM 5.2 fumbled the launch — benchmarks collapsed, "
    "everyone noticed' (anti-vendor dunk on Chinese-vendor release)\n"
    "     → glm: pt=[buzz_releases], sent=negative,\n"
    "       discourse_roles=[fud], cn_nationalism=none,\n"
    "       us_nationalism=none. (per rules 16, 19: harsh critique\n"
    "       of Chinese-vendor product is anti-vendor sentiment,\n"
    "       not US-China framing.)\n"
    "  J. 'Kimi K2.7 is fast but DeepSeek V4 is faster on coding "
    "tasks; the AI race is heating up between US and Chinese "
    "vendors'\n"
    "     → kimi + deepseek: pt=[performance_comparisons],\n"
    "       sent=neutral, discourse_roles=[uncategorized],\n"
    "       cn_nationalism=mild_pro, us_nationalism=anti. (this\n"
    "       post DOES invoke US-China framing explicitly — rule 16\n"
    "       applies the other way: nationalism fires when the post\n"
    "       actually names the AI race.)\n"
)


def build_batch_pragmatics_full_prompt(
    tweets: list[dict[str, Any]],
) -> str:
    """Build the batch (N tweets) variant of the per-post prompt.

    Each tweet dict has keys: `tweet_id` (str), `text` (str), and
    `brand_ids` (list[str]). The system rules + worked examples are
    shared across all tweets via the `_PRAGMATICS_FULL_SYSTEM_PROMPT`
    constant — meaning a single API call can amortize ~3.5 KB of
    prefix tokens across up to 20 posts before the per-tweet payload
    even starts. Prompt-cache hits stay warm cycle-to-cycle.
    """
    import json as _json

    payload = _json.dumps(
        [
            {
                "tweet_id": str(t.get("tweet_id") or t.get("id") or ""),
                "text": t.get("text") or "",
                "brand_ids": list(t.get("brand_ids") or []),
            }
            for t in tweets
        ],
        ensure_ascii=False,
    )
    return (
        _PRAGMATICS_FULL_SYSTEM_PROMPT
        + f"\n\nTweets (JSON array of {len(tweets)}):\n{payload}"
    )


def _parse_pragmatics_full_response(
    response: dict[str, Any],
    brand_registry_ids: set[str],
) -> dict[str, Any]:
    """Parse the merged LLM response into the new U2a shape.

    Returns:
        {
            "by_brand": {brand_id: {post_type, sentiment, discourse_role,
                                    china_nationalism, us_nationalism}},
            "unsanctioned_flags": [str, ...],
        }

    Each per-brand entry's discourse_role is a SINGLE string (scalar),
    not an array. U2b's array reshape is applied at a higher layer
    (Store API / U4's bulk_insert path) — the parser deliberately keeps
    the scalar shape to preserve backwards-compat with callers that
    iterate `result[brand_id]["discourse_role"]`.

    The U2b multi-value path lives in `_parse_pragmatics_full_response_arrays`
    (added below) — callers that need arrays call that variant directly.
    """
    if not isinstance(response, dict):
        return {"by_brand": {}, "unsanctioned_flags": []}
    results = response.get("classifications")
    if not isinstance(results, list):
        return {"by_brand": {}, "unsanctioned_flags": []}
    out: dict[str, dict[str, str]] = {}
    for item in results:
        if not isinstance(item, dict):
            continue
        b = item.get("brand_id")
        if not isinstance(b, str) or b not in brand_registry_ids:
            continue
        # Plan 2026-07-13-001 compat: the new batch wire format emits
        # `post_types: [str]` and `discourse_roles: [str]` (arrays).
        # The legacy scalar format emits `post_type` / `discourse_role`
        # as single strings. Accept either — take the first allowed
        # array element when an array is present.
        raw_pt = item.get("post_types")
        if isinstance(raw_pt, list) and raw_pt:
            pt = next(
                (p for p in raw_pt
                 if isinstance(p, str) and p in _VALID_POST_TYPES),
                None,
            )
        else:
            pt = item.get("post_type")
        raw_dr = item.get("discourse_roles")
        if isinstance(raw_dr, list) and raw_dr:
            dr = next(
                (d for d in raw_dr
                 if isinstance(d, str) and d in _VALID_DISCOURSE),
                None,
            )
        else:
            dr = item.get("discourse_role")
        sent = item.get("sentiment")
        cn = item.get("china_nationalism")
        un = item.get("us_nationalism")
        post_type = pt if pt in _VALID_POST_TYPES else "hands_on_usage"
        sentiment = sent if sent in _VALID_SENTIMENTS else "neutral"
        discourse_role = (
            dr if isinstance(dr, str) and dr in _VALID_DISCOURSE
            else "uncategorized"
        )
        # `post_type` and `discourse_role` are only assigned when the
        # raw value passed the enum check; otherwise the above
        # `hands_on_usage` / `uncategorized` defaults apply. No
        # additional normalization needed below.
        china = (
            cn if isinstance(cn, str) and cn in _VALID_NATIONALISM
            else "none"
        )
        us = (
            un if isinstance(un, str) and un in _VALID_NATIONALISM
            else "none"
        )
        out[b] = {
            "post_type": post_type,
            "sentiment": sentiment,
            "discourse_role": discourse_role,
            "china_nationalism": china,
            "us_nationalism": us,
        }
    flags = _parse_unsanctioned_flags(response.get("unsanctioned_flags"))
    return {"by_brand": out, "unsanctioned_flags": flags}


def _parse_unsanctioned_flags(raw: Any) -> list[str]:
    """Filter the top-level unsanctioned_flags array against the allow-list."""
    if not isinstance(raw, list):
        return []
    return [f for f in raw if isinstance(f, str) and f in _VALID_UNSANCTIONED_FLAGS]


def _parse_pragmatics_full_response_arrays(
    response: dict[str, Any],
    brand_registry_ids: set[str],
) -> dict[str, Any]:
    """U2b: parse the LLM response into multi-value arrays.

    Each per-brand entry emits `post_types: [str]` and
    `discourse_roles: [str]` arrays. Sentiment / nationalism stay
    scalar (one valence per post × brand is the natural semantic).
    N rows are produced per brand — one per (post_type, discourse_role)
    combination — by `_expand_per_brand_to_rows` below.

    Returns:
        {
            "rows": [
                {"brand_id", "post_type", "sentiment",
                 "discourse_role", "china_nationalism", "us_nationalism"},
                ...
            ],
            "unsanctioned_flags": [str, ...],
        }

    The caller (Store.bulk_insert_post_brand_signals +
    bulk_insert_post_brand_discourse) iterates `rows` and inserts each
    into the appropriate junction table.
    """
    if not isinstance(response, dict):
        return {"rows": [], "unsanctioned_flags": []}
    results = response.get("classifications")
    if not isinstance(results, list):
        return {"rows": [], "unsanctioned_flags": []}
    rows: list[dict[str, str]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        b = item.get("brand_id")
        if not isinstance(b, str) or b not in brand_registry_ids:
            continue
        # post_types array — default to ["hands_on_usage"] if missing/invalid.
        raw_pts = item.get("post_types")
        if not isinstance(raw_pts, list) or not raw_pts:
            post_types = ["hands_on_usage"]
        else:
            post_types = [
                p for p in raw_pts
                if isinstance(p, str) and p in _VALID_POST_TYPES
            ]
            # Security: hard cap at _ARRAY_HARD_CAP entries.
            if len(post_types) > _ARRAY_HARD_CAP:
                logger.warning(
                    "classify_pragmatics_full: post_types=%d > hard cap %d; "
                    "truncating (brand_id=%r)",
                    len(post_types), _ARRAY_HARD_CAP, b,
                )
                post_types = post_types[:_ARRAY_HARD_CAP]
            if not post_types:
                post_types = ["hands_on_usage"]
        # discourse_roles array — default to ["uncategorized"] if missing/invalid.
        raw_drs = item.get("discourse_roles")
        if not isinstance(raw_drs, list) or not raw_drs:
            discourse_roles = ["uncategorized"]
        else:
            discourse_roles = [
                d for d in raw_drs
                if isinstance(d, str) and d in _VALID_DISCOURSE
            ]
            if len(discourse_roles) > _ARRAY_HARD_CAP:
                logger.warning(
                    "classify_pragmatics_full: discourse_roles=%d > hard cap %d; "
                    "truncating (brand_id=%r)",
                    len(discourse_roles), _ARRAY_HARD_CAP, b,
                )
                discourse_roles = discourse_roles[:_ARRAY_HARD_CAP]
            if not discourse_roles:
                discourse_roles = ["uncategorized"]
        # Scalar fields with the same coercion rules.
        sent = item.get("sentiment")
        cn = item.get("china_nationalism")
        un = item.get("us_nationalism")
        sentiment = sent if sent in _VALID_SENTIMENTS else "neutral"
        china = cn if isinstance(cn, str) and cn in _VALID_NATIONALISM else "none"
        us = un if isinstance(un, str) and un in _VALID_NATIONALISM else "none"
        # Expand: one row per (post_type × discourse_role) pair.
        # Each row gets the same sentiment + nationalism values
        # (per the plan: sentiment is per-(post, brand, post_type) — so
        # all rows for the same brand share sentiment; discourse roles
        # get their own row but inherit the post's sentiment).
        for pt in post_types:
            for dr in discourse_roles:
                rows.append({
                    "brand_id": b,
                    "post_type": pt,
                    "sentiment": sentiment,
                    "discourse_role": dr,
                    "china_nationalism": china,
                    "us_nationalism": us,
                })
    flags = _parse_unsanctioned_flags(response.get("unsanctioned_flags"))
    return {"rows": rows, "unsanctioned_flags": flags}


def classify_pragmatics_full(
    text: str,
    brand_ids: list[str],
    brand_registry: list,
    anthropic_client: "ClaudeClient | None" = None,
    *,
    model: str | None = None,
    thinking: "dict | None" = None,
) -> dict[str, Any]:
    """U4 (U2a): per-brand classification + top-level unsanctioned_flags.

    Returns `{"by_brand": {...}, "unsanctioned_flags": [...]}` (U2a shape).
    Callers that only want the by_brand dict should index result["by_brand"].
    """
    empty = {"by_brand": {}, "unsanctioned_flags": []}
    if not brand_ids or not text:
        return empty
    if anthropic_client is None:
        return empty
    # If the caller didn't supply a brand_registry, trust the
    # brand_ids argument (the fixture path doesn't read the live
    # `brands` table). The parser then validates the LLM's
    # response against the same set.
    if brand_registry:
        registry_ids = {b.brand_id for b in brand_registry}
    else:
        registry_ids = set(brand_ids)
    prompt = build_pragmatics_full_prompt(text, brand_ids)
    try:
        response = _call_signal_with_retry(
            anthropic_client,
            prompt,
            model=model,
            thinking=thinking,
        )
    except LlmBudgetExhausted:
        raise
    except Exception as e:
        logger.warning(
            "classify_pragmatics_full: LLM call failed after %d retries: %s",
            _MAX_RETRIES, e,
        )
        return empty
    # U2b-fix: route through the array-aware parser. The prompt at
    # build_pragmatics_full_prompt explicitly requests `post_types: [str]`
    # and `discourse_roles: [str]` arrays (lines 1048, 1060, 1088, 1090),
    # but the previous scalar parser at line 1263 read `post_type` /
    # `discourse_role` (singular) — which never matched the LLM's
    # array output, so every post_type fell through to "hands_on_usage"
    # and every discourse_role to "uncategorized". Smoketest data on
    # 2026-07-06 confirmed 20/20 degenerate on those two prongs.
    #
    # We reshape the array parser's `rows` back into the legacy
    # U2a `by_brand` shape by collapsing post_types[] / discourse_roles[]
    # into their first element. Callers that need the multi-value
    # structure (Store.bulk_insert_post_brand_signals) call the
    # array parser directly via `_parse_pragmatics_full_response_arrays`.
    raw = _parse_pragmatics_full_response_arrays(response, registry_ids)
    by_brand: dict[str, dict[str, str]] = {}
    for row in raw["rows"]:
        bid = row["brand_id"]
        if bid in by_brand:
            # Duplicate brand_id in the LLM response — keep the
            # first row's classification; later rows are ignored.
            logger.warning(
                "classify_pragmatics_full: duplicate brand_id=%r in "
                "response rows; keeping first", bid,
            )
            continue
        by_brand[bid] = {
            "post_type": row["post_type"],
            "sentiment": row["sentiment"],
            "discourse_role": row["discourse_role"],
            "china_nationalism": row["china_nationalism"],
            "us_nationalism": row["us_nationalism"],
        }
    parsed = {"by_brand": by_brand, "unsanctioned_flags": raw["unsanctioned_flags"]}
    if not parsed["by_brand"]:
        # Compat shim: the new batch wire format wraps each per-tweet
        # entry in a `results: [{tweet_id, classifications, ...}]` array.
        # The per-post caller (and the legacy / non-batch response path)
        # may receive either shape from a client adapter; if the
        # `classifications` top-level key is missing, descend into the
        # first `results` entry.
        if isinstance(response, dict):
            results_arr = response.get("results")
            if isinstance(results_arr, list) and results_arr:
                first = results_arr[0]
                if isinstance(first, dict):
                    parsed = _parse_pragmatics_full_response(
                        first, registry_ids,
                    )
    if not parsed["by_brand"]:
        logger.warning(
            "classify_pragmatics_full returned no classifications for "
            "text=%r brand_ids=%r",
            text[:80], brand_ids,
        )
    return parsed


def _classify_one_batch_to_by_brand(
    per_tweet: dict[str, Any],
    registry_ids: set[str],
    tweet_id: str,
) -> dict[str, Any]:
    """Reduce one `results[i]` entry to the legacy U2a by_brand shape.

    Mirrors the array-reshape loop at the bottom of `classify_pragmatics_full`
    (first-row-wins per brand_id, dedup warning logged). Posts with
    no `classifications` key return the empty shape.

    Returns:
        {"by_brand": {brand_id: {...scalar prongs...}},
         "unsanctioned_flags": [str, ...]}
    """
    if not isinstance(per_tweet, dict):
        return {"by_brand": {}, "unsanctioned_flags": []}
    rows = per_tweet.get("classifications")
    if not isinstance(rows, list):
        return {"by_brand": {}, "unsanctioned_flags": []}
    by_brand: dict[str, dict[str, str]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        b = row.get("brand_id")
        if not isinstance(b, str) or b not in registry_ids:
            continue
        if b in by_brand:
            logger.warning(
                "classify_batch_pragmatics_full: duplicate brand_id=%r "
                "in tweet_id=%r; keeping first", b, tweet_id,
            )
            continue
        # Per-brand array fields — collapse to the first allowed value
        # (the legacy `by_brand` shape is scalar; the multi-value path
        # is the array parser in `_parse_pragmatics_full_response_arrays`).
        raw_pts = row.get("post_types") or []
        raw_drs = row.get("discourse_roles") or []
        pt = next(
            (p for p in raw_pts
             if isinstance(p, str) and p in _VALID_POST_TYPES),
            "hands_on_usage",
        )
        dr = next(
            (d for d in raw_drs
             if isinstance(d, str) and d in _VALID_DISCOURSE),
            "uncategorized",
        )
        sent = row.get("sentiment")
        cn = row.get("china_nationalism")
        un = row.get("us_nationalism")
        by_brand[b] = {
            "post_type": pt if pt in _VALID_POST_TYPES else "hands_on_usage",
            "sentiment": sent if sent in _VALID_SENTIMENTS else "neutral",
            "discourse_role": dr,
            "china_nationalism": (
                cn if isinstance(cn, str) and cn in _VALID_NATIONALISM
                else "none"
            ),
            "us_nationalism": (
                un if isinstance(un, str) and un in _VALID_NATIONALISM
                else "none"
            ),
        }
    flags = _parse_unsanctioned_flags(per_tweet.get("unsanctioned_flags"))
    return {"by_brand": by_brand, "unsanctioned_flags": flags}


def _validate_deepseek_response_shape(
    parsed: Any,
    expected_count: int,
) -> None:
    """Assert the wire format of a batched classifier response.

    The DeepSeek V4 Pro endpoint (and the production prompt, per
    `_PRAGMATICS_FULL_SYSTEM_PROMPT`) emits a wire shape of:
        {
          "results": [
            {"tweet_id": str, "classifications": [...], "unsanctioned_flags": [...]},
            ...
          ]
        }
    with one entry per input tweet. The shape is consumed by
    `_classify_one_batch_to_by_brand` above, which already handles a
    missing `unsanctioned_flags` gracefully via `_parse_unsanctioned_flags`.

    This validator is a defense-in-depth check that runs before the
    parser, so a future DS V4 prompt drift (e.g. a model that wraps
    results differently or drops the `tweet_id` field) surfaces as a
    typed `ValueError` with a clear message, rather than a generic
    KeyError deep in the parser. The fail-soft contract at lines
    1815-1849 already catches `Exception` and falls back to per-post
    retries, so a shape-drift exception routes through the same
    recovery path.

    Args:
        parsed: the deserialized JSON response from the LLM.
        expected_count: number of input tweets in the batch (the
            validator asserts `len(results) == expected_count`).

    Raises:
        ValueError: with a descriptive message identifying the missing
            or malformed element. Missing `unsanctioned_flags` is
            logged at WARNING but does not raise (the existing parser
            defaults to `[]`).
    """
    if not isinstance(parsed, dict):
        raise ValueError(
            f"shape drift: response is {type(parsed).__name__}, expected dict"
        )
    if "results" not in parsed:
        raise ValueError("shape drift: response missing 'results' key")
    results = parsed["results"]
    if not isinstance(results, list):
        raise ValueError(
            f"shape drift: 'results' is {type(results).__name__}, expected list"
        )
    if len(results) != expected_count:
        raise ValueError(
            f"shape drift: 'results' has {len(results)} entries, "
            f"expected {expected_count}"
        )
    for i, entry in enumerate(results):
        if not isinstance(entry, dict):
            raise ValueError(
                f"shape drift: results[{i}] is {type(entry).__name__}, "
                f"expected dict"
            )
        if not isinstance(entry.get("tweet_id"), str):
            raise ValueError(
                f"shape drift: results[{i}].tweet_id is "
                f"{type(entry.get('tweet_id')).__name__}, expected str"
            )
        if not isinstance(entry.get("classifications"), list):
            raise ValueError(
                f"shape drift: results[{i}].classifications is "
                f"{type(entry.get('classifications')).__name__}, expected list"
            )
        if "unsanctioned_flags" not in entry:
            # Log at WARNING but do not raise — the existing parser
            # defaults to [] via `_parse_unsanctioned_flags` (which
            # returns [] for non-list input per the helper at line
            # 1467). This is the documented graceful-default path.
            logger.warning(
                "shape drift: results[%d] (tweet_id=%r) missing "
                "'unsanctioned_flags'; parser will default to []",
                i, entry.get("tweet_id"),
            )


def classify_batch_pragmatics_full(
    tweets: list[dict[str, Any]],
    brand_registry: list,
    anthropic_client: "ClaudeClient | None" = None,
    *,
    on_batch_error: "Callable[[list[dict[str, Any]], Exception], None] | None" = None,
    max_tokens: int = 4096,
    thinking: "dict | None" = None,
    model: str | None = None,
) -> list[dict[str, Any]]:
    """U4 (batched): per-post classification across N tweets, one LLM call per batch.

    Each tweet dict MUST have keys: `tweet_id` (or `id`), `text`, and
    `brand_ids` (list[str]). Tweets without brands are skipped — but they
    still occupy a slot in the returned list so the caller can index
    `result[i]` ↔ `tweets[i]`. For tweets with no brands the result is
    `{"by_brand": {}, "unsanctioned_flags": []}` (the same empty shape
    `classify_pragmatics_full` returns in that case).

    Batching mirrors `translate_batch_pragmatics`: outer loop walks
    `range(0, len(tweets), _CLASSIFY_BATCH_SIZE)` (20 posts/batch), the
    `_PRAGMATICS_FULL_SYSTEM_PROMPT` prefix is shared across every batch
    so Anthropic's prompt-cache stays warm. At 200 posts this is
    ~10 LLM calls instead of 200 — a ~20× cost reduction that fits
    Cycle 1's 15-min budget.

    Args:
        tweets: list of `{"tweet_id": str, "text": str, "brand_ids": [str]}`.
        brand_registry: list of `BrandRow`-like (read brand_id). When
            empty, the union of all `brand_ids` arguments is used.
        anthropic_client: a ClaudeClient instance. None → short-circuit
            to per-tweet empty shape (the no-LLM path).
        on_batch_error: optional callback `(batch, exc)` invoked per-batch
            when the LLM call raised (after retries exhausted) OR the
            response failed to parse. Per-tweet failure is isolated — the
            rest of the run continues with empty-shape entries.
        max_tokens: output token budget for the LLM generation. Default
            4096 (covers N=20 structured JSON ~3000 tokens). Must be
            high enough or the response truncates mid-JSON (the
            "Unterminated string" failure mode).

    Returns:
        list of length `len(tweets)`, index-aligned. Each entry is
        `{"by_brand": {brand_id: {"post_type", "sentiment", "discourse_role",
         "china_nationalism", "us_nationalism"}}, "unsanctioned_flags": [str]}` —
        the same shape `classify_pragmatics_full` returns, so the
        `_run_post_fetch` Stage 2 loop body does not need to change.
    """
    empty = {"by_brand": {}, "unsanctioned_flags": []}
    if not tweets:
        return []
    if anthropic_client is None:
        return [dict(empty) for _ in tweets]

    # Resolve `thinking` default from env: when not explicitly passed
    # (None), use the env-driven helper. The M3/direct paths resolve to
    # None so behavior is unchanged. The deepseek path resolves to
    # {"type": "disabled"} so the reasoning model does not consume the
    # entire output budget on internal deliberation.
    if thinking is None:
        import os as _os
        thinking = _resolve_thinking_default(_os.environ.get(
            "X_MONITOR_CLASSIFIER_BASE_URL",
            _os.environ.get("ANTHROPIC_BASE_URL", ""),
        ))

    if brand_registry:
        registry_ids = {b.brand_id for b in brand_registry}
    else:
        registry_ids = set().union(
            *(set(t.get("brand_ids") or []) for t in tweets)
        )

    results: list[dict[str, Any]] = []
    for start in range(0, len(tweets), _CLASSIFY_BATCH_SIZE):
        batch = tweets[start: start + _CLASSIFY_BATCH_SIZE]
        # Skip posts that carry no brand list — emit empty shape in
        # their slot so the result list is index-aligned with the
        # input. The classifier's purpose is per-brand classification;
        # unattributed posts have nothing to classify.
        kept: list[dict[str, Any]] = []
        kept_indexes: list[int] = []
        skipped_count = 0
        for i, t in enumerate(batch):
            if not (t.get("brand_ids") or []):
                skipped_count += 1
                continue
            kept.append(t)
            kept_indexes.append(i)
        if not kept:
            results.extend([dict(empty) for _ in batch])
            continue
        prompt = build_batch_pragmatics_full_prompt(kept)
        try:
            response = _call_signal_with_retry(
                anthropic_client, prompt,
                max_tokens=max_tokens, thinking=thinking,
                model=model,
            )
        except LlmBudgetExhausted:
            raise
        except Exception as exc:
            # Plan 2026-07-13-001 fail-soft contract: when a batch
            # fails to classify, fall back to per-post retries so a
            # single bad post doesn't poison the rest of the batch.
            # This preserves the legacy per-post granularity under the
            # v1.7 batched API. If the per-post fallback also raises
            # for a particular post, that single post gets empty shape
            # and the others still get their per-post classification.
            logger.warning(
                "classify_batch_pragmatics_full: batch LLM call failed "
                "after %d retries for batch of %d posts; falling back "
                "to per-post retries: %s",
                _MAX_RETRIES, len(kept), exc,
            )
            if on_batch_error is not None:
                on_batch_error(batch, exc)
            for t in batch:
                try:
                    single = classify_pragmatics_full(
                        text=t.get("text") or "",
                        brand_ids=list(t.get("brand_ids") or []),
                        brand_registry=list(brand_registry) if brand_registry else [],
                        anthropic_client=anthropic_client,
                        model=model,
                        thinking=thinking,
                    )
                    results.append(
                        single if isinstance(single, dict) else dict(empty),
                    )
                except LlmBudgetExhausted:
                    raise
                except Exception as single_exc:
                    logger.warning(
                        "classify_batch_pragmatics_full: per-post fallback "
                        "also failed for tweet_id=%s: %s",
                        t.get("tweet_id") or t.get("id"), single_exc,
                    )
                    results.append(dict(empty))
            continue
        # Validate the wire shape BEFORE consuming entries. The validator
        # raises ValueError on drift, which is caught below by the
        # fail-soft contract. (The redundant count check that lived here
        # pre-swap is now subsumed by `_validate_deepseek_response_shape`.)
        try:
            _validate_deepseek_response_shape(response, len(kept))
        except ValueError as shape_exc:
            logger.warning(
                "classify_batch_pragmatics_full: %s; emitting empty "
                "for entire batch of %d posts",
                shape_exc, len(kept),
            )
            for _ in batch:
                results.append(dict(empty))
            if on_batch_error is not None:
                on_batch_error(batch, shape_exc)
            continue
        parsed = response.get("results")  # validator already proved this is a list
        # Build a tweet_id → entry map so the result list is robust
        # to the LLM emitting them out of order.
        per_id: dict[str, dict[str, Any]] = {}
        for entry in parsed:
            if isinstance(entry, dict):
                tid = entry.get("tweet_id")
                if isinstance(tid, str):
                    per_id[tid] = entry
        # Walk the input batch (so order matches) and decode each.
        for t in batch:
            tid = str(t.get("tweet_id") or t.get("id") or "")
            entry = per_id.get(tid)
            if entry is None:
                results.append(dict(empty))
                continue
            decoded = _classify_one_batch_to_by_brand(
                entry, registry_ids, tid,
            )
            results.append(decoded)
        # Sanity warning — useful for catching LLM drift on the
        # prompt cache (e.g. a system change that drops tweet_id).
        if skipped_count:
            logger.debug(
                "classify_batch_pragmatics_full: skipped %d tweets with "
                "no brand_ids in batch of %d", skipped_count, len(batch),
            )
    return results


# --- Real Anthropic client (lazy import) --------------------------------


class AnthropicClaudeClient:
    """Production Claude client using `requests` directly.

    Avoids the Anthropic SDK (which uses httpx → httpcore) because
    Python 3.14.5 on macOS 26.3.1 has an intermittent SSL read hang
    with httpx/httpcore's connection pool that `requests` (urllib3)
    does not trigger. The Anthropic Messages API is a simple REST
    endpoint — POST /v1/messages with JSON body and x-api-key header.

    Callers pass standard Anthropic API kwargs (model, max_tokens,
    messages, temperature, thinking, system, etc.) to
    ``messages_create(**kwargs)`` and receive a parsed JSON dict back.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = (base_url or "https://api.anthropic.com").rstrip("/")

    def messages_create(self, **kwargs: Any) -> dict[str, Any]:
        """Send a messages.create request and return the parsed JSON."""
        import json as _json

        # Resolve the thinking default when not explicitly passed by the
        # caller. DeepSeek V4 Pro is a reasoning model that emits
        # ThinkingBlocks (no .text) unless thinking={"type": "disabled"}
        # is set; the blocks are then invisible to the loops below, the
        # response body is empty, and json.loads("") raises. Inject the
        # thinking kwarg from the operator's proxy config so the response
        # always carries at least one TextBlock. MiniMax / direct
        # Anthropic paths return None (no-op).
        if "thinking" not in kwargs:
            import os as _os
            thinking = _resolve_thinking_default(_os.environ.get(
                "X_MONITOR_CLASSIFIER_BASE_URL",
                _os.environ.get("ANTHROPIC_BASE_URL", ""),
            ))
            if thinking is not None:
                kwargs["thinking"] = thinking

        url = f"{self._base_url}/v1/messages"
        headers = {
            "x-api-key": self._api_key or "",
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        # Pull out the body fields that go to the Anthropic API.
        # The kwargs dict is a flat bag of model, max_tokens, messages,
        # temperature, thinking, system, etc. — pass everything through.
        #
        # Use http.client directly instead of requests/urllib3.
        # Python 3.14.5 on macOS 26.3.1 has an intermittent SSL read hang
        # with urllib3's connection pool after the process has made prior
        # HTTPS requests to different hosts (TwitterAPI.io). A fresh
        # http.client connection per call avoids the pooled-connection
        # path entirely.
        import json as _json_module
        import http.client
        import urllib.parse
        from urllib.parse import urlparse
        parsed = urlparse(url)
        body_bytes = _json_module.dumps(kwargs).encode("utf-8")
        timeout = kwargs.pop("timeout", 60)
        conn = http.client.HTTPSConnection(
            parsed.hostname,
            parsed.port or 443,
            timeout=timeout,
        )
        try:
            conn.request("POST", parsed.path, body=body_bytes, headers=headers)
            r = conn.getresponse()
            raw_body = r.read()
        finally:
            conn.close()
        if not (200 <= r.status < 300):
            raise RuntimeError(
                f"LLM API returned {r.status}: {raw_body[:500]!r}"
            )
        body = _json_module.loads(raw_body)
        # Extract text from content blocks (Anthropic response format).
        # Skip ThinkingBlocks (DeepSeek without thinking=disabled).
        text_parts: list[str] = []
        for block in body.get("content") or []:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
        raw = "\n".join(text_parts).strip()
        # Trailing-prose-tolerant parser (plan 2026-08-04-001).
        # Replaces the inline json.loads + except fallback with the shared
        # helper. Same warning shape and same fallback dict as before.
        return parse_llm_response(
            raw,
            logger_name="x_monitor.attribution",
            fallback={"verdict": "uncertain", "reason": "llm_non_json_response"},
        )


# --- Public re-exports for compat shim (Unit 6) -------------------------

__all__ = [
    # Constants
    "UNATTRIBUTED_BRAND_ID",
    "BRAND_SOURCE_PRIORITY",
    "Source",
    "SourceType",
    # Dataclasses
    "MentionRow",
    "BrandRow",
    # Validation + keyword index
    "validate_raw_token",
    "compile_keyword_index",
    # Extractors (Decision 6)
    "extract_user_mentions",
    "extract_hashtag_mentions",
    "extract_body_keywords",
    "extract_search_term_match",
    # Consolidator + classifier
    "compute_post_brands",
    "attribute_to_brands",
    "classify_post",
    "classify_pragmatics_full",
    "classify_batch_pragmatics_full",
    "build_signal_prompt",
    "build_pragmatics_full_prompt",
    "build_batch_pragmatics_full_prompt",
    # LLM client (Protocol + concrete)
    "AnthropicClaudeClient",
]
