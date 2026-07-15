# {{AGENT_ATTRIBUTION}}
"""Run pipeline: harvest, persist, dedupe, sentinel, lock (R16, R17, R19, R20, R22, R25)."""

from __future__ import annotations

import contextlib
import fcntl
import json
import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Plan 2026-07-11-002 (U4): Account / derive_edges / find_clusters /
# role_tag moved from x_monitor.accounts (deleted) to
# x_monitor.account_graph.
from .account_graph import Account, derive_edges, find_clusters, role_tag
from .apify import (
    TwitterApiAuthError,
    TwitterApiClient,
    TwitterApiRateLimitError,
    TwitterApiServerError,
)
from .config import KNOWN_MODELS, Config
from .queries import (
    Query,
    assert_under_operator_cap,
    count_x_operators,
    estimated_cost,
    load_queries,
)
from .query_plan import plan_calls
# v1.8 (R15, R20): the per-tweet classification seam uses the
# multi-brand `attribute_to_brands` + `classify_post` from
# `x_monitor.attribution`. U9 (migration 022) drops the legacy
# `classify_signal` 6-bucket single-string classifier — the pipeline
# now stamps (post_type, sentiment) tuples per brand instead.
from .attribution import (
    UNATTRIBUTED_BRAND_ID,
    MentionRow,
    attribute_to_brands,
    classify_post,
    compile_keyword_index,
    _max_tokens_for_batch,
)
from .relevance import filter_posts  # noqa: F401 — re-exported for tests
from .review import ReviewQueue
from .store import Store
from .headlines import HeadlinesCache, enrich_posts

log = logging.getLogger(__name__)

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# U2: hours subtracted from `last_completed_at` before emitting
# TwitterAPI.io's `since:` operator. The 1-hour overlap absorbs near-
# boundary posts (a post whose created_at is a few seconds AFTER the
# previous cursor but appears in the API's index a few seconds before
# the new cursor would naturally include it). 1 hour is enough for
# typical ingestion latency without re-fetching a full prior day.
CURSOR_OVERLAP_HOURS: int = 1


def _iso_to_epoch(value: str | None) -> int | None:
    """Parse an ISO-8601 timestamp to unix seconds, or None.

    Used to turn a post's `last_quote_fetched_at` (ISO) into the unix
    `sinceTime` for the next /twitter/tweet/quotes call.
    """
    if not value:
        return None
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def filter_and_review(
    items: list[dict[str, Any]],
    q: Query,
    brand_id: str,
    review: ReviewQueue,
    cache: HeadlinesCache | None = None,
    api: TwitterApiClient | None = None,
    run_fetches_used: list[int] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Per-model post-fetch pipeline: review-queue + headline enrichment.

    Plan 2026-07-11-001 (KTD6): the relevance-filter step (which read
    `data/filters/<brand>.yaml` via `filter_posts`) is removed. What
    remains:
      - The banned-token review-queue path: the in-code banned list
        still produces `soft` items; they go to the operator review
        queue via `review.append_rule_match`.
      - The headline-enrichment pass (URL-only posts get their
        article headlines via `enrich_posts`).
      - The low-engagement-filter step is a downstream concern
        (per-tweet `like_count` filtering in the dashboard / kept-set
        inspection); it is in-code, not yaml-driven.

    Returns (kept, drop_stats). The drop_stats shape is preserved for
    backward-compat with the per-query summary keys (`n_dropped`,
    `n_kept`, `n_soft_dropped`, `reasons`).

    U9 (migration 022): the `expected_signal == "release"` low-engagement
    review rule was REMOVED with the 6-signal taxonomy. The rule fired
    on Q1/release posts with like_count < 2; with `expected_signal`
    gone, the rule cannot apply uniformly. Per-Q1 low-engagement
    enforcement is a follow-up if needed (operators can still inspect
    the kept set with like_count=0/1 via the dashboard).
    """
    # The relevance-filter step (filter_posts with cfg from yaml) is
    # gone — KTD6. We do not synthesize a fake cfg here; the per-model
    # yaml read path is permanently retired. Items pass through with
    # the in-code banned-token + low-engagement rules only.
    kept: list[dict[str, Any]] = list(items)
    stats: dict[str, Any] = {
        "n_kept": len(kept),
        "n_dropped": 0,
        "n_soft_dropped": 0,
        "reasons": {},
    }
    # v1.4: enrich the kept set with article headlines (X-articles go
    # through api.get_article when both api and the URL match).
    if cache is not None:
        kept, headline_stats = enrich_posts(
            kept, cache, api=api, run_fetches_used=run_fetches_used,
        )
        # Merge headline stats into the filter drop_stats so they show
        # up in the per-query summary. Filter keys win on collision.
        for k, v in headline_stats.items():
            stats.setdefault(k, v)
    return kept, stats

class PipelineLockBusy(Exception):
    """Raised when another run is already in-flight."""

@contextlib.contextmanager
def pipeline_lock(lock_path: Path, *, blocking: bool = False):
    """Acquire fcntl.flock on the given path. Non-blocking by default.

    On contention (non-blocking), yields False and exits cleanly so the
    caller can write degraded:already_running to its run JSON and exit 0.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = open(lock_path, "w")
    try:
        try:
            fcntl.flock(
                fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
            )
            acquired = True
        except BlockingIOError:
            acquired = False
        yield acquired
    finally:
        if acquired:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except Exception:
                pass
        fd.close()

def _signal_to_qid(signal: str) -> str:
    """U9 (migration 022): the Q1-Q6 source_query_id mapping is GONE.

    This stub is kept only as a defensive default for the rare code
    path that still imports it; it now returns "Q5" (the generic
    "other" QID) for any input. New code must not call this.
    """
    return "Q5"


# Centralized min_faves floor for Call A (the curated-handles list call).
# Imported from query_plan (not declared here) to avoid the circular
# import — query_plan is imported by run.py, not the other way around.
# Was 1 historically (the "release-like" preset) — lowered to 0 so the
# list call surfaces every post from the curated handles, not just
# ones that already have traction. brand_wide calls (B1/B2/B3/C1/C2)
# have always been 0; this constant only governs the `account` path.
# Pinned by tests/test_min_faves_list_call.py.
from .query_plan import MIN_FAVES_FOR_LIST_CALL  # noqa: E402


def _planned_call_to_query(call: "PlannedCall") -> Query:
    """Synthesize a Query object for the v1.2 filter_and_review helper.

    U9 (migration 022): the Query model no longer carries
    `expected_signal` (the 6-signal taxonomy was killed). The filter
    only reads .id, .min_faves, .query_string. Account calls use
    MIN_FAVES_FOR_LIST_CALL (currently 0); brand_wide calls use 0.
    """
    from .query_plan import PlannedCall  # local to avoid circular at import
    if call.call_kind == "account":
        qid, min_faves = "Q1", MIN_FAVES_FOR_LIST_CALL
    else:
        qid, min_faves = "Q5", 0
    return Query(
        id=qid,  # type: ignore[arg-type]
        query_string=call.query_string,
        max_results=50,
        enabled=True,
        min_faves=min_faves,
    )

# Plan 2026-07-11-001 (U3): _brand_tokens_map and the per-brand yaml
# read path are retired. The keyword index is now self-brand-only —
# see _build_brand_index below. The "per-model brand token map"
# previously computed from data/queries/<m>.yaml is now sourced from
# the brand_keywords table (DB) when downstream consumers need it.
# (Kept as a marker; see also `_log_brand_search_terms_drift` removal.)

def _staff_handles_map(store, enabled_models: list[str]) -> dict[str, list[str]]:
    """Build {brand_id: [handle, ...]} for staff/official attribution.

    Plan 2026-07-11-002 (U4): the data/accounts/*.yaml file read is
    retired. The DB's `brands_accounts WHERE role_id IN (2, 3)` is
    canonical; we read once via
    `Store.read_brand_official_staff_handles` and return only the
    handle list (the role_key discriminator is unused at this call
    site — v1.6 attribute_to_brand folds official + staff into a
    single per-brand list).
    """
    out: dict[str, list[str]] = {}
    seeded = store.read_brand_official_staff_handles(enabled_models)
    for m in enabled_models:
        pairs = seeded.get(m, [])
        out[m] = [handle for handle, _role in pairs]
    return out

# v1.7: brand-alias map for tokens v1.7 yamls use that don't match the
# canonical brand_id (e.g. "kimi" -> "moonshot_kimi"). Hoisted out of the
# (dead in v1.7) intent branch so the unified attribution path can use it.
_BRAND_ALIASES: dict[str, str] = {
    "kimi": "moonshot_kimi",
    # bare "moonshot" REMOVED: it matches the Moonshot crypto exchange
    # (spam: "$X on the Moonshot Top 100 Leaderboard"), not Moonshot AI.
    # Legit posts match via "kimi", "k2", or the CJK name below.
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


def _build_brand_index(
    models: list[str],
) -> tuple[Any, dict[str, str]]:
    """Build the per-cycle brand keyword index + search-term map.

    Plan 2026-07-11-001: the v1.7-era yaml token map input is gone
    (data/queries/ is deleted). The keyword index is now self-brand-
    only — each enabled model name matches itself in post text.
    Brand-specific multi-token lists live in `brand_keywords` (DB)
    and are loaded via `Store.read_brand_keywords()` when downstream
    consumers need them; this index is the body_keyword attribution
    fallback.

    Returns (compiled_keyword_index, brand_search_terms) — the index
    is used by `_attribute_call_items` for body_keyword attribution;
    `brand_search_terms` is the per-cycle DB-load shape for callers
    that still expect a yaml-shape map.
    """
    keyword_triples: list[tuple[str, str, bool]] = [
        (m, m, False) for m in models if m in KNOWN_MODELS
    ]
    index = compile_keyword_index(keyword_triples)
    brand_search_terms: dict[str, str] = {
        tok.lower(): bid for bid, tok, _ in keyword_triples
    }
    return index, brand_search_terms


def _load_brand_search_terms_from_db(store: Any) -> dict[str, str]:
    """Return the {term: brand_id} map from the `brand_search_terms` table.

    This is the post-fetch attribution source of truth (per the
    hybrid-by-design contract documented in migration 017). The yaml
    files in data/queries/ are *not* read at attribution time — the DB
    table is. The yaml is the source for the query string built by
    query_plan.plan_calls() at cycle time.
    """
    return store.read_brand_search_terms()


# Plan 2026-07-11-001 (U3): _log_brand_search_terms_drift is removed
# along with the per-brand yaml read path. Its job was to compare
# the yaml-derived {term: brand_id} map against the DB-loaded map;
# with yamls gone, there is nothing to compare. The DB is now the
# single source of truth for brand_search_terms.


def _attribute_call_items(
    items: list[dict[str, Any]],
    index: Any,
    brand_search_terms: dict[str, str],
    brand_registry: dict[str, Any] | None = None,
    anthropic_client: Any = None,
) -> int:
    """Stamp brand_id/brand_ids/mentions/classifications on each item via
    attribute_to_brands + classify_post.

    U9 (migration 022): replaces the legacy single-string
    `_legacy_classify_signal` with the new (post_type, sentiment)
    classifier. Each item gets:
      - it["brand_id"]      (legacy compat: first match)
      - it["brand_ids"]     (list of all detected brands)
      - it["mentions"]      (list of MentionRow instances)
      - it["classifications"] (dict[brand_id, (post_type, sentiment)])

    user_mention / hashtag stay offline (detection tables not populated);
    attribution is body_keyword + search_term only. Items that match no
    brand are marked _unattributed (classifications={}). Returns the
    count of items that matched at least one brand.

    When `brand_registry` + `anthropic_client` are provided, classify_post
    makes an LLM call to derive (post_type, sentiment). When omitted,
    no classifications are written (the legacy single-string signal
    fallback is gone; the pipeline can run offline-only and skip the
    posts_brands_signals writes).
    """
    from datetime import datetime as _dt, timezone as _tz
    classified = 0
    for it in items:
        _fallback_created_at = _dt.now(_tz.utc).isoformat(timespec="seconds")
        # Fold the quoted tweet's text into the body that attribute_to_brands
        # matches (it reads post["text"], attribution.py). A quote-repost of a
        # brand tweet should attribute even when the reposter's commentary lacks
        # the keyword. Stored posts.text stays commentary-only (store.insert).
        _body = it.get("text", "") or ""
        _quoted = it.get("quoted_text") or ""
        post_like = {
            "tweet_id": it.get("id", ""),
            "id": it.get("id", ""),
            "text": (_body + "\n" + _quoted) if _quoted else _body,
            "created_at": it.get("created_at") or _fallback_created_at,
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
            # U9: per-brand (post_type, sentiment) classification via
            # `classify_post`. When brand_registry + anthropic_client are
            # both provided this hits Claude Haiku; when either is
            # missing, classify_post returns {} and the kept item still
            # gets stored (post_type + sentiment are filled in later by
            # the reattribute pipeline if needed).
            classifications: dict[str, tuple[str, str]] = {}
            if brand_registry is not None:
                classifications = classify_post(
                    text=it.get("text") or "",
                    brand_ids=brand_ids,
                    brand_registry=brand_registry,
                    anthropic_client=anthropic_client,
                )
            it["classifications"] = classifications
            classified += 1
    return classified


def _ingest_quote_tweets(
    qt_items: list[dict[str, Any]],
    parent_tweet_id: str,
    parent_text: str,
    *,
    index: Any,
    brand_search_terms: dict[str, str],
    store: Store,
) -> int:
    """Ingest captured quote-tweets through the SAME attribution +
    classification path as original posts.

    For each QT: if it carries no `quoted_text` AND its `quoted_status_id`
    equals the parent, attach the parent's text (the D5 invariant — only
    when the QT actually quotes this parent; a QT nesting a different quote
    is classified on commentary alone). Then `_attribute_call_items` folds
    commentary + quoted_text for `attribute_to_brands` and classifies the
    signal on the commentary only. Multi-brand QTs inherit 1/N-weighted
    `posts_brands`/`posts_brands_signals` via `store.insert_posts`. Idempotent:
    re-ingesting a QT (same tweet_id) is a no-op (INSERT OR IGNORE + ON
    CONFLICT). Returns the number of QTs newly inserted.
    """
    parent_id_str = str(parent_tweet_id or "")
    for qt in qt_items:
        if not qt.get("quoted_text") and str(
            qt.get("quoted_status_id") or ""
        ) == parent_id_str:
            qt["quoted_text"] = parent_text
    _attribute_call_items(
        qt_items, index, brand_search_terms,
        brand_registry=None, anthropic_client=None,
    )
    kept = [it for it in qt_items if not it.get("_unattributed")]
    if not kept:
        return 0
    return store.insert_posts(kept)


# v12 (plan 2026-07-06-001 U2): demote post_type='hands_on_usage' to a more
# specific value when the source text contains a strong marker for
# performance_comparisons or event_announcement. The classifier prompt
# rules 13/14/15 try to steer the LLM away from hands_on_usage, but
# _parse_pragmatics_full_response coerces unknown post_types to
# hands_on_usage as a fallback. This helper is the parser-side counter-
# measure: detect the markers in the raw text and override the type.
_PERF_COMPARE_MARKERS = (
    "benchmark", "eval", "ttft", "latency", "ranking",
    " vs ", "side-by-side", "climbed n spots", "dropped n spots",
    "nth place",
)
_EVENT_ANNOUNCEMENT_MARKERS = (
    "is generally available", "launched today", "shipped",
    "now in beta", "now live", "released",
)


def _post_process_pragmatics(
    by_brand: dict[str, dict[str, str]],
    text: str,
) -> dict[str, dict[str, str]]:
    """Demote post_type='hands_on_usage' to a more specific type when the
    raw source text carries a strong marker. Pure function — returns a new
    by_brand dict, never mutates the caller's.

    Performance comparisons win over event announcements when both
    markers fire (the plan's Edge case C establishes this order).
    """
    if not by_brand:
        return by_brand
    if not text:
        return by_brand
    haystack = text.lower()
    # Compute each marker family exactly once per post.
    perf = any(m in haystack for m in _PERF_COMPARE_MARKERS)
    event = (
        len(text) < 280
        and any(m in haystack for m in _EVENT_ANNOUNCEMENT_MARKERS)
    )
    if not (perf or event):
        return by_brand
    demoted_to = "performance_comparisons" if perf else "event_announcement"
    out: dict[str, dict[str, str]] = {}
    for brand_id, prongs in by_brand.items():
        if prongs.get("post_type") == "hands_on_usage":
            new_prongs = dict(prongs)
            new_prongs["post_type"] = demoted_to
            out[brand_id] = new_prongs
        else:
            out[brand_id] = prongs
    return out


def _run_post_fetch(
    kept_posts: list[dict[str, Any]],
    *,
    store: Store,
    anthropic_client: Any,
    brand_registry_rows: list[Any],
    brand_tokens: dict[str, list[str]] | None = None,
) -> dict[str, int]:
    """U5: stream-aligned post-fetch transformer runner.

    Plan: docs/plans/2026-07-02-002-feat-streamlined-post-fetch-pipeline-plan.md
    (Unit 5 of 8). Runs the three U3 + U4 transformers over the
    cycle's KEPT post set, AFTER `store.insert_posts` has written
    the raw posts:

      1. `translate_batch_pragmatics` (U3) writes text_en / text_zh_cn
         / lang_detected to `posts` and emits the four-pronged row
         (literal_zh + cn_equivalent + annotation). Pragmatic register
         (discourse_role) was REMOVED from the translator in plan
         2026-07-06-001 — it's the classifier's exclusive output.
      2. `classify_pragmatics_full` (U4) writes the per-brand
         (post_type + sentiment) pair to `posts_brands_signals` AND
         the (discourse_role + china_nationalism + us_nationalism)
         triple to `posts_brands_discourse`.

    Fail-soft per stage: an LLM failure on one post never aborts the
    cycle. Counters surface in the run summary so the smoketest
    runner (U7) can assert the cycle hit its per-stage count targets.

    Args:
        kept_posts: the per-cycle kept posts. Each dict must have
            `tweet_id` (or `id`) and `text`. The per-brand
            classifications live on `classifications` (set by
            `_attribute_call_items` via classify_post) — U4's merged
            call REPLACES those with the five-prong result.
        store: open Store (caller's transaction).
        anthropic_client: a ClaudeClient-protocol object. When None,
            skip both stages (used by --dry-run and offline tests).
        brand_registry_rows: list of BrandRow from store.read_brands().
        brand_tokens: optional {brand_id: [brand_names...]} for the
            translator's brand-preservation prompt block.

    Returns:
        Counter dict with keys:
          n_translated       — kept posts with text_en + text_zh_cn
          n_discourse        — kept posts with at least one
                               posts_brands_discourse row written
          n_nationalism      — kept posts with both nationalism FKs
                               populated
          n_failed_translate — kept posts whose LLM call failed
    """
    counters = {
        "n_translated": 0,
        "n_discourse": 0,
        "n_nationalism": 0,
        "n_failed_translate": 0,
    }
    if not kept_posts or anthropic_client is None:
        return counters

    # Lazy imports to avoid pulling translator / classification
    # modules when the caller is offline (the no-`anthropic_client`
    # path is the offline-test path).
    from .translator import translate_batch_pragmatics
    from .attribution import (
        classify_pragmatics_full,
        classify_batch_pragmatics_full,
    )

    # --- Stage 1: translate_batch_pragmatics (U3) ------------------------
    # Build the per-post translation batch (one call per 20-post batch).
    # Build the brand_names list across the kept set so the prompt
    # block covers every brand we may reference.
    brand_names: list[str] = []
    seen_names: set[str] = set()
    if brand_tokens:
        for names in brand_tokens.values():
            for n in names:
                if n not in seen_names:
                    brand_names.append(n)
                    seen_names.add(n)
    t0 = time.monotonic()
    try:
        translation_rows = translate_batch_pragmatics(
            kept_posts,
            ["en", "zh_cn"],
            anthropic_client,
            brand_names=brand_names or None,
        )
    except Exception as e:
        log.warning("_run_post_fetch: translate_batch_pragmatics failed: %s", e)
        translation_rows = []
    t_translate = time.monotonic() - t0
    log.info(
        "_run_post_fetch: translate_batch_pragmatics %d rows in %.2fs",
        len(translation_rows), t_translate,
    )

    # Persist translations to `posts` via Store.bulk_update_translations.
    # This is the v1.7 Store method — it reads only text_en / text_zh_cn
    # / lang_detected (backward-compat with U3's row shape).
    bulk_translation_rows = [
        {
            "tweet_id": r["tweet_id"],
            "text_en": r.get("text_en"),
            "text_zh_cn": r.get("text_zh_cn") or r.get("literal_zh"),
            "lang_detected": r.get("lang_detected"),
        }
        for r in translation_rows
    ]
    n_updated = store.bulk_update_translations(bulk_translation_rows)
    counters["n_translated"] = n_updated
    counters["n_failed_translate"] = sum(
        1 for r in translation_rows if r.get("translation_failed")
    )

    # --- Stage 2: classify_pragmatics_full (U4, batched) -----------------
    # Plan 2026-07-13-001 (timeout investigation): the prior per-post
    # serial LLM call (one Haiku call per kept post) cost ~1.5 s × N
    # posts and dominated wall time at N=20. `classify_batch_pragmatics_full`
    # batches 20 posts per LLM call using `_PRAGMATICS_FULL_SYSTEM_PROMPT`
    # as the shared prefix — Anthropic's prompt-cache amortizes the
    # ~11 KB of rules + examples across the batch, and across cycles.
    # Result shape is index-aligned with `kept_posts` so the loop below
    # can range-index without re-keying.
    #
    # NOTE: pass per-batch max_tokens via _max_tokens_for_batch (computed
    # from len(batch_inputs)). The helper uses 200 tokens/tweet linear
    # estimate, clamped to [4096, 8192], grounded in the DS V4 probe at
    # data/runs/dsv4-probe-20260715T071331Z.json. Pre-swap, M3.0 via proxy
    # needed 4096 headroom for the ~3000-token structured JSON response of
    # a 20-post batch (the 1M context window is input-side only). See
    # docs/debug/2026-07-15-max-tokens-not-threaded-into-classify-batch.md
    # for the original truncation analysis.
    t0 = time.monotonic()
    discourse_rows: list[dict[str, Any]] = []
    signal_rows: list[dict[str, Any]] = []
    unsanctioned_by_post: dict[str, list[str]] = {}
    n_nationalism = 0

    # Build the per-post payload list. Posts with no brand_ids are
    # skipped here (the classifier's purpose is per-brand) and
    # surfaced in the result list as empty-shape entries.
    batch_inputs: list[dict[str, Any]] = [
        {
            "tweet_id": str(it.get("id") or it.get("tweet_id") or ""),
            "text": it.get("text") or "",
            "brand_ids": list(it.get("brand_ids") or []),
        }
        for it in kept_posts
    ]
    try:
        classification_results = classify_batch_pragmatics_full(
            batch_inputs,
            brand_registry_rows,
            anthropic_client,
            max_tokens=_max_tokens_for_batch(len(batch_inputs)),
        )
    except Exception as e:
        log.warning(
            "_run_post_fetch: classify_batch_pragmatics_full failed: %s", e,
        )
        classification_results = [
            {"by_brand": {}, "unsanctioned_flags": []}
            for _ in kept_posts
        ]

    # Pair `kept_posts` with `classification_results` (index-aligned) and
    # emit the same `(signal_rows, discourse_rows, unsanctioned_by_post,
    # n_nationalism)` rows the prior per-post loop produced. The downstream
    # write paths (`insert_posts_brands_signals`,
    # `bulk_insert_post_brand_discourse`) are unchanged.
    for it, classified in zip(kept_posts, classification_results):
        tid = str(it.get("id") or it.get("tweet_id"))
        # U2a: pull the per-brand dict out of the new return shape.
        by_brand = classified.get("by_brand", {}) if isinstance(
            classified, dict) else {}
        # v12 (plan 2026-07-06-001 U2): parser-layer demotion. When the
        # LLM-defaulted post_type='hands_on_usage' but the raw text
        # contains a strong marker for performance_comparisons or
        # event_announcement, override. Fail-soft: log + keep the
        # un-post-processed by_brand on any exception.
        try:
            by_brand = _post_process_pragmatics(
                by_brand, it.get("text") or "",
            )
        except Exception as e:
            log.warning(
                "_run_post_fetch: _post_process_pragmatics failed for "
                "tweet_id=%s: %s",
                tid, e,
            )
        for brand_id, prongs in by_brand.items():
            # posts_brands_signals: (post_type, sentiment) per brand.
            # Scalar fields preserved from the legacy shape.
            signal_rows.append({
                "tweet_id": tid,
                "brand_id": brand_id,
                "post_type": prongs["post_type"],
                "sentiment": prongs["sentiment"],
            })
            # posts_brands_discourse: (discourse_role + 2 nationalism
            # axes) per brand. act_id = 1 (v1 always writes a single
            # speech-act per post × brand).
            discourse_rows.append({
                "tweet_id": tid,
                "brand_id": brand_id,
                "discourse_key": prongs["discourse_role"],
                "act_id": 1,
                "china_nationalism": prongs["china_nationalism"],
                "us_nationalism": prongs["us_nationalism"],
            })
            if (
                prongs["china_nationalism"] != "none"
                and prongs["us_nationalism"] != "none"
            ):
                n_nationalism += 1
        # U2a: capture top-level unsanctioned flags for the new table.
        flags = classified.get("unsanctioned_flags", []) if isinstance(
            classified, dict) else []
        if flags:
            unsanctioned_by_post[tid] = list(flags)
    t_classify = time.monotonic() - t0
    log.info(
        "_run_post_fetch: classify_batch_pragmatics_full %d brand rows "
        "(%d discourse, %d signal) in %.2fs",
        len(discourse_rows), len(discourse_rows),
        len(signal_rows), t_classify,
    )

    # Persist. The U4 path REPLACES the (post_type, sentiment) row
    # classify_post wrote (we don't double-write — U4 wins because
    # it's the merged-path writer). Insert one signal row per
    # (post × brand) — the existing `insert_posts_brands_signals`
    # is per-row (not bulk), so loop. Failures are per-row (the
    # method drops unknowns to dead-letter and continues).
    for s in signal_rows:
        try:
            store.insert_posts_brands_signals(
                post_id=s["tweet_id"],
                brand_id=s["brand_id"],
                post_type=s["post_type"],
                sentiment=s["sentiment"],
            )
        except Exception as e:
            log.warning(
                "_run_post_fetch: insert_posts_brands_signals "
                "(tweet_id=%s brand_id=%s): %s",
                s["tweet_id"], s["brand_id"], e,
            )
    try:
        store.bulk_insert_post_brand_discourse(discourse_rows)
    except Exception as e:
        log.warning("_run_post_fetch: bulk_insert_post_brand_discourse: %s", e)

    # U8a: Stage 3 — unsanctioned flags. One row per post with
    # non-empty unsanctioned_flags. Failures are per-row (the Store
    # method dead-letters on FK violations and continues).
    t_unsanc = time.monotonic()
    n_unsanctioned = 0
    for tid, flags in unsanctioned_by_post.items():
        try:
            store.upsert_unsanctioned_flags(tid, flags)
            n_unsanctioned += 1
        except Exception as e:
            log.warning(
                "_run_post_fetch: upsert_unsanctioned_flags "
                "(tweet_id=%s): %s", tid, e,
            )
    t_unsanc_ms = int((time.monotonic() - t_unsanc) * 1000)
    log.info(
        "_run_post_fetch: upsert_unsanctioned_flags %d posts in %dms",
        n_unsanctioned, t_unsanc_ms,
    )

    # Per-post counters for the smoketest runner.
    # n_discourse = kept posts with at least one PERSISTED discourse
    # row. The Store dead-letters `uncategorized` rows (KTD5), so the
    # row count returned by bulk_insert_post_brand_discourse may be
    # less than `len(discourse_rows)`. We approximate the per-post
    # set by re-reading the DB rather than re-counting the input —
    # the smoketest runner (U7) only needs an order-of-magnitude
    # signal.
    persisted_count = len({
        r["tweet_id"] for r in discourse_rows
        if r["discourse_key"] != "uncategorized"
    })
    counters["n_discourse"] = persisted_count
    counters["n_nationalism"] = n_nationalism
    counters["n_unsanctioned"] = n_unsanctioned
    counters["t_unsanctioned_ms"] = t_unsanc_ms
    return counters


class RunPipeline:
    """The x-monitor daily collection pipeline."""

    def __init__(self, config: Config, data_dir: Path, db_path: Path):
        self.config = config
        self.data_dir = data_dir
        self.db_path = db_path
        self.runs_dir = data_dir / "runs"
        # Plan 2026-07-11-001: data/queries/ is gone; runtime token
        # source is brand_keywords (DB).
        # Plan 2026-07-11-002 (U4): data/accounts/ is also gone; the
        # per-brand official/staff handle source is `brands_accounts`
        # (DB). See `Store.read_brand_official_staff_handles`.
        self.raw_dir = self.runs_dir / "raw"
        self.lock_path = self.runs_dir / "LOCK"
        self.review_queue_path = data_dir / "_review_queue.json"

    # --- cost & skip order ------------------------------------------------

    def estimate_cost(self, queries_per_model: dict[str, list[Query]]) -> int:
        total = 0
        for qs in queries_per_model.values():
            total += estimated_cost(qs)
        return total

    def apply_skip_order(
        self, queries: list[Query], budget: int
    ) -> tuple[list[Query], list[Query]]:
        """Return (queries_to_run, queries_skipped) after applying skip order
        if estimated cost > budget."""
        cost = estimated_cost(queries)
        if cost <= budget:
            return queries, []
        # Skip in the order from config; Q1 (release) is last.
        skip_order = self.config.degraded_skip_order
        enabled = [q for q in queries if q.enabled]
        disabled = [q for q in queries if not q.enabled]
        by_id = {q.id: q for q in enabled}
        # Walk the skip order and drop the cheapest first, until we fit.
        skipped: list[Query] = []
        kept: list[Query] = list(enabled)
        # Sort by max_results ascending so the smallest-cost query is dropped
        # first within a tie; this preserves the highest-signal Q1 last.
        for qid in skip_order:
            if qid not in by_id:
                continue
            if estimated_cost(kept) <= budget:
                break
            q = by_id[qid]
            if q in kept:
                kept.remove(q)
                skipped.append(q)
        return kept + disabled, skipped

    # --- execute ---------------------------------------------------------

    def execute(
        self,
        apify: TwitterApiClient,
        *,
        model_filter: list[str] | None = None,
        query_filter: list[str] | None = None,
        dry_run: bool = False,
        limit_per_call: int | None = None,
        no_skip_under_budget: bool = False,
        max_pages_per_call: int | None = None,
    ) -> dict[str, Any]:
        """Run the daily harvest.

        Plan 2026-07-13-001 (live_a_z_populate): the two new args
        thread the smoketest-style operator overrides through to the
        TwitterAPI.io max_results cap and the skip-order loop. When
        the operator runs `x-monitor run --limit-per-call 20
        --no-skip-under-budget` from `scripts.live_a_z_populate`, the
        pipeline behaves like the v1.6 smoketest (small-batch, no
        budget gating) while still writing to `data/x_monitoring.db`.

        Returns the run summary dict (also written to data/runs/<run_id>.json).
        """
        # Plan 2026-07-13-001: stash on `self` so the deeply nested
        # call site (`_query_twitterapi` + `apply_skip_order`) can
        # read them without a parameter refactor through 5 layers.
        self.limit_per_call = limit_per_call
        self.no_skip_under_budget = no_skip_under_budget
        self.max_pages_per_call = max_pages_per_call

        # Pre-flight $20 budget guard (plan 2026-07-13-001 follow-up).
        # TwitterAPI.io charges 300 credits per /twitter/tweet/advanced_search
        # page regardless of `n_results`. The 6-call smoketest shape
        # (A + B1 + B2 + B3 + C1 + C2) means worst-case spend is:
        #     6 calls × max_pages × 300 credits
        # We refuse to start if would_spend > 2,000,000 credits ($20).
        # This is hard-fail: an accidental `--max-pages-per-call 99999`
        # can never drain the budget silently.
        _BUDGET_HARD_CAP_CREDITS = 2_000_000  # $20 at TwitterAPI.io pricing
        _CREDITS_PER_ADVANCED_SEARCH_PAGE = 300
        _N_CALLS = 6  # A, B1, B2, B3, C1, C2
        _effective_max_pages = (
            self.max_pages_per_call
            if self.max_pages_per_call is not None
            else self.config.search.max_pages
        )
        _would_spend = (
            _N_CALLS * _effective_max_pages * _CREDITS_PER_ADVANCED_SEARCH_PAGE
        )
        if _would_spend > _BUDGET_HARD_CAP_CREDITS:
            raise RuntimeError(
                f"Pre-flight budget guard: would burn "
                f"{_would_spend:,} credits (${_would_spend / 100_000:.2f}) "
                f"at max_pages={_effective_max_pages} × {_N_CALLS} calls × "
                f"{_CREDITS_PER_ADVANCED_SEARCH_PAGE} credits/page, which "
                f"exceeds the ${_BUDGET_HARD_CAP_CREDITS // 100_000} hard cap "
                f"({_BUDGET_HARD_CAP_CREDITS:,} credits). Lower "
                f"--max-pages-per-call to "
                f"{_BUDGET_HARD_CAP_CREDITS // (_N_CALLS * _CREDITS_PER_ADVANCED_SEARCH_PAGE)} "
                f"or less and re-run."
            )
        run_id = f"{_now_iso().replace(':', '').replace('+', '_').replace('-', '')}-{uuid.uuid4().hex[:8]}"
        phase_timings: dict[str, float] = {}
        _run_t0 = time.monotonic()

        def _t(phase: str, t0: float) -> None:
            phase_timings[phase] = round(time.monotonic() - t0, 3)

        summary: dict[str, Any] = {
            "run_id": run_id,
            "started_at": _now_iso(),
            "finished_at": None,
            "status": "running",
            "degraded": {},
            "queries": [],
            "phase_timings_sec": phase_timings,
            "totals": {
                "n_queries_run": 0,
                "n_results": 0,
                "n_inserted": 0,
                "n_classifications_written": 0,
                "n_classifications_dropped": 0,
                "n_headlines_fetched": 0,
                "n_headlines_cached": 0,
            },
        }

        with pipeline_lock(self.lock_path) as acquired:
            if not acquired:
                summary["status"] = "degraded"
                summary["degraded"]["already_running"] = True
                summary["finished_at"] = _now_iso()
                self._write_summary(run_id, summary)
                return summary

            self._write_summary(run_id, summary)
            self._update_latest_symlink(run_id, running=True)

            # Load brand tokens from the DB (Plan 2026-07-15-003 U1).
            # The per-brand `data/queries/<m>.yaml` files were retired by
            # migration 030 (brand_keywords table). The legacy Query list
            # shape is preserved here only as a placeholder for the v1.6
            # budget/skip-order machinery, which is a no-op in v1.7 (cost
            # <= budget always). The single Query stub per brand feeds
            # `apply_skip_order` without surfacing as a real signal.
            models = model_filter or self.config.enabled_models
            store = Store(self.db_path)
            try:
                primary_keywords = store.read_primary_brand_keywords()
            except Exception as e:
                summary["degraded"]["missing_brand_keywords"] = str(e)
                primary_keywords = {}
            for m in models:
                if m not in primary_keywords:
                    summary["degraded"][f"missing_brand_keywords:{m}"] = (
                        f"no rows in brand_keywords for brand_id={m!r}"
                    )
            queries_per_model: dict[str, list[Query]] = {
                m: [
                    Query(
                        id="Q5",  # legacy Q-id; never reaches the DB
                        query_string="(placeholder)",
                        enabled=True,
                    )
                ]
                for m in models
            }

            # Apply skip order per model
            budget = self.config.daily_ceiling
            adjusted: dict[str, list[Query]] = {}
            # Plan 2026-07-13-001: --no-skip-under-budget forces every
            # per-model query through, bypassing the
            # daily_ceiling-based skip-order. In v1.7 this is largely
            # a no-op (per-model yaml is retired), but the knob keeps
            # the operator intent explicit.
            for m, qs in queries_per_model.items():
                if self.no_skip_under_budget:
                    kept, skipped = qs, []
                else:
                    kept, skipped = self.apply_skip_order(qs, budget)
                adjusted[m] = kept
                for q in skipped:
                    summary["queries"].append(
                        {
                            "brand_id": m,
                            "query_id": q.id,
                            "status": "skipped_budget",
                            "n_results": 0,
                        }
                    )
                    if "skipped_budget" not in summary["degraded"]:
                        summary["degraded"]["skipped_budget"] = []
                    summary["degraded"]["skipped_budget"].append(f"{m}/{q.id}")

            # Store init (auto-migrates) — note: Store was created earlier
            # (Plan 2026-07-15-003 U1 lifted this so read_primary_brand_keywords
            # can feed both the legacy stub list and the planner).
            review = ReviewQueue(self.review_queue_path)
            # v1.4: headline cache for URL-only posts (lives in data/).
            cache = HeadlinesCache(self.data_dir / "headlines_cache.json")
            # Per-run counter for API + HTTP fetches (shared across all
            # queries in this run). Live runs use the v1.2 defaults of
            # per_query_cap=8, per_run_cap=50.
            run_fetches_used: list[int] = [0]

            try:
                # Plan 2026-07-11-001: data/filters/*.yaml is retired.
                # The relevance-filter step (must_have_any / must_have_none
                # / canonical_handles / etc.) was the only consumer of
                # that surface; the in-code banned-token review-queue and
                # low-engagement-filter steps stay. See KTD6.
                # U7 hybrid by design: load the {term: brand_id} map from
                # the DB once per cycle. The yaml is the source for query
                # string construction (query_plan.py); the DB is the
                # source for post-fetch attribution. We also build the
                # yaml-derived map below only to feed the drift-detection
                # log — the attribution side uses the DB-loaded map.
                brand_search_terms_db = _load_brand_search_terms_from_db(store)
                # v1.6: build the per-cycle call list once. Account calls
                # (1 per brand) come first, then intent calls (1-3 per
                # bucket, split when over the operator cap). For each call:
                #   1. Run apify.run_search (paginated since v1.6 commit 1).
                #   2. For intent calls, reclassify each tweet's
                #      brand_id + source_query_id via attribute_to_brand
                #      + classify_signal.
                #   3. Run the existing v1.2 filter_and_review (F1
                #      hijack, banned-token review-queue, low-engagement).
                #   4. Insert kept rows + log summary.
                # v1.7: pass x_monitor_list_id to plan_calls when set on
                # config. When None, plan_calls raises TypeError (v1.7 does
                # not support a list-less fallback). The transitional
                # `x_monitor_list_id: int | None = None` on Config lets
                # legacy configs surface a clear "set x_monitor_list_id"
                # error rather than silently emit 0 calls.
                if self.config.x_monitor_list_id is None:
                    raise ValueError(
                        "config.x_monitor_list_id must be set in v1.7 — "
                        "Call A is list-based; see plan §'Call A — list-based "
                        "fan-in' for the operator steps to create the list."
                    )
                _t_plan = time.monotonic()
                # Plan 2026-07-11-001: plan_calls() signature is now
                # `(x_monitor_list_id, x_query_specs)` — no data_dir,
                # no call_b_groups, no call_c_specs. The legacy
                # per-brand yaml read path is retired in U3.
                #
                # Plan 2026-07-11-002 (U2): wide-net B-specs
                # (B1/B2/B3) read per-brand tokens from
                # `brand_keywords.is_primary=1` via the
                # `primary_keywords` kwarg. Already loaded once per run
                # at the top of cmd_run (Plan 2026-07-15-003 U1) — reuse
                # the cached dict here to avoid a second SQL roundtrip
                # per cycle.
                plan = plan_calls(
                    self.config.x_monitor_list_id,
                    self.config.x_query_specs or None,
                    primary_keywords=primary_keywords,
                )
                _t("plan", _t_plan)
                # Plan 2026-07-11-001 (U3): the per-brand yaml read
                # path is gone. Plan 2026-07-11-002 (U4):
                # `data/accounts/*.yaml` is also gone; staff_handles
                # now reads from `brands_accounts WHERE role_id IN (2,
                # 3)` via Store.read_brand_official_staff_handles.
                staff_handles = _staff_handles_map(store, models)
                _t_loop = time.monotonic()
                # U5: per-cycle accumulator for the post-fetch
                # transformers. Each `_attribute_call_items` returns
                # kept items in its own dict; we accumulate the
                # NEWLY-INSERTED set so _run_post_fetch runs once
                # after the loop. Use a list (order preserved) plus
                # a set to dedupe across calls when the same tweet
                # shows up twice (rare — repeated brand mentions).
                cycle_kept: list[dict[str, Any]] = []
                cycle_kept_ids: set[str] = set()
                for call in plan:
                    if dry_run:
                        summary["queries"].append(
                            {
                                "brand_id": call.brand_id,
                                "call_kind": call.call_kind,
                                "bucket": call.bucket,
                                "query_id": call.call_id,
                                "status": "dry_run",
                                "query_length": call.query_length,
                                "n_results": 0,
                            }
                        )
                        continue
                    raw_path = self.raw_dir / run_id / f"{call.brand_id}_{call.call_kind}_{call.bucket or 'acct'}.json"
                    raw_path.parent.mkdir(parents=True, exist_ok=True)

                    # U2 (since= cursor): read the prior cursor for
                    # this PlannedCall. If present, subtract
                    # CURSOR_OVERLAP_HOURS so near-boundary posts
                    # don't fall between cycles, and pass it as the
                    # `since=` kwarg. `apify.run_search` only injects
                    # it as a `since:` operator if the query string
                    # doesn't already contain one — no conflict
                    # with explicit `since:` strings.
                    #
                    # Build synth_q first so its `.id` (the Q1-Q6
                    # source query id) can be used as the query_id
                    # portion of the cursor key.
                    synth_q = _planned_call_to_query(call)

                    prior_iso = store.get_last_completed_at(
                        call.brand_id,
                        call.call_id,
                        call.call_kind,
                        call.bucket,
                        synth_q.id,
                    )
                    since_time_epoch: int | None = None
                    since_cursor: str | None = None
                    if prior_iso:
                        try:
                            prior_dt = datetime.fromisoformat(
                                prior_iso.replace("Z", "+00:00")
                            )
                            since_dt = prior_dt - timedelta(
                                hours=CURSOR_OVERLAP_HOURS
                            )
                            # TwitterAPI.io's `sinceTime` query param
                            # (unix epoch) is the sub-day-precision
                            # cursor. The `since:` operator truncates
                            # to date-only — using it would over-fetch
                            # by up to 24h per cycle.
                            since_time_epoch = int(since_dt.timestamp())
                            # Keep the date form as a hard floor (in case
                            # TwitterAPI.io's `sinceTime` semantics drift
                            # in the future).
                            since_cursor = since_dt.date().isoformat()
                        except (ValueError, TypeError):
                            # Defensive: a row with a malformed
                            # timestamp is treated as no cursor so
                            # the cycle still runs.
                            log.warning(
                                "call_state cursor for brand=%s call_id=%s "
                                "kind=%s bucket=%s query_id=%s has malformed "
                                "timestamp %r; ignoring",
                                call.brand_id, call.call_id,
                                call.call_kind, call.bucket,
                                synth_q.id, prior_iso,
                            )
                            since_cursor = None

                    _t_fetch = time.monotonic()
                    try:
                        s = self.config.search
                        # Plan 2026-07-13-001 (live_a_z_populate):
                        # `limit_per_call` overrides the config-driven
                        # per-call result cap when set (operator-driven
                        # smoketest-style runs). The TwitterAPI.io
                        # client caps each response at 20/page, so the
                        # upper bound is `max_pages * 20`.
                        max_results_cap = (
                            self.limit_per_call
                            if self.limit_per_call is not None
                            else s.max_results
                        )
                        # `max_pages_per_call` overrides the config-driven
                        # pagination safety cap when set (operator-driven
                        # production-shape runs). At 20 posts/page, the
                        # per-call ceiling is `max_pages × max_per_page`.
                        max_pages_cap = (
                            self.max_pages_per_call
                            if self.max_pages_per_call is not None
                            else s.max_pages
                        )
                        items = apify.run_search(
                            call.query_string,
                            max_results=max_results_cap,
                            since=since_cursor,
                            since_time=since_time_epoch,
                            max_pages=max_pages_cap,
                            max_per_page=s.max_per_page,
                        )
                    except TwitterApiAuthError as e:
                        summary["degraded"]["twitterapi_auth"] = str(e)
                        summary["status"] = "aborted"
                        break
                    except (TwitterApiRateLimitError, TwitterApiServerError) as e:
                        summary["queries"].append(
                            {
                                "brand_id": call.brand_id,
                                "call_kind": call.call_kind,
                                "bucket": call.bucket,
                                "query_id": call.call_id,
                                "status": "error",
                                "query_length": call.query_length,
                                "n_results": 0,
                                "error": str(e),
                            }
                        )
                        continue
                    _t(f"call.{call.brand_id}.{call.call_kind}.{call.bucket or 'acct'}.fetch", _t_fetch)

                    _t_attr = time.monotonic()
                    # v1.8 (R15): for intent calls, reclassify each tweet
                    # via the multi-brand pipeline. Populate
                    #   - it["brand_id"]      (legacy compat: first match)
                    #   - it["brand_ids"]     (list of all detected brands)
                    #   - it["mentions"]      (list of MentionRow instances)
                    #   - it["signals"]       (dict[brand_id, signal])
                    # source_query_id is derived from the legacy single-bucket
                    # classifier (compat path) so the per-tweet Q1-Q6 mapping
                    # for the dashboard stays consistent with v1.7.
                    #
                    # For account calls, the brand_id is the brand and
                    # source_query_id is "Q1" (release).
                    # v1.7: attribute every call's items via the
                    # per-cycle keyword index. Previously only the
                    # (dead in v1.7) `intent` branch ran attribute_to_brands;
                    # account (Call A, brand_id='*') and brand_wide
                    # (Call B) took an `else` branch that stamped the
                    # placeholder call.brand_id, collapsing every Call A
                    # post to _unattributed in insert_posts. Now all
                    # call kinds resolve real brand_ids via body_keyword
                    # + search_term matching (user_mention/hashtag stay
                    # offline — detection tables not populated).
                    # U7 hybrid: the body_keyword index is built from
                    # yaml tokens, but the {term: brand_id} map for
                    # search_term attribution comes from the DB
                    # (`brand_search_terms_db`, loaded once per cycle).
                    # The yaml is the query-side source; the DB is the
                    # attribution-side source.
                    index, _ = _build_brand_index(models)
                    classified = _attribute_call_items(
                        items, index, brand_search_terms_db,
                        brand_registry=None, anthropic_client=None,
                    )
                    # Drop items that matched no brand. These have no
                    # signal value for brand polarity. (v1.6 intent-branch
                    # contract, unified to all call kinds.)
                    items = [
                        it for it in items if not it.get("_unattributed")
                    ]
                    _t(f"call.{call.brand_id}.{call.call_kind}.{call.bucket or 'acct'}.attribute", _t_attr)
                    _t_filter = time.monotonic()
                    log.info(
                        "call brand_id=%s kind=%s bucket=%s n_results=%d "
                        "n_classified=%d",
                        call.brand_id, call.call_kind, call.bucket,
                        len(items), classified,
                    )
                    # `synth_q` was built earlier (U2 cursor read
                    # needs synth_q.id as the cursor query_id).
                    # The filter is per-model, but the tweets now span
                    # potentially many models. We partition by brand_id
                    # and filter each subset.
                    by_model: dict[str, list[dict]] = {}
                    for it in items:
                        m_id = it.get("brand_id") or "unknown"
                        by_model.setdefault(m_id, []).append(it)
                    kept_all: list[dict] = []
                    n_filtered_total = 0
                    reasons_total: dict[str, int] = {}
                    n_review_total = 0
                    for m_id, m_items in by_model.items():
                        # Plan 2026-07-11-001: RelevanceConfig / cfg_m
                        # are gone; the relevance-filter step was
                        # removed. The review-queue + headline-
                        # enrichment steps remain.
                        kept_m, drop_stats = filter_and_review(
                            m_items, synth_q, m_id, review,
                            cache=cache, api=apify,
                            run_fetches_used=run_fetches_used,
                        )
                        kept_all.extend(kept_m)
                        n_filtered_total += drop_stats["n_dropped"]
                        for k, v in drop_stats["reasons"].items():
                            reasons_total[k] = reasons_total.get(k, 0) + v
                        n_review_total += drop_stats["n_soft_dropped"]

                    # Persist raw of the KEPT set. MentionRow
                    # dataclasses are not JSON-serializable by
                    # default; coerce them to dicts via `vars()`
                    # before dumping so the raw file can be re-read
                    # by the resume path (which expects plain
                    # dicts).
                    def _jsonable_post(it: dict[str, Any]) -> dict[str, Any]:
                        out = dict(it)
                        ms = out.get("mentions")
                        if isinstance(ms, list):
                            out["mentions"] = [
                                m if isinstance(m, dict) else vars(m)
                                for m in ms
                            ]
                        return out

                    raw_path.write_text(
                        json.dumps(
                            [_jsonable_post(it) for it in kept_all],
                            ensure_ascii=False,
                            default=str,
                        ),
                        encoding="utf-8",
                    )
                    n_inserted = store.insert_posts(kept_all)
                    # U5: append newly-inserted posts to the cycle
                    # accumulator so _run_post_fetch has the full
                    # kept set after the loop ends. dedupe by tweet_id.
                    for _it in kept_all:
                        _tid = str(_it.get("id") or _it.get("tweet_id") or "")
                        if _tid and _tid not in cycle_kept_ids:
                            cycle_kept.append(_it)
                            cycle_kept_ids.add(_tid)
                    # Plan 2026-07-15-003 U3: n_classifications_written is
                    # read once after _run_post_fetch completes (further
                    # below), so post-fetch writes via
                    # `insert_posts_brands_signals` count toward the
                    # total. Do NOT accumulate it here — the per-cycle
                    # value is meaningless since post-fetch runs after
                    # the loop.
                    _t(f"call.{call.brand_id}.{call.call_kind}.{call.bucket or 'acct'}.filter+store", _t_filter)

                    log.info(
                        "call model=%s kind=%s bucket=%s n_results=%d "
                        "n_kept=%d n_dropped=%d reasons=%s n_review=%d",
                        call.brand_id, call.call_kind, call.bucket,
                        len(items), len(kept_all), n_filtered_total,
                        reasons_total, n_review_total,
                    )

                    # U2 (cursor advance): only advance on success,
                    # AFTER filter/store completed. If any preceding
                    # step raised, we'd have already broken out of
                    # the loop via TwitterApiAuthError / the
                    # rate-limit-and-server-error continues, so this
                    # point is reached only when the whole per-call
                    # pipeline succeeded. We do NOT advance on
                    # inserted_count == 0 — the cursor covers "we
                    # fetched through this moment"; 0 inserted is
                    # still a successful fetch.
                    try:
                        store.set_last_completed_at(
                            call.brand_id,
                            call.call_id,
                            call.call_kind,
                            call.bucket,
                            synth_q.id,
                            _now_iso(),
                        )
                    except Exception as exc:
                        # A failing cursor write must not abort the
                        # cycle — log and keep going. Worst case:
                        # the next cycle re-fetches some tweets,
                        # which the tweet_id dedup in insert_posts
                        # already handles.
                        log.warning(
                            "failed to advance call_state cursor for "
                            "brand=%s call_id=%s kind=%s bucket=%s "
                            "query_id=%s: %s",
                            call.brand_id, call.call_id,
                            call.call_kind, call.bucket,
                            synth_q.id, exc,
                        )

                    summary["queries"].append(
                        {
                            "brand_id": call.brand_id,
                            "call_kind": call.call_kind,
                            "bucket": call.bucket,
                            # Plan 2026-07-15-003 U2: emit the planner's
                            # A/B/C call_id, not the v1.6 Query stub's
                            # Q-string id. (U1 keeps the Query stub only
                            # to satisfy apply_skip_order's type signature.)
                            "query_id": call.call_id,
                            "query_length": call.query_length,
                            "status": "completed",
                            "n_results": len(items),
                            "n_kept": len(kept_all),
                            "n_filtered": n_filtered_total,
                            "filter_reasons": reasons_total,
                            "n_review_added": n_review_total,
                            "n_inserted": n_inserted,
                            "raw_path": str(raw_path.relative_to(self.data_dir)),
                        }
                    )
                    summary["totals"]["n_queries_run"] += 1
                    summary["totals"]["n_results"] += len(items)
                    summary["totals"]["n_inserted"] += n_inserted
                _t("calls_loop_total", _t_loop)

                if summary["status"] == "aborted":
                    pass  # already handled in the inner break

                # U5: post-fetch transformers (translate + classify).
                # Runs ONCE per cycle on the cycle_kept accumulator.
                # Skipped on dry_run / abort (the kept set is empty
                # under dry_run anyway). See plan §5 High-Level
                # Technical Design.
                if not dry_run and summary["status"] != "aborted" and cycle_kept:
                    _t_pf = time.monotonic()
                    try:
                        # Lazy import to avoid pulling the anthropic
                        # SDK at module load (offline / no-key paths
                        # still work via _run_post_fetch's no-client
                        # short-circuit).
                        # Use the env-driven factory so the classifier
                        # respects ANTHROPIC_BASE_URL /
                        # X_MONITOR_CLASSIFIER_BASE_URL / DEEPSEEK_API_KEY
                        # routing. Constructing AnthropicClaudeClient()
                        # bare here would route to api.anthropic.com via
                        # the SDK's default (ANTHROPIC_API_KEY), bypassing
                        # the operator's proxy / DeepSeek override.
                        from x_monitor.reattribute import (
                            build_anthropic_client_from_env,
                        )
                        anthropic_client = build_anthropic_client_from_env()
                        # brand_registry_rows from the open Store;
                        # brand_tokens from the cycle's per-model map.
                        pf_counters = _run_post_fetch(
                            cycle_kept,
                            store=store,
                            anthropic_client=anthropic_client,
                            brand_registry_rows=store.read_brands(),
                            brand_tokens=getattr(
                                self.config, "brand_tokens_map", None
                            ),
                        )
                        summary.setdefault("post_fetch", {}).update(pf_counters)
                        # Also surface per-stage wall-clock for the
                        # smoketest runner (U7).
                        summary["post_fetch"]["wall_clock_sec"] = (
                            time.monotonic() - _t_pf
                        )
                    except Exception as e:  # never abort the run over post-fetch
                        log.warning("post-fetch transformers failed: %s", e)
                        summary.setdefault("post_fetch", {})[
                            "error"
                        ] = str(e)
                    _t("post_fetch", _t_pf)
                    # Plan 2026-07-15-003 U3: read the final classification
                    # counters once after _run_post_fetch completes (both
                    # the inline `insert_posts` writer at store.py:780 and
                    # `insert_posts_brands_signals` bump them).
                    summary["totals"]["n_classifications_written"] = (
                        store._classifications_written
                    )
                    summary["totals"]["n_classifications_dropped"] = (
                        store._classifications_dropped
                    )

                # v1.9 (2026-06-22): quote-tweet capture. Runs after the
                # main harvest so newly-attributed posts are in the DB.
                # Skipped on dry_run / abort. See plan Units 4 & 5.
                if not dry_run and summary["status"] != "aborted":
                    # Plan 2026-07-11-001 (U3): _brand_tokens_map is
                    # gone. The body_keyword index is now self-brand-
                    # only.
                    qt_index, _ = _build_brand_index(models)
                    qt_staff = _staff_handles_map(store, models)
                    _t_qt_o = time.monotonic()
                    try:
                        qt_out = self._capture_official_quote_tweets(
                            apify, store, qt_index, brand_search_terms_db, qt_staff,
                        )
                        summary.setdefault("quote_tweets", {}).update(qt_out)
                    except Exception as e:  # never abort the run over QT capture
                        log.warning("official QT capture failed: %s", e)
                        summary.setdefault("quote_tweets", {})[
                            "official_error"
                        ] = str(e)
                    _t("qt_official", _t_qt_o)

                    _t_qt_d = time.monotonic()
                    try:
                        daily_out = self._capture_nonofficial_quote_tweets_daily(
                            apify, store, qt_index, brand_search_terms_db, qt_staff,
                        )
                        summary.setdefault("quote_tweets", {}).update(daily_out)
                    except Exception as e:  # never abort the run over QT capture
                        log.warning("daily QT capture failed: %s", e)
                        summary.setdefault("quote_tweets", {})[
                            "daily_error"
                        ] = str(e)
                    _t("qt_daily", _t_qt_d)
            finally:
                # Account graph update MUST run on an open DB. Previously
                # the close() here meant _update_accounts below crashed
                # with `sqlite3.ProgrammingError: Cannot operate on a
                # closed database` (task #288). The store stays open
                # through the account-graph step and closes once the
                # summary write is done.
                pass

            # Account graph update
            _t_acc = time.monotonic()
            self._update_accounts(store, summary)
            _t("account_graph", _t_acc)

            if summary["status"] == "running":
                summary["status"] = "completed" if not summary["degraded"] else "degraded"
            summary["finished_at"] = _now_iso()
            _t("total", _run_t0)
            # Per-request HTTP log captured by TwitterApiClient._get.
            # Surfaced at the top level of the run JSON so scripts/
            # dump_http_log.py can post-process any past run without
            # needing live access to the apify client.
            try:
                summary["http_log"] = list(apify._request_log)
            except AttributeError:
                summary["http_log"] = []
            self._write_summary(run_id, summary)
            self._update_latest_symlink(run_id, running=False)
            # Close the store at the very end (task #288 — was
            # previously inside the post-fetch finally block, which
            # caused _update_accounts above to crash on a closed DB).
            try:
                store.close()
            except Exception:
                pass
            return summary

    def _capture_official_quote_tweets(
        self,
        apify: TwitterApiClient,
        store: Store,
        index: Any,
        brand_search_terms: dict[str, str],
        staff_handles: dict[str, list[str]],
    ) -> dict[str, Any]:
        """Adaptive every-cycle QT capture for official/staff posts.

        Tracks recent official/staff posts (created within
        `quote_tweets.track_recency_days`), batched-refreshes their current
        `quote_count`, and for any whose `quote_count` grew by >=
        `official_delta` since the last fetch, pulls the new QTs and ingests
        them. Velocity is emergent: a flooding post crosses the threshold
        every cycle; a quiet one never does.

        `update_quote_tracking` runs AFTER a successful fetch (and ingest),
        so a failed ingest retries the same `sinceTime` window next cycle
        (idempotent via tweet_id dedup). A successful ingest whose tracking
        update fails simply re-fetches next cycle — safe, never double-counted.
        """
        cfg = self.config.quote_tweets
        staff_set = {h for hs in staff_handles.values() for h in hs}
        out: dict[str, Any] = {"official_n_tracked": 0}
        if not staff_set:
            return out
        cutoff_epoch = (
            int(datetime.now(timezone.utc).timestamp())
            - cfg.track_recency_days * 86400
        )
        placeholders = ",".join("?" for _ in staff_set)
        rows = store._conn.execute(
            "SELECT tweet_id, text, last_quote_count_seen, last_quote_fetched_at "
            f"FROM posts WHERE author_handle IN ({placeholders}) "
            "AND created_at_epoch >= ?",
            (*staff_set, cutoff_epoch),
        ).fetchall()
        out["official_n_tracked"] = len(rows)
        if not rows:
            return out
        # Batched refresh: one chunked call for every tracked post's counts.
        try:
            fresh = apify.get_tweets_by_ids([r["tweet_id"] for r in rows])
        except Exception as e:
            log.warning("official QT refresh failed: %s", e)
            out["official_refresh_error"] = str(e)
            return out
        n_calls = 0
        n_qts = 0
        n_ingested = 0
        for r in rows:
            tid = r["tweet_id"]
            info = fresh.get(tid)
            if not info:
                continue
            fresh_qc = int(info.get("quote_count") or 0)
            delta = fresh_qc - int(r["last_quote_count_seen"] or 0)
            if delta < cfg.official_delta:
                continue
            since_time = _iso_to_epoch(r["last_quote_fetched_at"])
            try:
                qts = apify.get_quote_tweets(
                    tid, since_time=since_time, max_pages=cfg.max_pages
                )
            except Exception as e:
                log.warning("official QT fetch failed for %s: %s", tid, e)
                continue
            n_calls += 1
            if qts:
                try:
                    ingested = _ingest_quote_tweets(
                        qts, tid, r["text"] or "",
                        index=index,
                        brand_search_terms=brand_search_terms,
                        store=store,
                    )
                except Exception as e:
                    log.warning("official QT ingest failed for %s: %s", tid, e)
                    ingested = 0
                n_ingested += ingested
                n_qts += len(qts)
            # Advance tracking after a successful fetch even when 0 new QTs
            # came back, so a post that crossed the threshold but had no new
            # quotes doesn't re-bill the 15-tweet floor every cycle.
            store.update_quote_tracking(tid, fresh_qc, _now_iso())
            if n_calls >= cfg.official_call_budget:
                break
        out.update(
            official_n_calls=n_calls,
            official_n_qts_fetched=n_qts,
            official_n_ingested=n_ingested,
        )
        return out

    def _capture_nonofficial_quote_tweets_daily(
        self,
        apify: TwitterApiClient,
        store: Store,
        index: Any,
        brand_search_terms: dict[str, str],
        staff_handles: dict[str, list[str]],
    ) -> dict[str, Any]:
        """Once-per-day QT capture for non-official posts.

        Date-gated via `data/_qt_daily_marker` (runs at most once per UTC
        day). Selects recent non-official posts (created within
        `quote_tweets.daily_recency_days`, author NOT a staff/official
        handle), batched-refreshes their current `quote_count`, and for any
        with new growth (`delta >= 1`) fetches + ingests the new QTs.
        `daily_call_budget` caps the fetch CALLS. Older posts age out of the
        recency window, so the daily poll set stays bounded.

        Tracking advances for every checked post (growth or not) so a stable
        post isn't re-fetched, and `sinceTime` resumes correctly.
        """
        cfg = self.config.quote_tweets
        out: dict[str, Any] = {"daily_ran": False}
        if not cfg.daily_enabled:
            return out
        today = datetime.now(timezone.utc).date().isoformat()
        marker = self.data_dir / "_qt_daily_marker"
        if marker.exists() and marker.read_text(encoding="utf-8").strip() == today:
            return out  # already ran today
        staff_set = {h for hs in staff_handles.values() for h in hs}
        cutoff_epoch = (
            int(datetime.now(timezone.utc).timestamp())
            - cfg.daily_recency_days * 86400
        )
        # Non-official = author NOT in the staff/official set. LIMIT caps the
        # refresh candidate set so a huge recent-post volume can't drain the
        # budget on count-lookups alone.
        if staff_set:
            rows = store._conn.execute(
                "SELECT tweet_id, text, last_quote_count_seen, last_quote_fetched_at "
                f"FROM posts WHERE created_at_epoch >= ? "
                f"AND author_handle NOT IN ({','.join('?' for _ in staff_set)}) "
                "ORDER BY created_at_epoch DESC LIMIT 500",
                (cutoff_epoch, *staff_set),
            ).fetchall()
        else:
            rows = store._conn.execute(
                "SELECT tweet_id, text, last_quote_count_seen, last_quote_fetched_at "
                "FROM posts WHERE created_at_epoch >= ? "
                "ORDER BY created_at_epoch DESC LIMIT 500",
                (cutoff_epoch,),
            ).fetchall()
        out["daily_n_candidates"] = len(rows)
        if not rows:
            # See the post-loop comment for why we always write the marker.
            marker.write_text(today, encoding="utf-8")
            out["daily_ran"] = True
            return out
        try:
            fresh = apify.get_tweets_by_ids([r["tweet_id"] for r in rows])
        except Exception as e:
            log.warning("daily QT refresh failed: %s", e)
            out["daily_refresh_error"] = str(e)
            return out  # no marker write -> retries next cycle
        n_calls = 0
        n_qts = 0
        n_ingested = 0
        for r in rows:
            tid = r["tweet_id"]
            info = fresh.get(tid)
            if not info:
                continue
            fresh_qc = int(info.get("quote_count") or 0)
            delta = fresh_qc - int(r["last_quote_count_seen"] or 0)
            if delta >= 1:
                since_time = _iso_to_epoch(r["last_quote_fetched_at"])
                try:
                    qts = apify.get_quote_tweets(
                        tid, since_time=since_time, max_pages=cfg.max_pages
                    )
                except Exception as e:
                    log.warning("daily QT fetch failed for %s: %s", tid, e)
                    continue
                n_calls += 1
                if qts:
                    try:
                        ingested = _ingest_quote_tweets(
                            qts, tid, r["text"] or "",
                            index=index,
                            brand_search_terms=brand_search_terms,
                            store=store,
                        )
                    except Exception as e:
                        log.warning("daily QT ingest failed for %s: %s", tid, e)
                        ingested = 0
                    n_ingested += ingested
                    n_qts += len(qts)
                    # Only advance tracking on a successful ingest; if
                    # `ingested == 0` (raised or all filtered), keep the
                    # prior `last_quote_count_seen` so the next cycle
                    # re-fetches the missed QTs instead of treating them
                    # as already-seen.
                    if ingested > 0:
                        store.update_quote_tracking(tid, fresh_qc, _now_iso())
                else:
                    # No new QTs reported by the API — record the observed
                    # count so we do not keep polling this stable post.
                    store.update_quote_tracking(tid, fresh_qc, _now_iso())
                if n_calls >= cfg.daily_call_budget:
                    break
            else:
                # No new growth — advance tracking so we don't re-check a
                # stable post's count every day (cheap local UPDATE).
                store.update_quote_tracking(tid, fresh_qc, _now_iso())
        # Marker is written unconditionally (incl. on budget break). Same-day
        # resume is safe because per-post `update_quote_tracking` above
        # persists the observed `quote_count` and `last_quote_fetched_at`;
        # the marker only gates the *next* UTC day, not retries within today.
        marker.write_text(today, encoding="utf-8")
        out.update(
            daily_ran=True,
            daily_n_calls=n_calls,
            daily_n_qts_fetched=n_qts,
            daily_n_ingested=n_ingested,
        )
        return out

    def _update_accounts(self, store: Store, summary: dict[str, Any]) -> None:
        """Re-upsert per-brand official/staff handles from the DB +
        discover commenters from posts and upsert them as 'community'
        or 'unknown' role.

        Plan 2026-07-11-002 (U4): the per-brand yaml seed
        (`data/accounts/<brand>.yaml`) is retired. The DB's
        `brands_accounts WHERE role_id IN (2, 3)` is canonical; the
        `Store.read_brand_official_staff_handles` helper returns
        `(handle, role_key)` pairs that this method threads through
        `upsert_account`. The yaml `display_name / verified /
        bio_contains_brand / multi_brand_voice / notes` metadata is
        lost in the transition — operator-managed handles carry
        `verified=False, bio_contains_brand=False,
        multi_brand_voice=False, notes=""` defaults unless they
        update the row directly via SQL.

        Commenter discovery (the in-code post-body loop below)
        continues unchanged: it reads from `posts`, not yaml.
        """
        # Read seeded (handle, role_key) pairs from the DB once.
        seeded = store.read_brand_official_staff_handles(
            self.config.enabled_models
        )
        for m in self.config.enabled_models:
            seed_pairs = seeded.get(m, [])
            # Re-upsert seeded accounts (role + last_seen_at).
            for handle, role_key in seed_pairs:
                store.upsert_account(
                    brand_id=m,
                    handle=handle,
                    role=role_key,
                )
            # Discover commenters from posts and upsert them as
            # 'community' or 'unknown' role. The role_tag rules
            # upgrade suspicious/developer/employee on the next pass.
            posts = store.get_all_posts(m)
            commenters: dict[str, dict[str, Any]] = {}
            for p in posts:
                in_reply = p.get("in_reply_to_user_id")
                author = p.get("author_handle")
                if in_reply and author and in_reply != author:
                    a = commenters.setdefault(
                        author,
                        {
                            "role": "community",
                            "verified": False,
                            "bio_contains_brand": False,
                            "multi_posts": 0,
                            "posts": [],
                        },
                    )
                    a["multi_posts"] += 1
                    a["posts"].append(p)
            seeded_handles = {h for h, _ in seed_pairs}
            for handle, info in commenters.items():
                if handle in seeded_handles:
                    continue
                role = role_tag(
                    Account(handle=handle, role=info["role"]),
                    posts_for_account=info["posts"][:10],
                )
                # NOTE(task #308): `thread_count` is computed but not
                # persisted. `Store.upsert_account` does not accept the
                # `multiple_posts_in_thread_with_official` kwarg, and we
                # are intentionally NOT extending the schema right now
                # (the metric is not load-bearing; nothing reads it back).
                # If a future feature needs the metric, either add a
                # column here or log it to the run-summary JSON instead.
                thread_count = sum(
                    1 for p in info["posts"] if p.get("in_reply_to_user_id")
                )
                del thread_count  # marker for future wiring
                store.upsert_account(
                    brand_id=m,
                    handle=handle,
                    role=role,
                    source_query_ids=[],
                    verified=False,
                    bio_contains_brand=False,
                    multi_brand_voice=False,
                )
                for p in info["posts"]:
                    store.record_appearance(m, handle, p["tweet_id"], role_at_time=role)

    def _write_summary(self, run_id: str, summary: dict[str, Any]) -> None:
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        path = self.runs_dir / f"{run_id}.json"
        path.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

    def _update_latest_symlink(self, run_id: str, running: bool) -> None:
        """Atomic replace of LATEST.json (or LATEST.running.json) symlink."""
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        target = self.runs_dir / f"{run_id}.json"
        link_name = "LATEST.running.json" if running else "LATEST.json"
        link_path = self.runs_dir / link_name
        tmp_link = self.runs_dir / f".{link_name}.tmp"
        try:
            if tmp_link.is_symlink() or tmp_link.exists():
                tmp_link.unlink()
            os.symlink(target.name, tmp_link)
            os.replace(tmp_link, link_path)
        except OSError as e:
            log.warning("symlink replace failed: %s", e)

    # --- resume ----------------------------------------------------------

    def resume(self, run_id: str, apify: TwitterApiClient) -> dict[str, Any]:
        """Re-read raw JSON for a prior run and re-attempt inserts.

        Does NOT call Apify. Idempotent on tweet_id.
        """
        raw_dir = self.raw_dir / run_id
        if not raw_dir.exists():
            raise FileNotFoundError(f"no raw dir for run_id {run_id}")
        store = Store(self.db_path)
        try:
            totals = {"n_queries": 0, "n_results": 0, "n_inserted": 0}
            for raw_file in sorted(raw_dir.glob("*.json")):
                items = json.loads(raw_file.read_text(encoding="utf-8"))
                if not isinstance(items, list):
                    continue
                totals["n_queries"] += 1
                totals["n_results"] += len(items)
                n = store.insert_posts(items)
                totals["n_inserted"] += n
            return {"run_id": run_id, "resumed": True, "totals": totals}
        finally:
            store.close()
