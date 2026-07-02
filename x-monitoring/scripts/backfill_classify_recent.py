#!/usr/bin/env python3
"""Quick backfill: classify the N most recent unclassified posts.

Wires the real ``classify_post`` against the real DB. Walks the
``posts`` table for posts that have no row in ``posts_brands_signals``
yet, calls ``classify_post`` on each with their attributed brand slugs,
then writes the result via ``Store.insert_posts_brands_signals``.

This is the same call shape the live pipeline would make if it weren't
passing ``brand_registry=None, anthropic_client=None`` — so a green run
here is the strongest signal we can get without flipping the pipeline
wiring.

Usage:
    scripts/backfill_classify_recent.py [--limit 50]
    scripts/backfill_classify_recent.py --dry-run       # no LLM calls
    scripts/backfill_classify_recent.py --out FILE.json
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from x_monitor.attribution import (  # noqa: E402
    AnthropicClaudeClient,
    BrandRow,
    classify_post,
)
from x_monitor.config import load_config  # noqa: E402
from x_monitor.store import Store  # noqa: E402


def _load_unclassified(
    db_path: Path,
    limit: int,
) -> list[dict]:
    """Load the N most recent posts that have no row in
    ``posts_brands_signals`` and at least one non-sentinel attributed
    brand. Each row carries the post text and the brand slugs it was
    attributed to (deduped per post)."""
    q = """
        SELECT
            p.id          AS post_rowid,
            p.tweet_id    AS tweet_id,
            substr(p.text, 1, 240) AS text_preview,
            p.text        AS text,
            p.created_at  AS created_at,
            GROUP_CONCAT(b.nickname) AS brand_slugs_csv
        FROM posts p
        JOIN posts_brands pb ON pb.post_id = p.id
        JOIN brands b ON b.id = pb.brand_id
        WHERE b.is_sentinel = 0
          AND p.id NOT IN (
              SELECT DISTINCT post_id FROM posts_brands_signals WHERE post_id IS NOT NULL
          )
          AND length(p.text) > 0
        GROUP BY p.id
        ORDER BY p.created_at DESC
        LIMIT ?
    """
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    rows = con.execute(q, (limit,)).fetchall()
    out: list[dict] = []
    for r in rows:
        slugs = [s for s in r["brand_slugs_csv"].split(",") if s]
        out.append({
            "post_rowid": r["post_rowid"],
            "tweet_id": r["tweet_id"],
            "text": r["text"],
            "text_preview": r["text_preview"],
            "created_at": r["created_at"],
            "brand_slugs": slugs,
        })
    con.close()
    return out


def _build_registry(store: Store) -> list[BrandRow]:
    """Use the live brand table as the registry so R8 hallucination
    drops match what the production path will see."""
    return list(store.read_brands())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=50,
                        help="how many recent unclassified posts to backfill")
    parser.add_argument("--db", default="data/x_monitoring.db",
                        help="path to the SQLite DB")
    parser.add_argument("--out", help="also persist results JSON to this path")
    parser.add_argument("--dry-run", action="store_true",
                        help="skip the LLM call; show what would be classified")
    args = parser.parse_args()

    db_path = Path(args.db)
    cfg = load_config(Path("config.yaml"))
    store = Store(db_path)

    rows = _load_unclassified(db_path, args.limit)
    print(f"# loaded {len(rows)} unclassified posts (most recent first)")
    for i, r in enumerate(rows, 1):
        slugs_str = ",".join(r["brand_slugs"])
        preview = r["text_preview"].replace("\n", " ")
        print(f"  [{i:2d}] {r['created_at']}  {slugs_str:<28}  \"{preview[:80]}\"")
    print()

    if args.dry_run or not rows:
        print("# dry-run; no LLM calls made")
        return 0

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY not in env", file=sys.stderr)
        return 1

    base_url = os.environ.get("ANTHROPIC_BASE_URL") or None
    client = AnthropicClaudeClient(api_key=api_key, base_url=base_url)
    registry = _build_registry(store)

    print(f"# model: {os.environ.get('ANTHROPIC_MODEL', '(auto)')}  "
          f"base_url: {base_url or '(anthropic default)'}  "
          f"registry_brands: {len(registry)}")
    print()

    results: list[dict] = []
    n_inserted = 0
    n_skipped_llm_empty = 0
    n_skipped_unresolvable_brand = 0

    def _count_pbs() -> int:
        return store._conn.execute(
            "SELECT COUNT(*) FROM posts_brands_signals"
        ).fetchone()[0]

    rows_before = _count_pbs()

    for i, r in enumerate(rows, 1):
        t0 = time.monotonic()
        out = classify_post(
            text=r["text"],
            brand_ids=r["brand_slugs"],
            brand_registry=registry,
            anthropic_client=client,
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        classifications = []
        for slug in r["brand_slugs"]:
            if slug in out:
                pt, sent = out[slug]
                # Store.insert_posts_brands_signals expects post_id as
                # the tweet_id TEXT (uniqued on posts.tweet_id), not the
                # posts.id INTEGER rowid. The resolver is _tweet_int_id.
                # Track inserts via SQL row count, not the Store's
                # in-process counter (which only increments inside
                # insert_posts, not in this public upsert path).
                before = _count_pbs()
                store.insert_posts_brands_signals(
                    post_id=r["tweet_id"],
                    brand_id=slug,
                    post_type=pt,
                    sentiment=sent,
                )
                delta = _count_pbs() - before
                if delta > 0:
                    n_inserted += 1
                else:
                    # Brand not in DB or sentinel — see Store guard.
                    n_skipped_unresolvable_brand += 1
                classifications.append({"brand": slug, "post_type": pt, "sentiment": sent})
            else:
                n_skipped_llm_empty += 1
                classifications.append({"brand": slug, "post_type": None, "sentiment": None,
                                        "reason": "llm_omitted"})

        preview = r["text_preview"].replace("\n", " ")
        cls_short = "; ".join(
            f"{c['brand']}={c['post_type']}/{c['sentiment']}"
            if c.get("post_type") else f"{c['brand']}=none"
            for c in classifications
        )
        print(
            f"  [{i:2d}] {r['tweet_id']}  dur={elapsed_ms:>5d}ms  "
            f"\"{preview[:70]}\""
        )
        print(f"        -> {cls_short}")

        results.append({
            "tweet_id": r["tweet_id"],
            "post_rowid": r["post_rowid"],
            "created_at": r["created_at"],
            "text_preview": r["text_preview"],
            "brand_slugs": r["brand_slugs"],
            "classifications": classifications,
            "duration_ms": elapsed_ms,
        })

    rows_after = _count_pbs()
    store.close()
    print()
    print(f"# inserted: {n_inserted}  "
          f"skipped (llm omitted brand): {n_skipped_llm_empty}  "
          f"skipped (brand unresolvable): {n_skipped_unresolvable_brand}  "
          f"pbs_rows: {rows_before} -> {rows_after} (+{rows_after - rows_before})")

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps({
            "model": os.environ.get("ANTHROPIC_MODEL"),
            "base_url": base_url,
            "n_posts_attempted": len(rows),
            "n_classifications_inserted": n_inserted,
            "pbs_row_count_before": rows_before,
            "pbs_row_count_after": rows_after,
            "results": results,
        }, indent=2, ensure_ascii=False))
        print(f"# wrote {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
