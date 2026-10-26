"""Checkpoint public GitHub evidence without interpreting model release dates."""

from __future__ import annotations

from dataclasses import replace

from core.benchmark_metric_identity import SOURCE_STATISTICS_POLICY
from core.benchmark_metric_store import aware_instant, safe_payload
from core.collection_jobs import register_job
from core.collection_state import checkpoint_scope, claim_job, finish_run
from core.github_metadata_client import METADATA_FILES, GitHubMetadataClient
from core.measurement_taxonomy import digest, require
from core.models import (
    Account,
    CollectionJob,
    CollectionObservation,
    CollectionObservationInput,
    CollectionRun,
    CollectionScopeRun,
    DataSource,
)
from scripts.benchmark_download_collector.sources import Budget, SourceError


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


def _envelope(result, *, payload=None, reused_from=None):
    return {
        "collection_request_id": result.collection_request_id,
        "url": result.url,
        "status": result.status,
        "etag": result.etag,
        "next_url": result.next_url,
        "observed_at": result.observed_at.isoformat(),
        "retry_at": result.retry_at.isoformat() if result.retry_at else None,
        "payload": result.payload if payload is None else payload,
        "reused_from": reused_from,
    }


def _record(
    run,
    scope,
    identifier,
    kind,
    payload,
    *,
    observed_at,
    coordinate=None,
    reused_from=None,
    dimensions=None,
    metadata=None,
):
    safe_payload(payload)
    resource = (
        f"{identifier}:{kind}:{digest({'coordinate': coordinate, 'payload': payload})}"
    )
    clocks = {}
    published_at = None
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
        if payload.get("published_at"):
            published_at = aware_instant(payload["published_at"])
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
    key = digest({"resource_key": resource})
    observation, _ = CollectionObservation.objects.get_or_create(
        run=run,
        observation_key=key,
        defaults={
            "scope_run": scope,
            "resource_key": resource,
            "source_identifier": str(identifier),
            "source_subject_kind": "account" if kind == "publisher" else "repository",
            "observed_at": observed_at,
            "listing": payload,
            "dimensions": {
                "kind": kind,
                "coordinate": coordinate,
                **(dimensions or {}),
            },
            "source_metadata": {
                "clocks": clocks,
                "reused_from": reused_from,
                **(metadata or {}),
            },
            "published_at": published_at,
            "publication_precision": "instant" if published_at else "unknown",
        },
    )
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
    ids = [o.pk for o in observations if any(w in o.listing for w in wires if w)]
    if ids:
        enqueue_projection(claim, contract=contract, evidence_ids=ids)


def _scope(claim, kind, key):
    return CollectionScopeRun.objects.filter(
        run_id=claim.run_id, scope_kind=kind, scope_key=key
    ).first()


def _prepare_capture(claim, client, kind, key, ownership, scoped=None):
    scoped = scoped or checkpoint_scope(
        claim, scope_kind=kind, scope_key=key, ownership=ownership
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
        envelopes=[*(scope.envelopes if scope else []), _envelope(result)],
        outcome=f"http_{result.status}",
    )
    raise CollectionStop(f"http_{result.status}", result.retry_at)


def _cached_inventory_page(previous, cursor):
    """Read the previous actual response through its typed receipt/input links."""
    from core.collection_capture import read_document

    receipt = previous.requests.filter(
        cursor_before=cursor, transport_outcome="received",
        http_status__in=[200, 304], error_code__isnull=True,
    ).select_related("archive").order_by("-attempt__ordinal", "-ordinal").first()
    if receipt is None:
        return None
    body_request = receipt if receipt.archive_id else None
    resource = previous.observations.filter(
        inputs__input_request=receipt,
    ).order_by("pk").first()
    observed_at = resource.observed_at if resource else receipt.received_at
    # A 304 has no response body. Follow earlier resource results to the actual
    # public body rather than copying it into the new transport receipt.
    seen = set()
    while body_request is None and resource and resource.pk not in seen:
        seen.add(resource.pk)
        body_edge = resource.inputs.filter(
            input_request__archive__isnull=False,
            input_request__endpoint_url=receipt.endpoint_url,
        ).select_related("input_request__archive").first()
        if body_edge:
            body_request = body_edge.input_request
            break
        earlier = resource.inputs.filter(input_role="cached_response").select_related("input_observation").first()
        resource = earlier.input_observation if earlier else None
    if body_request is None:
        return None
    payload = read_document(body_request.archive)
    require(isinstance(payload, list), "cached repository listing required")
    return {
        "url": receipt.endpoint_url, "payload": payload,
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
            )
            _queue_numeric(claim, run, [observation])

        checkpoint_scope(
            claim,
            scope_kind="publisher",
            scope_key=key,
            ownership=pin,
            enumeration_complete=True,
            outcome="complete",
            envelopes=[_envelope(result)],
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
        envelope = {
            **_envelope(result, payload=rows, reused_from=reused),
            "next_url": next_url,
        }
        envelopes = [*(scoped.envelopes if scoped else []), envelope]
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
                )
                if reused:
                    from core.models import (
                        CollectionObservationInput,
                        CollectionRequest,
                    )

                    prior = CollectionObservation.objects.get(
                        scope_run_id=reused["scope_id"],
                        source_identifier=str(row["id"]),
                        observation_kind="repository",
                        observed_at=observation.observed_at,
                        payload_sha256=digest(row),
                    )
                    require(prior.listing == row, "cached repository payload changed")
                    CollectionObservationInput.objects.get_or_create(
                        observation=observation,
                        input_observation=prior,
                        input_role="cached_response",
                        defaults={"input_sha256": prior.payload_sha256},
                    )
                    validation = CollectionRequest.objects.get(
                        pk=result.collection_request_id,
                        scope_run=scope,
                        http_status=304,
                    )
                    CollectionObservationInput.objects.get_or_create(
                        observation=observation,
                        input_request=validation,
                        input_role="cache_validation",
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
            envelopes=envelopes,
            enumeration_complete=next_url is None,
            outcome="complete" if next_url is None else "pending",
            raw_count=(scoped.raw_count if scoped else 0) + len(rows),
            write=write,
        )
        items[0] += len(rows)
    return scoped.observations.filter(dimensions__kind="repository").order_by("pk")


def _repository_access(claim, client, repository):
    """Cached inventory cannot authorize today's public content acquisition."""
    repo = repository.listing
    key = str(repo["id"])
    ownership = {"repository_id": key, "owner_id": str(repo["owner"]["id"])}
    _prepare_capture(
        claim,
        client,
        "repository_access",
        key,
        ownership,
        _scope(claim, "repository_access", key),
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
            envelopes=[_envelope(result)],
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
            )
            _queue_numeric(claim, run, [observation])

    checkpoint_scope(
        claim,
        scope_kind="repository_access",
        scope_key=key,
        ownership=ownership,
        enumeration_complete=True,
        outcome="observed" if public else "inaccessible",
        envelopes=[
            {
                "url": result.url,
                "status": result.status,
                "observed_at": result.observed_at.isoformat(),
                "public": public,
                "collection_request_id": result.collection_request_id,
            }
        ],
        write=write_access,
    )
    return public


def _release_assets(claim, client, repository, releases, items, limit):
    repo = repository.listing
    for release in releases.observations.filter(dimensions__kind="releases").order_by(
        "pk"
    ):
        release_id = release.listing["id"]
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
                claim, client, "release_assets", key, ownership, scoped
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
                run, scope, rows=rows, result=result, release_id=release_id, release=release
            ):
                captured = [
                    _record(
                        run,
                        scope,
                        repo["id"],
                        "release_asset",
                        row,
                        observed_at=result.observed_at,
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
                        observation=observation, input_observation=release,
                        input_role="release_asset_parent",
                        defaults={"row_locator": str(release_id), "input_sha256": release.observation_key},
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
                envelopes=[*(scoped.envelopes if scoped else []), _envelope(result)],
                enumeration_complete=result.next_url is None,
                outcome="complete" if result.next_url is None else "pending",
                raw_count=(scoped.raw_count if scoped else 0) + len(rows),
                write=write_assets,
            )
            items[0] += len(rows)


def _events(claim, client, repository, kind, items, limit):
    repo = repository.listing
    ownership = {"repository_id": repo["id"], "owner_id": repo["owner"]["id"]}
    key = str(repo["id"]) + ":" + kind
    scoped = _scope(claim, "repository_events", key)
    while scoped is None or not scoped.enumeration_complete:
        if items[0] >= limit:
            raise CollectionStop("item_cap")
        scoped = _prepare_capture(
            claim, client, "repository_events", key, ownership, scoped
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
                )

        scoped = checkpoint_scope(
            claim,
            scope_kind="repository_events",
            scope_key=key,
            ownership=ownership,
            cursor=result.next_url,
            cursor_history=history,
            envelopes=[*(scoped.envelopes if scoped else []), _envelope(result)],
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
    repo, revision = repository.listing, head.listing["sha"]
    tree_revision = head.listing.get("commit", {}).get("tree", {}).get("sha")
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
            claim, client, "repository_tree", key, ownership, scoped
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
            envelopes=[_envelope(result)],
            write=lambda run, scope: _record(
                run,
                scope,
                repo["id"],
                "tree",
                result.payload,
                coordinate=revision,
                observed_at=result.observed_at,
            ),
        )
    files = scoped.observations.get(dimensions__kind="tree").listing["tree"]
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
            claim, client, "repository_file", key, ownership, file_scope
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
            envelopes=[_envelope(result)],
            write=lambda run, scope, result=result, filename=filename: _record(
                run,
                scope,
                repo["id"],
                "file",
                result.payload,
                coordinate={"revision": revision, "filename": filename},
                observed_at=result.observed_at,
            ),
        )


def execute_github_catalog(job_id, *, client=None, key=None):
    """Execute one finite invocation; registration and inspection remain inert."""
    candidate = CollectionJob.objects.get(pk=job_id)
    require(
        candidate.operation == "github_catalog" and candidate.source_id == "github",
        "GitHub catalog job required",
    )
    claim = claim_job(job_id)
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
                    claim, "repository_access", str(repository.listing["id"])
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
    scopes = run.scopes.all()
    selected, successful = (
        scopes.count(),
        scopes.filter(enumeration_complete=True).count(),
    )
    report = {
        "operation": "github_catalog",
        "stop_reason": reason,
        "items_this_invocation": items[0],
        "bytes_this_invocation": budget.total_bytes_read,
        "api_version": "2026-03-10",
        "native_clocks_are_release_leads": True,
        "numeric_projection": projection,
        "physical_accounting_complete": True,
        "inaccessible_repositories": list(
            scopes.filter(
                scope_kind="repository_access", outcome="inaccessible"
            ).values_list("scope_key", flat=True)
        ),
        "inventory_complete": {
            s.scope_key: s.enumeration_complete
            for s in scopes.filter(scope_kind="publisher_repos")
        },
    }
    run.refresh_from_db()
    return finish_run(
        claim,
        status="partial" if reason else "success",
        report=report,
        request_count=run.request_count + requests_before - budget.remaining,
        selected_count=selected,
        success_count=successful,
        retry_at=retry_at,
        error_code=reason,
    )
