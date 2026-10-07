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
from core.official_company_candidates import candidate_priorities

LEGACY_INITIAL_KEY = "official-company-initial-v1"
INITIAL_KEY = "official-company-filtered-initial-v1"


def enqueue_filtered_accounts(accounts, *, initial_scan=None, deadline=None):
    priorities = candidate_priorities(accounts)
    existing = set(
        OfficialCompanyAccountState.objects.filter(
            account_id__in=[a.pk for a in accounts]
        ).values_list("account_id", flat=True)
    )
    processed = []
    for account in accounts:
        if deadline and time.monotonic() >= deadline:
            break
        if priorities[account.pk] is not None or account.pk in existing:
            enqueue_account(
                account,
                initial_scan=initial_scan,
                candidate_priority=priorities[account.pk],
            )
        processed.append(account)
    return processed


def coverage():
    scan = OfficialCompanyScan.objects.filter(pk=INITIAL_KEY).first()
    states = (
        OfficialCompanyAccountState.objects.filter(initial_scan=scan)
        if scan
        else OfficialCompanyAccountState.objects.none()
    )
    candidates = states.filter(candidate_priority__in=[1, 2, 3]).exclude(
        status="suppressed"
    )
    counts = dict(
        candidates.values("status").annotate(n=Count("pk")).values_list("status", "n")
    )
    gold = OfficialCompanyScan.objects.filter(pk=INITIAL_KEY + ":gold").first()
    candidate_count = sum(counts.values())
    unresolved = sum(counts.get(k, 0) for k in ["pending", "claimed", "retry_due"])
    screened_candidates = (
        candidates.filter(account_id__lte=scan.cursor).count()
        if scan and scan.cursor
        else 0
    )
    return {
        "population": scan.population if scan else 0,
        "enumerated": scan.enumerated if scan else 0,
        "enumeration_complete": bool(scan and scan.complete),
        "gold_staged": gold.enumerated if gold else 0,
        "gold_staging_complete": bool(gold and gold.complete),
        "candidates": candidate_count,
        "deferred": max(0, (scan.enumerated if scan else 0) - screened_candidates),
        "outcomes": counts,
        "priorities": dict(
            candidates.values("candidate_priority")
            .annotate(n=Count("pk"))
            .values_list("candidate_priority", "n")
        ),
        "coverage_complete": bool(scan and scan.complete and unresolved == 0),
    }


def scan_initial_batch(*, limit=100, deadline=None):
    if not 1 <= limit <= 500:
        raise ValueError("initial inventory batch must be 1..500")
    with transaction.atomic():
        legacy = OfficialCompanyScan.objects.filter(pk=LEGACY_INITIAL_KEY).first()
        scan, created = OfficialCompanyScan.objects.select_for_update().get_or_create(
            key=INITIAL_KEY,
            defaults={"started_at": legacy.started_at, "population": legacy.population}
            if legacy
            else {},
        )
        if created:
            if not legacy:
                scan.population = Account.objects.filter(
                    first_seen_at__lte=scan.started_at
                ).count()
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
        inventory = Account.objects.filter(first_seen_at__lte=scan.started_at)
        # Stage gold first, without counting authors twice. The subsequent full
        # ID inventory supplies whole-population coverage, even if badges change.
        gold, _ = OfficialCompanyScan.objects.select_for_update().get_or_create(
            key=INITIAL_KEY + ":gold", defaults={"started_at": scan.started_at}
        )
        if not gold.complete:
            gold_rows = list(
                inventory.filter(
                    verified_type__iexact="Business", author_id__gt=gold.cursor
                ).order_by("author_id")[:limit]
            )
            for account in enqueue_filtered_accounts(
                gold_rows, initial_scan=scan, deadline=deadline
            ):
                gold.cursor = account.author_id
                gold.enumerated += 1
            gold.complete = not inventory.filter(
                verified_type__iexact="Business", author_id__gt=gold.cursor
            ).exists()
            gold.save()
            if (
                gold_rows
                or not gold.complete
                or (deadline and time.monotonic() >= deadline)
            ):
                scan.save()
                return coverage()
        rows = list(
            inventory.filter(author_id__gt=scan.cursor).order_by("author_id")[:limit]
        )
        for account in enqueue_filtered_accounts(
            rows, initial_scan=scan, deadline=deadline
        ):
            scan.cursor = account.author_id
            scan.enumerated += 1
        scan.complete = not inventory.filter(author_id__gt=scan.cursor).exists()
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
        unique = {}
        for row in rows:
            account = getattr(row, account_field) if account_field else row
            if account is not None:
                unique[account.pk] = account
        processed = {
            a.pk
            for a in enqueue_filtered_accounts(list(unique.values()), deadline=deadline)
        }
        seen = set()
        for row in rows:
            if deadline and time.monotonic() >= deadline:
                break
            account = getattr(row, account_field) if account_field else row
            if account is not None and account.pk not in seen:
                if account.pk not in processed:
                    break
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
                : bounds[3]
            ]
        )
        if not rows:
            scan.cursor = ""
            rows = list(Account.objects.order_by("author_id")[: bounds[3]])
        for account in enqueue_filtered_accounts(rows, deadline=deadline):
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
            status__in=["pending", "retry_due", "claimed"],
            candidate_priority__in=[1, 2, 3],
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
    ids = []
    for priority in [1, 2, 3]:
        tier = qs.filter(candidate_priority=priority)
        retry = list(
            tier.filter(status__in=["retry_due", "claimed"])
            .order_by("created_at")
            .values_list("pk", flat=True)[:1]
        )
        remaining = limit - len(ids)
        selected = retry[:remaining] + list(
            tier.filter(status="pending")
            .order_by("created_at" if initial else "-updated_at")
            .values_list("pk", flat=True)[: max(0, remaining - len(retry))]
        )
        if len(selected) < remaining:
            selected += list(
                tier.exclude(pk__in=selected)
                .order_by("created_at")
                .values_list("pk", flat=True)[: remaining - len(selected)]
            )
        ids += selected
        if len(ids) >= limit:
            break
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
