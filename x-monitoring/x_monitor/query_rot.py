# {{AGENT_ATTRIBUTION}}
"""Query-rot detection: flip a query's enabled flag after N consecutive 0-result days."""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

import yaml

log = logging.getLogger(__name__)


def read_run_zero_result_streaks(
    runs_dir: Path,
    lookback_days: int = 7,
) -> dict[tuple[str, str], int]:
    """Walk data/runs/*.json and return (brand_id, query_id) -> consecutive
    zero-result streak ending at the most recent run.

    We process runs in mtime-DESCENDING order, and for each (brand_id,
    query_id), we count the streak until we see a run with non-zero results
    (streak breaks) or until we run out of recent runs.
    """
    streaks: dict[tuple[str, str], int] = {}
    if not runs_dir.exists():
        return streaks
    # Sort by mtime descending — newest first
    candidates: list[Path] = []
    for p in runs_dir.glob("*.json"):
        if p.name.startswith("LATEST"):
            continue
        candidates.append(p)
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    cutoff = date.today() - timedelta(days=lookback_days)
    finished: set[tuple[str, str]] = set()  # streak fully resolved
    for p in candidates:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        started = data.get("started_at", "")[:10]
        if not started:
            continue
        try:
            run_date = date.fromisoformat(started)
        except ValueError:
            continue
        if run_date < cutoff:
            continue
        for q in data.get("queries") or []:
            key = (q.get("brand_id", ""), q.get("query_id", ""))
            if key in finished:
                continue
            if q.get("status") not in ("completed", "skipped_budget"):
                continue
            if q.get("n_results", 0) == 0:
                streaks[key] = streaks.get(key, 0) + 1
            else:
                # Streak broken — mark finished so we don't keep counting
                streaks[key] = 0
                finished.add(key)
    return streaks


def threshold_for(brand_id: str, per_model: dict[str, int], default: int) -> int:
    return per_model.get(brand_id, default)


def detect_rot(
    queries_root: Path,
    runs_dir: Path,
    default_threshold: int,
    per_model: dict[str, int],
) -> list[tuple[str, str, int]]:
    """Return list of (brand_id, query_id, streak) for queries that should
    be flipped to enabled=false."""
    streaks = read_run_zero_result_streaks(runs_dir)
    flipped: list[tuple[str, str, int]] = []
    for (brand_id, query_id), streak in streaks.items():
        if streak >= threshold_for(brand_id, per_model, default_threshold):
            flipped.append((brand_id, query_id, streak))
    return flipped


def apply_rot(
    queries_root: Path,
    flips: Iterable[tuple[str, str, int]],
) -> int:
    """Update data/queries/<brand_id>.yaml to set enabled=false on flipped
    queries. Returns the number of files updated."""
    files_touched: set[Path] = set()
    for brand_id, query_id, _ in flips:
        path = queries_root / f"{brand_id}.yaml"
        if not path.exists():
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        changed = False
        for q in data.get("queries") or []:
            if q.get("id") == query_id and q.get("enabled") is True:
                q["enabled"] = False
                changed = True
        if changed:
            path.write_text(
                yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )
            files_touched.add(path)
    return len(files_touched)
