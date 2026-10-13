"""Checkpoint public GitHub evidence without interpreting model release dates."""

from __future__ import annotations

from core.benchmark_metric_store import aware_instant, safe_payload
from core.collection_jobs import register_job
from core.collection_state import checkpoint_scope, claim_job, finish_run
from core.github_metadata_client import METADATA_FILES, GitHubMetadataClient
from core.measurement_taxonomy import digest, require
from core.models import (
    Account,
    CollectionJob,
    CollectionObservation,
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
    *, job_key, publisher_ids, budgets, mode="recurring", schedule=None
):
    source = register_github_source()
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
    return register_job(
        job_key=job_key,
        source=source,
        purpose="catalog",
        operation="github_catalog",
        mode=mode,
        definition={
            "version": 1,
            "scope": {"publishers": publishers},
            "budgets": budgets,
            "schedule": schedule
            or (
                {"kind": "daily_utc", "driver": "shared", "hour": 10}
                if mode == "recurring"
                else {"kind": "manual", "driver": "manual"}
            ),
        },
    )


def _envelope(result, *, payload=None, reused_from=None):
    return {
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
):
    safe_payload(payload)
    resource = (
        f"{identifier}:{kind}:{digest({'coordinate': coordinate, 'payload': payload})}"
    )
    clocks = {}
    published_at = None
    if kind == "repository":
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
            "dimensions": {"kind": kind, "coordinate": coordinate},
            "source_metadata": {"clocks": clocks, "reused_from": reused_from},
            "published_at": published_at,
            "publication_precision": "instant" if published_at else "unknown",
        },
    )
    return observation


def _scope(claim, kind, key):
    return CollectionScopeRun.objects.filter(
        run_id=claim.run_id, scope_kind=kind, scope_key=key
    ).first()


def _checked_response(claim, result, *, kind, key, ownership, scope):
    if result.status in {200, 304}:
        return
    checkpoint_scope(
        claim,
        scope_kind=kind,
        scope_key=key,
        ownership=ownership,
        cursor=scope.cursor if scope else None,
        cursor_history=scope.cursor_history if scope else [],
        envelopes=[*(scope.envelopes if scope else []), _envelope(result)],
        outcome=f"http_{result.status}",
    )
    raise CollectionStop(f"http_{result.status}", result.retry_at)


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
        checkpoint_scope(
            claim,
            scope_kind="publisher",
            scope_key=key,
            ownership=pin,
            enumeration_complete=True,
            outcome="complete",
            envelopes=[_envelope(result)],
            write=lambda run, scope: _record(
                run,
                scope,
                key,
                "publisher",
                result.payload,
                observed_at=result.observed_at,
            ),
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
        if items[0] >= job.definition["budgets"]["items"]:
            raise CollectionStop("item_cap")
        cursor = scoped.cursor if scoped else None
        cached = None
        if previous:
            cached = (
                next((e for e in previous.envelopes if e.get("url") == cursor), None)
                if cursor
                else (previous.envelopes[0] if previous.envelopes else None)
            )
        result = client.repositories(
            pin["login"],
            pin["account_kind"],
            next_url=cursor,
            etag=cached.get("etag") if cached else None,
            per_page=min(100, job.definition["budgets"]["items"] - items[0]),
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
            len(rows) <= job.definition["budgets"]["items"] - items[0],
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
        history = [*(scoped.cursor_history if scoped else []), result.url]
        require(not next_url or next_url not in history, "pagination loop")

        def write(run, scope, rows=rows, result=result, reused=reused):
            for row in rows:
                _record(
                    run,
                    scope,
                    row["id"],
                    "repository",
                    row,
                    observed_at=result.observed_at,
                    reused_from=reused,
                )

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


def _events(claim, client, repository, kind, items, limit):
    repo = repository.listing
    ownership = {"repository_id": repo["id"], "owner_id": repo["owner"]["id"]}
    key = str(repo["id"]) + ":" + kind
    scoped = _scope(claim, "repository_events", key)
    while scoped is None or not scoped.enumeration_complete:
        if items[0] >= limit:
            raise CollectionStop("item_cap")
        result = client.events(
            repo["full_name"],
            kind,
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
        history = [*(scoped.cursor_history if scoped else []), result.url]
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
            raw_count=(scoped.raw_count if scoped else 0) + len(rows),
            write=write,
        )
        items[0] += len(rows)
    return scoped


def _pinned_metadata(claim, client, repository, commits):
    head = commits.observations.order_by("pk").first()
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
                max_requests=job.definition["budgets"]["requests"],
                max_bytes=job.definition["budgets"]["bytes"],
                max_seconds=job.definition["budgets"]["seconds"],
            ),
            key=key,
        )
    budget = client.budget
    budget.remaining = min(budget.remaining, job.definition["budgets"]["requests"])
    budget.max_bytes = min(budget.max_bytes, job.definition["budgets"]["bytes"])
    budget.deadline = min(
        budget.deadline, budget.clock() + job.definition["budgets"]["seconds"]
    )
    requests_before = budget.remaining
    reason, retry_at = None, None
    items = [0]
    try:
        publishers = job.definition["scope"].get("publishers")
        require(
            isinstance(publishers, list) and publishers,
            "reviewed publisher scope required",
        )
        for publisher in publishers:
            repositories = _publisher_inventory(claim, client, publisher, items)
            for repository in repositories:
                _events(
                    claim,
                    client,
                    repository,
                    "releases",
                    items,
                    job.definition["budgets"]["items"],
                )
                _events(
                    claim,
                    client,
                    repository,
                    "tags",
                    items,
                    job.definition["budgets"]["items"],
                )
                commits = _events(
                    claim,
                    client,
                    repository,
                    "commits",
                    items,
                    job.definition["budgets"]["items"],
                )
                _pinned_metadata(claim, client, repository, commits)
    except SourceError as exc:
        reason, retry_at = str(exc), getattr(exc, "retry_at", None)
    except (ValueError, KeyError, TypeError, Account.DoesNotExist):
        reason = "invalid_or_unqualified_source_data"
    finally:
        if own_client:
            own_client.close()
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
