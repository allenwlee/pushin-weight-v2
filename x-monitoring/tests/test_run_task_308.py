"""Regression test for task #308.

Background: `run.py:_update_accounts` used to pass the kwarg
`multiple_posts_in_thread_with_official=thread_count` to
`Store.upsert_account`, but the store method never accepted that
argument. The mismatch surfaced as a TypeError at the end of every
live run (after U1's closed-DB fix unblocked the path).

Fix chosen: drop the kwarg from the call site. The `thread_count`
local is kept computed for now (so the work isn't lost) but a
`del thread_count` marker documents that nothing currently
persists it. If a future feature needs the metric, a column-add
migration is the right next step — but for now the metric is
not load-bearing.

This test pins the fix so a future regression that re-adds the
kwarg (intentionally or otherwise) fails CI before it can break
the run tail again.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_PY = REPO_ROOT / "x_monitor" / "run.py"


def _read_run_py() -> str:
    return RUN_PY.read_text(encoding="utf-8")


def test_run_py_does_not_pass_multiple_posts_in_thread_with_official() -> None:
    """The call site at _update_accounts must not pass the kwarg
    that Store.upsert_account does not accept.

    The pattern matches the kwarg only as it would appear as a
    real Python keyword argument: `multiple_posts_in_thread_with_official=`
    (followed by `=`). This avoids false positives on comments
    or docstrings that mention the kwarg by name.
    """
    src = _read_run_py()
    pattern = r"\bmultiple_posts_in_thread_with_official\s*="
    assert not re.search(pattern, src), (
        "x_monitor/run.py must NOT pass "
        "`multiple_posts_in_thread_with_official=` as a kwarg to "
        "`Store.upsert_account`. The store method doesn't accept "
        "that kwarg (task #308). If the metric is needed again, "
        "either extend the store signature + add a column, or "
        "log the value to the run-summary JSON — but do NOT "
        "re-add the unknown kwarg here."
    )


def test_run_py_task_308_marker_present() -> None:
    """The fix comment that documents task #308 must stay so the
    decision isn't lost when someone reads this code in six months."""
    src = _read_run_py()
    assert "task #308" in src, (
        "x_monitor/run.py must carry the task #308 marker comment "
        "near the thread_count computation. The marker documents "
        "WHY the metric is computed-but-not-persisted."
    )