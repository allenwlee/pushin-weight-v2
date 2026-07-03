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
from dataclasses import dataclass
from typing import Any, Literal, Protocol


logger = logging.getLogger(__name__)


# --- Type aliases --------------------------------------------------------


Source = Literal["user_mention", "hashtag", "body_keyword", "search_term"]


# Alias for tests / external callers that prefer the explicit type name.
# Kept identical to `Source` so callers can use either.
SourceType = Source


# Source-confidence priority (R2). user_mention + hashtag are higher
# confidence than body_keyword + search_term because they are explicit
# brand signals (someone typed the handle or hashtag). Mixed signals
# take the MAX confidence across contributing sources.
BRAND_SOURCE_PRIORITY: dict[Source, float] = {
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


def _resolve_signal_model() -> str:
    """Return the model id for signal classification.

    Direct Anthropic API: "claude-haiku-4-5" (cheapest Claude, fits the
    structured-JSON signal task).

    Minimax proxy (ANTHROPIC_BASE_URL points at api.minimax.io/anthropic):
    the proxy only routes the operator's registered model id
    (ANTHROPIC_MODEL env). Default to "MiniMax-M3.0" — it does NOT emit
    a thinking block for structured JSON (6 output tokens per request).
    "MiniMax-M2.7" still works but emits ~150 tokens of thinking per
    call (5.5x slower) — the operator's ~/.env.secrets previously had
    ANTHROPIC_MODEL=MiniMax-M2.7 set, which silently triggered that
    slower path.

    Resolution order:
      1. ANTHROPIC_MODEL env var (set by the operator's shell / wrapper)
      2. "MiniMax-M3.0" if ANTHROPIC_BASE_URL routes through api.minimax.io
      3. "claude-haiku-4-5" default (when talking to api.anthropic.com directly)
    """
    import os
    explicit = os.environ.get("ANTHROPIC_MODEL")
    if explicit:
        return explicit
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "")
    if "minimax.io" in base_url:
        return "MiniMax-M3.0"
    return "claude-haiku-4-5"


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
) -> dict[str, Any]:
    """Call the LLM with exponential backoff (mirrors translator)."""
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            return client.messages_create(
                model=_SIGNAL_MODEL,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
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


_VALID_DISCOURSE: frozenset[str] = frozenset({
    "genuine_hype", "sarcasm", "dunk_yingyang", "self_deprecation",
    "cope", "fud", "distillation_accusation", "ai_slop_critique",
    "absurdist_meme",
})
_VALID_NATIONALISM: frozenset[str] = frozenset({
    "none", "mild_pro", "pro", "constructive_critical", "anti", "mixed",
})
_VALID_POST_TYPES = {
    "buzz_releases", "hands_on_usage",
    "performance_comparisons", "feedback_questions",
}
_VALID_SENTIMENTS = {"positive", "negative", "neutral", "mixed"}


def build_pragmatics_full_prompt(text: str, brand_ids: list[str]) -> str:
    """Build the §5.1 + U9 merged per-post classifier prompt."""
    brand_list = ", ".join(brand_ids) if brand_ids else "(none)"
    return (
        "You classify a tweet's relationship to a list of brands, "
        "across five dimensions.\n\n"
        "Tweet text:\n"
        f"\"\"\"\n{text}\n\"\"\"\n\n"
        f"Brands (in order): {brand_list}\n\n"
        "For each brand, return FIVE fields from these exact sets:\n\n"
        "post_type (4 buckets — what KIND of post):\n"
        "  - buzz_releases            (brand announced something new)\n"
        "  - hands_on_usage           (user is using / showing the brand)\n"
        "  - performance_comparisons  (benchmark / eval / head-to-head)\n"
        "  - feedback_questions       (user asking how-to / help / complaint)\n\n"
        "sentiment (4 values — the VALENCE):\n"
        "  - positive                 (praise, enthusiasm)\n"
        "  - negative                 (criticism, disappointment)\n"
        "  - neutral                  (informational / question)\n"
        "  - mixed                    (multiple valences in one post)\n\n"
        "discourse_role (9 keys — pragmatic register, §2):\n"
        "  - genuine_hype             (straight praise)\n"
        "  - sarcasm                  (English verbal irony)\n"
        "  - dunk_yingyang            (阴阳怪气 / passive-aggressive dunk)\n"
        "  - self_deprecation         (自嘲 / self-mockery)\n"
        "  - cope                     (嘴硬 / stubborn denial)\n"
        "  - fud                      (唱衰 / spreading doom)\n"
        "  - distillation_accusation  (套壳 / 蒸馏指控)\n"
        "  - ai_slop_critique         (AI content-garbage accusation)\n"
        "  - absurdist_meme           (抽象整活 / absurdist antics)\n\n"
        "china_nationalism (6-step scale, §4.4):\n"
        "  - none                     (no China-nationalism layer)\n"
        "  - mild_pro                 (温和亲华 — subtle positive)\n"
        "  - pro                      (亲华 — open positive)\n"
        "  - constructive_critical   (建设性批评 — pro-CN criticism)\n"
        "  - anti                     (反华 — hostile)\n"
        "  - mixed                    (mixed modes in one post)\n\n"
        "us_nationalism (6-step scale, same as china_nationalism but\n"
        "applied to the US axis — anti = 反美, etc.):\n"
        "  - none / mild_pro / pro / constructive_critical / anti / mixed\n\n"
        "Rules:\n"
        "1. Return ONLY a JSON object: {\"classifications\": "
        "[{\"brand_id\": str, \"post_type\": str, \"sentiment\": str, "
        "\"discourse_role\": str, \"china_nationalism\": str, "
        "\"us_nationalism\": str}, ...]}\n"
        "2. RETURN ONE ROW FOR EVERY BRAND LISTED. The brand list "
        "is what the keyword detector found in the text — if a "
        "brand name appears, you MUST produce a row. Cross-brand "
        "comparison posts (\"GLM 5.2 vs Kimi K2.7\"), reply chains "
        "where the brand is mentioned, posts sharing screenshots "
        "with the brand name — ALL count. Only skip a brand if "
        "the post text contains ZERO mention of it (this should be "
        "impossible given how the brand list was derived).\n"
        "3. Use the EXACT brand_id strings from the list above.\n"
        "4. nationalism is ORTHOGONAL to post_type × sentiment × "
        "discourse_role — a single post can be e.g. (perf_compare, "
        "positive, genuine_hype, none, constructive_critical).\n"
        "5. If the tweet is off-topic for all brands (shouldn't "
        "happen if the brand list is non-empty), return "
        "{\"classifications\": []}.\n"
        "6. No prose, no explanation, no code fences.\n"
    )


def _parse_pragmatics_full_response(
    response: dict[str, Any],
    brand_registry_ids: set[str],
) -> dict[str, dict[str, str]]:
    """Parse the merged LLM response with per-brand five-prong rows."""
    if not isinstance(response, dict):
        return {}
    results = response.get("classifications")
    if not isinstance(results, list):
        return {}
    out: dict[str, dict[str, str]] = {}
    for item in results:
        if not isinstance(item, dict):
            continue
        b = item.get("brand_id")
        if not isinstance(b, str) or b not in brand_registry_ids:
            continue
        pt = item.get("post_type")
        sent = item.get("sentiment")
        dr = item.get("discourse_role")
        cn = item.get("china_nationalism")
        un = item.get("us_nationalism")
        post_type = pt if pt in _VALID_POST_TYPES else "hands_on_usage"
        sentiment = sent if sent in _VALID_SENTIMENTS else "neutral"
        discourse_role = (
            dr if isinstance(dr, str) and dr in _VALID_DISCOURSE
            else "uncategorized"
        )
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
    return out


def classify_pragmatics_full(
    text: str,
    brand_ids: list[str],
    brand_registry: list,
    anthropic_client: "ClaudeClient | None" = None,
) -> dict[str, dict[str, str]]:
    """U4: per-brand five-prong classification via one merged LLM call."""
    if not brand_ids or not text:
        return {}
    if anthropic_client is None:
        return {}
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
        response = _call_signal_with_retry(anthropic_client, prompt)
    except Exception as e:
        logger.warning(
            "classify_pragmatics_full: LLM call failed after %d retries: %s",
            _MAX_RETRIES, e,
        )
        return {}
    parsed = _parse_pragmatics_full_response(response, registry_ids)
    if not parsed:
        logger.warning(
            "classify_pragmatics_full returned no classifications for "
            "text=%r brand_ids=%r",
            text[:80], brand_ids,
        )
    return parsed


# --- Real Anthropic client (lazy import) --------------------------------


class AnthropicClaudeClient:
    """Production Claude client using the Anthropic SDK.

    Mirrors `x_monitor.translator.AnthropicClaudeClient`. Imports
    `anthropic` lazily so test envs without the SDK can still import
    this module.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
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

    def messages_create(self, **kwargs: Any) -> dict[str, Any]:
        """Send a messages.create request and return the parsed JSON."""
        import json as _json
        msg = self._client.messages.create(**kwargs)
        text_parts: list[str] = []
        for block in msg.content:
            if hasattr(block, "text"):
                text_parts.append(block.text)
        raw = "\n".join(text_parts).strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            inner = (
                "\n".join(lines[1:-1])
                if lines[-1].strip().startswith("```")
                else "\n".join(lines[1:])
            )
            raw = inner.strip()
        return _json.loads(raw)


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
    "build_signal_prompt",
    # LLM client (Protocol + concrete)
    "AnthropicClaudeClient",
]
