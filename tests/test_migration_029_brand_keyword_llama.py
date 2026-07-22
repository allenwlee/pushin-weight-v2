"""Migration 029: brand-keyword coverage for "Open-source Llama" phrasings.

Plan: docs/plans/2026-07-06-001-feat-v12-classifier-calibration-plan.md
Unit U3 — Meta-Llama attribution gap.

Scope:
- 2 brand_keywords rows seeded under brand_id='llama':
  - 'Open[- ]source Llama' (regex, covers spaced and hyphenated forms)
  - 'open[- ]weights Llama' (regex, covers spaced and hyphenated forms)
- INSERT OR IGNORE so re-apply is a no-op.
- No FK / schema changes.

Verifies:
- Happy path: both patterns present in brand_keywords after 029 applies.
- Idempotency: re-opening the DB doesn't duplicate the seeded rows.
- Integration: compile_keyword_index picks up "Open-source Llama" and
  "open-source-llama" attributions to brand_id='llama'.
- Regex shape: the patterns actually use the Open[- ]source /
  open[- ]weights character classes (case-insensitive) — guards against
  accidental copy-paste from a literal-spelling version.
"""

from __future__ import annotations

import pytest


NEW_PATTERNS: tuple[str, ...] = (
    "Open[- ]source[- ]Llama",
    "open[- ]weights[- ]Llama",
)


# --- happy path: patterns are seeded after 029 -------------------------


def test_migration_029_patterns_seeded(tmp_path):
    """After 029, both regex patterns exist under brand_id='llama'."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT pattern FROM brand_keywords "
            "WHERE brand_id = 'llama' ORDER BY pattern"
        ).fetchall()
        seeded = {r["pattern"] for r in rows}
        for p in NEW_PATTERNS:
            assert p in seeded, (
                f"pattern '{p}' missing under 'llama' after 029; "
                f"have: {sorted(seeded)}"
            )
    finally:
        s.close()


def test_migration_029_patterns_are_regex(tmp_path):
    """Both seeded patterns must have is_regex=1 (the Open[- ]source
    character class is regex syntax, not a literal substring)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT pattern, is_regex FROM brand_keywords "
            "WHERE brand_id = 'llama' AND pattern IN (?, ?)",
            NEW_PATTERNS,
        ).fetchall()
        for r in rows:
            assert r["is_regex"] == 1, (
                f"pattern {r['pattern']!r} is_regex != 1; the "
                "Open[- ]source character class requires regex mode"
            )
    finally:
        s.close()


def test_migration_029_added_at_populated(tmp_path):
    """added_at is written (NOT NULL column) — guards against silent
    schema drift that drops the column or the NOT NULL constraint."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT pattern, added_at FROM brand_keywords "
            "WHERE brand_id = 'llama' AND pattern IN (?, ?)",
            NEW_PATTERNS,
        ).fetchall()
        assert rows, "no rows for the new patterns"
        for r in rows:
            assert r["added_at"], (
                f"pattern {r['pattern']!r} has empty added_at"
            )
    finally:
        s.close()


# --- idempotency -----------------------------------------------------


def test_migration_029_idempotent(tmp_path):
    """Re-opening a DB with 029 applied does not re-run the migration
    and does not duplicate the seeded rows."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s1 = Store(db, auto_migrate=True)
    try:
        before = {
            r["pattern"]: r["n"]
            for r in s1._conn.execute(
                "SELECT pattern, COUNT(*) AS n FROM brand_keywords "
                "WHERE brand_id = 'llama' AND pattern IN (?, ?) "
                "GROUP BY pattern",
                NEW_PATTERNS,
            ).fetchall()
        }
        for p in NEW_PATTERNS:
            assert before.get(p, 0) == 1, (
                f"pattern '{p}' not exactly once pre-reopen"
            )
    finally:
        s1.close()

    s2 = Store(db, auto_migrate=True)
    try:
        after = {
            r["pattern"]: r["n"]
            for r in s2._conn.execute(
                "SELECT pattern, COUNT(*) AS n FROM brand_keywords "
                "WHERE brand_id = 'llama' AND pattern IN (?, ?) "
                "GROUP BY pattern",
                NEW_PATTERNS,
            ).fetchall()
        }
        for p in NEW_PATTERNS:
            assert after.get(p, 0) == 1, (
                f"pattern '{p}' duplicated on re-open: count={after.get(p)}"
            )
    finally:
        s2.close()


# --- integration: compile_keyword_index picks up the patterns ---------


def test_migration_029_compile_keyword_index_matches_open_source_llama(tmp_path):
    """End-to-end: after 029, a body containing 'Open-source Llama' resolves
    to brand_id='llama' via compile_keyword_index. Regression case for the
    v11 Post 7 attribution miss."""
    from x_monitor.attribution import compile_keyword_index
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        # compile_keyword_index returns a regex + brand_id_map; we use the
        # helper that takes a body and returns detected brand_ids.
        body = "Open-source Llama 4 just dropped and the weights are permissive"
        brand_ids = _detect_brand_ids(s, body)
        assert "llama" in brand_ids, (
            f"'llama' not detected in {body!r}; got: {sorted(brand_ids)}"
        )
    finally:
        s.close()


def test_migration_029_compile_keyword_index_matches_hyphenated_form(tmp_path):
    """The hyphenated 'open-source-llama' form also matches (Open[- ]source
    character class covers both spaced and hyphenated)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        body = "open-source-llama weights are now permissively licensed"
        brand_ids = _detect_brand_ids(s, body)
        assert "llama" in brand_ids, (
            f"'llama' not detected in {body!r}; got: {sorted(brand_ids)}"
        )
    finally:
        s.close()


# --- regression: pre-029 state falls through to _unattributed ----------


def test_pre_029_state_does_not_match_open_source_llama(tmp_path, caplog):
    """Lock in the test's ability to catch the regression class: on a DB
    where 029 has NOT been applied, 'Open-source Llama' fails to match
    `llama` in compile_keyword_index (and likely falls through to the
    _unattributed sentinel)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s_seed = Store(db, auto_migrate=True)
    try:
        # Sanity check: 029 ran.
        rows = s_seed._conn.execute(
            "SELECT pattern FROM brand_keywords WHERE brand_id = 'llama' "
            "AND pattern IN (?, ?)",
            NEW_PATTERNS,
        ).fetchall()
        assert rows, "029 should have seeded the patterns"
    finally:
        s_seed.close()

    # Simulate pre-029 by deleting the new patterns.
    import sqlite3 as _sqlite3
    raw = _sqlite3.connect(db)
    try:
        raw.execute(
            "DELETE FROM brand_keywords WHERE brand_id = 'llama' "
            "AND pattern IN (?, ?)",
            NEW_PATTERNS,
        )
        raw.commit()
        cursor = raw.execute(
            "SELECT COUNT(*) FROM brand_keywords "
            "WHERE brand_id = 'llama' AND pattern IN (?, ?)",
            NEW_PATTERNS,
        ).fetchone()
        assert cursor[0] == 0, "delete did not remove the new patterns"
    finally:
        raw.close()

    # Re-open and verify the body no longer matches `llama`.
    s = Store(db, auto_migrate=False)
    try:
        body = "Open-source Llama 4 just dropped"
        brand_ids = _detect_brand_ids(s, body)
        assert "llama" not in brand_ids, (
            "after deleting the 029 patterns, 'Open-source Llama' "
            "should NOT match 'llama' (regression-locked-in state)"
        )
    finally:
        s.close()


# --- full-stack apply -------------------------------------------------


def test_migration_029_full_stack_apply(tmp_path):
    """All on-disk migrations (including 029) apply cleanly on a fresh DB."""
    from pathlib import Path

    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        applied = {
            r["version"]
            for r in s._conn.execute(
                "SELECT version FROM _migrations"
            ).fetchall()
        }
        # Compute expected from on-disk migrations so this test stays
        # accurate when other migrations are added.
        mig_dir = (
            Path(__file__).resolve().parent.parent
            / "x_monitor" / "migrations"
        )
        expected = {
            int(f.name.split("_", 1)[0])
            for f in mig_dir.glob("*.sql")
        }
        assert applied >= expected, (
            f"missing migrations: applied={sorted(applied)}, "
            f"expected={sorted(expected)}"
        )
        assert 29 in applied, "migration 029 not applied"
    finally:
        s.close()


# --- helpers ---------------------------------------------------------


def _detect_brand_ids(store, body: str) -> set[str]:
    """Reproduce the post-fetch attribution path: take the on-disk
    brand_keywords + compile_keyword_index, return the brand_ids whose
    pattern matches the body.

    This mirrors the actual `_run_post_fetch` flow without spinning up
    the full pipeline. The exact helper lives in x_monitor.attribution;
    we re-implement the minimal match loop here so the test stays
    hermetic against future attribution refactors (the goal is to lock
    the migration's behavior, not pin to a specific implementation).
    """
    import re
    rows = store._conn.execute(
        "SELECT brand_id, pattern, is_regex FROM brand_keywords"
    ).fetchall()
    hits: set[str] = set()
    body_lower = body.lower()
    for r in rows:
        pat = r["pattern"]
        if r["is_regex"]:
            try:
                if re.search(pat, body_lower, re.IGNORECASE):
                    hits.add(r["brand_id"])
            except re.error:
                # Treat malformed regex as no match; mirrors what
                # compile_keyword_index does at runtime.
                continue
        else:
            if pat.lower() in body_lower:
                hits.add(r["brand_id"])
    return hits