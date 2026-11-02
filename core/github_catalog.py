"""Checkpoint public GitHub evidence without interpreting model release dates."""

from __future__ import annotations

from dataclasses import replace

from core.benchmark_metric_identity import SOURCE_STATISTICS_POLICY
from core.benchmark_metric_store import aware_instant, safe_payload
from core.collection_capture import observation_object_documents
from core.collection_jobs import register_job
from core.collection_state import checkpoint_scope as shared_checkpoint_scope
from core.collection_state import claim_job, fenced_run, finish_run
from core.github_metadata_client import METADATA_FILES, GitHubMetadataClient
from core.measurement_taxonomy import digest, require
from core.models import (
    Account,
    CollectionJob,
    CollectionObservation,
    CollectionObservationInput,
    CollectionRequest,
    CollectionRun,
    CollectionScopeRun,
    DataSource,
)
from scripts.benchmark_download_collector.sources import Budget, SourceError

CAPTURE_KIND = "github-catalog-object-v1"
SCOPE_PHASE = "typed-github-catalog-v1"


def validate_typed_scope(job, run, kind, key, ownership, observation):
    """Validate each scope against its frozen publisher and captured parent."""
    require(
        job.source_id == "github"
        and job.purpose == "catalog"
        and job.operation == "github_catalog"
        and run.job_id == job.pk,
        "GitHub catalog scope required",
    )
    pins = job.scope["publishers"]
    if kind in {"publisher", "publisher_repos"}:
        require(
            observation is None
            and any(key == pin["native_id"] and ownership == pin for pin in pins),
            "frozen publisher scope required",
        )
        return
    require(
        observation is not None and observation.run_id == run.pk,
        "GitHub scope needs an owned resource observation",
    )
    snapshot = observation.resource_snapshot
    account = snapshot.publisher_account
    require(
        account is not None
        and account.data_source_id == "github"
        and snapshot.native_identifier == observation.source_identifier
        and snapshot.resource_kind == observation.observation_kind
        and any(
            str(account.pk) == pin["account_key"]
            and account.normalized_identifier == pin["native_id"]
            for pin in pins
        ),
        "captured publisher differs from the frozen publisher",
    )
    repository_id = int(observation.source_identifier)
    owner_id = int(account.normalized_identifier)
    if kind == "repository_access":
        expected = {"repository_id": str(repository_id), "owner_id": str(owner_id)}
        valid = observation.observation_kind == "repository" and key == str(
            repository_id
        )
    elif kind == "repository_events":
        expected = {"repository_id": repository_id, "owner_id": owner_id}
        valid = observation.observation_kind == "repository" and key in {
            f"{repository_id}:{event}" for event in ("releases", "tags", "commits")
        }
    elif kind == "release_assets":
        release_id = int(snapshot.native_stable_id)
        expected = {
            "repository_id": repository_id,
            "release_id": release_id,
            "owner_id": owner_id,
        }
        valid = (
            observation.observation_kind == "releases"
            and key == f"{repository_id}:{release_id}"
        )
    elif kind in {"repository_tree", "repository_file"}:
        expected = {
            "repository_id": repository_id,
            "revision": snapshot.revision,
            "tree_revision": snapshot.tree_revision,
        }
        prefix = f"{repository_id}:{snapshot.revision}"
        valid = observation.observation_kind == "commits" and (
            key == prefix
            if kind == "repository_tree"
            else key in {f"{prefix}:{filename}" for filename in METADATA_FILES}
        )
    else:
        raise ValueError("unsupported GitHub catalog scope")
    require(
        valid
        and ownership == expected
        and all(
            type(ownership[name]) is type(value) for name, value in expected.items()
        ),
        "GitHub scope ownership changed",
    )


def checkpoint_scope(claim, *, resource_observation=None, write=None, **kwargs):
    """Save parent coordinates with the fenced typed checkpoint."""
    current = _scope(claim, kwargs["scope_kind"], kwargs["scope_key"])
    if resource_observation is None and current is not None:
        resource_observation = current.resource_observation

    def save(run, scope):
        scope.phase = SCOPE_PHASE
        fields = ["phase"]
        if scope.scope_kind in {"repository_tree", "repository_file"}:
            scope.requested_revision = kwargs["ownership"]["revision"]
            fields.append("requested_revision")
            if scope.scope_kind == "repository_file":
                scope.resource_path = scope.scope_key.split(":", 2)[2]
                fields.append("resource_path")
        scope.save(update_fields=fields)
        if write is not None:
            write(run, scope)

    return shared_checkpoint_scope(
        claim,
        resource_observation=resource_observation,
        typed=True,
        write=save,
        **kwargs,
    )


def _documents(
    payload, kind, *, coordinate=None, reused_from=None, dimensions=None, metadata=None
):
    clocks = {}
    if kind in {"repository", "repository_access"}:
        clocks = {
            "repository_created_at": payload.get("created_at"),
            "repository_updated_at": payload.get("updated_at"),
        }
    elif kind == "releases":
        clocks = {
            "release_created_at": payload.get("created_at"),
            "release_published_at": payload.get("published_at"),
            "release_updated_at": payload.get("updated_at"),
        }
    elif kind == "commits":
        commit = payload.get("commit", {})
        clocks = {
            "author_at": commit.get("author", {}).get("date"),
            "committer_at": commit.get("committer", {}).get("date"),
        }
    elif kind == "release_asset":
        clocks = {
            "asset_created_at": payload.get("created_at"),
            "asset_updated_at": payload.get("updated_at"),
        }
    return (
        payload,
        {"kind": kind, "coordinate": coordinate, **(dimensions or {})},
        {
            "clocks": clocks,
            "reused_from": reused_from,
            "projection_kind": CAPTURE_KIND,
            **(metadata or {}),
        },
    )


def observation_documents(observation):
    """Resolve the selected public object from immutable receipts, never old JSON."""
    from core.collection_capture import read_document

    require(
        observation.projection_kind == CAPTURE_KIND
        and observation.run.job.source_id == "github"
        and observation.run.job.purpose == "catalog"
        and observation.run.job.operation in {"github_catalog", "model_history"},
        "typed GitHub capture required",
    )
    selected, reused = observation, None
    while True:
        direct = list(
            selected.inputs.filter(input_role="github_source_object").select_related(
                "input_request__archive",
                "input_request__attempt",
            )
        )
        cached = list(
            selected.inputs.filter(input_role="cached_response").select_related(
                "input_observation__run",
            )
        )
        require(
            len(direct) + len(cached) == 1, "one selected GitHub source object required"
        )
        if direct:
            edge = direct[0]
            request = edge.input_request
            require(
                request is not None
                and request.attempt.run_id == selected.run_id
                and request.scope_run_id == selected.scope_run_id
                and request.transport_outcome == "received"
                and request.http_status == 200
                and request.archive_id is not None
                and edge.input_sha256 == request.archive.content_sha256,
                "GitHub source receipt ownership or checksum changed",
            )
            payload = read_document(request.archive)
            if isinstance(payload, list):
                require(
                    edge.row_locator is not None
                    and edge.row_locator.isascii()
                    and edge.row_locator.isdecimal(),
                    "GitHub page row locator required",
                )
                position = int(edge.row_locator)
                require(position < len(payload), "GitHub page row is absent")
                payload = payload[position]
            else:
                require(
                    edge.row_locator is None, "GitHub object cannot have a page locator"
                )
            break
        edge = cached[0]
        prior = edge.input_observation
        require(
            prior is not None
            and prior.run.job_id == selected.run.job_id
            and prior.pk < selected.pk
            and prior.observation_kind == selected.observation_kind == "repository"
            and prior.source_identifier == selected.source_identifier
            and prior.observed_at == selected.observed_at
            and edge.input_sha256 == prior.payload_sha256 == selected.payload_sha256,
            "cached GitHub object ownership or checksum changed",
        )
        validations = list(
            selected.inputs.filter(input_role="cache_validation").select_related(
                "input_request__attempt"
            )
        )
        require(len(validations) == 1, "GitHub cache validation receipt required")
        validation = validations[0].input_request
        require(
            validation is not None
            and validation.attempt.run_id == selected.run_id
            and validation.scope_run_id == selected.scope_run_id
            and validation.transport_outcome == "received"
            and validation.http_status == 304
            and validation.archive_id is None,
            "GitHub cache validation receipt required",
        )
        if reused is None:
            reused = {
                "run_id": str(prior.run_id),
                "scope_id": prior.scope_run_id,
                "observed_at": prior.observed_at.isoformat(),
            }
        if prior.projection_kind != CAPTURE_KIND:
            payload = observation_object_documents(prior)[0]
            break
        selected = prior
    require(
        isinstance(payload, dict) and digest(payload) == observation.payload_sha256,
        "GitHub selected payload changed",
    )
    kind = observation.observation_kind
    coordinate, dimensions, metadata = None, {}, {}
    parent = observation.scope_run.resource_observation
    if parent is not None:
        publisher = parent.resource_snapshot.publisher_account
        require(publisher is not None, "GitHub parent publisher is missing")
        metadata["owner_id"] = int(publisher.normalized_identifier)
    require(
        observation.source_subject_kind
        == ("account" if kind == "publisher" else "repository"),
        "GitHub selected subject kind changed",
    )
    if kind in {"publisher", "repository", "repository_access"}:
        require(
            str(payload.get("id")) == observation.source_identifier,
            "GitHub selected native identity changed",
        )
    if parent is not None:
        require(
            parent.run_id == observation.run_id
            and parent.source_identifier == observation.source_identifier,
            "GitHub parent repository changed",
        )
    if kind == "releases":
        coordinate = payload["id"]
    elif kind == "commits":
        coordinate = payload["sha"]
    elif kind == "tags":
        coordinate = {"name": payload["name"], "sha": payload["commit"]["sha"]}
    elif kind in {"tree", "file"}:
        revision = observation.scope_run.requested_revision
        require(
            parent is not None
            and parent.observation_kind == "commits"
            and revision
            == observation.provider_revision
            == parent.resource_snapshot.revision,
            "GitHub requested revision changed",
        )
        if kind == "tree":
            require(
                payload.get("sha") == parent.resource_snapshot.tree_revision,
                "GitHub captured tree revision changed",
            )
        else:
            require(
                observation.scope_run.resource_path in METADATA_FILES,
                "GitHub captured metadata path changed",
            )
        coordinate = (
            revision
            if kind == "tree"
            else {"revision": revision, "filename": observation.scope_run.resource_path}
        )
        metadata["revision"] = revision
    elif kind == "release_asset":
        parent = observation.scope_run.resource_observation
        edge = observation.inputs.get(input_role="release_asset_parent")
        require(
            parent is not None
            and edge.input_observation_id == parent.pk
            and parent.source_identifier == observation.source_identifier
            and edge.input_sha256 == parent.observation_key,
            "GitHub asset parent changed",
        )
        release_id = int(parent.resource_snapshot.native_stable_id)
        require(
            edge.row_locator == str(release_id),
            "GitHub asset release coordinate changed",
        )
        dimensions = {"release_id": release_id, "asset_id": payload["id"]}
        coordinate = dimensions
        metadata = {
            "repository_id": int(observation.source_identifier),
            "owner_id": int(
                parent.resource_snapshot.publisher_account.normalized_identifier
            ),
        }
    return _documents(
        payload,
        kind,
        coordinate=coordinate,
        reused_from=reused,
        dimensions=dimensions,
        metadata=metadata,
    )


def catalog_report(run):
    """Build the operator report from scope, attempt and projection results."""
    scopes = run.scopes.exclude(
        scope_kind__in={"numeric_projection_item", "catalog_execution", "release_detection"}
    )
    attempt = run.attempts.order_by("-ordinal").first()
    projection = None
    if run.job.scope.get("numeric_contract_id"):
        from core.source_metric_projection import projection_report

        queues = CollectionScopeRun.objects.filter(
            run__job=run.job, scope_kind="numeric_projection"
        )
        results = (
            CollectionRun.objects.filter(
                scopes__scope_kind="numeric_projection_result",
                scopes__resource_observation__run__job=run.job,
                started_at__gte=attempt.started_at,
            )
            .distinct()
            .order_by("started_at", "pk")
            if attempt
            else CollectionRun.objects.none()
        )
        if attempt and attempt.finished_at:
            results = results.filter(started_at__lte=attempt.finished_at)
            queues = queues.filter(run__started_at__lte=attempt.finished_at)
        reports = [(row, projection_report(row)) for row in results]
        projection = {
            "written_values": sum(report["written_values"] for _, report in reports),
            "reused_resources": sum(
                len(report["reused_observation_ids"]) for _, report in reports
            ),
            "acknowledged": sum(
                row.scopes.filter(scope_kind="numeric_projection_result")
                .exclude(outcome="rejected")
                .count()
                for row, _ in reports
            ),
            "runs": [str(row.pk) for row, _ in reports],
            "pending": queues.filter(outcome="pending").exists(),
            "pending_resources": CollectionScopeRun.objects.filter(
                parent_scope__in=queues,
                scope_kind="numeric_projection_item",
                outcome="pending",
            ).count(),
        }
    return {
        "operation": "github_catalog",
        "stop_reason": run.error_code,
        "items_this_invocation": attempt.actual_items if attempt else None,
        "bytes_this_invocation": attempt.actual_response_bytes if attempt else None,
        "api_version": "2026-03-10",
        "native_clocks_are_release_leads": True,
        "numeric_projection": projection,
        "physical_accounting_complete": attempt.accounting_complete
        if attempt
        else False,
        "inaccessible_repositories": list(
            scopes.filter(scope_kind="repository_access", outcome="inaccessible")
            .order_by("pk")
            .values_list("scope_key", flat=True)
        ),
        "inventory_complete": dict(
            scopes.filter(scope_kind="publisher_repos").values_list(
                "scope_key", "enumeration_complete"
            )
        ),
    }


class CollectionStop(SourceError):
    def __init__(self, code, retry_at=None):
        super().__init__(code)
        self.retry_at = retry_at


def register_github_source():
    """Registration supplies no activation or provider calls."""
    return DataSource.objects.get_or_create(
        pk="github",
        defaults={
            "name": "GitHub",
            "source_type": "model_adoption",
            "website_url": "https://github.com",
            "adapter_key": "github-catalog-v1",
            "identifier_normalizer": "exact-v1",
        },
    )[0]


def register_github_job(
    *,
    job_key,
    publisher_ids,
    budgets,
    mode="recurring",
    schedule=None,
    github_role="inventory",
    numeric_contract_id=None,
):
    require(
        github_role in {"inventory", "release_watch", "full"}, "unsupported GitHub role"
    )
    register_github_source()
    publishers = []
    for key in publisher_ids:
        account = Account.objects.get(pk=key, data_source_id="github")
        require(
            account.account_kind in {"organization", "individual"},
            "reviewed publisher kind required",
        )
        require(
            account.brands.filter(role_id="official").exists()
            or account.companies.filter(role_id="official").exists(),
            "reviewed official publisher required",
        )
        publishers.append(
            {
                "account_key": str(account.pk),
                "native_id": account.normalized_identifier,
                "login": account.handle,
                "account_kind": account.account_kind,
            }
        )
    require(publishers, "at least one reviewed publisher required")
    require(len(publishers) == 1, "register one GitHub account per collection job")
    from core.collection_publisher_jobs import publisher_job_spec

    return register_job(
        **publisher_job_spec(
            job_key=job_key,
            account=account,
            budgets=budgets,
            mode=mode,
            schedule=schedule,
            options={"github_role": github_role},
            numeric_contract_id=numeric_contract_id,
        )
    )


def _record(
    run,
    scope,
    identifier,
    kind,
    payload,
    *,
    observed_at,
    request_id,
    coordinate=None,
    reused_from=None,
    dimensions=None,
    metadata=None,
):
    from core.collection_capture import link_request, read_document
    from core.collection_resources import (
        observation_fact_values,
        project_observation_facts,
    )

    safe_payload(payload)
    metadata = dict(metadata or {})
    if kind in {"tree", "file"}:
        metadata["revision"] = scope.requested_revision
    documents = _documents(
        payload,
        kind,
        coordinate=coordinate,
        reused_from=reused_from,
        dimensions=dimensions,
        metadata=metadata,
    )
    resource = (
        f"{identifier}:{kind}:{digest({'coordinate': coordinate, 'payload': payload})}"
    )
    published_at = (
        aware_instant(payload["published_at"])
        if kind == "releases" and payload.get("published_at")
        else None
    )
    draft = CollectionObservation(
        run=run, scope_run=scope, source_identifier=str(identifier)
    )
    observation, _ = CollectionObservation.objects.get_or_create(
        run=run,
        observation_key=digest({"resource_key": resource}),
        defaults={
            "scope_run": scope,
            "resource_key": resource,
            "source_identifier": str(identifier),
            "source_subject_kind": "account" if kind == "publisher" else "repository",
            "observed_at": observed_at,
            "published_at": published_at,
            "publication_precision": "instant" if published_at else "unknown",
            **observation_fact_values(draft, documents=documents),
        },
    )
    require(
        observation.scope_run_id == scope.pk
        and observation.payload_sha256 == digest(payload),
        "GitHub capture identity changed",
    )
    request = CollectionRequest.objects.select_related("archive").get(
        pk=request_id, scope_run=scope
    )
    if reused_from:
        require(
            request.http_status == 304 and kind == "repository",
            "cached inventory validation required",
        )
        prior = CollectionObservation.objects.get(
            scope_run_id=reused_from["scope_id"],
            run_id=reused_from["run_id"],
            source_identifier=str(identifier),
            observation_kind="repository",
            observed_at=observed_at,
            payload_sha256=digest(payload),
        )
        require(
            observation_object_documents(prior)[0] == payload,
            "cached repository payload changed",
        )
        edge, _ = CollectionObservationInput.objects.get_or_create(
            observation=observation,
            input_observation=prior,
            input_role="cached_response",
            defaults={"input_sha256": prior.payload_sha256},
        )
        require(
            edge.input_sha256 == prior.payload_sha256,
            "cached repository checksum changed",
        )
        CollectionObservationInput.objects.get_or_create(
            observation=observation,
            input_request=request,
            input_role="cache_validation",
        )
    else:
        require(
            request.http_status == 200 and request.archive_id is not None,
            "public source body required",
        )
        body = read_document(request.archive)
        locator = (
            str(body.index(payload))
            if isinstance(body, list) and payload in body
            else None
        )
        require(
            body == payload or locator is not None,
            "selected GitHub object absent from response",
        )
        # Identical repeated objects keep the first selected immutable receipt.
        existing = observation.inputs.filter(input_role="github_source_object").first()
        if existing is None:
            link_request(
                observation, request, role="github_source_object", row_locator=locator
            )
    if kind == "release_asset":
        parent = scope.resource_observation
        require(
            parent is not None and parent.observation_kind == "releases",
            "release asset parent required",
        )
        CollectionObservationInput.objects.get_or_create(
            observation=observation,
            input_observation=parent,
            input_role="release_asset_parent",
            defaults={
                "row_locator": str(parent.resource_snapshot.native_stable_id),
                "input_sha256": parent.observation_key,
            },
        )
    project_observation_facts(observation)
    if kind == "releases" and payload.get("draft") is False and payload.get("published_at"):
        from django.conf import settings

        if settings.PRODUCT_RELEASE_BACKGROUND_ENABLED:
            from core.product_release_source_queue import enqueue_github_release

            enqueue_github_release(observation, captured_row=payload)
    return observation


def _queue_numeric(claim, run, observations):
    """Queue the exact captured payloads inside their fenced evidence transaction."""
    contract_id = run.job.scope.get("numeric_contract_id")
    if not contract_id:
        return
    from core.models import MetricCollectionContract
    from core.source_metric_projection import enqueue_projection

    contract = MetricCollectionContract.objects.get(pk=contract_id)
    config = contract.source_configuration["github"]
    require(
        config.get("eligibility_policy") == SOURCE_STATISTICS_POLICY,
        "statistics contract required",
    )
    wires = {d["definition_metadata"].get("wire_field") for d in config["definitions"]}
    ids = []
    for observation in observations:
        payload = observation_object_documents(observation)[0]
        if any(wire in payload for wire in wires if wire):
            ids.append(observation.pk)
    if ids:
        enqueue_projection(claim, contract=contract, evidence_ids=ids)


def _scope(claim, kind, key):
    return CollectionScopeRun.objects.filter(
        run_id=claim.run_id, scope_kind=kind, scope_key=key
    ).first()


def _prepare_capture(
    claim, client, kind, key, ownership, scoped=None, *, resource_observation=None
):
    if scoped is not None:
        require(
            scoped.run_id == claim.run_id
            and scoped.scope_kind == kind
            and scoped.scope_key == key
            and scoped.phase == SCOPE_PHASE,
            "GitHub scope requires typed adoption before acquisition",
        )
        require(
            scoped.resource_observation_id
            == (resource_observation.pk if resource_observation is not None else None),
            "GitHub scope parent changed before acquisition",
        )
        if kind in {"repository_tree", "repository_file"}:
            require(
                scoped.requested_revision == ownership["revision"],
                "GitHub pinned revision changed before acquisition",
            )
            if kind == "repository_file":
                require(
                    scoped.resource_path == key.split(":", 2)[2],
                    "GitHub metadata path changed before acquisition",
                )
    scoped = scoped or checkpoint_scope(
        claim,
        scope_kind=kind,
        scope_key=key,
        ownership=ownership,
        resource_observation=resource_observation,
    )
    client.collection_scope = scoped
    return scoped


def _checked_response(claim, result, *, kind, key, ownership, scope):
    if result.status in {200, 304}:
        return
    checkpoint_scope(
        claim,
        scope_kind=kind,
        scope_key=key,
        ownership=ownership,
        cursor=scope.cursor if scope else None,
        cursor_history=scope.recorded_cursors if scope else [],
        outcome=f"http_{result.status}",
    )
    raise CollectionStop(f"http_{result.status}", result.retry_at)


def _cached_inventory_page(previous, cursor):
    """Read the previous actual response through its typed receipt/input links."""
    from core.collection_capture import read_document

    receipt = (
        previous.requests.filter(
            cursor_before=cursor,
            transport_outcome="received",
            http_status__in=[200, 304],
            error_code__isnull=True,
        )
        .select_related("archive")
        .order_by("-attempt__ordinal", "-ordinal")
        .first()
    )
    if receipt is None:
        return None
    body_request = receipt if receipt.archive_id else None
    resource = (
        previous.observations.filter(
            inputs__input_request=receipt,
        )
        .order_by("pk")
        .first()
    )
    observed_at = resource.observed_at if resource else receipt.received_at
    # A 304 has no response body. Follow earlier resource results to the actual
    # public body rather than copying it into the new transport receipt.
    seen = set()
    while body_request is None and resource and resource.pk not in seen:
        seen.add(resource.pk)
        body_edge = (
            resource.inputs.filter(
                input_request__archive__isnull=False,
                input_request__endpoint_url=receipt.endpoint_url,
            )
            .select_related("input_request__archive")
            .first()
        )
        if body_edge:
            body_request = body_edge.input_request
            break
        earlier = (
            resource.inputs.filter(input_role="cached_response")
            .select_related("input_observation")
            .first()
        )
        resource = earlier.input_observation if earlier else None
    if body_request is None:
        return None
    payload = read_document(body_request.archive)
    require(isinstance(payload, list), "cached repository listing required")
    return {
        "url": receipt.endpoint_url,
        "payload": payload,
        "next_url": body_request.cursor_after,
        "etag": receipt.response_etag or receipt.etag,
        "observed_at": observed_at.isoformat(),
    }


def _publisher_inventory(claim, client, pin, items):
    account = Account.objects.get(pk=pin["account_key"], data_source_id="github")
    require(
        account.normalized_identifier == pin["native_id"]
        and account.account_kind == pin["account_kind"],
        "publisher pin changed",
    )
    require(
        account.brands.filter(role_id="official").exists()
        or account.companies.filter(role_id="official").exists(),
        "official ownership no longer admitted",
    )
    key = pin["native_id"]
    profile = _scope(claim, "publisher", key)
    if profile is None or not profile.enumeration_complete:
        profile = _prepare_capture(claim, client, "publisher", key, pin, profile)
        result = client.owner(pin["login"])
        _checked_response(
            claim, result, kind="publisher", key=key, ownership=pin, scope=profile
        )
        require(
            isinstance(result.payload, dict) and str(result.payload.get("id")) == key,
            "native publisher identity mismatch",
        )
        require(
            result.payload.get("type")
            == ("Organization" if pin["account_kind"] == "organization" else "User"),
            "publisher kind mismatch",
        )

        def write_profile(run, scope):
            observation = _record(
                run,
                scope,
                key,
                "publisher",
                result.payload,
                observed_at=result.observed_at,
                request_id=result.collection_request_id,
            )
            _queue_numeric(claim, run, [observation])

        checkpoint_scope(
            claim,
            scope_kind="publisher",
            scope_key=key,
            ownership=pin,
            enumeration_complete=True,
            outcome="complete",
            write=write_profile,
        )
    scoped = _scope(claim, "publisher_repos", key)
    previous = None
    job = CollectionRun.objects.get(pk=claim.run_id).job
    if job.last_success_id and job.last_success_id != claim.run_id:
        previous = CollectionScopeRun.objects.filter(
            run_id=job.last_success_id,
            scope_kind="publisher_repos",
            scope_key=key,
            enumeration_complete=True,
        ).first()
    while scoped is None or not scoped.enumeration_complete:
        if items[0] >= job.budgets["items"]:
            raise CollectionStop("item_cap")
        cursor = scoped.cursor if scoped else None
        cached = _cached_inventory_page(previous, cursor) if previous else None
        scoped = _prepare_capture(claim, client, "publisher_repos", key, pin, scoped)
        result = client.repositories(
            pin["login"],
            pin["account_kind"],
            next_url=cursor,
            etag=cached.get("etag") if cached else None,
            per_page=min(100, job.budgets["items"] - items[0]),
        )
        _checked_response(
            claim, result, kind="publisher_repos", key=key, ownership=pin, scope=scoped
        )
        reused = None
        if result.status == 304:
            require(
                cached
                and cached.get("url") == result.url
                and isinstance(cached.get("payload"), list),
                "uncached not-modified inventory",
            )
            rows, next_url = cached["payload"], cached.get("next_url")
            reused = {
                "run_id": str(previous.run_id),
                "scope_id": previous.pk,
                "observed_at": cached["observed_at"],
            }
        else:
            rows, next_url = result.payload, result.next_url
        require(isinstance(rows, list), "repository listing required")
        require(
            len(rows) <= job.budgets["items"] - items[0],
            "listing exceeds remaining item budget",
        )
        for row in rows:
            require(
                isinstance(row, dict)
                and type(row.get("id")) is int
                and row["id"] > 0
                and row.get("private") is False
                and str(row.get("owner", {}).get("id")) == key,
                "public native repository ownership required",
            )
            client.repo_url(row["full_name"])
        history = [*(scoped.recorded_cursors if scoped else []), result.url]
        require(not next_url or next_url not in history, "pagination loop")

        def write(run, scope, rows=rows, result=result, reused=reused):
            captured = []
            for row in rows:
                observation = _record(
                    run,
                    scope,
                    row["id"],
                    "repository",
                    row,
                    observed_at=aware_instant(reused["observed_at"])
                    if reused
                    else result.observed_at,
                    reused_from=reused,
                    request_id=result.collection_request_id,
                )
                captured.append(observation)
            # A 304 carries old counters. Fresh detail below provides today's
            # numbers; the reused listing never becomes a new numeric snapshot.
            if not reused:
                _queue_numeric(claim, run, captured)

        scoped = checkpoint_scope(
            claim,
            scope_kind="publisher_repos",
            scope_key=key,
            ownership=pin,
            cursor=next_url,
            cursor_history=history,
            enumeration_complete=next_url is None,
            outcome="complete" if next_url is None else "pending",
            raw_count=(scoped.raw_count if scoped else 0) + len(rows),
            write=write,
        )
        items[0] += len(rows)
    return (
        scoped.observations.filter(observation_kind="repository")
        .select_related("legacy_archive")
        .order_by("pk")
    )


def _repository_access(claim, client, repository):
    """Cached inventory cannot authorize today's public content acquisition."""
    repo = observation_object_documents(repository)[0]
    key = str(repo["id"])
    ownership = {"repository_id": key, "owner_id": str(repo["owner"]["id"])}
    _prepare_capture(
        claim,
        client,
        "repository_access",
        key,
        ownership,
        _scope(claim, "repository_access", key),
        resource_observation=repository,
    )
    result = client.repository(repo["full_name"])
    if result.status == 404:
        checkpoint_scope(
            claim,
            scope_kind="repository_access",
            scope_key=key,
            ownership=ownership,
            enumeration_complete=True,
            outcome="inaccessible",
        )
        return False
    _checked_response(
        claim,
        result,
        kind="repository_access",
        key=key,
        ownership=ownership,
        scope=_scope(claim, "repository_access", key),
    )
    data = result.payload
    require(
        isinstance(data, dict)
        and str(data.get("id")) == key
        and str(data.get("owner", {}).get("id")) == ownership["owner_id"]
        and type(data.get("private")) is bool,
        "native repository access identity mismatch",
    )
    public = data["private"] is False

    def write_access(run, scope):
        if public:
            observation = _record(
                run,
                scope,
                key,
                "repository_access",
                data,
                observed_at=result.observed_at,
                request_id=result.collection_request_id,
            )
            _queue_numeric(claim, run, [observation])

    checkpoint_scope(
        claim,
        scope_kind="repository_access",
        scope_key=key,
        ownership=ownership,
        enumeration_complete=True,
        outcome="observed" if public else "inaccessible",
        write=write_access,
    )
    return public


def _release_assets(claim, client, repository, releases, items, limit):
    repo = observation_object_documents(repository)[0]
    for release in (
        releases.observations.filter(observation_kind="releases")
        .select_related("legacy_archive")
        .order_by("pk")
    ):
        release_id = observation_object_documents(release)[0]["id"]
        key = f"{repo['id']}:{release_id}"
        ownership = {
            "repository_id": repo["id"],
            "release_id": release_id,
            "owner_id": repo["owner"]["id"],
        }
        scoped = _scope(claim, "release_assets", key)
        while scoped is None or not scoped.enumeration_complete:
            if items[0] >= limit:
                raise CollectionStop("item_cap")
            scoped = _prepare_capture(
                claim,
                client,
                "release_assets",
                key,
                ownership,
                scoped,
                resource_observation=release,
            )
            result = client.release_assets(
                repo["full_name"],
                release_id,
                repository_id=repo["id"],
                next_url=scoped.cursor if scoped else None,
                per_page=min(100, limit - items[0]),
            )
            _checked_response(
                claim,
                result,
                kind="release_assets",
                key=key,
                ownership=ownership,
                scope=scoped,
            )
            rows = result.payload
            require(
                isinstance(rows, list) and len(rows) <= limit - items[0],
                "bounded release asset list required",
            )
            require(
                all(
                    isinstance(row, dict)
                    and type(row.get("id")) is int
                    and row["id"] > 0
                    for row in rows
                ),
                "native asset ID required",
            )
            history = [*(scoped.recorded_cursors if scoped else []), result.url]
            require(
                not result.next_url or result.next_url not in history,
                "asset pagination loop",
            )

            def write_assets(
                run,
                scope,
                rows=rows,
                result=result,
                release_id=release_id,
                release=release,
            ):
                captured = [
                    _record(
                        run,
                        scope,
                        repo["id"],
                        "release_asset",
                        row,
                        observed_at=result.observed_at,
                        request_id=result.collection_request_id,
                        coordinate={"release_id": release_id, "asset_id": row["id"]},
                        dimensions={"release_id": release_id, "asset_id": row["id"]},
                        metadata={
                            "owner_id": repo["owner"]["id"],
                            "repository_id": repo["id"],
                        },
                    )
                    for row in rows
                ]
                for observation in captured:
                    require(
                        observation.source_identifier == release.source_identifier,
                        "release asset repository differs from its parent",
                    )
                    edge, _ = CollectionObservationInput.objects.get_or_create(
                        observation=observation,
                        input_observation=release,
                        input_role="release_asset_parent",
                        defaults={
                            "row_locator": str(release_id),
                            "input_sha256": release.observation_key,
                        },
                    )
                    require(
                        edge.row_locator == str(release_id)
                        and edge.input_sha256 == release.observation_key,
                        "release asset parent evidence changed",
                    )
                _queue_numeric(claim, run, captured)

            scoped = checkpoint_scope(
                claim,
                scope_kind="release_assets",
                scope_key=key,
                ownership=ownership,
                cursor=result.next_url,
                cursor_history=history,
                enumeration_complete=result.next_url is None,
                outcome="complete" if result.next_url is None else "pending",
                raw_count=(scoped.raw_count if scoped else 0) + len(rows),
                write=write_assets,
            )
            items[0] += len(rows)


def _events(claim, client, repository, kind, items, limit):
    repo = observation_object_documents(repository)[0]
    ownership = {"repository_id": repo["id"], "owner_id": repo["owner"]["id"]}
    key = str(repo["id"]) + ":" + kind
    scoped = _scope(claim, "repository_events", key)
    while scoped is None or not scoped.enumeration_complete:
        if items[0] >= limit:
            raise CollectionStop("item_cap")
        scoped = _prepare_capture(
            claim,
            client,
            "repository_events",
            key,
            ownership,
            scoped,
            resource_observation=repository,
        )
        result = client.events(
            repo["full_name"],
            kind,
            repository_id=repo["id"],
            next_url=scoped.cursor if scoped else None,
            per_page=min(100, limit - items[0]),
        )
        _checked_response(
            claim,
            result,
            kind="repository_events",
            key=key,
            ownership=ownership,
            scope=scoped,
        )
        rows = result.payload
        require(
            isinstance(rows, list) and len(rows) <= limit - items[0],
            "bounded evidence list required",
        )
        raw_count = len(rows)
        if kind == "releases":
            require(
                all(
                    isinstance(row, dict) and type(row.get("draft")) is bool
                    for row in rows
                ),
                "release public-status flag required",
            )
            rows = [row for row in rows if not row["draft"] and row.get("published_at")]
            if result.collection_request_id:
                from core.collection_capture import capture_public_selection

                capture_public_selection(result.collection_request_id, rows)
            # Credentials used for rate limits must not retain unpublished data.
            result = replace(result, payload=rows)
        coordinates = []
        for row in rows:
            require(isinstance(row, dict), "GitHub evidence object required")
            coordinate = (
                row.get("id")
                if kind == "releases"
                else row.get("sha")
                if kind == "commits"
                else {"name": row.get("name"), "sha": row.get("commit", {}).get("sha")}
            )
            require(coordinate is not None, "native evidence coordinate required")
            if kind == "commits":
                client.revision(coordinate)
            if kind == "tags":
                client.revision(coordinate["sha"])
            coordinates.append(coordinate)
        history = [*(scoped.recorded_cursors if scoped else []), result.url]
        require(
            not result.next_url or result.next_url not in history, "pagination loop"
        )

        def write(run, scope, rows=rows, coordinates=coordinates, result=result):
            for row, coordinate in zip(rows, coordinates, strict=True):
                _record(
                    run,
                    scope,
                    repo["id"],
                    kind,
                    row,
                    coordinate=coordinate,
                    observed_at=result.observed_at,
                    request_id=result.collection_request_id,
                )

        scoped = checkpoint_scope(
            claim,
            scope_kind="repository_events",
            scope_key=key,
            ownership=ownership,
            cursor=result.next_url,
            cursor_history=history,
            enumeration_complete=result.next_url is None,
            outcome="complete" if result.next_url is None else "pending",
            raw_count=(scoped.raw_count if scoped else 0) + raw_count,
            write=write,
        )
        items[0] += raw_count
    return scoped


def _pinned_metadata(claim, client, repository, commits, *, head=None):
    head = head or commits.observations.order_by("pk").first()
    if head is None:
        return
    repo, head_document = (
        observation_object_documents(repository)[0],
        observation_object_documents(head)[0],
    )
    revision = head_document["sha"]
    tree_revision = head_document.get("commit", {}).get("tree", {}).get("sha")
    client.revision(tree_revision)
    ownership = {
        "repository_id": repo["id"],
        "revision": revision,
        "tree_revision": tree_revision,
    }
    key = str(repo["id"]) + ":" + revision
    scoped = _scope(claim, "repository_tree", key)
    if scoped is None or not scoped.enumeration_complete:
        scoped = _prepare_capture(
            claim,
            client,
            "repository_tree",
            key,
            ownership,
            scoped,
            resource_observation=head,
        )
        result = client.tree(repo["full_name"], tree_revision)
        _checked_response(
            claim,
            result,
            kind="repository_tree",
            key=key,
            ownership=ownership,
            scope=scoped,
        )
        require(
            isinstance(result.payload, dict)
            and result.payload.get("sha") == tree_revision
            and isinstance(result.payload.get("tree"), list),
            "file tree required",
        )
        scoped = checkpoint_scope(
            claim,
            scope_kind="repository_tree",
            scope_key=key,
            ownership=ownership,
            enumeration_complete=True,
            outcome="truncated" if result.payload.get("truncated") else "complete",
            write=lambda run, scope: _record(
                run,
                scope,
                repo["id"],
                "tree",
                result.payload,
                coordinate=revision,
                observed_at=result.observed_at,
                request_id=result.collection_request_id,
            ),
        )
    files = observation_object_documents(
        scoped.observations.select_related("legacy_archive").get(
            observation_kind="tree"
        )
    )[0]["tree"]
    for item in files:
        filename = item.get("path")
        if (
            filename not in METADATA_FILES
            or item.get("type") != "blob"
            or type(item.get("size")) is not int
            or item["size"] > 128 * 1024
        ):
            continue
        key = str(repo["id"]) + ":" + revision + ":" + filename
        file_scope = _scope(claim, "repository_file", key)
        if file_scope and file_scope.enumeration_complete:
            continue
        file_scope = _prepare_capture(
            claim,
            client,
            "repository_file",
            key,
            ownership,
            file_scope,
            resource_observation=head,
        )
        result = client.file(repo["full_name"], filename, revision)
        _checked_response(
            claim,
            result,
            kind="repository_file",
            key=key,
            ownership=ownership,
            scope=file_scope,
        )
        require(
            result.payload.get("sha") == item.get("sha"),
            "pinned file revision mismatch",
        )
        checkpoint_scope(
            claim,
            scope_kind="repository_file",
            scope_key=key,
            ownership=ownership,
            enumeration_complete=True,
            outcome="complete",
            write=lambda run, scope, result=result, filename=filename: _record(
                run,
                scope,
                repo["id"],
                "file",
                result.payload,
                coordinate={"revision": revision, "filename": filename},
                observed_at=result.observed_at,
                request_id=result.collection_request_id,
            ),
        )


def execute_github_catalog(job_id, *, client=None, key=None):
    """Execute one finite invocation; registration and inspection remain inert."""
    candidate = CollectionJob.objects.get(pk=job_id)
    require(
        candidate.operation == "github_catalog" and candidate.source_id == "github",
        "GitHub catalog job required",
    )
    claim = claim_job(job_id, typed=True)
    run = CollectionRun.objects.select_related("job").get(pk=claim.run_id)
    job = run.job
    require(
        job.operation == "github_catalog" and job.source_id == "github",
        "GitHub catalog job required",
    )
    own_client = None
    if client is None:
        import httpx

        own_client = httpx.Client(trust_env=False)
        client = GitHubMetadataClient(
            Budget(
                own_client,
                max_requests=job.budgets["requests"],
                max_bytes=job.budgets["bytes"],
                max_seconds=job.budgets["seconds"],
            ),
            key=key,
        )
    budget = client.budget
    from core.collection_capture import RequestCapture

    previous_capture = client.capture
    client.capture = RequestCapture(claim)
    budget.remaining = min(budget.remaining, job.budgets["requests"])
    budget.max_bytes = min(budget.max_bytes, job.budgets["bytes"])
    budget.deadline = min(budget.deadline, budget.clock() + job.budgets["seconds"])
    requests_before = budget.remaining
    reason, retry_at = None, None
    items = [0]
    try:
        from core.source_metric_projection import drain_pending_projections

        scope = job.scope
        role = scope.get("github_role", "full")
        require(
            role in {"inventory", "release_watch", "full"}, "unsupported GitHub role"
        )
        if scope.get("numeric_contract_id"):
            pending = drain_pending_projections(
                job.pk, budget=budget, origin_claim=claim
            )
            if pending["pending"]:
                raise CollectionStop("numeric_projection_pending")
        publishers = scope.get("publishers")
        require(
            isinstance(publishers, list) and publishers,
            "reviewed publisher scope required",
        )
        for publisher in publishers:
            repositories = _publisher_inventory(claim, client, publisher, items)
            for repository in repositories:
                prior_access = _scope(
                    claim,
                    "repository_access",
                    str(observation_object_documents(repository)[0]["id"]),
                )
                if (
                    role == "inventory"
                    and prior_access
                    and prior_access.enumeration_complete
                ):
                    continue
                if not _repository_access(claim, client, repository):
                    continue
                if role == "inventory":
                    continue
                releases = _events(
                    claim,
                    client,
                    repository,
                    "releases",
                    items,
                    job.budgets["items"],
                )
                if scope.get(
                    "include_release_assets", bool(scope.get("numeric_contract_id"))
                ):
                    _release_assets(
                        claim,
                        client,
                        repository,
                        releases,
                        items,
                        job.budgets["items"],
                    )
                if role == "release_watch":
                    continue
                _events(
                    claim,
                    client,
                    repository,
                    "tags",
                    items,
                    job.budgets["items"],
                )
                commits = _events(
                    claim,
                    client,
                    repository,
                    "commits",
                    items,
                    job.budgets["items"],
                )
                _pinned_metadata(claim, client, repository, commits)
    except SourceError as exc:
        reason, retry_at = str(exc), getattr(exc, "retry_at", None)
    except (ValueError, KeyError, TypeError, Account.DoesNotExist):
        reason = "invalid_or_unqualified_source_data"
    finally:
        client.capture = previous_capture
        if own_client:
            own_client.close()
    projection = None
    if job.scope.get("numeric_contract_id"):
        from core.source_metric_projection import drain_pending_projections

        try:
            projection = drain_pending_projections(
                job.pk, budget=budget, origin_claim=claim
            )
            if projection["pending"] and reason is None:
                reason = "numeric_projection_pending"
        except (ValueError, KeyError, TypeError):
            reason = reason or "numeric_projection_failed"
    scopes = run.scopes.exclude(
        scope_kind__in={"numeric_projection_item", "catalog_execution", "release_detection"}
    )
    selected, successful = (
        scopes.count(),
        scopes.filter(enumeration_complete=True).count(),
    )
    with fenced_run(claim) as (_, locked_run):
        attempt = locked_run.attempts.select_for_update().get(pk=claim.attempt_id)
        attempt.actual_items = items[0]
        attempt.save(update_fields=["actual_items"])
    run.refresh_from_db()
    finished = finish_run(
        claim,
        status="partial" if reason else "success",
        typed=True,
        physical_accounting_complete=True,
        request_count=run.request_count + requests_before - budget.remaining,
        selected_count=selected,
        success_count=successful,
        retry_at=retry_at,
        error_code=reason,
    )
    if run.scopes.filter(scope_kind="release_detection", outcome="pending").exists():
        from core.product_release_acquisition import dispatch_due_recovery

        dispatch_due_recovery()
    return finished
