"""Bounded native catalog observations precede reviewed crosswalk/cohort admission."""

from __future__ import annotations

from django.utils import timezone

from core.collection_state import checkpoint_scope, claim_job, finish_run
from core.hf_catalog import _envelopes, persist_product
from core.hf_metadata_client import HFMetadataClient
from core.measurement_taxonomy import digest, require
from core.models import (
    CollectionJob,
    CollectionObservation,
    CollectionRun,
    CollectionScopeRun,
)
from scripts.benchmark_download_collector.sources import (
    Budget,
    SourceError,
    openrouter_catalog_page,
)


def _openrouter(claim, job, budget, key):
    ownership = {"authors": job.definition["scope"].get("authors", [])}
    scoped = CollectionScopeRun.objects.filter(
        run_id=claim.run_id, scope_kind="model_catalog", scope_key="models"
    ).first()
    count = 0
    while scoped is None or not scoped.enumeration_complete:
        remaining = job.definition["budgets"]["items"] - count
        if remaining <= 0:
            raise SourceError("item_cap")
        offset = int(scoped.cursor) if scoped and scoped.cursor else 0
        result = openrouter_catalog_page(
            budget,
            key=key,
            offset=offset,
            limit=min(500, remaining),
            authors=ownership["authors"],
        )
        if budget.total_bytes_read > budget.max_bytes:
            raise SourceError("response_size_cap")
        observed_at = timezone.now()

        def write(run, scope, result=result, observed_at=observed_at):
            for row in result["rows"]:
                key = digest(
                    {"kind": "model_catalog", "native_id": row["id"], "payload": row}
                )
                CollectionObservation.objects.get_or_create(
                    run=run,
                    observation_key=key,
                    defaults={
                        "scope_run": scope,
                        "resource_key": key,
                        "source_identifier": row["id"],
                        "source_subject_kind": "model",
                        "listing": row,
                        "observed_at": observed_at,
                        "dimensions": {"kind": "model_catalog"},
                        "source_metadata": {
                            "listing_created_unix": row.get("created"),
                            "catalog_id": row["id"],
                            "canonical_slug": row["canonical_slug"],
                            "usage_mapping_verified": False,
                        },
                    },
                )

        history = [*(scoped.cursor_history if scoped else []), str(offset)]
        require(
            result["next_offset"] is None or str(result["next_offset"]) not in history,
            "catalog pagination loop",
        )
        scoped = checkpoint_scope(
            claim,
            scope_kind="model_catalog",
            scope_key="models",
            ownership=ownership,
            cursor=str(result["next_offset"])
            if result["next_offset"] is not None
            else None,
            cursor_history=history,
            enumeration_complete=result["complete"],
            outcome="complete" if result["complete"] else "pending",
            write=write,
            envelopes=[*(scoped.envelopes if scoped else []), result],
            raw_count=(scoped.raw_count if scoped else 0) + len(result["rows"]),
        )
        count += len(result["rows"])
    return count


def _hf(claim, job, budget):
    frozen = job.definition["scope"]["hf_scope"]
    rules = frozen["rules"]
    count = 0
    before = budget.remaining
    require(budget.deadline > budget.clock(), "inventory deadline expired")
    client = HFMetadataClient(
        budget.client,
        max_requests=budget.remaining,
        max_seconds=budget.deadline - budget.clock(),
        max_bytes=budget.max_bytes,
        max_total_bytes=budget.max_bytes - budget.total_bytes_read,
        clock=budget.clock,
        sleep=budget.sleep,
    )
    try:
        for entry in frozen["namespaces"]:
            namespace = entry["namespace"]
            scoped = CollectionScopeRun.objects.filter(
                run_id=claim.run_id, scope_kind="namespace", scope_key=namespace
            ).first()
            while scoped is None or not scoped.enumeration_complete:
                remaining = job.definition["budgets"]["items"] - count
                if remaining <= 0:
                    raise SourceError("item_cap")
                result = client.list_page(
                    namespace,
                    scoped.cursor if scoped else None,
                    limit=min(100, remaining),
                    sort="createdAt",
                )
                envelopes = [
                    *(scoped.envelopes if scoped else []),
                    *_envelopes(result, "listing"),
                ]
                if result.outcome != "ok":
                    checkpoint_scope(
                        claim,
                        scope_kind="namespace",
                        scope_key=namespace,
                        ownership=entry,
                        cursor=scoped.cursor if scoped else None,
                        envelopes=envelopes,
                        outcome=result.outcome,
                    )
                    raise SourceError(result.outcome)
                history = (
                    [
                        *(scoped.cursor_history if scoped else []),
                        scoped.cursor or "first",
                    ]
                    if scoped
                    else ["first"]
                )
                require(
                    result.next_cursor is None or result.next_cursor not in history,
                    "HF cursor loop",
                )
                observed_at = timezone.now()

                def write(
                    run, scope, result=result, entry=entry, observed_at=observed_at
                ):
                    for row in result.payload:
                        key = digest({"resource_key": row["id"].casefold()})
                        observation, _ = CollectionObservation.objects.get_or_create(
                            run=run,
                            observation_key=key,
                            defaults={
                                "scope_run": scope,
                                "resource_key": row["id"].casefold(),
                                "source_identifier": row["id"],
                                "source_subject_kind": "repository",
                                "listing": row,
                                "observed_at": observed_at,
                                "dimensions": {"kind": "creation_inventory"},
                            },
                        )
                        persist_product(observation, entry, rules, row, "listing")

                scoped = checkpoint_scope(
                    claim,
                    scope_kind="namespace",
                    scope_key=namespace,
                    ownership=entry,
                    cursor=result.next_cursor,
                    cursor_history=history,
                    envelopes=envelopes,
                    enumeration_complete=result.next_cursor is None,
                    outcome="complete" if result.next_cursor is None else "pending",
                    raw_count=(scoped.raw_count if scoped else 0) + len(result.payload),
                    write=write,
                )
                count += len(result.payload)
    finally:
        budget.remaining = before - client.requests
        budget.total_bytes_read += client.bytes_received
    return count


def execute_model_inventory(job_id, *, budget=None, key=None):
    job = CollectionJob.objects.get(pk=job_id)
    require(
        job.operation == "model_inventory" and job.source_id in {"hf", "openrouter"},
        "supported catalog inventory job required",
    )
    claim = claim_job(job_id)
    owned = None
    if budget is None:
        import httpx

        owned = httpx.Client(trust_env=False)
        limits = job.definition["budgets"]
        budget = Budget(
            owned,
            max_requests=limits["requests"],
            max_seconds=limits["seconds"],
            max_bytes=limits["bytes"],
        )
    limits = job.definition["budgets"]
    budget.remaining = min(budget.remaining, limits["requests"])
    budget.max_bytes = min(budget.max_bytes, limits["bytes"])
    budget.deadline = min(budget.deadline, budget.clock() + limits["seconds"])
    before = budget.remaining
    reason, items = None, 0
    try:
        items = (
            _hf(claim, job, budget)
            if job.source_id == "hf"
            else _openrouter(claim, job, budget, key)
        )
    except SourceError as exc:
        reason = str(exc)
    except (KeyError, ValueError, TypeError):
        reason = "invalid_or_unqualified_catalog"
    finally:
        if owned:
            owned.close()
    run = CollectionRun.objects.get(pk=claim.run_id)
    scopes = run.scopes.all()
    from django.db.models import Sum

    total_items = scopes.aggregate(items=Sum("raw_count"))["items"] or 0
    prior_items = run.report.get("total_committed_items", 0)
    items = total_items - prior_items
    if (
        job.source_id == "hf"
        and job.definition["scope"].get("hf_scope", {}).get("gaps")
        and reason is None
    ):
        reason = "inventory_scope_incomplete"
    return finish_run(
        claim,
        status="partial" if reason else "success",
        request_count=run.request_count + before - budget.remaining,
        selected_count=scopes.count(),
        success_count=scopes.filter(enumeration_complete=True).count(),
        error_code=reason,
        report={
            "stop_reason": reason,
            "items_this_invocation": items,
            "total_committed_items": total_items,
            "bytes_this_invocation": budget.total_bytes_read,
            "catalog_is_release_adjudication": False,
            "usage_mapping_inferred": False,
        },
    )
