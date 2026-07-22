#!/usr/bin/env python3
"""Dump the per-HTTP-request log captured by an x-monitor run.

The pipeline records every TwitterAPI.io HTTP exchange into
``summary["http_log"]`` of the run JSON. This script pulls that log out,
prints a flat list of every request, groups them into logical calls, and
optionally writes a structured report to disk.

Usage:
    scripts/dump_http_log.py                       # dump LATEST run
    scripts/dump_http_log.py RUN_ID               # dump specific run
    scripts/dump_http_log.py path/to/run.json     # dump specific file
    scripts/dump_http_log.py --out docs/x.json    # also persist report
    scripts/dump_http_log.py --latency-summary    # print per-call latency
                                                 # distribution (mean, p50,
                                                 # p95, p99, outliers). U4.

Each entry in http_log is one logical HTTP exchange (URL + params + any
retries collapsed into a single record). Fields:

    path          endpoint, e.g. /twitter/tweet/advanced_search
    params        request params (truncated strings for readability)
    status        HTTP status code
    n_results     items in response list (tweets / quotes / followers / users)
    duration_ms   wall-clock duration including any retries
    attempts      HTTP attempts (1 = no retry)
    has_next_page whether the response carried a continuation cursor
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


def _short(val: object) -> str:
    s = str(val)
    return s[:80] + "..." if len(s) > 80 else s


def group_calls(log: list[dict]) -> list[dict]:
    """Group HTTP requests by logical signature.

    For /advanced_search: shared query+queryType. For /quotes: shared tweetId.
    Everything else: a flat group of one.
    """
    by_signature: dict[str, list[dict]] = defaultdict(list)
    for r in log:
        path = r["path"]
        params = r["params"]
        if path.endswith("/advanced_search"):
            sig = f"SEARCH query={_short(params.get('query', '?'))}"
        elif path.endswith("/quotes"):
            sig = f"QT tweetId={params.get('tweetId', '?')}"
        else:
            sig = f"{path} " + " ".join(
                f"{k}={_short(params.get(k, '?'))}" for k in sorted(params.keys())
            )
        by_signature[sig].append(r)
    out = []
    for sig, items in by_signature.items():
        out.append({
            "signature": sig,
            "n_requests": len(items),
            "total_duration_ms": sum(r["duration_ms"] for r in items),
            "total_results": sum(r["n_results"] for r in items),
            "items": items,
        })
    return out


def render_flat(log: list[dict]) -> str:
    lines = []
    for i, r in enumerate(log, 1):
        params_compact = " ".join(
            f"{k}={_short(v)}" for k, v in r["params"].items()
        )
        lines.append(
            f"  [{i:3d}] {r['path']:<40}  "
            f"dur={r['duration_ms']:>6d}ms  "
            f"status={r['status']}  "
            f"results={r['n_results']:>3d}  "
            f"attempts={r['attempts']}  "
            f"next={r['has_next_page']}  "
            f"params=({params_compact})"
        )
    return "\n".join(lines)


def latency_percentiles(durations_ms: list[int]) -> dict[str, float | int | None]:
    """Return mean / median / p95 / p99 / max for a list of millisecond
    durations.

    Returns sentinel values (None for percentiles, 0 for everything)
    when the input is empty so callers can render a clean row instead
    of a KeyError. Sorts a copy — does NOT mutate the input.
    """
    if not durations_ms:
        return {
            "n": 0, "mean_ms": 0, "median_ms": None,
            "p95_ms": None, "p99_ms": None, "max_ms": 0, "min_ms": 0,
        }
    sorted_d = sorted(durations_ms)
    n = len(sorted_d)

    def _percentile(p: float) -> float:
        # Linear interpolation between adjacent ranks (same method
        # numpy's default percentile uses). With n=1 we return the
        # only value.
        if n == 1:
            return float(sorted_d[0])
        rank = (p / 100.0) * (n - 1)
        lo = int(rank)
        hi = min(lo + 1, n - 1)
        frac = rank - lo
        return sorted_d[lo] * (1 - frac) + sorted_d[hi] * frac

    return {
        "n": n,
        "mean_ms": sum(sorted_d) / n,
        "median_ms": _percentile(50),
        "p95_ms": _percentile(95),
        "p99_ms": _percentile(99),
        "max_ms": sorted_d[-1],
        "min_ms": sorted_d[0],
    }


def render_latency_summary(log: list[dict]) -> str:
    """Print a per-endpoint latency distribution table.

    Two sections:
      1. Per-endpoint mean/p50/p95/p99/max.
      2. Outliers — the top 5% (or top 3, whichever is greater) of
         requests across the whole run, with their path + duration
         for manual inspection.
    """
    if not log:
        return "# (no HTTP requests to summarize)"

    by_path: dict[str, list[int]] = defaultdict(list)
    for r in log:
        by_path[r["path"]].append(r["duration_ms"])

    lines = ["## Latency distribution (per endpoint)"]
    lines.append(
        "  endpoint                                          "
        "  n   mean    p50    p95    p99     max"
    )
    for path in sorted(by_path.keys()):
        d = by_path[path]
        s = latency_percentiles(d)
        mean_v = f"{s['mean_ms']:>6.0f}"
        p50_v = "  -  " if s["median_ms"] is None else f"{s['median_ms']:>6.0f}"
        p95_v = "  -  " if s["p95_ms"] is None else f"{s['p95_ms']:>6.0f}"
        p99_v = "  -  " if s["p99_ms"] is None else f"{s['p99_ms']:>6.0f}"
        lines.append(
            f"  {path[:50]:<50}  "
            f"{s['n']:>3d}  "
            f"{mean_v}  "
            f"{p50_v}  "
            f"{p95_v}  "
            f"{p99_v}  "
            f"{s['max_ms']:>6d}"
        )

    lines.append("")
    lines.append("## Outliers (top by duration)")
    sorted_log = sorted(log, key=lambda r: -r["duration_ms"])
    n_outliers = max(3, len(sorted_log) // 20)
    for r in sorted_log[:n_outliers]:
        lines.append(
            f"  {r['duration_ms']:>6d}ms  "
            f"{r['path']:<40}  "
            f"status={r['status']}  "
            f"results={r['n_results']}"
        )

    overall = latency_percentiles(
        [r["duration_ms"] for r in log]
    )
    lines.append("")
    lines.append("## Overall")
    if overall["median_ms"] is None:
        lines.append("  (no requests)")
    else:
        lines.append(
            f"  n={overall['n']}  "
            f"mean={overall['mean_ms']:.0f}ms  "
            f"p50={overall['median_ms']:.0f}ms  "
            f"p95={overall['p95_ms']:.0f}ms  "
            f"p99={overall['p99_ms']:.0f}ms  "
            f"max={overall['max_ms']}ms  "
            f"min={overall['min_ms']}ms"
        )
    return "\n".join(lines)


def render_grouped(groups: list[dict]) -> str:
    lines = []
    for g in groups:
        sig = g["signature"]
        total = g["total_duration_ms"]
        n_req = g["n_requests"]
        n_res = g["total_results"]
        lines.append(
            f"  {sig[:90]:<90}  "
            f"reqs={n_req}  "
            f"total_dur={total:>6d}ms  "
            f"results={n_res}"
        )
        for i, it in enumerate(g["items"], 1):
            params_short = " ".join(
                f"{k}={_short(v)}" for k, v in it["params"].items()
            )
            lines.append(
                f"      page{i}: dur={it['duration_ms']:>5d}ms "
                f"status={it['status']} results={it['n_results']:>3d} "
                f"next={it['has_next_page']} ({params_short})"
            )
        lines.append("")
    return "\n".join(lines)


def resolve_run_path(arg: str | None, runs_dir: Path) -> Path:
    if arg is None or arg == "LATEST":
        latest = runs_dir / "LATEST.json"
        if not latest.exists():
            sys.exit(f"No LATEST.json in {runs_dir}")
        return latest.resolve()
    p = Path(arg)
    if p.is_absolute() and p.exists():
        return p
    candidate = runs_dir / f"{arg}.json"
    if candidate.exists():
        return candidate
    if p.exists():
        return p
    sys.exit(f"Run not found: {arg}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "run", nargs="?", default="LATEST",
        help="run_id, 'LATEST', or path to run JSON (default: LATEST)",
    )
    parser.add_argument(
        "--data-dir", default="data/runs",
        help="directory holding run JSONs (default: data/runs)",
    )
    parser.add_argument(
        "--out", default=None,
        help="if set, write a structured report JSON to this path",
    )
    parser.add_argument(
        "--no-pretty", action="store_true",
        help="print only the flat list (skip the grouped section)",
    )
    parser.add_argument(
        "--latency-summary", action="store_true",
        help="print a per-endpoint latency distribution (mean / p50 / "
             "p95 / p99 / max) plus the overall distribution and top "
             "outliers. U4 observation tool.",
    )
    args = parser.parse_args()

    run_path = resolve_run_path(args.run, Path(args.data_dir))
    summary = json.loads(run_path.read_text())
    log = summary.get("http_log") or []
    run_id = summary.get("run_id", "?")
    started = summary.get("started_at", "?")
    finished = summary.get("finished_at", "?")
    status = summary.get("status", "?")
    phase_timings = summary.get("phase_timings_sec", {})

    print(f"# x-monitor http_log dump")
    print(f"# Run:      {run_id}  ({run_path.name})")
    print(f"# Started:  {started}   Finished: {finished}   Status: {status}")
    print(f"# Requests: {len(log)}")
    if log:
        total_ms = sum(r["duration_ms"] for r in log)
        by_path: dict[str, int] = defaultdict(int)
        by_path_dur: dict[str, int] = defaultdict(int)
        for r in log:
            by_path[r["path"]] += 1
            by_path_dur[r["path"]] += r["duration_ms"]
        print(f"# Total HTTP wall-clock: {total_ms} ms ({total_ms/1000:.2f}s)")
        print(f"# By endpoint:")
        for p, n in sorted(by_path.items(), key=lambda kv: -kv[1]):
            print(
                f"#   {n:3d}  "
                f"{by_path_dur[p]:>7d}ms  "
                f"{p}"
            )
        print(f"# Phase timings (s):")
        for k, v in phase_timings.items():
            print(f"#   {k}={v}")
    print()

    print("## Every HTTP request (flat list)")
    print(render_flat(log))
    print()

    if not args.no_pretty:
        groups = group_calls(log)
        # deterministic order: search queries first (longest total duration
        # first), then everything else
        groups.sort(key=lambda g: (-g["total_duration_ms"], g["signature"]))
        print("## Logical calls (grouped)")
        print(render_grouped(groups))
        print()

    if args.latency_summary:
        print(render_latency_summary(log))
        print()

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "run_id": run_id,
            "started_at": started,
            "finished_at": finished,
            "status": status,
            "phase_timings_sec": phase_timings,
            "n_requests": len(log),
            "http_log": log,
            "logical_calls": group_calls(log),
        }
        if args.latency_summary:
            by_path: dict[str, list[int]] = defaultdict(list)
            for r in log:
                by_path[r["path"]].append(r["duration_ms"])
            report["latency_by_endpoint"] = {
                p: latency_percentiles(d)
                for p, d in by_path.items()
            }
            report["latency_overall"] = latency_percentiles(
                [r["duration_ms"] for r in log]
            )
        out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"# Wrote report to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
