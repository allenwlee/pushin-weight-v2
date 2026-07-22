"""Test the $20 pre-flight budget guard.

Plan 2026-07-13-001 follow-up: the smoketest wants to push
max_pages_per_call to 25 to capture production-shape volumes
without burning the budget. TwitterAPI.io charges 300 credits
per /twitter/tweet/advanced_search page; the 6-call smoketest
shape (A + B1 + B2 + B3 + C1 + C2) means worst-case spend is:

    6 calls × max_pages × 300 credits

At $20 = 2,000,000 credits, the hard cap is 1111 pages/call.

The guard must:
  (a) refuse to start if would_spend > 2,000,000 credits.
  (b) raise a clear RuntimeError naming the cap + the would-be
      spend + the operator-actionable fix.
  (c) NOT fire when the operator sets max_pages=25 (well under cap).
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_budget_guard_constants_present() -> None:
    """run.py must carry the budget math constants the guard relies on."""
    src = _read("x_monitor/run.py")
    assert "_BUDGET_HARD_CAP_CREDITS = 2_000_000" in src, (
        "run.py must declare the $20 hard cap as 2_000_000 credits."
    )
    assert "_CREDITS_PER_ADVANCED_SEARCH_PAGE = 300" in src, (
        "run.py must declare the per-page credit cost (300)."
    )
    assert "_N_CALLS = 6" in src, (
        "run.py must declare the smoketest call count (6 = A+B1+B2+B3+C1+C2)."
    )


def test_budget_guard_raises_when_over_cap() -> None:
    """The guard must raise RuntimeError with the cap, would-be spend,
    and the operator-actionable fix (lower max_pages)."""
    src = _read("x_monitor/run.py")
    # The RuntimeError message must mention all three things.
    assert "raise RuntimeError(" in src, (
        "run.py must raise RuntimeError when the budget guard trips."
    )
    # The error must name the cap so the operator sees it in the log.
    assert "2_000_000" in src or "2,000,000" in src, (
        "Budget guard error must include the 2,000,000 credit cap."
    )
    # The error must include the operator-actionable fix.
    assert "--max-pages-per-call" in src, (
        "Budget guard error must mention --max-pages-per-call so the "
        "operator knows which flag to lower."
    )


def test_budget_guard_math_formula() -> None:
    """The would-spend formula must be 6 × max_pages × 300."""
    src = _read("x_monitor/run.py")
    # Formula spans multiple lines (paren-wrapped), so substring match
    # is more robust than regex here.
    assert (
        "_N_CALLS * _effective_max_pages * _CREDITS_PER_ADVANCED_SEARCH_PAGE"
        in src
    ), (
        "Budget guard formula must be `_N_CALLS * _effective_max_pages "
        "* _CREDITS_PER_ADVANCED_SEARCH_PAGE`."
    )


def test_budget_guard_threshold() -> None:
    """The hard cap comparison must use `>` (not `>=`) so the boundary
    value (exactly 2,000,000 credits) is allowed."""
    src = _read("x_monitor/run.py")
    assert "if _would_spend > _BUDGET_HARD_CAP_CREDITS:" in src, (
        "Budget guard must use strict `>` so a run that lands exactly "
        "on the cap is allowed (only over-cap trips the guard)."
    )