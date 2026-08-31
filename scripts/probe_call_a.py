"""Probe just Call A against TwitterAPI.io.

Bypasses RunPipeline.execute() and calls apify.run_search directly
with the Call A query string. Used to measure how many posts the
curated-handles list returns at a given min_faves floor.

Usage:
  python3.14 -m scripts.probe_call_a [--min-faves N] [--max-pages N]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PKG_ROOT))


def main() -> int:
    p = argparse.ArgumentParser(description="Probe Call A's fetch yield")
    p.add_argument("--list-id", type=int, default=2067062923525275922,
                   help="X list ID for the curated handles (default: 2067062923525275922)")
    p.add_argument("--min-faves", type=int, default=0,
                   help="min_faves floor for the query (default: 0)")
    p.add_argument("--max-pages", type=int, default=5,
                   help="Pagination cap (default: 5 = ~100 posts max)")
    p.add_argument("--since", default="2026-07-13",
                   help="since: cursor (default: 2026-07-13)")
    args = p.parse_args()

    # Build the Call A query exactly as _build_query would render it.
    query = f"(list:{args.list_id}) min_faves:{args.min_faves} since:{args.since}"
    print(f"query: {query}", file=sys.stderr)
    print(f"max_pages: {args.max_pages}", file=sys.stderr)

    from x_monitor.apify import TwitterApiClient
    from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose

    api = TwitterApiClient.from_env(TwitterApiCredentialPurpose.ON_DEMAND)
    items = api.run_search(
        query,
        max_results=20 * args.max_pages,
        max_pages=args.max_pages,
        max_per_page=20,
    )

    summary = {
        "query": query,
        "n_results": len(items),
        "tweet_ids": [t.get("tweet_id") for t in items[:25]],
        "first_5": [
            {
                "tweet_id": t.get("tweet_id"),
                "author_handle": t.get("author_handle"),
                "lang": t.get("lang"),
                "like_count": t.get("like_count"),
                "text_snippet": (t.get("text") or "")[:80],
            }
            for t in items[:5]
        ],
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
