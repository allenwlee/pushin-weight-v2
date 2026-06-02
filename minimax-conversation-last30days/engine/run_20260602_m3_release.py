#!/usr/bin/env python3
# {{AGENT_ATTRIBUTION}}
"""
Focused last30days run for the MiniMax M3.0 release (2026-06-01, ~25h before
this run). 2-day lookback, MiniMax-only (no Qwen/DeepSeek controls).

Query design (13 queries, breaking-news scoped):
  - Core:        M3.0 release + brand+model
  - Comparisons: vs Claude, vs DeepSeek, vs Qwen (defines the narrative)
  - Capabilities: multimodal, image, video, speech, music, coding
  - Reception:   benchmark, review, pricing

Usage:
    python3 engine/run_20260602_m3_release.py
    python3 engine/run_20260602_m3_release.py --no-quick
    python3 engine/run_20260602_m3_release.py --days 3

Outputs land in ../20260602/producer/ (created if missing).
"""
import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
LAST30DAYS = HERE / "last30days.py"
DEFAULT_OUT_DIR = HERE.parent / "20260602" / "producer"

QUERIES = [
    # Core release narrative
    ("MiniMax M3.0",                         "m3-core.md"),
    ("MiniMax M3 release",                   "m3-release.md"),
    # Direct comparisons — define the M3.0 narrative
    ("MiniMax M3 vs Claude",                 "m3-vs-claude.md"),
    ("MiniMax M3 vs DeepSeek",               "m3-vs-deepseek.md"),
    ("MiniMax M3 vs Qwen",                   "m3-vs-qwen.md"),
    # Capabilities — the differentiators
    ("MiniMax M3 multimodal",                "m3-multimodal.md"),
    ("MiniMax M3 image",                     "m3-image.md"),
    ("MiniMax M3 video",                     "m3-video.md"),
    ("MiniMax M3 speech",                    "m3-speech.md"),
    ("MiniMax M3 music",                     "m3-music.md"),
    ("MiniMax M3 coding",                    "m3-coding.md"),
    # Reception
    ("MiniMax M3 benchmark",                 "m3-benchmark.md"),
    ("MiniMax M3 review",                    "m3-review.md"),
    ("MiniMax M3 pricing",                   "m3-pricing.md"),
]


def run_query(query: str, output_path: Path, quick: bool, days: int) -> bool:
    cmd = ["python3", str(LAST30DAYS), query, "--emit=compact", "--days", str(days)]
    if quick:
        cmd.append("--quick")
    print(f"  -> {' '.join(cmd[2:])} > {output_path.name}", file=sys.stderr)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        print(f"  !! {output_path.name}: 180s timeout", file=sys.stderr)
        return False
    if result.returncode != 0:
        print(f"  !! {output_path.name}: exit {result.returncode}", file=sys.stderr)
        if result.stderr:
            print(f"     stderr[:300]: {result.stderr[:300]}", file=sys.stderr)
        return False
    output_path.write_text(result.stdout)
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1] if __doc__ else "")
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR,
                    help=f"Output dir (default: {DEFAULT_OUT_DIR})")
    ap.add_argument("--days", type=int, default=2, help="Lookback days (default: 2 — breaking-news window)")
    ap.add_argument("--no-quick", action="store_true", help="Disable --quick (slower, more coverage)")
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    quick = not args.no_quick

    print(f"MiniMax M3.0 release run — {len(QUERIES)} queries, {args.days}-day window, quick={quick}",
          file=sys.stderr)
    print(f"Output: {args.out_dir}", file=sys.stderr)

    failures = []
    for i, (query, fname) in enumerate(QUERIES, 1):
        print(f"\n[{i}/{len(QUERIES)}] {query}", file=sys.stderr)
        out_path = args.out_dir / fname
        if not run_query(query, out_path, quick=quick, days=args.days):
            failures.append((query, fname))

    total = len(QUERIES)
    print(f"\n{total - len(failures)}/{total} queries succeeded. Outputs in {args.out_dir}", file=sys.stderr)
    if failures:
        print("\nFailures:", file=sys.stderr)
        for q, fn in failures:
            print(f"  {q} -> {fn}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
