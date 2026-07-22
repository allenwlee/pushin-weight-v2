# {{AGENT_ATTRIBUTION}}
"""Tests for scripts.seed_list_handles_to_db (plan 005 U3).

The seed script's job is to insert the 22 list-not-in-DB handles into
the ``accounts`` table and cross-product each into ``brands_accounts``
via the company cascade (10 original + 16 from the 3c Summary table,
4 already in the original 10 so merged total is 22; 4 list-only handles
excluded). These tests pin the four behaviors from the plan's U3 test
scenarios:

    1. Happy path: 3 handles -> 3 accounts rows + correct brands_accounts
       cross-product (sum of company-owned brand counts).
    2. Idempotency: run twice, total row counts unchanged on second run.
    3. Missing brand_company: a handle whose company has no
       brands_companies rows produces zero brands_accounts rows AND a
       warning (not an exception).
    4. author_id lookup fallback: when the API path fails, the script
       inserts with ``author_id = handle`` (placeholder), not raising.

Each test seeds a fresh SQLite DB via Store, populates the minimum
table set, runs ``seed_one`` or ``seed_all`` with ``--no-api`` so CI
stays hermetic, and asserts against row counts and content.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.seed_list_handles_to_db import (
    DEFAULT_SEED,
    ROLE_KEY_TO_ID,
    SeedTriple,
    _company_brand_ids,
    _load_seed,
    seed_all,
    seed_one,
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


def _seed_minimal_company_graph(db_path: Path) -> None:
    """Insert 3 brands + 2 companies + 3 brands_companies rows.

    Companies and brands use `_test_` prefixed nicknames so they don't
    collide with the production schema's real companies (the migration
    seeds real companies that already have their own brands_companies
    rows — see migration 030/032). Using prefixed names keeps the test
    hermetic against the live schema.

    Graph:
      company=_test_bytedance   owns brands _test_doubao + _test_seed
      company=_test_alibaba     owns brand _test_qwen
    """
    store = Store(db_path, auto_migrate=False)
    try:
        # Companies
        store._conn.execute(
            "INSERT OR IGNORE INTO companies "
            "(nickname, display_name) VALUES ('_test_bytedance', 'Test ByteDance')"
        )
        store._conn.execute(
            "INSERT OR IGNORE INTO companies "
            "(nickname, display_name) VALUES ('_test_alibaba', 'Test Alibaba')"
        )
        # Brands
        store._conn.execute(
            "INSERT OR IGNORE INTO brands "
            "(nickname, display_name) VALUES ('_test_doubao', 'Test Doubao')"
        )
        store._conn.execute(
            "INSERT OR IGNORE INTO brands "
            "(nickname, display_name) VALUES ('_test_seed', 'Test Seed')"
        )
        store._conn.execute(
            "INSERT OR IGNORE INTO brands "
            "(nickname, display_name) VALUES ('_test_qwen', 'Test Qwen')"
        )
        # Look up ids
        bytedance_id = store._conn.execute(
            "SELECT id FROM companies WHERE nickname='_test_bytedance'"
        ).fetchone()["id"]
        alibaba_id = store._conn.execute(
            "SELECT id FROM companies WHERE nickname='_test_alibaba'"
        ).fetchone()["id"]
        doubao_id = store._conn.execute(
            "SELECT id FROM brands WHERE nickname='_test_doubao'"
        ).fetchone()["id"]
        seed_id = store._conn.execute(
            "SELECT id FROM brands WHERE nickname='_test_seed'"
        ).fetchone()["id"]
        qwen_id = store._conn.execute(
            "SELECT id FROM brands WHERE nickname='_test_qwen'"
        ).fetchone()["id"]
        # brands_companies
        store._conn.execute(
            "INSERT OR IGNORE INTO brands_companies (brand_id, company_id) "
            "VALUES (?, ?)", (doubao_id, bytedance_id)
        )
        store._conn.execute(
            "INSERT OR IGNORE INTO brands_companies (brand_id, company_id) "
            "VALUES (?, ?)", (seed_id, bytedance_id)
        )
        store._conn.execute(
            "INSERT OR IGNORE INTO brands_companies (brand_id, company_id) "
            "VALUES (?, ?)", (qwen_id, alibaba_id)
        )
        store._conn.commit()
    finally:
        store.close()


# ----------------------------------------------------------------------
# 1. Happy path
# ----------------------------------------------------------------------


def test_happy_path_three_handles_three_accounts_and_cross_product(
    fresh_db: Path,
) -> None:
    """3 handles -> 3 accounts rows + N brands_accounts rows.

    Pick 3 handles whose companies have known brand counts:
      doubaoai    -> bytedance -> 2 brands (doubao, seed)   -> 2 rows
      hailuo_ai   -> minimax   -> 0 brands in this fixture   -> 0 rows + warn
      chujiezheng -> alibaba   -> 1 brand  (qwen)            -> 1 row
    Total: 3 accounts + 3 brands_accounts.
    """
    _seed_minimal_company_graph(fresh_db)

    triples = [
        SeedTriple(handle="doubaoai",    company="_test_bytedance", role="official"),
        SeedTriple(handle="hailuo_ai",   company="_test_orphan_co", role="official"),
        SeedTriple(handle="chujiezheng", company="_test_alibaba",   role="staff"),
    ]
    store = Store(fresh_db, auto_migrate=False)
    try:
        results = seed_all(store, triples, use_api=False)
    finally:
        store.close()

    # All 3 accounts inserted
    account_rows = [
        r for r in (
            Store(fresh_db, auto_migrate=False)
            ._conn.execute("SELECT handle FROM accounts")
            .fetchall()
        )
    ]
    handles_in_db = {r["handle"] for r in account_rows}
    assert {"doubaoai", "hailuo_ai", "chujiezheng"}.issubset(handles_in_db)

    # Brands_accounts cross-product: doubaoai -> _test_doubao + _test_seed;
    # chujiezheng -> _test_qwen. hailuo_ai has no company graph -> 0 rows
    # but a warning.
    # Filter to test-handles only — migration 032 also inserts frontier
    # vendor accounts (OpenAI/Anthropic/Google/xAI) which are unrelated
    # to this assertion.
    ba_rows = (
        Store(fresh_db, auto_migrate=False)
        ._conn.execute(
            """
            SELECT b.nickname AS brand, a.handle AS handle, r.key AS role
            FROM brands_accounts ba
            JOIN brands  b ON b.id = ba.brand_id
            JOIN accounts a ON a.id = ba.accounts_id
            JOIN roles   r ON r.id = ba.role_id
            WHERE a.handle IN ('doubaoai', 'hailuo_ai', 'chujiezheng')
            ORDER BY a.handle, b.nickname
            """
        )
        .fetchall()
    )
    tuples = {(r["handle"], r["brand"], r["role"]) for r in ba_rows}
    assert ("doubaoai", "_test_doubao", "official") in tuples
    assert ("doubaoai", "_test_seed",   "official") in tuples
    assert ("chujiezheng", "_test_qwen", "staff") in tuples
    assert len(tuples) == 3, f"expected 3 brands_accounts rows, got {tuples}"

    # hailuo_ai surfaces a warning (no brands_companies for company=minimax)
    hailuo_result = next(r for r in results if r.handle == "hailuo_ai")
    assert hailuo_result.brands_accounts_skipped, (
        "missing-company case must surface as warning, not silent"
    )


# ----------------------------------------------------------------------
# 2. Idempotency
# ----------------------------------------------------------------------


def test_idempotency_second_run_is_no_op(fresh_db: Path) -> None:
    """Re-running seed_all after a successful run produces no changes."""
    _seed_minimal_company_graph(fresh_db)

    triples = [
        SeedTriple(handle="doubaoai", company="_test_bytedance", role="official"),
        SeedTriple(handle="chujiezheng", company="_test_alibaba", role="staff"),
    ]

    # First run
    store = Store(fresh_db, auto_migrate=False)
    try:
        seed_all(store, triples, use_api=False)
    finally:
        store.close()

    s1 = Store(fresh_db, auto_migrate=False)
    try:
        accts_1 = s1._conn.execute("SELECT COUNT(*) AS n FROM accounts").fetchone()["n"]
        ba_1 = s1._conn.execute("SELECT COUNT(*) AS n FROM brands_accounts").fetchone()["n"]
    finally:
        s1.close()

    # Second run
    store = Store(fresh_db, auto_migrate=False)
    try:
        results_2 = seed_all(store, triples, use_api=False)
    finally:
        store.close()

    s2 = Store(fresh_db, auto_migrate=False)
    try:
        accts_2 = s2._conn.execute("SELECT COUNT(*) AS n FROM accounts").fetchone()["n"]
        ba_2 = s2._conn.execute("SELECT COUNT(*) AS n FROM brands_accounts").fetchone()["n"]
    finally:
        s2.close()

    assert accts_1 == accts_2, "idempotency violation: accounts count grew"
    assert ba_1 == ba_2, "idempotency violation: brands_accounts count grew"

    # Every result on the second run reports account_inserted=False and
    # brands_accounts_inserted=[] — that's the contract.
    for r in results_2:
        assert r.account_inserted is False
        assert r.brands_accounts_inserted == []


# ----------------------------------------------------------------------
# 3. Missing brand_company
# ----------------------------------------------------------------------


def test_missing_brand_company_warns_not_errors(fresh_db: Path) -> None:
    """A handle whose company has no brands_companies rows produces
    zero brands_accounts rows AND a warning — not an exception.
    """
    _seed_minimal_company_graph(fresh_db)

    triple = SeedTriple(handle="orphan_handle", company="_test_orphan_co", role="official")

    store = Store(fresh_db, auto_migrate=False)
    try:
        # Must not raise
        result = seed_one(store, triple, use_api=False)
    finally:
        store.close()

    # Account row was inserted (the upsert is company-independent)
    s = Store(fresh_db, auto_migrate=False)
    try:
        row = s._conn.execute(
            "SELECT id FROM accounts WHERE handle = 'orphan_handle'"
        ).fetchone()
    finally:
        s.close()
    assert row is not None, "account row must be inserted even with no brands_companies"

    # No brands_accounts rows for this handle
    s = Store(fresh_db, auto_migrate=False)
    try:
        n = s._conn.execute(
            """
            SELECT COUNT(*) AS n FROM brands_accounts ba
            JOIN accounts a ON a.id = ba.accounts_id
            WHERE a.handle = 'orphan_handle'
            """
        ).fetchone()["n"]
    finally:
        s.close()
    assert n == 0, f"expected 0 brands_accounts rows, got {n}"

    # Warning surfaced
    assert result.brands_accounts_skipped, (
        "missing-company case must surface as warning, not silently pass"
    )


# ----------------------------------------------------------------------
# 4. author_id lookup fallback
# ----------------------------------------------------------------------


def test_author_id_fallback_uses_lowercased_handle(fresh_db: Path) -> None:
    """When the API lookup fails (use_api=False), the script inserts
    with author_id = lowercased handle (placeholder), not raising.
    """
    _seed_minimal_company_graph(fresh_db)

    triple = SeedTriple(handle="Fallback_Test", company="_test_alibaba", role="official")

    store = Store(fresh_db, auto_migrate=False)
    try:
        result = seed_one(store, triple, use_api=False)
    finally:
        store.close()

    assert result.author_id == "fallback_test", (
        f"expected placeholder author_id 'fallback_test', got {result.author_id!r}"
    )
    assert result.author_id_source == "placeholder"

    # And the row actually landed in the DB with that author_id
    s = Store(fresh_db, auto_migrate=False)
    try:
        row = s._conn.execute(
            "SELECT author_id, handle FROM accounts WHERE handle = 'Fallback_Test'"
        ).fetchone()
    finally:
        s.close()
    assert row is not None
    assert row["author_id"] == "fallback_test"


# ----------------------------------------------------------------------
# Helper / contract tests (lower-stakes)
# ----------------------------------------------------------------------


def test_default_seed_has_twenty_two_triples() -> None:
    """DEFAULT_SEED merges the original plan 005 U3 10 triples with the
    16 operator-disposed triples from the 3c Summary table (2026-07-09
    reconciliation). 4 of those 16 were already in the original 10, so
    the merged count is 22. List-only handles (Meituan_LongCat,
    robbyant_brain, ZhihuFrontier, ShunyuYao12) are excluded — they
    stay on the x.com list but never get a brands_accounts row.
    """
    assert len(DEFAULT_SEED) == 22, (
        f"DEFAULT_SEED should have 22 entries after the 2026-07-09 "
        f"3c merge; got {len(DEFAULT_SEED)}"
    )


def test_role_key_to_id_covers_all_default_roles() -> None:
    """Every role used in DEFAULT_SEED must have a known role_id mapping."""
    used = {t["role"] for t in DEFAULT_SEED}
    assert used.issubset(ROLE_KEY_TO_ID), (
        f"unmapped roles in DEFAULT_SEED: {used - set(ROLE_KEY_TO_ID)}"
    )


def test_load_seed_with_no_path_returns_defaults() -> None:
    """No --input -> default 22 triples (post-3c merge)."""
    triples = _load_seed(None)
    assert len(triples) == 22
    assert all(isinstance(t, SeedTriple) for t in triples)


def test_load_seed_with_yaml_file(tmp_path: Path) -> None:
    """--input <yaml> -> parses the file."""
    p = tmp_path / "my_handles.yaml"
    p.write_text(
        "- handle: foo\n  company: bar_co\n  role: official\n"
        "- handle: baz\n  company: qux_co\n  role: staff\n",
        encoding="utf-8",
    )
    triples = _load_seed(p)
    assert len(triples) == 2
    assert triples[0] == SeedTriple("foo", "bar_co", "official")
    assert triples[1] == SeedTriple("baz", "qux_co", "staff")


def test_company_brand_ids_returns_empty_for_unknown_company(fresh_db: Path) -> None:
    """A company nickname not in the companies table yields [] (no rows)."""
    _seed_minimal_company_graph(fresh_db)
    store = Store(fresh_db, auto_migrate=False)
    try:
        ids = _company_brand_ids(store, "_test_no_such_company")
    finally:
        store.close()
    assert ids == []