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
from .config import Config
from .queries import Query, estimated_cost, load_queries
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
    model_id: str,
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
    `author_handle`, `favorite_count`, `model_id`, `source_query_id`).

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
            model_id=model_id,
            rule="must_have_none",
        )
    # Low-engagement rule runs ONLY on the kept set.
    for it in kept:
        if (
            q.expected_signal == "release"
            and (it.get("favorite_count") or 0) < 2
        ):
            review.append_rule_match(
                tweet_id=it.get("id", ""),
                reason="low_engagement",
                model_id=model_id,
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
                            "model_id": m,
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
                for m, qs in adjusted.items():
                    if query_filter:
                        qs = [q for q in qs if q.id in query_filter]
                    cfg = cfgs.get(m, RelevanceConfig())
                    for q in qs:
                        if not q.enabled:
                            continue
                        if dry_run:
                            summary["queries"].append(
                                {
                                    "model_id": m,
                                    "query_id": q.id,
                                    "status": "dry_run",
                                    "n_results": 0,
                                }
                            )
                            continue

                        raw_path = self.raw_dir / run_id / f"{m}_{q.id}.json"
                        raw_path.parent.mkdir(parents=True, exist_ok=True)

                        # Single attempt; retry inside TwitterApiClient handles
                        # 429/5xx. Auth failures abort the run.
                        try:
                            items = apify.run_search(
                                q.query_string,
                                max_results=q.max_results,
                            )
                        except TwitterApiAuthError as e:
                            summary["degraded"]["twitterapi_auth"] = str(e)
                            summary["status"] = "aborted"
                            break
                        except (TwitterApiRateLimitError, TwitterApiServerError) as e:
                            summary["queries"].append(
                                {
                                    "model_id": m,
                                    "query_id": q.id,
                                    "status": "error",
                                    "error": str(e),
                                    "n_results": 0,
                                }
                            )
                            continue

                        # Stamp model_id on each item BEFORE the filter pass
                        # (the filter needs model_id for the review-queue
                        # side effect).
                        for it in items:
                            it["model_id"] = m
                            it["source_query_id"] = q.id

                        # v1.2: apply per-model relevance filter. The helper
                        # also routes banned-token soft-drops and the
                        # low-engagement rule to the review queue. Critical:
                        # the rule iterates over the KEPT set, not `items`,
                        # so a filter-dropped post never lands in the review
                        # queue with a tweet_id that isn't in the DB.
                        kept, drop_stats = filter_and_review(
                            items, q, m, cfg, review,
                            cache=cache, api=apify,
                            run_fetches_used=run_fetches_used,
                        )

                        # Persist raw of the KEPT set (not the raw search
                        # response) so data/runs/raw/ reflects what we
                        # actually inserted. Drop counts are in the
                        # per-query summary entry, so nothing is lost.
                        raw_path.write_text(
                            json.dumps(kept, ensure_ascii=False, default=str),
                            encoding="utf-8",
                        )
                        n_inserted = store.insert_posts(kept)

                        log.info(
                            "model=%s query=%s n_results=%d n_kept=%d "
                            "n_dropped=%d reasons=%s n_review=%d",
                            m, q.id, len(items), drop_stats["n_kept"],
                            drop_stats["n_dropped"], drop_stats["reasons"],
                            drop_stats["n_soft_dropped"],
                        )

                        summary["queries"].append(
                            {
                                "model_id": m,
                                "query_id": q.id,
                                "status": "completed",
                                "n_results": len(items),
                                "n_kept": drop_stats["n_kept"],
                                "n_filtered": drop_stats["n_dropped"],
                                "filter_reasons": drop_stats["reasons"],
                                "n_review_added": drop_stats["n_soft_dropped"],
                                "n_inserted": n_inserted,
                                "n_url_only": drop_stats.get("n_url_only", 0),
                                "n_headlines_fetched": drop_stats.get("n_fetched", 0),
                                "n_headlines_cached": drop_stats.get("n_cached", 0),
                                "n_via_api": drop_stats.get("n_via_api", 0),
                                "raw_path": str(raw_path.relative_to(self.data_dir)),
                            }
                        )
                        summary["totals"]["n_queries_run"] += 1
                        summary["totals"]["n_results"] += len(items)
                        summary["totals"]["n_inserted"] += n_inserted

                    if summary["status"] == "aborted":
                        break
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
        """Regenerate accounts/<model_id>.yaml-derived upserts from posts."""
        for m in self.config.enabled_models:
            try:
                seed = load_accounts(m, self.accounts_dir)
            except (FileNotFoundError, ValueError):
                continue
            # Always re-upsert seeded accounts (roles, last_seen_at).
            for a in seed:
                store.upsert_account(
                    model_id=m,
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
                    model_id=m,
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
