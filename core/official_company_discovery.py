"""Resumable full inventory and independent observation-driven discovery."""

from __future__ import annotations

import json
import time
from datetime import datetime

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from core.models import (
    Account,
    AccountProfileSnapshot,
    OfficialCompanyAccountState,
    OfficialCompanyScan,
    Post,
)
from core.official_company_accounts import (
    ROLE,
    enqueue_account,
    evaluate_account,
    register_account,
)

INITIAL_KEY = "official-company-initial-v1"


def coverage():
    scan = OfficialCompanyScan.objects.filter(pk=INITIAL_KEY).first()
    states = (
        OfficialCompanyAccountState.objects.filter(initial_scan=scan)
        if scan
        else OfficialCompanyAccountState.objects.none()
    )
    counts = dict(
        states.values("status").annotate(n=Count("pk")).values_list("status", "n")
    )
    unresolved = sum(counts.get(k, 0) for k in ["pending", "claimed", "retry_due"])
    return {
        "population": scan.population if scan else 0,
        "enumerated": scan.enumerated if scan else 0,
        "enumeration_complete": bool(scan and scan.complete),
        "outcomes": counts,
        "coverage_complete": bool(
            scan
            and scan.complete
            and sum(counts.values()) >= scan.population
            and unresolved == 0
        ),
    }


def scan_initial_batch(*, limit=100, deadline=None):
    if not 1 <= limit <= 500:
        raise ValueError("initial inventory batch must be 1..500")
    with transaction.atomic():
        scan, created = OfficialCompanyScan.objects.select_for_update().get_or_create(
            key=INITIAL_KEY
        )
        if created:
            scan.population = Account.objects.filter(
                first_seen_at__lte=scan.started_at
            ).count()
            # Changes during the full scan belong to independent observation
            # cursors, even when they occur behind the initial keyset cursor.
            for key in [
                "account-observations",
                "post-observations",
                "profile-observations",
            ]:
                OfficialCompanyScan.objects.get_or_create(
                    key=key, defaults={"started_at": scan.started_at}
                )
        if scan.complete:
            return coverage()
        rows = list(
            Account.objects.filter(
                first_seen_at__lte=scan.started_at, author_id__gt=scan.cursor
            ).order_by("author_id")[:limit]
        )
        for account in rows:
            if deadline and time.monotonic() >= deadline:
                break
            enqueue_account(account, initial_scan=scan)
            scan.cursor = account.author_id
            scan.enumerated += 1
        scan.complete = not Account.objects.filter(
            first_seen_at__lte=scan.started_at, author_id__gt=scan.cursor
        ).exists()
        scan.save()
    return coverage()


def _observations(key, model, time_field, *, limit, account_field=None, deadline=None):
    with transaction.atomic():
        scan, _ = OfficialCompanyScan.objects.select_for_update().get_or_create(key=key)
        cursor = (
            json.loads(scan.cursor)
            if scan.cursor
            else {"at": scan.started_at.isoformat(), "pk": None}
        )
        at = datetime.fromisoformat(cursor["at"])
        after = Q(**{time_field + "__gt": at})
        if cursor["pk"] is not None:
            after |= Q(**{time_field: at, "pk__gt": cursor["pk"]})
        # Observation timestamps, never the post's publication date.
        observations = model.objects.filter(after).order_by(time_field, "pk")
        if account_field:
            observations = observations.select_related(account_field)
        rows = list(observations[:limit])
        seen = set()
        for row in rows:
            if deadline and time.monotonic() >= deadline:
                break
            account = getattr(row, account_field) if account_field else row
            if account is not None and account.pk not in seen:
                enqueue_account(account)
                seen.add(account.pk)
            scan.cursor = json.dumps(
                {"at": getattr(row, time_field).isoformat(), "pk": row.pk}
            )
            scan.enumerated += 1
        scan.save()
    return len(seen)


def enqueue_incremental(*, limit=100, deadline=None):
    if not 1 <= limit <= 100:
        raise ValueError("incremental account bound must be 1..100")
    # All-account rotation closes observation timestamp / late-commit races and
    # covers existing rows when incremental discovery precedes initial scanning.
    per_source, remainder = divmod(limit, 4)
    # Small operator batches still rotate across the whole account population.
    bounds = [
        per_source + int(remainder >= 2),
        per_source + int(remainder >= 3),
        per_source,
        per_source + int(remainder >= 1),
    ]
    count = 0
    sources = [
        ("account-observations", Account, "last_seen_at", None),
        ("post-observations", Post, "fetched_at", "author"),
        ("profile-observations", AccountProfileSnapshot, "last_observed_at", "account"),
    ]
    for (key, model, field, account_field), source_limit in zip(
        sources, bounds[:3], strict=True
    ):
        if source_limit == 0:
            continue
        count += _observations(
            key,
            model,
            field,
            limit=source_limit,
            account_field=account_field,
            deadline=deadline,
        )
    with transaction.atomic():
        scan, _ = OfficialCompanyScan.objects.select_for_update().get_or_create(
            key="rotating-inventory"
        )
        rows = list(
            Account.objects.filter(author_id__gt=scan.cursor).order_by("author_id")[
                :bounds[3]
            ]
        )
        if not rows:
            scan.cursor = ""
            rows = list(Account.objects.order_by("author_id")[:bounds[3]])
        for account in rows:
            if deadline and time.monotonic() >= deadline:
                break
            enqueue_account(account)
            count += 1
            scan.cursor = account.author_id
        scan.save()
    return count


def build_discovery_call(cfg):
    from core.targeted_extraction import build_targeted_extraction_calls
    from x_monitor.deepinfra import DeepInfraChatCompletionsClient

    if not cfg.enabled:
        return None
    client = DeepInfraChatCompletionsClient.from_env(
        model=cfg.model, request_profile="deepseek_0731"
    )
    call = build_targeted_extraction_calls(
        client=client, roles={ROLE: cfg}, timeout_seconds=cfg.request_timeout_seconds
    ).get(ROLE)
    if call is not None:
        from core.official_company_accounts import digest

        call.credential_revision = digest({"key": client.api_key, "model": cfg.model})
    return call


def drain_accounts(*, cfg, call, limit, budget_scope, initial=False, deadline=None):
    now = timezone.now()
    result = {"attempted": 0, "registered": 0}
    qs = (
        OfficialCompanyAccountState.objects.filter(
            status__in=["pending", "retry_due", "claimed"]
        )
        .filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
        .filter(
            ~Q(status="claimed")
            | Q(claim_expires_at__isnull=True)
            | Q(claim_expires_at__lte=now)
        )
    )
    if initial:
        qs = qs.filter(initial_scan_id=INITIAL_KEY)
    # One due retry gets a slot; the remaining slots draw oldest unseen work.
    retry = list(
        qs.filter(status__in=["retry_due", "claimed"])
        .order_by("created_at")
        .values_list("pk", flat=True)[:1]
    )
    ids = retry + list(
        qs.filter(status="pending")
        .order_by("created_at" if initial else "-updated_at")
        .values_list("pk", flat=True)[: max(0, limit - len(retry))]
    )
    if len(ids) < limit:
        ids += list(
            qs.exclude(pk__in=ids)
            .order_by("created_at")
            .values_list("pk", flat=True)[: limit - len(ids)]
        )
    for state_id in ids[:limit]:
        if deadline and time.monotonic() + cfg.request_timeout_seconds + 2 > deadline:
            break
        if evaluate_account(
            state_id, cfg=cfg, call=call, budget_scope=budget_scope, initial=initial
        ):
            result["attempted"] += 1
    if cfg.registration_enabled:
        for state_id in (
            OfficialCompanyAccountState.objects.filter(status="accepted")
            .order_by("updated_at")
            .values_list("pk", flat=True)[:limit]
        ):
            if deadline and time.monotonic() + 1 > deadline:
                break
            result["registered"] += int(register_account(state_id, cfg=cfg) is not None)
    return result


def run_discovery_lane(
    *, cfg, run_id, deadline=None, call=None, client=None, allowance=2
):
    if not cfg.enabled:
        return {"status": "disabled"}
    lane_end = time.monotonic() + cfg.lane_deadline_seconds
    if deadline is not None:
        lane_end = min(lane_end, time.monotonic() + deadline.remaining())
    if lane_end - time.monotonic() < cfg.request_timeout_seconds + 2:
        return {"status": "deferred_deadline"}
    enqueued = enqueue_incremental(deadline=lane_end)
    result = drain_accounts(
        cfg=cfg,
        call=call,
        limit=min(cfg.max_calls_per_cycle, allowance),
        budget_scope=str(run_id),
        deadline=lane_end,
    )
    result.update(status="complete", enqueued=enqueued)
    if cfg.list_sync_enabled and client is not None:
        from core.official_company_lists import sync_intents

        result["list_sync"] = sync_intents(cfg=cfg, client=client, deadline=lane_end)
    return result
