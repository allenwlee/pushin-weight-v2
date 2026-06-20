# {{AGENT_ATTRIBUTION}}
"""Reattribute historical posts through the v1.8 call-path pipeline (Unit 5).

Walks every row in `posts` and re-runs the v1.8 multi-brand attribution
pipeline (`attribute_to_brands` + `compute_post_brands` +
`classify_signal`) on each. Writes the results to `post_brands`,
`post_mentions`, and `post_brand_signals` via the v1.8 Store methods,
which are idempotent via `ON CONFLICT DO UPDATE`.

This is the backfill path that runs after migration 004 has dropped
the `posts.brand_id` column. The migration leaves `post_brands` /
`post_mentions` / `post_brand_signals` empty (or partially filled for
posts that pre-date the v1.8 schema); `reattribute_all_posts` walks
all 2,008 historical posts and fills them in.

Design notes (R19, plan Unit 5):
  - **Idempotent**: every write uses `ON CONFLICT DO UPDATE`. Running
    the function twice on the same DB produces identical row counts.
  - **Detection tables loaded ONCE**: `compile_keyword_index` is the
    expensive call (regex compilation). We load the four detection
    tables once at the top of the function and pass them down for
    every post.
  - **LLM is optional**: `classify_signal` returns `{}` when no
    `anthropic_client` is supplied. Offline operation is the default.
  - **Per-post transaction**: we wrap each post's 3-table write in
    `store.transaction()`. A single post failing doesn't poison the
    rest of the batch.
  - **brand_filter is via JOIN**: we JOIN against post_brands to
    limit the SELECT to posts already attributed to that brand.

Public function:
  - `reattribute_all_posts(db_path, *, batch_size, dry_run, limit,
    brand_filter, anthropic_client)`: returns a counts dict.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .attribution import (
    UNATTRIBUTED_BRAND_ID,
    AnthropicClaudeClient,
    BrandRow,
    attribute_to_brands,
    classify_signal,
    compile_keyword_index,
    compute_post_brands,
)
from .store import Store


logger = logging.getLogger(__name__)


# Cap on how many posts a single call processes when `limit is None`.
# The CLI exposes --limit; this is a safety belt for accidental calls.
DEFAULT_BATCH_SIZE = 100


def _read_search_queries(store: Store) -> dict[str, list[str]]:
    """Return {query_id: keywords[]} from `search_queries`.

    `posts.source_query_id` is a soft pointer to a row in
    `search_queries.query_id` (per migration 004). The keyword list
    is stored JSON-encoded in `search_queries.keywords_json` (text).
    Returns an empty dict if the table is empty so the extractor
    falls through to "no search_term match".
    """
    try:
        rows = store._conn.execute(
            "SELECT query_id, keywords_json FROM search_queries"
        ).fetchall()
    except Exception as e:
        logger.warning(
            "reattribute: failed to read search_queries (%s); "
            "treating as empty",
            e,
        )
        return {}
    out: dict[str, list[str]] = {}
    for r in rows:
        qid = r["query_id"]
        try:
            kws = json.loads(r["keywords_json"] or "[]")
            if isinstance(kws, list):
                out[qid] = [str(k) for k in kws if k]
            else:
                out[qid] = []
        except (ValueError, TypeError):
            logger.warning(
                "reattribute: search_queries[%s].keywords_json is not "
                "valid JSON; treating as empty",
                qid,
            )
            out[qid] = []
    return out


def _normalize_post_row(row: dict[str, Any]) -> dict[str, Any]:
    """Coerce a raw `posts` row into the dict shape extractors expect.

    The `entities` column is JSON text; we decode it here so the
    extractors see a dict. The `tweet_id` field is aliased to `id`
    for callers that prefer the short key.
    """
    out = dict(row)
    entities = out.get("entities")
    if isinstance(entities, (str, bytes, bytearray)):
        if isinstance(entities, (bytes, bytearray)):
            entities = entities.decode("utf-8", errors="replace")
        try:
            out["entities"] = json.loads(entities) if entities else {}
        except (ValueError, TypeError):
            out["entities"] = {}
    elif entities is None:
        out["entities"] = {}
    if "tweet_id" in out and "id" not in out:
        out["id"] = out["tweet_id"]
    elif "id" in out and "tweet_id" not in out:
        out["tweet_id"] = out["id"]
    return out


def _select_posts(
    store: Store,
    *,
    limit: int | None,
    brand_filter: str | None,
) -> list[dict[str, Any]]:
    """Read the posts we'll reattribute.

    When `brand_filter` is None, this is a straight SELECT on `posts`
    (ordered by `tweet_id` for stable runs). When `brand_filter` is
    set, we do an INNER JOIN against `post_brands` to filter — this
    is the per-model view the dashboard uses.
    """
    if brand_filter is None:
        sql = "SELECT * FROM posts ORDER BY tweet_id"
        params: tuple[Any, ...] = ()
    else:
        sql = (
            "SELECT p.* FROM posts p "
            "JOIN post_brands pb ON pb.post_id = p.tweet_id "
            "WHERE pb.brand_id = ? "
            "ORDER BY p.tweet_id"
        )
        params = (brand_filter,)
    if limit is not None:
        sql = sql + " LIMIT ?"
        params = params + (int(limit),)
    rows = store._conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def reattribute_all_posts(
    db_path: Path,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    dry_run: bool = False,
    limit: int | None = None,
    brand_filter: str | None = None,
    anthropic_client: Any = None,
) -> dict[str, int]:
    """Re-run attribution on every post in `db_path`.

    Args:
        db_path:         path to `x_monitoring.db`. The Store opens
                         this with `auto_migrate=True` so a 003-state
                         DB will be auto-promoted to 004 before the
                         read. Idempotent on an already-004 DB.
        batch_size:      number of posts per progress-log chunk.
                         The underlying query is one-shot (no
                         streaming); this only affects logging.
        dry_run:         when True, no DB writes happen — the counts
                         still reflect what would have been written.
        limit:           optional cap on posts processed.
        brand_filter:    optional brand_id; only reattribute posts
                         currently attributed to this brand (joined
                         via post_brands).
        anthropic_client: optional `AnthropicClaudeClient` instance.
                          When None, no signal classification happens
                          (default for offline / dry-run operation).

    Returns:
        Counts dict with keys:
          - posts_scanned
          - post_brands_written
          - post_mentions_written
          - post_brand_signals_written
          - errors
    """
    counts: dict[str, int] = {
        "posts_scanned": 0,
        "post_brands_written": 0,
        "post_mentions_written": 0,
        "post_brand_signals_written": 0,
        "errors": 0,
    }

    db_path = Path(db_path)
    store = Store(db_path, auto_migrate=True)
    try:
        # Load detection tables ONCE (R19: amortize regex compile).
        brand_accounts = store.read_brand_accounts()
        brand_hashtags = store.read_brand_hashtags()
        brand_keywords_raw = store.read_brand_keywords()
        brand_search_terms = store.read_brand_search_terms()
        search_queries = _read_search_queries(store)
        brand_registry = store.read_brands()

        compiled_keyword_index = compile_keyword_index(brand_keywords_raw)
        logger.info(
            "reattribute: loaded detection tables: "
            "accounts=%d hashtags=%d keywords=%d search_terms=%d "
            "search_queries=%d brands=%d",
            len(brand_accounts),
            len(brand_hashtags),
            len(brand_keywords_raw),
            len(brand_search_terms),
            len(search_queries),
            len(brand_registry),
        )

        posts = _select_posts(
            store,
            limit=limit,
            brand_filter=brand_filter,
        )
        logger.info(
            "reattribute: selected %d posts (limit=%s brand_filter=%s)",
            len(posts),
            limit,
            brand_filter,
        )

        n_posts = len(posts)
        i = 0
        while i < n_posts:
            batch = posts[i:i + batch_size]
            for post in batch:
                counts["posts_scanned"] += 1
                normalized = _normalize_post_row(post)
                source_query_id = normalized.get("source_query_id")
                search_query = search_queries.get(source_query_id or "", [])

                # 1+2. Extract + consolidate.
                try:
                    mentions = attribute_to_brands(
                        normalized,
                        brand_accounts=brand_accounts,
                        brand_hashtags=brand_hashtags,
                        compiled_keyword_index=compiled_keyword_index,
                        search_query=search_query,
                        brand_search_terms=brand_search_terms,
                    )
                    post_brands = compute_post_brands(normalized, mentions)
                except Exception as e:
                    logger.warning(
                        "reattribute: post %s raised during "
                        "extraction: %s",
                        normalized.get("tweet_id"),
                        e,
                    )
                    counts["errors"] += 1
                    continue

                # 3. Per-brand signal classification (optional).
                brand_ids_for_signal = [
                    b for b, _w in post_brands if b != UNATTRIBUTED_BRAND_ID
                ]
                signals = classify_signal(
                    text=normalized.get("text") or "",
                    brand_ids=brand_ids_for_signal,
                    brand_registry=brand_registry,
                    anthropic_client=anthropic_client,
                )

                n_post_brands = len(post_brands)
                n_mentions = len(mentions)
                n_signals = len(signals)

                if dry_run:
                    counts["post_brands_written"] += n_post_brands
                    counts["post_mentions_written"] += n_mentions
                    counts["post_brand_signals_written"] += n_signals
                    continue

                # Real write path. Each post in its own transaction
                # so a single failure doesn't poison the batch.
                post_id = str(
                    normalized.get("tweet_id")
                    or normalized.get("id")
                    or ""
                )
                if not post_id:
                    logger.warning(
                        "reattribute: post without tweet_id; skipping"
                    )
                    counts["errors"] += 1
                    continue

                try:
                    with store.transaction():
                        for brand_id, weight in post_brands:
                            store.insert_post_brands(
                                post_id=post_id,
                                brand_id=brand_id,
                                weight=weight,
                            )
                        for m in mentions:
                            store.insert_post_mentions(
                                post_id=post_id,
                                brand_id=m.brand_id,
                                source=m.source,
                                raw_token=m.raw_token,
                                mentioned_at=m.mentioned_at,
                            )
                        for brand_id, signal in signals.items():
                            if brand_id == UNATTRIBUTED_BRAND_ID:
                                continue
                            store.insert_post_brand_signals(
                                post_id=post_id,
                                brand_id=brand_id,
                                signal=signal,
                            )
                    counts["post_brands_written"] += n_post_brands
                    counts["post_mentions_written"] += n_mentions
                    counts["post_brand_signals_written"] += n_signals
                except Exception as e:
                    logger.warning(
                        "reattribute: post %s failed to write: %s",
                        post_id,
                        e,
                    )
                    counts["errors"] += 1

            i += len(batch)
            if n_posts == 0 or i % (batch_size * 5) == 0 or i == n_posts:
                logger.info(
                    "reattribute: progress %d/%d posts",
                    i,
                    n_posts,
                )

        logger.info("reattribute: complete %s", counts)
        return counts
    finally:
        store.close()


__all__ = [
    "DEFAULT_BATCH_SIZE",
    "reattribute_all_posts",
]


def build_anthropic_client_from_env() -> AnthropicClaudeClient | None:
    """Return an `AnthropicClaudeClient` honoring the operator's proxy config.

    Resolution:
      * If ANTHROPIC_BASE_URL contains "minimax.io", the operator is
        routing through the minimax proxy. The proxy accepts only
        MINIMAX_API_TOKEN (the `sk-cp-uh…` token from `~/.env.secrets`)
        and the operator-registered model id (ANTHROPIC_MODEL, typically
        "MiniMax-M2.7"). ANTHROPIC_API_KEY is silently rejected (401).
      * Otherwise, talk to api.anthropic.com directly using
        ANTHROPIC_API_KEY (the `sk-ant-api…` key from `~/.env.secrets`).

    Used by the CLI subcommand. Returns None when no auth credential is
    available so the reattribute falls back to non-LLM mode. The
    Anthropic SDK import is deferred to the call site to keep
    `x_monitor.reattribute` importable in environments without the
    SDK (e.g. the test env, which has no anthropic installed).
    """
    import os
    base_url = os.environ.get("ANTHROPIC_BASE_URL")
    use_minimax_proxy = bool(base_url) and "minimax.io" in base_url

    if use_minimax_proxy:
        api_key = os.environ.get("MINIMAX_API_TOKEN")
        if not api_key:
            logger.warning(
                "reattribute: ANTHROPIC_BASE_URL routes through the minimax "
                "proxy but MINIMAX_API_TOKEN is not set; running without "
                "signal classification"
            )
            return None
    else:
        api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get(
            "ANTHROPIC_KEY"
        )
        if not api_key:
            return None

    try:
        return AnthropicClaudeClient(api_key=api_key, base_url=base_url)
    except ImportError:
        logger.warning(
            "reattribute: anthropic SDK not installed; "
            "running without signal classification"
        )
        return None
    except Exception as e:
        logger.warning(
            "reattribute: failed to construct AnthropicClaudeClient: %s; "
            "running without signal classification",
            e,
        )
        return None
