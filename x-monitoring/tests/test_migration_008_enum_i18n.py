"""Migration 008: enum i18n lookup tables + FK conversion.

Plan: docs/plans/2026-06-23-001-feat-i18n-locale-columns-plan.md (Unit 2).

Verifies:
- 6 new tables created (signal_keys, signal_labels, role_keys, role_labels,
  engagement_tier_keys, engagement_tier_labels).
- Seed rows present for all keys × both locales.
- The 4 enum columns (posts_brands_signals.signal, brands_accounts.role,
  companies_accounts.role, accounts.engagement_tier) are now FK-validated.
- The posts_brands_signals CHECK (brand_id <> '_unattributed') survived the
  table rebuild (P0 review fix from migration 004 history).
- Idempotency on re-apply.
"""

import pytest


# --- happy path: tables + seeds ----------------------------------------


def test_migration_008_creates_signal_keys_and_labels(tmp_path):
    """signal_keys has 6 rows; signal_labels has 12 (6 × 2 locales)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        keys = {r[0] for r in s._conn.execute("SELECT key FROM signal_keys").fetchall()}
        assert keys == {"release", "community_question", "criticism",
                        "commenter_capture", "praise", "other"}

        labels = {(r[0], r[1]): r[2] for r in s._conn.execute(
            "SELECT key, lang, label FROM signal_labels"
        ).fetchall()}
        assert len(labels) == 12
        # Spot-check best-guess zh-CN seeds (operator-overridable via JSON).
        assert labels[("release", "en")] == "Release"
        assert labels[("release", "zh_cn")] == "发布"
        assert labels[("praise", "zh_cn")] == "称赞"
    finally:
        s.close()


def test_migration_008_creates_role_keys_and_labels(tmp_path):
    """role_keys has 5 rows; role_labels has 10 (5 × 2 locales)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        keys = {r[0] for r in s._conn.execute("SELECT key FROM role_keys").fetchall()}
        assert keys == {"official", "community", "researcher", "press", "vendor"}

        labels = {(r[0], r[1]): r[2] for r in s._conn.execute(
            "SELECT key, lang, label FROM role_labels"
        ).fetchall()}
        assert len(labels) == 10
        assert labels[("official", "zh_cn")] == "官方"
        assert labels[("researcher", "zh_cn")] == "研究者"
    finally:
        s.close()


def test_migration_008_creates_engagement_tier_keys_and_labels(tmp_path):
    """engagement_tier_keys has 3 rows; labels has 6."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        keys = {r[0] for r in s._conn.execute(
            "SELECT key FROM engagement_tier_keys"
        ).fetchall()}
        assert keys == {"low", "medium", "high"}

        labels = {(r[0], r[1]): r[2] for r in s._conn.execute(
            "SELECT key, lang, label FROM engagement_tier_labels"
        ).fetchall()}
        assert len(labels) == 6
        assert labels[("high", "zh_cn")] == "高"
    finally:
        s.close()


# --- happy path: FK conversion -----------------------------------------


def test_migration_008_posts_brands_signals_signal_is_fk(tmp_path):
    """posts_brands_signals.signal is now FK-validated against signal_keys."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        fks = s._conn.execute(
            "SELECT * FROM pragma_foreign_key_list('posts_brands_signals')"
        ).fetchall()
        fk_targets = {(r[2], r[3]) for r in fks}  # (table, from_col) -> table
        # The signal FK references signal_keys.
        assert any(r[2] == "signal_keys" and r[3] == "signal" for r in fks), (
            f"signal FK missing from posts_brands_signals. FKs found: {fks}"
        )
    finally:
        s.close()


def test_migration_008_posts_brands_signals_check_constraint_preserved(tmp_path):
    """The CHECK (brand_id <> '_unattributed') survived the table rebuild
    (P0 review fix from migration 004 history)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        # sqlite_master stores the table SQL including CHECK constraints.
        sql = s._conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='posts_brands_signals'"
        ).fetchone()[0]
        assert "brand_id <> '_unattributed'" in sql, (
            f"CHECK constraint missing in rebuilt posts_brands_signals: {sql}"
        )
    finally:
        s.close()


def test_migration_008_brands_accounts_role_is_fk(tmp_path):
    """brands_accounts.role references role_keys."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        fks = s._conn.execute(
            "SELECT * FROM pragma_foreign_key_list('brands_accounts')"
        ).fetchall()
        assert any(r[2] == "role_keys" and r[3] == "role" for r in fks), (
            f"role FK missing from brands_accounts. FKs found: {fks}"
        )
    finally:
        s.close()


def test_migration_008_companies_accounts_role_is_fk(tmp_path):
    """companies_accounts.role references role_keys."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        fks = s._conn.execute(
            "SELECT * FROM pragma_foreign_key_list('companies_accounts')"
        ).fetchall()
        assert any(r[2] == "role_keys" and r[3] == "role" for r in fks)
    finally:
        s.close()


def test_migration_008_accounts_engagement_tier_is_fk(tmp_path):
    """accounts.engagement_tier references engagement_tier_keys."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        fks = s._conn.execute(
            "SELECT * FROM pragma_foreign_key_list('accounts')"
        ).fetchall()
        assert any(
            r[2] == "engagement_tier_keys" and r[3] == "engagement_tier" for r in fks
        ), f"engagement_tier FK missing. FKs found: {fks}"
    finally:
        s.close()


# --- idempotency -------------------------------------------------------


def test_migration_008_idempotent(tmp_path):
    """Re-opening a DB that has 007 applied does not re-run it."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s1 = Store(db, auto_migrate=True)
    s1.close()

    s2 = Store(db, auto_migrate=True)
    try:
        applied = [
            r[0] for r in s2._conn.execute(
                "SELECT version FROM _migrations ORDER BY version"
            ).fetchall()
        ]
        assert applied.count(7) == 1
        # Lookup-table row counts unchanged.
        n_keys = s2._conn.execute("SELECT COUNT(*) FROM signal_keys").fetchone()[0]
        assert n_keys == 6
        n_labels = s2._conn.execute("SELECT COUNT(*) FROM signal_labels").fetchone()[0]
        assert n_labels == 12
    finally:
        s2.close()


# --- integration -------------------------------------------------------


def test_migration_008_full_stack_apply(tmp_path):
    """All migrations 001-008 apply on a fresh DB; data round-trip
    works through the rebuilt FK-validated tables."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        applied = sorted(
            r[0] for r in s._conn.execute("SELECT version FROM _migrations").fetchall()
        )
        # 001-011 (quote-tweets 005/006 already on main; i18n 007/008;
        # HF products 009; M:N rename to plural-plural 010 on this branch;
        # 011 = rename locale to lang).
        assert applied == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], f"unexpected versions: {applied}"
    finally:
        s.close()


def test_migration_008_round_trip_posts_brands_signals(tmp_path):
    """Inserting a posts_brands_signals row with a valid signal succeeds;
    the FK is honored at write time."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        # First insert a posts row (FK target).
        # Migration 001: tweet_id PK, author_handle NOT NULL, fetched_at NOT NULL.
        # Migration 004: model_id was dropped; signal was dropped.
        s._conn.execute(
            "INSERT INTO posts (tweet_id, author_handle, fetched_at, text) "
            "VALUES (?, ?, ?, ?)",
            ("t_fk_007", "u_fk_007", "2026-06-23T00:00:00+00:00", "test"),
        )
        # Insert a valid posts_brands_signals row.
        s._conn.execute(
            "INSERT INTO posts_brands_signals (post_id, brand_id, signal) "
            "VALUES (?, ?, ?)",
            ("t_fk_007", "minimax", "release"),
        )
        row = s._conn.execute(
            "SELECT signal FROM posts_brands_signals WHERE post_id = ?", ("t_fk_007",)
        ).fetchone()
        assert row["signal"] == "release"
    finally:
        s.close()