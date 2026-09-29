"""Shared claim and persistence boundary for scheduled and manual User About."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

from django.db import transaction
from django.db.models import OuterRef, Q, Subquery
from django.utils import timezone

from core.models import Account, AccountUserAboutActivation, AccountUserAboutClaim, Post
from monitor.twitterapi.user_about import (
    ACCOUNT_QUARANTINE_REASONS,
    FetchBatchResult,
    FetchOutcome,
    FetchSelection,
    fetch_user_about_batch,
)

if TYPE_CHECKING:
    from core.models import AccountObservationOutcome


@dataclass(frozen=True)
class AppliedFetchBatch:
    batch: FetchBatchResult
    applications: tuple[tuple[FetchOutcome, AccountObservationOutcome | None], ...]
    deferred_claims: int


def activate_scheduled_user_about() -> datetime:
    """Create the one durable watermark before a scheduled search begins."""
    activation, _ = AccountUserAboutActivation.objects.get_or_create(key=1)
    return activation.activated_at


def due_new_account_selections(
    *, watermark: datetime, limit: int, now: datetime | None = None
) -> list[FetchSelection]:
    """Select oldest first-post accounts without a rolling age cutoff."""
    if limit <= 0:
        return []
    rows = _due_new_accounts(watermark=watermark, now=now).values_list(
        "author_id", "handle"
    )[:limit]
    return [
        FetchSelection(author_id=author_id, handle=handle) for author_id, handle in rows
    ]


def count_due_new_accounts(*, watermark: datetime, now: datetime | None = None) -> int:
    return _due_new_accounts(watermark=watermark, now=now).count()


def oldest_due_new_account_age_seconds(
    *, watermark: datetime, now: datetime | None = None
) -> float | None:
    """Aggregate backlog age without reporting any account identifier."""
    now = now or timezone.now()
    first_post_at = _due_new_accounts(watermark=watermark, now=now).values_list(
        "first_post_at", flat=True
    ).first()
    return max(0.0, (now - first_post_at).total_seconds()) if first_post_at else None


def _due_new_accounts(*, watermark: datetime, now: datetime | None = None):
    if timezone.is_naive(watermark):
        raise ValueError("watermark must be timezone-aware")
    now = now or timezone.now()
    earliest_post = (
        Post.objects.filter(author_id=OuterRef("author_id"))
        .order_by("fetched_at")
        .values("fetched_at")[:1]
    )
    return (
        Account.objects.filter(
            author_id__regex=r"^[0-9]+$",
            account_based_in_fetched_at__isnull=True,
        )
        .exclude(handle__isnull=True)
        .exclude(handle="")
        .annotate(first_post_at=Subquery(earliest_post))
        .filter(first_post_at__gte=watermark)
        .filter(
            Q(user_about_claim__isnull=True)
            | Q(
                user_about_claim__state=AccountUserAboutClaim.State.RETRY_DUE,
                user_about_claim__next_eligible_at__lte=now,
            )
        )
        .order_by("first_post_at", "author_id")
    )


def claim_account(
    *,
    author_id: str,
    owner: str,
    lease_seconds: float = 120,
    refresh: bool = False,
    now: datetime | None = None,
) -> AccountUserAboutClaim | None:
    """Acquire an Account-keyed claim before HTTP, fencing competing callers."""
    if not owner or lease_seconds <= 0:
        raise ValueError("owner and positive lease_seconds are required")
    now = now or timezone.now()
    with transaction.atomic():
        accounts = Account.objects.select_for_update().filter(author_id=author_id)
        if not refresh:
            accounts = accounts.filter(account_based_in_fetched_at__isnull=True)
        account = accounts.exclude(handle__isnull=True).exclude(handle="").first()
        if account is None:
            return None
        claim = (
            AccountUserAboutClaim.objects.select_for_update()
            .filter(account=account)
            .first()
        )
        if claim is None:
            claim = AccountUserAboutClaim(account=account)
        elif claim.state == AccountUserAboutClaim.State.ACTIVE:
            if claim.lease_expires_at and claim.lease_expires_at <= now:
                claim.state = AccountUserAboutClaim.State.UNCERTAIN
                claim.last_reason = "lease_expired"
                claim.save(update_fields=["state", "last_reason", "updated_at"])
            return None
        elif refresh and claim.state == AccountUserAboutClaim.State.FETCHED:
            pass
        elif (
            claim.state != AccountUserAboutClaim.State.RETRY_DUE
            or claim.next_eligible_at
            and claim.next_eligible_at > now
        ):
            return None
        claim.state = AccountUserAboutClaim.State.ACTIVE
        claim.owner = owner
        claim.lease_expires_at = now + timedelta(seconds=lease_seconds)
        claim.next_eligible_at = None
        claim.admissions += 1
        claim.last_reason = ""
        claim.save()
        return claim


def settle_outcome(
    *,
    author_id: str,
    owner: str,
    outcome: FetchOutcome | None,
    now: datetime | None = None,
) -> AccountObservationOutcome | None:
    """Apply accepted evidence and settle the owned claim in one transaction.

    A missing outcome means the bounded fetcher admitted no HTTP for this
    selection, so it can become due again immediately. A response with an
    uncertain transport result receives a retry delay.
    """
    now = now or timezone.now()
    with transaction.atomic():
        account = (
            Account.objects.select_for_update().filter(author_id=author_id).first()
        )
        if account is None:
            return None
        claim = (
            AccountUserAboutClaim.objects.select_for_update()
            .filter(account=account, owner=owner)
            .first()
        )
        if claim is None or claim.state not in {
            AccountUserAboutClaim.State.ACTIVE,
            AccountUserAboutClaim.State.UNCERTAIN,
        }:
            return None
        applied = None
        reason = outcome.reason if outcome else "not_admitted"
        if outcome is not None and outcome.author_id != author_id:
            reason = "identity_mismatch"
        elif (
            outcome is not None
            and reason == "success"
            and outcome.observation is None
        ):
            reason = "schema_drift"
        elif (
            outcome is not None
            and reason == "success"
            and outcome.observation is not None
        ):
            observation = outcome.observation
            applied = Account.apply_observation(
                author_id=author_id,
                observed_author_id=observation.author_id,
                source="user_about",
                observed_at=observation.candidates["account_based_in_fetched_at"],
                candidates=observation.candidates,
                present_fields=observation.present_fields,
                expected_handle=(
                    account.handle
                    if observation.candidates.get("unavailable") is True
                    else None
                ),
            )
            if applied.identity_rejected:
                reason = "identity_mismatch"
            else:
                # The observation gateway owns the timestamp. If it rejected
                # the checkpoint, roll back its other fields with this claim.
                account.refresh_from_db(fields=["account_based_in_fetched_at"])
                if account.account_based_in_fetched_at is None:
                    raise ValueError("User About observation rejected its checkpoint")
        if reason == "success":
            claim.state = AccountUserAboutClaim.State.FETCHED
            claim.next_eligible_at = None
        elif reason in ACCOUNT_QUARANTINE_REASONS:
            claim.state = AccountUserAboutClaim.State.QUARANTINED
            claim.next_eligible_at = None
        else:
            claim.state = AccountUserAboutClaim.State.RETRY_DUE
            claim.next_eligible_at = now + (
                timedelta(minutes=15) if outcome is not None else timedelta(0)
            )
        claim.lease_expires_at = None
        claim.last_reason = reason
        claim.save()
        return applied


def mark_claims_uncertain(*, author_ids: list[str], owner: str) -> None:
    """Keep ambiguous requests fenced when a batch exits unexpectedly."""
    AccountUserAboutClaim.objects.filter(
        account_id__in=author_ids,
        owner=owner,
        state=AccountUserAboutClaim.State.ACTIVE,
    ).update(
        state=AccountUserAboutClaim.State.UNCERTAIN,
        last_reason="batch_interrupted",
        updated_at=timezone.now(),
    )


def fetch_apply_user_about_batch(
    selections: list[FetchSelection],
    *,
    api_key: str,
    rate_qps: float,
    concurrency: int,
    max_attempts: int,
    max_credits: int,
    max_wall_seconds: float,
    min_request_window_seconds: float = 0,
    refresh: bool = False,
    fetcher: Callable[..., Awaitable[FetchBatchResult]] = fetch_user_about_batch,
    clock: Callable[[], float] = time.monotonic,
) -> AppliedFetchBatch:
    """Share claim, existing bounded fetcher, and observation across callers."""
    if max_wall_seconds <= 0:
        raise ValueError("max_wall_seconds must be positive")
    started = clock()
    owner = str(uuid4())
    claimed: list[FetchSelection] = []
    for selection in selections:
        if clock() - started >= max_wall_seconds - min_request_window_seconds:
            break
        if (
            claim_account(
                author_id=selection.author_id,
                owner=owner,
                lease_seconds=max_wall_seconds + 30,
                refresh=refresh,
            )
            is not None
        ):
            claimed.append(selection)
    if not claimed:
        return AppliedFetchBatch(
            batch=FetchBatchResult(
                outcomes=[],
                attempts=0,
                retries=0,
                projected_credits=0,
                latencies_ms=[],
                wall_seconds=0,
                stop_reason=None,
            ),
            applications=(),
            deferred_claims=len(selections),
        )
    try:
        remaining_wall = max(0.0, max_wall_seconds - (clock() - started))
        fetch_kwargs = {
            "api_key": api_key,
            "rate_qps": rate_qps,
            "concurrency": concurrency,
            "max_attempts": max_attempts,
            "max_credits": max_credits,
            "max_wall_seconds": remaining_wall,
        }
        if min_request_window_seconds:
            fetch_kwargs["min_request_window_seconds"] = min_request_window_seconds
        if remaining_wall <= 0 or remaining_wall < min_request_window_seconds:
            batch = FetchBatchResult(
                outcomes=[], attempts=0, retries=0, projected_credits=0,
                latencies_ms=[], wall_seconds=0,
                stop_reason=(
                    "deadline_envelope"
                    if min_request_window_seconds else "wall_time_budget"
                ),
            )
        else:
            batch = asyncio.run(fetcher(claimed, **fetch_kwargs))
        claimed_ids = {selection.author_id for selection in claimed}
        returned_ids = [outcome.author_id for outcome in batch.outcomes]
        if len(returned_ids) != len(set(returned_ids)) or not set(
            returned_ids
        ).issubset(claimed_ids):
            raise ValueError("User About batch returned an invalid selection set")
        outcomes = {outcome.author_id: outcome for outcome in batch.outcomes}
        applications = []
        for selection in claimed:
            outcome = outcomes.get(selection.author_id)
            applied = settle_outcome(
                author_id=selection.author_id,
                owner=owner,
                outcome=outcome,
            )
            if outcome is not None:
                applications.append((outcome, applied))
    except Exception:
        mark_claims_uncertain(
            author_ids=[selection.author_id for selection in claimed], owner=owner
        )
        raise
    batch = replace(batch, wall_seconds=clock() - started)
    return AppliedFetchBatch(
        batch=batch,
        applications=tuple(applications),
        deferred_claims=len(selections) - len(claimed),
    )
