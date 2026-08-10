"""Persist CycleRunner summary JSON for cost tooling (plan 2026-08-10-003).

Lives under scripts/harvest_cost; imported thinly from monitor.cycle.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Mapping

logger = logging.getLogger(__name__)

# Default under repo data/runs — same family as v1 run summaries.
DEFAULT_RUNS_SUBDIR = Path("data/runs")


def default_runs_dir(repo_root: Path | None = None) -> Path:
    root = repo_root if repo_root is not None else Path.cwd()
    return root / DEFAULT_RUNS_SUBDIR


def attach_http_log(summary: dict[str, Any], api: Any) -> None:
    """Copy TwitterApiClient._request_log into summary['http_log'] if present."""
    try:
        log = getattr(api, "_request_log", None)
        if log is None:
            return
        summary["http_log"] = list(log)
    except Exception as exc:  # never break harvest
        logger.warning("cycle_summary_emit: attach_http_log failed: %s", exc)


def persist_cycle_summary(
    summary: Mapping[str, Any],
    *,
    runs_dir: Path | None = None,
    repo_root: Path | None = None,
) -> Path | None:
    """Write summary JSON to data/runs/<run_id>.json. Returns path or None on failure."""
    try:
        run_id = str(summary.get("run_id") or "unknown")
        # sanitize path segment
        safe_id = "".join(c if c.isalnum() or c in "-_." else "_" for c in run_id)
        base = runs_dir if runs_dir is not None else default_runs_dir(repo_root)
        base.mkdir(parents=True, exist_ok=True)
        path = base / f"{safe_id}.json"
        path.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        # latest pointer (best-effort)
        latest = base / "latest.json"
        try:
            if latest.is_symlink() or latest.exists():
                latest.unlink()
            latest.symlink_to(path.name)
        except OSError:
            # Windows / restricted FS: write a small pointer file
            latest.write_text(path.name, encoding="utf-8")
        logger.info(
            "cycle_cost_summary run_id=%s n_calls=%s n_results=%s path=%s",
            safe_id,
            (summary.get("totals") or {}).get("n_calls_run"),
            (summary.get("totals") or {}).get("n_results"),
            path,
        )
        return path
    except Exception as exc:
        logger.warning("cycle_summary_emit: persist failed: %s", exc)
        return None


def finalize_and_persist(
    summary: dict[str, Any],
    api: Any | None = None,
    *,
    runs_dir: Path | None = None,
    repo_root: Path | None = None,
) -> Path | None:
    """Attach http_log when possible and persist. Never raises."""
    if api is not None:
        attach_http_log(summary, api)
    return persist_cycle_summary(summary, runs_dir=runs_dir, repo_root=repo_root)
