"""Migration 007: i18n locale columns on brands / companies / accounts.

Plan: docs/plans/2026-06-23-001-feat-i18n-locale-columns-plan.md (Unit 1).
Verifies the additive ALTER TABLE statements land cleanly and the
backfill-friendly partial indexes exist.

NOTE: This migration was originally numbered 006. It was renumbered to
007 at rebase time (2026-06-23) because main had just received
migrations 005_quoted_text.sql + 006_quote_capture_tracking.sql from
the quote-tweets branch.

Plan: docs/plans/2026-06-23-001-feat-i18n-locale-columns-plan.md (Unit 1).
Verifies the additive ALTER TABLE statements land cleanly and the
backfill-friendly partial indexes exist.
"""

import pytest


# --- happy path --------------------------------------------------------


def test_migration_007_adds_display_name_columns_to_brands(tmp_path):
    """After migration 007, brands has display_name_en and display_name_zh_cn."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        cols = {r[1] for r in s._conn.execute("PRAGMA table_info(brands)").fetchall()}
        assert "display_name_en" in cols
        assert "display_name_zh_cn" in cols
        # Source column retained as fallback.
        assert "display_name" in cols
        # Migration recorded.
        applied = {r[0] for r in s._conn.execute("SELECT version FROM _migrations").fetchall()}
        assert 6 in applied
    finally:
        s.close()


def test_migration_007_adds_display_name_columns_to_companies(tmp_path):
    """After migration 007, companies has display_name_en and display_name_zh_cn."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        cols = {r[1] for r in s._conn.execute("PRAGMA table_info(companies)").fetchall()}
        assert "display_name_en" in cols
        assert "display_name_zh_cn" in cols
        assert "display_name" in cols
    finally:
        s.close()


def test_migration_007_adds_bio_columns_to_accounts(tmp_path):
    """After migration 007, accounts has bio_en and bio_zh_cn."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        cols = {r[1] for r in s._conn.execute("PRAGMA table_info(accounts)").fetchall()}
        assert "bio_en" in cols
        assert "bio_zh_cn" in cols
        # Source bio retained as fallback.
        assert "bio" in cols
    finally:
        s.close()


def test_migration_007_creates_partial_backfill_indexes(tmp_path):
    """Partial indexes with WHERE <col>_<locale> IS NULL exist for the
    backfill driver (translator.translate_registry_rows)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        idx_rows = s._conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        ).fetchall()
        names = {r[0] for r in idx_rows}
        expected = {
            "idx_brands_display_name_en_backfill",
            "idx_brands_display_name_zh_cn_backfill",
            "idx_companies_display_name_en_backfill",
            "idx_companies_display_name_zh_cn_backfill",
            "idx_accounts_bio_en_backfill",
            "idx_accounts_bio_zh_cn_backfill",
        }
        assert expected.issubset(names), (
            f"missing backfill indexes: {expected - names}"
        )
    finally:
        s.close()


# --- idempotency -------------------------------------------------------


def test_migration_007_idempotent(tmp_path):
    """Re-opening a DB that already has 007 applied does not re-run it."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s1 = Store(db, auto_migrate=True)
    s1.close()

    s2 = Store(db, auto_migrate=True)
    try:
        applied = [
            r[0]
            for r in s2._conn.execute(
                "SELECT version FROM _migrations ORDER BY version"
            ).fetchall()
        ]
        assert applied.count(7) == 1
        # No duplicate columns either (would have raised on second apply).
        cols = {r[1] for r in s2._conn.execute("PRAGMA table_info(brands)").fetchall()}
        assert "display_name_en" in cols
        assert "display_name_zh_cn" in cols
    finally:
        s2.close()


# --- integration -------------------------------------------------------


def test_migration_007_full_stack_apply(tmp_path):
    """All migrations 001-007 apply cleanly on a fresh DB; partial indexes
    exist; _resolve_locale() pipeline still works."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        applied = sorted(
            r[0] for r in s._conn.execute("SELECT version FROM _migrations").fetchall()
        )
        # 001-012 should all be present on a fresh DB. Quote-tweets migrations
        # 005 + 006 are now part of main (merged 2026-06-23). HF 009 lives on
        # feat/hf-products-crawler (this branch, just rebased + renumbered).
        # M:N rename to plural-plural 010 added on this branch.
        # 011 = rename locale to lang.
        # 012 = drop engagement_tier tables.
        assert applied == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12], f"unexpected versions: {applied}"
        # Verify the brand seed from migration 004 still readable.
        row = s._conn.execute(
            "SELECT brand_id, display_name FROM brands WHERE brand_id = 'minimax'"
        ).fetchone()
        assert row is not None
        assert row["display_name"] == "MiniMax AI"
    finally:
        s.close()


# --- fallback chain exercised via SELECT (no helpers yet) --------------


def test_migration_007_null_locale_columns_default(tmp_path):
    """Existing rows have NULL on the new columns (forward-only, no
    backfill in SQL). The dashboard's fallback chain (D6) returns the
    source display_name / bio when the locale column is NULL."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT display_name, display_name_en, display_name_zh_cn FROM brands WHERE brand_id = 'minimax'"
        ).fetchall()
        assert len(rows) == 1
        row = rows[0]
        assert row["display_name"] == "MiniMax AI"
        assert row["display_name_en"] is None
        assert row["display_name_zh_cn"] is None
    finally:
        s.close()