"""U5 - apply loop body wiring U3 caller + U4 apply + exit summary logging.

Plan: docs/plans/2026-07-31-001-fix-lonely-placeholders-cron-apply-plan.md
Units U3, U4, U5.

`run_apply_loop` is the heart of the cron run:
  - Iterates candidate handles in batches of `batch_size`.
  - For each batch, calls `monitor.twitterapi.caller.lookup_batch`
    (U3) with rate_qps, concurrency, breaker.
  - For each successful LookupResult, calls `apply_one_row` (U4).
  - For each dead-letter LookupResult, appends a JSON line to
    ~/lonely-apply-dead-letter.log (KTD5).
  - Tracks partial=true if the breaker tripped, --max-seconds elapsed,
    or a SIGTERM was received (KTD7).
  - Returns a summary dict that `_emit_summary` (U2 helper) writes
    to stdout + ~/lonely-apply.log.

The loop is split into `_run_one_batch` for testability -- tests
can mock the batch generator and assert summary fields.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import time
from pathlib import Path
from typing import Any

from monitor.reconcile.apply_one_row import apply_one_row
from monitor.twitterapi.caller import (
    CircuitBreaker,
    LookupStats,
    lookup_batch,
)


def run_apply_loop(
    *,
    candidate_placeholders: list[tuple[str, str]],  # [(handle, author_id), ...]
    api_key: str | None,
    rate_qps: float,
    concurrency: int,
    batch_size: int,
    max_seconds: float,
    apply_log_path: Path,
    dead_letter_log_path: Path,
    received_signal_ref: list,  # mutable ref so SIGTERM/SIGINT can flip partial=true
) -> dict[str, Any]:
    """Run the full apply loop. Returns the exit summary dict.

    `received_signal_ref` is a single-element list; element 0 is None
    or a signal name. The caller (the management command) registers
    SIGTERM/SIGINT handlers that set this list's element.
    """
    started_at = time.time()
    deadline = started_at + max_seconds
    stats = LookupStats()
    breaker = CircuitBreaker()
    by_reason: dict[str, int] = {}
    resolved = 0
    dead_lettered = 0
    applied_count = 0
    rate_samples: list[float] = []

    # Open dead-letter log once for the whole run; we flush per write.
    dl_handle = None
    try:
        dl_handle = dead_letter_log_path.open("a")
    except OSError:
        pass

    try:
        for i in range(0, len(candidate_placeholders), batch_size):
            batch = candidate_placeholders[i : i + batch_size]
            handles = [h for h, _ in batch]

            # Wall-clock budget check before each batch.
            if time.time() > deadline or received_signal_ref[0] is not None:
                break

            # TwitterAPI lookup for this batch (U3).
            t0 = time.time()
            results: list = []
            try:
                # Run the async iterator to completion in a fresh loop.
                # We deliberately do NOT keep a long-lived loop across
                # batches: aiohttp's loop + connector are recreated per
                # batch, but each batch is short (~40s at 200 handles
                # and 5 QPS), so the connection-pool churn is bounded
                # and the cron can interleave DB writes between batches.
                async def _collect() -> list:
                    out = []
                    async for r in lookup_batch(
                        handles,
                        api_key=api_key or "",
                        rate_qps=rate_qps,
                        concurrency=concurrency,
                        stats=stats,
                        breaker=breaker,
                    ):
                        out.append(r)
                    return out

                results = asyncio.run(_collect())
            except Exception as exc:
                # Catastrophic batch failure -- record partial and bail.
                return _make_summary(
                    started_at=started_at,
                    stats=stats,
                    by_reason=by_reason,
                    partial=True,
                    error=f"batch_failed: {type(exc).__name__}: {exc}",
                    applied_count=applied_count,
                    rate_samples=rate_samples,
                )

            t1 = time.time()
            batch_secs = max(t1 - t0, 0.001)
            rate_samples.append(len(handles) / batch_secs)

            # Index by handle for the apply loop.
            by_handle = {r.handle: r for r in results}

            for handle, placeholder_author_id in batch:
                if time.time() > deadline or received_signal_ref[0] is not None:
                    # Append a partial flag and stop iterating.
                    return _make_summary(
                        started_at=started_at,
                        stats=stats,
                        by_reason=by_reason,
                        partial=True,
                        applied_count=applied_count,
                        rate_samples=rate_samples,
                    )

                lookup = by_handle.get(handle)
                if lookup is None or not lookup.success:
                    # Dead-letter (lookup is None only if the batch
                    # result dict is incomplete -- defensive).
                    reason = (lookup.reason if lookup else "unknown")
                    if dl_handle is not None:
                        try:
                            dl_handle.write(
                                json.dumps(
                                    {
                                        "handle": handle,
                                        "placeholder_author_id": placeholder_author_id,
                                        "reason": reason,
                                        "status_code": (
                                            lookup.status_code if lookup else None
                                        ),
                                        "response_excerpt": (
                                            lookup.response_excerpt if lookup else ""
                                        ),
                                        "ts": time.strftime(
                                            "%Y-%m-%dT%H:%M:%S%z", time.localtime()
                                        ),
                                    },
                                    sort_keys=True,
                                )
                                + "\n"
                            )
                        except OSError:
                            pass
                    by_reason[reason] = by_reason.get(reason, 0) + 1
                    dead_lettered += 1
                    continue

                # Apply (U4).
                apply_result = apply_one_row(
                    handle=handle,
                    placeholder_author_id=placeholder_author_id,
                    canonical=lookup.canonical,  # type: ignore[arg-type]
                )
                if apply_result.success:
                    resolved += 1
                    applied_count += 1
                else:
                    # Apply failed (integrity_error / exception); treat
                    # as dead-letter so the cron can move on.
                    if dl_handle is not None:
                        try:
                            dl_handle.write(
                                json.dumps(
                                    {
                                        "handle": handle,
                                        "placeholder_author_id": placeholder_author_id,
                                        "reason": f"apply_{apply_result.reason}",
                                        "ts": time.strftime(
                                            "%Y-%m-%dT%H:%M:%S%z", time.localtime()
                                        ),
                                    },
                                    sort_keys=True,
                                )
                                + "\n"
                            )
                        except OSError:
                            pass
                    by_reason[f"apply_{apply_result.reason}"] = (
                        by_reason.get(f"apply_{apply_result.reason}", 0) + 1
                    )
                    dead_lettered += 1

        # Loop exited normally -- either batch loop completed or
        # deadline/signal broke it (already handled above).
        return _make_summary(
            started_at=started_at,
            stats=stats,
            by_reason=by_reason,
            partial=(received_signal_ref[0] is not None or breaker.is_open),
            applied_count=applied_count,
            rate_samples=rate_samples,
            breaker_tripped=breaker.is_open,
        )
    finally:
        if dl_handle is not None:
            try:
                dl_handle.close()
            except OSError:
                pass


def _make_summary(
    *,
    started_at: float,
    stats: LookupStats,
    by_reason: dict[str, int],
    partial: bool,
    applied_count: int = 0,
    rate_samples: list[float] | None = None,
    error: str | None = None,
    breaker_tripped: bool = False,
) -> dict[str, Any]:
    finished_at = time.time()
    if rate_samples:
        # Average observed QPS across batches; the pacing gate means
        # this should be very close to rate_qps.
        avg_rate = sum(rate_samples) / len(rate_samples)
    else:
        avg_rate = 0.0
    summary = {
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(started_at)),
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(finished_at)),
        "dry_run": False,
        "total_placeholders": stats.looked_up,
        "looked_up": stats.looked_up,
        "resolved": stats.resolved,
        "applied": applied_count,
        "dead_lettered": stats.dead_lettered,
        "retried_after_429": stats.retried_after_429,
        "circuit_open_short_circuits": stats.circuit_open_short_circuits,
        "rate_actual_qps": round(avg_rate, 3),
        "max_time_wait_sockets": 0,  # measured externally (U6)
        "partial": partial,
        "dead_letter_reasons": dict(by_reason),
        "breaker_tripped": breaker_tripped,
    }
    if error:
        summary["error"] = error
    return summary