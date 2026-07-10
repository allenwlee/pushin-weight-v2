# {{AGENT_ATTRIBUTION}}
"""Tests for scripts.backfill_brand_keywords + parse_brand_tokens.

Plan: docs/plans/2026-07-10-001-feat-brand-keywords-backfill-plan.md

Coverage:
- parse_brand_tokens extracts the first paren group from Q2 (and
  Q3/Q5/Q6) query strings, ignoring Q1/Q4.
- Idempotency: re-running the script inserts 0 new rows.
- Missing yaml: a brand with no query yaml surfaces a warning (rc=2)
  and no rows are inserted for that brand.
- Existing rows preserved: pre-seeded entries survive a re-run.
- Round-trip: fresh DB seeded by the script has exactly the expected
  tokens per brand.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.backfill_brand_keywords import (
    _enumerate_pairs,
    _existing_pairs,
    _insert_pairs,
    _load_enabled_models,
    main as backfill_main,
)
from x_monitor.config import load_config
# Plan 2026-07-11-001 retires `x_monitor.query_plan.parse_brand_tokens`.
# The backfill script and its tests now use the inlined parser from
# the U1 authoring tool (`migrations/_authoring/seed_residual_keywords`)
# which owns its own copy.
from x_monitor.migrations._authoring.seed_residual_keywords import (
    _parse_brand_tokens as parse_brand_tokens,
)
from x_monitor.store import Store


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


@pytest.fixture
def fresh_db(tmp_path: Path) -> Path:
    """A fresh, migrated DB path. Tests INSERT their own seed data."""
    p = tmp_path / "x_monitoring.db"
    s = Store(p, auto_migrate=True)
    s.close()
    return p


@pytest.fixture
def queries_dir(tmp_path: Path) -> Path:
    """A temp queries dir with three test brands (real KNOWN_MODELS
    nicknames). Returns the dir path. The yaml content uses synthetic
    tokens — these tests are about the parser/script plumbing, not
    the actual brand tokens (which are owned by the live repo yaml).
    """
    qdir = tmp_path / "queries"
    qdir.mkdir()

    # Brand 'sakana_ai' (real KNOWN_MODELS): 3 tokens, quoted variant
    # present. Used as the "Brand A" stand-in throughout the tests.
    (qdir / "sakana_ai.yaml").write_text(
        "queries:\n"
        "  - id: Q1\n    query_string: 'different query'\n"
        "  - id: Q2\n    query_string: '(Alpha OR Beta OR Gamma) min_faves:0'\n"
        "  - id: Q3\n    query_string: '(X) noise'\n"
        "  - id: Q4\n    query_string: 'noise'\n"
        "  - id: Q5\n    query_string: '(Delta)'\n"
        "  - id: Q6\n    query_string: '(Epsilon)'\n",
        encoding="utf-8",
    )

    # Brand 'ernie' (real KNOWN_MODELS): multi-byte token + quoted.
    # Used as the "Brand B" stand-in.
    (qdir / "ernie.yaml").write_text(
        "queries:\n"
        "  - id: Q2\n    query_string: '(\"Sakana AI\" OR サカナAI OR 海螺)'\n",
        encoding="utf-8",
    )

    # Brand 'upstage' (real KNOWN_MODELS): missing Q2 entirely; only
    # Q1 with a paren group. Used as the "Brand C" stand-in.
    (qdir / "upstage.yaml").write_text(
        "queries:\n"
        "  - id: Q1\n    query_string: '(useless)'\n",
        encoding="utf-8",
    )

    return qdir


def _write_config(
    path: Path,
    enabled_models: list[str],
    queries_dir: Path,
) -> None:
    """Write a minimal config.yaml that the backfill script will accept.

    Uses real brand nicknames from KNOWN_MODELS because Config
    validates enabled_models against the registry. `daily_ceiling`
    and other required fields get their defaults baked in.
    """
    path.write_text(
        "enabled_models:\n"
        + "\n".join(f"  - {m}" for m in enabled_models)
        + "\n"
        + "daily_ceiling: 333\n"
        + "x_monitor_list_id: 2067062923525275922\n",
        encoding="utf-8",
    )


def _seed_brand_rows(db_path: Path, brand_nicknames: list[str]) -> None:
    """Insert the brand_nicknames into the brands table so the FK on
    brand_keywords.brand_id is satisfied. Tests that call the backfill
    script must run this first; without it, the FK raises and the
    test misattributes the failure to the script.
    """
    s = Store(db_path, auto_migrate=False)
    try:
        for nick in brand_nicknames:
            s._conn.execute(
                "INSERT OR IGNORE INTO brands (nickname, display_name) "
                "VALUES (?, ?)",
                (nick, nick),
            )
        s._conn.commit()
    finally:
        s.close()


# ----------------------------------------------------------------------
# 1. parse_brand_tokens extracts Q2/Q3/Q5/Q6 paren groups only
# ----------------------------------------------------------------------


def test_parse_brand_tokens_extracts_first_paren_group_only(
    queries_dir: Path,
) -> None:
    """Only Q2/Q3/Q5/Q6 contribute; Q1/Q4 paren groups are ignored.
    Multi-byte + quoted tokens survive verbatim.
    """
    out = parse_brand_tokens(
        ["sakana_ai", "ernie", "upstage", "no_yaml_brand"],
        queries_dir,
    )

    # sakana_ai (Brand A): tokens from Q2 (Alpha, Beta, Gamma), Q3 (X),
    # Q5 (Delta), Q6 (Epsilon). Q1's paren group is ignored.
    assert out["sakana_ai"] == ["Alpha", "Beta", "Gamma", "X", "Delta", "Epsilon"]

    # ernie (Brand B): 3 tokens including multi-byte (サカナAI, 海螺)
    # and a quoted token ("Sakana AI"). Quotes preserved verbatim —
    # the downstream OR-join handles them.
    assert out["ernie"] == ['"Sakana AI"', "サカナAI", "海螺"]

    # upstage (Brand C): no Q2/Q3/Q5/Q6; falls back to [] (the brand
    # contributes 0 paren groups to Call B).
    assert out["upstage"] == []

    # no_yaml_brand: missing yaml; falls back to [].
    assert out["no_yaml_brand"] == []


# ----------------------------------------------------------------------
# 2. Idempotency
# ----------------------------------------------------------------------


def test_backfill_is_idempotent(
    fresh_db: Path, queries_dir: Path, tmp_path: Path
) -> None:
    """Re-running inserts 0 new rows; total count unchanged."""
    cfg_path = tmp_path / "config.yaml"
    _write_config(cfg_path, ["sakana_ai", "ernie"], queries_dir)
    _seed_brand_rows(fresh_db, ["sakana_ai", "ernie"])

    # First run — actual write.
    rc1 = backfill_main([
        "--config", str(cfg_path),
        "--db", str(fresh_db),
        "--queries-dir", str(queries_dir),
    ])
    assert rc1 == 0

    s = Store(fresh_db, auto_migrate=False)
    try:
        n1 = s._conn.execute(
            "SELECT COUNT(*) AS n FROM brand_keywords"
        ).fetchone()["n"]
    finally:
        s.close()

    # Second run — should be a no-op.
    rc2 = backfill_main([
        "--config", str(cfg_path),
        "--db", str(fresh_db),
        "--queries-dir", str(queries_dir),
    ])
    assert rc2 == 0

    s = Store(fresh_db, auto_migrate=False)
    try:
        n2 = s._conn.execute(
            "SELECT COUNT(*) AS n FROM brand_keywords"
        ).fetchone()["n"]
    finally:
        s.close()

    assert n1 == n2, f"idempotency violation: {n1} -> {n2}"


# ----------------------------------------------------------------------
# 3. Brand with no query yaml produces a warning
# ----------------------------------------------------------------------


def test_backfill_warns_for_brand_with_no_query_yaml(
    fresh_db: Path, queries_dir: Path, tmp_path: Path, capsys
) -> None:
    """A brand whose yaml is missing or whose Q2 is empty surfaces a
    WARN line in stdout, returns rc=2, and adds no new rows for that
    brand (existing rows from migration 004 are preserved).

    Note: a fresh DB after `auto_migrate=True` has migration-004-seeded
    rows for production enabled_models brands. The test snapshots
    before/after for `upstage` (the empty-Q2 brand) and asserts the
    delta is 0 — i.e., the script did not insert any upstage rows.
    """
    cfg_path = tmp_path / "config.yaml"
    _write_config(cfg_path, ["sakana_ai", "upstage"], queries_dir)
    _seed_brand_rows(fresh_db, ["sakana_ai", "upstage"])

    s = Store(fresh_db, auto_migrate=False)
    try:
        upstage_before = s._conn.execute(
            "SELECT COUNT(*) AS n FROM brand_keywords WHERE brand_id = ?",
            ("upstage",),
        ).fetchone()["n"]
    finally:
        s.close()

    rc = backfill_main([
        "--config", str(cfg_path),
        "--db", str(fresh_db),
        "--queries-dir", str(queries_dir),
    ])
    out = capsys.readouterr().out
    assert rc == 2, (
        f"expected rc=2 (warning), got {rc}; stdout: {out!r}"
    )
    assert "upstage" in out, (
        f"warning should name the empty brand; stdout: {out!r}"
    )

    # sakana_ai: script added its Q2-paren tokens. upstage: delta = 0.
    s = Store(fresh_db, auto_migrate=False)
    try:
        n_upstage_after = s._conn.execute(
            "SELECT COUNT(*) AS n FROM brand_keywords WHERE brand_id = ?",
            ("upstage",),
        ).fetchone()["n"]
        n_a = s._conn.execute(
            "SELECT COUNT(*) AS n FROM brand_keywords WHERE brand_id = ?",
            ("sakana_ai",),
        ).fetchone()["n"]
    finally:
        s.close()
    assert n_upstage_after == upstage_before, (
        f"upstage delta should be 0; was {upstage_before}, now {n_upstage_after}"
    )
    assert n_a > 0


# ----------------------------------------------------------------------
# 4. Existing rows preserved
# ----------------------------------------------------------------------


def test_backfill_existing_rows_are_preserved(
    fresh_db: Path, queries_dir: Path, tmp_path: Path
) -> None:
    """A custom pre-seeded row survives the backfill (INSERT OR IGNORE)."""
    s = Store(fresh_db, auto_migrate=False)
    try:
        s._conn.execute(
            """
            INSERT INTO brand_keywords (brand_id, pattern, is_regex, added_at)
            VALUES ('sakana_ai', 'CustomToken', 0, datetime('now'))
            """
        )
        s._conn.commit()
    finally:
        s.close()

    cfg_path = tmp_path / "config.yaml"
    _write_config(cfg_path, ["sakana_ai"], queries_dir)
    _seed_brand_rows(fresh_db, ["sakana_ai"])

    rc = backfill_main([
        "--config", str(cfg_path),
        "--db", str(fresh_db),
        "--queries-dir", str(queries_dir),
    ])
    assert rc == 0

    s = Store(fresh_db, auto_migrate=False)
    try:
        row = s._conn.execute(
            """
            SELECT pattern FROM brand_keywords
            WHERE brand_id = 'sakana_ai' AND pattern = 'CustomToken'
            """
        ).fetchone()
    finally:
        s.close()
    assert row is not None, "CustomToken row should still exist after backfill"


# ----------------------------------------------------------------------
# 5. Hermetic round-trip: every (brand, token) pair lands exactly once
# ----------------------------------------------------------------------


def test_backfill_round_trip_inserts_expected_pairs(
    fresh_db: Path, queries_dir: Path, tmp_path: Path
) -> None:
    """After backfill, every (brand, token) pair parsed by
    parse_brand_tokens is present in the DB.

    Note: a fresh DB after `auto_migrate=True` already has rows seeded
    by migration 004 (the canonical brand-keyword seed for the production
    enabled_models list). The test asserts the script's *contribution*
    is present — not that the table is empty before the script runs.
    """
    cfg_path = tmp_path / "config.yaml"
    enabled = ["sakana_ai", "ernie"]
    _write_config(cfg_path, enabled, queries_dir)
    _seed_brand_rows(fresh_db, enabled)

    expected_pairs, empty_brands = _enumerate_pairs(enabled, queries_dir)
    assert empty_brands == [], "test fixture must not have empty brands"

    rc = backfill_main([
        "--config", str(cfg_path),
        "--db", str(fresh_db),
        "--queries-dir", str(queries_dir),
    ])
    assert rc == 0

    s = Store(fresh_db, auto_migrate=False)
    try:
        existing = _existing_pairs(s)
    finally:
        s.close()

    expected_set = set(expected_pairs)
    missing = expected_set - existing
    assert not missing, f"expected pairs not written: {missing}"


# ----------------------------------------------------------------------
# Helper / contract tests (lower-stakes)
# ----------------------------------------------------------------------


def test_load_enabled_models_reads_tmp_config(tmp_path: Path) -> None:
    """`_load_enabled_models` parses a config.yaml and returns its
    enabled_models list. Verified against a tmp config (with real
    KNOWN_MODELS nicknames) to keep the test hermetic.
    """
    cfg = tmp_path / "c.yaml"
    cfg.write_text(
        "enabled_models:\n  - ernie\n  - upstage\n"
        "daily_ceiling: 333\n"
        "x_monitor_list_id: 2067062923525275922\n",
        encoding="utf-8",
    )
    assert _load_enabled_models(cfg) == ["ernie", "upstage"]


def test_enumerate_pairs_empty_brand_for_missing_yaml(
    queries_dir: Path,
) -> None:
    """A missing yaml surfaces as an empty brand in the enumeration."""
    pairs, empty = _enumerate_pairs(
        ["sakana_ai", "missing_brand"], queries_dir,
    )
    assert "missing_brand" in empty
    # sakana_ai's tokens should still be enumerated.
    assert any(b == "sakana_ai" for b, _ in pairs)


def test_insert_pairs_inserts_then_skips(tmp_path: Path) -> None:
    """Pure helper test: first call inserts, second call all-skipped."""
    p = tmp_path / "x_monitoring.db"
    s = Store(p, auto_migrate=True)
    try:
        # brand_keywords.brand_id has a FK to brands.nickname; seed
        # the brands row so the FK accepts the inserts below.
        s._conn.execute(
            "INSERT OR IGNORE INTO brands (nickname, display_name) "
            "VALUES ('brandA', 'brandA')"
        )
        s._conn.commit()

        inserted, skipped = _insert_pairs(s, [
            ("brandA", "alpha"), ("brandA", "beta"),
        ])
        assert len(inserted) == 2
        assert len(skipped) == 0

        inserted2, skipped2 = _insert_pairs(s, [
            ("brandA", "alpha"), ("brandA", "gamma"),
        ])
        assert ("brandA", "alpha") in skipped2
        assert ("brandA", "gamma") in inserted2
    finally:
        s.close()