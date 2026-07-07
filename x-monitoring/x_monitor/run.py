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

from .accounts import Account, derive_edges, find_clusters, load_accounts, role_tag
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
)
from .relevance import RelevanceConfig, filter_posts, load_filter
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
    cfg: RelevanceConfig,
    review: ReviewQueue,
    cache: HeadlinesCache | None = None,
    api: TwitterApiClient | None = None,
    run_fetches_used: list[int] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Apply the per-model relevance filter, then layer review-queue rules.

    Returns (kept, drop_stats) where:
      - kept: items that should be inserted into the DB.
      - drop_stats: dict with n_dropped, n_kept, n_soft_dropped, reasons.
        Reasons are the keys from x_monitor.relevance.

    Side effects:
      - Soft-dropped items are added to the review queue with
        reason="banned_token" (so the operator can promote them via
        `x-monitor review resolve` if they turn out to be real signal).

    U9 (migration 022): the `expected_signal == "release"` low-engagement
    review rule was REMOVED with the 6-signal taxonomy. The rule fired
    on Q1/release posts with like_count < 2; with `expected_signal`
    gone, the rule cannot apply uniformly. Per-Q1 low-engagement
    enforcement is a follow-up if needed (operators can still inspect
    the kept set with like_count=0/1 via the dashboard).

    Items here are normalized post dicts (with `id`, `text`,
    `author_handle`, `like_count`, `brand_id`, `source_query_id`).

    If `cache` is provided, the kept set is passed through enrich_posts()
    so URL-only posts get their article headlines (X-articles go through
    api.get_article when both `api` and the URL match). The returned
    `kept` list reflects the enrichment.
    """
    kept, stats, soft = filter_posts(items, cfg)
    for sd in soft:
        review.append_rule_match(
            tweet_id=sd["tweet_id"],
            reason=sd["reason"],
            brand_id=brand_id,
            rule="must_have_none",
        )
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


def _planned_call_to_query(call: "PlannedCall") -> Query:
    """Synthesize a Query object for the v1.2 filter_and_review helper.

    U9 (migration 022): the Query model no longer carries
    `expected_signal` (the 6-signal taxonomy was killed). The filter
    only reads .id, .min_faves, .query_string. Account calls get
    Q1 (min_faves=1, the "release-like" preset); brand_wide calls
    get a generic Q5 (min_faves=0).
    """
    from .query_plan import PlannedCall  # local to avoid circular at import
    if call.call_kind == "account":
        qid, min_faves = "Q1", 1
    else:
        qid, min_faves = "Q5", 0
    return Query(
        id=qid,  # type: ignore[arg-type]
        query_string=call.query_string,
        max_results=50,
        enabled=True,
        min_faves=min_faves,
    )

def _brand_tokens_map(enabled_models: list[str], data_dir: Path) -> dict[str, list[str]]:
    """Build {brand_id: [brand_token, ...]} from data/queries/<m>.yaml.

    Mirrors query_plan._load_brand_tokens_per_model; duplicated here
    so RunPipeline doesn't have to import a private function.
    """
    from .query_plan import _load_brand_tokens_per_model
    return _load_brand_tokens_per_model(enabled_models, data_dir / "queries")

def _staff_handles_map(enabled_models: list[str], data_dir: Path) -> dict[str, list[str]]:
    """Build {brand_id: [handle, ...]} for staff/official attribution.

    For v1.6 the attribute_to_brand prefers author_handle match over
    text-contains, so we fold the official handle into the per-brand
    list alongside staff.
    """
    from .accounts import load_accounts, load_staff
    out: dict[str, list[str]] = {}
    for m in enabled_models:
        try:
            accts = load_accounts(m, data_dir)
        except (FileNotFoundError, ValueError):
            out[m] = []
            continue
        handles = [a.handle for a in accts if a.role == "official"]
        try:
            staff = load_staff(m, data_dir)
        except (FileNotFoundError, ValueError):
            staff = []
        out[m] = handles + [s.handle for s in staff]
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
    brand_tokens: dict[str, list[str]],
    models: list[str],
) -> tuple[Any, dict[str, str]]:
    """Build the per-cycle brand keyword index + search-term map.

    Maps v1.7 yaml brand tokens to canonical brand_ids via KNOWN_MODELS
    + _BRAND_ALIASES, then seeds each enabled model's self-brand so
    posts that mention the model name are detected via body_keyword.

    Returns (compiled_keyword_index, brand_search_terms) — shared across
    all call kinds in the cycle.
    """
    keyword_triples: list[tuple[str, str, bool]] = []
    for model_id, toks in brand_tokens.items():
        for tok in toks:
            canonical = tok.strip().lower()
            if not canonical:
                continue
            if canonical in KNOWN_MODELS:
                keyword_triples.append((canonical, tok, False))
            elif canonical in _BRAND_ALIASES:
                keyword_triples.append(
                    (_BRAND_ALIASES[canonical], tok, False)
                )
            # else: token doesn't map to a known brand; drop it.
    for m in models:
        if m in KNOWN_MODELS and not any(
            t[0] == m for t in keyword_triples
        ):
            keyword_triples.append((m, m, False))
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


def _log_brand_search_terms_drift(
    yaml_terms: dict[str, str],
    db_terms: dict[str, str],
) -> None:
    """Log a warning if the yaml and DB brand_search_terms maps disagree.

    Drift is informational, not a hard fail. Three signals:

      1. term in yaml but not in DB — the DB has stale coverage; the
         query string can still match this term, but the attribution
         side cannot map it back to a brand.
      2. term in DB but not in yaml — the DB has an attribution entry
         that no current query string produces. Probably leftover from
         a removed brand or query; safe to drop, but flagged.
      3. term in both with different brand_id — a brand_id mismatch
         on a shared term; the DB wins at attribution time (yaml is
         query-side, DB is attribution-side).
    """
    yaml_keys = set(yaml_terms)
    db_keys = set(db_terms)
    only_yaml = yaml_keys - db_keys
    only_db = db_keys - yaml_keys
    shared = yaml_keys & db_keys
    mismatched = {t for t in shared if yaml_terms[t] != db_terms[t]}
    if not (only_yaml or only_db or mismatched):
        return
    log.warning(
        "brand_search_terms drift: yaml-only=%d db-only=%d mismatched=%d "
        "(yaml=%d db=%d); DB wins at attribution time",
        len(only_yaml), len(only_db), len(mismatched),
        len(yaml_keys), len(db_keys),
    )
    if only_yaml:
        sample = sorted(only_yaml)[:5]
        log.warning("  yaml-only terms (sample): %s", sample)
    if only_db:
        sample = sorted(only_db)[:5]
        log.warning("  db-only terms (sample): %s", sample)
    if mismatched:
        sample = sorted(mismatched)[:5]
        log.warning("  mismatched terms (sample): %s", sample)


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
    from .attribution import classify_pragmatics_full

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

    # --- Stage 2: classify_pragmatics_full (U4) -------------------------
    # One LLM call per post (not batched here — the U4 prompt is
    # already structured for per-brand output; batching posts is the
    # Store's job, not the LLM call's). For ~200 kept posts at the
    # typical 15-min cadence this is ~200 calls; the
    # `_call_signal_with_retry` retry policy handles transient 429/5xx.
    # U2a/U2b: classify_pragmatics_full returns the new shape
    # {"by_brand": {...}, "unsanctioned_flags": [...]}. We use the
    # by_brand dict for signal/discourse persistence and the
    # unsanctioned_flags for the new posts_unsanctioned_flags write.
    t0 = time.monotonic()
    discourse_rows: list[dict[str, Any]] = []
    signal_rows: list[dict[str, Any]] = []
    unsanctioned_by_post: dict[str, list[str]] = {}
    n_nationalism = 0
    for it in kept_posts:
        brand_ids = it.get("brand_ids") or []
        if not brand_ids:
            continue
        try:
            classified = classify_pragmatics_full(
                text=it.get("text") or "",
                brand_ids=list(brand_ids),
                brand_registry=brand_registry_rows,
                anthropic_client=anthropic_client,
            )
        except Exception as e:
            log.warning(
                "_run_post_fetch: classify_pragmatics_full failed for "
                "tweet_id=%s: %s",
                it.get("id") or it.get("tweet_id"), e,
            )
            continue
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
                it.get("id") or it.get("tweet_id"), e,
            )
        for brand_id, prongs in by_brand.items():
            # posts_brands_signals: (post_type, sentiment) per brand.
            # Scalar fields preserved from the legacy shape.
            signal_rows.append({
                "tweet_id": str(it.get("id") or it.get("tweet_id")),
                "brand_id": brand_id,
                "post_type": prongs["post_type"],
                "sentiment": prongs["sentiment"],
            })
            # posts_brands_discourse: (discourse_role + 2 nationalism
            # axes) per brand. act_id = 1 (v1 always writes a single
            # speech-act per post × brand).
            discourse_rows.append({
                "tweet_id": str(it.get("id") or it.get("tweet_id")),
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
            tid = str(it.get("id") or it.get("tweet_id"))
            unsanctioned_by_post[tid] = list(flags)
    t_classify = time.monotonic() - t0
    log.info(
        "_run_post_fetch: classify_pragmatics_full %d brand rows "
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
        self.queries_dir = data_dir / "queries"
        self.accounts_dir = data_dir / "accounts"
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
    ) -> dict[str, Any]:
        """Run the daily harvest.

        Returns the run summary dict (also written to data/runs/<run_id>.json).
        """
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

            # Load queries
            models = model_filter or self.config.enabled_models
            queries_per_model: dict[str, list[Query]] = {}
            for m in models:
                try:
                    queries_per_model[m] = load_queries(m, self.data_dir)
                except (FileNotFoundError, ValueError) as e:
                    summary["degraded"][f"missing_queries:{m}"] = str(e)
                    queries_per_model[m] = []

            # Apply skip order per model
            budget = self.config.daily_ceiling
            adjusted: dict[str, list[Query]] = {}
            for m, qs in queries_per_model.items():
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

            # Store init (auto-migrates)
            store = Store(self.db_path)
            review = ReviewQueue(self.review_queue_path)
            # v1.4: headline cache for URL-only posts (lives in data/).
            cache = HeadlinesCache(self.data_dir / "headlines_cache.json")
            # Per-run counter for API + HTTP fetches (shared across all
            # queries in this run). Live runs use the v1.2 defaults of
            # per_query_cap=8, per_run_cap=50.
            run_fetches_used: list[int] = [0]

            try:
                # Load per-model filter configs once per model (v1.2).
                # Missing files return an empty config (no filter applied),
                # so legacy models without a YAML continue to work.
                cfgs: dict[str, RelevanceConfig] = {
                    m: load_filter(m, self.data_dir) for m in adjusted
                }
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
                plan = plan_calls(
                    self.data_dir, models,
                    x_monitor_list_id=self.config.x_monitor_list_id,
                    call_b_groups=self.config.call_b_groups,
                    call_c_specs=self.config.call_c_specs or None,
                )
                _t("plan", _t_plan)
                # Pre-load brand-token + staff-handle maps for
                # attribute_to_brand (intent calls only). These are
                # computed once per run — pure data lookup, no API.
                brand_tokens = _brand_tokens_map(models, self.data_dir)
                staff_handles = _staff_handles_map(models, self.data_dir)
                # U7 drift detection: compare the yaml-derived
                # {term: brand_id} map (built below for the body_keyword
                # index only) to the DB-loaded map. Informational;
                # does not abort the cycle.
                _, yaml_terms_for_drift = _build_brand_index(
                    brand_tokens, models
                )
                _log_brand_search_terms_drift(
                    yaml_terms_for_drift, brand_search_terms_db
                )
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
                                "query_id": "Q1" if call.call_kind == "account" else "QX",
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
                    since_cursor: str | None = None
                    if prior_iso:
                        try:
                            prior_dt = datetime.fromisoformat(
                                prior_iso.replace("Z", "+00:00")
                            )
                            since_dt = prior_dt - timedelta(
                                hours=CURSOR_OVERLAP_HOURS
                            )
                            # TwitterAPI.io's `since:` is a YYYY-MM-DD
                            # operator. Use the date in UTC.
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
                        items = apify.run_search(
                            call.query_string,
                            max_results=s.max_results,
                            since=since_cursor,
                            max_pages=s.max_pages,
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
                                "query_id": "Q1" if call.call_kind == "account" else "QX",
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
                    index, _ = _build_brand_index(brand_tokens, models)
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
                        cfg_m = cfgs.get(m_id, RelevanceConfig())
                        kept_m, drop_stats = filter_and_review(
                            m_items, synth_q, m_id, cfg_m, review,
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
                    summary["totals"]["n_classifications_written"] += store._classifications_written
                    summary["totals"]["n_classifications_dropped"] += store._classifications_dropped
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
                            "query_id": synth_q.id,
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
                        from x_monitor.translator import (
                            AnthropicClaudeClient,
                        )
                        anthropic_client = AnthropicClaudeClient()
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

                # v1.9 (2026-06-22): quote-tweet capture. Runs after the
                # main harvest so newly-attributed posts are in the DB.
                # Skipped on dry_run / abort. See plan Units 4 & 5.
                if not dry_run and summary["status"] != "aborted":
                    qt_brand_tokens = _brand_tokens_map(models, self.data_dir)
                    # U7 hybrid: the body_keyword index is built from
                    # yaml tokens; the {term: brand_id} map for
                    # search_term attribution comes from the DB
                    # (`brand_search_terms_db`).
                    qt_index, _ = _build_brand_index(qt_brand_tokens, models)
                    qt_staff = _staff_handles_map(models, self.data_dir)
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
                store.close()

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
        """Regenerate accounts/<brand_id>.yaml-derived upserts from posts."""
        for m in self.config.enabled_models:
            try:
                seed = load_accounts(m, self.accounts_dir)
            except (FileNotFoundError, ValueError):
                continue
            # Always re-upsert seeded accounts (roles, last_seen_at).
            for a in seed:
                store.upsert_account(
                    brand_id=m,
                    handle=a.handle,
                    role=a.role,
                    source_query_ids=a.source_query_ids,
                    display_name=a.display_name,
                    verified=a.verified,
                    bio_contains_brand=a.bio_contains_brand,
                    multi_brand_voice=a.multi_brand_voice,
                    notes=a.notes,
                )
            # Discover commenters from posts and upsert them as 'community'
            # or 'unknown' role. The role_tag rules (Q5) will upgrade
            # suspicious/developer/employee on the next pass.
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
            for handle, info in commenters.items():
                if any(s.handle == handle for s in seed):
                    continue
                role = role_tag(
                    Account(handle=handle, role=info["role"]),
                    posts_for_account=info["posts"][:10],
                )
                # Count multi-thread appearances
                thread_count = sum(
                    1 for p in info["posts"] if p.get("in_reply_to_user_id")
                )
                store.upsert_account(
                    brand_id=m,
                    handle=handle,
                    role=role,
                    source_query_ids=[],
                    verified=False,
                    bio_contains_brand=False,
                    multi_brand_voice=False,
                    multiple_posts_in_thread_with_official=thread_count,
                )
                # Record appearances
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
