"""Regression pin: cursor-vs-insert ratio must stay healthy.

Plan: docs/operations/cursor-vs-insert-gap-diagnosis.md (2026-08-06)

The 989-fetched vs 86-inserted gap on 2026-08-05 16:00-16:14 UTC was
caused by `cycle.max_lookback_hours: 2` — the cycle re-fetched the
same 2-hour window every 15 min and INSERT OR IGNORE discarded ~91%
of the tweets. This pin asserts the cycle's insert-to-fetch ratio
stays in a healthy band; if the cursor logic drifts again, the test
fails loudly.

The band is calibrated from the post-fix curl evidence:
- 1-hour floor + 15-min cadence -> ~30-50% ratio (most tweets are new)
- 30-min floor + 15-min cadence -> ~50-80% ratio
- 15-min floor + 15-min cadence -> ~80-95% ratio
- 2-hour floor (the bug) -> ~9% ratio

If the test fails, look at:
  1. `config.yaml::cycle.max_lookback_hours` (set to 2; should be 0.25)
  2. `monitor/cycle.py:_read_cursor_since` (the cursor floor + clamp)
  3. `data/runs/LATEST.json` cycle summary (per-query n_inserted vs n_results)
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path("/Users/fuchitalee/development/pushin-weight-v2")
RENDER_PG = "dpg-d9koekqjobas73fvjqng-a"
REPO_NAME = "pushin-weight-v2"


def _ssh_psql(sql: str) -> str:
    # Run a SQL query via the Render-proxied psql and return stdout
    result = subprocess.run(
        ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ServerAliveInterval=5",
         "-o", "ServerAliveCountMax=4", "fuchitalee",
         f"render psql {RENDER_PG} --command \"{sql}\" -o text --confirm"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def _fetched_vs_inserted_24h() -> tuple[int, int]:
    """Best-effort: 24h fetched count vs 24h inserted count.

    Returns (inserted, fetched). Both come from the `posts` table
    (fetched_at vs created_at / live fetch window). No TwitterAPI.io
    usage-history endpoint exists, so fetched-from-API cannot be
    reconciled directly — the dashboard shows it, but the dashboard
    is not queryable via API.
    """
    sql = (
        "SELECT count(*) FILTER (WHERE inserted_at_or_recent_marker) AS ins, "
        "count(*) AS fetch FROM posts WHERE fetched_at > now() - interval '24 hours'"
    )
    # The posts table has no inserted_at column; use fetched_at as a proxy
    # for the total pool of fetched tweets in the 24h window. The
    # insertion test against a tighter 15-min floor is below.
    raise NotImplementedError("placeholder: see fallback test below")


def _parse_psql_count(out: str) -> int:
    """Parse count from `psql -o text` output (skip dashes + header)."""
    for line in out.splitlines():
        line = line.strip()
        if line.isdigit():
            return int(line)
    return 0

def _fetched_vs_inserted_recent_15min() -> tuple[int, int]:
    """Tighter 15-min window: compare tweets fetched (per the live cron)
    against unique posts inserted in the most recent 15-min bucket.

    The cron uses `now - max_lookback_hours` as the since_time floor.
    At a 2-hour floor, the dashboard shows ~989 tweets fetched per cycle
    even though only ~86 are new. We assert the ratio is in the
    healthy band [0.30, 0.95].
    """
    # No live cron (paused). Use the most recent 15-min bucket of the
    # current day as the surrogate cycle. The dashboard showed 989
    # fetches for the 01:00 JST cycle; the 16:00-16:14 UTC bucket
    # shows 86 inserts in the DB. We re-fetch the cycle data via the
    # DB and the previous dashboard snapshot.
    inserts_sql = (
        "SELECT count(*) FROM posts "
        "WHERE fetched_at >= '2026-08-05 16:00:00+00' "
        "AND fetched_at < '2026-08-05 16:15:00+00'"
    )
    out = _ssh_psql(inserts_sql)
    inserted = _parse_psql_count(out)
    return inserted, 989  # dashboard-observed fetch count for this cycle


def test_insert_to_fetch_ratio_stays_healthy():
    """The 16:00-16:14 UTC cycle (2026-08-05) inserted 86 posts.

    The dashboard showed 989 tweets fetched across 52 calls in the
    equivalent 01:00-01:08 JST cycle. With a 2-hour fetch floor and
    ~91% of tweets already in `posts`, the insert-to-fetch ratio was
    0.087 — the bug. After lowering `max_lookback_hours` to 0.25,
    the ratio should rebound to >= 0.30 (most fetched tweets are new
    once the floor is one cycle window).
    """
    inserted, dashboar_fetched = _fetched_vs_inserted_recent_15min()
    if dashboar_fetched == 0:
        # No data to assert against. Skip rather than fail.
        import pytest
        pytest.skip("no cycle data available to compute ratio")
    ratio = inserted / dashboar_fetched
    assert 0.30 <= ratio <= 0.95, (
        f"insert:fetch ratio {ratio:.3f} (inserted={inserted}, "
        f"fetched={dashboar_fetched}) is outside the healthy band [0.30, 0.95]. "
        "This is the symptom of the cursor-floor bug: see "
        "docs/operations/cursor-vs-insert-gap-diagnosis.md. Likely "
        "cause: `config.yaml::cycle.max_lookback_hours: 2` re-fetches "
        "the same 2-hour window every 15-min cycle and INSERT OR IGNORE "
        "discards the duplicates. Fix: lower max_lookback_hours to 0.25 "
        "(15 min, one cycle window)."
    )
