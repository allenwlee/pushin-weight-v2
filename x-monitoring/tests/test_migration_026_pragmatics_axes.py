"""Migration 025: pragmatics axes — discourse_keys + nationalism_keys
+ posts_brands_discourse.

Plan: docs/plans/2026-07-02-002-feat-streamlined-post-fetch-pipeline-plan.md
(Unit 1 of 8).

Verifies:
- discourse_keys is created with exactly 9 rows (no `other` bucket).
- discourse_labels is created with 18 rows (9 keys × {en, zh_cn}).
- nationalism_keys is created with exactly 6 rows.
- nationalism_labels is created with 12 rows (6 keys × {en, zh_cn}).
- posts_brands_discourse is created with composite PK
  (post_id, brand_id, discourse_key, act_id) and INTEGER FK columns.
- The 3 brand-scoped indexes (idx_post_brand_dis_b_dr / _b_cn_nat /
  _b_us_nat) exist.
- Idempotency: re-opening a DB with 025 applied does not re-run it.
- Full stack apply: all migrations 001-025 apply on a fresh DB.
- Integration: Store.bulk_insert_post_brand_discourse writes the
  INTEGER FKs correctly (callers pass TEXT keys; the Store resolves).
- Integration: an unknown discourse_key is dead-lettered and the row
  is dropped (FK constraint not raised).
- Integration: a NULL china_nationalism / us_nationalism is allowed
  (the backfill window).
- Integration: bulk_update_nationalism fills the two NULL FKs and
  returns True; returns False if the discourse row doesn't exist.
- Integration: get_post_brand_discourse_for_post joins back to TEXT
  keys and returns the four-pronged row shape callers expect.
"""

import pytest


# --- happy path: tables present -----------------------------------


def test_migration_026_discourse_keys_created(tmp_path):
    """The `discourse_keys` table is created with the 9 expected rows."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT key FROM discourse_keys ORDER BY key"
        ).fetchall()
        keys = {r["key"] for r in rows}
        assert keys == {
            "genuine_hype", "sarcasm", "dunk_yingyang",
            "self_deprecation", "cope", "fud",
            "distillation_accusation", "ai_slop_critique",
            "absurdist_meme",
        }, f"unexpected discourse_keys set: {sorted(keys)}"
        # No `other` bucket (KTD5).
        assert "other" not in keys, (
            "discourse_keys must NOT have an `other` bucket per KTD5"
        )
    finally:
        s.close()


def test_migration_026_discourse_labels_seeded(tmp_path):
    """Both en + zh_cn labels are seeded for every discourse key."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT key, lang FROM discourse_labels"
        ).fetchall()
        assert len(rows) == 18, (
            f"expected 18 discourse_labels (9 keys × 2 langs), got {len(rows)}"
        )
        langs = {(r["key"], r["lang"]) for r in rows}
        for key in (
            "genuine_hype", "sarcasm", "dunk_yingyang",
            "self_deprecation", "cope", "fud",
            "distillation_accusation", "ai_slop_critique",
            "absurdist_meme",
        ):
            assert (key, "en") in langs, f"missing en label for {key}"
            assert (key, "zh_cn") in langs, f"missing zh_cn label for {key}"
    finally:
        s.close()


def test_migration_026_nationalism_keys_created(tmp_path):
    """The `nationalism_keys` table is created with the 6 expected rows."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT key FROM nationalism_keys ORDER BY key"
        ).fetchall()
        keys = {r["key"] for r in rows}
        assert keys == {
            "none", "mild_pro", "pro", "constructive_critical",
            "anti", "mixed",
        }, f"unexpected nationalism_keys set: {sorted(keys)}"
    finally:
        s.close()


def test_migration_026_nationalism_labels_seeded(tmp_path):
    """Both en + zh_cn labels are seeded for every nationalism key."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT key, lang FROM nationalism_labels"
        ).fetchall()
        assert len(rows) == 12, (
            f"expected 12 nationalism_labels (6 keys × 2 langs), got {len(rows)}"
        )
    finally:
        s.close()


def test_migration_026_posts_brands_discourse_schema(tmp_path):
    """posts_brands_discourse has composite PK + INTEGER FKs."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        cols = {
            r["name"]: r
            for r in s._conn.execute(
                "PRAGMA table_info(posts_brands_discourse)"
            ).fetchall()
        }
        assert set(cols) == {
            "post_id", "brand_id", "discourse_key", "act_id",
            "china_nationalism", "us_nationalism",
        }, f"unexpected columns: {set(cols)}"
        # All four PK columns must be INTEGER (migration 020
        # convention; FOREIGN KEY columns store INTEGER ids).
        for col in (
            "post_id", "brand_id", "discourse_key",
            "china_nationalism", "us_nationalism",
        ):
            assert cols[col]["type"] == "INTEGER", (
                f"{col} is {cols[col]['type']!r}, expected INTEGER"
            )
        assert cols["act_id"]["type"] == "INTEGER"
        # Two nationalism FKs are nullable; the four PK columns are not.
        assert cols["china_nationalism"]["notnull"] == 0
        assert cols["us_nationalism"]["notnull"] == 0
        for col in ("post_id", "brand_id", "discourse_key", "act_id"):
            assert cols[col]["notnull"] == 1, (
                f"{col} must be NOT NULL (it's part of the composite PK)"
            )
    finally:
        s.close()


def test_migration_026_brand_scoped_indexes_created(tmp_path):
    """The three brand-scoped indexes (pushin_weight mirror) exist."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        idx = {
            r["name"]
            for r in s._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        for expected in (
            "idx_post_brand_dis_b_dr",
            "idx_post_brand_dis_b_cn_nat",
            "idx_post_brand_dis_b_us_nat",
        ):
            assert expected in idx, (
                f"missing index {expected}; found {sorted(i for i in idx if 'discourse' in i or 'dis_b' in i)}"
            )
    finally:
        s.close()


# --- idempotency / full-stack ------------------------------------------


def test_migration_026_idempotent(tmp_path):
    """Re-opening a DB with 025 applied does not re-run it."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s1 = Store(db, auto_migrate=True)
    s1.close()
    s2 = Store(db, auto_migrate=True)
    try:
        applied = s2.applied_migrations()
        assert 25 in applied
        # Verify the 9-row count survived a second open.
        n = s2._conn.execute(
            "SELECT COUNT(*) AS n FROM discourse_keys"
        ).fetchone()["n"]
        assert n == 9, f"second open changed discourse_keys count to {n}"
    finally:
        s2.close()


def test_migration_026_full_stack_fresh_db(tmp_path):
    """All migrations 001-025 apply on a fresh DB (no exceptions)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        applied = s.applied_migrations()
        # Migrations 021 was not numbered (skipped); 022, 023, 024, 025
        # are the latest. The point is the runner didn't blow up on a
        # fresh DB through 025.
        assert 25 in applied
        # And the new tables exist.
        names = {
            r["name"]
            for r in s._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for t in (
            "discourse_keys", "discourse_labels",
            "nationalism_keys", "nationalism_labels",
            "posts_brands_discourse",
        ):
            assert t in names, f"missing table {t} after 025"
    finally:
        s.close()


# --- integration: Store helpers ------------------------------------------


def _seed_post_brand_signal_row(
    s, tweet_id: str, brand_id: str
) -> None:
    """Helper: insert a minimal post + brand + signal row so a
    posts_brands_discourse row has valid parents to FK against.

    Bypasses `insert_posts` (which is heavy) — direct SQL writes
    using the same INTEGER-id convention.
    """
    # Pick any two known brands. Migration 004 seeds the standard
    # roster; if the seed isn't present we fall back to a synthetic
    # brand row.
    known = {b.brand_id for b in s.read_brands()}
    if brand_id not in known:
        # Insert a synthetic brand directly. Bypasses the validation
        # in Store — acceptable because we're seeding a test fixture.
        # After migration 023 the slug column is `nickname`, not
        # `brand_id`.
        s._conn.execute(
            """
            INSERT INTO brands(nickname, display_name, accent_color,
                               is_sentinel, created_at)
            VALUES (?, ?, '#9ca3af', 0, '2026-07-02T00:00:00+00:00')
            """,
            (brand_id, brand_id),
        )
        # Brand cache may already be populated; invalidate so the
        # next _brand_int_id() call sees the new row.
        s._brand_cache = None
        s._brand_id_map = None
    s._conn.execute(
        """
        INSERT OR IGNORE INTO posts(tweet_id, text, created_at, fetched_at)
        VALUES (?, 'test post', '2026-07-02T00:00:00+00:00',
                '2026-07-02T00:00:00+00:00')
        """,
        (tweet_id,),
    )
    post_id_int = s._tweet_int_id(tweet_id)
    brand_id_int = s._brand_int_id(brand_id)
    s._conn.execute(
        """
        INSERT OR IGNORE INTO posts_brands(post_id, brand_id, weight)
        VALUES (?, ?, 1.0)
        """,
        (post_id_int, brand_id_int),
    )


def test_bulk_insert_post_brand_discourse_writes_text_to_int_fks(tmp_path):
    """Callers pass TEXT keys; the Store resolves to INTEGER ids."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        _seed_post_brand_signal_row(s, "111", "openai")
        n = s.bulk_insert_post_brand_discourse([{
            "tweet_id": "111",
            "brand_id": "openai",
            "discourse_key": "dunk_yingyang",
            "act_id": 1,
            "china_nationalism": "mixed",
            "us_nationalism": "constructive_critical",
        }])
        assert n == 1
        # Verify the INTEGER FK columns actually got the right ids
        # (not the literal strings).
        row = s._conn.execute(
            """
            SELECT pbd.discourse_key, pbd.china_nationalism,
                   pbd.us_nationalism, pbd.act_id
            FROM posts_brands_discourse pbd
            JOIN posts p ON p.id = pbd.post_id
            JOIN brands b ON b.id = pbd.brand_id
            WHERE p.tweet_id = ? AND b.nickname = ?
            """,
            ("111", "openai"),
        ).fetchone()
        # Compare against the *_id_map resolved values.
        assert row["discourse_key"] == s._discourse_int_id(
            "dunk_yingyang"
        )
        assert row["china_nationalism"] == s._nationalism_int_id("mixed")
        assert row["us_nationalism"] == s._nationalism_int_id(
            "constructive_critical"
        )
        assert row["act_id"] == 1
    finally:
        s.close()


def test_bulk_insert_post_brand_discourse_unknown_key_dead_lettered(tmp_path):
    """An unknown discourse_key is dead-lettered and the row dropped."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        _seed_post_brand_signal_row(s, "222", "anthropic")
        n = s.bulk_insert_post_brand_discourse([{
            "tweet_id": "222",
            "brand_id": "anthropic",
            "discourse_key": "made_up_category",
            "act_id": 1,
        }])
        assert n == 0
        # No row written.
        rows = s._conn.execute(
            "SELECT COUNT(*) AS n FROM posts_brands_discourse"
        ).fetchone()["n"]
        assert rows == 0
    finally:
        s.close()


def test_bulk_insert_post_brand_discourse_nationalism_nullable(tmp_path):
    """The two nationalism FKs are allowed to be NULL during backfill."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        _seed_post_brand_signal_row(s, "333", "deepseek")
        n = s.bulk_insert_post_brand_discourse([{
            "tweet_id": "333",
            "brand_id": "deepseek",
            "discourse_key": "genuine_hype",
            "act_id": 1,
            # no china_nationalism / us_nationalism — backfill window
        }])
        assert n == 1
        rows = s.get_post_brand_discourse_for_post("333")
        assert len(rows) == 1
        assert rows[0]["discourse_key"] == "genuine_hype"
        assert rows[0]["china_nationalism"] is None
        assert rows[0]["us_nationalism"] is None
    finally:
        s.close()


def test_bulk_update_nationalism_fills_null_fks(tmp_path):
    """Second-pass classifier path: NULL → filled."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        _seed_post_brand_signal_row(s, "444", "qwen")
        s.bulk_insert_post_brand_discourse([{
            "tweet_id": "444",
            "brand_id": "qwen",
            "discourse_key": "fud",
            "act_id": 1,
        }])
        ok = s.bulk_update_nationalism(
            tweet_id="444",
            brand_id="qwen",
            discourse_key="fud",
            act_id=1,
            china_nationalism="pro",
            us_nationalism="anti",
        )
        assert ok is True
        rows = s.get_post_brand_discourse_for_post("444")
        assert rows[0]["china_nationalism"] == "pro"
        assert rows[0]["us_nationalism"] == "anti"
    finally:
        s.close()


def test_bulk_update_nationalism_returns_false_when_row_missing(tmp_path):
    """No matching discourse row → False (not an error)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        _seed_post_brand_signal_row(s, "555", "claude")
        ok = s.bulk_update_nationalism(
            tweet_id="555",
            brand_id="claude",
            discourse_key="dunk_yingyang",
            act_id=1,
            china_nationalism="none",
            us_nationalism="none",
        )
        assert ok is False
    finally:
        s.close()


def test_get_post_brand_discourse_joins_back_to_text_keys(tmp_path):
    """The read method returns TEXT keys, not INTEGER ids."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        _seed_post_brand_signal_row(s, "666", "openai")
        s.bulk_insert_post_brand_discourse([{
            "tweet_id": "666",
            "brand_id": "openai",
            "discourse_key": "ai_slop_critique",
            "act_id": 1,
            "china_nationalism": "anti",
            "us_nationalism": "mild_pro",
        }])
        rows = s.get_post_brand_discourse_for_post("666")
        assert len(rows) == 1
        # TEXT-land: callers never see INTEGER ids.
        assert rows[0]["brand_id"] == "openai"
        assert rows[0]["discourse_key"] == "ai_slop_critique"
        assert rows[0]["china_nationalism"] == "anti"
        assert rows[0]["us_nationalism"] == "mild_pro"
        assert rows[0]["act_id"] == 1
    finally:
        s.close()


def test_bulk_insert_post_brand_discourse_act_id_range_guard(tmp_path):
    """act_id outside [1, 99] raises ValueError."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        _seed_post_brand_signal_row(s, "777", "openai")
        with pytest.raises(ValueError):
            s.bulk_insert_post_brand_discourse([{
                "tweet_id": "777",
                "brand_id": "openai",
                "discourse_key": "genuine_hype",
                "act_id": 0,
            }])
        with pytest.raises(ValueError):
            s.bulk_insert_post_brand_discourse([{
                "tweet_id": "777",
                "brand_id": "openai",
                "discourse_key": "genuine_hype",
                "act_id": 100,
            }])
    finally:
        s.close()


def test_bulk_insert_post_brand_discourse_idempotent_upsert(tmp_path):
    """Re-inserting the same (post, brand, discourse, act) updates
    the nationalism columns in place rather than failing."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        _seed_post_brand_signal_row(s, "888", "openai")
        # First insert: NULL nationalism.
        s.bulk_insert_post_brand_discourse([{
            "tweet_id": "888",
            "brand_id": "openai",
            "discourse_key": "self_deprecation",
            "act_id": 1,
        }])
        # Second insert: same PK, with nationalism.
        n = s.bulk_insert_post_brand_discourse([{
            "tweet_id": "888",
            "brand_id": "openai",
            "discourse_key": "self_deprecation",
            "act_id": 1,
            "china_nationalism": "mixed",
            "us_nationalism": "mixed",
        }])
        assert n == 1  # upsert counts as written
        rows = s.get_post_brand_discourse_for_post("888")
        assert len(rows) == 1  # still one row, not two
        assert rows[0]["china_nationalism"] == "mixed"
    finally:
        s.close()