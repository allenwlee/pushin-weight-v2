#!/usr/bin/env python3
"""Backfill display_name_zh_cn on `brands` and `companies`.

Unit 6 (i18n plan): thin wrapper around `x-monitor translate-registry`
that pre-loads the standard operator config and runs in both-dry-run
first, then live. Idempotent: only fills rows where display_name_zh_cn
is NULL.

Usage:
    python3 scripts/2026-06-23-002-backfill-display-name-zh-cn.py /path/to/x.db [--live]
"""
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str]) -> int:
    print("$", " ".join(cmd))
    return subprocess.call(cmd)


def main() -> int:
    if len(sys.argv) < 2:
        print(
            "usage: 2026-06-23-002-backfill-display-name-zh-cn.py "
            "<db_path> [--live]",
            file=sys.stderr,
        )
        return 2
    db_path = Path(sys.argv[1]).resolve()
    if not db_path.exists():
        print(f"db not found at {db_path}", file=sys.stderr)
        return 2
    live = "--live" in sys.argv[2:]

    repo_root = Path(__file__).resolve().parent.parent
    py = sys.executable

    base = [
        py, "-m", "x_monitor", "translate-registry",
        "--locale", "zh_cn", "--limit", "500",
    ]

    n_total = 0
    for table in ("brands", "companies"):
        rc = run(base + [table, "display_name", "--dry-run"])
        if rc != 0:
            return rc
        if not live:
            continue
        rc = run(base + [table, "display_name"])
        if rc != 0:
            return rc
        n_total += 1

    print(f"done: {n_total} table(s) processed (live={live})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
