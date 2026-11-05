"""Regression test for the MIN_FAVES_FOR_LIST_CALL constant.

Plan 2026-07-13-001 follow-up: Call A (the curated-handles list call)
historically used `min_faves: 1` (the "release-like" preset) to filter
out low-engagement posts. The user lowered this to 0 so the list call
surfaces every post from the curated handles, not just ones that
already have traction.

The constant MIN_FAVES_FOR_LIST_CALL in x_monitor/query_plan.py is the
single source of truth. This test pins both:
  (a) the constant must exist and equal 0;
  (b) `_planned_call_to_query` must consult it for `account` calls
      (so a future caller can't reintroduce a hardcoded 1).

If this test fails, Call A's min_faves floor regressed.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_min_faves_constant_exists_and_is_zero() -> None:
    """The MIN_FAVES_FOR_LIST_CALL constant must exist in query_plan.py
    and be set to 0. It's declared there (not in run.py) to avoid the
    circular import — query_plan is imported by run.py."""
    src = _read("x_monitor/query_plan.py")
    assert "MIN_FAVES_FOR_LIST_CALL: int = 0" in src, (
        "x_monitor/query_plan.py must declare "
        "`MIN_FAVES_FOR_LIST_CALL: int = 0`. If the constant moved, "
        "update this test."
    )


def test_run_py_imports_constant_from_query_plan() -> None:
    """run.py must import the constant from query_plan (not redeclare
    it locally) so there's a single source of truth."""
    src = _read("x_monitor/run.py")
    assert "from .query_plan import MIN_FAVES_FOR_LIST_CALL" in src, (
        "x_monitor/run.py must import MIN_FAVES_FOR_LIST_CALL from "
        ".query_plan (single source of truth). If the import path "
        "changed, update this test."
    )


def test_build_query_uses_constant_for_call_a() -> None:
    """query_plan._build_query must read the constant for the
    Call A path, not hardcode 1."""
    src = _read("x_monitor/query_plan.py")
    pattern = r"min_faves:\{MIN_FAVES_FOR_LIST_CALL\}"
    assert re.search(pattern, src), (
        "_build_query's Call A branch must use `min_faves:"
        "{MIN_FAVES_FOR_LIST_CALL}` (not a hardcoded 1)."
    )


def test_planned_call_to_query_uses_constant_for_account_calls(monkeypatch) -> None:
    """Exercise the current converter; its old Q1 assignment is retired."""
    from x_monitor import run
    from x_monitor.query_plan import PlannedCall

    # A distinct value proves the account path reads the constant rather
    # than merely returning the same currently configured zero by accident.
    monkeypatch.setattr(run, "MIN_FAVES_FOR_LIST_CALL", 7)
    for call_id, kind, expected in [("A", "account", 7), ("B1", "brand_wide", 0)]:
        call = PlannedCall(call_id=call_id, call_kind=kind, brand_id="*", bucket=None,
                           query_string="fixture", query_length=7)
        query = run._planned_call_to_query(call)
        assert query.id == call_id
        assert query.min_faves == expected
        assert query.query_string == "fixture"


def test_no_hardcoded_min_faves_equals_one_for_account() -> None:
    """No surviving hardcoded `min_faves = 1` literal in the runtime
    code paths of run.py or query_plan.py (the pre-fix value for Call A).
    Docstring examples are excluded — they document the historical
    shape, not current behavior."""
    import re as _re

    def _strip_docstrings(src: str) -> str:
        """Remove triple-quoted strings (module + class/function
        docstrings) so docstring examples don't trip the literal
        check."""
        # Strip """...""" blocks (greedy across lines).
        return _re.sub(r'"""[\s\S]*?"""', "", src)

    for path in ("x_monitor/run.py", "x_monitor/query_plan.py"):
        src = _strip_docstrings(_read(path))
        pattern = r"\bmin_faves\s*=\s*1\b"
        matches = list(_re.finditer(pattern, src))
        assert not matches, (
            f"{path} still has {len(matches)} hardcoded runtime "
            f"`min_faves = 1` literal(s). Use MIN_FAVES_FOR_LIST_CALL "
            f"instead (or set the constant to the desired floor)."
        )