"""Migration 025: main-loop since= cursor persistence.

Plan: docs/plans/2026-07-02-001-feat-configurable-search-limits-and-backlog-plan.md
Unit 2 of 6 (U2 — Wire since= cursor for main-loop search).

Scope:
- New `call_state` table keyed by
  (brand_id, call_id, call_kind, bucket, query_id) with a
  `last_completed_at` ISO-8601 TEXT column.
- Store.get_last_completed_at(...) / set_last_completed_at(...)
  helpers used by the main loop to remember "we already fetched
  through this moment".

Verifies:
- Schema: call_state table exists after migration with the expected
  columns and PK.
- Happy path: get_last_completed_at returns None for a fresh key,
  returns the stored value after set_last_completed_at.
- Idempotency: set_last_completed_at twice advances monotonically
  (UPSERT semantics).
- Composite-key isolation: rows with different (brand_id, call_id,
  call_kind, bucket, query_id) tuples do not collide.
- Full-stack apply: all on-disk migrations (including 025) apply
  cleanly.
"""

from __future__ import annotations

import pytest


CALL_STATE_PK = (
    "brand_id", "call_id", "call_kind", "bucket", "query_id",
)


# --- schema ----------------------------------------------------------


def test_migration_025_call_state_table_present(tmp_path):
    """Migration 025 creates the call_state table."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='call_state'"
        ).fetchall()
        all_tables = [
            r["name"]
            for r in s._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        assert rows, (
            f"call_state table missing after 025; have tables: {all_tables}"
        )
    finally:
        s.close()


def test_migration_025_call_state_columns(tmp_path):
    """call_state has the columns the Store helpers rely on."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        cols = {
            r["name"]
            for r in s._conn.execute(
                "PRAGMA table_info(call_state)"
            ).fetchall()
        }
        for required in {
            "brand_id", "call_id", "call_kind", "bucket",
            "query_id", "last_completed_at", "updated_at",
        }:
            assert required in cols, (
                f"call_state missing column {required!r}; have {cols}"
            )
    finally:
        s.close()


def test_migration_025_call_state_primary_key(tmp_path):
    """call_state PK is the composite (brand_id, call_id, call_kind,
    bucket, query_id) — matches what the Store helpers use."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        pk_rows = s._conn.execute(
            "PRAGMA table_info(call_state)"
        ).fetchall()
        pk_cols = [r["name"] for r in pk_rows if r["pk"] > 0]
        assert tuple(pk_cols) == CALL_STATE_PK, (
            f"call_state PK != expected: got {pk_cols}, "
            f"expected {list(CALL_STATE_PK)}"
        )
    finally:
        s.close()


# --- helpers: round-trip --------------------------------------------


def test_migration_025_get_returns_none_for_missing_row(tmp_path):
    """get_last_completed_at returns None when no row exists for the
    composite key (first-ever cycle for this PlannedCall)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        result = s.get_last_completed_at(
            brand_id="minimax",
            call_id="B",
            call_kind="brand_wide",
            bucket=None,
            query_id="Q5",
        )
        assert result is None, (
            f"expected None for fresh key, got {result!r}"
        )
    finally:
        s.close()


def test_migration_025_set_then_get_round_trip(tmp_path):
    """set_last_completed_at then get_last_completed_at returns the
    stored ISO string."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        iso = "2026-07-01T10:00:00+00:00"
        s.set_last_completed_at(
            brand_id="minimax",
            call_id="B",
            call_kind="brand_wide",
            bucket=None,
            query_id="Q5",
            last_completed_at=iso,
        )
        got = s.get_last_completed_at(
            brand_id="minimax",
            call_id="B",
            call_kind="brand_wide",
            bucket=None,
            query_id="Q5",
        )
        assert got == iso, (
            f"round-trip mismatch: stored {iso!r}, got {got!r}"
        )
    finally:
        s.close()


def test_migration_025_set_idempotent_advances(tmp_path):
    """Calling set_last_completed_at twice advances the stored value
    (UPSERT semantics, not insert-only)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        first = "2026-07-01T10:00:00+00:00"
        second = "2026-07-01T22:30:00+00:00"
        s.set_last_completed_at(
            "qwen", "B", "brand_wide", None, "Q5", first,
        )
        s.set_last_completed_at(
            "qwen", "B", "brand_wide", None, "Q5", second,
        )
        got = s.get_last_completed_at(
            "qwen", "B", "brand_wide", None, "Q5",
        )
        assert got == second, (
            f"set_last_completed_at did not UPSERT: "
            f"first={first!r} second={second!r} got={got!r}"
        )
    finally:
        s.close()


# --- composite-key isolation ----------------------------------------


def test_migration_025_composite_key_isolation(tmp_path):
    """Different (brand_id, call_id, call_kind, bucket, query_id)
    tuples do not collide. Each unique key has its own cursor."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        # Two different brand_ids at the same call_id/kind/bucket/query_id.
        s.set_last_completed_at(
            "minimax", "B", "brand_wide", None, "Q5",
            "2026-07-01T10:00:00+00:00",
        )
        s.set_last_completed_at(
            "qwen", "B", "brand_wide", None, "Q5",
            "2026-07-01T11:00:00+00:00",
        )
        # Two different call_ids at the same brand/kind/bucket/query_id
        # (the U2 spec calls out this exact case: two Call C specs).
        s.set_last_completed_at(
            "minimax", "C1", "brand_wide", None, "Q5",
            "2026-07-01T12:00:00+00:00",
        )
        s.set_last_completed_at(
            "minimax", "C2", "brand_wide", None, "Q5",
            "2026-07-01T13:00:00+00:00",
        )
        # Two different query_ids (signal rotation edge case).
        s.set_last_completed_at(
            "minimax", "B", "brand_wide", None, "Q1",
            "2026-07-01T14:00:00+00:00",
        )

        # Confirm each round-trips independently.
        assert s.get_last_completed_at(
            "minimax", "B", "brand_wide", None, "Q5",
        ) == "2026-07-01T10:00:00+00:00"
        assert s.get_last_completed_at(
            "qwen", "B", "brand_wide", None, "Q5",
        ) == "2026-07-01T11:00:00+00:00"
        assert s.get_last_completed_at(
            "minimax", "C1", "brand_wide", None, "Q5",
        ) == "2026-07-01T12:00:00+00:00"
        assert s.get_last_completed_at(
            "minimax", "C2", "brand_wide", None, "Q5",
        ) == "2026-07-01T13:00:00+00:00"
        assert s.get_last_completed_at(
            "minimax", "B", "brand_wide", None, "Q1",
        ) == "2026-07-01T14:00:00+00:00"

        # Total row count = 5.
        n_rows = s._conn.execute(
            "SELECT COUNT(*) AS n FROM call_state"
        ).fetchone()["n"]
        assert n_rows == 5, f"expected 5 call_state rows, got {n_rows}"
    finally:
        s.close()


def test_migration_025_null_bucket_distinct_from_string_bucket(tmp_path):
    """NULL bucket is treated as a distinct cursor from a string
    bucket with the same (brand_id, call_id, call_kind, query_id).
    The v1.6 contract has bucket=NULL for v1.7 calls; this guards
    against accidentally coalescing both into one row."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        s.set_last_completed_at(
            "minimax", "B", "brand_wide", None, "Q5",
            "2026-07-01T10:00:00+00:00",
        )
        s.set_last_completed_at(
            "minimax", "B", "brand_wide", "v16_bucket", "Q5",
            "2026-07-01T11:00:00+00:00",
        )
        assert s.get_last_completed_at(
            "minimax", "B", "brand_wide", None, "Q5",
        ) == "2026-07-01T10:00:00+00:00"
        assert s.get_last_completed_at(
            "minimax", "B", "brand_wide", "v16_bucket", "Q5",
        ) == "2026-07-01T11:00:00+00:00"
    finally:
        s.close()


# --- full-stack apply ------------------------------------------------


def test_migration_025_full_stack_apply(tmp_path):
    """All on-disk migrations (including 025) apply cleanly on a fresh
    DB."""
    from pathlib import Path

    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        applied = {
            r["version"]
            for r in s._conn.execute(
                "SELECT version FROM _migrations"
            ).fetchall()
        }
        mig_dir = (
            Path(__file__).resolve().parent.parent
            / "x_monitor" / "migrations"
        )
        expected = {
            int(f.name.split("_", 1)[0])
            for f in mig_dir.glob("*.sql")
        }
        assert applied >= expected, (
            f"missing migrations: applied={sorted(applied)}, "
            f"expected={sorted(expected)}"
        )
        assert 25 in applied, "migration 025 not applied"
    finally:
        s.close()