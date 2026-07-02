"""Migration 024: seed the 9 v1.7 brands missing from the brands table.

Plan: docs/plans/2026-07-02-001-feat-configurable-search-limits-and-backlog-plan.md
Unit 3 of 6 (U3 — Resolve llama/yi FK-violation noise; operator-scoped
to register all 9 missing brands in one migration, not just llama/yi).

Scope:
- 9 brands (llama, nvidia_nemo, doubao, yi, sensechat, exaone, kuaishou,
  sakana, upstage) inserted with INSERT OR IGNORE so re-apply is a no-op.
- accent_color / display_name_zh_cn populated where a Chinese (or
  Korean) name is conventional.
- No FK changes; the existing FK on posts_brands.brand_id already
  references brands.id.

Verifies:
- Happy path: all 9 nicknames are present in `brands` after 024.
- Idempotency: re-applying the migration does not duplicate rows.
- Integration: insert_posts succeeds for a post attributed to llama
  (the FK no longer fires).
- Regression: a fresh DB where 024 has been skipped still produces the
  FK-violation warning for these brand_ids (proves the test catches the
  pre-fix state).
- Full-stack apply: all on-disk migrations (including 024) apply cleanly.
"""

from __future__ import annotations

import pytest


# Brands the migration is responsible for inserting.
NEW_BRANDS: tuple[str, ...] = (
    "llama",
    "nvidia_nemo",
    "doubao",
    "yi",
    "sensechat",
    "exaone",
    "kuaishou",
    "sakana",
    "upstage")


# --- happy path: 9 brands are present after 024 ----------------------


def test_migration_024_brands_seeded(tmp_path):
    """After 024, all 9 v1.7 brands have a row in `brands`."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT nickname FROM brands ORDER BY nickname"
        ).fetchall()
        seeded = {r["nickname"] for r in rows}
        for b in NEW_BRANDS:
            assert b in seeded, (
                f"brand '{b}' missing after 024; have: {sorted(seeded)}"
            )
    finally:
        s.close()


def test_migration_024_brand_rows_have_display_name(tmp_path):
    """The seeded brands carry a non-empty display_name (operator-facing)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        for b in NEW_BRANDS:
            row = s._conn.execute(
                "SELECT display_name FROM brands WHERE nickname = ?", (b,)
            ).fetchone()
            assert row is not None, f"brand '{b}' not seeded"
            assert row["display_name"], (
                f"brand '{b}' has empty display_name"
            )
    finally:
        s.close()


def test_migration_024_unattributed_sentinel_preserved(tmp_path):
    """The `_unattributed` sentinel row (id=1, is_sentinel=1) survives."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        row = s._conn.execute(
            "SELECT id, is_sentinel FROM brands WHERE nickname = '_unattributed'"
        ).fetchone()
        assert row is not None, "_unattributed sentinel row missing"
        assert row["is_sentinel"] == 1, (
            f"_unattributed is_sentinel != 1: {row['is_sentinel']!r}"
        )
    finally:
        s.close()


# --- idempotency -----------------------------------------------------


def test_migration_024_idempotent(tmp_path):
    """Re-opening a DB with 024 applied does not re-run the migration,
    and does not duplicate the seeded rows."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s1 = Store(db, auto_migrate=True)
    try:
        # Capture seeded counts.
        before = {
            r["nickname"]: r["n"]
            for r in s1._conn.execute(
                "SELECT nickname, COUNT(*) AS n FROM brands "
                "GROUP BY nickname"
            ).fetchall()
        }
        for b in NEW_BRANDS:
            assert before.get(b, 0) == 1, f"brand '{b}' not exactly once pre-reopen"
    finally:
        s1.close()

    s2 = Store(db, auto_migrate=True)
    try:
        after = {
            r["nickname"]: r["n"]
            for r in s2._conn.execute(
                "SELECT nickname, COUNT(*) AS n FROM brands "
                "GROUP BY nickname"
            ).fetchall()
        }
        for b in NEW_BRANDS:
            assert after.get(b, 0) == 1, (
                f"brand '{b}' duplicated on re-open: count={after.get(b)}"
            )
    finally:
        s2.close()


# --- integration: FK on posts_brands no longer fires -----------------


def test_migration_024_posts_brands_insert_succeeds_for_llama(tmp_path, caplog):
    """End-to-end: a post attributed to `llama` writes to posts_brands
    without raising and without emitting the FK-violation warning.

    Pre-024, the FK on `posts_brands.brand_id REFERENCES brands(id)`
    would reject the write, and Store.insert_posts would log:
        "insert_posts: dropping posts_brands row for brand_id='llama'
         not in brands table"
    After 024, the warning is gone and the posts_brands row is written.
    """
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        # Capture the brand INTEGER id for `llama` so we can verify
        # the posts_brands row landed.
        llama_id = s._conn.execute(
            "SELECT id FROM brands WHERE nickname = 'llama'"
        ).fetchone()["id"]

        with caplog.at_level("WARNING"):
            s.insert_posts([
                {
                    "id": "t_llama_001",
                    "brand_id": "llama",
                    "text": "Llama 4 is great",
                },
            ])

        # The posts_brands row should now exist (no FK violation).
        row = s._conn.execute(
            "SELECT brand_id FROM posts_brands pb "
            "JOIN posts p ON p.id = pb.post_id "
            "WHERE p.tweet_id = 't_llama_001'"
        ).fetchone()
        assert row is not None, (
            "no posts_brands row for the llama post; "
            "the FK-violation-drop path may still be firing"
        )
        assert row["brand_id"] == llama_id, (
            f"wrong brand_id in posts_brands: got {row['brand_id']}, "
            f"expected {llama_id}"
        )

        # And no warning should have been logged for the FK violation.
        fk_warnings = [
            rec for rec in caplog.records
            if "dropping posts_brands row" in rec.getMessage()
            and "llama" in rec.getMessage()
        ]
        assert not fk_warnings, (
            f"unexpected FK-violation warnings: "
            f"{[r.getMessage() for r in fk_warnings]}"
        )
    finally:
        s.close()


def test_migration_024_posts_brands_insert_succeeds_for_all_new_brands(
    tmp_path, caplog
):
    """All 9 v1.7 brands now resolve to a posts_brands row when a post
    names them. Locks in that no brand in the new batch regresses."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        with caplog.at_level("WARNING"):
            for i, b in enumerate(NEW_BRANDS):
                s.insert_posts([
                    {
                        "id": f"t_{b}_{i}",
                        "brand_id": b,
                        "text": f"post about {b}",
                    },
                ])

        # All 9 posts_brands rows should be present.
        rows = s._conn.execute(
            "SELECT p.tweet_id, b.nickname FROM posts_brands pb "
            "JOIN posts p ON p.id = pb.post_id "
            "JOIN brands b ON b.id = pb.brand_id"
        ).fetchall()
        nicknames = {r["nickname"] for r in rows}
        for b in NEW_BRANDS:
            assert b in nicknames, (
                f"posts_brands row for '{b}' missing; "
                f"got nicknames: {sorted(nicknames)}"
            )

        # No FK-violation warnings for any new brand.
        fk_warnings = [
            rec.getMessage() for rec in caplog.records
            if "dropping posts_brands row" in rec.getMessage()
        ]
        assert not fk_warnings, (
            f"unexpected FK-violation warnings: {fk_warnings}"
        )
    finally:
        s.close()


# --- regression: pre-024 state would warn ----------------------------


def test_pre_024_state_emits_fk_violation_warning(tmp_path, caplog):
    """Lock in the test's ability to catch the regression class: on a
    DB where 024 has NOT been applied, `insert_posts` for a post
    attributed to a missing brand (e.g. `llama`) emits the FK
    violation warning that this unit is here to silence.

    Simulation strategy: open the Store with auto_migrate=True so the
    full schema (migrations 1-24) is in place, then DELETE the brands
    that 024 would have added and re-open. The fresh Store builds its
    brand-id cache from the post-delete state, so a subsequent
    `insert_posts` for `llama` will route through the FK-violation
    drop path.

    This locks in that any future regression (the migration is
    accidentally skipped, or a brand is removed from 024) is
    detectable.
    """
    from x_monitor.store import Store

    db = tmp_path / "x.db"

    # Apply the full schema (including 024) to seed the brands.
    s_seed = Store(db, auto_migrate=True)
    try:
        # Sanity check: 024 ran (so llama is seeded).
        row = s_seed._conn.execute(
            "SELECT 1 FROM brands WHERE nickname = 'llama'"
        ).fetchone()
        assert row is not None, "024 should have seeded `llama`"
    finally:
        s_seed.close()

    # Now simulate pre-024 by deleting the seeded brands. Use a
    # throwaway connection to avoid the brand_id_map cache on
    # s_seed._conn (which we just closed anyway).
    import sqlite3 as _sqlite3
    raw = _sqlite3.connect(db)
    try:
        raw.execute(
            "DELETE FROM brands WHERE nickname IN "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            NEW_BRANDS,
        )
        raw.commit()
        # Verify the delete took.
        cursor = raw.execute(
            "SELECT 1 FROM brands WHERE nickname = 'llama'"
        ).fetchone()
        assert cursor is None, "delete did not remove `llama`"
    finally:
        raw.close()

    # Re-open the Store from the post-delete state. The brand-id
    # cache will rebuild without `llama`.
    s = Store(db, auto_migrate=False)
    try:
        with caplog.at_level("WARNING"):
            s.insert_posts([
                {
                    "id": "t_pre_llama",
                    "brand_id": "llama",
                    "text": "Llama 4 is great",
                },
            ])

        # The warning that U3 is here to silence MUST appear.
        fk_warnings = [
            rec.getMessage() for rec in caplog.records
            if "dropping posts_brands row" in rec.getMessage()
            and "llama" in rec.getMessage()
        ]
        assert fk_warnings, (
            "expected the FK-violation warning for 'llama' to fire "
            "in the pre-024 state; got none"
        )
    finally:
        s.close()


# --- full-stack apply ------------------------------------------------


def test_migration_024_full_stack_apply(tmp_path):
    """All on-disk migrations (including 024) apply cleanly on a fresh DB."""
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
        # Compute expected from on-disk migrations so this test stays
        # accurate when other migrations are added (021 is reserved —
        # intentionally absent).
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
        assert 24 in applied, "migration 024 not applied"
    finally:
        s.close()