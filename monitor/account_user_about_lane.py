"""Bounded scheduled User About lane after post persistence and enrichment."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime

from monitor.twitterapi.user_about import (
    FetchBatchResult,
    fetch_user_about_batch,
)
from monitor.twitterapi.user_about_service import (
    count_due_new_accounts,
    due_new_account_selections,
    fetch_apply_user_about_batch,
    oldest_due_new_account_age_seconds,
)
from x_monitor.config import Config, MonotonicDeadline
from x_monitor.twitterapi_credentials import (
    TwitterApiCredentialPurpose,
    require_twitterapi_api_key,
)


def run_scheduled_user_about_lane(
    *,
    cfg: Config,
    deadline: MonotonicDeadline,
    watermark: datetime,
    cycle_kind: str,
    dry_run: bool,
    primary_aborted: bool,
    fetcher: Callable[..., Awaitable[FetchBatchResult]] = fetch_user_about_batch,
) -> dict[str, int | float | str | None]:
    """Attempt oldest due accounts within the shared cycle deadline."""
    result: dict[str, int | float | str | None] = {
        "status": "disabled",
        "due": 0,
        "oldest_due_age_seconds": None,
        "selected": 0,
        "claimed": 0,
        "attempted": 0,
        "accepted": 0,
        "success_empty": 0,
        "mapped_country": 0,
        "direct_region": 0,
        "unresolved": 0,
        "quarantined": 0,
        "deferred": 0,
        "retries": 0,
        "projected_credits": 0,
        "wall_seconds": 0.0,
        "stop_reason": None,
    }
    lane = cfg.harvest.user_about
    if cycle_kind != "scheduled" or dry_run or primary_aborted or not lane.enabled:
        return result

    due = count_due_new_accounts(watermark=watermark)
    result["due"] = due
    result["deferred"] = due
    if due == 0:
        result["status"] = "no_due_accounts"
        return result
    result["oldest_due_age_seconds"] = oldest_due_new_account_age_seconds(
        watermark=watermark
    )

    # Keep 30 seconds outside this lane for persistence and cycle summary.
    wall_seconds = min(float(lane.max_wall_seconds), deadline.remaining() - 30.0)
    if wall_seconds < 15.0:
        result["status"] = "deferred_deadline"
        result["stop_reason"] = "deadline_envelope"
        return result

    selections = due_new_account_selections(
        watermark=watermark, limit=lane.max_accounts
    )
    result["selected"] = len(selections)
    if not selections:
        result["status"] = "deferred_claims"
        return result
    try:
        api_key = require_twitterapi_api_key(TwitterApiCredentialPurpose.SCHEDULED)
    except RuntimeError:
        result["status"] = "credential_unavailable"
        result["stop_reason"] = "scheduled_credential_unavailable"
        return result

    try:
        applied_batch = fetch_apply_user_about_batch(
            selections,
            api_key=api_key,
            rate_qps=lane.effective_qps,
            concurrency=lane.concurrency,
            max_attempts=lane.max_attempts,
            max_credits=lane.max_credits,
            max_wall_seconds=wall_seconds,
            min_request_window_seconds=15,
            fetcher=fetcher,
        )
    except Exception as exc:  # noqa: BLE001 - this optional lane cannot abort a cycle
        result["status"] = "failed"
        result["stop_reason"] = type(exc).__name__
        return result

    batch = applied_batch.batch
    degraded_stops = {
        "auth_invalid",
        "auth_forbidden",
        "circuit_open",
        "account_quarantine_threshold",
    }
    result["status"] = (
        "completed"
        if batch.stop_reason is None
        else "degraded"
        if batch.stop_reason in degraded_stops
        else "deferred_budget"
    )
    result["claimed"] = len(selections) - applied_batch.deferred_claims
    result["attempted"] = len(batch.outcomes)
    result["retries"] = batch.retries
    result["projected_credits"] = batch.projected_credits
    result["wall_seconds"] = batch.wall_seconds
    result["stop_reason"] = batch.stop_reason
    result["deferred"] = max(0, due - len(batch.outcomes))
    if result["claimed"] == 0:
        result["status"] = "deferred_claims"
    for fetched, observation_outcome in applied_batch.applications:
        if observation_outcome is None or observation_outcome.identity_rejected:
            if fetched.reason in {"identity_mismatch", "schema_drift"} or (
                observation_outcome is not None
                and observation_outcome.identity_rejected
            ):
                result["quarantined"] += 1
            continue
        result["accepted"] += 1
        observation = fetched.observation
        if observation is None:
            continue
        candidates = observation.candidates
        if not candidates.get("account_based_in"):
            result["success_empty"] += 1
        if candidates.get("country_code"):
            result["mapped_country"] += 1
        elif candidates.get("based_in_region_key"):
            result["direct_region"] += 1
        elif candidates.get("account_based_in"):
            result["unresolved"] += 1
    return result
