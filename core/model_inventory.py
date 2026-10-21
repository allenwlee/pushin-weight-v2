"""Bounded native catalog observations precede reviewed crosswalk/cohort admission."""

from __future__ import annotations

from django.utils import timezone

from core.collection_state import checkpoint_scope, claim_job, fenced_run, finish_run
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
    from core.collection_capture import capture_budget

    with capture_budget(claim, budget, scope_kind="model_catalog", scope_key="models", ownership={"authors": job.scope.get("authors", [])}):
        return _openrouter_pages(claim, job, budget, key)


def _openrouter_pages(claim, job, budget, key):
    ownership = {"authors": job.scope.get("authors", [])}
    scoped = CollectionScopeRun.objects.filter(
        run_id=claim.run_id, scope_kind="model_catalog", scope_key="models"
    ).first()
    count = 0
    while scoped is None or not scoped.enumeration_complete:
        remaining = job.budgets["items"] - count
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
    frozen = job.scope["hf_scope"]
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

    def record_attempt(envelope):
        import httpx

        from core.collection_capture import begin_request
        from core.models import CollectionAttempt

        with fenced_run(claim) as (_, run):
            request = begin_request(
                CollectionAttempt.objects.get(pk=claim.attempt_id), client.collection_scope,
                endpoint_url=str(httpx.Request("GET", envelope["endpoint"], params=envelope["parameters"]).url),
                cursor=client.collection_scope.cursor,
            )
            envelope["collection_request_id"] = str(request.pk)
            run.request_count += 1
            run.report = {
                **run.report,
                "physical_accounting_complete": False,
                "last_physical_attempt": {
                    "endpoint": envelope["endpoint"],
                    "attempted_at": envelope["attempted_at"],
                    "outcome": "reserved_before_dispatch",
                },
            }
            run.save(update_fields=["request_count", "report", "updated_at"])

    client.on_attempt = record_attempt

    def record_result(envelope, body, response_bytes):
        from core.collection_capture import finish_request
        from core.models import CollectionRequest

        finish_request(
            CollectionRequest.objects.get(pk=envelope["collection_request_id"]),
            outcome="received" if envelope["http_status"] is not None else "transport_error",
            body=body, http_status=envelope["http_status"],
            error_code=None if envelope["outcome"] == "ok" else envelope["outcome"],
            response_bytes=response_bytes,
            body_encoding="decoded-body-v1",
        )

    client.on_result = record_result
    contract = None
    if job.scope.get("numeric_contract_id"):
        from core.models import MetricCollectionContract

        contract = MetricCollectionContract.objects.get(
            pk=job.scope["numeric_contract_id"]
        )
    try:
        for entry in frozen["namespaces"]:
            namespace = entry["namespace"]
            scoped = CollectionScopeRun.objects.filter(
                run_id=claim.run_id, scope_kind="namespace", scope_key=namespace
            ).first()
            while scoped is None or not scoped.enumeration_complete:
                if scoped is None:
                    scoped = checkpoint_scope(claim, scope_key=namespace, ownership=entry)
                client.collection_scope = scoped
                remaining = job.budgets["items"] - count
                watch_exception = job.scope.get(
                    "watch_inventory"
                ) and entry["company"].casefold() in {"google", "nvidia"}
                if watch_exception:
                    from django.db.models import Sum

                    already = (
                        CollectionScopeRun.objects.filter(
                            run_id=claim.run_id,
                            scope_kind="namespace",
                            ownership__company=entry["company"],
                        ).aggregate(total=Sum("raw_count"))["total"]
                        or 0
                    )
                    remaining = min(remaining, 100 - already)
                    if remaining <= 0:
                        checkpoint_scope(
                            claim,
                            scope_kind="namespace",
                            scope_key=namespace,
                            ownership=entry,
                            enumeration_complete=True,
                            outcome="watch_limit",
                            envelopes=scoped.envelopes if scoped else [],
                        )
                        break
                if remaining <= 0:
                    raise SourceError("item_cap")
                result = client.list_page(
                    namespace,
                    scoped.cursor if scoped else None,
                    limit=min(100, remaining),
                    sort="lastModified" if watch_exception else "createdAt",
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
                require(
                    len(result.payload) <= min(100, remaining),
                    "HF inventory provider exceeded item limit",
                )
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
                    numeric_ids = []
                    baseline = (
                        not CollectionRun.objects.filter(job=job, status="success")
                        .exclude(pk=run.pk)
                        .exists()
                    )
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
                        previous = not baseline and (
                            CollectionObservation.objects.filter(
                                run__job=job,
                                run__status="success",
                                source_identifier=row["id"],
                                dimensions__kind="creation_inventory",
                            )
                            .exclude(run=run)
                            .exists()
                        )
                        observation.source_metadata = {
                            **observation.source_metadata,
                            "inventory_event": "baseline"
                            if baseline
                            else "known"
                            if previous
                            else "newly_observed",
                            "historical_public_visibility_proven": False,
                        }
                        observation.save(
                            update_fields=["source_metadata", "updated_at"]
                        )
                        persist_product(observation, entry, rules, row, "listing")
                        if contract and any(
                            wire in row
                            and metric in contract.source_configuration["hf"]["metrics"]
                            for wire, metric in (
                                ("downloads", "downloads"),
                                ("downloadsAllTime", "downloads_all_time"),
                                ("likes", "likes"),
                                ("trendingScore", "trending_score"),
                            )
                        ):
                            numeric_ids.append(observation.pk)
                    if numeric_ids:
                        from core.source_metric_projection import enqueue_projection

                        enqueue_projection(
                            claim, contract=contract, evidence_ids=numeric_ids
                        )

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
            if job.scope.get("ingest_metadata"):
                _hf_metadata(claim, job, client, entry, rules, contract)
    finally:
        budget.remaining = before - client.requests
        budget.total_bytes_read += client.bytes_received
    return count


def execute_model_inventory(job_id, *, budget=None, key=None):
    job = CollectionJob.objects.get(pk=job_id)
    require(
        (job.operation == "model_inventory" and job.source_id in {"hf", "openrouter"})
        or (job.operation == "hf_catalog" and job.source_id == "hf"),
        "supported catalog inventory job required",
    )
    claim = claim_job(job_id)
    owned = None
    if budget is None:
        import httpx

        owned = httpx.Client(trust_env=False)
        limits = job.budgets
        budget = Budget(
            owned,
            max_requests=limits["requests"],
            max_seconds=limits["seconds"],
            max_bytes=limits["bytes"],
        )
    limits = job.budgets
    budget.cumulative = True
    budget.remaining = min(budget.remaining, limits["requests"])
    budget.max_bytes = min(budget.max_bytes, limits["bytes"])
    budget.deadline = min(budget.deadline, budget.clock() + limits["seconds"])
    before = budget.remaining
    reason, items = None, 0
    projection = None
    try:
        if job.scope.get("numeric_contract_id"):
            from core.source_metric_projection import drain_pending_projections

            projection = drain_pending_projections(
                job.pk, budget=budget, origin_claim=claim
            )
            if projection["pending"]:
                raise SourceError("numeric_projection_pending")
        items = (
            _hf(claim, job, budget)
            if job.source_id == "hf"
            else _openrouter(claim, job, budget, key)
        )
    except SourceError as exc:
        reason = str(exc)
    except (KeyError, ValueError, TypeError) as exc:
        reason = "invalid_or_unqualified_catalog"
        with fenced_run(claim) as (_, failed_run):
            failed_run.report = {**failed_run.report, "catalog_error": str(exc)}
            failed_run.save(update_fields=["report", "updated_at"])
    finally:
        if owned:
            owned.close()
    run = CollectionRun.objects.get(pk=claim.run_id)
    if job.scope.get("numeric_contract_id"):
        from core.source_metric_projection import drain_pending_projections

        try:
            projection = drain_pending_projections(
                job.pk, budget=budget, origin_claim=claim
            )
            if projection["pending"]:
                reason = reason or "numeric_projection_pending"
        except ValueError as exc:
            reason = "numeric_projection_failed"
            projection = {"pending": True, "error": str(exc)}
    run.refresh_from_db()
    scopes = run.scopes.exclude(
        scope_kind__in=["numeric_projection", "hf_metadata", "hf_profile"]
    )
    from django.db.models import Sum

    total_items = scopes.aggregate(items=Sum("raw_count"))["items"] or 0
    prior_items = run.report.get("total_committed_items", 0)
    items = total_items - prior_items
    if (
        job.source_id == "hf"
        and job.scope.get("hf_scope", {}).get("gaps")
        and reason is None
        and not job.scope.get("numeric_contract_id")
    ):
        reason = "inventory_scope_incomplete"
    return finish_run(
        claim,
        status="partial" if reason else "success",
        request_count=run.request_count
        if job.source_id == "hf"
        else run.request_count + before - budget.remaining,
        selected_count=scopes.count(),
        success_count=scopes.filter(enumeration_complete=True).count(),
        error_code=reason,
        report={
            "stop_reason": reason,
            "numeric_projection": projection,
            "scope_coverage": [
                {**gap, "outcome": "unavailable"}
                for gap in job.scope.get("hf_scope", {}).get("gaps", [])
            ],
            "metadata_coverage": list(
                run.scopes.filter(scope_kind__in=["hf_metadata", "hf_profile"]).values(
                    "scope_kind", "scope_key", "outcome", "enumeration_complete"
                )
            ),
            "physical_accounting_complete": True,
            "missing_numeric_fields": _hf_missing_fields(run, job)
            if job.source_id == "hf"
            else [],
            "items_this_invocation": items,
            "total_committed_items": total_items,
            "bytes_this_invocation": budget.total_bytes_read,
            "catalog_is_release_adjudication": False,
            "usage_mapping_inferred": False,
        },
    )


def _hf_metadata(claim, job, client, entry, rules, contract):
    """Enrich each saved listing once per run; counters keep their fetch clocks."""
    from core.models import Account, Product
    from core.source_metric_projection import enqueue_projection

    listings = CollectionObservation.objects.filter(
        run_id=claim.run_id,
        scope_run__scope_kind="namespace",
        scope_run__scope_key=entry["namespace"],
    ).order_by("pk")
    partial = False
    for listing in listings:
        for group in ("detail", "expanded"):
            existing = CollectionScopeRun.objects.filter(
                run_id=claim.run_id,
                scope_kind="hf_metadata",
                scope_key=listing.source_identifier + ":" + group,
            ).first()
            if existing and existing.enumeration_complete:
                continue
            client.collection_scope = existing or checkpoint_scope(
                claim, scope_kind="hf_metadata",
                scope_key=listing.source_identifier + ":" + group,
                ownership={"namespace": entry["namespace"], "repository": listing.source_identifier},
            )
            result = client.model_group(listing.source_identifier, group)
            observed_at = timezone.now()
            accepted = result.outcome in {"ok", "partial_expansion"}

            def write(
                run,
                scope,
                result=result,
                group=group,
                listing=listing,
                observed_at=observed_at,
                accepted=accepted,
            ):
                if not accepted:
                    return
                previous = (
                    Product.objects.get(pk=listing.product_id).siblings
                    if listing.product_id
                    else None
                )
                observation = CollectionObservation.objects.create(
                    run=run,
                    scope_run=scope,
                    resource_key=listing.resource_key,
                    source_identifier=listing.source_identifier,
                    source_subject_kind="repository",
                    listing=result.payload,
                    observed_at=observed_at,
                    observation_key=digest([str(run.pk), listing.pk, group]),
                    envelopes=_envelopes(result, group),
                    groups={group: result.outcome},
                    dimensions={"kind": "hf_metadata", "group": group},
                    source_metadata={"historical_public_visibility_proven": False},
                )
                if group == "detail" and "siblings" in result.payload:
                    paths = lambda rows: {
                        r.get("rfilename"): r.get("blobId")
                        or r.get("lfs", {}).get("oid")
                        for r in (rows or [])
                        if isinstance(r, dict)
                    }
                    old, new = paths(previous), paths(result.payload["siblings"])
                    changed = sorted(
                        path
                        for path in set(old) | set(new)
                        if path not in old or path not in new or old[path] != new[path]
                    )
                    observation.source_metadata["file_changes"] = {
                        "changed_paths": changed,
                        "kind": "baseline"
                        if previous is None
                        else "weights"
                        if any(
                            p.endswith((".safetensors", ".bin", ".gguf", ".pt", ".pth"))
                            for p in changed
                        )
                        else "setup_or_readme"
                        if changed
                        else "unchanged",
                        "comparison_basis": "file_paths_and_supplied_hashes",
                        "weight_binaries_downloaded": False,
                    }
                # Listing owns rolling counters. An optional fresh field uses the
                # first detail/expanded response actually supplying it, never an
                # old listing clock or a duplicate complete model-number set.
                supplied = set(listing.listing)
                prior = CollectionObservation.objects.filter(
                    run=run,
                    source_identifier=listing.source_identifier,
                    dimensions__kind="hf_metadata",
                ).exclude(pk=observation.pk)
                for captured in prior:
                    supplied.update(captured.source_metadata.get("numeric_fields", []))
                selected_metrics = (
                    contract.source_configuration["hf"]["metrics"] if contract else []
                )
                optional = [
                    wire
                    for wire, metric in (
                        ("downloads", "downloads"),
                        ("likes", "likes"),
                        ("downloadsAllTime", "downloads_all_time"),
                        ("trendingScore", "trending_score"),
                    )
                    if wire in result.payload
                    and wire not in supplied
                    and metric in selected_metrics
                ]
                observation.source_metadata["numeric_fields"] = optional
                observation.save(update_fields=["source_metadata", "updated_at"])
                persist_product(observation, entry, rules, result.payload, group)
                if contract and optional:
                    enqueue_projection(
                        claim, contract=contract, evidence_ids=[observation.pk]
                    )

            checkpoint_scope(
                claim,
                scope_kind="hf_metadata",
                scope_key=listing.source_identifier + ":" + group,
                ownership={
                    "namespace": entry["namespace"],
                    "repository": listing.source_identifier,
                },
                enumeration_complete=accepted,
                outcome=result.outcome,
                envelopes=_envelopes(result, group),
                write=write,
            )
            if not accepted:
                partial = True
                if client.stop_reason:
                    raise SourceError(client.stop_reason)
    profile = CollectionScopeRun.objects.filter(
        run_id=claim.run_id, scope_kind="hf_profile", scope_key=entry["namespace"]
    ).first()
    if profile is None or not profile.enumeration_complete:
        account = Account.objects.get(
            data_source_id="hf", normalized_identifier=entry["namespace"].casefold()
        )
        client.collection_scope = profile or checkpoint_scope(
            claim, scope_kind="hf_profile", scope_key=entry["namespace"],
            ownership={"account_id": str(account.pk)},
        )
        response = (
            client.account_counts(entry["namespace"], account.account_kind)
            if account.account_kind in {"organization", "individual"}
            else client.namespace_info(entry["namespace"])
        )
        observed_at = timezone.now()

        def profile_write(run, scope):
            if response.outcome != "ok":
                return
            observation = CollectionObservation.objects.create(
                run=run,
                scope_run=scope,
                resource_key=entry["namespace"].casefold(),
                source_subject_kind="account",
                source_identifier=entry["namespace"],
                listing=response.payload,
                observed_at=observed_at,
                observation_key=digest([str(run.pk), "profile", entry["namespace"]]),
                envelopes=_envelopes(response, "profile"),
            )
            from core.account_identity import upsert_account

            current = Account.objects.select_for_update().get(pk=account.pk)
            metadata = dict(current.provider_metadata)
            metadata["hf_profile"] = {
                **metadata.get("hf_profile", {}),
                **response.payload,
            }
            metadata["hf_profile_observation"] = {
                "id": observation.pk,
                "observed_at": observed_at.isoformat(),
            }
            upsert_account(
                source="hf",
                external_identifier=current.external_identifier,
                handle=current.handle,
                account_kind=current.account_kind,
                provider_metadata=metadata,
            )
            if contract and any(
                wire in response.payload
                and metric in contract.source_configuration["hf"]["metrics"]
                for wire, metric in (
                    ("numFollowers", "followers"),
                    ("numModels", "models_count"),
                    ("numDatasets", "datasets_count"),
                    ("numSpaces", "spaces_count"),
                )
            ):
                enqueue_projection(
                    claim, contract=contract, evidence_ids=[observation.pk]
                )

        checkpoint_scope(
            claim,
            scope_kind="hf_profile",
            scope_key=entry["namespace"],
            ownership={"account_id": str(account.pk)},
            enumeration_complete=response.outcome == "ok",
            outcome=response.outcome,
            envelopes=_envelopes(response, "profile"),
            write=profile_write,
        )
        partial |= response.outcome != "ok"
    if partial:
        raise SourceError("metadata_partial")


def _hf_missing_fields(run, job):
    """Explicit terminal gaps for optional selected fields absent from all groups."""
    from core.models import MetricCollectionContract

    contract_id = job.scope.get("numeric_contract_id")
    if not contract_id:
        return []
    contract = MetricCollectionContract.objects.get(pk=contract_id)
    metrics = contract.source_configuration["hf"]["metrics"]
    repository_fields = {
        "downloads": "downloads",
        "downloads_all_time": "downloadsAllTime",
        "likes": "likes",
        "trending_score": "trendingScore",
    }
    account_fields = {
        "followers": "numFollowers",
        "models_count": "numModels",
        "datasets_count": "numDatasets",
        "spaces_count": "numSpaces",
    }
    groups = {}
    for observation in run.observations.filter(status="ok"):
        key = (observation.source_subject_kind, observation.source_identifier)
        groups.setdefault(key, set()).update(observation.listing)
    result = []
    for (kind, identity), returned in groups.items():
        for metric, wire in (
            account_fields if kind == "account" else repository_fields
        ).items():
            if metric in metrics and wire not in returned:
                result.append(
                    {
                        "source": "hf",
                        "source_identifier": identity,
                        "metric": metric,
                        "outcome": "not_returned",
                        "reason": "selected_field_absent_from_captured_groups",
                    }
                )
    return result
