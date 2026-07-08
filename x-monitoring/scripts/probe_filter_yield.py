#!/usr/bin/env python3
# {{AGENT_ATTRIBUTION}}
"""Per-call filter-yield ramp probe for x-monitor.

Plan: docs/plans/2026-07-08-004-feat-filter-yield-ramp-probe-plan.md

For each advanced_search call the production pipeline emits (Call A,
B1, B2, B3, C1) and each ramp level (default 50, 100, 150, 200), the
probe fires one live `advanced_search` request and records:

  n_results             — TwitterAPI.io n_results
  n_kept_after_filter   — kept-set size after the keyword-detector
                          regex (what production would actually persist)
  wall_clock_ms         — HTTP round-trip
  cost_estimate_usd     — n_results * $0.00015
  t_newest, t_oldest    — first / last created_at in the response
  n_within_15min        — count of tweets in the last 15 minutes
  extrapolated_n_in_15min — linear-density extrapolation when capped
  extrapolation_confidence — high / medium / low
  sample_tweet_ids      — first 3 IDs (relevance spot-check)

Output: a single CSV file. Per-call summary also printed to stdout.

Usage:
    scripts/probe_filter_yield.py --dry-run
    TWITTERAPI_IO_KEY=... scripts/probe_filter_yield.py \\
        --max-results 50,100,150,200 \\
        --output /tmp/filter_yield_$(date -u +%Y%m%dT%H%M%SZ).csv
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Make the package importable when run as a module from the repo root.
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(REPO_ROOT))

# TwitterAPI.io published rate: $0.15 per 1k tweets returned.
TWITTERAPI_USD_PER_TWEET = 0.15 / 1000.0

# TwitterAPI.io's per-call ceiling for advanced_search (100/page x 10 pages).
DEFAULT_HARD_MAX = 1000

# Default ramp levels — chosen to cover the current 50 cap, the v1.7
# reference of 200, and one intermediate step at 100.
DEFAULT_RAMP = "50,100,150,200"

# Default budget cap in USD. Worst case (5 calls x 4 levels all clamped
# to hard_max=1000): 5 * (50+100+150+1000) * $0.00015 = $0.975, well below
# the cap. The cap is a safety belt for accidental bad inputs.
DEFAULT_BUDGET_CAP_USD = 1.50

# Per-request HTTP timeout.
HTTP_TIMEOUT_SECONDS = 30.0

# Retry policy for 429 / 5xx: 2 retries with short backoff.
MAX_RETRIES = 2
BACKOFF_SECONDS = (0.5, 1.0)

# Per-call summary output cap (only the highest ramp level is summarized).
SUMMARY_RAMP_LEVEL = 200

# Window for the "did we catch the whole burst" diagnostic.
WINDOW_MINUTES = 15


# --- helpers --------------------------------------------------------------


def _have_api_creds() -> tuple[bool, str | None]:
    for env in ("TWITTER_API_KEY", "TWITTERAPI_IO_KEY"):
        v = os.environ.get(env)
        if v:
            return True, v
    return False, None


def _load_config() -> Any:
    from x_monitor.config import load_config
    cfg_path = REPO_ROOT / "config.yaml"
    if not cfg_path.exists():
        sys.exit(f"config.yaml not found at {cfg_path}")
    return load_config(cfg_path)


def _parse_ramp(arg: str) -> list[int]:
    parts = [p.strip() for p in arg.split(",") if p.strip()]
    if not parts:
        sys.exit("error: --max-results is empty")
    out: list[int] = []
    for p in parts:
        try:
            n = int(p)
        except ValueError:
            sys.exit(f"error: --max-results contains non-integer value: {p!r}")
        if n <= 0:
            sys.exit(f"error: --max-results values must be positive; got {n}")
        out.append(n)
    return out


def _clamp_ramp(ramp: list[int], hard_max: int) -> list[int]:
    """Apply per-level hard-max clamping. Logs a warning when the
    clamp fires (the case this defends against: someone types
    --max-results 1000000)."""
    clamped: list[int] = []
    for n in ramp:
        if n > hard_max:
            print(
                f"probe_filter_yield: ramp level {n} -> {hard_max} (hard-max)",
                file=sys.stderr,
            )
            clamped.append(hard_max)
        else:
            clamped.append(n)
    return clamped


def _projected_cost_usd(
    ramp: list[int], n_calls: int, hard_max: int
) -> float:
    """Worst-case projected cost: assume every call returns `min(level,
    hard_max)` tweets (the API ceiling). Defends against a config with
    too many ramp levels or too many calls."""
    clamped = _clamp_ramp(ramp, hard_max)
    total_tweets = sum(clamped) * n_calls
    return total_tweets * TWITTERAPI_USD_PER_TWEET


# --- timestamp + extrapolation -------------------------------------------


def _parse_iso(ts: str | None) -> datetime | None:
    """Parse TwitterAPI.io's created_at into a tz-aware datetime. The
    API uses 'Mon Jul 08 14:23:01 +0000 2026' or '2026-07-08T14:23:01Z'
    — both are common. Returns None on parse failure."""
    if not ts:
        return None
    for fmt in (
        "%a %b %d %H:%M:%S %z %Y",  # TwitterAPI.io default
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
    ):
        try:
            return datetime.strptime(ts, fmt)
        except ValueError:
            continue
    return None


def _tweet_timestamps(items: list[dict]) -> list[datetime]:
    """Extract parsed timestamps from a list of tweet dicts. Items
    with missing or unparseable created_at are silently dropped."""
    out: list[datetime] = []
    for it in items:
        ts = it.get("created_at") or it.get("createdAt")
        dt = _parse_iso(ts) if isinstance(ts, str) else None
        if dt is not None:
            out.append(dt)
    return out


def _analyze_timestamps(
    items: list[dict],
    max_results: int,
) -> dict[str, Any]:
    """Compute t_newest, t_oldest, n_within_15min, and (if capped)
    the linear-density extrapolation. Items is the raw response from
    `client.run_search`."""
    parsed = _tweet_timestamps(items)
    if not parsed:
        return {
            "t_newest": None,
            "t_oldest": None,
            "n_within_15min": 0,
            "extrapolated_n_in_15min": None,
            "extrapolation_confidence": "high",
        }
    t_newest = max(parsed)
    t_oldest = min(parsed)
    window = timezone.utc.utcoffset(None)  # tz-aware comparison anchor
    # Use a 15-minute window measured from the newest returned tweet.
    cutoff = t_newest.timestamp() - WINDOW_MINUTES * 60
    n_within_15min = sum(1 for t in parsed if t.timestamp() >= cutoff)

    n_results = len(items)

    # Linear extrapolation only fires when we hit the cap AND there
    # are within-window observations to anchor the density on.
    extrapolated: float | None = None
    confidence = "high"
    if n_within_15min < n_results and n_within_15min > 0:
        oldest_in_window = min(
            (t for t in parsed if t.timestamp() >= cutoff),
            default=None,
        )
        if oldest_in_window is not None and oldest_in_window != t_newest:
            span_seconds = (t_newest - oldest_in_window).total_seconds()
            if span_seconds > 0:
                density = n_within_15min / (span_seconds / 60.0)  # tweets/min
                extrapolated = density * WINDOW_MINUTES
                # Confidence: medium if extrapolation is < 2x observed,
                # low if > 2x. The 2x cutoff is heuristic; bursts can
                # legitimately exceed it.
                ratio = extrapolated / max(n_within_15min, 1)
                if ratio <= 2.0:
                    confidence = "medium"
                else:
                    confidence = "low"

    return {
        "t_newest": t_newest.isoformat(),
        "t_oldest": t_oldest.isoformat(),
        "n_within_15min": n_within_15min,
        "extrapolated_n_in_15min": (
            round(extrapolated) if extrapolated is not None else None
        ),
        "extrapolation_confidence": confidence,
    }


# --- per-call firing -----------------------------------------------------


def _fire_one_call(
    client: Any,
    call: Any,
    max_results: int,
) -> dict[str, Any]:
    """Fire one advanced_search request. Returns a per-row result dict
    suitable for the CSV. All numeric fields may be `None` on failure."""
    t0 = time.monotonic()
    items: list[dict] = []
    error: str | None = None
    last_exc: Exception | None = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            items = client.run_search(
                call.query_string, max_results=max_results,
            )
            error = None
            break
        except Exception as exc:
            last_exc = exc
            error = exc.__class__.__name__
            # No retry on the last attempt.
            if attempt < MAX_RETRIES:
                time.sleep(BACKOFF_SECONDS[attempt])
            else:
                items = []

    wall_clock_ms = int((time.monotonic() - t0) * 1000)

    if not items:
        # Failure path: emit null fields, continue to next call.
        return {
            "n_results": None,
            "n_kept_after_filter": None,
            "wall_clock_ms": wall_clock_ms,
            "cost_estimate_usd": None,
            "t_newest": None,
            "t_oldest": None,
            "n_within_15min": 0,
            "extrapolated_n_in_15min": None,
            "extrapolation_confidence": "high",
            "sample_tweet_ids": "",
            "error": error or "unknown",
        }

    # Kept-set: tweets where the keyword-detector regex matches a
    # brand token. Mirrors the production attribute_to_brands path.
    n_kept = _kept_after_filter(items)
    n_results = len(items)
    cost = round(n_results * TWITTERAPI_USD_PER_TWEET, 6)
    ts_analysis = _analyze_timestamps(items, max_results)

    sample_ids = ",".join(
        str(it.get("id") or it.get("tweet_id") or "?")
        for it in items[:3]
    )

    return {
        "n_results": n_results,
        "n_kept_after_filter": n_kept,
        "wall_clock_ms": wall_clock_ms,
        "cost_estimate_usd": cost,
        **ts_analysis,
        "sample_tweet_ids": sample_ids,
        "error": "",
    }


def _kept_after_filter(items: list[dict]) -> int:
    """Count tweets whose text contains at least one monitored brand
    token. Reads the keyword index from the live DB via a Store
    instance — the same index production uses."""
    from x_monitor.store import Store
    from x_monitor.attribution import compile_keyword_index, detect_brand_mentions

    db_path = REPO_ROOT / "data" / "x_monitoring.db"
    if not db_path.exists():
        # No DB available — fall back to a permissive count (assume all
        # tweets are "kept"). The operator can re-run once the DB is
        # back. This matches the smoketest's pre-DB mode.
        return len(items)

    store = Store(db_path, auto_migrate=False)
    try:
        brand_keywords = store.read_brand_keywords()
    finally:
        store.close()
    compiled_index = compile_keyword_index(brand_keywords)

    kept = 0
    for it in items:
        text = it.get("text") or it.get("full_text") or ""
        mentions = detect_brand_mentions(text, compiled_index)
        if mentions:
            kept += 1
    return kept


# --- CSV output ----------------------------------------------------------


CSV_HEADER = [
    "call_id",
    "max_results",
    "n_results",
    "n_kept_after_filter",
    "wall_clock_ms",
    "cost_estimate_usd",
    "t_newest",
    "t_oldest",
    "n_within_15min",
    "extrapolated_n_in_15min",
    "extrapolation_confidence",
    "sample_tweet_ids",
    "error",
]


def _row_for_csv(call_id: str, max_results: int, result: dict[str, Any]) -> list:
    """Build a CSV row in the order of CSV_HEADER."""
    return [
        call_id,
        max_results,
        result.get("n_results"),
        result.get("n_kept_after_filter"),
        result.get("wall_clock_ms"),
        result.get("cost_estimate_usd"),
        result.get("t_newest"),
        result.get("t_oldest"),
        result.get("n_within_15min"),
        result.get("extrapolated_n_in_15min"),
        result.get("extrapolation_confidence"),
        result.get("sample_tweet_ids"),
        result.get("error", ""),
    ]


def _print_summary(rows: list[dict]) -> None:
    """Print a per-call summary at the SUMMARY_RAMP_LEVEL."""
    summary_rows = [r for r in rows if r["max_results"] == SUMMARY_RAMP_LEVEL]
    if not summary_rows:
        return
    print("")
    print(f"=== Per-call yield (max_results={SUMMARY_RAMP_LEVEL}) ===")
    for r in summary_rows:
        cid = r["call_id"]
        nr = r.get("n_results")
        kept = r.get("n_kept_after_filter")
        cost = r.get("cost_estimate_usd") or 0.0
        n15 = r.get("n_within_15min")
        ext = r.get("extrapolated_n_in_15min")
        conf = r.get("extrapolation_confidence", "high")
        nr_str = f"{nr}" if nr is not None else "n/a"
        kept_str = f"{kept}" if kept is not None else "n/a"
        ext_str = (
            f"  ext_15min={ext} ({conf})" if ext is not None else ""
        )
        print(
            f"  {cid:3s}: n_results={nr_str:>4s}  kept={kept_str:>4s}  "
            f"n_within_15min={n15:>4s}  cost=${cost:.4f}{ext_str}"
        )


# --- main ----------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-results", type=str, default=DEFAULT_RAMP,
        help=f"comma-separated ramp levels (default: {DEFAULT_RAMP})",
    )
    parser.add_argument(
        "--hard-max", type=int, default=DEFAULT_HARD_MAX,
        help=f"per-call ceiling; ramp levels above this are clamped "
             f"(default: {DEFAULT_HARD_MAX})",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="emit planned call set without firing HTTP",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="CSV output path (default: /tmp/filter_yield_<UTC>.csv)",
    )
    parser.add_argument(
        "--budget-cap", type=float, default=DEFAULT_BUDGET_CAP_USD,
        help=f"refuse runs whose projected cost exceeds this USD figure "
             f"(default: {DEFAULT_BUDGET_CAP_USD})",
    )
    args = parser.parse_args()

    ramp = _parse_ramp(args.max_results)
    hard_max = args.hard_max
    if hard_max <= 0:
        sys.exit(f"error: --hard-max must be positive; got {hard_max}")

    cfg = _load_config()
    from x_monitor.query_plan import plan_calls

    calls = plan_calls(
        data_dir=REPO_ROOT / "data",
        enabled_models=cfg.enabled_models,
        x_monitor_list_id=cfg.x_monitor_list_id,
        call_c_specs=cfg.call_c_specs,
        call_b_groups=cfg.call_b_groups,
    )

    n_calls = len(calls)
    projected = _projected_cost_usd(ramp, n_calls, hard_max)
    if projected > args.budget_cap:
        sys.exit(
            f"error: projected cost ${projected:.4f} exceeds budget cap "
            f"${args.budget_cap:.4f} (clamped ramp: "
            f"{_clamp_ramp(ramp, hard_max)} x {n_calls} calls); raise "
            f"--budget-cap or reduce --max-results"
        )

    print(
        f"probe_filter_yield: n_calls={n_calls} ramp={ramp} "
        f"hard_max={hard_max} projected_cost=${projected:.4f}"
    )
    for call in calls:
        print(
            f"  {call.call_id:3s}  query_length={call.query_length:4d}  "
            f"q={call.query_string[:80]}"
            + ("..." if len(call.query_string) > 80 else "")
        )

    if args.dry_run:
        print("")
        print("dry-run: no HTTP calls fired. Planned call set printed above.")
        # Still write a placeholder CSV so downstream tooling can
        # exercise the same output path. Each row carries n_results=null
        # so consumers can tell dry-run from a live run.
        all_rows = [
            {
                "call_id": call.call_id,
                "max_results": min(level, hard_max),
                "n_results": None,
                "n_kept_after_filter": None,
                "wall_clock_ms": None,
                "cost_estimate_usd": None,
                "t_newest": None,
                "t_oldest": None,
                "n_within_15min": None,
                "extrapolated_n_in_15min": None,
                "extrapolation_confidence": None,
                "sample_tweet_ids": "",
                "error": "dry-run",
            }
            for call in calls
            for level in _clamp_ramp(ramp, hard_max)
        ]
        if args.output is None:
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            out_path = Path(f"/tmp/filter_yield_{ts}.csv")
        else:
            out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(CSV_HEADER)
            for r in all_rows:
                writer.writerow(_row_for_csv(r["call_id"], r["max_results"], r))
        print(f"wrote {len(all_rows)} rows (dry-run placeholders) to {out_path}")
        return 0

    have_creds, _ = _have_api_creds()
    if not have_creds:
        print(
            "error: no API key in env (set TWITTERAPI_IO_KEY or "
            "TWITTER_API_KEY)", file=sys.stderr,
        )
        return 2

    from x_monitor.apify import TwitterApiClient
    client = TwitterApiClient.from_env()

    # Run the actual probe.
    all_rows: list[dict] = []
    for call in calls:
        for level in ramp:
            clamped_level = min(level, hard_max)
            row = _fire_one_call(client, call, clamped_level)
            row["call_id"] = call.call_id
            row["max_results"] = clamped_level
            all_rows.append(row)
            _print_progress(call.call_id, clamped_level, row)

    # Print summary.
    _print_summary(all_rows)

    # Write CSV.
    if args.output is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = Path(f"/tmp/filter_yield_{ts}.csv")
    else:
        out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(CSV_HEADER)
        for r in all_rows:
            writer.writerow(_row_for_csv(r["call_id"], r["max_results"], r))
    print(f"\nwrote {len(all_rows)} rows to {out_path}")
    return 0


def _print_progress(call_id: str, level: int, row: dict) -> None:
    """Print one-line progress per (call, level). Avoids flooding the
    terminal while still giving the operator a heartbeat during the
    ~3-minute probe run."""
    nr = row.get("n_results")
    kept = row.get("n_kept_after_filter")
    ms = row.get("wall_clock_ms")
    nr_str = f"{nr}" if nr is not None else "n/a"
    kept_str = f"{kept}" if kept is not None else "n/a"
    print(
        f"  [{call_id:3s} @ {level:4d}] n_results={nr_str:>4s}  "
        f"kept={kept_str:>4s}  wall={ms}ms"
    )


if __name__ == "__main__":
    sys.exit(main())
