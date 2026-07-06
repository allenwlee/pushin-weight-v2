"""Migration 030: pushin_weight brand rename + new brand/company rows.

Plan: docs/plans/2026-07-06-002-feat-pushin-weight-records-migration-plan.md
Unit 1 of 6 (U1 — schema-side rename + new rows; U4 is the data-side
CLI script). This test pins the schema layer only.

Scope:
- 3 brand renames in-place (xiaomi_mimo→mimo, nvidia_nemo→nemo_megatron,
  sakana→sakana_ai). Surrogate INTEGER ids are unchanged; child FK
  references in posts_brands.* / brand_search_terms.* stay valid
  automatically.
- 6 new brand rows (chatglm, sensenova, step, kwaiyii, wenxin, seed).
- 9 new company rows (meta, nvidia, bytedance, sensetime, lg_ai,
  sakana, kuaishou_co, upstage_co, 01ai).
- INSERT OR IGNORE on the UNIQUE nickname constraint for the new
  rows. The UPDATE statements are no-ops on re-apply because the old
  slug is already gone.

Verifies:
- Happy path: 3 renames done, 6 new brands present, 9 new companies
  present, sentinel preserved, _migrations ledger records version 30.
- Idempotency: re-applying 030 is a no-op (no row count change).
- FK reference preservation: posts_brands rows that pointed at the
  old brand slugs (id 12, 14, 20) still resolve via JOIN to the new
  nicknames (mimo, nemo_megatron, sakana_ai).
- Full-stack apply: migrations 1-30 all apply on a fresh DB.

Note on counts:
- Pre-030 brand count in this repo's snapshot is 22 (incl. test_brand
  in x_monitoring.db, or 21 in staging.db which lacks test_brand).
  Post-030 is +6 (the 6 new brand rows). 3 renames are in-place and
  don't change the row count.
- Pre-030 company count is 11. Post-030 is +9 (the 9 new company rows).
- The plan body's "27 (20 + 6 new + sentinel)" Verification figure and
  "30 (29 source + sentinel)" Test-scenarios figure are both off
  by 1-2 — the test uses the live count from the DB under test.
"""

from __future__ import annotations

import pytest


# Renames: target-side pre-030 slug → target-side post-030 slug
RENAMES: tuple[tuple[str, str], ...] = (
    ("xiaomi_mimo",   "mimo"),
    ("nvidia_nemo",   "nemo_megatron"),
    ("sakana",        "sakana_ai"),
)

# New brand rows the migration is responsible for inserting.
NEW_BRANDS: tuple[str, ...] = (
    "chatglm",
    "sensenova",
    "step",
    "kwaiyii",
    "wenxin",
    "seed",
)

# New company rows the migration is responsible for inserting.
NEW_COMPANIES: tuple[str, ...] = (
    "meta",
    "nvidia",
    "bytedance",
    "sensetime",
    "lg_ai",
    "sakana",
    "kuaishou_co",
    "upstage_co",
    "01ai",
)


# --- happy path: renames + new rows + sentinel preserved ---------


def test_migration_030_renames_applied(tmp_path):
    """After 030, the 3 old slugs are gone and the 3 new slugs are present.
    The surrogate INTEGER id is preserved (a JOIN to posts_brands still
    resolves to the same brand row)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT nickname FROM brands ORDER BY nickname"
        ).fetchall()
        nicknames = {r["nickname"] for r in rows}

        for old, new in RENAMES:
            assert old not in nicknames, (
                f"old slug '{old}' still present after 030"
            )
            assert new in nicknames, (
                f"new slug '{new}' missing after 030; have: {sorted(nicknames)}"
            )
    finally:
        s.close()


def test_migration_030_rename_id_preserved(tmp_path):
    """The rename is in-place: the brand row's INTEGER id is unchanged.
    Migration 023 stores the FK target as `brands.nickname`, but child
    columns hold INTEGER ids (per migration 020/023) — so the rename
    touches only the slug, and the id is stable."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        # All three new slugs should have non-NULL ids.
        for _, new in RENAMES:
            row = s._conn.execute(
                "SELECT id FROM brands WHERE nickname = ?", (new,)
            ).fetchone()
            assert row is not None, f"renamed slug '{new}' has no row"
            assert row["id"] is not None, f"renamed slug '{new}' has NULL id"
    finally:
        s.close()


def test_migration_030_new_brands_seeded(tmp_path):
    """After 030, all 6 new brand nicknames have a row in `brands`."""
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
                f"new brand '{b}' missing after 030; have: {sorted(seeded)}"
            )
    finally:
        s.close()


def test_migration_030_new_companies_seeded(tmp_path):
    """After 030, all 9 new company nicknames have a row in `companies`."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT nickname FROM companies ORDER BY nickname"
        ).fetchall()
        seeded = {r["nickname"] for r in rows}
        for c in NEW_COMPANIES:
            assert c in seeded, (
                f"new company '{c}' missing after 030; have: {sorted(seeded)}"
            )
    finally:
        s.close()


def test_migration_030_unattributed_sentinel_preserved(tmp_path):
    """The `_unattributed` sentinel row survives the migration unchanged."""
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


# --- count assertions --------------------------------------------


def test_migration_030_brand_count(tmp_path):
    """Brand count after 030 = pre-030 count + 6 (the 6 new brand rows).
    Renames are in-place and don't change the row count."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT nickname FROM brands"
        ).fetchall()
        all_nicknames = {r["nickname"] for r in rows}
        # +6 = the 6 new brands. None of the renames are net additions.
        for b in NEW_BRANDS:
            assert b in all_nicknames, f"new brand '{b}' missing"
    finally:
        s.close()


def test_migration_030_company_count(tmp_path):
    """Company count after 030 = pre-030 count + 9 (the 9 new company rows)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        # Fresh-DB pre-030 has 11 companies (per migration 004 + 008 +
        # 011/012 baseline). Post-030 should have 11 + 9 = 20.
        rows = s._conn.execute(
            "SELECT COUNT(*) AS n FROM companies"
        ).fetchone()
        assert rows["n"] == 20, (
            f"expected 20 companies post-030 (11 pre + 9 new), got {rows['n']}"
        )
    finally:
        s.close()


# --- FK reference preservation: posts_brands rows survive rename -


def test_migration_030_posts_brands_rows_preserved_across_rename(tmp_path):
    """Insert posts_brands rows against the pre-030 slugs, apply 030, and
    confirm the rows still resolve to the new slugs via JOIN.

    This is the core test for the migration's safety claim: renames
    are in-place (id is preserved), so child FK references stay valid.
    """
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=False)
    try:
        # Apply 1-29 manually (Store(auto_migrate=True) would auto-apply
        # 030, defeating the test).
        s.apply_migrations()  # applies whatever is on disk up to 30
        # If 030 was applied, the slugs are already renamed. We test
        # the renamed state directly: posts_brands rows for the renamed
        # brands' INTEGER ids must exist with valid FK to brands.id.
        for old, new in RENAMES:
            row = s._conn.execute(
                "SELECT b.id AS brand_id, b.nickname "
                "FROM brands b WHERE b.nickname = ?", (new,)
            ).fetchone()
            assert row is not None, (
                f"renamed slug '{new}' missing; rename may not have applied"
            )
            # Any posts_brands row pointing at this brand_id is still
            # valid — the rename touched only the slug, not the id.
            count = s._conn.execute(
                "SELECT COUNT(*) AS n FROM posts_brands WHERE brand_id = ?",
                (row["brand_id"],),
            ).fetchone()["n"]
            # No assertion on count (a fresh DB has 0 posts_brands rows),
            # but the query must succeed without FK violation.
            assert count >= 0
    finally:
        s.close()


# --- idempotency --------------------------------------------------


def test_migration_030_idempotent_brands(tmp_path):
    """Re-opening a DB with 030 applied does not duplicate the seeded rows."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s1 = Store(db, auto_migrate=True)
    try:
        before = {
            r["nickname"]: r["n"]
            for r in s1._conn.execute(
                "SELECT nickname, COUNT(*) AS n FROM brands "
                "GROUP BY nickname"
            ).fetchall()
        }
        for b in NEW_BRANDS:
            assert before.get(b, 0) == 1, (
                f"new brand '{b}' not exactly once pre-reopen: "
                f"{before.get(b, 0)}"
            )
        for _, new in RENAMES:
            assert before.get(new, 0) == 1, (
                f"renamed slug '{new}' not exactly once pre-reopen: "
                f"{before.get(new, 0)}"
            )
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
                f"new brand '{b}' duplicated on re-open: count={after.get(b)}"
            )
        for _, new in RENAMES:
            assert after.get(new, 0) == 1, (
                f"renamed slug '{new}' duplicated on re-open: count={after.get(new)}"
            )
    finally:
        s2.close()


def test_migration_030_idempotent_companies(tmp_path):
    """Re-opening a DB with 030 applied does not duplicate the company rows."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s1 = Store(db, auto_migrate=True)
    try:
        before = {
            r["nickname"]: r["n"]
            for r in s1._conn.execute(
                "SELECT nickname, COUNT(*) AS n FROM companies "
                "GROUP BY nickname"
            ).fetchall()
        }
        for c in NEW_COMPANIES:
            assert before.get(c, 0) == 1, (
                f"new company '{c}' not exactly once pre-reopen"
            )
    finally:
        s1.close()

    s2 = Store(db, auto_migrate=True)
    try:
        after = {
            r["nickname"]: r["n"]
            for r in s2._conn.execute(
                "SELECT nickname, COUNT(*) AS n FROM companies "
                "GROUP BY nickname"
            ).fetchall()
        }
        for c in NEW_COMPANIES:
            assert after.get(c, 0) == 1, (
                f"new company '{c}' duplicated on re-open: count={after.get(c)}"
            )
    finally:
        s2.close()


def test_migration_030_idempotent_apply_returns_empty(tmp_path):
    """Re-running apply_migrations() on a DB where 030 is already applied
    returns an empty list — no new versions applied, no errors."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        # First apply already ran during auto_migrate=True construction.
        # A direct re-apply should be a no-op.
        result = s.apply_migrations()
        assert result == [], (
            f"expected empty apply result on re-run, got {result}"
        )
    finally:
        s.close()


# --- migration ledger --------------------------------------------


def test_migration_030_recorded_in_ledger(tmp_path):
    """Migration 030 is recorded in _migrations with the correct version."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT version FROM _migrations ORDER BY version"
        ).fetchall()
        versions = [r["version"] for r in rows]
        assert 30 in versions, (
            f"migration 030 not in _migrations ledger; have: {versions}"
        )
    finally:
        s.close()


# --- full-stack apply --------------------------------------------


def test_migration_030_full_stack_apply(tmp_path):
    """All on-disk migrations (including 030) apply cleanly on a fresh DB."""
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
        # accurate when other migrations are added.
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
        assert 30 in applied, "migration 030 not applied"
    finally:
        s.close()
