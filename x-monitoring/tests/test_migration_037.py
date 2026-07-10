# {{AGENT_ATTRIBUTION}}
"""Tests for migration 037: brands_accounts canonization + post-step.

Plan: docs/plans/2026-07-11-002-feat-call-b-revival-via-x-query-specs-plan.md
(Unit U4).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from x_monitor.store import Store


# ----------------------------------------------------------------------
# 1. Fresh DB migrates to v37 — `_applied_config_snapshot` gets the
#    brands_accounts row from the post-step.
# ----------------------------------------------------------------------


def test_migration_037_fresh_db_post_step_writes_brands_accounts_json(
    tmp_path: Path,
) -> None:
    """A fresh DB after `auto_migrate=True` reaches v37; the post-step
    (KTD7 header lists `brands_accounts`) writes the brands_accounts
    artifact row to `_applied_config_snapshot`."""
    p = tmp_path / "fresh.db"
    s = Store(p, auto_migrate=True)
    try:
        assert 37 in s.applied_migrations()
        rows = s._conn.execute(
            "SELECT artifact FROM _applied_config_snapshot WHERE artifact='brands_accounts'"
        ).fetchall()
        assert len(rows) == 1
    finally:
        s.close()


# ----------------------------------------------------------------------
# 2. KTD7 header convention — migration 037 declares the post-step.
# ----------------------------------------------------------------------


def test_migration_037_post_step_touches_header_present() -> None:
    """The migration file's first non-comment line carries the KTD7
    header so the U4 post-step fires the brands_accounts export."""
    sql_path = (
        Path(__file__).parent.parent
        / "x_monitor"
        / "migrations"
        / "037_brands_accounts_canonize.sql"
    )
    text = sql_path.read_text(encoding="utf-8")
    assert "-- post_step_touches: brands_accounts" in text, (
        "KTD7 header missing — U4 post-step cannot gate on this migration."
    )


# ----------------------------------------------------------------------
# 3. Replay-safe — running apply_migrations twice is a no-op.
# ----------------------------------------------------------------------


def test_migration_037_replay_safe(tmp_path: Path) -> None:
    """A second apply_migrations on a v37 DB is a no-op; the
    `brands_accounts` artifact row is unchanged."""
    p = tmp_path / "replay.db"
    s1 = Store(p, auto_migrate=True)
    s1.close()

    s2 = Store(p, auto_migrate=False)
    try:
        n_before = s2._conn.execute(
            "SELECT COUNT(*) FROM _applied_config_snapshot WHERE artifact='brands_accounts'"
        ).fetchone()[0]
        applied = s2.apply_migrations()
        assert applied == []
        n_after = s2._conn.execute(
            "SELECT COUNT(*) FROM _applied_config_snapshot WHERE artifact='brands_accounts'"
        ).fetchone()[0]
        assert n_after == n_before
    finally:
        s2.close()


# ----------------------------------------------------------------------
# 4. `Store.read_brand_official_staff_handles` returns
#    {(handle, role_key), ...} tuples per brand from brands_accounts
#    joined to accounts + roles.
# ----------------------------------------------------------------------


def test_read_brand_official_staff_handles(tmp_path: Path) -> None:
    """`read_brand_official_staff_handles` returns the right shape:
    `dict[str, list[tuple[handle, role_key]]]`, filtered to
    `role_id IN (2, 3)` (official + staff)."""
    p = tmp_path / "accounts.db"
    s = Store(p, auto_migrate=True)
    try:
        # Seed brands + accounts + edges. Use OR IGNORE so the test
        # is robust to the brand rows already being seeded by
        # earlier migrations (the 20 enabled brands are inserted by
        # migration 030 / migration 032 etc.).
        for bid in ("minimax", "qwen"):
            s._conn.execute(
                "INSERT OR IGNORE INTO brands(nickname, is_sentinel) VALUES (?, 0)",
                (bid,),
            )
        for handle, role_key, bid in [
            ("MiniMaxAI", "official", "minimax"),
            ("MiniMax_AI", "staff", "minimax"),
            ("qwen_handle", "official", "qwen"),
        ]:
            # Skip accounts that already exist (some migrations seed
            # the same handles); use the existing row id when so.
            existing = s._conn.execute(
                "SELECT id FROM accounts WHERE handle=?",
                (handle,),
            ).fetchone()
            if existing is None:
                s._conn.execute(
                    "INSERT INTO accounts(author_id, handle) VALUES (?, ?)",
                    (f"handle:{handle}", handle),
                )
                account_id = s._conn.execute(
                    "SELECT id FROM accounts WHERE handle=?",
                    (handle,),
                ).fetchone()["id"]
            else:
                account_id = existing["id"]
            role_id = s._conn.execute(
                "SELECT id FROM roles WHERE key=?", (role_key,)
            ).fetchone()["id"]
            brand_pk = s._conn.execute(
                "SELECT id FROM brands WHERE nickname=?", (bid,)
            ).fetchone()["id"]
            # Skip the edge if it already exists (uniqueness on
            # (brand_id, accounts_id)).
            already_edge = s._conn.execute(
                "SELECT 1 FROM brands_accounts WHERE brand_id=? AND accounts_id=? AND role_id=?",
                (brand_pk, account_id, role_id),
            ).fetchone()
            if already_edge is None:
                s._conn.execute(
                    "INSERT INTO brands_accounts(brand_id, accounts_id, role_id, added_at) "
                    "VALUES (?, ?, ?, datetime('now'))",
                    (brand_pk, account_id, role_id),
                )
        s._conn.commit()

        out = s.read_brand_official_staff_handles(["minimax", "qwen"])
        # Order in the dict is by brand_id, handle — the assertions
        # check set membership rather than exact order to be robust
        # to the migration-time seed (which may already include some
        # of these handles).
        assert "minimax" in out
        assert "qwen" in out
        minimax_pairs = set(out["minimax"])
        qwen_pairs = set(out["qwen"])
        # Both must include at least the seed we inserted.
        assert ("MiniMaxAI", "official") in minimax_pairs
        assert ("MiniMax_AI", "staff") in minimax_pairs
        assert ("qwen_handle", "official") in qwen_pairs
    finally:
        s.close()


# ----------------------------------------------------------------------
# 5. `Store.export_brands_accounts_json` writes a JSON round-trip
#    with the expected schema.
# ----------------------------------------------------------------------


def test_export_brands_accounts_json(tmp_path: Path) -> None:
    """The post-step export writes `data/brands_accounts.json` with
    `brand_id / handle / role_key / added_at` per row, deterministic
    across REINDEX (explicit ORDER BY)."""
    p = tmp_path / "export.db"
    s = Store(p, auto_migrate=True)
    try:
        # Reset the snapshot row so the explicit export is a first-write.
        s._conn.execute("DELETE FROM _applied_config_snapshot")
        s._conn.commit()

        target = tmp_path / "brands_accounts.json"
        wrote = s.export_brands_accounts_json(target)
        assert wrote is True
        body = json.loads(target.read_text(encoding="utf-8"))
        assert isinstance(body, list)
        for row in body:
            assert set(row.keys()) == {"brand_id", "handle", "role_key", "added_at"}
    finally:
        s.close()


# ----------------------------------------------------------------------
# 6. data/accounts/ is gone — `git ls-files` returns empty.
# ----------------------------------------------------------------------


def test_data_accounts_directory_removed(tmp_path: Path) -> None:
    """After U4 commits, `data/accounts/` does not exist in the
    repo tree. This test guards the deletion by importing a check
    against the live x-monitoring/ layout."""
    accounts_dir = Path(__file__).parent.parent / "data" / "accounts"
    # Note: tests run from the project root in CI; we just check
    # that the directory is gone (the test passes after the commit).
    assert not accounts_dir.exists(), (
        "data/accounts/ should be deleted by U4; still on disk"
    )