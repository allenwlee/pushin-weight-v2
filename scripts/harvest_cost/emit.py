"""Persist CycleRunner summary JSON for cost tooling (plan 2026-08-10-003).

Lives under scripts/harvest_cost; imported thinly from monitor.cycle.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from monitor.harvest_summary import (
    build_cohort_receipt,
    build_summary_envelope,
    redact_http_log,
    redacted_summary_payload,
    serialize_cohort_receipt,
    serialize_summary_envelope,
)

logger = logging.getLogger(__name__)

# Default under repo data/runs — same family as v1 run summaries.
DEFAULT_RUNS_SUBDIR = Path("data/runs")


def default_runs_dir(repo_root: Path | None = None) -> Path:
    root = repo_root if repo_root is not None else Path.cwd()
    return root / DEFAULT_RUNS_SUBDIR


def attach_http_log(summary: dict[str, Any], api: Any) -> None:
    """Copy only safe request metrics into ``summary['http_log']``.

    Query parameters and provider response bodies are intentionally omitted;
    the canonical Render envelope has no need for them and they are an easy
    route for credentials or post text to leak into durable evidence.
    """
    try:
        log = getattr(api, "_request_log", None)
        if log is None:
            return
        summary["http_log"] = redact_http_log(log)
    except Exception as exc:  # never break harvest
        logger.warning("cycle_summary_emit: attach_http_log failed: %s", exc)


def persist_cycle_summary(
    summary: Mapping[str, Any],
    *,
    envelope: Mapping[str, Any] | None = None,
    runs_dir: Path | None = None,
    repo_root: Path | None = None,
) -> Path | None:
    """Write summary JSON to data/runs/<run_id>.json. Returns path or None on failure."""
    try:
        envelope = envelope or build_summary_envelope(summary)
        persisted_summary = redacted_summary_payload(summary, envelope)
        run_id = str(persisted_summary.get("run_id") or "unknown")
        # sanitize path segment
        safe_id = "".join(c if c.isalnum() or c in "-_." else "_" for c in run_id)
        base = runs_dir if runs_dir is not None else default_runs_dir(repo_root)
        base.mkdir(parents=True, exist_ok=True)
        path = base / f"{safe_id}.json"
        path.write_text(
            json.dumps(persisted_summary, indent=2, ensure_ascii=False, default=str),
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
    envelope: Mapping[str, Any] | None = None
    try:
        envelope = build_summary_envelope(summary)
        logger.info(serialize_summary_envelope(envelope))
        cohort = build_cohort_receipt(summary, envelope=envelope)
        if cohort is not None:
            logger.info(serialize_cohort_receipt(cohort))
    except Exception as exc:
        logger.warning("cycle_summary_emit: canonical envelope failed: %s", exc)
    return persist_cycle_summary(
        summary,
        envelope=envelope,
        runs_dir=runs_dir,
        repo_root=repo_root,
    )
