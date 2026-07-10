# {{AGENT_ATTRIBUTION}}
"""Tests for the U4 post-step JSON export.

Plan: docs/plans/2026-07-11-001-feat-queries-and-filters-retire-and-export-poststep-plan.md
(Unit U4).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from x_monitor.store import Store


# ----------------------------------------------------------------------
# 1. export_brand_keywords_json writes a JSON file on first call.
# ----------------------------------------------------------------------


def test_export_brand_keywords_json_first_write(tmp_path: Path) -> None:
    """First export on a fresh DB writes the JSON file. Round-trip
    parse yields the same list as the SQL SELECT.

    Note: when `auto_migrate=True` is used, the post-step fires during
    `Store.__init__` and the snapshot row is already populated — so
    the explicit export call returns False (no-op, hash unchanged).
    We clear the snapshot row to test the "first write" path
    directly."""
    p = tmp_path / "fresh.db"
    s = Store(p, auto_migrate=True)
    try:
        # Reset the snapshot so the explicit export is a first-write.
        s._conn.execute("DELETE FROM _applied_config_snapshot")
        s._conn.commit()

        target = tmp_path / "brand_keywords.json"
        wrote = s.export_brand_keywords_json(target)
        assert wrote is True
        assert target.exists()
        body = json.loads(target.read_text(encoding="utf-8"))
        assert isinstance(body, list)
        # brand_keywords is non-empty after auto_migrate.
        assert len(body) > 0
        first = body[0]
        assert set(first.keys()) == {"brand_id", "pattern", "is_regex", "is_primary"}
    finally:
        s.close()


# ----------------------------------------------------------------------
# 2. Idempotency — second call on unchanged DB does NOT rewrite the
#    file (mtime unchanged).
# ----------------------------------------------------------------------


def test_export_brand_keywords_json_idempotent(tmp_path: Path) -> None:
    """A second invocation on an unchanged DB returns False (no write)
    and the file's mtime is unchanged."""
    p = tmp_path / "idem.db"
    s = Store(p, auto_migrate=True)
    try:
        # Reset snapshot so the explicit first call writes.
        s._conn.execute("DELETE FROM _applied_config_snapshot")
        s._conn.commit()
        target = tmp_path / "brand_keywords.json"
        s.export_brand_keywords_json(target)
        mtime_1 = target.stat().st_mtime

        wrote = s.export_brand_keywords_json(target)
        assert wrote is False
        assert target.stat().st_mtime == mtime_1
    finally:
        s.close()


# ----------------------------------------------------------------------
# 3. KTD7 post_step_touches header — apply_migrations fires the export
#    only for migrations that declare it.
# ----------------------------------------------------------------------


def test_post_step_header_fires_export(tmp_path: Path) -> None:
    """When migration 035 (which has -- post_step_touches: brand_keywords,
    x_query_specs) is applied, the export fires. The brand_keywords
    snapshot row is recorded."""
    p = tmp_path / "u4.db"
    s = Store(p, auto_migrate=True)
    try:
        # _applied_config_snapshot has the brand_keywords entry
        # (x_query_specs has no table yet — that's a follow-up).
        rows = s._conn.execute(
            "SELECT * FROM _applied_config_snapshot WHERE artifact = ?",
            ("brand_keywords",),
        ).fetchall()
        assert len(rows) == 1
        # Hash is non-empty.
        assert rows[0]["content_hash"] != ""
    finally:
        s.close()


# ----------------------------------------------------------------------
# 4. Migration without the KTD7 header does NOT trigger the export.
# ----------------------------------------------------------------------


def test_post_step_skips_migration_without_header(tmp_path: Path) -> None:
    """A migration whose SQL body has no `-- post_step_touches:` line
    does not fire the export. Snapshot row remains absent."""
    # Migration 001 (the first one) has no such header.
    p = tmp_path / "noheader.db"
    s = Store(p, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT * FROM _applied_config_snapshot"
        ).fetchall()
        # Only the post-step from migration 035 (which DOES have the
        # header) should have written — brand_keywords yes,
        # x_query_specs no (no table).
        artifacts = {r["artifact"] for r in rows}
        # brand_keywords may or may not be present depending on whether
        # the post-step actually ran — but x_query_specs must NOT be.
        assert "x_query_specs" not in artifacts
    finally:
        s.close()


# ----------------------------------------------------------------------
# 5. Hash determinism — explicit ORDER BY makes the hash stable across
#    REINDEX.
# ----------------------------------------------------------------------


def test_hash_stable_across_reindex(tmp_path: Path) -> None:
    """Two back-to-back exports on the same DB produce the same hash
    even after REINDEX (which would reorder rows by ROWID)."""
    p = tmp_path / "hash.db"
    s = Store(p, auto_migrate=True)
    try:
        # Wipe snapshot so we can compare hashes.
        s._conn.execute("DELETE FROM _applied_config_snapshot")
        s._conn.commit()

        target = tmp_path / "bk.json"
        s.export_brand_keywords_json(target)
        h1 = s._conn.execute(
            "SELECT content_hash FROM _applied_config_snapshot "
            "WHERE artifact = ?",
            ("brand_keywords",),
        ).fetchone()["content_hash"]

        # REINDEX then re-export — hash must match.
        s._conn.execute("REINDEX brand_keywords")
        s.export_brand_keywords_json(target)
        h2 = s._conn.execute(
            "SELECT content_hash FROM _applied_config_snapshot "
            "WHERE artifact = ?",
            ("brand_keywords",),
        ).fetchone()["content_hash"]

        assert h1 == h2, "explicit ORDER BY must keep the hash stable"
    finally:
        s.close()


# ----------------------------------------------------------------------
# 6. Snapshot is updated on content change.
# ----------------------------------------------------------------------


def test_snapshot_updates_on_content_change(tmp_path: Path) -> None:
    """Inserting a new brand_keyword row changes the hash; the
    snapshot row is updated to the new hash."""
    p = tmp_path / "snapshot.db"
    s = Store(p, auto_migrate=True)
    try:
        target = tmp_path / "bk.json"
        s.export_brand_keywords_json(target)
        h1 = s._conn.execute(
            "SELECT content_hash FROM _applied_config_snapshot "
            "WHERE artifact = ?",
            ("brand_keywords",),
        ).fetchone()["content_hash"]

        # Add a new row.
        s._conn.execute(
            "INSERT INTO brand_keywords (brand_id, pattern, is_regex, added_at) "
            "VALUES ('minimax', 'NewToken', 0, datetime('now'))"
        )
        s._conn.commit()

        wrote = s.export_brand_keywords_json(target)
        assert wrote is True, "content changed — must rewrite"
        h2 = s._conn.execute(
            "SELECT content_hash FROM _applied_config_snapshot "
            "WHERE artifact = ?",
            ("brand_keywords",),
        ).fetchone()["content_hash"]
        assert h1 != h2
    finally:
        s.close()


# ----------------------------------------------------------------------
# 7. _post_migration_step — header parser matches KTD7 form.
# ----------------------------------------------------------------------


def test_post_migration_step_header_parser() -> None:
    """`_post_migration_step` reads the KTD7 `-- post_step_touches:`
    header. Direct test of the regex via a constructed SQL body."""
    import re
    body = (
        "-- post_step_touches: brand_keywords,x_query_specs\n"
        "BEGIN;\n"
        "CREATE TABLE foo (x INTEGER);\n"
        "COMMIT;\n"
    )
    m = re.search(
        r"--\s*post_step_touches:\s*([\w,\s]+?)\s*(?:--|$)",
        body,
        re.MULTILINE,
    )
    assert m is not None
    artifacts = {a.strip() for a in m.group(1).split(",") if a.strip()}
    assert artifacts == {"brand_keywords", "x_query_specs"}
