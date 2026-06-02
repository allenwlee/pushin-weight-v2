#!/usr/bin/env python3
# {{AGENT_ATTRIBUTION}}
"""
Run the last30days research queries defined in the 8-unit plan.

The plan lives at:
    ../20260526/consumer/2026-05-26-001-feat-minimax-conversation-research-plan.md

Usage:
    python3 scripts/run_research.py --out-dir minimax-conversation-last30days/20260602/producer
    python3 scripts/run_research.py --unit 2 --out-dir .../producer
    python3 scripts/run_research.py --units 2,3,4 --quick --out-dir .../producer

Output filenames match the plan spec. All queries use --emit=compact; add
--quick to stay under 5-min bash timeouts.
"""
import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
LAST30DAYS = HERE / "last30days.py"

# Plan unit -> {label: (query_string, output_filename)}
UNITS = {
    2: {  # Core model conversation queries
        "minimax":   ("Minimax AI",                  "minimax-core-queries.md"),
        "qwen":      ("Qwen AI",                     "qwen-core-queries.md"),
        "deepseek":  ("DeepSeek AI",                 "deepseek-core-queries.md"),
    },
    3: {  # Language-agnostic brand-name queries
        "minimax":   ("MiniMax",                     "language-distribution-minimax.md"),
        "qwen":      ("Qwen",                        "language-distribution-qwen.md"),
        "deepseek":  ("DeepSeek",                    "language-distribution-deepseek.md"),
    },
    4: {  # MiniMax variant breakdown
        "M2.7":      ("MiniMax M2.7",                "chinese-minimax-minimax-m2.7.md"),
        "Mavis":     ("MiniMax Mavis",               "chinese-minimax-minimax-mavis.md"),
        "Hub":       ("MiniMax Hub",                 "chinese-minimax-minimax-hub.md"),
        "Agent":     ("MiniMax Agent",               "chinese-minimax-minimax-agent.md"),
        "Speech":    ("MiniMax Speech",              "chinese-minimax-minimax-speech.md"),
    },
    5: {  # Use-case segmentation
        "agent":                 ("MiniMax agent Claude Code",  "usecase-agent.md"),
        "music":                 ("MiniMax music",              "usecase-music.md"),
        "speech":                ("MiniMax speech audio",       "usecase-speech.md"),
        "deepseek-coding":       ("DeepSeek coding",            "usecase-deepseek-coding.md"),
        "minimax-coding":        ("MiniMax coding",             "usecase-minimax-coding.md"),
        "minimax-image-generate":("MiniMax image generate",     "usecase-minimax-image-generate.md"),
        "minimax-video-sora":    ("MiniMax video Sora",         "usecase-minimax-video-sora.md"),
        "qwen-coding":           ("Qwen coding",                "usecase-qwen-coding.md"),
        "qwen-image":            ("Qwen image",                 "usecase-qwen-image.md"),
        "minimax_image":         ("MiniMax image",              "usecase-minimax_image.md"),
        "minimax_video":         ("MiniMax video",              "usecase-minimax_video.md"),
    },
    7: {  # Pricing / value
        "minimax":   ("Minimax Token Plan pricing",  "pricing-minimax.md"),
        "qwen":      ("Qwen API pricing",            "pricing-qwen.md"),
        "deepseek":  ("DeepSeek price cut V4 Pro",   "pricing-deepseek.md"),
        "generic":   ("AI model cost comparison",    "pricing-generic.md"),
    },
}


def run_query(query: str, output_path: Path, quick: bool = False) -> bool:
    cmd = ["python3", str(LAST30DAYS), query, "--emit=compact"]
    if quick:
        cmd.append("--quick")
    print(f"  -> {' '.join(cmd[2:])} > {output_path.name}", file=sys.stderr)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        print(f"  !! {output_path.name}: 300s timeout", file=sys.stderr)
        return False
    if result.returncode != 0:
        print(f"  !! {output_path.name}: exit {result.returncode}", file=sys.stderr)
        print(f"     stderr: {result.stderr[:200]}", file=sys.stderr)
        return False
    output_path.write_text(result.stdout)
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1] if __doc__ else "")
    ap.add_argument("--out-dir", required=True, help="Target producer/ dir for outputs")
    ap.add_argument("--units", default="2,3,4,5,7", help="Comma-separated unit numbers to run (default: 2,3,4,5,7)")
    ap.add_argument("--unit", type=int, help="Run only this unit (overrides --units)")
    ap.add_argument("--quick", action="store_true", help="Pass --quick to last30days.py (faster, less coverage)")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    units_to_run = [args.unit] if args.unit else [int(u) for u in args.units.split(",")]
    failures = []
    total = 0

    for unit_num in units_to_run:
        queries = UNITS.get(unit_num, {})
        if not queries:
            print(f"unit {unit_num}: no queries defined", file=sys.stderr)
            continue
        print(f"\n=== Unit {unit_num} ({len(queries)} queries) ===", file=sys.stderr)
        for label, (query, fname) in queries.items():
            out_path = out_dir / fname
            total += 1
            if not run_query(query, out_path, quick=args.quick):
                failures.append((unit_num, label, query))

    print(f"\n{total - len(failures)}/{total} queries succeeded. Outputs in {out_dir}", file=sys.stderr)
    if failures:
        print("\nFailures:", file=sys.stderr)
        for u, k, q in failures:
            print(f"  unit {u} / {k}: {q}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
