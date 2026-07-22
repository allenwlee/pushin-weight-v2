"""Tests for the n_classifications_written counter (Plan 2026-07-15-003 U3).

Before this plan, the counter was read incrementally after each per-call
loop iteration, BEFORE _run_post_fetch ran. Since post_fetch is the path
that writes the majority of classifications via
`insert_posts_brands_signals`, the counter reported 0 even when hundreds
of classifications actually landed.

Two fixes:
  1. `Store.insert_posts_brands_signals` now bumps
     `_classifications_written` after each successful INSERT (mirror the
     pattern at the inline `insert_posts` writer).
  2. The counter is read once after `_run_post_fetch` completes instead
     of incrementally per call.

These tests pin both halves.
"""
from __future__ import annotations

from pathlib import Path

import pytest


def test_insert_posts_brands_signals_bumps_counter(tmp_path: Path) -> None:
    """A successful insert_posts_brands_signals call increments
    store._classifications_written by 1. Mirrors the inline writer's
    pattern at store.py:780."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    store = Store(db, auto_migrate=True)
    try:
        # Bootstrap the minimum reference rows needed for the FK guards.
        # We need a brand, a post_type_key, and a sentiment_key.
        store._conn.execute(
            "INSERT OR IGNORE INTO brands(nickname, display_name) VALUES (?, ?)",
            ("minimax", "MiniMax"),
        )
        store._conn.execute(
            "INSERT OR IGNORE INTO post_type_keys(key) VALUES (?)",
            ("performance_comparisons",),
        )
        store._conn.execute(
            "INSERT OR IGNORE INTO sentiment_keys(key) VALUES (?)",
            ("positive",),
        )
        store._conn.execute(
            "INSERT OR REPLACE INTO posts(tweet_id, text, lang_detected, "
            "created_at, fetched_at) VALUES (?, ?, ?, ?, ?)",
            ("t1", "hello world", "en", "2026-07-15", "2026-07-15"),
        )
        store._conn.commit()

        before = store._classifications_written

        store.insert_posts_brands_signals(
            post_id="t1",
            brand_id="minimax",
            post_type="performance_comparisons",
            sentiment="positive",
        )

        assert store._classifications_written == before + 1
    finally:
        store.close()


def test_dropped_classification_does_not_bump_counter(tmp_path: Path) -> None:
    """When insert_posts_brands_signals drops the row (unknown post_type
    dead-letter), the counter is NOT bumped."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    store = Store(db, auto_migrate=True)
    try:
        store._conn.execute(
            "INSERT OR IGNORE INTO brands(nickname, display_name) VALUES (?, ?)",
            ("minimax", "MiniMax"),
        )
        store._conn.execute(
            "INSERT OR REPLACE INTO posts(tweet_id, text, lang_detected, "
            "created_at, fetched_at) VALUES (?, ?, ?, ?, ?)",
            ("t1", "hello world", "en", "2026-07-15", "2026-07-15"),
        )
        store._conn.commit()

        before = store._classifications_written

        # Unknown post_type triggers the dead-letter path.
        store.insert_posts_brands_signals(
            post_id="t1",
            brand_id="minimax",
            post_type="nonexistent_post_type",
            sentiment="positive",
        )

        assert store._classifications_written == before, (
            "Dropped classification should not bump the counter"
        )
    finally:
        store.close()


def test_counter_read_after_post_fetch_not_per_cycle(tmp_path: Path) -> None:
    """The run JSON's n_classifications_written reflects the final counter
    state AFTER post_fetch, not the partial state per cycle. We assert
    the cmd_run code path's behavior at the source level: cmd_run no
    longer accumulates the counter inside the per-call loop."""
    from pathlib import Path
    import re

    src = Path(
        "/Users/fuchitalee/development/minimax-marketing/x-monitoring/x_monitor/run.py"
    ).read_text()

    # Find every place n_classifications_written is touched.
    matches = list(re.finditer(
        r"n_classifications_written", src
    ))
    assert len(matches) >= 2, (
        f"Expected multiple references to n_classifications_written, "
        f"got {len(matches)}"
    )

    # The accumulator pattern `summary[...][...] += store._classifications_written`
    # must NOT appear (we removed it). The set pattern (single read) is OK.
    accumulator_pattern = re.search(
        r'summary\["totals"\]\["n_classifications_written"\]\s*\+=',
        src,
    )
    assert accumulator_pattern is None, (
        "The per-cycle accumulator was removed; it must not come back. "
        f"Match at offset {accumulator_pattern.start()}"
    )

    # The single-read pattern (assignment) MUST appear.
    # The RHS is split across lines (parenthesized), so allow whitespace.
    assignment_pattern = re.search(
        r'summary\["totals"\]\["n_classifications_written"\]\s*=\s*\(\s*'
        r'store\._classifications_written',
        src,
    )
    assert assignment_pattern is not None, (
        "The single-read pattern (after _run_post_fetch) is missing"
    )