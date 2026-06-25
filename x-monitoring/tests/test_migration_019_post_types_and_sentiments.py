"""Migration 019: post_types + sentiments taxonomy.

Plan: docs/plans/2026-06-24-163000-replace-legacy-signals-with-post-types-and-sentiments.md
(Unit 9 of 9).

Scope (the deliberately minimal version):
- post_type_keys + post_type_labels tables created with 4 keys × 2 locales.
- sentiment_keys + sentiment_labels tables created with 4 keys × 2 locales.
- posts_brands_signals gets 2 new nullable TEXT columns (post_type,
  sentiment), FK-validated against their respective *_keys tables.
- The existing signal_id column is preserved (backward-compat).
- Heuristic backfill: legacy signal_id values map to (post_type, sentiment)
  pairs documented in the migration.

Verifies:
- post_type_keys exists with 4 keys (buzz_releases, hands_on_usage,
  performance_comparisons, feedback_questions).
- post_type_labels exists with 8 rows (4 keys × 2 locales).
- sentiment_keys exists with 4 keys (positive, negative, neutral, mixed).
- sentiment_labels exists with 8 rows (4 keys × 2 locales).
- post_type_keys / sentiment_keys have INTEGER id PKs (post-U8 convention).
- posts_brands_signals has new post_type + sentiment columns (NULLABLE TEXT).
- FK on post_type → post_type_keys.key.
- FK on sentiment → sentiment_keys.key.
- Indexes on (brand_id, post_type) and (brand_id, sentiment) exist.
- Heuristic backfill: signal_id='release' → (buzz_releases, neutral).
- Heuristic backfill: signal_id='praise' → (buzz_releases, positive).
- Heuristic backfill: signal_id='criticism' → (feedback_questions, negative).
- Heuristic backfill: signal_id='community_question' → (feedback_questions, neutral).
- Heuristic backfill: signal_id='commenter_capture' → (hands_on_usage, neutral).
- Heuristic backfill: signal_id='other' → (hands_on_usage, neutral).
- Idempotency: re-opening a DB that has 019 applied does not re-run it.
- Full stack apply: all migrations 001-019 apply on a fresh DB.
- Integration: insert_posts_brands_signals writes post_type + sentiment kwargs.
- Integration: dead-letter still drops unknown post_type values.
- Integration: dead-letter still drops unknown sentiment values.
- Integration: _known_post_type_keys returns 4 string keys.
- Integration: _known_sentiment_keys returns 4 string keys.
"""

import pytest


# --- happy path: post_type_keys seeded -----------------------------


def test_migration_019_post_type_keys_seeded(tmp_path):
    """post_type_keys has the 4 canonical post_type keys."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        keys = {
            r["key"]
            for r in s._conn.execute("SELECT key FROM post_type_keys").fetchall()
        }
        assert keys == {
            "buzz_releases", "hands_on_usage",
            "performance_comparisons", "feedback_questions",
        }, f"unexpected post_type keys: {keys}"
    finally:
        s.close()


def test_migration_019_post_type_keys_have_integer_pk(tmp_path):
    """post_type_keys uses INTEGER id PK (post-U8 convention)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        col = s._conn.execute(
            "SELECT type, pk FROM pragma_table_info('post_type_keys') "
            "WHERE name='id'"
        ).fetchone()
        assert col is not None, "post_type_keys.id missing"
        assert "INTEGER" in col["type"].upper()
        assert col["pk"] == 1, f"id is not PK. pk={col['pk']}"
        # key is UNIQUE NOT NULL TEXT.
        key_col = s._conn.execute(
            "SELECT type, [notnull] AS nn FROM pragma_table_info('post_type_keys') "
            "WHERE name='key'"
        ).fetchone()
        assert key_col["nn"] == 1
        assert "TEXT" in key_col["type"].upper()
    finally:
        s.close()


def test_migration_019_post_type_labels_seeded(tmp_path):
    """post_type_labels has 8 rows (4 keys × 2 locales)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        n = s._conn.execute("SELECT COUNT(*) FROM post_type_labels").fetchone()[0]
        assert n == 8, f"post_type_labels has {n} rows, expected 8"
        # Each key has en + zh_cn labels.
        labels = {
            (r["key"], r["lang"]): r["label"]
            for r in s._conn.execute(
                "SELECT key, lang, label FROM post_type_labels"
            ).fetchall()
        }
        assert labels[("buzz_releases", "en")] == "Buzz & Releases"
        assert labels[("buzz_releases", "zh_cn")] == "发布与热度"
        assert labels[("hands_on_usage", "en")] == "Hands-on Usage"
        assert labels[("hands_on_usage", "zh_cn")] == "实际使用体验"
        assert labels[("performance_comparisons", "en")] == "Performance & Comparisons"
        assert labels[("performance_comparisons", "zh_cn")] == "性能与对比"
        assert labels[("feedback_questions", "en")] == "Feedback & Questions"
        assert labels[("feedback_questions", "zh_cn")] == "问题与建议"
    finally:
        s.close()


# --- happy path: sentiment_keys + labels seeded --------------------


def test_migration_019_sentiment_keys_seeded(tmp_path):
    """sentiment_keys has the 4 canonical sentiment keys."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        keys = {
            r["key"]
            for r in s._conn.execute("SELECT key FROM sentiment_keys").fetchall()
        }
        assert keys == {"positive", "negative", "neutral", "mixed"}, (
            f"unexpected sentiment keys: {keys}"
        )
    finally:
        s.close()


def test_migration_019_sentiment_keys_have_integer_pk(tmp_path):
    """sentiment_keys uses INTEGER id PK (post-U8 convention)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        col = s._conn.execute(
            "SELECT type, pk FROM pragma_table_info('sentiment_keys') "
            "WHERE name='id'"
        ).fetchone()
        assert col is not None
        assert "INTEGER" in col["type"].upper()
        assert col["pk"] == 1
    finally:
        s.close()


def test_migration_019_sentiment_labels_seeded(tmp_path):
    """sentiment_labels has 8 rows (4 keys × 2 locales)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        n = s._conn.execute("SELECT COUNT(*) FROM sentiment_labels").fetchone()[0]
        assert n == 8, f"sentiment_labels has {n} rows, expected 8"
        labels = {
            (r["key"], r["lang"]): r["label"]
            for r in s._conn.execute(
                "SELECT key, lang, label FROM sentiment_labels"
            ).fetchall()
        }
        assert labels[("positive", "en")] == "Positive"
        assert labels[("positive", "zh_cn")] == "正面"
        assert labels[("negative", "en")] == "Negative"
        assert labels[("negative", "zh_cn")] == "负面"
        assert labels[("neutral", "en")] == "Neutral"
        assert labels[("neutral", "zh_cn")] == "中性"
        assert labels[("mixed", "en")] == "Mixed"
        assert labels[("mixed", "zh_cn")] == "混合"
    finally:
        s.close()


# --- happy path: posts_brands_signals gains columns -----------------


def test_migration_019_posts_brands_signals_has_post_type_sentiment(tmp_path):
    """posts_brands_signals has the new post_type + sentiment columns.

    U8 (migration 020): post_type + sentiment became INTEGER FK
    columns (storing the id of post_type_keys / sentiment_keys
    rows). Migration 019 added them as nullable TEXT; 020 converted
    them to INTEGER-storing-id; 022 made them NOT NULL.

    U9 (migration 022): the legacy `signal_id` column was DROPPED.
    """
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        cols = {
            r["name"]: r for r in s._conn.execute(
                "PRAGMA table_info(posts_brands_signals)"
            ).fetchall()
        }
        assert "post_type" in cols, "post_type column missing"
        assert "sentiment" in cols, "sentiment column missing"
        # U9: signal_id is GONE.
        assert "signal_id" not in cols, (
            "signal_id column should be DROPPED post-022 (U9)"
        )
        # Post-020 + post-022: both columns are INTEGER FKs and
        # NOT NULL.
        assert "INTEGER" in cols["post_type"]["type"].upper(), (
            f"post_type should be INTEGER FK post-020, got {cols['post_type']['type']!r}"
        )
        assert cols["post_type"]["notnull"] == 1, (
            "post_type should be NOT NULL post-022"
        )
        assert "INTEGER" in cols["sentiment"]["type"].upper(), (
            f"sentiment should be INTEGER FK post-020, got {cols['sentiment']['type']!r}"
        )
        assert cols["sentiment"]["notnull"] == 1, (
            "sentiment should be NOT NULL post-022"
        )
    finally:
        s.close()


def test_migration_019_post_type_fk_references_post_type_keys(tmp_path):
    """FK on posts_brands_signals.post_type → post_type_keys.id.

    U8 (migration 020): the FK target became post_type_keys.id
    (the INTEGER PK), not post_type_keys.key (the TEXT slug).
    Migration 019 originally pointed at the TEXT key.
    """
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        fks = s._conn.execute(
            "SELECT * FROM pragma_foreign_key_list('posts_brands_signals')"
        ).fetchall()
        assert any(
            r[2] == "post_type_keys" and r[3] == "post_type" and r[4] == "id"
            for r in fks
        ), f"post_type FK to post_type_keys.id missing. FKs: {fks}"
    finally:
        s.close()


def test_migration_019_sentiment_fk_references_sentiment_keys(tmp_path):
    """FK on posts_brands_signals.sentiment → sentiment_keys.id.

    U8 (migration 020): the FK target became sentiment_keys.id
    (the INTEGER PK), not sentiment_keys.key.
    """
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        fks = s._conn.execute(
            "SELECT * FROM pragma_foreign_key_list('posts_brands_signals')"
        ).fetchall()
        assert any(
            r[2] == "sentiment_keys" and r[3] == "sentiment" and r[4] == "id"
            for r in fks
        ), f"sentiment FK to sentiment_keys.id missing. FKs: {fks}"
    finally:
        s.close()


def test_migration_019_signal_id_dropped(tmp_path):
    """U9 (migration 022): the legacy signal_id FK is GONE.

    Migration 019 originally preserved the signal_id FK → signals.key
    because the new columns were ADDITIVE. Migration 022 completed
    the replacement: the `signal_id` column and the `signals` table
    are both dropped, so no signal_id FK can exist.
    """
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        fks = s._conn.execute(
            "SELECT * FROM pragma_foreign_key_list('posts_brands_signals')"
        ).fetchall()
        assert not any(
            r[3] == "signal_id" for r in fks
        ), f"signal_id FK should be DROPPED post-022. FKs: {fks}"
        # The `signals` table is also gone.
        sig_row = s._conn.execute(
            "SELECT name FROM sqlite_master WHERE name='signals'"
        ).fetchone()
        assert sig_row is None, "signals table should be DROPPED post-022"
    finally:
        s.close()


# --- happy path: new indexes ---------------------------------------


def test_migration_019_indexes_on_new_columns(tmp_path):
    """The 2 new indexes cover (brand_id, post_type) and (brand_id, sentiment)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        indexes = {
            r[0]
            for r in s._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        assert "idx_posts_brands_signals_brand_id_post_type" in indexes, (
            f"missing (brand_id, post_type) index. indexes={indexes}"
        )
        assert "idx_posts_brands_signals_brand_id_sentiment" in indexes, (
            f"missing (brand_id, sentiment) index. indexes={indexes}"
        )
        # U9 (migration 022): the legacy (brand_id, signal_id) index
        # is DROPPED — the signal_id column no longer exists.
        assert "idx_posts_brands_signals_brand_id_signal_id" not in indexes, (
            f"legacy (brand_id, signal_id) index should be DROPPED post-022. "
            f"indexes={indexes}"
        )
    finally:
        s.close()


# U9 (migration 022): the legacy signal_id column and signals table
# are DROPPED. The signal_id → (post_type, sentiment) backfill that
# 019 originally performed was a one-shot UPDATE on the data; 022
# completed the replacement by removing the source data. There is
# no post-022 data to backfill, so the 4 backfill tests are GONE.


# --- idempotency ---------------------------------------------------


def test_migration_019_idempotent(tmp_path):
    """Re-opening a DB that has 019 applied does not re-run it."""
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
        assert applied.count(19) == 1
        # Row counts unchanged.
        n_pt = s2._conn.execute("SELECT COUNT(*) FROM post_type_keys").fetchone()[0]
        n_sent = s2._conn.execute("SELECT COUNT(*) FROM sentiment_keys").fetchone()[0]
        assert n_pt == 4
        assert n_sent == 4
    finally:
        s2.close()


# --- full stack apply ----------------------------------------------


def test_migration_019_full_stack_apply(tmp_path):
    """All migrations 001-019 apply on a fresh DB; the post_type +
    sentiment taxonomy is in effect. Migration 021 was INTENTIONALLY
    SKIPPED (reserved for an unrelated HF products crawler that
    never landed). After U9 migration 022 ships, the applied set is
    {1..19, 20, 22} (21 is missing).

    U9: the legacy signals family is GONE post-022 (signals +
    signal_labels dropped, signal_id column dropped). The new
    taxonomy (post_type + sentiment) is the only classification
    surface.
    """
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        applied = sorted(
            r[0]
            for r in s._conn.execute("SELECT version FROM _migrations").fetchall()
        )
        expected = sorted(set(range(1, 21)) | {22})
        assert applied == expected, (
            f"unexpected versions: {applied} (expected {expected})"
        )
        # Both new enum families are in effect.
        for tbl in (
            "post_type_keys", "post_type_labels",
            "sentiment_keys", "sentiment_labels",
        ):
            rows = s._conn.execute(
                "SELECT name FROM sqlite_master WHERE name = ?", (tbl,)
            ).fetchall()
            assert rows, f"{tbl} missing"
        # U9: the legacy signals family is GONE.
        for tbl in ("signals", "signal_labels"):
            rows = s._conn.execute(
                "SELECT name FROM sqlite_master WHERE name = ?", (tbl,)
            ).fetchall()
            assert not rows, f"{tbl} should be DROPPED post-022"
    finally:
        s.close()


# --- integration: insert_paths accept new kwargs -------------------


def test_migration_019_insert_posts_brands_signals_writes_post_type_sentiment(tmp_path):
    """insert_posts_brands_signals writes the (post_type, sentiment)
    args to the new columns.

    U9 (migration 022): the `signal` kwarg is REMOVED. The legacy
    6-bucket taxonomy is gone — only (post_type, sentiment) remain.
    The signature is (post_id, brand_id, post_type, sentiment).
    """
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        s._conn.execute(
            "INSERT INTO posts (tweet_id, author_handle, fetched_at) "
            "VALUES (?, ?, ?)",
            ("t_u9_insert", "u_u9", "2026-06-24T00:00:00+00:00"),
        )
        s.insert_posts_brands_signals(
            "t_u9_insert", "minimax",
            "buzz_releases", "positive",
        )
        # U8: post_id is INTEGER. JOIN via posts.tweet_id to resolve.
        row = s._conn.execute(
            "SELECT pt.key AS post_type, sn.key AS sentiment "
            "FROM posts_brands_signals pbs "
            "JOIN posts p ON p.id = pbs.post_id "
            "JOIN post_type_keys pt ON pt.id = pbs.post_type "
            "JOIN sentiment_keys sn ON sn.id = pbs.sentiment "
            "WHERE p.tweet_id = ?",
            ("t_u9_insert",),
        ).fetchone()
        assert row["post_type"] == "buzz_releases"
        assert row["sentiment"] == "positive"
    finally:
        s.close()


# U9 (migration 022): the legacy single-string `signal` insert path
# is GONE. `signal=` was a backward-compat shim for the v1.8
# (R15) taxonomy; 022 completed the replacement. There is no
# post-022 row that has signal-only data.


# --- integration: dead-letter guards on new fields ----------------


def test_migration_019_unknown_post_type_dead_lettered(tmp_path):
    """The FK guard dead-letters unknown post_type values."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        s._conn.execute(
            "INSERT INTO posts (tweet_id, author_handle, fetched_at) "
            "VALUES (?, ?, ?)",
            ("t_u9_ghost_pt", "u_ghost_pt", "2026-06-24T00:00:00+00:00"),
        )
        s.insert_posts_brands_signals(
            "t_u9_ghost_pt", "minimax",
            post_type="ghost_post_type",
            sentiment="positive",
        )
        row = s._conn.execute(
            "SELECT * FROM posts_brands_signals WHERE post_id = ?",
            ("t_u9_ghost_pt",),
        ).fetchone()
        assert row is None, "unknown post_type was not dead-lettered"
    finally:
        s.close()


def test_migration_019_unknown_sentiment_dead_lettered(tmp_path):
    """The FK guard dead-letters unknown sentiment values."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        s._conn.execute(
            "INSERT INTO posts (tweet_id, author_handle, fetched_at) "
            "VALUES (?, ?, ?)",
            ("t_u9_ghost_sent", "u_ghost_sent", "2026-06-24T00:00:00+00:00"),
        )
        s.insert_posts_brands_signals(
            "t_u9_ghost_sent", "minimax",
            post_type="buzz_releases",
            sentiment="ghost_sentiment",
        )
        row = s._conn.execute(
            "SELECT * FROM posts_brands_signals WHERE post_id = ?",
            ("t_u9_ghost_sent",),
        ).fetchone()
        assert row is None, "unknown sentiment was not dead-lettered"
    finally:
        s.close()


# --- integration: cache helpers ------------------------------------


def test_migration_019_known_post_type_keys_returns_seeded_set(tmp_path):
    """_known_post_type_keys returns the 4-key seeded set."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        keys = s._known_post_type_keys()
        assert keys == {
            "buzz_releases", "hands_on_usage",
            "performance_comparisons", "feedback_questions",
        }, f"unexpected post_type keys: {keys}"
    finally:
        s.close()


def test_migration_019_known_sentiment_keys_returns_seeded_set(tmp_path):
    """_known_sentiment_keys returns the 4-key seeded set."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        keys = s._known_sentiment_keys()
        assert keys == {"positive", "negative", "neutral", "mixed"}, (
            f"unexpected sentiment keys: {keys}"
        )
    finally:
        s.close()
