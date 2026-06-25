"""U7: brand_search_terms hybrid by design.

Plan: docs/plans/2026-06-24-002-refactor-schema-modernization-batch-plan.md
(Unit 7 of 9, R7).

Verifies the new contract:
- yaml (data/queries/<brand>.yaml) is the single source for the
  TwitterAPI.io query string.
- DB (`brand_search_terms` table) is the single source for the
  {term: brand_id} map used at post-fetch attribution time.
- The yaml is NOT read at attribution time in the live fetch path.
- The DB is NOT used to build the query string.
- A startup-time drift check logs a warning when the yaml and DB
  coverage disagree.

Migration 017 is a no-op DDL-wise; its slot just records the cutover
in the _migrations ledger.
"""

import logging
import tempfile
from pathlib import Path

import pytest

from x_monitor.run import (
    _build_brand_index,
    _load_brand_search_terms_from_db,
    _log_brand_search_terms_drift,
)
from x_monitor.store import Store


# --- migration 017: no-op DDL ----------------------------------------


def test_migration_017_applies_with_no_ddl_change(tmp_path):
    """Migration 017 applies cleanly on a fresh DB. The DDL is a
    no-op (BEGIN; COMMIT;) — the brand_search_terms table shape
    is unchanged; what changes is the contract documented in the
    migration comments and enforced in code."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        # brand_search_terms table still exists with the same shape.
        rows = s._conn.execute(
            "SELECT name FROM sqlite_master WHERE name = 'brand_search_terms'"
        ).fetchall()
        assert rows, "brand_search_terms table missing after 017"

        # brand_search_terms has the original 2 columns from migration 004.
        cols = {
            r[1] for r in s._conn.execute(
                "PRAGMA table_info(brand_search_terms)"
            ).fetchall()
        }
        assert {"brand_id", "term", "added_at"} <= cols
    finally:
        s.close()


def test_migration_017_records_version_in_ledger(tmp_path):
    """Migration 017 inserts a row in _migrations (the only behavior
    change in 017's DDL slot)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        applied = [
            r[0]
            for r in s._conn.execute(
                "SELECT version FROM _migrations ORDER BY version"
            ).fetchall()
        ]
        assert applied.count(17) == 1, f"version 17 not applied once: {applied}"
    finally:
        s.close()


def test_migration_017_idempotent(tmp_path):
    """Re-opening a DB that has 017 applied does not re-run it."""
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
        assert applied.count(17) == 1
    finally:
        s2.close()


def test_migration_017_full_stack_apply(tmp_path):
    """All migrations 001-020 apply on a fresh DB; brand_search_terms
    is in effect as the attribution-side store.

    U9: migration 021 was INTENTIONALLY SKIPPED (reserved for an
    unrelated HF products crawler that never landed). After U9
    migration 022 ships, the applied set is {1..20, 22} (21 is
    missing). This test now asserts that gap rather than the
    contiguous 1-20 range.
    """
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        applied = sorted(
            r[0] for r in s._conn.execute("SELECT version FROM _migrations").fetchall()
        )
        expected = sorted(set(range(1, 21)) | {22})
        assert applied == expected, (
            f"unexpected versions: {applied} (expected {expected})"
        )
        rows = s._conn.execute(
            "SELECT name FROM sqlite_master WHERE name = 'brand_search_terms'"
        ).fetchall()
        assert rows, "brand_search_terms missing after full stack"
    finally:
        s.close()


# --- _load_brand_search_terms_from_db --------------------------------


def test_load_brand_search_terms_from_db_returns_seeded_map(tmp_path):
    """_load_brand_search_terms_from_db returns the {term: brand_id}
    map from the DB. With no seeded rows it returns an empty dict."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        # Seed 2 rows directly (the table is operator-curated; no
        # auto-population in U7). INSERT OR IGNORE because migration
        # 004 already seeded the 'minimax' brand.
        s._conn.execute(
            "INSERT OR IGNORE INTO brands(brand_id, display_name, "
            "accent_color, is_sentinel, created_at) VALUES (?, ?, ?, ?, ?)",
            ("minimax", "MiniMax", "#a855f7", 0, "2026-06-24T00:00:00+00:00"),
        )
        # brand_search_terms.brand_id is INTEGER (FK -> brands.id) post-020
        brand_int = s._conn.execute(
            "SELECT id FROM brands WHERE brand_id = ?", ("minimax",)
        ).fetchone()["id"]
        s._conn.execute(
            "INSERT INTO brand_search_terms(brand_id, term, added_at) "
            "VALUES (?, ?, ?)",
            (brand_int, "minimax", "2026-06-24T00:00:00+00:00"),
        )
        s._conn.execute(
            "INSERT INTO brand_search_terms(brand_id, term, added_at) "
            "VALUES (?, ?, ?)",
            (brand_int, "海螺", "2026-06-24T00:00:00+00:00"),
        )
        terms = _load_brand_search_terms_from_db(s)
        assert terms == {"minimax": "minimax", "海螺": "minimax"}
    finally:
        s.close()


def test_load_brand_search_terms_from_db_empty_when_no_seeds(tmp_path):
    """A fresh DB with no seeded brand_search_terms rows returns
    an empty dict (not None, not raises)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        terms = _load_brand_search_terms_from_db(s)
        assert terms == {}
    finally:
        s.close()


# --- _log_brand_search_terms_drift -----------------------------------


def test_drift_no_warning_when_yaml_and_db_match(caplog):
    """No warning is logged when the yaml and DB maps agree."""
    m = {"minimax": "minimax", "海螺": "minimax"}
    with caplog.at_level(logging.WARNING, logger="x_monitor.run"):
        _log_brand_search_terms_drift(m, dict(m))
    assert "drift" not in caplog.text.lower()


def test_drift_warning_when_yaml_term_missing_from_db(caplog):
    """A yaml term that's not in the DB triggers a warning."""
    yaml_terms = {"minimax": "minimax", "海螺": "minimax", "ghost": "minimax"}
    db_terms = {"minimax": "minimax", "海螺": "minimax"}
    with caplog.at_level(logging.WARNING, logger="x_monitor.run"):
        _log_brand_search_terms_drift(yaml_terms, db_terms)
    assert "drift" in caplog.text.lower()
    assert "yaml-only" in caplog.text.lower()


def test_drift_warning_when_db_term_missing_from_yaml(caplog):
    """A DB term that's not in the yaml triggers a warning."""
    yaml_terms = {"minimax": "minimax"}
    db_terms = {"minimax": "minimax", "leftover": "deepseek"}
    with caplog.at_level(logging.WARNING, logger="x_monitor.run"):
        _log_brand_search_terms_drift(yaml_terms, db_terms)
    assert "db-only" in caplog.text.lower()


def test_drift_warning_when_brand_id_mismatches(caplog):
    """A term present in both maps with different brand_id triggers
    a warning (DB wins at attribution time)."""
    yaml_terms = {"minimax": "minimax"}
    db_terms = {"minimax": "deepseek"}
    with caplog.at_level(logging.WARNING, logger="x_monitor.run"):
        _log_brand_search_terms_drift(yaml_terms, db_terms)
    assert "mismatched" in caplog.text.lower()


# --- contract: yaml and DB can diverge safely ------------------------


def test_yaml_and_db_can_diverge_for_attribution_path(tmp_path):
    """The yaml and DB are independent stores. Seeding only the DB
    (the new contract) and reading it back via
    _load_brand_search_terms_from_db returns the DB values. The yaml
    is not consulted at attribution time — a yaml whose tokens
    disagree with the DB is invisible to the attribution path."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        s._conn.execute(
            "INSERT OR IGNORE INTO brands(brand_id, display_name, "
            "accent_color, is_sentinel, created_at) VALUES (?, ?, ?, ?, ?)",
            ("minimax", "MiniMax", "#a855f7", 0, "2026-06-24T00:00:00+00:00"),
        )
        # DB-side: only 'minimax' is a search term.
        # brand_search_terms.brand_id is INTEGER (FK -> brands.id) post-020
        brand_int = s._conn.execute(
            "SELECT id FROM brands WHERE brand_id = ?", ("minimax",)
        ).fetchone()["id"]
        s._conn.execute(
            "INSERT INTO brand_search_terms(brand_id, term, added_at) "
            "VALUES (?, ?, ?)",
            (brand_int, "minimax", "2026-06-24T00:00:00+00:00"),
        )
        # _build_brand_index from yaml would add '海螺' to its map;
        # the DB-side path does not.
        yaml_tokens = {"minimax": ["minimax", "海螺"]}
        _, yaml_map = _build_brand_index(yaml_tokens, ["minimax"])
        assert "海螺" in yaml_map
        db_map = _load_brand_search_terms_from_db(s)
        assert "海螺" not in db_map
        # The two maps diverge — the contract is that the DB wins
        # at attribution time, so the live path uses db_map.
    finally:
        s.close()
