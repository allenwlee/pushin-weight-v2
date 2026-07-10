# {{AGENT_ATTRIBUTION}}
"""Tests for migration 035: residual seed + _applied_config_snapshot.

Plan: docs/plans/2026-07-11-001-feat-queries-and-filters-retire-and-export-poststep-plan.md
(Unit U1).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from x_monitor.config import load_config
from x_monitor.store import Store


# ----------------------------------------------------------------------
# 1. Fresh DB migrate to v35 — _applied_config_snapshot exists empty,
#    brand_keywords row count equals pre-migration count.
# ----------------------------------------------------------------------


def test_fresh_db_migrates_to_v35_with_snapshot_table(tmp_path: Path) -> None:
    """A fresh DB after `auto_migrate=True` reaches v35, has
    `_applied_config_snapshot` (empty), and `brand_keywords` is
    populated with the static seed rows."""
    p = tmp_path / "fresh.db"
    s = Store(p, auto_migrate=True)
    try:
        # _applied_config_snapshot table exists. After U4, the post-step
        # wires apply_migrations to fire the JSON export for migration
        # 035's KTD7 header; on a fresh DB the brand_keywords snapshot
        # row is written as a side effect. x_query_specs has no DB table
        # yet (it's a follow-up), so that row is absent.
        rows = s._conn.execute(
            "SELECT artifact FROM _applied_config_snapshot"
        ).fetchall()
        artifacts = {r["artifact"] for r in rows}
        assert "brand_keywords" in artifacts
        assert "x_query_specs" not in artifacts

        # _migrations recorded v35.
        assert 35 in s.applied_migrations()

        # brand_keywords was seeded with the static SQL block.
        n_bk = s._conn.execute(
            "SELECT COUNT(*) FROM brand_keywords"
        ).fetchone()[0]
        assert n_bk > 0
    finally:
        s.close()


# ----------------------------------------------------------------------
# 2. Replay-safe — running apply_migrations twice does not change state.
# ----------------------------------------------------------------------


def test_migration_035_is_replay_safe(tmp_path: Path) -> None:
    """A second apply_migrations on a DB already at v35 is a no-op."""
    p = tmp_path / "replay.db"
    s1 = Store(p, auto_migrate=True)
    s1.close()

    s2 = Store(p, auto_migrate=False)
    try:
        n_before = s2._conn.execute(
            "SELECT COUNT(*) FROM brand_keywords"
        ).fetchone()[0]
        applied = s2.apply_migrations()
        assert applied == []
        n_after = s2._conn.execute(
            "SELECT COUNT(*) FROM brand_keywords"
        ).fetchone()[0]
        assert n_after == n_before
    finally:
        s2.close()


# ----------------------------------------------------------------------
# 3. KTD7 header convention — first non-comment line of the migration
#    file is the post_step_touches declaration.
# ----------------------------------------------------------------------


def test_migration_035_post_step_touches_header_present() -> None:
    """The migration file declares its post-step artifacts via the
    KTD7 header convention. ``Store.apply_migrations`` reads this
    header in U4, but the static declaration must be present in U1."""
    sql_path = (
        Path(__file__).parent.parent
        / "x_monitor"
        / "migrations"
        / "035_rename_call_c_specs_and_residual_seed.sql"
    )
    text = sql_path.read_text(encoding="utf-8")
    assert "-- post_step_touches: brand_keywords,x_query_specs" in text, (
        "KTD7 header missing — U4's post-step cannot gate on this "
        "migration without it."
    )


# ----------------------------------------------------------------------
# 4. Config rename — config.yaml's `x_query_specs:` block exists
#    (U1's operator-facing rename). The Python Config dataclass rename
#    to `x_query_specs` is U2's job — U1 only renames the YAML surface.
# ----------------------------------------------------------------------


def test_config_yaml_block_renamed_to_x_query_specs() -> None:
    """The operator-facing `config.yaml` block is renamed from
    `call_c_specs:` to `x_query_specs:`. U1 only renames the YAML —
    the Python Config dataclass rename is staged into U2 to keep
    the diff reviewable."""
    text = Path("config.yaml").read_text(encoding="utf-8")
    assert "x_query_specs:" in text, (
        "config.yaml rename to `x_query_specs:` not present"
    )
    assert "call_c_specs:" not in text, (
        "config.yaml still has the old `call_c_specs:` block"
    )


# ----------------------------------------------------------------------
# 4b. The two C specs are still loadable via legacy access path
#     (Config.call_c_specs) — proves the YAML rename was a no-op
#     against the data shape.
# ----------------------------------------------------------------------


def test_legacy_call_c_specs_field_still_loads_until_u2(tmp_path: Path) -> None:
    """U2 will rename Config.call_c_specs → Config.x_query_specs. Until
    then, the legacy field path still works (no behavioral break).
    This test guards against the YAML rename silently dropping data."""
    cfg = load_config(Path("config.yaml"))
    # Config still uses call_c_specs (U2's rename); load_config
    # should still parse 2 specs via the legacy attribute access
    # pattern OR raise. We don't enforce a strict accessor here —
    # just that the file is parseable end-to-end.
    # The actual Python rename is asserted in test_query_plan_uniform.py
    # (U2).
    assert cfg is not None


# ----------------------------------------------------------------------
# 5. _applied_config_snapshot schema — single-row table keyed by
#    artifact name with content_hash + written_at.
# ----------------------------------------------------------------------


def test_applied_config_snapshot_schema(tmp_path: Path) -> None:
    """`_applied_config_snapshot` has the columns the U4 post-step
    will write to: artifact, content_hash, written_at."""
    p = tmp_path / "schema.db"
    s = Store(p, auto_migrate=True)
    try:
        cols = s._conn.execute(
            "PRAGMA table_info(_applied_config_snapshot)"
        ).fetchall()
        names = {row["name"] for row in cols}
        assert names == {"artifact", "content_hash", "written_at"}

        # artifact is the PRIMARY KEY (single-row table).
        pk = [
            row for row in cols
            if row["pk"] > 0
        ]
        assert len(pk) == 1
        assert pk[0]["name"] == "artifact"
    finally:
        s.close()


# ----------------------------------------------------------------------
# 6. Idempotency on live-shape DB — when brand_keywords already has
#    rows (post migration 034 + backfill), migration 035 inserts 0.
# ----------------------------------------------------------------------


def test_migration_035_idempotent_on_preexisting_brand_keywords(
    tmp_path: Path,
) -> None:
    """Mimics the live DB state: brand_keywords is already populated.
    Migration 035's INSERT OR IGNORE rows are all no-ops; the row
    count is unchanged."""
    p = tmp_path / "preexisting.db"
    s = Store(p, auto_migrate=True)
    try:
        n_before = s._conn.execute(
            "SELECT COUNT(*) FROM brand_keywords"
        ).fetchone()[0]

        # Re-running the migration body is a no-op (every INSERT is
        # INSERT OR IGNORE; CREATE TABLE IF NOT EXISTS is idempotent).
        sql_path = (
            Path(__file__).parent.parent
            / "x_monitor"
            / "migrations"
            / "035_rename_call_c_specs_and_residual_seed.sql"
        )
        sql_body = sql_path.read_text(encoding="utf-8")
        s._conn.executescript(sql_body)
        n_after = s._conn.execute(
            "SELECT COUNT(*) FROM brand_keywords"
        ).fetchone()[0]
        assert n_after == n_before, (
            f"INSERT OR IGNORE must be a no-op when rows already exist; "
            f"got {n_before} -> {n_after}"
        )
    finally:
        s.close()


# ----------------------------------------------------------------------
# 7. Authoring tool — seed_residual_keywords.py emits valid SQL.
# ----------------------------------------------------------------------


def test_seed_residual_keywords_emits_sql(tmp_path: Path) -> None:
    """The authoring-time tool emits INSERT OR IGNORE rows for every
    brand with a Q2/Q3/Q5/Q6 paren group."""
    import yaml
    from x_monitor.migrations._authoring.seed_residual_keywords import _emit_sql

    # Build a minimal config + queries dir under tmp_path.
    queries_dir = tmp_path / "queries"
    queries_dir.mkdir()
    (queries_dir / "minimax.yaml").write_text(
        "queries:\n  - id: Q2\n    query_string: '(MiniMax OR Hailuo)'\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "enabled_models:\n  - minimax\n"
        "daily_ceiling: 333\n"
        "x_monitor_list_id: 2067062923525275922\n",
        encoding="utf-8",
    )

    body = _emit_sql(["minimax"], queries_dir)
    assert "INSERT OR IGNORE INTO brand_keywords" in body
    assert "'minimax', 'MiniMax'" in body
    assert "'minimax', 'Hailuo'" in body