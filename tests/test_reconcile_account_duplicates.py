"""U10 tests - reconcile_account_duplicates command helpers.

Plan: docs/plans/2026-07-30-002-feat-hybrid-funnel-then-reconcile-accounts-plan.md
Unit U10.

Tests the pure helper functions (no DB). The full live-DB command
behavior is exercised via scripts/u9_live_pin.py + manual
`manage.py reconcile_account_duplicates --dry-run --limit N`.
"""

from __future__ import annotations

from monitor.management.commands.reconcile_account_duplicates import (
    PLACEHOLDER_PREFIXES,
    _classify_group,
    _is_placeholder,
    _canonical_integer_for_handle,
    _repoint_fk,
)


def test_placeholder_prefixes_constant():
    assert PLACEHOLDER_PREFIXES == ("handle:", "synthetic:")


def test_is_placeholder():
    assert _is_placeholder("handle:DoubaoAI") is True
    assert _is_placeholder("synthetic:wsj") is True
    assert _is_placeholder("1856750484977324034") is False
    assert _is_placeholder("") is False


def test_classify_group_mixed():
    """Group with one integer + one placeholder."""
    result = _classify_group(
        "DoubaoAI",
        ["1856750484977324034", "handle:DoubaoAI", "synthetic:DoubaoAI"],
    )
    assert result["handle"] == "DoubaoAI"
    assert result["integer_ids"] == ["1856750484977324034"]
    assert set(result["placeholder_ids"]) == {"handle:DoubaoAI", "synthetic:DoubaoAI"}
    assert result["is_all_placeholder"] is False


def test_classify_group_all_integer():
    result = _classify_group("kimi", ["123", "456"])
    assert result["integer_ids"] == ["123", "456"]
    assert result["placeholder_ids"] == []
    assert result["is_all_placeholder"] is False


def test_classify_group_all_placeholder():
    """Phase 2 group: all placeholders, no integer yet."""
    result = _classify_group(
        "WSJ", ["handle:WSJ", "synthetic:WSJ"],
    )
    assert result["integer_ids"] == []
    assert set(result["placeholder_ids"]) == {"handle:WSJ", "synthetic:WSJ"}
    assert result["is_all_placeholder"] is True


def test_canonical_integer_needs_cursor():
    """The function expects a DB cursor; verify it doesn't run without one."""
    import pytest
    cursor = None  # type: ignore
    with pytest.raises(AttributeError):
        _canonical_integer_for_handle(
            cursor,  # type: ignore
            handle="DoubaoAI",
            integer_ids_in_group=["1856750484977324034"],
        )


def test_classify_group_preserves_first_seen_order():
    """_find_duplicate_groups orders by first_seen_at ASC; the
    classifier must preserve that order for the integer_ids list."""
    result = _classify_group(
        "Reuters",
        ["1652541", "handle:Reuters"],
    )
    assert result["integer_ids"] == ["1652541"]
    assert result["placeholder_ids"] == ["handle:Reuters"]


class _FakeCursor:
    """Minimal cursor that records SQL and returns canned rows.

    Drives _repoint_fk through the pre-pass DELETE for conflicting
    brands and the per-table UPDATE. The cursor's execute records
    the SQL and binds responses to subsequent fetchall/fetchone calls.
    """

    def __init__(self, responses=None):
        self.calls = []
        self._responses = list(responses or [])
        self.rowcount = 0

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        for i, (p, r) in enumerate(self._responses):
            if p in sql:
                self._responses.pop(i)
                self._next = r
                return
        self.rowcount = 0

    def fetchall(self):
        return getattr(self, "_next", [])

    def fetchone(self):
        rows = getattr(self, "_next", [])
        return rows[0] if rows else None


def test_repoint_fk_handles_brands_accounts_duplicate_key():
    """The pre-pass must DELETE placeholder rows whose canonical
    integer already has a brands_accounts row for the same brand_id,
    BEFORE the brands_accounts UPDATE fires (so the unique constraint
    `brands_accounts_pkey` does not kill the SAVEPOINT).
    """
    cur = _FakeCursor(
        responses=[
            ("SELECT DISTINCT ba.brand_id", [("minimax",), ("qwen",)]),
            ("DELETE FROM brands_accounts", None),
        ]
    )
    counts = _repoint_fk(
        cur,
        canonical="1875078099538423808",
        placeholder_ids=["handle:DoubaoAI"],
        handle="DoubaoAI",
    )
    # The pre-pass issues a SELECT first, then a DELETE.
    assert "SELECT DISTINCT ba.brand_id" in cur.calls[0][0]
    assert "DELETE FROM brands_accounts" in cur.calls[1][0]
    assert "brands_accounts_source_deleted" in counts
    # The remaining 4 calls are the per-table UPDATEs.
    update_sql = " ".join(c[0] for c in cur.calls[2:])
    assert "UPDATE posts" in update_sql
    assert "UPDATE account_post_appearances" in update_sql
    assert "UPDATE brands_accounts" in update_sql
    assert "UPDATE companies_accounts" in update_sql


def test_repoint_fk_no_conflict_short_circuits_pre_pass():
    """When no (brand_id, canonical_accounts_id) collision exists, the
    pre-pass DELETE must not run (empty conflicting_brands).
    """
    cur = _FakeCursor(
        responses=[
            ("SELECT DISTINCT ba.brand_id", []),
        ]
    )
    counts = _repoint_fk(
        cur,
        canonical="1875078099538423808",
        placeholder_ids=["handle:RareBrand"],
        handle="RareBrand",
    )
    delete_calls = [c for c in cur.calls if "DELETE FROM brands_accounts" in c[0]]
    assert delete_calls == []
    assert counts.get("brands_accounts_source_deleted", 0) == 0
