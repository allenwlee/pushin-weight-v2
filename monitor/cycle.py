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
  8. Emit run summary in LATEST.json compatible shape

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
from datetime import datetime, timezone
from typing import Any

from django.conf import settings
from django.db import transaction

from core.models import (
    Account,
    Brand,
    BrandKeyword,
    BrandSearchTerm,
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


def _load_enabled_models(brand_filter: list[str] | None = None) -> list[str]:
    """Load the enabled model list from settings or DB.

    Uses the brand_filter (from --brands CLI flag) if provided; otherwise
    reads from settings.KNOWN_MODELS. Filters to brands that exist in the
    brands table.
    """
    if brand_filter:
        # Validate that the requested brands exist
        existing = set(
            Brand.objects.filter(nickname__in=brand_filter).values_list(
                "nickname", flat=True
            )
        )
        return [b for b in brand_filter if b in existing]
    # Fall back to settings.KNOWN_MODELS (the canonical list).
    # TODO(U2): derive from Brand.objects.values_list('nickname', flat=True)
    known = getattr(settings, "KNOWN_MODELS", None)
    if known:
        return sorted(known)
    # Last resort: read from DB
    return sorted(
        Brand.objects.filter(is_sentinel=False).values_list("nickname", flat=True)
    )


def _load_x_monitor_list_id() -> int | None:
    """Load the X list ID from settings or environment."""
    list_id = getattr(settings, "X_MONITOR_LIST_ID", None)
    if list_id is not None:
        return int(list_id)
    import os
    env_val = os.environ.get("X_MONITOR_LIST_ID")
    if env_val:
        return int(env_val)
    return None


def _load_x_query_specs() -> list[XQuerySpec] | None:
    """Load x_query_specs from settings.

    Returns None when not configured (caller will use empty list).
    If settings.X_MONITOR_X_QUERY_SPECS is a list of dicts, converts
    them to XQuerySpec instances.
    """
    raw = getattr(settings, "X_MONITOR_X_QUERY_SPECS", None)
    if raw is None:
        return None
    if isinstance(raw, list):
        specs: list[XQuerySpec] = []
        for item in raw:
            if isinstance(item, XQuerySpec):
                specs.append(item)
            elif isinstance(item, dict):
                # Filter to only fields the dataclass accepts
                import dataclasses as _dc
                valid_fields = {f.name for f in _dc.fields(XQuerySpec)}
                filtered = {k: v for k, v in item.items() if k in valid_fields}
                specs.append(XQuerySpec(**filtered))
        return specs if specs else None
    return None


# ============================================================================
# ORM persistence helpers
# ============================================================================


def _upsert_account(raw: dict[str, Any]) -> Account | None:
    """Create or update an Account row from a normalized tweet dict.

    Returns the Account instance or None if the tweet has no author info.
    """
    author_id = str(raw.get("author_id") or raw.get("authorId") or "")
    if not author_id:
        return None
    defaults: dict[str, Any] = {}
    handle = raw.get("author_handle") or raw.get("authorHandle") or ""
    if handle:
        defaults["handle"] = handle
    display_name = raw.get("author_display_name") or raw.get("authorName") or ""
    if display_name:
        defaults["display_name"] = display_name
    verified = raw.get("author_verified") or raw.get("authorVerified") or False
    defaults["verified"] = bool(verified)
    followers = raw.get("author_followers") or raw.get("authorFollowers")
    if followers is not None:
        defaults["followers_count"] = int(followers)
    following = raw.get("author_following") or raw.get("authorFollowing")
    if following is not None:
        defaults["following_count"] = int(following)
    acc, _created = Account.objects.update_or_create(
        author_id=author_id, defaults=defaults
    )
    return acc


def _make_json_safe(obj: Any) -> Any:
    """Recursively convert dataclass/NamedTuple instances to plain dicts for JSON."""
    from dataclasses import asdict, is_dataclass

    if isinstance(obj, dict):
        return {k: _make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_make_json_safe(v) for v in obj]
    if is_dataclass(obj):
        return _make_json_safe(asdict(obj))
    if hasattr(obj, "_asdict"):  # NamedTuple
        return _make_json_safe(obj._asdict())
    return obj


def _upsert_post(raw: dict[str, Any], account: Account | None = None) -> Post | None:
    """Create or update a Post row from a normalized tweet dict.

    Returns the Post instance or None if the tweet has no id.
    The raw dict is stored in the `raw` JSONField for full-fidelity replay.
    """
    tweet_id = str(raw.get("id") or raw.get("tweet_id") or "")
    if not tweet_id:
        return None
    defaults: dict[str, Any] = {"raw": _make_json_safe(raw)}
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
        defaults["quoted_status_id"] = str(quoted_id)
    conversation_id = raw.get("conversation_id") or raw.get("conversationId") or ""
    if conversation_id:
        defaults["conversation_id"] = str(conversation_id)
    entities = raw.get("entities") or {}
    if entities:
        defaults["entities"] = entities
    source_qid = raw.get("source_query_id") or raw.get("sourceQueryId") or ""
    if source_qid:
        defaults["source_query_id"] = source_qid
    created_at_epoch = raw.get("created_at_epoch") or raw.get("createdAtEpoch")
    if created_at_epoch is not None:
        defaults["created_at_epoch"] = int(created_at_epoch)
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


def plan_calls_for_cycle() -> list[PlannedCall]:
    """Plan harvest calls from settings — shared by CycleRunner and backfill.

    Reads X_MONITOR_LIST_ID, brand filter, primary keywords, and
    x_query_specs from Django settings. Returns empty list when the
    list ID is not configured.
    """
    list_id = _load_x_monitor_list_id()
    if list_id is None:
        logger.warning(
            "plan_calls_for_cycle: X_MONITOR_LIST_ID not set — "
            "Call A is list-based; without it no calls are planned."
        )
        return []

    primary_keywords = _load_primary_keywords()
    x_query_specs = _load_x_query_specs() or []

    brand_filter_raw = getattr(settings, "X_MONITOR_CYCLE_BRAND_FILTER", None)
    if brand_filter_raw and isinstance(brand_filter_raw, str):
        brand_filter = [b.strip() for b in brand_filter_raw.split(",") if b.strip()]
        if brand_filter:
            primary_keywords = {
                k: v for k, v in primary_keywords.items() if k in brand_filter
            }
            logger.info("plan_calls_for_cycle: brand filter active — %s", brand_filter)

    limit_per_call = getattr(settings, "X_MONITOR_CYCLE_LIMIT_PER_CALL", 50)

    return plan_calls(
        list_id,
        x_query_specs,
        primary_keywords=primary_keywords,
        limit_per_call=limit_per_call,
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
        dry_run: bool = False,
        cycle_kind: str = "manual",
        _backfill_call_ids: list[str] | None = None,
        _max_llm_calls: int | None = None,
    ) -> None:
        self.dry_run = dry_run
        self.cycle_kind = cycle_kind  # 'scheduled' or 'manual'
        # If set, only execute these call IDs (all must be in the plan).
        # Used by the backfill command for batched, resumable execution.
        self._backfill_call_ids = _backfill_call_ids
        # Hard cap on LLM batches per invocation.  None = no cap.
        # Used by the backfill command to limit API spend on large windows.
        self._max_llm_calls = _max_llm_calls
        self._llm_call_count: int = 0
        # Per-cycle accumulators for the run summary
        self._posts_seen: int = 0
        self._posts_inserted: int = 0
        self._posts_attributed: int = 0
        self._api_calls: int = 0
        self._errors: list[str] = []

    # ------------------------------------------------------------------
    # Step 1: Plan
    # ------------------------------------------------------------------

    def _plan_calls(self) -> list[PlannedCall]:
        """Build the per-cycle call list via plan_calls_for_cycle()."""
        try:
            calls = plan_calls_for_cycle()
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

    def _fetch_tweets(
        self, call: PlannedCall, api: TwitterApiClient
    ) -> list[dict[str, Any]]:
        """Fetch tweets for one PlannedCall via TwitterAPI.io.

        Returns the normalized tweet list. Per-call errors (rate limit,
        server error) are caught — one bad query doesn't kill the cycle.
        """
        limit_per_call = getattr(settings, "X_MONITOR_CYCLE_LIMIT_PER_CALL", None)
        max_pages = getattr(settings, "X_MONITOR_CYCLE_MAX_PAGES_PER_CALL", None)
        since_time = getattr(settings, "X_MONITOR_CYCLE_SINCE_TIME", None)
        until_time = getattr(settings, "X_MONITOR_CYCLE_UNTIL_TIME", None)
        max_results_cap = int(limit_per_call) if limit_per_call is not None else 50
        max_pages_cap = int(max_pages) if max_pages is not None else 5

        try:
            items = api.run_search(
                call.query_string,
                max_results=max_results_cap,
                max_pages=max_pages_cap,
                max_per_page=20,
                since_time=int(since_time) if since_time else None,
                until_time=int(until_time) if until_time else None,
            )
        except TwitterApiAuthError as exc:
            logger.error("_fetch_tweets: auth failure on %s: %s", call.call_id, exc)
            self._errors.append(f"fetch.{call.call_id}: auth: {exc}")
            return []
        except (TwitterApiRateLimitError, TwitterApiServerError) as exc:
            logger.warning(
                "_fetch_tweets: rate/server error on %s: %s", call.call_id, exc
            )
            self._errors.append(f"fetch.{call.call_id}: {exc}")
            return []
        except Exception as exc:
            logger.warning("_fetch_tweets: error on %s: %s", call.call_id, exc)
            self._errors.append(f"fetch.{call.call_id}: {exc}")
            return []

        self._api_calls += 1
        return items

    # ------------------------------------------------------------------
    # Step 3: Attribute
    # ------------------------------------------------------------------

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
    ) -> tuple[int, int]:
        """Persist attributed items via Django ORM.

        For each item: upsert Account → upsert Post → persist attribution
        (PostBrand + PostBrandMention + PostBrandSignal).

        Returns (n_inserted, n_attributed).
        """
        n_inserted = 0
        n_attributed = 0
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
                tid = str(it.get("id") or it.get("tweet_id") or "?")
                logger.warning("_persist_items: failed for tweet_id=%s: %s", tid, exc)
                self._errors.append(f"persist.{tid}: {exc}")
        return n_inserted, n_attributed

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

        # Build Anthropic client from env
        from x_monitor.reattribute import build_anthropic_client_from_env

        client = build_anthropic_client_from_env()
        if client is None:
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

        brand_registry = list(BrandModel.objects.filter(is_sentinel=False))

        # ---- Stage 1: translate ----
        from x_monitor.translator import translate_batch_pragmatics

        try:
            translation_rows = translate_batch_pragmatics(
                tweets, ["en", "zh_cn"], client
            )
        except Exception as exc:
            logger.warning("_run_post_fetch: translate failed: %s", exc)
            translation_rows = []

        # Persist translations back to Post rows
        if translation_rows:
            from core.models import Post as PostModel

            for r in translation_rows:
                tid = r.get("tweet_id")
                if not tid:
                    continue
                PostModel.objects.filter(tweet_id=tid).update(
                    text_en=r.get("text_en") or None,
                    text_zh_cn=r.get("text_zh_cn")
                    or r.get("literal_zh")
                    or None,
                    lang_detected=r.get("lang_detected") or None,
                )
            counters["n_translated"] = len(translation_rows)
            counters["n_failed_translate"] = sum(
                1 for r in translation_rows if r.get("translation_failed")
            )

        # ---- Stage 2: classify ----
        from x_monitor.attribution import classify_batch_pragmatics_full

        pause_sec = getattr(settings, "X_MONITOR_LLM_PAUSE_SECONDS", 1)

        try:
            results = classify_batch_pragmatics_full(
                tweets, brand_registry, client
            )
        except Exception as exc:
            logger.warning("_run_post_fetch: classify failed: %s", exc)
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
                    PBSignal.objects.update_or_create(
                        post_id=tid,
                        brand_id=brand_id,
                        post_type_id=post_type,
                        defaults={"sentiment_id": sentiment or ""},
                    )
                    counters["n_discourse"] += 1

                discourse_keys = cls.get("discourse_role") or []
                cn_nat = cls.get("china_nationalism")
                us_nat = cls.get("us_nationalism")

                if discourse_keys:
                    for act_idx, dk in enumerate(discourse_keys):
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
        enabled_models = _load_enabled_models(brand_filter)
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

            # Fetch
            items = self._fetch_tweets(call, api)
            if not items:
                call_entry["status"] = "no_results"
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

            # Persist
            n_inserted, n_attributed = self._persist_items(kept)
            self._posts_inserted += n_inserted
            call_entry["n_inserted"] = n_inserted

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

            call_entry["status"] = "completed"
            call_entry["wall_clock_sec"] = round(time.monotonic() - call_t0, 3)
            summary["calls"].append(call_entry)
            summary["totals"]["n_calls_run"] += 1

        # ---- Post-fetch: translate + classify ----
        if kept_all and summary["status"] != "aborted":
            pf_counters = self._run_post_fetch(kept_all)
            summary.setdefault("post_fetch", {}).update(pf_counters)

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
