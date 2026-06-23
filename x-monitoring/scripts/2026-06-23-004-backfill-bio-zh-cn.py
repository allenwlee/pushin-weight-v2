#!/usr/bin/env python3
"""Backfill bio_zh_cn on `accounts`.

Unit 6 (i18n plan): thin wrapper around `x-monitor translate-registry`
specialized to the accounts.bio column. bio is only on accounts
(otherwise the CLI rejects with rc=2). Idempotent: only fills rows
where bio_zh_cn is NULL.

Usage:
    python3 scripts/2026-06-23-004-backfill-bio-zh-cn.py /path/to/x.db [--live]
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
            "usage: 2026-06-23-004-backfill-bio-zh-cn.py "
            "<db_path> [--live]",
            file=sys.stderr,
        )
        return 2
    db_path = Path(sys.argv[1]).resolve()
    if not db_path.exists():
        print(f"db not found at {db_path}", file=sys.stderr)
        return 2
    live = "--live" in sys.argv[2:]

    py = sys.executable
    base = [
        py, "-m", "x_monitor", "translate-registry",
        "accounts", "bio", "--locale", "zh_cn", "--limit", "500",
    ]

    rc = run(base + ["--dry-run"])
    if rc != 0:
        return rc
    if not live:
        print("dry-run only; pass --live to write DB")
        return 0
    rc = run(base)
    if rc != 0:
        return rc
    print("done: 1 table processed (live=True)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
