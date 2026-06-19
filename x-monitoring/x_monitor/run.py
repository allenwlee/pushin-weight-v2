# {{AGENT_ATTRIBUTION}}
"""Run pipeline: harvest, persist, dedupe, sentinel, lock (R16, R17, R19, R20, R22, R25)."""

from __future__ import annotations

import contextlib
import fcntl
import json
import logging
import os
import uuid
from datetime import datetime, timezone
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
# v1.8 (R15, R20): the per-tweet classification seam now uses the
# multi-brand `attribute_to_brands` from `x_monitor.attribution`.
# The legacy `classify_signal` (single-string) is kept via the
# compat shim for the `source_query_id` derivation; it emits a
# DeprecationWarning on every call, so we suppress the warning here
# (the pipeline is the one remaining legitimate user of the legacy
# path until the per-brand LLM classifier is wired in).
import warnings as _warnings
from .intent_classifier import classify_signal as _legacy_classify_signal
from .attribution import (
    UNATTRIBUTED_BRAND_ID,
    MentionRow,
    attribute_to_brands,
    compile_keyword_index,
)
from .relevance import RelevanceConfig, filter_posts, load_filter
from .review import ReviewQueue
from .store import Store
from .headlines import HeadlinesCache, enrich_posts

log = logging.getLogger(__name__)

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

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
      - Low-engagement release posts are added to the review queue with
        reason="low_engagement" (the existing R25 rule). This rule only
        runs on the KEPT set — the previous behavior iterated over the
        unfiltered `items`, which meant a filter-dropped post would
        still appear in the review queue with a tweet_id that wasn't
        in the DB. That bug is fixed here.

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
    # Low-engagement rule runs ONLY on the kept set.
    for it in kept:
        if (
            q.expected_signal == "release"
            and (it.get("like_count") or 0) < 2
        ):
            review.append_rule_match(
                tweet_id=it.get("id", ""),
                reason="low_engagement",
                brand_id=brand_id,
                rule="release_min_faves",
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
    """Map a classified signal to the legacy Q1-Q6 source_query_id.

    This preserves dashboard rendering (`signal_breakdown` keys are Q1-Q6)
    for tweets that came back from the new intent calls. Account calls
    always stamp Q1; intent calls stamp the signal-derived QID.
    """
    return {
        "release": "Q1",
        "community_question": "Q2",
        "criticism": "Q3",
        "commenter_capture": "Q4",
        "other": "Q5",
        "praise": "Q6",
    }.get(signal, "Q5")

def _planned_call_to_query(call: "PlannedCall") -> Query:
    """Synthesize a Query object for the v1.2 filter_and_review helper.

    The filter only reads .id, .min_faves, .query_string, and
    .expected_signal. Account calls get Q1/release; intent calls get
    Q5/other (the helper uses these only for logging; the per-tweet
    source_query_id is set on the tweet itself before this is called).
    """
    from .query_plan import PlannedCall  # local to avoid circular at import
    if call.call_kind == "account":
        qid, signal, min_faves = "Q1", "release", 1
    else:
        qid, signal = _signal_to_qid(call.expected_signal), call.expected_signal
        min_faves = 0
    return Query(
        id=qid,  # type: ignore[arg-type]
        query_string=call.query_string,
        expected_signal=signal,  # type: ignore[arg-type]
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
        summary: dict[str, Any] = {
            "run_id": run_id,
            "started_at": _now_iso(),
            "finished_at": None,
            "status": "running",
            "degraded": {},
            "queries": [],
            "totals": {
                "n_queries_run": 0,
                "n_results": 0,
                "n_inserted": 0,
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
                plan = plan_calls(
                    self.data_dir, models, x_monitor_list_id=self.config.x_monitor_list_id
                )
                # Pre-load brand-token + staff-handle maps for
                # attribute_to_brand (intent calls only). These are
                # computed once per run — pure data lookup, no API.
                brand_tokens = _brand_tokens_map(models, self.data_dir)
                staff_handles = _staff_handles_map(models, self.data_dir)
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

                    try:
                        items = apify.run_search(
                            call.query_string,
                            max_results=50,
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
                    if call.call_kind == "intent":
                        classified = 0
                        # Build a v1.8 detection-registry view of the
                        # per-cycle brand_tokens dict. The v1.7 yaml
                        # stores tokens under the MODEL key (e.g.
                        # {"minimax": ["Qwen", "DeepSeek"]}), but the
                        # actual brand_ids detected should be the
                        # canonical brand_ids ("qwen", "deepseek"). We
                        # map each token to its canonical brand_id by
                        # lowercasing and checking against KNOWN_MODELS;
                        # tokens that don't match a known brand are
                        # checked against an alias map (e.g. "kimi"
                        # → "moonshot_kimi") before being dropped.
                        #
                        # Fallback: if the per-model brand_tokens map
                        # is empty (yaml query strings don't have
                        # `(brand_a OR brand_b)` paren groups — legacy
                        # `'minimax'` queries, or models without a
                        # yaml), seed the keyword index with the model
                        # name itself so the self-brand is still
                        # detected via body_keyword. This matches the
                        # v1.7 contract where the model name == the
                        # brand_id.
                        # Per-model alias map: short tokens that v1.7
                        # yamls use to refer to the canonical brand_id.
                        # These tokens appear in v1.7 query OR-groups
                        # like `(kimi OR moonshot OR k2)` but don't
                        # match the canonical brand_id
                        # `moonshot_kimi` (with underscore). The alias
                        # map bridges the gap until the yamls are
                        # migrated to canonical brand_ids (v1.9).
                        _BRAND_ALIASES: dict[str, str] = {
                            "kimi": "moonshot_kimi",
                            "moonshot": "moonshot_kimi",
                            "k2": "moonshot_kimi",
                            "mimo": "xiaomi_mimo",
                            "xiaomi": "xiaomi_mimo",
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
                        keyword_triples: list[tuple[str, str, bool]] = []
                        for model_id, toks in brand_tokens.items():
                            for tok in toks:
                                canonical = tok.strip().lower()
                                if not canonical:
                                    continue
                                if canonical in KNOWN_MODELS:
                                    keyword_triples.append(
                                        (canonical, tok, False)
                                    )
                                elif canonical in _BRAND_ALIASES:
                                    keyword_triples.append(
                                        (
                                            _BRAND_ALIASES[canonical],
                                            tok,
                                            False,
                                        )
                                    )
                                # else: token doesn't map to a known
                                # brand; drop it. (v1.7 used model_id
                                # as the brand_id, but v1.8's
                                # multi-brand attribution wants the
                                # actual brand_id.)
                        # Seed self-brand detection for each enabled
                        # model that doesn't already have any tokens.
                        for m in models:
                            if m in KNOWN_MODELS and not any(
                                t[0] == m for t in keyword_triples
                            ):
                                keyword_triples.append((m, m, False))
                        index = compile_keyword_index(keyword_triples)
                        # Build brand_search_terms from the same triples
                        # so search-term matches resolve to the same
                        # canonical brand_ids.
                        brand_search_terms: dict[str, str] = {
                            tok.lower(): bid for bid, tok, _ in keyword_triples
                        }
                        for it in items:
                            # The MentionRow dataclass requires a
                            # non-empty `mentioned_at` (it stores ISO
                            # timestamps). When the post lacks a
                            # `created_at` (e.g. apify mock returns
                            # bare dicts in tests), fall back to the
                            # pipeline's "now" so the extractors can
                            # emit MentionRows. Real API responses
                            # always include `created_at`.
                            from datetime import datetime as _dt, timezone as _tz
                            _fallback_created_at = _dt.now(_tz.utc).isoformat(
                                timespec="seconds"
                            )
                            post_like = {
                                "tweet_id": it.get("id", ""),
                                "id": it.get("id", ""),
                                "text": it.get("text", ""),
                                "created_at": (
                                    it.get("created_at") or _fallback_created_at
                                ),
                                "entities": it.get("entities", {}),
                            }
                            # Per-source MentionRows via the v1.8
                            # multi-brand orchestrator. Returns
                            # `list[MentionRow]` (deduped by
                            # `(brand_id, source)`). user_mention /
                            # hashtag would require populating the
                            # detection tables, which the pipeline
                            # doesn't do (the compat path is offline);
                            # body_keyword + search_term are populated
                            # by passing the per-cycle keyword index
                            # and the empty brand_search_terms map.
                            mentions: list[MentionRow] = list(
                                attribute_to_brands(
                                    post_like,
                                    brand_accounts={},
                                    brand_hashtags={},
                                    compiled_keyword_index=index,
                                    search_query=[],
                                    brand_search_terms=brand_search_terms,
                                )
                            )
                            # brand_ids: union of non-sentinel, non-None
                            # brands from the MentionRow set.
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
                                # No brand matched: drop the tweet.
                                it["_unattributed"] = True
                                it["brand_ids"] = []
                                it["brand_id"] = UNATTRIBUTED_BRAND_ID
                                it["mentions"] = mentions
                                it["signals"] = {}
                            else:
                                # Legacy compat: brand_id is the first
                                # detected brand. The downstream
                                # `by_model` partition key uses this.
                                it["brand_id"] = brand_ids[0]
                                it["brand_ids"] = brand_ids
                                it["mentions"] = mentions
                                # signals: per-brand bucket via the
                                # legacy single-bucket classifier
                                # (no anthropic_client in this path).
                                # Emit the SAME signal for every
                                # detected brand — the per-brand
                                # decomposition is the v1.8 follow-up.
                                with _warnings.catch_warnings():
                                    _warnings.simplefilter(
                                        "ignore", DeprecationWarning,
                                    )
                                    sig = _legacy_classify_signal(
                                        it.get("text", "")
                                    )
                                it["signals"] = {b: sig for b in brand_ids}
                                classified += 1
                            # source_query_id still uses the legacy
                            # single-bucket classifier for Q1-Q6
                            # routing (no per-brand signal yet).
                            with _warnings.catch_warnings():
                                _warnings.simplefilter(
                                    "ignore", DeprecationWarning,
                                )
                                it["source_query_id"] = _signal_to_qid(
                                    _legacy_classify_signal(
                                        it.get("text", "")
                                    )
                                )
                        items = [
                            it for it in items if not it.get("_unattributed")
                        ]
                        log.info(
                            "intent call brand_id=%s bucket=%s n_results=%d "
                            "n_classified=%d",
                            call.brand_id, call.bucket, len(items) + sum(
                                1 for it in items if it.get("_unattributed")
                            ),
                            classified,
                        )
                    else:
                        for it in items:
                            it["brand_id"] = call.brand_id
                            it["brand_ids"] = [call.brand_id]
                            it["mentions"] = []
                            it["signals"] = {call.brand_id: "release"}
                            it["source_query_id"] = "Q1"

                    # The existing v1.2 filter + review-queue machinery
                    # expects a Query object (for source_query_id + min_faves).
                    # We synthesize one for the call. The Query.id is
                    # derived from the call shape:
                    #   account calls -> "Q1" (release)
                    #   intent calls  -> the signal-derived QID
                    synth_q = _planned_call_to_query(call)
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

                    log.info(
                        "call model=%s kind=%s bucket=%s n_results=%d "
                        "n_kept=%d n_dropped=%d reasons=%s n_review=%d",
                        call.brand_id, call.call_kind, call.bucket,
                        len(items), len(kept_all), n_filtered_total,
                        reasons_total, n_review_total,
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

                if summary["status"] == "aborted":
                    pass  # already handled in the inner break
            finally:
                store.close()

            # Account graph update
            self._update_accounts(store, summary)

            if summary["status"] == "running":
                summary["status"] = "completed" if not summary["degraded"] else "degraded"
            summary["finished_at"] = _now_iso()
            self._write_summary(run_id, summary)
            self._update_latest_symlink(run_id, running=False)
            return summary

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
                    engagement_tier=a.engagement_tier,
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
                    engagement_tier=("high" if info["multi_posts"] >= 5 else "low"),
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
