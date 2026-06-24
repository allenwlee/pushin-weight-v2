"""Migration 011: rename `locale` columns to `lang` on the i18n label tables.

Plan: docs/plans/2026-06-24-002-refactor-schema-modernization-batch-plan.md
(Unit 1 of 9, R1).

Verifies:
- All 3 `*_labels` tables (signal_labels, role_labels,
  engagement_tier_labels) have a `lang` column after migration 011 runs.
- None of them have a `locale` column.
- The composite PRIMARY KEY (key, lang) is intact.
- Seed rows are preserved across the column rename.
- Idempotency: re-opening a DB that has 011 applied does not re-run it.
- Full stack apply: all migrations 001-011 apply on a fresh DB; the
  `lang` column is present on all `*_labels` tables.
- Integration: `_pick_enum_label` returns the expected localized label
  for a (family, value, lang) lookup; a query against the old `locale`
  column name raises.
"""

import pytest


# --- happy path: column renamed ---------------------------------------


def test_migration_011_signal_labels_has_lang_column(tmp_path):
    """signal_labels has a `lang` column and no `locale` column."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        cols = {
            r[1]
            for r in s._conn.execute("PRAGMA table_info(signal_labels)").fetchall()
        }
        assert "lang" in cols, f"signal_labels missing `lang` column. cols={cols}"
        assert "locale" not in cols, (
            f"signal_labels still has `locale` column. cols={cols}"
        )
    finally:
        s.close()


def test_migration_011_role_labels_has_lang_column(tmp_path):
    """role_labels has a `lang` column and no `locale` column."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        cols = {
            r[1]
            for r in s._conn.execute("PRAGMA table_info(role_labels)").fetchall()
        }
        assert "lang" in cols, f"role_labels missing `lang` column. cols={cols}"
        assert "locale" not in cols, (
            f"role_labels still has `locale` column. cols={cols}"
        )
    finally:
        s.close()


# --- happy path: composite PK preserved + seed rows intact -----------


def test_migration_011_pk_preserved_signal_labels(tmp_path):
    """The composite PRIMARY KEY (key, lang) on signal_labels is intact
    after the column rename; 12 seed rows (6 keys x 2 locales) are present."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        sql = s._conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='signal_labels'"
        ).fetchone()[0]
        assert "PRIMARY KEY (key, lang)" in sql, (
            f"PK (key, lang) missing in signal_labels: {sql}"
        )

        rows = s._conn.execute("SELECT key, lang, label FROM signal_labels").fetchall()
        assert len(rows) == 12
        # Spot-check best-guess zh-CN seeds.
        labels = {(r[0], r[1]): r[2] for r in rows}
        assert labels[("release", "en")] == "Release"
        assert labels[("release", "zh_cn")] == "发布"
        assert labels[("praise", "zh_cn")] == "称赞"
    finally:
        s.close()


def test_migration_011_pk_preserved_role_labels(tmp_path):
    """The composite PRIMARY KEY (key, lang) on role_labels is intact;
    6 seed rows (3 keys x 2 locales) are present (post-U6 trim in 016)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        sql = s._conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='role_labels'"
        ).fetchone()[0]
        assert "PRIMARY KEY (key, lang)" in sql, (
            f"PK (key, lang) missing in role_labels: {sql}"
        )

        rows = s._conn.execute("SELECT key, lang, label FROM role_labels").fetchall()
        assert len(rows) == 6
        labels = {(r[0], r[1]): r[2] for r in rows}
        assert labels[("official", "zh_cn")] == "官方"
        assert labels[("staff", "zh_cn")] == "员工"
    finally:
        s.close()


# --- idempotency ------------------------------------------------------


def test_migration_011_idempotent(tmp_path):
    """Re-opening a DB that has 011 applied does not re-run it (the
    _migrations ledger records version 11 exactly once)."""
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
        assert applied.count(11) == 1
        # Seed row counts unchanged.
        n_labels = s2._conn.execute("SELECT COUNT(*) FROM signal_labels").fetchone()[0]
        assert n_labels == 12
    finally:
        s2.close()


# --- full stack apply -------------------------------------------------


def test_migration_011_full_stack_apply(tmp_path):
    """All migrations 001-011 apply on a fresh DB; the `lang` column is
    present on all 3 `*_labels` tables."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        applied = sorted(
            r[0]
            for r in s._conn.execute("SELECT version FROM _migrations").fetchall()
        )
        # 001-017: 005/006 = quote-tweets (already on this branch's base);
        # 007 = i18n locale columns; 008 = enum i18n lookup tables;
        # 009 = products; 010 = M:N rename to plural-plural;
        # 011 = rename locale to lang; 012 = drop engagement_tier tables;
        # 013 = rename post_mentions to posts_brands_mentions;
        # 014 = rename signal_keys to signals;
        # 015 = rename role_keys to roles;
        # 016 = trim role values to {official, staff, community};
        # 017 = brand_search_terms hybrid by design (no-op DDL).
        assert applied == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17], (
            f"unexpected versions: {applied}"
        )

        # After 012, engagement_tier_labels is dropped; only signal_labels
        # and role_labels should still have the `lang` column.
        for tbl in ("signal_labels", "role_labels"):
            cols = {
                r[1] for r in s._conn.execute(f"PRAGMA table_info({tbl})").fetchall()
            }
            assert "lang" in cols, f"{tbl} missing `lang` column. cols={cols}"
            assert "locale" not in cols, f"{tbl} still has `locale` column. cols={cols}"
    finally:
        s.close()


# --- integration: _pick_enum_label honors the renamed column ---------


def test_migration_011_pick_enum_label_returns_zh_cn_label(tmp_path):
    """_pick_enum_label('signal', 'release', 'zh_cn') returns the zh_cn
    label after the column rename. This exercises the full
    code path through store.py line 1363 (the SQL string that was
    updated from `locale = ?` to `lang = ?`)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        assert s._pick_enum_label("signal", "release", "zh_cn") == "发布"
        assert s._pick_enum_label("signal", "release", "en") == "Release"
        assert s._pick_enum_label("role", "official", "zh_cn") == "官方"
        assert s._pick_enum_label("role", "official", "en") == "Official"
    finally:
        s.close()


def test_migration_011_pick_enum_label_zh_cn_miss_falls_back_to_en(tmp_path):
    """A missing zh_cn label falls back to the English label, exercising
    the second SQL string at store.py line 1370 (also updated from
    `locale = 'en'` to `lang = 'en'`)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        s._conn.execute(
            "DELETE FROM signal_labels WHERE key = ? AND lang = ?",
            ("release", "zh_cn"),
        )
        assert s._pick_enum_label("signal", "release", "zh_cn") == "Release"
    finally:
        s.close()


def test_migration_011_query_against_old_column_raises(tmp_path):
    """A direct SQL query against the old `locale` column name raises
    — the column does not exist. This is the explicit guard that the
    rename happened, not just a column-add."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        with pytest.raises(Exception):
            s._conn.execute(
                "SELECT label FROM signal_labels WHERE key = ? AND locale = ?",
                ("release", "zh_cn"),
            ).fetchone()
    finally:
        s.close()
