"""Store: i18n helpers + enum FK guards (Unit 3).

Plan: docs/plans/2026-06-23-001-feat-i18n-locale-columns-plan.md (Unit 3).

Verifies:
- `_known_signal_keys` / `_known_role_keys` cached loaders return the
  seeded key sets and are idempotent across repeated calls (cache works).
  (engagement_tier was dropped in migration 012.)
- `_pick_i18n_text` fallback chain: locale col → en col → source col.
- `_pick_enum_label` lookup: zh_cn → en → raw value.
- FK guards drop unknown values to the dead-letter JSONL log without
  raising IntegrityError, and the corresponding row is not written.
- FK guards DO write rows with valid values.
- Bulk integration: 1000 posts_brands_signals rows with 0.1% unknown
  signal values → 990 succeed, 10 go to dead-letter.
"""

import json
from pathlib import Path

import pytest


# --- cached key loaders -------------------------------------------------


def test_known_signal_keys_returns_seeded_set(tmp_path):
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        keys = s._known_signal_keys()
        assert keys == {
            "release", "community_question", "criticism",
            "commenter_capture", "praise", "other",
        }
    finally:
        s.close()


def test_known_role_keys_returns_seeded_set(tmp_path):
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        keys = s._known_role_keys()
        assert keys == {"official", "community", "researcher", "press", "vendor"}
    finally:
        s.close()


def test_known_signal_keys_is_cached(tmp_path):
    """Calling twice in a row returns the same set object (cache hit)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        first = s._known_signal_keys()
        second = s._known_signal_keys()
        assert first is second  # identity check — same cached object
    finally:
        s.close()


# --- _pick_i18n_text fallback chain -------------------------------------


def test_pick_i18n_text_returns_zh_cn_when_present(tmp_path):
    from x_monitor.store import Store

    row = {
        "display_name": "MiniMax AI",
        "display_name_en": "MiniMax AI",
        "display_name_zh_cn": "MiniMax AI 公司",
    }
    text, is_translated = Store._pick_i18n_text(row, "display_name", "zh_cn")
    assert text == "MiniMax AI 公司"
    assert is_translated is True


def test_pick_i18n_text_falls_back_to_en(tmp_path):
    from x_monitor.store import Store

    row = {
        "display_name": "MiniMax AI",
        "display_name_en": "MiniMax AI",
        "display_name_zh_cn": None,
    }
    text, is_translated = Store._pick_i18n_text(row, "display_name", "zh_cn")
    assert text == "MiniMax AI"
    assert is_translated is False


def test_pick_i18n_text_falls_back_to_source(tmp_path):
    from x_monitor.store import Store

    row = {
        "display_name": "MiniMax AI",
        "display_name_en": None,
        "display_name_zh_cn": None,
    }
    text, is_translated = Store._pick_i18n_text(row, "display_name", "zh_cn")
    assert text == "MiniMax AI"
    assert is_translated is False


def test_pick_i18n_text_en_locale_returns_en_col(tmp_path):
    from x_monitor.store import Store

    row = {
        "display_name": "SourceName",
        "display_name_en": "EnglishName",
        "display_name_zh_cn": "中文名",
    }
    text, is_translated = Store._pick_i18n_text(row, "display_name", "en")
    assert text == "EnglishName"
    assert is_translated is True


def test_pick_i18n_text_unsupported_locale_falls_back_to_en(tmp_path):
    from x_monitor.store import Store

    row = {
        "display_name": "SourceName",
        "display_name_en": "EnglishName",
        "display_name_zh_cn": "中文名",
    }
    text, is_translated = Store._pick_i18n_text(row, "display_name", "fr")
    assert text == "EnglishName"
    assert is_translated is True


# --- _pick_enum_label lookup --------------------------------------------


def test_pick_enum_label_returns_zh_cn_label(tmp_path):
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        assert s._pick_enum_label("signal", "release", "zh_cn") == "发布"
        assert s._pick_enum_label("signal", "praise", "zh_cn") == "称赞"
    finally:
        s.close()


def test_pick_enum_label_returns_en_label(tmp_path):
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        assert s._pick_enum_label("signal", "release", "en") == "Release"
        assert s._pick_enum_label("role", "official", "en") == "Official"
    finally:
        s.close()


def test_pick_enum_label_falls_back_to_en_when_zh_cn_missing(tmp_path):
    """If the zh_cn label isn't seeded (operator override removed it),
    fall back to the en label rather than returning the raw key."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        # Wipe the zh_cn label for "release" to simulate override removal.
        s._conn.execute(
            "DELETE FROM signal_labels WHERE key = ? AND lang = ?",
            ("release", "zh_cn"),
        )
        assert s._pick_enum_label("signal", "release", "zh_cn") == "Release"
    finally:
        s.close()


def test_pick_enum_label_returns_raw_value_on_full_miss(tmp_path):
    """If the key doesn't exist at all (unseeded enum), return the raw
    value so the UI doesn't render 'None'."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        assert s._pick_enum_label("signal", "ghost_signal", "zh_cn") == "ghost_signal"
    finally:
        s.close()


def test_pick_enum_label_unknown_family_raises(tmp_path):
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        with pytest.raises(ValueError, match="unknown enum family"):
            s._pick_enum_label("not_a_family", "x", "en")
    finally:
        s.close()


def test_pick_enum_label_empty_value_returns_empty_string(tmp_path):
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        assert s._pick_enum_label("signal", None, "zh_cn") == ""
        assert s._pick_enum_label("signal", "", "zh_cn") == ""
    finally:
        s.close()


# --- dead-letter log ---------------------------------------------------


def test_dead_letter_enum_writes_jsonl(tmp_path):
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        s._dead_letter_enum(
            "signal", "ghost_signal",
            table="posts_brands_signals",
            post_id="t1",
            brand_id="minimax",
        )
        # File should be at <db_path.parent>/runs/<YYYY-MM-DD>/enum_dead_letter.jsonl
        runs = list((tmp_path / "runs").iterdir())
        assert len(runs) == 1
        log_path = runs[0] / "enum_dead_letter.jsonl"
        assert log_path.exists()
        line = log_path.read_text(encoding="utf-8").strip()
        record = json.loads(line)
        assert record["family"] == "signal"
        assert record["value"] == "ghost_signal"
        assert record["table"] == "posts_brands_signals"
        assert record["post_id"] == "t1"
        assert "ts" in record
    finally:
        s.close()


# --- FK guards on insert_posts_brands_signals -----------------------------


def test_insert_posts_brands_signals_unknown_signal_goes_to_dead_letter(tmp_path):
    """An unknown signal value does NOT raise IntegrityError; it lands in
    the dead-letter log and the row is not written."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        # Need a posts row for the FK chain to even reach signal.
        # 'minimax' brand is seeded by migration 004.
        s._conn.execute(
            "INSERT INTO posts (tweet_id, author_handle, fetched_at) "
            "VALUES (?, ?, ?)",
            ("t_signal_guard", "u_signal", "2026-06-23T00:00:00+00:00"),
        )
        # Unknown signal — must NOT raise.
        s.insert_posts_brands_signals(
            "t_signal_guard", "minimax", "ghost_signal",
        )
        # Row not written.
        row = s._conn.execute(
            "SELECT * FROM posts_brands_signals WHERE post_id = ?",
            ("t_signal_guard",),
        ).fetchone()
        assert row is None
        # Dead-letter log has one entry.
        log_files = list((tmp_path / "runs").rglob("enum_dead_letter.jsonl"))
        assert len(log_files) == 1
        record = json.loads(log_files[0].read_text(encoding="utf-8").strip().splitlines()[0])
        assert record["family"] == "signal"
        assert record["value"] == "ghost_signal"
    finally:
        s.close()


def test_insert_posts_brands_signals_valid_signal_writes(tmp_path):
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        s._conn.execute(
            "INSERT INTO posts (tweet_id, author_handle, fetched_at) "
            "VALUES (?, ?, ?)",
            ("t_valid_signal", "u_sig", "2026-06-23T00:00:00+00:00"),
        )
        s.insert_posts_brands_signals("t_valid_signal", "minimax", "release")
        row = s._conn.execute(
            "SELECT signal_id FROM posts_brands_signals WHERE post_id = ?",
            ("t_valid_signal",),
        ).fetchone()
        assert row["signal_id"] == "release"
        # No dead-letter entry.
        log_files = list((tmp_path / "runs").rglob("enum_dead_letter.jsonl"))
        assert log_files == []
    finally:
        s.close()


# --- FK guards on upsert_account ---------------------------------------


def test_upsert_account_unknown_role_skips_brands_accounts_edge(tmp_path):
    """Legacy callers pass role='unknown', which is NOT in role_keys.
    The accounts row is still upserted; the brands_accounts edge is not
    written; a dead-letter record is created."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        s.upsert_account("minimax", "u_role_unknown", role="unknown")
        # accounts row exists.
        acc = s._conn.execute(
            "SELECT author_id FROM accounts WHERE author_id = ?",
            ("handle:u_role_unknown",),
        ).fetchone()
        assert acc is not None
        # brands_accounts row NOT written.
        ba = s._conn.execute(
            "SELECT * FROM brands_accounts WHERE author_id = ?",
            ("handle:u_role_unknown",),
        ).fetchone()
        assert ba is None
        # Dead-letter log has the role record.
        log_files = list((tmp_path / "runs").rglob("enum_dead_letter.jsonl"))
        assert len(log_files) == 1
        lines = log_files[0].read_text(encoding="utf-8").strip().splitlines()
        record = json.loads(lines[0])
        assert record["family"] == "role"
        assert record["value"] == "unknown"
    finally:
        s.close()


def test_upsert_account_known_role_writes_brands_accounts_edge(tmp_path):
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        s.upsert_account(
            "minimax", "u_role_official",
            role="official",
        )
        ba = s._conn.execute(
            "SELECT role_id FROM brands_accounts WHERE author_id = ?",
            ("handle:u_role_official",),
        ).fetchone()
        assert ba["role_id"] == "official"
        # No dead-letter entries.
        assert list((tmp_path / "runs").rglob("enum_dead_letter.jsonl")) == []
    finally:
        s.close()


# --- bulk integration: 0.1% unknown signals ----------------------------


def test_bulk_insert_signals_with_1_percent_unknown(tmp_path):
    """Bulk integration: 1000 posts_brands_signals inserts with 1%
    unknown signal values → 990 succeed, 10 land in dead-letter."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        s._conn.execute(
            "INSERT INTO posts (tweet_id, author_handle, fetched_at) "
            "VALUES (?, ?, ?)",
            ("t_bulk", "u_bulk", "2026-06-23T00:00:00+00:00"),
        )
        # 'minimax' and 'qwen' are seeded by migration 004.
        # Build 1000 posts + signals with 1% unknown signal values.
        # We can't use insert_posts (it expects many other fields), so we
        # bulk-insert into posts + posts_brands_signals directly. The guard
        # only fires on insert_posts_brands_signals.
        valid_signals = ["release", "criticism", "praise", "other"]
        unknown_signal = "totally_made_up"
        rows = []
        for i in range(1000):
            tid = f"t_bulk_{i:04d}"
            brand_id = "minimax" if i % 2 == 0 else "qwen"
            sig = unknown_signal if (i % 100 == 0) else valid_signals[i % 4]
            rows.append((tid, brand_id, sig))
            s._conn.execute(
                "INSERT INTO posts (tweet_id, author_handle, fetched_at) "
                "VALUES (?, ?, ?)",
                (tid, "u_bulk", "2026-06-23T00:00:00+00:00"),
            )
        # Run all 1000 inserts through the guarded method.
        for tid, brand_id, sig in rows:
            s.insert_posts_brands_signals(tid, brand_id, sig)

        # Count written vs dropped.
        n_written = s._conn.execute(
            "SELECT COUNT(*) AS n FROM posts_brands_signals"
        ).fetchone()["n"]
        assert n_written == 990
        # Dead-letter log: 10 entries.
        log_files = list((tmp_path / "runs").rglob("enum_dead_letter.jsonl"))
        assert len(log_files) == 1
        lines = log_files[0].read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 10
        for line in lines:
            rec = json.loads(line)
            assert rec["family"] == "signal"
            assert rec["value"] == unknown_signal
    finally:
        s.close()


# --- insert_posts bulk signal guard ------------------------------------


def test_insert_posts_drops_unknown_signal_via_bulk_path(tmp_path):
    """insert_posts's bulk path also gets the signal FK guard (the LLM
    is the signal source and may hallucinate)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        posts = [
            {
                "id": "t_bulk_sig_ok",
                "author_handle": "u_b",
                "author_id": "999",
                "text": "valid",
                "created_at": "2026-06-23T00:00:00+00:00",
                "brand_ids": ["minimax"],
                "signals": {"minimax": "release"},
            },
            {
                "id": "t_bulk_sig_bad",
                "author_handle": "u_b",
                "author_id": "999",
                "text": "invalid signal",
                "created_at": "2026-06-23T00:00:00+00:00",
                "brand_ids": ["minimax"],
                "signals": {"minimax": "made_up_signal"},
            },
        ]
        s.insert_posts(posts)
        # Valid signal is written.
        ok = s._conn.execute(
            "SELECT signal_id FROM posts_brands_signals WHERE post_id = ?",
            ("t_bulk_sig_ok",),
        ).fetchone()
        assert ok["signal_id"] == "release"
        # Invalid signal was dropped — no row written.
        bad = s._conn.execute(
            "SELECT * FROM posts_brands_signals WHERE post_id = ?",
            ("t_bulk_sig_bad",),
        ).fetchone()
        assert bad is None
        # Drop counter incremented.
        assert s._signals_dropped >= 1
        # Dead-letter log has the entry.
        log_files = list((tmp_path / "runs").rglob("enum_dead_letter.jsonl"))
        assert len(log_files) == 1
        record = json.loads(
            log_files[0].read_text(encoding="utf-8").strip().splitlines()[0]
        )
        assert record["family"] == "signal"
        assert record["value"] == "made_up_signal"
    finally:
        s.close()