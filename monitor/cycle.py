"""Cycle orchestrator for x-monitor v2 Django migration (U6 + U1/U2).

Reuses x_monitor pipeline modules (query_plan, apify, attribution,
translator, reattribute) for the fetch / attribute / persist / translate /
classify steps.  Persists results via Django ORM instead of
x_monitor.store.Store.

The cycle flow:
  1. Load primary keywords from BrandKeyword (Django ORM)
  2. Plan calls via x_monitor.query_plan.plan_calls()
  3. For each call: fetch tweets via TwitterApiClient
  4. Attribute to brands via x_monitor.attribution.attribute_to_brands
  5. Persist via Django ORM (Post, Account, PostBrand, PostBrandMention,
     PostBrandSignal)
  6. Translate via x_monitor.translator.translate_batch_pragmatics (U1)
  7. Classify via x_monitor.attribution.classify_batch_pragmatics_full (U1)
  8. Quote-tweet channel (official every cycle + non-official daily)
  9. Emit run summary in LATEST.json compatible shape

LLM guardrails (U2):
  - Pause between classifier batches via X_MONITOR_LLM_PAUSE_SECONDS
  - Hard cap via _max_llm_calls (None = no cap, used by backfill command)

Key constraint (KTD2): The legacy x_monitor/run.py and macOS launchd
agents MUST remain untouched. This is a NEW entry point.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from django.conf import settings
from pathlib import Path
from x_monitor.config import Config, load_config
from django.db import transaction

from core.models import (
    Account,
    Brand,
    BrandKeyword,
    BrandSearchTerm,
    CallState,
    Post,
    PostBrand,
    PostBrandMention,
    PostBrandSignal,
    PostTypeKey,
    SentimentKey,
)

# x_monitor imports — reuse existing pipeline modules.
# These have no import-time side effects; they don't touch Store or
# read config.yaml at module level.
from x_monitor.apify import (
    TwitterApiAuthError,
    TwitterApiClient,
    TwitterApiRateLimitError,
    TwitterApiServerError,
)
from x_monitor.attribution import (
    UNATTRIBUTED_BRAND_ID,
    MentionRow,
    attribute_to_brands,
    compile_keyword_index,
)
from x_monitor.config import KNOWN_MODELS
from x_monitor.queries import X_LENGTH_CAP, assert_under_length_cap
from x_monitor.query_plan import PlannedCall, XQuerySpec, plan_calls

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Brand alias map (mirrors x_monitor/run.py:_BRAND_ALIASES)
# ---------------------------------------------------------------------------

_BRAND_ALIASES: dict[str, str] = {
    "kimi": "moonshot_kimi",
    "k2": "moonshot_kimi",
    "月之暗面": "moonshot_kimi",
    "暗面": "moonshot_kimi",
    "mimo": "mimo",
    "xiaomi": "mimo",
    "ling": "inclusionai",
    "ring": "inclusionai",
    "ming": "inclusionai",
    "chatglm": "glm",
    "智谱": "glm",
    "通义千问": "qwen",
    "通义": "qwen",
    "深度求索": "deepseek",
    "海螺": "minimax",
    "hailuo": "minimax",
}


# ============================================================================
# Helpers
# ============================================================================


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ============================================================================
# Incremental harvest cursor (plan 2026-07-27-002, U1)
# ============================================================================
#
# v1 (x_monitor/run.py) swept a time window per call: it read
# call_state.last_completed_at, derived a `since_time` floor from it, fetched
# everything in that window, then advanced the cursor.  v2 shipped without
# this, so every 15-minute cycle re-requested the newest <=100 posts per query
# with no time bounds -- cycles overlapped heavily and anything that scrolled
# past that slice between cycles was lost.  That was ~half of daily volume.
#
# These helpers restore the cursor.  Two deliberate differences from v1:
#   * the first window is CLAMPED (see cfg.cycle.max_lookback) so a stale cursor cannot
#     request a multi-day sweep that would silently truncate against the
#     per-call page cap;
#   * the value written is the same instant passed as `until_time`, so
#     consecutive windows chain exactly (v1 never bounded the upper end and
#     leaned on the overlap to absorb the difference).

# Boundary overlap re-requested on each cycle so a post written in the same
# second as the previous cursor cannot fall between two windows.  Mirrors v1's
# CURSOR_OVERLAP_HOURS (x_monitor/run.py:67).  Duplicates are discarded by
# tweet_id dedup, so overlap is cheap; a gap is not recoverable.





# CallState.bucket is TextField(blank=True, default=""), but every v2
# PlannedCall carries bucket=None.  Normalize on both read and write so the
# two never address different rows.  Mirrors v1's _NULL_BUCKET_SENTINEL
# (x_monitor/store.py:455-459).
_NULL_BUCKET_SENTINEL = ""




def _matches_any_term(text: str, quoted_text: str, terms: list[str]) -> bool:
    """Return True if any term appears in text or quoted_text (case-insensitive).

    Used by the U5 post-fetch ban match in CycleRunner.run(). terms
    must already be lowercased. Empty terms list → no match.
    """
    if not terms:
        return False
    haystack = ((text or "") + "\n" + (quoted_text or "")).lower()
    return any(term in haystack for term in terms if term)


def _apply_relevancy_gate(
    items: list[dict[str, Any]],
    *,
    call_id: str,
    llm_call,
) -> list[dict[str, Any]]:
    """Apply the U6 binary LLM relevancy gate to items.

    Per-item brand_id (set by _attribute_items) drives the gate via
    x_monitor.relevancy.should_apply_binary_gate. Drop decisions are
    returned; KEEP/uncertain items pass through. When llm_call is
    None the gate is a no-op (the constructor's default).
    """
    if llm_call is None:
        return items
    # Lazy import — x_monitor.relevancy is a thin module without
    # Django dependencies, but we keep the import deferred so the
    # cycle module can be imported in environments where the relevancy
    # gate is intentionally disabled.
    from x_monitor.relevancy import (
        call_binary_relevancy_llm,
        should_apply_binary_gate,
    )

    out: list[dict[str, Any]] = []
    for it in items:
        brand_hints = it.get("brand_id") or ""
        if not should_apply_binary_gate(
            call_id=call_id, brand_hints=brand_hints
        ):
            out.append(it)
            continue
        text = it.get("text") or ""
        verdict = call_binary_relevancy_llm(
            post_text=text,
            call_id=call_id,
            brand_hints=brand_hints,
            llm_call=llm_call,
        )
        if verdict.decision == "DROP":
            continue  # drop
        out.append(it)
    return out


def _item_created_epoch(it: dict[str, Any]) -> int | None:
    """Best-effort unix epoch for a normalized tweet dict (for window walks)."""
    raw_ep = it.get("created_at_epoch") or it.get("createdAtEpoch")
    if raw_ep is not None:
        try:
            return int(raw_ep)
        except (TypeError, ValueError):
            pass
    created_at_str = it.get("created_at") or it.get("createdAt") or ""
    if not created_at_str:
        return None
    for fmt in (
        "%a %b %d %H:%M:%S %z %Y",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
    ):
        try:
            parsed = datetime.strptime(created_at_str, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return int(parsed.timestamp())
        except (ValueError, TypeError):
            continue
    try:
        parsed = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp())
    except (ValueError, TypeError):
        return None


def _cursor_key(call: PlannedCall) -> dict[str, str]:
    """Build the call_state identity tuple for one planned call.

    Note that `brand_id` here is the *planner's placeholder*, not a real
    brand: "*" for the list-based Call A, and the first brand in iteration
    order for the B/C specs (x_monitor/query_plan.py:351, 370-379).
    Disambiguation between the six rows is owned by `call_id`.  Never
    re-derive brand_id from post-attribution -- that would collapse several
    B/C specs onto one cursor row.

    `query_id` follows v1's convention of carrying the planner's call_id
    (x_monitor/run.py:199-203).
    """
    return {
        "brand_id": call.brand_id,
        "call_id": call.call_id,
        "call_kind": call.call_kind,
        "bucket": call.bucket or _NULL_BUCKET_SENTINEL,
        "query_id": call.call_id,
    }


def _read_cursor_since(call: PlannedCall, *, now: datetime, cfg: Config) -> datetime:
    """Resolve the `since_time` floor for one call, clamped to cfg.cycle.max_lookback.

    Returns an aware UTC datetime, always.  Four cases:
      * no cursor row (cold start)  -> now - cfg.cycle.max_lookback
      * fresh cursor                -> cursor - cfg.cycle.cursor_overlap
      * stale cursor (or DB error)  -> now - cfg.cycle.max_lookback (the clamp)
      * future cursor (NTP rollback, a v1 legacy row whose TZ was
        mis-parsed, a manual psql write) -> now - cfg.cycle.cursor_overlap

    The future case is the subtle one: a prior AFTER now would otherwise
    produce since > until, TwitterAPI.io returns [] with no error, and the
    successful-empty-sweep advance rewinds the cursor to now -- permanently
    losing the (now, prior) span. Clamping since to (now - overlap) bounds
    the damage to a one-cycle re-fetch, which dedup absorbs.
    """
    floor = now - timedelta(hours=cfg.cycle.max_lookback_hours)
    ceiling = now - timedelta(seconds=cfg.cycle.cursor_overlap_seconds)
    try:
        row = CallState.objects.filter(**_cursor_key(call)).first()
        if row is None or row.last_completed_at is None:
            return floor
        prior = row.last_completed_at
        # Defensive: a naive value (USE_TZ flipped, a raw SQL insert, or a
        # value carried over from v1's ISO-string storage) would make the
        # comparison below raise TypeError. The per-call loop has no
        # try/except, so that would abort the WHOLE cycle -- all six calls --
        # rather than degrade one. Coerce to UTC instead.
        if prior.tzinfo is None:
            logger.warning(
                "_read_cursor_since: naive last_completed_at for call_id=%s; "
                "assuming UTC",
                call.call_id,
            )
            prior = prior.replace(tzinfo=timezone.utc)
        # A prior in the FUTURE would invert the window (since > until),
        # make TwitterAPI.io return [] with no error, and the empty-sweep
        # advance would rewind the cursor to now -- permanently losing the
        # (now, prior) span. Clamp the lower bound to (now - overlap) so the
        # damage is bounded to a single re-fetch that dedup absorbs.
        if prior > now:
            logger.warning(
                "_read_cursor_since: future last_completed_at for call_id=%s "
                "(%s, ahead of now by %s); clamping to now - overlap. Likely "
                "causes: NTP rollback, v1 import with TZ mis-parse, or a "
                "manual DB write.",
                call.call_id,
                prior.isoformat(),
                prior - now,
            )
            return ceiling
        return max(prior - timedelta(seconds=cfg.cycle.cursor_overlap_seconds), floor)
    except Exception as exc:
        logger.warning(
            "_read_cursor_since: cursor read failed for call_id=%s: %s; "
            "falling back to clamped lookback",
            call.call_id,
            exc,
        )
        return floor


def _advance_cursor(
    call: PlannedCall, *, upper_bound: datetime, now: datetime | None = None
) -> bool:
    """Record that this call swept through `upper_bound`. Returns success.

    `upper_bound` must be the exact instant passed to the API as
    `until_time`, so the next cycle's window begins where this one ended.

    Refuses to persist a value in the future. A future stored cursor
    would invert the next window (since > until), TwitterAPI.io would
    return [] with no error, and the successful-empty-sweep advance would
    rewind the cursor to now -- permanently losing the (now, prior) span.
    Reachable on NTP rollback, a v1 legacy import with TZ mis-parse, or a
    manual psql write. The in-tree writer is the only one we control, so
    refuse here and let the read-side clamp handle anything external.

    `now` is injectable so tests with a fixed `NOW` constant do not become
    time-sensitive.

    A cursor-write failure must never abort the cycle -- the posts are
    already stored, and not advancing only costs a bounded re-fetch that
    dedup discards.  So this logs and reports False rather than raising.
    """
    if upper_bound.tzinfo is None:
        raise ValueError(
            "_advance_cursor requires an aware datetime; got a naive one "
            "(CallState.last_completed_at is TIMESTAMPTZ under USE_TZ=True)"
        )
    if upper_bound > (now or datetime.now(timezone.utc)):
        raise ValueError(
            f"_advance_cursor refuses a future upper_bound ({upper_bound}); "
            "would invert the next window and lose data. Investigate clock "
            "or call site before allowing it."
        )
    try:
        CallState.objects.update_or_create(
            **_cursor_key(call),
            defaults={"last_completed_at": upper_bound},
        )
        return True
    except Exception as exc:
        logger.warning(
            "_advance_cursor: failed to advance call_state for call_id=%s "
            "(kind=%s brand=%s): %s -- next cycle will re-sweep this window",
            call.call_id,
            call.call_kind,
            call.brand_id,
            exc,
        )
        return False


def _load_primary_keywords() -> dict[str, list[str]]:
    """Load {brand_id: [pattern, ...]} for is_primary=1 keywords from the DB.

    Mirrors Store.read_primary_brand_keywords() but via Django ORM.
    Returns empty dict on DB unavailability (safe for dry-run).
    """
    out: dict[str, list[str]] = {}
    try:
        for kw in BrandKeyword.objects.filter(is_primary=True).select_related("brand"):
            brand_id = kw.brand_id
            out.setdefault(brand_id, []).append(kw.pattern)
    except Exception as exc:
        logger.warning("_load_primary_keywords: DB read failed: %s", exc)
    return out


def _load_brand_search_terms() -> dict[str, str]:
    """Load {term: brand_id} map from brand_search_terms table.

    Mirrors Store.read_brand_search_terms() but via Django ORM.
    Returns empty dict on DB unavailability.
    """
    out: dict[str, str] = {}
    try:
        for st in BrandSearchTerm.objects.all():
            out[st.term.lower()] = st.brand_id
    except Exception as exc:
        logger.warning("_load_brand_search_terms: DB read failed: %s", exc)
    # Fold brand aliases into the map so CJK / short-form tokens resolve.
    for alias, brand_id in _BRAND_ALIASES.items():
        out.setdefault(alias.lower(), brand_id)
    return out


def _build_brand_index(
    models: list[str],
) -> tuple[Any, dict[str, str]]:
    """Build the per-cycle brand keyword index + search-term map.

    Mirrors x_monitor/run.py:_build_brand_index. The keyword index is
    self-brand-only (each enabled model name matches itself in post text).
    Brand-specific multi-token lists are loaded separately from
    brand_keywords (DB).
    """
    keyword_triples: list[tuple[str, str, bool]] = [
        (m, m, False) for m in models if m in KNOWN_MODELS
    ]
    index = compile_keyword_index(keyword_triples)
    brand_search_terms: dict[str, str] = {
        tok.lower(): bid for bid, tok, _ in keyword_triples
    }
    return index, brand_search_terms


def _resolve_enabled_models(cfg: Config, brand_filter: list[str] | None = None) -> list[str]:
    """Resolve the enabled model list for a cycle.

    Reads from Config.enabled_models (plan 2026-08-01-001 U2). When
    brand_filter is set (--brands CLI flag), restricts to that subset,
    intersected with the brands that exist in the DB.
    """
    base = list(cfg.enabled_models)
    if not brand_filter:
        return base
    existing = set(
        Brand.objects.filter(nickname__in=brand_filter).values_list(
            "nickname", flat=True
        )
    )
    return [b for b in brand_filter if b in existing]
def _resolve_x_monitor_list_id(cfg: Config) -> int | None:
    """Resolve the X list ID from Config.

    The Config schema's x_monitor_list_id is read from config.yaml directly.
    """
    list_id = cfg.x_monitor_list_id
    if list_id is None:
        return None
    try:
        return int(list_id)
    except (TypeError, ValueError):
        return None
def _resolve_x_query_specs(cfg: Config) -> list[XQuerySpec]:
    """Resolve per-cycle XQuerySpec list.

    Plan 2026-08-05-001 (3/5): prefer the brand-centric harvest policy
    (config/harvest_policy.yaml) when present. Fall back to legacy
    `cfg.x_query_specs` only if the policy file is absent (pre-U5 mode;
    the migration cutover removes this fallback).

    Returns:
        list[XQuerySpec] ready for plan_calls(). Already validated by
        the policy loader.
    """
    # 3/5: try policy first
    policy_path = Path("config") / "harvest_policy.yaml"
    if policy_path.exists():
        from x_monitor.harvest_policy import load_policy
        from x_monitor.specs_from_policy import specs_from_policy
        policy = load_policy(policy_path)
        return list(specs_from_policy(policy))
    # Pre-U5 fallback: legacy x_query_specs
    return list(cfg.x_query_specs)
def _upsert_account(raw: dict[str, Any]) -> Account | None:
    """Create or update an Account row from a normalized tweet dict.

    Returns the Account instance or None if the tweet has no author info.

    Dual-write (U3, R14): the Account table carries a denormalized snapshot of
    author fields that overlap with the new posts.author_* columns. Update
    Account here so downstream consumers that key off Account don't lose
    recency. Use the *correct* key names — the prior version referenced
    `author_followers` / `author_following` (without the `_count` suffix) and
    the normalize layer never set those, so the corresponding Account fields
    were silently never written.
    """
    author_id = str(raw.get("author_id") or raw.get("authorId") or "")
    if not author_id:
        return None
    defaults: dict[str, Any] = {}
    handle = raw.get("author_handle") or raw.get("authorHandle") or ""
    if handle:
        defaults["handle"] = handle
    display_name = raw.get("author_display_name") or raw.get("author_name") or raw.get("authorName") or ""
    if display_name:
        defaults["display_name"] = display_name
    # Per U3 § 1.7, new metric columns use NULL-when-absent. The Account dual-write
    # was already using 0-coercion in the prior implementation; preserve that for
    # backward-compat with existing Account readers that expect an int.
    verified = bool(
        raw.get("author_verified")
        or raw.get("author_is_blue_verified")
        or raw.get("authorVerified")
    )
    defaults["verified"] = verified
    followers = raw.get("author_followers_count")
    if followers is not None:
        defaults["followers_count"] = int(followers)
    following = raw.get("author_following_count")
    if following is not None:
        defaults["following_count"] = int(following)
    favourites = raw.get("author_favourites_count")
    if favourites is not None:
        defaults["favourites_count"] = int(favourites)
    statuses = raw.get("author_statuses_count")
    if statuses is not None:
        defaults["statuses_count"] = int(statuses)
    media = raw.get("author_media_count")
    if media is not None:
        defaults["media_count"] = int(media)
    fast_followers = raw.get("author_fast_followers_count")
    if fast_followers is not None:
        defaults["fast_followers_count"] = int(fast_followers)
    is_blue = raw.get("author_is_blue_verified")
    if is_blue is not None:
        defaults["is_blue_verified"] = bool(is_blue)
    verified_type = raw.get("author_verified_type")
    if verified_type is not None:
        defaults["verified_type"] = verified_type
    profile_pic = raw.get("author_profile_picture")
    if profile_pic is not None:
        defaults["profile_picture"] = profile_pic
    location = raw.get("author_location")
    if location is not None:
        defaults["location"] = location
    description = raw.get("author_description")
    if description is not None:
        defaults["description"] = description
    profile_bio = raw.get("author_profile_bio_text")
    if profile_bio is not None:
        defaults["profile_bio_text"] = profile_bio
    acc, _created = Account.objects.update_or_create(
        author_id=author_id, defaults=defaults
    )
    return acc


def _upsert_post(raw: dict[str, Any], account: Account | None = None) -> Post | None:
    """Create or update a Post row from a normalized tweet dict.

    Returns the Post instance or None if the tweet has no id.

    Posts.raw denormalization (U3): writes both the typed columns (per
    `docs/plans/2026-07-27-004-…`) AND the `raw` JSONField for one release
    cycle. The dual-write is removed in U4 once the harvest has had ≥1
    cycle on the new code. The `quoted_status_id` is gated by Policy A
    (only set if the parent tweet_id already exists in posts).
    """
    tweet_id = str(raw.get("id") or raw.get("tweet_id") or "")
    if not tweet_id:
        return None
    defaults: dict[str, Any] = {}
    if account is not None:
        defaults["author"] = account
    handle = raw.get("author_handle") or raw.get("authorHandle") or ""
    if handle:
        defaults["author_handle"] = handle
    text = raw.get("text") or ""
    if text:
        defaults["text"] = text
    lang = raw.get("lang") or ""
    if lang:
        defaults["lang"] = lang
    created_at_str = raw.get("created_at") or raw.get("createdAt") or ""
    if created_at_str:
        parsed = None
        for fmt in (
            "%a %b %d %H:%M:%S %z %Y",   # Twitter API: "Wed Jul 22 03:40:35 +0000 2026"
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S%z",
        ):
            try:
                parsed = datetime.strptime(created_at_str, fmt).replace(tzinfo=timezone.utc)
                break
            except (ValueError, TypeError):
                continue
        if parsed is None:
            try:
                parsed = datetime.fromisoformat(
                    created_at_str.replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass
        if parsed:
            defaults["created_at"] = parsed
    like_count = raw.get("like_count") or raw.get("likeCount")
    if like_count is not None:
        defaults["like_count"] = int(like_count)
    retweet_count = raw.get("retweet_count") or raw.get("retweetCount")
    if retweet_count is not None:
        defaults["retweet_count"] = int(retweet_count)
    reply_count = raw.get("reply_count") or raw.get("replyCount")
    if reply_count is not None:
        defaults["reply_count"] = int(reply_count)
    quote_count = raw.get("quote_count") or raw.get("quoteCount")
    if quote_count is not None:
        defaults["quote_count"] = int(quote_count)
    in_reply_to = raw.get("in_reply_to_user_id") or raw.get("inReplyToUserId") or ""
    if in_reply_to:
        defaults["in_reply_to_user_id"] = str(in_reply_to)
    quoted_id = raw.get("quoted_status_id") or raw.get("quotedStatusId") or ""
    if quoted_id:
        # quoted_status_id is a FK to Post (self); must be a Post instance
        # or None. Look up the parent Post first; if it doesn't exist
        # (not yet harvested), leave the FK unset (NULL via
        # on_delete=SET_NULL).
        # The 2026-07-31 cycle run hit 8 persist failures because this
        # was passing the raw tweet-id string into a FK field.
        try:
            parent_post = Post.objects.filter(tweet_id=str(quoted_id)).only("tweet_id").first()
            if parent_post is not None:
                defaults["quoted_status_id"] = parent_post
            # else: leave FK unset; will be populated when parent is harvested
        except Exception:
            pass
    conversation_id = raw.get("conversation_id") or raw.get("conversationId") or ""
    if conversation_id:
        defaults["conversation_id"] = str(conversation_id)
    entities = raw.get("entities") or {}
    if entities:
        defaults["entities"] = entities
    source_qid = raw.get("source_query_id") or raw.get("sourceQueryId") or ""
    if source_qid:
        defaults["source_query_id"] = source_qid
    quoted_text = raw.get("quoted_text") or ""
    if quoted_text:
        defaults["quoted_text"] = quoted_text
    created_at_epoch = raw.get("created_at_epoch") or raw.get("createdAtEpoch")
    if created_at_epoch is not None:
        defaults["created_at_epoch"] = int(created_at_epoch)

    # --- § 1.2 New tweet top-level typed columns (U3).
    # Per § 1.7: new fields use NULL-when-absent, not 0/false coercion. The
    # `is not None` guard skips both missing keys AND None sentinels; the
    # normalize layer uses None for absent keys (not 0).
    for col, val in (
        ("created_at_raw", raw.get("created_at_raw")),
        ("bookmark_count", raw.get("bookmark_count")),
        ("is_reply", raw.get("is_reply")),
        ("is_retweet", raw.get("is_retweet")),
        ("is_quote", raw.get("is_quote")),
        ("in_reply_to_id", raw.get("in_reply_to_id")),
        ("in_reply_to_username", raw.get("in_reply_to_username")),
        ("tweet_type", raw.get("tweet_type")),
        ("tweet_url", raw.get("tweet_url")),
        ("tweet_twitter_url", raw.get("tweet_twitter_url")),
        ("card", raw.get("card")),
        ("place", raw.get("place")),
        ("client_source", raw.get("client_source")),
        ("view_count", raw.get("view_count")),
        ("article", raw.get("article")),
        ("is_limited_reply", raw.get("is_limited_reply")),
        ("community_info", raw.get("community_info")),
        ("display_text_range", raw.get("display_text_range")),
        ("extended_entities", raw.get("extended_entities")),
        ("quoted_author_handle", raw.get("quoted_author_handle")),
    ):
        if val is not None:
            defaults[col] = val

    # --- § 1.3 New author typed columns (U3).
    for col, val in (
        ("author_name", raw.get("author_name")),
        ("author_followers_count", raw.get("author_followers_count")),
        ("author_following_count", raw.get("author_following_count")),
        ("author_verified", raw.get("author_verified")),
        ("author_is_blue_verified", raw.get("author_is_blue_verified")),
        ("author_verified_type", raw.get("author_verified_type")),
        ("author_is_translator", raw.get("author_is_translator")),
        ("author_is_automated", raw.get("author_is_automated")),
        ("author_automated_by", raw.get("author_automated_by")),
        ("author_description", raw.get("author_description")),
        ("author_location", raw.get("author_location")),
        ("author_media_count", raw.get("author_media_count")),
        ("author_statuses_count", raw.get("author_statuses_count")),
        ("author_favourites_count", raw.get("author_favourites_count")),
        ("author_fast_followers_count", raw.get("author_fast_followers_count")),
        ("author_can_dm", raw.get("author_can_dm")),
        ("author_can_media_tag", raw.get("author_can_media_tag")),
        ("author_profile_picture", raw.get("author_profile_picture")),
        ("author_profile_bio", raw.get("author_profile_bio")),
        ("author_cover_picture", raw.get("author_cover_picture")),
        ("author_pinned_tweet_ids", raw.get("author_pinned_tweet_ids")),
        ("author_affiliates_highlighted_label",
         raw.get("author_affiliates_highlighted_label")),
        ("author_withheld_in_countries",
         raw.get("author_withheld_in_countries")),
        ("author_possibly_sensitive", raw.get("author_possibly_sensitive")),
        ("author_has_custom_timelines",
         raw.get("author_has_custom_timelines")),
        ("author_entities", raw.get("author_entities")),
        ("author_twitter_url", raw.get("author_twitter_url")),
        ("author_type", raw.get("author_type")),
        ("author_url", raw.get("author_url")),
        ("author_created_at_raw", raw.get("author_created_at_raw")),
        ("author_status", raw.get("author_status")),
    ):
        if val is not None:
            defaults[col] = val

    post, _created = Post.objects.update_or_create(
        tweet_id=tweet_id, defaults=defaults
    )
    return post


def _persist_attribution(
    post: Post,
    brand_ids: list[str],
    mentions: list[MentionRow],
    classifications: dict[str, tuple[str, str]] | None = None,
) -> int:
    """Persist PostBrand, PostBrandMention, and PostBrandSignal rows.

    Idempotent: uses get_or_create for junction tables, update_or_create
    for signals.

    Returns the number of brands this post was attributed to.
    """
    n = 0
    seen_sources: set[tuple[str, str, str]] = set()  # (brand_id, source) for dedup
    for mention in mentions:
        if not mention.brand_id or mention.brand_id == UNATTRIBUTED_BRAND_ID:
            continue
        bid = mention.brand_id
        # PostBrand (junction)
        PostBrand.objects.get_or_create(
            post=post,
            brand_id=bid,
            defaults={"weight": 1.0},
        )
        # PostBrandMention (one per source per brand)
        source_key = (bid, mention.source or "body_keyword")
        if source_key not in seen_sources:
            seen_sources.add(source_key)
            PostBrandMention.objects.get_or_create(
                post=post,
                brand_id=bid,
                source=mention.source or "body_keyword",
                defaults={"raw_token": mention.raw_token or ""},
            )
        if bid not in brand_ids:
            brand_ids.append(bid)
        n += 1

    # PostBrandSignal (per brand, per post_type)
    if classifications:
        for bid, (post_type, sentiment) in classifications.items():
            # Ensure the lookup keys exist
            pt_key, _ = PostTypeKey.objects.get_or_create(key=post_type)
            sent_key, _ = SentimentKey.objects.get_or_create(key=sentiment)
            PostBrandSignal.objects.update_or_create(
                post=post,
                brand_id=bid,
                post_type=pt_key,
                defaults={"sentiment": sent_key},
            )
    return len(set(brand_ids))


# ============================================================================
# CycleRunner
# ============================================================================


def plan_calls_for_cycle(cfg: Config | None = None) -> list[PlannedCall]:
    """Plan harvest calls from settings — shared by CycleRunner and backfill.

    Reads X_MONITOR_LIST_ID, brand filter, primary keywords, and
    x_query_specs from Django settings. Returns empty list when the
    list ID is not configured.

    The optional `cfg` parameter exists so production callers can pass
    the loaded Config (avoids a second disk read for callers that
    already loaded it). When `cfg is None`, the function falls back
    to load_config(Path("config.yaml")) — preserving backward
    compatibility with test monkeypatches that shim the function
    with zero-arg lambdas.
    """
    if cfg is None:
        cfg = load_config(Path("config.yaml"))

    list_id = _resolve_x_monitor_list_id(cfg)
    if list_id is None:
        logger.warning(
            "plan_calls_for_cycle: X_MONITOR_LIST_ID not set — "
            "Call A is list-based; without it no calls are planned."
        )
        return []

    x_query_specs = _resolve_x_query_specs(cfg) or []

    # 3/5: prefer policy-derived primary_keywords over the DB-backed
    # keyword table for search-token sourcing (R8). DB remains for
    # attribution.
    primary_keywords: dict[str, list[str]] | None = None
    policy_path = Path("config") / "harvest_policy.yaml"
    if policy_path.exists():
        from x_monitor.harvest_policy import load_policy
        from x_monitor.specs_from_policy import primary_keywords_from_policy
        policy = load_policy(policy_path)
        primary_keywords = primary_keywords_from_policy(policy)
    else:
        primary_keywords = _load_primary_keywords()

    brand_filter_raw = getattr(settings, "X_MONITOR_CYCLE_BRAND_FILTER", None)
    if brand_filter_raw and isinstance(brand_filter_raw, str):
        brand_filter = [b.strip() for b in brand_filter_raw.split(",") if b.strip()]
        if brand_filter:
            primary_keywords = {
                k: v for k, v in primary_keywords.items() if k in brand_filter
            }
            logger.info("plan_calls_for_cycle: brand filter active — %s", brand_filter)

    return plan_calls(
        list_id,
        x_query_specs,
        primary_keywords=primary_keywords,
    )


class CycleRunner:
    """Orchestrates one full harvest cycle.

    Usage:
        runner = CycleRunner(dry_run=True)
        stats = runner.run()
    """

    def __init__(
        self,
        *,
        cfg: Config | None = None,
        dry_run: bool = False,
        cycle_kind: str = "manual",
        _backfill_call_ids: list[str] | None = None,
        _max_llm_calls: int | None = None,
        _relevancy_llm_call=None,
    ) -> None:
        # Single config source-of-truth (plan 2026-08-01-001). When None,
        # load from config.yaml at the repo root. Tests pass a pre-built
        # Config to avoid disk I/O.
        if cfg is None:
            cfg = load_config(Path("config.yaml"))
        self.cfg = cfg
        self.dry_run = dry_run
        self.cycle_kind = cycle_kind  # 'scheduled' or 'manual'
        # If set, only execute these call IDs (all must be in the plan).
        # Used by the backfill command for batched, resumable execution.
        self._backfill_call_ids = _backfill_call_ids
        # Hard cap on LLM batches per invocation.  None = no cap.
        # Used by the backfill command to limit API spend on large windows.
        self._max_llm_calls = _max_llm_calls
        # U6 runtime wire-in: injected llm_call(system, user) -> str
        # dependency for the binary relevancy gate (R19a +
        # x_monitor/relevancy.py). Default None → gate is a no-op (KEEP).
        # Production wire-in passes an anthropic_messages_call function.
        self._relevancy_llm_call = _relevancy_llm_call
        self._llm_call_count: int = 0
        # Per-cycle accumulators for the run summary
        self._posts_seen: int = 0
        self._posts_inserted: int = 0
        self._posts_attributed: int = 0
        self._api_calls: int = 0
        self._errors: list[str] = []
        # Plan 2026-08-01-002 U4: typed counters surfaced via --json
        # n_errors_by_type. Each key represents a class of tolerated error
        # the cycle can recover from. The dashboard uses these to flag
        # silent-failure modes (e.g., "translator_batch_failed > 0 for 3
        # cycles in a row" = lang_detected regression in production).
        self._error_counts: dict[str, int] = {
            "translator_batch_failed": 0,
            "classifier_batch_failed": 0,
        }

    # ------------------------------------------------------------------
    # Step 1: Plan
    # ------------------------------------------------------------------

    def _plan_calls(self) -> list[PlannedCall]:
        """Build the per-cycle call list via plan_calls_for_cycle()."""
        try:
            calls = plan_calls_for_cycle(self.cfg)
        except (TypeError, ValueError) as exc:
            logger.warning("CycleRunner._plan_calls: plan_calls failed: %s", exc)
            self._errors.append(f"plan: {exc}")
            return []

        logger.info(
            "CycleRunner._plan_calls: %d calls planned",
            len(calls),
        )
        return calls

    # ------------------------------------------------------------------
    # Step 2: Fetch
    # ------------------------------------------------------------------

    def _resolve_window(
        self, call: PlannedCall, *, now: datetime
    ) -> tuple[int, int, bool]:
        """Resolve the (since_time, until_time) epoch window for one call.

        Returns (since_epoch, until_epoch, cursor_owned).  `cursor_owned` is
        False when the operator supplied an explicit window (the backfill
        command sets X_MONITOR_CYCLE_SINCE_TIME / _UNTIL_TIME): those runs
        sweep a historical span, so advancing the live cursor to their upper
        bound would skip everything in between.  R6.
        """
        op_since = getattr(settings, "X_MONITOR_CYCLE_SINCE_TIME", None)
        op_until = getattr(settings, "X_MONITOR_CYCLE_UNTIL_TIME", None)
        # `is not None`, not a falsy check: epoch 0 is a legitimate (if exotic)
        # lower bound for a full-history backfill, and silently substituting
        # the 2h cursor floor would quietly shrink an operator's window.
        if op_since is not None and str(op_since) != "":
            return (
                int(op_since),
                int(op_until)
                if op_until is not None and str(op_until) != ""
                else int(now.timestamp()),
                False,
            )

        since_dt = _read_cursor_since(call, now=now, cfg=self.cfg)
        return int(since_dt.timestamp()), int(now.timestamp()), True

    def _fetch_tweets(
        self, call: PlannedCall, api: TwitterApiClient, *, window: tuple[int, int]
    ) -> tuple[list[dict[str, Any]], str]:
        """Fetch tweets for one PlannedCall via TwitterAPI.io.

        Returns (items, outcome) where outcome is one of:
          "ok"                  -- the call ran; items may still be empty,
                                   which is a successful sweep of a quiet
                                   window and may advance the cursor (KTD5).
          "truncated"           -- the per-call ceiling hit before the window
                                   was exhausted. ``items`` still holds every
                                   tweet retrieved across walk passes; the
                                   caller MUST persist them but MUST NOT
                                   advance the cursor past the original window.
          "error"               -- the call failed (auth/rate/server/other).
          "length_cap_exceeded" -- the query would exceed the 512-char cap
                                   once the time operators are injected.

        The distinction matters because an empty list alone cannot tell a
        quiet window from a failure, and only the former may advance the
        cursor (R2).  Per-call errors are caught -- one bad query doesn't kill
        the cycle.

        When truncated, we walk ``until_time`` backward (Latest order returns
        newest first) up to ``self.cfg.cycle.max_truncation_walks`` times so a noisy call
        like C1 can drain a 2h clamp instead of deadlocking on the tip.
        """
        limit_per_call = getattr(settings, "X_MONITOR_CYCLE_LIMIT_PER_CALL", None)
        max_pages = getattr(settings, "X_MONITOR_CYCLE_MAX_PAGES_PER_CALL", None)
        max_per_page_cfg = getattr(settings, "X_MONITOR_CYCLE_MAX_PER_PAGE", None)
        max_results_cap = int(limit_per_call) if limit_per_call is not None else 50
        max_pages_cap = int(max_pages) if max_pages is not None else 5
        # Per-page request size (post-2026-07-31 wiring from
        # config.yaml::search.max_per_page). Falls back to 20 if unset.
        max_per_page_cap = int(max_per_page_cfg) if max_per_page_cfg is not None else 20
        # C1 needs a higher ceiling (see self.cfg.cycle.c1_max_results docstring).
        if call.call_id == "C1":
            max_results_cap = max(max_results_cap, self.cfg.cycle.c1_max_results)
            max_pages_cap = max(max_pages_cap, self.cfg.cycle.c1_max_pages)
        since_time, until_time = window

        logger.info(
            "_fetch_tweets: call_id=%s window=[%s, %s] (%.1f min) "
            "cap=%d pages=%d",
            call.call_id,
            since_time,
            until_time,
            (until_time - since_time) / 60.0,
            max_results_cap,
            max_pages_cap,
        )

        # Guard the post-injection length (R7 / KTD6). plan_calls already ran
        # assert_under_length_cap, but on the PRE-injection query -- it cannot
        # see the ~44 chars the two time operators add. An over-cap query is
        # the worst failure mode here: TwitterAPI.io returns zero results with
        # NO error, so the call looks like a quiet window and the cursor would
        # advance straight past a span that was never searched. Reporting it as
        # a distinct failure keeps the cursor pinned so the window is retried.
        # Length uses the original until_time (widest injection); walking the
        # upper bound shorter only shrinks the operator payload.
        effective_query = (
            f"{call.query_string} since_time:{since_time} until_time:{until_time}"
        )
        try:
            assert_under_length_cap(effective_query)
        except ValueError as exc:
            logger.error(
                "_fetch_tweets: %s would be %d chars after injecting the time "
                "operators (cap %d); skipping the call rather than letting "
                "TwitterAPI.io return a silent zero. %s",
                call.call_id,
                len(effective_query),
                X_LENGTH_CAP,
                exc,
            )
            self._errors.append(
                f"fetch.{call.call_id}: query length {len(effective_query)} "
                f"exceeds {X_LENGTH_CAP} after time operators"
            )
            return [], "length_cap_exceeded"

        all_items: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        cur_until = until_time
        still_truncated = False

        for walk in range(self.cfg.cycle.max_truncation_walks):
            try:
                items, truncated = api.run_search(
                    call.query_string,
                    max_results=max_results_cap,
                    max_pages=max_pages_cap,
                    max_per_page=max_per_page_cap,
                    since_time=since_time,
                    until_time=cur_until,
                )
            except TwitterApiAuthError as exc:
                logger.error(
                    "_fetch_tweets: auth failure on %s: %s", call.call_id, exc
                )
                self._errors.append(f"fetch.{call.call_id}: auth: {exc}")
                return all_items, ("error" if not all_items else "truncated")
            except (TwitterApiRateLimitError, TwitterApiServerError) as exc:
                logger.warning(
                    "_fetch_tweets: rate/server error on %s: %s", call.call_id, exc
                )
                self._errors.append(f"fetch.{call.call_id}: {exc}")
                return all_items, ("error" if not all_items else "truncated")
            except Exception as exc:
                logger.warning(
                    "_fetch_tweets: error on %s: %s", call.call_id, exc
                )
                self._errors.append(f"fetch.{call.call_id}: {exc}")
                return all_items, ("error" if not all_items else "truncated")

            self._api_calls += 1
            new_on_pass = 0
            for it in items or []:
                tid = str(it.get("id") or it.get("tweet_id") or "")
                if tid and tid in seen_ids:
                    continue
                if tid:
                    seen_ids.add(tid)
                all_items.append(it)
                new_on_pass += 1

            if not truncated:
                still_truncated = False
                if walk > 0:
                    logger.info(
                        "_fetch_tweets: call_id=%s drained window after %d "
                        "walk(s); total_items=%d",
                        call.call_id,
                        walk + 1,
                        len(all_items),
                    )
                break

            still_truncated = True
            epochs = [
                ep
                for it in (items or [])
                if (ep := _item_created_epoch(it)) is not None
            ]
            if not epochs:
                logger.warning(
                    "_fetch_tweets: call_id=%s truncated but no parseable "
                    "created_at on %d items; cannot walk further "
                    "(total_items=%d)",
                    call.call_id,
                    len(items or []),
                    len(all_items),
                )
                break
            oldest = min(epochs)
            # until_time is exclusive; set upper bound to the oldest returned
            # so the next Latest page covers older posts only.
            if oldest <= since_time or oldest >= cur_until:
                logger.warning(
                    "_fetch_tweets: call_id=%s truncated; oldest_epoch=%s "
                    "does not advance walk (since=%s cur_until=%s); "
                    "stopping (total_items=%d)",
                    call.call_id,
                    oldest,
                    since_time,
                    cur_until,
                    len(all_items),
                )
                break
            logger.warning(
                "_fetch_tweets: call_id=%s TRUNCATED pass=%d/%d n_pass=%d "
                "total=%d window=[%s,%s] -> walk until=%s (%.1f min left)",
                call.call_id,
                walk + 1,
                self.cfg.cycle.max_truncation_walks,
                new_on_pass,
                len(all_items),
                since_time,
                cur_until,
                oldest,
                (oldest - since_time) / 60.0,
            )
            cur_until = oldest
        else:
            # exhausted walk budget while still truncated
            still_truncated = True
            logger.warning(
                "_fetch_tweets: call_id=%s still truncated after %d walks; "
                "total_items=%d — caller must hold cursor",
                call.call_id,
                self.cfg.cycle.max_truncation_walks,
                len(all_items),
            )

        if still_truncated:
            return all_items, "truncated"
        return all_items, "ok"


    def _attribute_items(
        self,
        items: list[dict[str, Any]],
        index: Any,
        brand_search_terms: dict[str, str],
    ) -> int:
        """Stamp brand_id / brand_ids / mentions on each item via
        attribute_to_brands.

        Returns the count of items that matched at least one brand.
        """
        classified = 0
        for it in items:
            body = it.get("text") or ""
            quoted = it.get("quoted_text") or ""
            post_like = {
                "tweet_id": str(it.get("id") or it.get("tweet_id") or ""),
                "id": str(it.get("id") or it.get("tweet_id") or ""),
                "text": (body + "\n" + quoted) if quoted else body,
                "created_at": it.get("created_at") or _now_iso(),
                "entities": it.get("entities", {}),
            }
            mentions: list[MentionRow] = list(
                attribute_to_brands(
                    post_like,
                    brands_accounts={},
                    brand_hashtags={},
                    compiled_keyword_index=index,
                    search_query=[],
                    brand_search_terms=brand_search_terms,
                )
            )
            brand_ids: list[str] = []
            seen_brand: set[str] = set()
            for m in mentions:
                if (
                    m.brand_id
                    and m.brand_id != UNATTRIBUTED_BRAND_ID
                    and m.brand_id not in seen_brand
                ):
                    brand_ids.append(m.brand_id)
                    seen_brand.add(m.brand_id)
            if not brand_ids:
                it["_unattributed"] = True
                it["brand_ids"] = []
                it["brand_id"] = UNATTRIBUTED_BRAND_ID
                it["mentions"] = mentions
                it["classifications"] = {}
            else:
                it["brand_id"] = brand_ids[0]
                it["brand_ids"] = brand_ids
                it["mentions"] = mentions
                it["classifications"] = {}
                classified += 1
        return classified

    # ------------------------------------------------------------------
    # Step 4: Persist
    # ------------------------------------------------------------------

    def _persist_items(
        self,
        items: list[dict[str, Any]],
    ) -> tuple[int, int, int]:
        """Persist attributed items via Django ORM.

        For each item: upsert Account → upsert Post → persist attribution
        (PostBrand + PostBrandMention + PostBrandSignal).

        Returns (n_inserted, n_attributed, n_failed).  `n_failed` matters for
        the cursor: a per-item transaction that rolled back means that tweet
        was NOT stored, so the caller must not advance past its window. Losing
        the count would make the failure permanent, because the overlap only
        re-covers the last minute and tweet_id dedup only suppresses
        duplicates of writes that already succeeded.
        """
        n_inserted = 0
        n_attributed = 0
        n_failed = 0
        for it in items:
            if it.get("_unattributed"):
                continue
            try:
                with transaction.atomic():
                    account = _upsert_account(it)
                    post = _upsert_post(it, account=account)
                    if post is None:
                        continue
                    n_inserted += 1
                    brand_ids: list[str] = list(it.get("brand_ids") or [])
                    mentions: list[MentionRow] = list(it.get("mentions") or [])
                    classifications: dict = it.get("classifications") or {}
                    n_attr = _persist_attribution(
                        post, brand_ids, mentions, classifications
                    )
                    n_attributed += n_attr
            except Exception as exc:
                n_failed += 1
                tid = str(it.get("id") or it.get("tweet_id") or "?")
                logger.warning("_persist_items: failed for tweet_id=%s: %s", tid, exc)
                self._errors.append(f"persist.{tid}: {exc}")
        return n_inserted, n_attributed, n_failed

    # ------------------------------------------------------------------
    # Step 5: Post-fetch (translate + classify)
    # ------------------------------------------------------------------

    def _run_post_fetch(
        self,
        kept_posts: list[dict[str, Any]],
    ) -> dict[str, int]:
        """Run translation + classification on the cycle's kept posts.

        Stage 1 (translate): calls translate_batch_pragmatics to produce
        text_en / text_zh_cn / lang_detected for each post.

        Stage 2 (classify): calls classify_batch_pragmatics_full to produce
        PostBrandSignal and PostBrandDiscourse rows for each post.

        Guardrails:
          - Pause between classifier batches (X_MONITOR_LLM_PAUSE_SECONDS).
          - Hard cap on LLM batches (self._max_llm_calls).  When reached,
            classification stops — remaining posts are persisted without
            labels and will be picked up by the next invocation.

        Lazy imports are used so the module loads without LLM deps.
        """
        counters = {
            "n_translated": 0,
            "n_discourse": 0,
            "n_nationalism": 0,
            "n_failed_translate": 0,
        }

        if not kept_posts:
            return counters

        # Build separate translator + classifier clients.
        # build_translator_client_from_env reads ANTHROPIC_BASE_URL only
        # (typically the MiniMax proxy path); build_anthropic_client_from_env
        # honors X_MONITOR_CLASSIFIER_BASE_URL (DeepSeek on prod). The two
        # stages route to different endpoints, so they need different
        # clients — a single shared client makes translation silently fail
        # when the classifier routes through DeepSeek (recent posts had
        # lang_detected IS NULL because translate failed against the
        # DeepSeek base URL).
        from x_monitor.reattribute import (
            build_anthropic_client_from_env,
            build_translator_client_from_env,
        )

        translator_client = build_translator_client_from_env(self.cfg)
        classifier_client = build_anthropic_client_from_env(self.cfg)
        if translator_client is None and classifier_client is None:
            logger.warning(
                "_run_post_fetch: no LLM client available — "
                "skipping translate/classify"
            )
            return counters

        # Normalize kept_posts to v1 format: {tweet_id, text, brand_ids}
        tweets: list[dict[str, Any]] = []
        for it in kept_posts:
            tid = str(it.get("id") or it.get("tweet_id") or "")
            text = it.get("text") or ""
            brand_ids = it.get("brand_ids") or []
            if tid and text:
                tweets.append({
                    "tweet_id": tid,
                    "text": text,
                    "brand_ids": list(brand_ids),
                })

        if not tweets:
            return counters

        # Build brand_registry from Brand model
        from core.models import Brand as BrandModel

        # Convert Django Brand models to v1 BrandRow shape expected by classifier
        from x_monitor.attribution import BrandRow as _BrandRow
        brand_registry = [
            _BrandRow(
                brand_id=b.nickname,
                display_name=b.display_name or b.nickname,
                accent_color=b.accent_color or "#9ca3af",
                is_sentinel=b.is_sentinel,
            )
            for b in BrandModel.objects.filter(is_sentinel=False)
        ]

        # ---- Stage 1: translate ----
        from x_monitor.translator import translate_batch_pragmatics

        if translator_client is None:
            logger.warning(
                "_run_post_fetch: no translator client (ANTHROPIC_BASE_URL "
                "+ MINIMAX_API_TOKEN not set) — skipping translate; "
                "classifier stage will run if its client is available"
            )
            translation_rows = []
        else:
            try:
                translation_rows = translate_batch_pragmatics(
                    tweets,
                    ["en", "zh_cn"],
                    translator_client,
                    on_batch_error=lambda batch, exc: self._error_counts.__setitem__(
                        "translator_batch_failed",
                        self._error_counts["translator_batch_failed"] + 1,
                    ),
                    cfg=self.cfg,
                )
            except Exception as exc:
                logger.warning("_run_post_fetch: translate failed: %s", exc, exc_info=True)
                self._error_counts["translator_batch_failed"] += 1
                translation_rows = []

        # Persist translations back to Post rows.
        # Invariant: if lang_detected is a Chinese variant (zh, zh-cn,
        # zh-hans, zh-hant, zh-tw), text_zh_cn MUST equal the source
        # text — the original IS Chinese, so the per-locale zh_CN
        # column just mirrors `text`. Same for EN when lang_detected
        # is "en". Without this, the dashboard's 翻译 column under
        # zh_CN falls back to text_translated -> text (the English
        # source) which is wrong for already-Chinese posts.
        #
        # Note: translation_rows from translate_batch_pragmatics do NOT
        # carry the source `text` (the LLM already saw it). We do one
        # bulk SELECT for the affected tweet_ids to fetch the source
        # text, then apply the per-row invariant.
        if translation_rows:
            from core.models import Post as PostModel

            CHINESE_LANG_CODES = {"zh", "zh-cn", "zh_cn", "zh-hans", "zh-hant", "zh-tw"}
            tids = [r.get("tweet_id") for r in translation_rows if r.get("tweet_id")]
            source_text_by_tid: dict[str, str] = {}
            if tids:
                for post in PostModel.objects.filter(tweet_id__in=tids).values("tweet_id", "text"):
                    source_text_by_tid[str(post["tweet_id"])] = post["text"] or ""
            for r in translation_rows:
                tid = r.get("tweet_id")
                if not tid:
                    continue
                lang_detected = r.get("lang_detected")
                source_text = source_text_by_tid.get(str(tid), "")
                text_zh_cn = r.get("text_zh_cn") or r.get("literal_zh") or None
                text_en = r.get("text_en") or None
                # Invariant: Chinese-detected posts must have text_zh_cn
                # populated (use the source text if the LLM didn't emit one).
                if lang_detected in CHINESE_LANG_CODES and not text_zh_cn:
                    text_zh_cn = source_text or None
                # Same for English-detected posts and text_en.
                if lang_detected == "en" and not text_en:
                    text_en = source_text or None
                PostModel.objects.filter(tweet_id=tid).update(
                    text_en=text_en,
                    text_zh_cn=text_zh_cn,
                    lang_detected=lang_detected or None,
                )
            counters["n_translated"] = len(translation_rows)
            counters["n_failed_translate"] = sum(
                1 for r in translation_rows if r.get("translation_failed")
            )

        # ---- Stage 2: classify ----
        from x_monitor.attribution import classify_batch_pragmatics_full

        pause_sec = getattr(settings, "X_MONITOR_LLM_PAUSE_SECONDS", 1)

        try:
            if classifier_client is None:
                logger.warning(
                    "_run_post_fetch: no classifier client — skipping classify"
                )
                return counters
            results = classify_batch_pragmatics_full(
                tweets,
                brand_registry,
                classifier_client,
                on_batch_error=lambda batch, exc: self._error_counts.__setitem__(
                    "classifier_batch_failed",
                    self._error_counts["classifier_batch_failed"] + 1,
                ),
            )
        except Exception as exc:
            logger.warning("_run_post_fetch: classify failed: %s", exc, exc_info=True)
            self._error_counts["classifier_batch_failed"] += 1
            return counters

        # Persist classifications with guardrails
        from core.models import (
            PostBrandDiscourse as PBDiscourse,
            PostBrandSignal as PBSignal,
        )

        _CLASSIFY_BATCH_SIZE = getattr(
            settings, "X_MONITOR_CLASSIFY_BATCH_SIZE", 20
        )

        for i, (tweet, result) in enumerate(zip(tweets, results)):
            tid = tweet["tweet_id"]
            by_brand = result.get("by_brand") or {}

            for brand_id, cls in by_brand.items():
                post_type = cls.get("post_type")
                sentiment = cls.get("sentiment")
                if post_type:
                    try:
                        PBSignal.objects.update_or_create(
                            post_id=tid,
                            brand_id=brand_id,
                            post_type_id=post_type,
                            defaults={"sentiment_id": sentiment or ""},
                        )
                        counters["n_discourse"] += 1
                    except Exception:
                        logger.debug(
                            "_run_post_fetch: signal FK violation for %s/%s — skipping",
                            tid, post_type,
                        )

                discourse_raw = cls.get("discourse_role")
                # discourse_role may be a string or a list — normalize
                if isinstance(discourse_raw, str):
                    discourse_keys = [discourse_raw] if discourse_raw else []
                elif isinstance(discourse_raw, list):
                    discourse_keys = discourse_raw
                else:
                    discourse_keys = []
                cn_nat = cls.get("china_nationalism")
                us_nat = cls.get("us_nationalism")

                if discourse_keys:
                    for act_idx, dk in enumerate(discourse_keys):
                        if not dk:
                            continue
                        try:
                            PBDiscourse.objects.update_or_create(
                                post_id=tid,
                                brand_id=brand_id,
                                discourse_id=dk,
                                act_id=act_idx,
                                defaults={
                                    "china_nationalism_id": cn_nat or None,
                                    "us_nationalism_id": us_nat or None,
                                },
                            )
                        except Exception:
                            logger.debug(
                                "_run_post_fetch: discourse key %r not in FK table — skipping",
                                dk,
                            )
                    counters["n_nationalism"] += 1
                elif cn_nat or us_nat:
                    # Nationalism flags present without explicit discourse role —
                    # store under an empty discourse key.
                    PBDiscourse.objects.update_or_create(
                        post_id=tid,
                        brand_id=brand_id,
                        discourse_id="",
                        act_id=0,
                        defaults={
                            "china_nationalism_id": cn_nat or None,
                            "us_nationalism_id": us_nat or None,
                        },
                    )
                    counters["n_nationalism"] += 1

            # Guard: pause / cap at batch boundaries.
            # classify_batch_pragmatics_full batches 20 posts per LLM call
            # internally.  We track boundaries in the result loop so the
            # max_llm_calls cap can stop processing past a boundary.
            if (i + 1) % _CLASSIFY_BATCH_SIZE == 0 and i + 1 < len(tweets):
                if pause_sec > 0:
                    import time as _time

                    _time.sleep(pause_sec)
                self._llm_call_count += 1
                if (
                    self._max_llm_calls is not None
                    and self._llm_call_count >= self._max_llm_calls
                ):
                    logger.info(
                        "_run_post_fetch: max_llm_calls (%d) reached — "
                        "stopping classification",
                        self._max_llm_calls,
                    )
                    break
            elif (i + 1) % _CLASSIFY_BATCH_SIZE == 0:
                self._llm_call_count += 1

        return counters

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(self) -> dict[str, Any]:
        """Execute one harvest cycle.

        Returns a run summary dict (compatible with LATEST.json shape).
        """
        run_id = (
            f"{_now_iso().replace(':', '').replace('+', '_').replace('-', '')}"
            f"-{uuid.uuid4().hex[:8]}"
        )
        started_at = _now_iso()
        t0 = time.monotonic()

        summary: dict[str, Any] = {
            "run_id": run_id,
            "started_at": started_at,
            "finished_at": None,
            "status": "running",
            "cycle_kind": self.cycle_kind,
            "dry_run": self.dry_run,
            "degraded": {},
            "calls": [],
            "totals": {
                "n_calls_planned": 0,
                "n_calls_run": 0,
                "n_results": 0,
                "n_inserted": 0,
                "n_attributed": 0,
                "n_classifications_written": 0,
            },
            "errors": [],
        }

        # ---- Step 1: Plan calls ----
        try:
            calls = self._plan_calls()
        except Exception as exc:
            logger.exception("CycleRunner.run: plan_calls failed: %s", exc)
            summary["status"] = "aborted"
            summary["degraded"]["plan"] = str(exc)
            summary["finished_at"] = _now_iso()
            summary["wall_clock_sec"] = round(time.monotonic() - t0, 3)
            summary["errors"] = self._errors
            return summary

        summary["totals"]["n_calls_planned"] = len(calls)

        # Backfill batching: narrow to the requested call IDs.
        if self._backfill_call_ids:
            requested = set(self._backfill_call_ids)
            calls = [c for c in calls if c.call_id in requested]
            if not calls:
                summary["status"] = "completed"
                summary["degraded"]["backfill"] = (
                    "No matching calls in requested batch — may already be done."
                )
                summary["finished_at"] = _now_iso()
                summary["wall_clock_sec"] = round(time.monotonic() - t0, 3)
                summary["errors"] = self._errors
                return summary

        if not calls:
            summary["status"] = "degraded"
            summary["degraded"]["no_calls"] = (
                "No calls planned — check X_MONITOR_LIST_ID in settings"
            )
            summary["finished_at"] = _now_iso()
            summary["wall_clock_sec"] = round(time.monotonic() - t0, 3)
            summary["errors"] = self._errors
            return summary

        # Record planned calls in summary
        for call in calls:
            summary["calls"].append({
                "call_id": call.call_id,
                "call_kind": call.call_kind,
                "brand_id": call.brand_id,
                "bucket": call.bucket,
                "query_length": call.query_length,
                "status": "dry_run" if self.dry_run else "planned",
                "query_string": (
                    call.query_string if self.dry_run else "[redacted]"
                ),
            })

        # ---- Dry-run: stop here ----
        if self.dry_run:
            summary["status"] = "completed"
            summary["finished_at"] = _now_iso()
            summary["wall_clock_sec"] = round(time.monotonic() - t0, 3)
            summary["errors"] = self._errors
            logger.info(
                "CycleRunner.run (dry-run): %d calls planned in %.2fs",
                len(calls), summary["wall_clock_sec"],
            )
            return summary

        # ---- Live run: fetch + attribute + persist ----
        # Check skip_fetch flag
        skip_fetch = getattr(settings, "X_MONITOR_CYCLE_SKIP_FETCH", False)

        if skip_fetch:
            logger.info("CycleRunner.run: --skip-fetch active; plan only.")
            summary["status"] = "completed"
            summary["finished_at"] = _now_iso()
            summary["wall_clock_sec"] = round(time.monotonic() - t0, 3)
            summary["errors"] = self._errors
            return summary

        # Build TwitterAPI client from environment
        try:
            api = TwitterApiClient.from_env()
        except RuntimeError as exc:
            logger.error("CycleRunner.run: cannot create API client: %s", exc)
            summary["status"] = "aborted"
            summary["degraded"]["api_client"] = str(exc)
            summary["finished_at"] = _now_iso()
            summary["wall_clock_sec"] = round(time.monotonic() - t0, 3)
            summary["errors"] = self._errors
            return summary

        # Load enabled models and build keyword index once per cycle
        brand_filter_str = getattr(settings, "X_MONITOR_CYCLE_BRAND_FILTER", None)
        brand_filter: list[str] | None = None
        if brand_filter_str and isinstance(brand_filter_str, str):
            brand_filter = [
                b.strip() for b in brand_filter_str.split(",") if b.strip()
            ]
        enabled_models = _resolve_enabled_models(self.cfg, brand_filter)
        index, search_terms = _build_brand_index(enabled_models)
        # Merge DB-loaded brand_search_terms into the index-derived map
        db_search_terms = _load_brand_search_terms()
        search_terms = {**search_terms, **db_search_terms}

        kept_all: list[dict[str, Any]] = []

        for call in calls:
            call_t0 = time.monotonic()
            call_entry: dict[str, Any] = {
                "call_id": call.call_id,
                "call_kind": call.call_kind,
                "brand_id": call.brand_id,
                "bucket": call.bucket,
                "query_length": call.query_length,
                "status": "error",
                "n_results": 0,
                "n_kept": 0,
                "n_inserted": 0,
            }

            # Resolve this call's time window from its cursor (or the
            # operator-supplied override) BEFORE fetching, so the value we
            # later store is exactly the upper bound we queried.
            call_now = datetime.now(timezone.utc)
            since_epoch, until_epoch, cursor_owned = self._resolve_window(
                call, now=call_now
            )
            call_entry["window_since"] = since_epoch
            call_entry["window_until"] = until_epoch

            # Fetch
            items, outcome = self._fetch_tweets(
                call, api, window=(since_epoch, until_epoch)
            )
            # Hard failures: no items to keep, hold cursor, move on.
            # "truncated" is NOT a hard failure -- items were retrieved and
            # must be persisted; only the cursor advance is withheld so the
            # remainder of the window is re-swept next cycle.
            if outcome in ("error", "length_cap_exceeded"):
                logger.warning(
                    "run: call_id=%s outcome=%s -- holding cursor, no persist",
                    call.call_id,
                    outcome,
                )
                call_entry["status"] = outcome
                call_entry["cursor_advanced"] = False
                summary["calls"].append(call_entry)
                summary["totals"]["n_calls_run"] += 1
                continue

            if not items:
                if outcome == "ok":
                    # Empty but successful sweep: advance (KTD5), else a quiet
                    # brand would re-request the same window forever.
                    if cursor_owned:
                        call_entry["cursor_advanced"] = _advance_cursor(
                            call,
                            upper_bound=datetime.fromtimestamp(
                                until_epoch, tz=timezone.utc
                            ),
                        )
                    call_entry["status"] = "no_results"
                else:
                    # truncated with zero items -- hold cursor (R2)
                    logger.warning(
                        "run: call_id=%s outcome=truncated with 0 items -- "
                        "holding cursor",
                        call.call_id,
                    )
                    call_entry["status"] = "truncated"
                    call_entry["cursor_advanced"] = False
                summary["calls"].append(call_entry)
                summary["totals"]["n_calls_run"] += 1
                continue

            call_entry["n_results"] = len(items)
            self._posts_seen += len(items)

            # Attribute
            classified = self._attribute_items(items, index, search_terms)

            # Drop unattributed items
            kept = [it for it in items if not it.get("_unattributed")]
            self._posts_attributed += len(kept)
            call_entry["n_kept"] = len(kept)

            # U5 runtime wire-in: post-fetch ban match against
            # call.not_include (R12). Stable hijacks like F1/Kimi for
            # moonshot_kimi are listed in config.yaml's x_query_specs[*]
            # .not_include. We match case-insensitively against the
            # tweet's text and quoted_text. Drop counters surface in
            # call_entry["not_include_drops"] for ops dashboards.
            ni_terms = [t.lower() for t in (call.not_include or []) if t]
            ni_drop_count = 0
            if ni_terms:
                pre_drop = len(kept)
                kept = [
                    it for it in kept
                    if not _matches_any_term(
                        it.get("text") or "", it.get("quoted_text") or "",
                        ni_terms,
                    )
                ]
                ni_drop_count = pre_drop - len(kept)
            call_entry["not_include_drops"] = ni_drop_count
            self._posts_attributed -= ni_drop_count  # adjust attributed count

            # U6 runtime wire-in: binary LLM relevancy gate (R19a +
            # x_monitor/relevancy.py). Fires only when:
            #   - call_id is C1/C2/C3, OR
            #   - per-item brand_id (set by _attribute_items) names a
            #     C-tier brand (mimo/moonshot_kimi/yi/llama/ernie/upstage
            #     /doubao/sensechat/kuaishou).
            # The gate's llm_call dependency is injected by the wire-in
            # (see CycleRunner.__init__ — defaults to None → KEEP).
            # llm_drops counter surfaces in call_entry.
            if self._relevancy_llm_call is not None:
                kept = _apply_relevancy_gate(
                    kept,
                    call_id=call.call_id,
                    llm_call=self._relevancy_llm_call,
                )
                llm_drop_count = (
                    call_entry.get("n_kept", 0)
                    - len(kept)
                    - ni_drop_count
                )
            else:
                llm_drop_count = 0
            call_entry["llm_drops"] = max(llm_drop_count, 0)
            # Re-derive n_kept after both gates
            call_entry["n_kept"] = len(kept)
            # Update U7 keep_rate with post-gate counts
            nr = call_entry.get("n_results", 0)
            call_entry["keep_rate"] = round(len(kept) / nr, 4) if nr > 0 else 0.0

            # Persist -- including on truncated outcomes. Dropping the page
            # was the C1 deadlock: every cycle re-fetched the same tip, never
            # stored it, never advanced.
            n_inserted, n_attributed, n_persist_failed = self._persist_items(kept)
            self._posts_inserted += n_inserted
            call_entry["n_inserted"] = n_inserted
            call_entry["n_persist_failed"] = n_persist_failed

            # Accumulate for post-fetch
            seen_ids: set[str] = {
                str(k.get("id") or k.get("tweet_id") or "")
                for k in kept_all
            }
            for k in kept:
                tid = str(k.get("id") or k.get("tweet_id") or "")
                if tid and tid not in seen_ids:
                    kept_all.append(k)
                    seen_ids.add(tid)

            if outcome == "truncated":
                call_entry["status"] = "truncated"
                call_entry["cursor_advanced"] = False
                logger.warning(
                    "run: holding cursor for call_id=%s -- window TRUNCATED "
                    "after n_results=%d n_kept=%d n_inserted=%d; re-sweep "
                    "next cycle (items were persisted)",
                    call.call_id,
                    len(items),
                    len(kept),
                    n_inserted,
                )
            elif n_persist_failed:
                call_entry["status"] = "persist_incomplete"
                call_entry["cursor_advanced"] = False
                logger.warning(
                    "run: holding cursor for call_id=%s -- %d of %d items "
                    "failed to persist; the window will be re-swept",
                    call.call_id,
                    n_persist_failed,
                    len(kept),
                )
            else:
                call_entry["status"] = "completed"
                # Advance only when fetch AND attribute AND persist all
                # succeeded AND the window was fully drained.
                if cursor_owned:
                    call_entry["cursor_advanced"] = _advance_cursor(
                        call,
                        upper_bound=datetime.fromtimestamp(
                            until_epoch, tz=timezone.utc
                        ),
                    )
            call_entry["wall_clock_sec"] = round(time.monotonic() - call_t0, 3)

            # U7 anomaly metrics (plan 2026-07-30-002 U7): per-call
            # fetch_n + keep_rate. not_include_drops and llm_drops are
            # placeholders that count toward 0 until the U5 ban path
            # and U6 LLM gate are wired into the runtime (follow-up
            # work; this unit pins the shape so future wire-ins
            # populate the same fields).
            call_entry["fetch_n"] = call_entry.get("n_results", 0)
            nr = call_entry["fetch_n"]
            nk = call_entry.get("n_kept", 0)
            call_entry["keep_rate"] = round(nk / nr, 4) if nr > 0 else 0.0
            call_entry["not_include_drops"] = 0  # wire-in placeholder
            call_entry["llm_drops"] = 0           # wire-in placeholder

            summary["calls"].append(call_entry)
            summary["totals"]["n_calls_run"] += 1

            # U7 cycle-level anomaly aggregates: min/mean keep_rate
            # across calls, plus max keep_rate (a spike here means a
            # single call is much looser than the rest — investigate).
            tr = summary["totals"]
            rates = [c.get("keep_rate", 0.0) for c in summary["calls"]]
            tr["keep_rate_min"] = round(min(rates), 4) if rates else 0.0
            tr["keep_rate_mean"] = round(sum(rates) / len(rates), 4) if rates else 0.0
            tr["keep_rate_max"] = round(max(rates), 4) if rates else 0.0

        # ---- Post-fetch: translate + classify ----
        if kept_all and summary["status"] != "aborted":
            pf_counters = self._run_post_fetch(kept_all)
            summary.setdefault("post_fetch", {}).update(pf_counters)
            # Plan 2026-08-01-002 U4: surface typed error counters so
            # the dashboard (or operator grep) can flag silent-failure
            # modes (translator_batch_failed > 0 for 3 cycles in a row
            # = lang_detected regression in production).
            summary.setdefault("n_errors_by_type", {}).update(
                dict(self._error_counts)
            )

        # ---- Quote-tweet channel (v1 parity; ~24% of v1 volume) ----
        # Runs after the main harvest so newly-attributed parents are in
        # the DB. Never aborts the cycle — QT failures are degraded stats.
        if summary["status"] != "aborted":
            try:
                from monitor.quote_tweets import run_quote_tweet_channel

                qt_out = run_quote_tweet_channel(
                    self,
                    api,
                    index=index,
                    brand_search_terms=search_terms,
                    enabled_models=enabled_models,
                )
                summary.setdefault("quote_tweets", {}).update(qt_out)
                # Count QT inserts toward cycle totals for dashboard parity
                n_qt = int(qt_out.get("official_n_ingested") or 0) + int(
                    qt_out.get("daily_n_ingested") or 0
                )
                if n_qt:
                    self._posts_inserted += n_qt
                    self._posts_attributed += n_qt
                    logger.info(
                        "CycleRunner.run: quote-tweet channel ingested %d "
                        "(official=%s daily=%s)",
                        n_qt,
                        qt_out.get("official_n_ingested"),
                        qt_out.get("daily_n_ingested"),
                    )
            except Exception as exc:
                logger.warning("quote-tweet channel failed: %s", exc)
                summary.setdefault("quote_tweets", {})["error"] = str(exc)

        # ---- Finalize ----
        summary["totals"]["n_results"] = self._posts_seen
        summary["totals"]["n_inserted"] = self._posts_inserted
        summary["totals"]["n_attributed"] = self._posts_attributed

        if summary["status"] == "running":
            summary["status"] = "completed" if not self._errors else "degraded"
        summary["finished_at"] = _now_iso()
        summary["wall_clock_sec"] = round(time.monotonic() - t0, 3)
        summary["errors"] = self._errors

        logger.info(
            "CycleRunner.run: %d calls, %d posts seen, %d inserted, "
            "%d attributed in %.2fs",
            summary["totals"]["n_calls_run"],
            summary["totals"]["n_results"],
            summary["totals"]["n_inserted"],
            summary["totals"]["n_attributed"],
            summary["wall_clock_sec"],
        )
        return summary
