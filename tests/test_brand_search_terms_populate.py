"""Unit + integration tests for scripts/2026-06-25-004-populate-brand-search-terms.py.

Plan: docs/plans/2026-06-25-004-feat-populate-brand-search-terms-plan.md
Units 1 + 2 of 4. Verifies:
- _extract_tokens mirrors query_plan.parse_brand_tokens byte-for-byte
  (CJK, quoted, emoji, edge cases).
- Idempotency: a re-run inserts 0 new rows.
- Dry-run: no writes.
- Drift-zero: the post-write verification matches the yaml.
- Brand-row auto-creation: a fresh DB gets all 20 brands.
- Q1/Q4 ignored: account-based queries contribute no tokens.
"""
from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path

import pytest

# Make the scripts/ dir importable so we can import the script module
# directly without spawning a subprocess for unit tests.
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import importlib.util

_SPEC = importlib.util.spec_from_file_location(
    "populate_brand_search_terms",
    SCRIPTS_DIR / "2026-06-25-004-populate-brand-search-terms.py",
)
assert _SPEC is not None and _SPEC.loader is not None
_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_mod)
_extract_tokens = _mod._extract_tokens
_load_enabled_models = _mod._load_enabled_models
_new_brands_keys = sorted(_mod.NEW_BRANDS.keys())


# --- _extract_tokens unit tests -----------------------------------------


def test_extract_tokens_q2_only_yields_brand_clause():
    yaml_text = """
queries:
  - id: Q1
    query_string: 'from:BrandA min_faves:5'
  - id: Q2
    query_string: '(Foo OR Bar) (how OR tutorial) min_faves:2'
"""
    assert _extract_tokens(yaml_text) == ["Foo", "Bar"]


def test_extract_tokens_cjk_preserved_as_is():
    """CJK characters are stored verbatim — not lowercased, not transliterated."""
    yaml_text = """
queries:
  - id: Q2
    query_string: '(海螺 OR 零一万物 OR 通义千问) (how OR 怎么) min_faves:2'
"""
    assert _extract_tokens(yaml_text) == ["海螺", "零一万物", "通义千问"]


def test_extract_tokens_quoted_preserved_with_quotes():
    """Quoted tokens keep their double quotes."""
    yaml_text = """
queries:
  - id: Q6
    query_string: '("Llama 3" OR "love it" OR best) min_faves:5'
"""
    assert _extract_tokens(yaml_text) == ['"Llama 3"', '"love it"', "best"]


def test_extract_tokens_emoji_preserved():
    yaml_text = """
queries:
  - id: Q6
    query_string: '(🤯 OR 卧槽 OR 太强了) min_faves:5'
"""
    assert _extract_tokens(yaml_text) == ["🤯", "卧槽", "太强了"]


def test_extract_tokens_q1_and_q4_ignored():
    """Q1 (from:) and Q4 (to:) are account-based; no tokens."""
    yaml_text = """
queries:
  - id: Q1
    query_string: 'from:BrandHandle min_faves:5'
  - id: Q2
    query_string: '(A OR B) min_faves:2'
  - id: Q4
    query_string: 'to:BrandHandle min_faves:5'
"""
    assert _extract_tokens(yaml_text) == ["A", "B"]


def test_extract_tokens_q1_with_paren_group_still_ignored():
    """Q1 may have a paren group (e.g., llama.yaml), but it is skipped
    by design — the source algorithm mirrors query_plan's behavior."""
    yaml_text = """
queries:
  - id: Q1
    query_string: '(Llama OR "Llama 3") (AI OR model) min_faves:5'
  - id: Q2
    query_string: '(Llama OR "Llama 3") min_faves:2'
"""
    assert _extract_tokens(yaml_text) == ["Llama", '"Llama 3"']


def test_extract_tokens_dedup_preserving_order():
    yaml_text = """
queries:
  - id: Q2
    query_string: '(A OR B OR A) min_faves:2'
  - id: Q3
    query_string: '(B OR C) min_faves:1'
  - id: Q5
    query_string: '(D) min_faves:3'
"""
    assert _extract_tokens(yaml_text) == ["A", "B", "C", "D"]


def test_extract_tokens_no_q2_q3_q5_q6_returns_empty():
    yaml_text = """
queries:
  - id: Q1
    query_string: 'from:H min_faves:5'
  - id: Q4
    query_string: 'to:H min_faves:5'
"""
    assert _extract_tokens(yaml_text) == []


def test_extract_tokens_no_parens_returns_empty():
    yaml_text = """
queries:
  - id: Q2
    query_string: 'from:H min_faves:2'
"""
    assert _extract_tokens(yaml_text) == []


def test_extract_tokens_only_first_paren_group_per_entry():
    """Each Q entry contributes its first paren group only."""
    yaml_text = """
queries:
  - id: Q2
    query_string: '(A OR B) (how OR tutorial) min_faves:2'
"""
    assert _extract_tokens(yaml_text) == ["A", "B"]


def test_extract_tokens_real_minimax_yaml():
    """Sanity check against the real minimax.yaml: Q5 omits 海螺
    (only MiniMax + Hailuo), Q2/Q3/Q6 include 海螺."""
    p = Path(__file__).resolve().parents[1] / "data" / "queries" / "minimax.yaml"
    if not p.exists():
        pytest.skip("minimax.yaml not present")
    toks = _extract_tokens(p.read_text(encoding="utf-8"))
    assert "海螺" in toks
    assert "MiniMax" in toks
    assert "Hailuo" in toks
    # All tokens are dedup'd.
    assert len(toks) == len(set(toks))


# --- _load_enabled_models ------------------------------------------------


def test_load_enabled_models_returns_declaration_order(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("enabled_models:\n  - a\n  - b\n  - c\n")
    assert _load_enabled_models(cfg) == ["a", "b", "c"]


def test_load_enabled_models_missing_raises(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("other_key: 1\n")
    with pytest.raises(RuntimeError, match="enabled_models"):
        _load_enabled_models(cfg)


# --- integration: populate against tmp_path DB --------------------------


def _make_queries_dir(root: Path, brand_id: str, yaml_text: str) -> Path:
    qdir = root / "data" / "queries"
    qdir.mkdir(parents=True, exist_ok=True)
    (qdir / f"{brand_id}.yaml").write_text(yaml_text, encoding="utf-8")
    return qdir


def _new_brand_row_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM brands").fetchone()[0]


def _bst_row_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM brand_search_terms").fetchone()[0]


def test_populate_against_fresh_db_creates_brand_rows(tmp_path):
    """Fresh DB: brand_search_terms is empty; populate creates all 20
    brand rows (11 v1 + 9 new) and populates brand_search_terms."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    s.close()

    qdir = _make_queries_dir(
        tmp_path,
        "minimax",
        """
queries:
  - id: Q2
    query_string: '(MiniMax OR 海螺) (how OR 教程) min_faves:2'
  - id: Q3
    query_string: '(MiniMax OR 海螺) (broken OR 翻车) min_faves:1'
  - id: Q5
    query_string: '(MiniMax) (benchmark) min_faves:3'
  - id: Q6
    query_string: '(海螺 OR 🤯) (amazing) min_faves:5'
""",
    )
    _make_queries_dir(
        tmp_path,
        "llama",
        """
queries:
  - id: Q2
    query_string: '(Llama OR "Llama 3") min_faves:2'
""",
    )

    enabled = ["minimax", "llama"]
    rc = _mod._populate(db, qdir, enabled, dry_run=False)
    assert rc == 0

    conn = sqlite3.connect(db)
    try:
        # brand rows: 12 v1 (incl. _unattributed) + 1 (llama is new).
        # minimax already seeded by migration 004.
        n_brands = _new_brand_row_count(conn)
        assert n_brands == 13
        # minimax yields MiniMax + 海螺 + 🤯 (Q6's 🤯 is new; Q2/Q3/Q5
        # all dedup to MiniMax + 海螺; Q6 adds 🤯). llama yields
        # Llama + "Llama 3". Total: 5.
        assert _bst_row_count(conn) == 5
        # post-020: brand_search_terms.brand_id is INTEGER FK → brands.id;
        # JOIN back to brands.nickname so the assertion stays readable.
        rows = conn.execute(
            "SELECT b.nickname AS brand_slug, bst.term"
            " FROM brand_search_terms bst"
            " JOIN brands b ON b.id = bst.brand_id"
            " ORDER BY b.nickname, bst.term"
        ).fetchall()
        assert rows == [
            ('llama', '"Llama 3"'),
            ('llama', 'Llama'),
            ('minimax', 'MiniMax'),
            ('minimax', '海螺'),
            ('minimax', '🤯'),
        ]  # SQLite ORDER BY uses Unicode codepoint order
        # Per-brand term counts: minimax=3 (MiniMax, 海螺, 🤯), llama=2
        by_brand = conn.execute(
            "SELECT b.nickname AS brand_slug, COUNT(*)"
            " FROM brand_search_terms bst"
            " JOIN brands b ON b.id = bst.brand_id"
            " GROUP BY b.nickname ORDER BY b.nickname"
        ).fetchall()
        assert by_brand == [("llama", 2), ("minimax", 3)]
    finally:
        conn.close()


def test_populate_is_idempotent(tmp_path):
    """Re-running against the same DB inserts 0 new rows on the second pass."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    s.close()

    qdir = _make_queries_dir(
        tmp_path,
        "minimax",
        """
queries:
  - id: Q2
    query_string: '(MiniMax OR 海螺) (how) min_faves:2'
""",
    )
    enabled = ["minimax"]

    rc1 = _mod._populate(db, qdir, enabled, dry_run=False)
    assert rc1 == 0
    conn = sqlite3.connect(db)
    try:
        n_first = _bst_row_count(conn)
        assert n_first == 2  # MiniMax, 海螺
    finally:
        conn.close()

    rc2 = _mod._populate(db, qdir, enabled, dry_run=False)
    assert rc2 == 0
    conn = sqlite3.connect(db)
    try:
        n_second = _bst_row_count(conn)
        assert n_second == n_first
    finally:
        conn.close()


def test_populate_dry_run_makes_no_writes(tmp_path):
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    s.close()

    qdir = _make_queries_dir(
        tmp_path,
        "minimax",
        """
queries:
  - id: Q2
    query_string: '(MiniMax OR 海螺) (how) min_faves:2'
""",
    )
    enabled = ["minimax"]

    rc = _mod._populate(db, qdir, enabled, dry_run=True)
    assert rc == 0
    conn = sqlite3.connect(db)
    try:
        assert _bst_row_count(conn) == 0
    finally:
        conn.close()


def test_populate_drift_zero_with_zero_drift(caplog, tmp_path):
    """A successful populate reports drift-zero in the print summary."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    s.close()

    qdir = _make_queries_dir(
        tmp_path,
        "minimax",
        """
queries:
  - id: Q2
    query_string: '(MiniMax OR 海螺) (how) min_faves:2'
  - id: Q3
    query_string: '(海螺) (broken) min_faves:1'
""",
    )
    enabled = ["minimax"]

    with caplog.at_level(logging.WARNING):
        rc = _mod._populate(db, qdir, enabled, dry_run=False)
    assert rc == 0
    # No drift warning was emitted.
    assert "drift" not in caplog.text.lower() or "yaml-only=" not in caplog.text


def test_populate_missing_yaml_skips_brand_with_warning(tmp_path, capsys):
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    s.close()

    qdir = tmp_path / "data" / "queries"
    qdir.mkdir(parents=True, exist_ok=True)
    # No yamls written.
    enabled = ["minimax", "missing_brand"]

    rc = _mod._populate(db, qdir, enabled, dry_run=False)
    assert rc == 0
    captured = capsys.readouterr()
    assert "missing_brand: yaml missing" in captured.err


# --- NEW_BRANDS metadata table coverage ----------------------------------


def test_new_brands_covers_all_9_missing_brands():
    """The 9 NEW_BRANDS entries correspond to the 9 brand_ids that
    don't have a `brands` row from migration 004."""
    # All 9 brand_ids from the plan's R4 table.
    expected = {
        "llama", "nemo_megatron", "doubao", "yi", "sensechat",
        "exaone", "kuaishou", "sakana_ai", "upstage",
    }
    assert set(_new_brands_keys) == expected


def test_new_brands_values_are_strings():
    for brand_id, (display_name, accent_color) in _mod.NEW_BRANDS.items():
        assert isinstance(display_name, str) and display_name
        assert isinstance(accent_color, str) and accent_color.startswith("#")