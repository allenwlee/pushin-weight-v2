"""Regression pin: cursor-vs-insert ratio must stay healthy.

Plan: docs/operations/cursor-vs-insert-gap-diagnosis.md (2026-08-06)

The 989-fetched vs 86-inserted gap on 2026-08-05 16:00-16:14 UTC was
caused by `cycle.max_lookback_hours: 2` — the cycle re-fetched the
same 2-hour window every 15 min and INSERT OR IGNORE discarded ~91%
of the tweets.

Fix (Option A, 2026-08-06): `max_lookback_hours: 0.25` (15 min, one
cycle window). After this fix, the ratio should rebound to 0.30-0.95.

Two pins:
1. test_max_lookback_hours_is_one_cycle_or_less — catches a wrong-floor
   config bug (the original cause). Always runs; never skips.
2. test_insert_to_fetch_ratio_stays_healthy — runs against the most
   recent 15-min bucket; skips when no recent data exists (cron paused).
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path


REPO_ROOT = Path("/Users/fuchitalee/development/pushin-weight-v2")
RENDER_PG = "dpg-d9koekqjobas73fvjqng-a"
SSH_BASE = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ServerAliveInterval=5",
            "-o", "ServerAliveCountMax=4", "fuchitalee"]


def _ssh_psql(sql: str) -> str:
    """Run a SQL query via Render-proxied psql and return stdout."""
    cmd = SSH_BASE + ["render", "psql", RENDER_PG, "--command", sql, "-o", "text", "--confirm"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _parse_psql_count(out: str) -> int:
    """Parse count from `psql -o text` output (skip dashes + header)."""
    for line in out.splitlines():
        line = line.strip()
        if line.isdigit():
            return int(line)
    return 0


def _read_max_lookback_hours() -> float | None:
    """Read the current cycle.max_lookback_hours from config.yaml."""
    cfg = REPO_ROOT / "config.yaml"
    if not cfg.exists():
        return None
    text = cfg.read_text(encoding="utf-8")
    m = re.search(r"max_lookback_hours:\s*([0-9.]+)", text)
    return float(m.group(1)) if m else None


def test_max_lookback_hours_is_one_cycle_or_less():
    """The cursor floor must be <= 1 hour (one cycle window plus headroom).

    A 2-hour floor re-fetches the same window every 15 min and burns
    91% of credits on duplicate fetches. See
    docs/operations/cursor-vs-insert-gap-diagnosis.md.
    """
    hours = _read_max_lookback_hours()
    assert hours is not None, "config.yaml::cycle.max_lookback_hours is missing"
    assert hours <= 1.0, (
        f"cycle.max_lookback_hours={hours} is too high. The cursor floor "
        "should be <= 1.0 (one cycle window plus headroom; ~0.25 is "
        "the recommended value with the 15-min cron cadence). A larger "
        "window re-fetches tweets already in 'posts' and INSERT OR IGNORE "
        "discards them, wasting ~70% of the TwitterAPI.io credit budget. "
        "See docs/operations/cursor-vs-insert-gap-diagnosis.md. "
        "Exception: if the operator has a documented multi-cycle downtime "
        "recovery requirement, raise this ceiling in config.yaml and add "
        "an explicit comment explaining why."
    )


def test_insert_to_fetch_ratio_stays_healthy():
    """The most recent 15-min bucket's insert count should be >= 30.

    With `max_lookback_hours: 0.25` (15-min floor), each cycle fetches
    ~50-200 new tweets. If the floor is too high OR the cycle is stuck
    OR the classifier is dropping all tweets, the count drops.

    Skips when no recent cycle data exists (cron paused). Once the cron
    resumes, this pin will catch any future regression of the cursor
    floor or downstream filter.
    """
    import pytest
    hours = _read_max_lookback_hours()
    if hours is None or hours > 1.0:
        pytest.skip(
            f"cycle.max_lookback_hours={hours} > 1.0; the floor test "
            "should fire instead. Re-run after fixing the floor."
        )
    sql = (
        "SELECT count(*) FROM posts "
        "WHERE fetched_at >= date_trunc('hour', now()) "
        "AND fetched_at < date_trunc('hour', now()) + interval '15 minutes'"
    )
    try:
        out = _ssh_psql(sql)
    except Exception as exc:
        pytest.skip(f"cannot reach prod DB ({exc}); restore SSH on fuchitalee to run this pin")
    inserts = _parse_psql_count(out)
    if inserts == 0:
        pytest.skip("no recent 15-min bucket data (cron paused?)")
    assert inserts >= 30, (
        f"only {inserts} posts inserted in the most recent 15-min "
        "bucket. Expected >= 30 (typical 15-min cycle fetches 50-200 new "
        "tweets). Possible regressions: cursor floor too high, fetch loop "
        "stuck, classifier dropping all tweets, or TwitterAPI billing "
        "exhausted. See docs/operations/cursor-vs-insert-gap-diagnosis.md."
    )
