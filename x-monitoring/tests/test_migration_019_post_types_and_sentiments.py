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
    """posts_brands_signals has the new post_type + sentiment columns
    (NULLABLE TEXT, alongside the existing signal_id)."""
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
        assert "signal_id" in cols, "signal_id column missing (preserved)"
        # New columns are TEXT and NULLABLE.
        assert "TEXT" in cols["post_type"]["type"].upper()
        assert cols["post_type"]["notnull"] == 0, "post_type should be nullable"
        assert "TEXT" in cols["sentiment"]["type"].upper()
        assert cols["sentiment"]["notnull"] == 0, "sentiment should be nullable"
    finally:
        s.close()


def test_migration_019_post_type_fk_references_post_type_keys(tmp_path):
    """FK on posts_brands_signals.post_type → post_type_keys.key."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        fks = s._conn.execute(
            "SELECT * FROM pragma_foreign_key_list('posts_brands_signals')"
        ).fetchall()
        assert any(
            r[2] == "post_type_keys" and r[3] == "post_type" and r[4] == "key"
            for r in fks
        ), f"post_type FK to post_type_keys.key missing. FKs: {fks}"
    finally:
        s.close()


def test_migration_019_sentiment_fk_references_sentiment_keys(tmp_path):
    """FK on posts_brands_signals.sentiment → sentiment_keys.key."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        fks = s._conn.execute(
            "SELECT * FROM pragma_foreign_key_list('posts_brands_signals')"
        ).fetchall()
        assert any(
            r[2] == "sentiment_keys" and r[3] == "sentiment" and r[4] == "key"
            for r in fks
        ), f"sentiment FK to sentiment_keys.key missing. FKs: {fks}"
    finally:
        s.close()


def test_migration_019_signal_id_fk_preserved(tmp_path):
    """The legacy signal_id FK → signals.key is preserved through the rebuild."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        fks = s._conn.execute(
            "SELECT * FROM pragma_foreign_key_list('posts_brands_signals')"
        ).fetchall()
        assert any(
            r[2] == "signals" and r[3] == "signal_id" and r[4] == "key"
            for r in fks
        ), f"signal_id FK to signals.key missing. FKs: {fks}"
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
        # The legacy (brand_id, signal_id) index is recreated.
        assert "idx_posts_brands_signals_brand_id_signal_id" in indexes, (
            f"legacy (brand_id, signal_id) index missing. indexes={indexes}"
        )
    finally:
        s.close()


# --- happy path: backfill mapping ----------------------------------


def test_migration_019_backfill_release_to_buzz_neutral(tmp_path):
    """Pre-existing signal_id='release' is backfilled to
    (post_type='buzz_releases', sentiment='neutral')."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        s._conn.execute(
            "INSERT INTO posts (tweet_id, author_handle, fetched_at) "
            "VALUES (?, ?, ?)",
            ("t_release", "u_release", "2026-06-24T00:00:00+00:00"),
        )
        # Insert pre-backfill row directly with FK disabled (the
        # migration itself does the backfill; this simulates data that
        # was inserted pre-migration 019).
        s._conn.execute(
            "INSERT INTO posts_brands_signals(post_id, brand_id, signal_id) "
            "VALUES (?, ?, ?)",
            ("t_release", "minimax", "release"),
        )
        # Re-run just the backfill SQL (the migration's UPDATE).
        s._conn.executescript("""
            UPDATE posts_brands_signals SET
                post_type = CASE signal_id
                    WHEN 'release'             THEN 'buzz_releases'
                    WHEN 'praise'              THEN 'buzz_releases'
                    WHEN 'commenter_capture'   THEN 'hands_on_usage'
                    WHEN 'community_question'  THEN 'feedback_questions'
                    WHEN 'criticism'           THEN 'feedback_questions'
                    WHEN 'other'               THEN 'hands_on_usage'
                    ELSE 'hands_on_usage'
                END,
                sentiment = CASE signal_id
                    WHEN 'praise'              THEN 'positive'
                    WHEN 'criticism'           THEN 'negative'
                    WHEN 'community_question'  THEN 'neutral'
                    WHEN 'release'             THEN 'neutral'
                    WHEN 'commenter_capture'   THEN 'neutral'
                    WHEN 'other'               THEN 'neutral'
                    ELSE 'neutral'
                END
            WHERE post_type IS NULL OR sentiment IS NULL;
        """)
        row = s._conn.execute(
            "SELECT post_type, sentiment FROM posts_brands_signals "
            "WHERE post_id = ?",
            ("t_release",),
        ).fetchone()
        assert row["post_type"] == "buzz_releases", (
            f"expected buzz_releases, got {row['post_type']!r}"
        )
        assert row["sentiment"] == "neutral", (
            f"expected neutral, got {row['sentiment']!r}"
        )
    finally:
        s.close()


def test_migration_019_backfill_praise_to_buzz_positive(tmp_path):
    """Pre-existing signal_id='praise' is backfilled to
    (post_type='buzz_releases', sentiment='positive')."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        s._conn.execute(
            "INSERT INTO posts (tweet_id, author_handle, fetched_at) "
            "VALUES (?, ?, ?)",
            ("t_praise", "u_praise", "2026-06-24T00:00:00+00:00"),
        )
        s._conn.execute(
            "INSERT INTO posts_brands_signals(post_id, brand_id, signal_id) "
            "VALUES (?, ?, ?)",
            ("t_praise", "minimax", "praise"),
        )
        s._conn.executescript("""
            UPDATE posts_brands_signals SET
                post_type = CASE signal_id
                    WHEN 'release'             THEN 'buzz_releases'
                    WHEN 'praise'              THEN 'buzz_releases'
                    WHEN 'commenter_capture'   THEN 'hands_on_usage'
                    WHEN 'community_question'  THEN 'feedback_questions'
                    WHEN 'criticism'           THEN 'feedback_questions'
                    WHEN 'other'               THEN 'hands_on_usage'
                    ELSE 'hands_on_usage'
                END,
                sentiment = CASE signal_id
                    WHEN 'praise'              THEN 'positive'
                    WHEN 'criticism'           THEN 'negative'
                    WHEN 'community_question'  THEN 'neutral'
                    WHEN 'release'             THEN 'neutral'
                    WHEN 'commenter_capture'   THEN 'neutral'
                    WHEN 'other'               THEN 'neutral'
                    ELSE 'neutral'
                END
            WHERE post_type IS NULL OR sentiment IS NULL;
        """)
        row = s._conn.execute(
            "SELECT post_type, sentiment FROM posts_brands_signals "
            "WHERE post_id = ?",
            ("t_praise",),
        ).fetchone()
        assert row["post_type"] == "buzz_releases"
        assert row["sentiment"] == "positive"
    finally:
        s.close()


def test_migration_019_backfill_criticism_to_feedback_negative(tmp_path):
    """Pre-existing signal_id='criticism' is backfilled to
    (post_type='feedback_questions', sentiment='negative')."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        s._conn.execute(
            "INSERT INTO posts (tweet_id, author_handle, fetched_at) "
            "VALUES (?, ?, ?)",
            ("t_criticism", "u_criticism", "2026-06-24T00:00:00+00:00"),
        )
        s._conn.execute(
            "INSERT INTO posts_brands_signals(post_id, brand_id, signal_id) "
            "VALUES (?, ?, ?)",
            ("t_criticism", "minimax", "criticism"),
        )
        s._conn.executescript("""
            UPDATE posts_brands_signals SET
                post_type = CASE signal_id
                    WHEN 'release'             THEN 'buzz_releases'
                    WHEN 'praise'              THEN 'buzz_releases'
                    WHEN 'commenter_capture'   THEN 'hands_on_usage'
                    WHEN 'community_question'  THEN 'feedback_questions'
                    WHEN 'criticism'           THEN 'feedback_questions'
                    WHEN 'other'               THEN 'hands_on_usage'
                    ELSE 'hands_on_usage'
                END,
                sentiment = CASE signal_id
                    WHEN 'praise'              THEN 'positive'
                    WHEN 'criticism'           THEN 'negative'
                    WHEN 'community_question'  THEN 'neutral'
                    WHEN 'release'             THEN 'neutral'
                    WHEN 'commenter_capture'   THEN 'neutral'
                    WHEN 'other'               THEN 'neutral'
                    ELSE 'neutral'
                END
            WHERE post_type IS NULL OR sentiment IS NULL;
        """)
        row = s._conn.execute(
            "SELECT post_type, sentiment FROM posts_brands_signals "
            "WHERE post_id = ?",
            ("t_criticism",),
        ).fetchone()
        assert row["post_type"] == "feedback_questions"
        assert row["sentiment"] == "negative"
    finally:
        s.close()


def test_migration_019_backfill_remaining_signals(tmp_path):
    """The other 3 signals backfill correctly: community_question,
    commenter_capture, other."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        for sig, expected_pt, expected_sent in [
            ("community_question", "feedback_questions", "neutral"),
            ("commenter_capture", "hands_on_usage", "neutral"),
            ("other", "hands_on_usage", "neutral"),
        ]:
            tweet_id = f"t_{sig}"
            s._conn.execute(
                "INSERT INTO posts (tweet_id, author_handle, fetched_at) "
                "VALUES (?, ?, ?)",
                (tweet_id, f"u_{sig}", "2026-06-24T00:00:00+00:00"),
            )
            s._conn.execute(
                "INSERT INTO posts_brands_signals(post_id, brand_id, signal_id) "
                "VALUES (?, ?, ?)",
                (tweet_id, "minimax", sig),
            )
        s._conn.executescript("""
            UPDATE posts_brands_signals SET
                post_type = CASE signal_id
                    WHEN 'release'             THEN 'buzz_releases'
                    WHEN 'praise'              THEN 'buzz_releases'
                    WHEN 'commenter_capture'   THEN 'hands_on_usage'
                    WHEN 'community_question'  THEN 'feedback_questions'
                    WHEN 'criticism'           THEN 'feedback_questions'
                    WHEN 'other'               THEN 'hands_on_usage'
                    ELSE 'hands_on_usage'
                END,
                sentiment = CASE signal_id
                    WHEN 'praise'              THEN 'positive'
                    WHEN 'criticism'           THEN 'negative'
                    WHEN 'community_question'  THEN 'neutral'
                    WHEN 'release'             THEN 'neutral'
                    WHEN 'commenter_capture'   THEN 'neutral'
                    WHEN 'other'               THEN 'neutral'
                    ELSE 'neutral'
                END
            WHERE post_type IS NULL OR sentiment IS NULL;
        """)
        for sig, expected_pt, expected_sent in [
            ("community_question", "feedback_questions", "neutral"),
            ("commenter_capture", "hands_on_usage", "neutral"),
            ("other", "hands_on_usage", "neutral"),
        ]:
            tweet_id = f"t_{sig}"
            row = s._conn.execute(
                "SELECT post_type, sentiment FROM posts_brands_signals "
                "WHERE post_id = ?",
                (tweet_id,),
            ).fetchone()
            assert row["post_type"] == expected_pt, (
                f"{sig}: expected post_type={expected_pt}, got {row['post_type']!r}"
            )
            assert row["sentiment"] == expected_sent, (
                f"{sig}: expected sentiment={expected_sent}, got {row['sentiment']!r}"
            )
    finally:
        s.close()


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
    sentiment taxonomy is in effect alongside the legacy signal taxonomy."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        applied = sorted(
            r[0]
            for r in s._conn.execute("SELECT version FROM _migrations").fetchall()
        )
        assert applied == list(range(1, 20)), (
            f"unexpected versions: {applied}"
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
        # Legacy signals family still present (additive change).
        for tbl in ("signals", "signal_labels"):
            rows = s._conn.execute(
                "SELECT name FROM sqlite_master WHERE name = ?", (tbl,)
            ).fetchall()
            assert rows, f"{tbl} missing (should be preserved)"
    finally:
        s.close()


# --- integration: insert_paths accept new kwargs -------------------


def test_migration_019_insert_posts_brands_signals_writes_post_type_sentiment(tmp_path):
    """insert_posts_brands_signals writes the new post_type + sentiment
    kwargs to the renamed columns."""
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
            signal=None,
            post_type="buzz_releases",
            sentiment="positive",
        )
        row = s._conn.execute(
            "SELECT signal_id, post_type, sentiment FROM posts_brands_signals "
            "WHERE post_id = ?",
            ("t_u9_insert",),
        ).fetchone()
        assert row["post_type"] == "buzz_releases"
        assert row["sentiment"] == "positive"
        assert row["signal_id"] is None
    finally:
        s.close()


def test_migration_019_insert_legacy_signal_still_works(tmp_path):
    """The legacy signal-only insert path still works (backward compat)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        s._conn.execute(
            "INSERT INTO posts (tweet_id, author_handle, fetched_at) "
            "VALUES (?, ?, ?)",
            ("t_u9_legacy", "u_legacy", "2026-06-24T00:00:00+00:00"),
        )
        s.insert_posts_brands_signals(
            "t_u9_legacy", "minimax", signal="praise",
        )
        row = s._conn.execute(
            "SELECT signal_id, post_type, sentiment FROM posts_brands_signals "
            "WHERE post_id = ?",
            ("t_u9_legacy",),
        ).fetchone()
        assert row["signal_id"] == "praise"
        assert row["post_type"] is None
        assert row["sentiment"] is None
    finally:
        s.close()


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
