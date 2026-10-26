"""Bounded native catalog observations precede reviewed crosswalk/cohort admission."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from django.utils import timezone

from core.collection_groups import record_observation_group
from core.collection_state import checkpoint_scope, claim_job, fenced_run, finish_run
from core.hf_catalog import _record_result, persist_product
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

OPENROUTER_CAPTURE = "openrouter-catalog-object-v1"
OPENROUTER_PHASE = "typed-openrouter-catalog-v1"


def validate_typed_scope(job, run, kind, key, ownership, observation):
    """OpenRouter inventory enumerates the sealed author selection only."""
    require(
        job.source_id == "openrouter"
        and job.purpose == "catalog"
        and job.operation == "model_inventory"
        and run.job_id == job.pk
        and kind == "model_catalog"
        and key == "models"
        and observation is None
        and ownership == {"authors": job.scope.get("authors", [])},
        "OpenRouter catalog scope differs from frozen selection",
    )


def openrouter_observation_documents(observation):
    """Select the native catalog object from its exact physical response."""
    from core.collection_capture import read_document

    scope = observation.scope_run
    require(
        observation.projection_kind == OPENROUTER_CAPTURE
        and observation.observation_kind == "model_catalog"
        and observation.source_subject_kind == "model"
        and scope is not None
        and scope.run_id == observation.run_id
        and scope.phase == OPENROUTER_PHASE,
        "typed OpenRouter catalog observation required",
    )
    job = observation.run.job
    validate_typed_scope(
        job,
        observation.run,
        scope.scope_kind,
        scope.scope_key,
        {"authors": job.scope.get("authors", [])},
        scope.resource_observation,
    )
    links = list(
        observation.inputs.filter(
            input_role="openrouter_catalog_object"
        ).select_related(
            "input_request__archive",
            "input_request__attempt",
        )
    )
    require(len(links) == 1, "one selected OpenRouter catalog response required")
    link = links[0]
    request = link.input_request
    require(
        request is not None
        and request.scope_run_id == scope.pk
        and request.attempt.run_id == observation.run_id
        and request.receipt_kind == "physical"
        and request.http_method == "GET"
        and request.transport_outcome == "received"
        and request.http_status == 200
        and request.error_code is None
        and request.request_group == "catalog_listing"
        and request.archive_id is not None
        and link.input_sha256 == request.archive.content_sha256,
        "OpenRouter catalog receipt ownership or checksum changed",
    )
    endpoint = urlsplit(request.endpoint_url)
    query = parse_qs(endpoint.query, strict_parsing=True)
    require(
        endpoint.scheme == "https"
        and endpoint.netloc == "openrouter.ai"
        and endpoint.path == "/api/v1/models"
        and not endpoint.fragment
        and set(query) <= {"offset", "limit", "model_authors"}
        and query.get("offset") == [request.cursor_before or "0"]
        and len(query.get("limit", [])) == 1
        and query["limit"][0].isascii()
        and query["limit"][0].isdecimal()
        and 1 <= int(query["limit"][0]) <= 500
        and query.get("model_authors", [])
        == ([",".join(job.scope["authors"])] if job.scope.get("authors") else []),
        "OpenRouter catalog request differs from frozen selection",
    )
    document = read_document(request.archive)
    rows = document.get("data") if isinstance(document, dict) else None
    position = link.row_locator
    require(
        isinstance(rows, list)
        and isinstance(position, str)
        and position.isascii()
        and position.isdecimal()
        and str(int(position)) == position
        and int(position) < len(rows),
        "OpenRouter catalog selected position changed",
    )
    raw = rows[int(position)]
    require(
        isinstance(raw, dict)
        and raw.get("id") == observation.source_identifier
        and digest(raw) == observation.payload_sha256,
        "OpenRouter catalog selected identity or payload changed",
    )
    return (
        raw,
        {"kind": "model_catalog"},
        {
            "listing_created_unix": raw.get("created"),
            "catalog_id": raw["id"],
            "canonical_slug": raw["canonical_slug"],
            "usage_mapping_verified": False,
            "projection_kind": OPENROUTER_CAPTURE,
        },
    )


def _openrouter_scope(claim, job):
    scoped = CollectionScopeRun.objects.filter(
        run_id=claim.run_id,
        scope_kind="model_catalog",
        scope_key="models",
    ).first()
    if scoped is not None:
        require(
            scoped.phase == OPENROUTER_PHASE,
            "OpenRouter catalog scope requires typed adoption before acquisition",
        )
        validate_typed_scope(
            job,
            scoped.run,
            scoped.scope_kind,
            scoped.scope_key,
            {"authors": job.scope.get("authors", [])},
            scoped.resource_observation,
        )
        return scoped

    def prepare(run, scope):
        scope.phase = OPENROUTER_PHASE
        scope.save(update_fields=["phase"])

    return checkpoint_scope(
        claim,
        scope_kind="model_catalog",
        scope_key="models",
        ownership={"authors": job.scope.get("authors", [])},
        typed=True,
        write=prepare,
    )


def _openrouter(claim, job, budget, key):
    from core.collection_capture import RequestCapture

    scoped = _openrouter_scope(claim, job)
    previous = budget.capture, budget.collection_scope
    budget.capture, budget.collection_scope = RequestCapture(claim), scoped
    try:
        return _openrouter_pages(claim, job, budget, key)
    finally:
        budget.capture, budget.collection_scope = previous


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
        budget.collection_scope = scoped
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
            from core.collection_capture import (
                RequestCapture,
                link_request,
                read_document,
            )
            from core.collection_resources import project_observation_facts
            from core.models import CollectionAttempt

            request = (
                scope.requests.filter(
                    attempt_id=claim.attempt_id,
                    transport_outcome="received",
                    http_status=200,
                )
                .select_related("archive")
                .order_by("-ordinal")
                .first()
            )
            require(
                request is not None
                and request.archive_id is not None
                and read_document(request.archive).get("data") == result["rows"],
                "OpenRouter page has no matching captured response",
            )
            request.request_group = "catalog_listing"
            request.save(update_fields=["request_group"])
            RequestCapture.response_metadata(
                request,
                cursor=str(result["next_offset"])
                if result["next_offset"] is not None
                else None,
            )
            for position, row in enumerate(result["rows"]):
                key = digest(
                    {"kind": "model_catalog", "native_id": row["id"], "payload": row}
                )
                observation, created = CollectionObservation.objects.get_or_create(
                    run=run,
                    observation_key=key,
                    defaults={
                        "scope_run": scope,
                        "resource_key": key,
                        "source_identifier": row["id"],
                        "source_subject_kind": "model",
                        "observed_at": observed_at,
                        "observation_kind": "model_catalog",
                        "projection_kind": OPENROUTER_CAPTURE,
                        "payload_sha256": digest(row),
                    },
                )
                if created:
                    link_request(
                        observation,
                        request,
                        role="openrouter_catalog_object",
                        row_locator=str(position),
                    )
                    project_observation_facts(observation)
                else:
                    require(
                        openrouter_observation_documents(observation)[0] == row,
                        "OpenRouter selected catalog object changed",
                    )
            attempt = CollectionAttempt.objects.select_for_update().get(
                pk=claim.attempt_id
            )
            attempt.actual_items += len(result["rows"])
            attempt.save(update_fields=["actual_items"])

        history = [*(scoped.recorded_cursors if scoped else []), str(offset)]
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
            typed=True,
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
                CollectionAttempt.objects.get(pk=claim.attempt_id),
                client.collection_scope,
                endpoint_url=str(
                    httpx.Request(
                        "GET", envelope["endpoint"], params=envelope["parameters"]
                    ).url
                ),
                cursor=client.collection_scope.cursor,
            )
            envelope["collection_request_id"] = str(request.pk)
            run.request_count += 1
            run.save(update_fields=["request_count", "updated_at"])

    client.on_attempt = record_attempt

    def record_result(envelope, body, response_bytes):
        from core.collection_capture import finish_request
        from core.models import CollectionRequest

        finish_request(
            CollectionRequest.objects.get(pk=envelope["collection_request_id"]),
            outcome="received"
            if envelope["http_status"] is not None
            else "transport_error",
            body=body,
            http_status=envelope["http_status"],
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
                scoped = _prepare_hf_scope(
                    claim,
                    job,
                    "namespace",
                    namespace,
                    entry,
                    scoped=scoped,
                )
                client.collection_scope = scoped
                remaining = job.budgets["items"] - count
                watch_exception = job.scope.get("watch_inventory") and entry[
                    "company"
                ].casefold() in {"google", "nvidia"}
                if watch_exception:
                    from django.db.models import Sum

                    already = (
                        CollectionScopeRun.objects.filter(
                            run_id=claim.run_id,
                            scope_kind="namespace",
                            scope_key__in=[
                                row["namespace"]
                                for row in frozen["namespaces"]
                                if row["company"] == entry["company"]
                            ],
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
                            typed=True,
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
                _record_result(claim, scoped, result, "listing")
                if result.outcome != "ok":
                    checkpoint_scope(
                        claim,
                        scope_kind="namespace",
                        scope_key=namespace,
                        ownership=entry,
                        cursor=scoped.cursor if scoped else None,
                        typed=True,
                        outcome=result.outcome,
                    )
                    raise SourceError(result.outcome)
                require(
                    len(result.payload) <= min(100, remaining),
                    "HF inventory provider exceeded item limit",
                )
                history = (
                    [
                        *(scoped.recorded_cursors if scoped else []),
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
                    for position, row in enumerate(result.payload):
                        key = digest({"resource_key": row["id"].casefold()})
                        observation, created = (
                            CollectionObservation.objects.get_or_create(
                                run=run,
                                observation_key=key,
                                defaults={
                                    "scope_run": scope,
                                    "resource_key": row["id"].casefold(),
                                    "source_identifier": row["id"],
                                    "source_subject_kind": "repository",
                                    "observed_at": observed_at,
                                    "observation_kind": "creation_inventory",
                                    "historical_visibility_proven": False,
                                },
                            )
                        )
                        previous = not baseline and (
                            CollectionObservation.objects.filter(
                                run__job=job,
                                run__status="success",
                                source_identifier=row["id"],
                                observation_kind="creation_inventory",
                            )
                            .exclude(run=run)
                            .exists()
                        )
                        if created:
                            from core.hf_inventory_capture import capture_object

                            capture_object(
                                observation,
                                result,
                                raw=row,
                                position=position,
                                metadata={
                                    "inventory_event": "baseline"
                                    if baseline
                                    else "known"
                                    if previous
                                    else "newly_observed"
                                },
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
                    from core.models import CollectionAttempt

                    attempt = CollectionAttempt.objects.select_for_update().get(
                        pk=claim.attempt_id
                    )
                    attempt.actual_items += len(result.payload)
                    attempt.save(update_fields=["actual_items"])
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
                    typed=True,
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
    claim = claim_job(job_id, typed=True)
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
    reason = None
    projection = None
    try:
        if job.scope.get("numeric_contract_id"):
            from core.source_metric_projection import drain_pending_projections

            projection = drain_pending_projections(
                job.pk, budget=budget, origin_claim=claim
            )
            if projection["pending"]:
                raise SourceError("numeric_projection_pending")
        if job.source_id == "hf":
            _hf(claim, job, budget)
        else:
            _openrouter(claim, job, budget, key)
    except SourceError as exc:
        reason = str(exc)
    except (KeyError, ValueError, TypeError) as exc:
        reason = "invalid_or_unqualified_catalog"
        if job.source_id != "hf":
            with fenced_run(claim) as (_, failed_run):
                marker = failed_run.scopes.get(
                    scope_kind="inventory_execution", scope_key="execution"
                )
                diagnostic = str(exc)
                marker.error_code = diagnostic if len(diagnostic) <= 64 else reason
                marker.save(update_fields=["error_code"])
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
        scope_kind__in=[
            "numeric_projection",
            "numeric_projection_item",
            "hf_metadata",
            "hf_profile",
            "resource_group",
            "inventory_execution",
        ]
    )
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
        typed=True,
        physical_accounting_complete=True,
        request_count=run.request_count
        if job.source_id == "hf"
        else run.request_count + before - budget.remaining,
        selected_count=scopes.count(),
        success_count=scopes.filter(enumeration_complete=True).count(),
        error_code=reason,
    )


def inventory_report(run):
    """Current inventory status from typed checkpoints and physical attempts."""
    from django.db.models import Sum

    job = run.job
    require(
        job.purpose == "catalog"
        and (
            job.source_id == "hf"
            and job.operation in {"hf_catalog", "model_inventory"}
            or job.source_id == "openrouter"
            and job.operation == "model_inventory"
        ),
        "inventory report owner required",
    )
    attempt = run.attempts.order_by("-ordinal").first()
    queues = run.scopes.filter(scope_kind="numeric_projection")
    projection = (
        {"pending": queues.exclude(outcome="complete").exists()}
        if job.scope.get("numeric_contract_id")
        else None
    )
    report = {
        "stop_reason": run.error_code,
        "numeric_projection": projection,
        "scope_coverage": [
            {**gap, "outcome": "unavailable"}
            for gap in job.scope.get("hf_scope", {}).get("gaps", [])
        ],
        "metadata_coverage": list(
            run.scopes.filter(scope_kind__in=["hf_metadata", "hf_profile"]).values(
                "scope_kind",
                "scope_key",
                "outcome",
                "enumeration_complete",
            )
        ),
        "physical_accounting_complete": attempt.accounting_complete
        if attempt
        else False,
        "missing_numeric_fields": _hf_missing_fields(run, job)
        if job.source_id == "hf"
        else [],
        "items_this_invocation": attempt.actual_items if attempt else None,
        "total_committed_items": run.scopes.filter(
            scope_kind="namespace" if job.source_id == "hf" else "model_catalog"
        ).aggregate(total=Sum("raw_count"))["total"]
        or 0,
        "bytes_this_invocation": attempt.actual_response_bytes if attempt else None,
        "catalog_is_release_adjudication": False,
        "usage_mapping_inferred": False,
    }

    if (
        job.source_id == "openrouter"
        and run.error_code == "invalid_or_unqualified_catalog"
    ):
        marker = run.scopes.filter(
            scope_kind="inventory_execution", scope_key="execution"
        ).first()
        if marker and marker.error_code:
            report["catalog_error"] = marker.error_code
    return report


def _prepare_hf_scope(
    claim, job, kind, key, ownership, *, scoped=None, resource_observation=None
):
    """Validate an existing typed parent before issuing metadata requests."""
    from core.collection_state import _validate_typed_hf_scope

    run = (
        scoped.run if scoped is not None else CollectionRun.objects.get(pk=claim.run_id)
    )
    _validate_typed_hf_scope(job, run, kind, key, ownership, resource_observation)
    if scoped is not None:
        require(
            scoped.run_id == claim.run_id
            and scoped.scope_kind == kind
            and scoped.scope_key == key
            and scoped.resource_observation_id
            == (resource_observation.pk if resource_observation else None),
            "HF inventory scope parent changed before acquisition",
        )
        if kind == "hf_metadata":
            require(
                scoped.phase in (None, key.rsplit(":", 1)[1]),
                "HF metadata group changed before acquisition",
            )
        return scoped
    return checkpoint_scope(
        claim,
        scope_kind=kind,
        scope_key=key,
        ownership=ownership,
        resource_observation=resource_observation,
        typed=True,
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
            client.collection_scope = _prepare_hf_scope(
                claim,
                job,
                "hf_metadata",
                listing.source_identifier + ":" + group,
                {
                    "namespace": entry["namespace"],
                    "repository": listing.source_identifier,
                },
                scoped=existing,
                resource_observation=listing,
            )
            result = client.model_group(listing.source_identifier, group)
            _record_result(claim, client.collection_scope, result, group)
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
                scope.phase = group
                scope.resource_observation = listing
                scope.save(update_fields=["phase", "resource_observation"])
                observation = CollectionObservation.objects.create(
                    run=run,
                    scope_run=scope,
                    resource_key=listing.resource_key,
                    source_identifier=listing.source_identifier,
                    source_subject_kind="repository",
                    observed_at=observed_at,
                    observation_key=digest([str(run.pk), listing.pk, group]),
                    observation_kind="hf_metadata",
                    historical_visibility_proven=False,
                )
                record_observation_group(observation, group, result.outcome)
                metadata = {}
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
                    metadata["file_changes"] = {
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
                from core.collection_capture import observation_object_documents
                from core.collection_numeric_selection import numeric_fields

                supplied = set(observation_object_documents(listing)[0])
                prior = CollectionObservation.objects.filter(
                    run=run,
                    source_identifier=listing.source_identifier,
                    observation_kind="hf_metadata",
                ).exclude(pk=observation.pk)
                for captured in prior:
                    supplied.update(numeric_fields(captured) or [])
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
                from core.hf_inventory_capture import capture_object

                capture_object(
                    observation,
                    result,
                    raw=result.payload,
                    fields=optional,
                    metadata=metadata,
                )
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
                resource_observation=listing,
                typed=True,
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
        client.collection_scope = _prepare_hf_scope(
            claim,
            job,
            "hf_profile",
            entry["namespace"],
            {"account_id": str(account.pk)},
            scoped=profile,
        )
        response = (
            client.account_counts(entry["namespace"], account.account_kind)
            if account.account_kind in {"organization", "individual"}
            else client.namespace_info(entry["namespace"])
        )
        _record_result(claim, client.collection_scope, response, "profile")
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
                observation_kind="hf_profile",
                observed_at=observed_at,
                observation_key=digest([str(run.pk), "profile", entry["namespace"]]),
            )
            from core.hf_inventory_capture import capture_object

            capture_object(observation, response, raw=response.payload)
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
            typed=True,
            write=profile_write,
        )
        partial |= response.outcome != "ok"
    if partial:
        raise SourceError("metadata_partial")


def _hf_missing_fields(run, job):
    """Explicit terminal gaps for optional selected fields absent from all groups."""
    from core.collection_capture import observation_object_documents
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
    for observation in run.observations.filter(status="ok").select_related(
        "legacy_archive"
    ):
        key = (observation.source_subject_kind, observation.source_identifier)
        groups.setdefault(key, set()).update(
            observation_object_documents(observation)[0]
        )
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
