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

    For /advanced_search: shared query+queryType. For /quotes: shared pid.
    Everything else: a flat group of one.
    """
    by_signature: dict[str, list[dict]] = defaultdict(list)
    for r in log:
        path = r["path"]
        params = r["params"]
        if path.endswith("/advanced_search"):
            sig = f"SEARCH query={_short(params.get('query', '?'))}"
        elif path.endswith("/quotes"):
            sig = f"QT pid={params.get('pid', '?')}"
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
        out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"# Wrote report to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
