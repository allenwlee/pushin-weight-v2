#!/usr/bin/env python3
"""One-shot backfill: populate posts.created_at_epoch from created_at.

Run once after migration 006 applies. SQLite cannot parse the Twitter
format ("Mon Jun 08 22:25:20 +0000 2026") in pure SQL, so we parse in
Python via x_monitor.store._created_at_epoch. Idempotent: only touches
rows where created_at_epoch IS NULL.

Usage (from the x-monitoring dir):
    .venv/bin/python scripts/2026-06-22-140225-backfill-created-at-epoch.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from x_monitor.store import _created_at_epoch  # noqa: E402

DB = Path(__file__).resolve().parent.parent / "data" / "x_monitoring.db"


def main() -> int:
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT tweet_id, created_at FROM posts WHERE created_at_epoch IS NULL"
    ).fetchall()
    n = 0
    skipped = 0
    for r in rows:
        ep = _created_at_epoch(r["created_at"])
        if ep is None:
            skipped += 1
            continue
        con.execute(
            "UPDATE posts SET created_at_epoch = ? WHERE tweet_id = ?",
            (ep, r["tweet_id"]),
        )
        n += 1
    con.commit()
    con.close()
    print(
        f"backfilled created_at_epoch for {n} posts "
        f"({skipped} unparseable skipped) in {DB}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
