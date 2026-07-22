"""Migration 011: rename `locale` columns to `lang` on the i18n label tables.

Plan: docs/plans/2026-06-24-002-refactor-schema-modernization-batch-plan.md
(Unit 1 of 9, R1).

Migration 011 originally renamed `locale` → `lang` on THREE label
tables: signal_labels, role_labels, engagement_tier_labels. Subsequent
migrations have narrowed the surviving set:

- Migration 012 DROPPED engagement_tier_labels (U5).
- Migration 022 (U9 kill) DROPPED signal_labels along with the legacy
  6-signal taxonomy.
- Migration 019 added post_type_labels + sentiment_labels, also with
  `lang` columns (the convention propagated to new tables).

So post-022 the surviving tables that 011's rename applies to are:
role_labels, post_type_labels, sentiment_labels. The rename itself is
preserved on all of them; only signal_labels and engagement_tier_labels
no longer exist.

Verifies (post-022):
- role_labels has a `lang` column and no `locale` column.
- post_type_labels has a `lang` column.
- sentiment_labels has a `lang` column.
- signal_labels is GONE (post-022).
- Composite PRIMARY KEY (key, lang) is intact on role_labels.
- Seed rows are preserved across the column rename (role_labels: 6).
- Idempotency: re-opening a DB that has 011 applied does not re-run it.
- Full stack apply: all migrations {1..20, 22} apply on a fresh DB
  (only 21 absent).
- Integration: `_pick_enum_label('role', ...)` returns the expected
  localized label; the `signal` family is no longer supported.
- Integration: query against the old `locale` column name raises.
"""

import pytest


# --- happy path: column renamed ---------------------------------------


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


def test_migration_011_post_type_labels_has_lang_column(tmp_path):
    """post_type_labels (created in 019) has a `lang` column."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        cols = {
            r[1]
            for r in s._conn.execute(
                "PRAGMA table_info(post_type_labels)"
            ).fetchall()
        }
        assert "lang" in cols, (
            f"post_type_labels missing `lang` column. cols={cols}"
        )
    finally:
        s.close()


def test_migration_011_sentiment_labels_has_lang_column(tmp_path):
    """sentiment_labels (created in 019) has a `lang` column."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        cols = {
            r[1]
            for r in s._conn.execute(
                "PRAGMA table_info(sentiment_labels)"
            ).fetchall()
        }
        assert "lang" in cols, (
            f"sentiment_labels missing `lang` column. cols={cols}"
        )
    finally:
        s.close()


def test_migration_011_signal_labels_dropped_by_022(tmp_path):
    """signal_labels (originally renamed by 011) was dropped by 022 along
    with the legacy 6-signal taxonomy."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT name FROM sqlite_master WHERE name='signal_labels'"
        ).fetchall()
        assert rows == [], (
            f"signal_labels should be DROPPED post-022 (still present: {rows})"
        )
    finally:
        s.close()


# --- happy path: composite PK preserved + seed rows intact -----------


def test_migration_011_pk_preserved_role_labels(tmp_path):
    """The composite PRIMARY KEY (key, lang) on role_labels is intact
    after the column rename; 6 seed rows (3 keys x 2 locales) are present
    (post-U6 trim in 016)."""
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
        # role_labels row count unchanged.
        n_labels = s2._conn.execute("SELECT COUNT(*) FROM role_labels").fetchone()[0]
        assert n_labels == 6
    finally:
        s2.close()


# --- full stack apply -------------------------------------------------


def test_migration_011_full_stack_apply(tmp_path):
    """All migrations {1..20, 22} apply on a fresh DB (only 21 absent);
    the `lang` column is present on all surviving `*_labels` tables.

    Post-012: engagement_tier_labels is dropped.
    Post-022: signal_labels is dropped (along with the 6-signal taxonomy).
    Surviving `*_labels` tables: role_labels, post_type_labels,
    sentiment_labels — all with `lang` columns.
    """
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        applied = sorted(
            r[0]
            for r in s._conn.execute("SELECT version FROM _migrations").fetchall()
        )
        expected = sorted(set(range(1, 21)) | {22, 23})
        assert applied == expected, (
            f"unexpected versions: {applied} (expected {expected})"
        )

        # Surviving `*_labels` tables all have `lang`.
        for tbl in ("role_labels", "post_type_labels", "sentiment_labels"):
            cols = {
                r[1] for r in s._conn.execute(f"PRAGMA table_info({tbl})").fetchall()
            }
            assert "lang" in cols, f"{tbl} missing `lang` column. cols={cols}"
            assert "locale" not in cols, (
                f"{tbl} still has `locale` column. cols={cols}"
            )

        # The 2 dropped tables are gone.
        for tbl in ("signal_labels", "engagement_tier_labels"):
            rows = s._conn.execute(
                "SELECT name FROM sqlite_master WHERE name = ?", (tbl,)
            ).fetchall()
            assert rows == [], f"{tbl} should be GONE (post-022 / post-012)"
    finally:
        s.close()


# --- integration: _pick_enum_label honors the renamed column ---------


def test_migration_011_pick_enum_label_returns_zh_cn_label(tmp_path):
    """_pick_enum_label returns the expected localized label after the
    column rename. The `signal` family is no longer supported post-022;
    the test exercises `role`, `post_type`, `sentiment` instead."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        assert s._pick_enum_label("role", "official", "zh_cn") == "官方"
        assert s._pick_enum_label("role", "official", "en") == "Official"
        assert s._pick_enum_label("post_type", "buzz_releases", "zh_cn") == "发布与热度"
        assert s._pick_enum_label("sentiment", "positive", "zh_cn") == "正面"
    finally:
        s.close()


def test_migration_011_pick_enum_label_zh_cn_miss_falls_back_to_en(tmp_path):
    """A missing zh_cn label falls back to the English label, exercising
    the second SQL string (also updated from `locale = 'en'` to
    `lang = 'en'`)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        s._conn.execute(
            "DELETE FROM role_labels WHERE key = ? AND lang = ?",
            ("official", "zh_cn"),
        )
        assert s._pick_enum_label("role", "official", "zh_cn") == "Official"
    finally:
        s.close()


def test_migration_011_pick_enum_label_signal_family_unsupported(tmp_path):
    """The `signal` family is removed post-022; calling _pick_enum_label
    with `signal` raises ValueError."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        with pytest.raises(ValueError):
            s._pick_enum_label("signal", "release", "zh_cn")
    finally:
        s.close()


def test_migration_011_query_against_old_column_raises(tmp_path):
    """A direct SQL query against the old `locale` column name raises
    on the surviving `role_labels` table — the column does not exist.
    This is the explicit guard that the rename happened, not just a
    column-add."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        with pytest.raises(Exception):
            s._conn.execute(
                "SELECT label FROM role_labels WHERE key = ? AND locale = ?",
                ("official", "zh_cn"),
            ).fetchone()
    finally:
        s.close()
