#!/usr/bin/env python3
"""Probe a Call C spec against the live TwitterAPI.io and report counts +
sample tweets.

Plan: docs/plans/2026-07-02-001-feat-configurable-search-limits-and-backlog-plan.md
Unit 5 of 6 (U5 — Review Call C narrow AND-filter).

The U5 question is whether the multi-brand Call C spec at
``config.yaml`` ``call_c_specs:`` returns ≥1 relevant post per cycle.
This probe answers it without running the full pipeline.

Without live credentials the script exits early with a clear message
("no API key in env"). When ``TWITTER_API_KEY`` (or ``TWITTERAPI_IO_KEY``)
is present, the script:

1. Loads ``config.yaml`` from the repo's ``x-monitoring/`` directory.
2. Builds the query string for each CallCBrandSpec via
   ``x_monitor.query_plan._build_call_c_query``.
3. Fires one ``/twitter/tweet/advanced_search`` request against the
   live API at max_results=10 (a small probe; the spec's max_results
   is a per-cycle budget, not a probe budget).
4. Prints the n_results, the first 5 tweet ids + truncated text, and
   which brand the post-fetch attribute_to_brands regex would route
   each one to (using the brand-token map).

Usage:
    scripts/probe_call_c_spec.py
    scripts/probe_call_c_spec.py --max-results 25

The script writes nothing to data/ and never touches the DB. It is
safe to run on a laptop with API access. Operators should rerun this
after any edit to the spec to confirm n_results > 0 and relevance
ratio is acceptable.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# Locate the x-monitoring package relative to this script.
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
PKG_ROOT = REPO_ROOT / "x_monitor"

# Make the package importable when running from the repo root.
sys.path.insert(0, str(REPO_ROOT))


def _have_api_creds() -> tuple[bool, str | None]:
    """Return (have_creds, key_value_or_None). The probe exits early
    if creds are absent so this script is safe to commit."""
    for env in ("TWITTER_API_KEY", "TWITTERAPI_IO_KEY"):
        v = os.environ.get(env)
        if v:
            return True, v
    return False, None


def _load_config():
    from x_monitor.config import load_config
    cfg_path = REPO_ROOT / "config.yaml"
    if not cfg_path.exists():
        sys.exit(f"config.yaml not found at {cfg_path}")
    return load_config(cfg_path)


def _build_query(spec) -> str:
    from x_monitor.query_plan import _build_call_c_query
    return _build_call_c_query(spec)


def _extract_brand(tweet_text: str, brand_tokens: dict[str, list[str]]) -> str | None:
    """Mimic the post-fetch attribute_to_brands routing for the probe's
    own diagnostic: for each brand, scan tweet text (case-insensitive)
    for any of the brand's tokens; first match wins. Returns the brand
    id or None. This is intentionally cheap — the probe is a smoke
    check, not the production attribution path."""
    if not tweet_text:
        return None
    text_lower = tweet_text.lower()
    for brand_id, toks in brand_tokens.items():
        for tok in toks:
            if tok and tok.lower() in text_lower:
                return brand_id
    return None


def _probe(spec, api_key: str, max_results: int) -> dict:
    """Fire one probe against the live API. Returns a result dict with:
       - query: the query string we built.
       - n_results: count from the API response.
       - samples: list of up to 5 {id, text, attributed_brand}.
    """
    # Imported lazily so the script can be inspected even on
    # systems without x_monitor installed.
    try:
        from x_monitor.apify import TwitterApiClient
    except ImportError as exc:
        sys.exit(f"x_monitor.apify not importable: {exc}")

    client = TwitterApiClient(api_key=api_key)
    query = _build_query(spec)
    items = client.run_search(query, max_results=max_results)

    # Build a flat brand -> tokens map from the spec for relevance
    # scoring on each sample.
    brand_tokens = spec.brands

    samples = []
    for it in items[:5]:
        text = it.get("text") or it.get("full_text") or ""
        samples.append({
            "id": it.get("id") or it.get("tweet_id") or "?",
            "text": text[:140],
            "attributed_brand": _extract_brand(text, brand_tokens),
        })

    return {
        "query": query,
        "n_results": len(items),
        "samples": samples,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-results", type=int, default=10,
        help="max_results for the probe request (default: 10)",
    )
    parser.add_argument(
        "--call-id", default=None,
        help="probe only the spec whose call_id matches; default: probe all",
    )
    args = parser.parse_args()

    have_creds, key = _have_api_creds()
    if not have_creds:
        print(
            "# probe_call_c_spec.py — no API key in $TWITTER_API_KEY or "
            "$TWITTERAPI_IO_KEY; skipping live probe.\n"
            "# Set one of these env vars and rerun to get live counts."
        )
        return 0

    cfg = _load_config()
    specs = cfg.call_c_specs or []
    if not specs:
        print("# no call_c_specs configured; nothing to probe.")
        return 0
    if args.call_id:
        specs = [s for s in specs if getattr(s, "call_id", "") == args.call_id]
        if not specs:
            sys.exit(f"no spec with call_id={args.call_id!r}")

    for i, spec in enumerate(specs):
        cid = getattr(spec, "call_id", "") or f"(spec-{i})"
        print(f"## Spec {cid}")
        try:
            r = _probe(spec, key, args.max_results)
        except Exception as exc:
            print(f"  probe failed: {exc}")
            continue
        print(f"  query:    {r['query'][:200]}"
              f"{'...' if len(r['query']) > 200 else ''}")
        print(f"  n_results: {r['n_results']}  (probe max_results={args.max_results})")
        for j, s in enumerate(r["samples"], 1):
            print(f"  sample {j}: id={s['id']!s:<22} "
                  f"attributed={s['attributed_brand']!r}")
            print(f"            text={s['text']!r}")
        n_attr = sum(1 for s in r["samples"] if s["attributed_brand"] is not None)
        print(f"  relevance: {n_attr}/{len(r['samples'])} samples matched a covered brand")
        # Hard signal: AND-filter too narrow.
        if r["n_results"] == 0:
            print("  ! n_results=0 — AND-filter is too narrow for the current API.")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())