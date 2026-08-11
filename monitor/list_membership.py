"""Observe and reconcile the curated Twitter list behind Call A."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.models import Account, TwitterListMembership, TwitterListSyncState
from x_monitor.apify import ListMembersSnapshot, TwitterApiClient
from x_monitor.config import Config


@dataclass
class MembershipResult:
    status: str
    observed: int = 0
    activated: int = 0
    deactivated: int = 0
    snapshot_id: str | None = None
    completed_at: datetime | None = None
    degraded: list[str] = field(default_factory=list)


def _upsert_account(
    member: dict[str, Any], *, degraded: list[str]
) -> tuple[Account, bool]:
    author_id = str(member.get("author_id") or "").strip()
    if not author_id:
        raise ValueError("list member is missing a stable author_id")
    handle = str(member.get("handle") or "").strip() or None
    display_name = str(member.get("display_name") or "").strip() or None
    defaults = {"handle": handle, "display_name": display_name}
    try:
        with transaction.atomic():
            account, created = Account.objects.get_or_create(
                author_id=author_id, defaults=defaults
            )
    except IntegrityError:
        account, created = Account.objects.get_or_create(author_id=author_id)
        degraded.append(f"handle_conflict:{author_id}")

    changed: list[str] = []
    if handle and account.handle != handle:
        account.handle = handle
        changed.append("handle")
    if display_name and account.display_name != display_name:
        account.display_name = display_name
        changed.append("display_name")
    if changed:
        try:
            with transaction.atomic():
                account.save(update_fields=[*changed, "last_seen_at"])
        except IntegrityError:
            account.refresh_from_db()
            degraded.append(f"handle_conflict:{author_id}")
    return account, created


def _upsert_membership(
    *,
    list_id: int,
    account: Account,
    observed_at: datetime,
    source: str,
    source_run_id: str,
    complete: bool,
) -> tuple[TwitterListMembership, bool, bool]:
    membership = TwitterListMembership.objects.filter(
        list_id=list_id, account=account
    ).first()
    if membership is None:
        membership = TwitterListMembership.objects.create(
            list_id=list_id,
            account=account,
            active=True,
            first_seen_at=observed_at,
            last_seen_at=observed_at,
            last_complete_reconciliation_at=(observed_at if complete else None),
            source=source,
            source_run_id=source_run_id,
        )
        return membership, True, False
    was_active = membership.active
    membership.active = True
    membership.last_seen_at = max(observed_at, membership.first_seen_at)
    if complete:
        membership.last_complete_reconciliation_at = max(
            observed_at, membership.first_seen_at
        )
    membership.source = source
    membership.source_run_id = source_run_id
    membership.save()
    return membership, False, was_active


def observe_call_a_authors(
    *,
    list_id: int,
    items: list[dict[str, Any]],
    run_id: str,
    observed_at: datetime | None = None,
) -> MembershipResult:
    """Apply current-membership evidence carried directly by a Call A page."""

    observed_at = observed_at or timezone.now()
    result = MembershipResult(status="observed")
    seen_ids: set[str] = set()
    for item in items:
        author_id = str(item.get("author_id") or "").strip()
        if not author_id:
            result.degraded.append("missing_author_id")
            continue
        if author_id in seen_ids:
            continue
        seen_ids.add(author_id)
        member = {
            "author_id": author_id,
            "handle": item.get("author_handle") or item.get("username"),
            "display_name": item.get("author_name"),
        }
        try:
            with transaction.atomic():
                account, created = _upsert_account(member, degraded=result.degraded)
                if created:
                    result.degraded.append(f"unknown_account:{author_id}")
                _upsert_membership(
                    list_id=list_id,
                    account=account,
                    observed_at=observed_at,
                    source="call_a",
                    source_run_id=run_id,
                    complete=False,
                )
                result.observed += 1
        except (IntegrityError, ValueError) as exc:
            result.degraded.append(f"observation_failed:{author_id}:{exc}")
    if result.degraded:
        result.status = "degraded"
    return result


def reconciliation_due(
    *, list_id: int, interval_hours: int, now: datetime | None = None
) -> bool:
    now = now or timezone.now()
    state = TwitterListSyncState.objects.filter(list_id=list_id).first()
    return state is None or state.last_complete_at <= now - timedelta(
        hours=interval_hours
    )


def reconcile_complete_snapshot(
    *,
    list_id: int,
    snapshot: ListMembersSnapshot,
    snapshot_id: str,
    completed_at: datetime | None = None,
) -> MembershipResult:
    """Atomically replace active membership after a validated full walk."""

    if not snapshot.complete:
        return MembershipResult(
            status="incomplete",
            snapshot_id=snapshot_id,
            degraded=[snapshot.reason or "incomplete_snapshot"],
        )
    wall_now = timezone.now()
    if completed_at is None or completed_at < wall_now:
        completed_at = wall_now
    result = MembershipResult(
        status="completed",
        snapshot_id=snapshot_id,
        completed_at=completed_at,
    )
    with transaction.atomic():
        active_ids: set[str] = set()
        for member in snapshot.members:
            account, created = _upsert_account(member, degraded=result.degraded)
            if created:
                result.degraded.append(f"unknown_account:{account.author_id}")
            active_ids.add(account.author_id)
            _, membership_created, was_active = _upsert_membership(
                list_id=list_id,
                account=account,
                observed_at=completed_at,
                source="snapshot",
                source_run_id=snapshot_id,
                complete=True,
            )
            result.activated += int(membership_created or not was_active)

        removed = TwitterListMembership.objects.filter(
            list_id=list_id, active=True
        ).exclude(account_id__in=active_ids)
        result.deactivated = removed.update(
            active=False,
            last_complete_reconciliation_at=completed_at,
            source="snapshot",
            source_run_id=snapshot_id,
        )
        TwitterListSyncState.objects.update_or_create(
            list_id=list_id,
            defaults={
                "snapshot_id": snapshot_id,
                "last_complete_at": completed_at,
            },
        )
    if result.degraded:
        result.status = "degraded"
    return result


def run_due_reconciliation(
    *,
    api: TwitterApiClient,
    cfg: Config,
    list_id: int,
    deadline: Any,
    run_id: str,
    force: bool = False,
) -> MembershipResult:
    membership_cfg = cfg.harvest.list_membership
    if not force and not reconciliation_due(
        list_id=list_id,
        interval_hours=membership_cfg.reconcile_interval_hours,
    ):
        return MembershipResult(status="not_due")
    request_envelope = membership_cfg.request_timeout_seconds * (
        int(getattr(api, "max_retries", 2)) + 1
    ) + 8
    if not deadline.can_start(request_envelope):
        return MembershipResult(
            status="deferred", degraded=["deadline_exhausted"]
        )
    try:
        snapshot = api.run_list_members(
            list_id,
            max_pages=membership_cfg.max_pages,
            page_size=membership_cfg.page_size,
            deadline=deadline,
            request_timeout_seconds=membership_cfg.request_timeout_seconds,
        )
    except Exception as exc:
        return MembershipResult(
            status="incomplete", degraded=[f"snapshot_error:{exc}"]
        )
    snapshot_id = f"{run_id}:list:{uuid.uuid4().hex[:12]}"
    return reconcile_complete_snapshot(
        list_id=list_id,
        snapshot=snapshot,
        snapshot_id=snapshot_id,
    )
