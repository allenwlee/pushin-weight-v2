"""Regression test for the MIN_FAVES_FOR_LIST_CALL constant.

Plan 2026-07-13-001 follow-up: Call A (the curated-handles list call)
historically used `min_faves: 1` (the "release-like" preset) to filter
out low-engagement posts. The user lowered this to 0 so the list call
surfaces every post from the curated handles, not just ones that
already have traction.

The constant MIN_FAVES_FOR_LIST_CALL in x_monitor/run.py is the
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


def test_planned_call_to_query_uses_constant_for_account_calls() -> None:
    """_planned_call_to_query must read the constant for `account`
    calls, not hardcode 1."""
    src = _read("x_monitor/run.py")
    # The branch must reference MIN_FAVES_FOR_LIST_CALL.
    pattern = (
        r'call\.call_kind\s*==\s*"account"\s*:\s*\n\s*'
        r'qid,\s*min_faves\s*=\s*"Q1",\s*MIN_FAVES_FOR_LIST_CALL'
    )
    assert re.search(pattern, src), (
        "_planned_call_to_query must use MIN_FAVES_FOR_LIST_CALL "
        "(not a hardcoded 1) for `account` calls."
    )


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