"""Shared accessors for legacy and analytical trend coverage packets."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def selected_coverage(facts: Mapping[str, Any] | None) -> Mapping[str, Any]:
    """Return selected-window coverage from either supported packet shape."""
    coverage = (facts or {}).get("coverage")
    if not isinstance(coverage, Mapping):
        return {}
    selected = coverage.get("selected")
    return selected if isinstance(selected, Mapping) else coverage


def selected_coverage_state(facts: Mapping[str, Any] | None) -> str:
    return str(selected_coverage(facts).get("state") or "")
