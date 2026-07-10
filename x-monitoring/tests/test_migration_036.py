# {{AGENT_ATTRIBUTION}}
"""Tests for migration 036: add is_primary to brand_keywords + seed curated subset.

Plan: docs/plans/2026-07-11-002-feat-call-b-revival-via-x-query-specs-plan.md
(Unit U1).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from x_monitor.store import Store


# ----------------------------------------------------------------------
# 1. Fresh DB migrates to v36 — is_primary column exists, primary rows
#    are seeded per enabled_models brand.
# ----------------------------------------------------------------------


def test_migration_036_fresh_db_seeds_primary_subset(tmp_path: Path) -> None:
    """A fresh DB after `auto_migrate=True` reaches v36 with the
    `is_primary` column and a curated 2-4-token primary subset per
    `enabled_models` brand."""
    p = tmp_path / "fresh.db"
    s = Store(p, auto_migrate=True)
    try:
        assert 36 in s.applied_migrations()

        # is_primary column exists with default 0
        cols = s._conn.execute("PRAGMA table_info(brand_keywords)").fetchall()
        names = {row["name"] for row in cols}
        assert "is_primary" in names
        # All non-primary rows default to 0; primary rows set explicitly.
        for row in cols:
            if row["name"] == "is_primary":
                assert row["dflt_value"] == "0"
                assert row["notnull"] == 1

        # Per-brand primary counts in [2, 4]
        for bid in [
            "minimax", "qwen", "deepseek", "glm", "mimo", "moonshot_kimi",
            "inclusionai", "mistral", "stepfun", "ernie", "hunyuan",
            "llama", "nemo_megatron", "doubao", "yi", "sensechat",
            "exaone", "kuaishou", "sakana_ai", "upstage",
        ]:
            n = s._conn.execute(
                "SELECT COUNT(*) FROM brand_keywords WHERE brand_id=? AND is_primary=1",
                (bid,),
            ).fetchone()[0]
            assert 2 <= n <= 4, f"{bid} has {n} primary rows; expected 2-4"

        # Total primary rows is in a sensible range (20 brands * ~3 = ~60).
        n_total = s._conn.execute(
            "SELECT COUNT(*) FROM brand_keywords WHERE is_primary=1"
        ).fetchone()[0]
        assert 40 <= n_total <= 80
    finally:
        s.close()


# ----------------------------------------------------------------------
# 2. Replay-safe — running apply_migrations twice on the same DB is a no-op.
# ----------------------------------------------------------------------


def test_migration_036_replay_safe(tmp_path: Path) -> None:
    """A second apply_migrations on a DB already at v36 is a no-op;
    primary row count is unchanged."""
    p = tmp_path / "replay.db"
    s1 = Store(p, auto_migrate=True)
    s1.close()

    s2 = Store(p, auto_migrate=False)
    try:
        n_before = s2._conn.execute(
            "SELECT COUNT(*) FROM brand_keywords WHERE is_primary=1"
        ).fetchone()[0]
        applied = s2.apply_migrations()
        assert applied == []
        n_after = s2._conn.execute(
            "SELECT COUNT(*) FROM brand_keywords WHERE is_primary=1"
        ).fetchone()[0]
        assert n_after == n_before
    finally:
        s2.close()


# ----------------------------------------------------------------------
# 3. KTD7 header — migration file declares its post-step artifacts.
# ----------------------------------------------------------------------


def test_migration_036_post_step_touches_header_present() -> None:
    """The migration file's first non-comment line carries the KTD7
    header so the U4 runner fires the JSON export after apply."""
    sql_path = (
        Path(__file__).parent.parent
        / "x_monitor"
        / "migrations"
        / "036_add_is_primary_to_brand_keywords.sql"
    )
    text = sql_path.read_text(encoding="utf-8")
    assert "-- post_step_touches: brand_keywords" in text, (
        "KTD7 header missing — U4 post-step cannot gate on this migration."
    )


# ----------------------------------------------------------------------
# 4. Non-primary rows unchanged — existing is_primary=0 rows are NOT
#    updated; only the curated subset flips to is_primary=1.
# ----------------------------------------------------------------------


def test_migration_036_non_primary_rows_unchanged(tmp_path: Path) -> None:
    """All pre-existing brand_keywords rows that aren't in the curated
    primary subset remain is_primary=0 after migration."""
    p = tmp_path / "non_primary.db"
    s = Store(p, auto_migrate=True)
    try:
        n_total = s._conn.execute(
            "SELECT COUNT(*) FROM brand_keywords"
        ).fetchone()[0]
        n_primary = s._conn.execute(
            "SELECT COUNT(*) FROM brand_keywords WHERE is_primary=1"
        ).fetchone()[0]
        n_non_primary = s._conn.execute(
            "SELECT COUNT(*) FROM brand_keywords WHERE is_primary=0"
        ).fetchone()[0]
        assert n_primary + n_non_primary == n_total
        # The plan's curated subset is small relative to the total row count
        # (operators grew brand_keywords post-migration 034).
        assert n_primary < n_total
        assert n_non_primary > 0
    finally:
        s.close()


# ----------------------------------------------------------------------
# 5. Post-step export includes is_primary — after apply_migrations
#    triggers the KTD7 post-step, data/brand_keywords.json round-trips
#    with the new column.
# ----------------------------------------------------------------------


def test_migration_036_export_includes_is_primary(tmp_path: Path) -> None:
    """`Store.export_brand_keywords_json` writes every row with the
    `is_primary` field populated. The post-step (which fires
    automatically on migration 036 via KTD7 header) writes the same
    shape; this test asserts the explicit export API."""
    p = tmp_path / "export.db"
    s = Store(p, auto_migrate=True)
    try:
        # Reset the snapshot row so the explicit export is a first-write.
        s._conn.execute("DELETE FROM _applied_config_snapshot")
        s._conn.commit()

        target = tmp_path / "brand_keywords.json"
        wrote = s.export_brand_keywords_json(target)
        assert wrote is True
        assert target.exists()

        body = json.loads(target.read_text(encoding="utf-8"))
        assert isinstance(body, list)
        assert len(body) > 0
        # Every row has is_primary as an int (0 or 1).
        for row in body:
            assert "is_primary" in row
            assert isinstance(row["is_primary"], int)
            assert row["is_primary"] in (0, 1)
        # At least one row has is_primary=1 (curated subset).
        assert any(row["is_primary"] == 1 for row in body)
        # The export row shape preserves all prior columns.
        first = body[0]
        assert set(first.keys()) == {"brand_id", "pattern", "is_regex", "is_primary"}
    finally:
        s.close()


# ----------------------------------------------------------------------
# 6. Each enabled_models brand has a primary token — confirms the
#    curated subset covers every brand in enabled_models, not a subset.
# ----------------------------------------------------------------------


def test_migration_036_covers_all_enabled_brands(tmp_path: Path) -> None:
    """Every brand in `enabled_models` has at least one is_primary=1 row."""
    p = tmp_path / "coverage.db"
    s = Store(p, auto_migrate=True)
    try:
        with open(Path("config.yaml"), encoding="utf-8") as f:
            import yaml

            cfg = yaml.safe_load(f)
        for bid in cfg["enabled_models"]:
            n = s._conn.execute(
                "SELECT COUNT(*) FROM brand_keywords WHERE brand_id=? AND is_primary=1",
                (bid,),
            ).fetchone()[0]
            assert n >= 1, (
                f"{bid} is in enabled_models but has 0 is_primary=1 rows"
            )
    finally:
        s.close()


# ----------------------------------------------------------------------
# 7. Legacy xiaomi_mimo brand (migration 030) has zero primary rows.
# ----------------------------------------------------------------------


def test_migration_036_legacy_brand_unaffected(tmp_path: Path) -> None:
    """The legacy migration-030 brand `xiaomi_mimo` (superseded by
    `mimo`) is not in enabled_models and gets zero is_primary=1 rows."""
    p = tmp_path / "legacy.db"
    s = Store(p, auto_migrate=True)
    try:
        n = s._conn.execute(
            "SELECT COUNT(*) FROM brand_keywords WHERE brand_id='xiaomi_mimo' AND is_primary=1"
        ).fetchone()[0]
        assert n == 0
    finally:
        s.close()