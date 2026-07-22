#!/usr/bin/env python3
"""Backfill display_name_en on `brands` and `companies`.

Unit 6 (i18n plan): thin wrapper around `x-monitor translate-registry`
that pre-loads the standard operator config and runs in both-dry-run
first, then live. Idempotent: only fills rows where display_name_en
is NULL.

Usage:
    python3 scripts/2026-06-23-001-backfill-display-name-en.py /path/to/x.db [--live]

The default mode is dry-run; pass --live to actually call the LLM
and write the DB. The dry-run preview is intended to be inspected by
the operator before running live.
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
            "usage: 2026-06-23-001-backfill-display-name-en.py "
            "<db_path> [--live]",
            file=sys.stderr,
        )
        return 2
    db_path = Path(sys.argv[1]).resolve()
    if not db_path.exists():
        print(f"db not found at {db_path}", file=sys.stderr)
        return 2
    live = "--live" in sys.argv[2:]

    # Wrapper script lives next to the x-monitor package; the CLI
    # module is `python -m x_monitor translate-registry ...`.
    repo_root = Path(__file__).resolve().parent.parent
    py = sys.executable

    base = [
        py, "-m", "x_monitor", "translate-registry",
        "--locale", "en", "--limit", "500",
    ]

    # Two tables: brands, companies. Each gets a separate CLI call so
    # progress and errors are scoped to one table.
    n_total = 0
    for table in ("brands", "companies"):
        # Always run a dry-run first so the operator can preview the
        # row count before going live. We only print the row count,
        # not the actual translated strings, to keep the log small.
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
