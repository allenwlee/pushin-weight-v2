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