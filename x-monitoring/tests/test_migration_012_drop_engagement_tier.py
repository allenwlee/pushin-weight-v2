"""Migration 012: drop engagement_tier_keys + engagement_tier_labels; remove
engagement_tier column from accounts.

Plan: docs/plans/2026-06-24-002-refactor-schema-modernization-batch-plan.md
(Unit 2 of 9, R2).

Verifies:
- engagement_tier_keys / engagement_tier_labels do not exist after migration.
- accounts has no engagement_tier column after migration.
- accounts still has the other expected columns (handle, bio_en, etc.).
- The backfill partial indexes on bio_en / bio_zh_cn are preserved.
- Idempotency: re-opening a DB that has 012 applied does not re-run it.
- Full stack apply: all migrations 001-012 apply on a fresh DB; the
  engagement_tier artifacts are gone.
- Integration: `upsert_account` no longer takes an engagement_tier
  parameter; calling it without the kwarg still writes a valid row.
- Integration: `_pick_enum_label` rejects "engagement_tier" as an
  unknown family (post-drop, the family no longer exists).
- Integration: `_known_engagement_tier_keys` is removed from the
  Store API.
"""

import pytest


# --- happy path: tables dropped ---------------------------------------


def test_migration_012_engagement_tier_keys_dropped(tmp_path):
    """engagement_tier_keys does not exist after migration 012."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT name FROM sqlite_master WHERE name = 'engagement_tier_keys'"
        ).fetchall()
        assert rows == [], (
            f"engagement_tier_keys still exists: {rows}"
        )
    finally:
        s.close()


def test_migration_012_engagement_tier_labels_dropped(tmp_path):
    """engagement_tier_labels does not exist after migration 012."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT name FROM sqlite_master WHERE name = 'engagement_tier_labels'"
        ).fetchall()
        assert rows == [], (
            f"engagement_tier_labels still exists: {rows}"
        )
    finally:
        s.close()


# --- happy path: column removed from accounts ------------------------


def test_migration_012_accounts_has_no_engagement_tier_column(tmp_path):
    """accounts has no engagement_tier column after migration 012."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        cols = {
            r[1] for r in s._conn.execute("PRAGMA table_info(accounts)").fetchall()
        }
        assert "engagement_tier" not in cols, (
            f"accounts still has engagement_tier column. cols={cols}"
        )
    finally:
        s.close()


def test_migration_012_accounts_preserves_other_columns(tmp_path):
    """The accounts table rebuild preserves all other columns (handle,
    bio_en, bio_zh_cn, etc.). The schema shape is unchanged except for
    the dropped engagement_tier column."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        cols = {
            r[1] for r in s._conn.execute("PRAGMA table_info(accounts)").fetchall()
        }
        expected = {
            "author_id", "handle", "display_name", "bio", "bio_fetched_at",
            "verified", "bio_contains_brand",
            "first_seen_at", "last_seen_at", "source_query_ids", "notes",
            "bio_en", "bio_zh_cn",
        }
        missing = expected - cols
        assert not missing, f"accounts missing expected columns: {missing}"
    finally:
        s.close()


def test_migration_012_accounts_bio_backfill_indexes_preserved(tmp_path):
    """The backfill partial indexes on accounts.bio_en / bio_zh_cn
    survive the table rebuild (these were created in migration 007
    and must persist across the 012 rebuild)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        indexes = {
            r[0]
            for r in s._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='accounts'"
            ).fetchall()
        }
        assert "idx_accounts_bio_en_backfill" in indexes, (
            f"idx_accounts_bio_en_backfill missing. indexes={indexes}"
        )
        assert "idx_accounts_bio_zh_cn_backfill" in indexes, (
            f"idx_accounts_bio_zh_cn_backfill missing. indexes={indexes}"
        )
    finally:
        s.close()


# --- happy path: no FK to engagement_tier_keys -----------------------


def test_migration_012_accounts_has_no_engagement_tier_fk(tmp_path):
    """accounts has no FK to engagement_tier_keys after migration 012."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        fks = s._conn.execute(
            "SELECT * FROM pragma_foreign_key_list('accounts')"
        ).fetchall()
        assert not any(
            r[2] == "engagement_tier_keys" for r in fks
        ), f"accounts still has FK to engagement_tier_keys. FKs found: {fks}"
    finally:
        s.close()


# --- idempotency ------------------------------------------------------


def test_migration_012_idempotent(tmp_path):
    """Re-opening a DB that has 012 applied does not re-run it (the
    _migrations ledger records version 12 exactly once)."""
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
        assert applied.count(12) == 1
    finally:
        s2.close()


# --- full stack apply -------------------------------------------------


def test_migration_012_full_stack_apply(tmp_path):
    """All migrations 001-012 apply on a fresh DB; the engagement_tier
    artifacts are gone; the remaining 4 i18n tables are intact."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        applied = sorted(
            r[0]
            for r in s._conn.execute("SELECT version FROM _migrations").fetchall()
        )
        # 001-015: 005/006 = quote-tweets; 007 = i18n locale columns;
        # 008 = enum i18n lookup tables; 009 = products;
        # 010 = M:N rename to plural-plural;
        # 011 = rename locale to lang;
        # 012 = drop engagement_tier tables;
        # 013 = rename post_mentions to posts_brands_mentions;
        # 014 = rename signal_keys to signals;
        # 015 = rename role_keys to roles.
        assert applied == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15], (
            f"unexpected versions: {applied}"
        )

        # engagement_tier artifacts are gone.
        for tbl in ("engagement_tier_keys", "engagement_tier_labels"):
            rows = s._conn.execute(
                "SELECT name FROM sqlite_master WHERE name = ?", (tbl,)
            ).fetchall()
            assert rows == [], f"{tbl} still exists: {rows}"

        # Remaining 4 i18n tables are intact.
        # (signal_keys was renamed to signals in 014; role_keys is still
        # role_keys was renamed to roles in 015.)
        for tbl in ("signals", "signal_labels", "roles", "role_labels"):
            rows = s._conn.execute(
                "SELECT name FROM sqlite_master WHERE name = ?", (tbl,)
            ).fetchall()
            assert rows, f"{tbl} missing"
    finally:
        s.close()


# --- integration: upsert_account no longer takes engagement_tier -----


def test_migration_012_upsert_account_works_without_engagement_tier(tmp_path):
    """upsert_account no longer accepts an engagement_tier kwarg; the
    call without that arg still writes a valid accounts row and the
    matching brands_accounts edge."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        # No engagement_tier kwarg — call works as before for the
        # remaining fields.
        s.upsert_account("minimax", "u_post_012", role="official")
        row = s._conn.execute(
            "SELECT handle FROM accounts WHERE author_id = ?",
            ("handle:u_post_012",),
        ).fetchone()
        assert row is not None
        assert row["handle"] == "u_post_012"

        # brands_accounts edge was written for the known role.
        ba = s._conn.execute(
            "SELECT role_id FROM brands_accounts WHERE author_id = ?",
            ("handle:u_post_012",),
        ).fetchone()
        assert ba["role_id"] == "official"
    finally:
        s.close()


# --- integration: _pick_enum_label rejects engagement_tier -----------


def test_migration_012_pick_enum_label_rejects_engagement_tier(tmp_path):
    """_pick_enum_label rejects 'engagement_tier' as an unknown family
    (the family was removed in 012). The post-012 families are
    'signal' and 'role' only."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        with pytest.raises(ValueError, match="unknown enum family"):
            s._pick_enum_label("engagement_tier", "high", "en")
    finally:
        s.close()


# --- integration: _known_engagement_tier_keys removed ----------------


def test_migration_012_known_engagement_tier_keys_removed(tmp_path):
    """The _known_engagement_tier_keys method is removed from the Store
    API; calling it raises AttributeError."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        assert not hasattr(s, "_known_engagement_tier_keys"), (
            "Store still has _known_engagement_tier_keys method after 012"
        )
    finally:
        s.close()
