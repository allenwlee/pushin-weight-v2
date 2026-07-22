"""Test the --max-pages-per-call CLI flag plumbing.

Plan 2026-07-13-001 follow-up: the smoketest driver wants to push
the pagination safety cap higher (e.g., 25 pages/call) to capture
production-shape volumes under a $20 budget. Today cfg.search.max_pages
defaults to 5 — too small for the budget-bounded run profile.

The flag threads through `cmd_run` → `RunPipeline.execute(...,
max_pages_per_call=N)` → the fetch call site at run.py:~1080 where
it overrides `cfg.search.max_pages`.

Two regressions to pin:
  (a) The CLI flag must exist with `default=None` so production
      behavior is unchanged when the flag is omitted.
  (b) When the operator sets --max-pages-per-call N, N must flow
      all the way to the apify.run_search() max_pages= kwarg.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_cli_flag_exists_with_default_none() -> None:
    """`--max-pages-per-call` must be wired on the `run` subparser
    with `default=None` so production runs are unaffected."""
    src = _read("x_monitor/__main__.py")
    # Simple substring check: the flag definition with type=int and
    # default=None must be present. (Help-text regex matching is too
    # brittle across multi-line arg blocks.)
    needle = '"--max-pages-per-call", type=int, default=None'
    assert needle in src, (
        "x_monitor/__main__.py must register --max-pages-per-call "
        "with type=int, default=None (mirrors --limit-per-call "
        "convention). If the flag moved, update this test."
    )


def test_cmd_run_forwards_max_pages_per_call_to_execute() -> None:
    """cmd_run must forward the flag value to RunPipeline.execute()."""
    src = _read("x_monitor/__main__.py")
    assert "max_pages_per_call=getattr(args, \"max_pages_per_call\", None)" in src, (
        "cmd_run must forward --max-pages-per-call via getattr() to "
        "RunPipeline.execute(max_pages_per_call=...)."
    )


def test_run_pipeline_execute_accepts_max_pages_per_call() -> None:
    """The execute() method signature must include max_pages_per_call."""
    src = _read("x_monitor/run.py")
    pattern = r"def execute\([^{]*max_pages_per_call: int \| None = None"
    assert re.search(pattern, src, re.DOTALL), (
        "RunPipeline.execute() must accept max_pages_per_call: int | None = None"
    )


def test_run_pipeline_stashes_max_pages_per_call() -> None:
    """The execute() body must stash the value on self so the
    nested fetch call site can read it."""
    src = _read("x_monitor/run.py")
    assert "self.max_pages_per_call = max_pages_per_call" in src, (
        "RunPipeline.execute() must stash max_pages_per_call on self "
        "so the fetch call site can read it."
    )


def test_fetch_call_site_uses_max_pages_per_call_override() -> None:
    """The apify.run_search() call must use max_pages_per_call when set,
    else fall back to cfg.search.max_pages."""
    src = _read("x_monitor/run.py")
    # The local var name `max_pages_cap` is the seam.
    assert "max_pages_cap = (" in src, (
        "run.py must compute a `max_pages_cap` local that prefers "
        "self.max_pages_per_call over s.max_pages."
    )
    assert "max_pages=max_pages_cap" in src, (
        "apify.run_search(...) must be called with max_pages=max_pages_cap."
    )