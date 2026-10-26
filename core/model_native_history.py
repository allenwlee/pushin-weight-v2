"""Native repository history with fenced, resumable public metadata evidence.

Numeric admission remains the reviewed history importer's responsibility. Missing
source evidence creates a coverage outcome, never a zero-valued metric row.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from core.benchmark_metric_identity import SOURCE_STATISTICS_POLICY
from core.benchmark_metric_store import aware_instant
from core.collection_state import (
    checkpoint_scope,
)
from core.measurement_taxonomy import digest, require
from core.models import (
    BrandCompany,
    CollectionObservation,
    CollectionRun,
    CollectionScopeRun,
    SourceSubjectMapping,
)
from core.publisher_accounts import get_publisher
from scripts.benchmark_download_collector.sources import (
    SourceError,
)

HF_CAPTURE_KIND = "hf-native-history-v1"
HF_SCOPE_PHASE = "typed-hf-native-history-v1"


def _native_pins(job):
    for model in job.scope.get("models", []):
        pins = [
            p for p in model.get("provider_pins", []) if p["source"] == job.source_id
        ]
        if not pins and job.source_id == "hf":
            creation = model.get("creation", {})
            if creation.get("source") == "hf" and creation.get("native_identifier"):
                pins = [{"native_identifier": creation["native_identifier"]}]
        yield from pins


def validate_typed_scope(job, run, kind, key, ownership, observation):
    """Validate native acquisition against frozen selection and captured parents."""
    require(
        job.purpose == "catalog"
        and job.operation == "model_history"
        and job.source_id in {"hf", "github"}
        and run.job_id == job.pk,
        "native history job required",
    )
    identifier = ownership.get("repository_id")
    pins = [p for p in _native_pins(job) if p["native_identifier"] == str(identifier)]
    require(pins, "native repository differs from frozen model selection")
    if job.source_id == "hf":
        namespace = identifier.split("/", 1)[0]
        publisher = get_publisher(source="hf", identifier=namespace, confirmed=True)
        require(
            BrandCompany.objects.filter(
                brand_id=job.scope["brand_id"], company_id=publisher.company_id
            ).exists(),
            "HF publisher ownership changed",
        )
        require(
            ownership
            == {
                "repository_id": identifier,
                "namespace": namespace,
                "company_id": publisher.company_id,
            },
            "HF native scope ownership changed",
        )
        if kind == "hf_history_head":
            require(
                key == identifier and observation is None,
                "HF native head scope changed",
            )
            return
        require(
            kind == "hf_repository_history"
            and key
            in {
                identifier + ":commits",
                identifier + ":tree",
            },
            "HF native history coordinate changed",
        )
        if observation is None:
            require(
                key.endswith(":tree") and not _hf_dated_head(run.pk, identifier, job),
                "HF history parent required",
            )
            require(
                run.scopes.filter(
                    scope_kind=kind,
                    scope_key=identifier + ":commits",
                    enumeration_complete=True,
                ).exists(),
                "HF commit enumeration must finish before reporting missing history",
            )
            return
        require(
            observation.run_id == run.pk
            and observation.source_identifier == identifier
            and observation.projection_kind == HF_CAPTURE_KIND
            and observation.resource_snapshot.publisher_account_id
            == publisher.account_id,
            "HF history parent differs from selected repository",
        )
        require(
            (
                key.endswith(":commits")
                and observation.observation_kind == "hf_metadata"
                and observation.scope_run.scope_kind == "hf_history_head"
            )
            or (
                key.endswith(":tree")
                and observation.observation_kind == "hf_commits"
                and observation.pk
                == getattr(_hf_dated_head(run.pk, identifier, job), "pk", None)
            ),
            "HF history parent differs from cutoff selection",
        )
        return
    mappings = list(
        SourceSubjectMapping.objects.filter(
            pk__in=[p["mapping_id"] for p in pins],
            source_id="github",
            external_identifier=str(identifier),
        ).select_related("publisher_account")
    )
    mappings = [
        m
        for m in mappings
        if any(
            str(m.pk) == p["mapping_id"] and m.mapping_hash == p["mapping_hash"]
            for p in pins
        )
    ]
    require(mappings, "reviewed GitHub mapping changed")
    if kind == "repository_history":
        require(
            observation is None
            and key == identifier
            and any(
                ownership
                == {
                    "repository_id": identifier,
                    "publisher_account_key": str(m.publisher_account_id),
                    "mapping_hash": m.mapping_hash,
                }
                for m in mappings
            ),
            "GitHub history ownership changed",
        )
        return
    require(
        observation is not None
        and observation.run_id == run.pk
        and observation.source_identifier == str(identifier)
        and observation.projection_kind == "github-catalog-object-v1",
        "GitHub history needs its captured parent",
    )
    snapshot = observation.resource_snapshot
    require(
        snapshot.publisher_account_id in {m.publisher_account_id for m in mappings},
        "GitHub history publisher changed",
    )
    owner = int(snapshot.publisher_account.normalized_identifier)
    if kind == "repository_events":
        expected = {"repository_id": int(identifier), "owner_id": owner}
        valid = observation.observation_kind == "repository" and key in {
            f"{identifier}:{event}" for event in ("releases", "tags", "commits")
        }
    elif kind == "release_assets":
        release_id = int(snapshot.native_stable_id)
        expected = {
            "repository_id": int(identifier),
            "release_id": release_id,
            "owner_id": owner,
        }
        valid = (
            observation.observation_kind == "releases"
            and key == f"{identifier}:{release_id}"
        )
    elif kind in {"repository_tree", "repository_file"}:
        from core.github_metadata_client import METADATA_FILES

        expected = {
            "repository_id": int(identifier),
            "revision": snapshot.revision,
            "tree_revision": snapshot.tree_revision,
        }
        prefix = f"{identifier}:{snapshot.revision}"
        valid = (
            observation.observation_kind == "commits"
            and snapshot.committed_at is not None
            and snapshot.committed_at < aware_instant(job.scope["cutoff"])
            and (
                key == prefix
                if kind == "repository_tree"
                else key in {f"{prefix}:{filename}" for filename in METADATA_FILES}
            )
        )
    else:
        raise ValueError("unsupported GitHub native history scope")
    require(valid and ownership == expected, "GitHub native history coordinate changed")


def observation_documents(observation):
    """Read the exact accepted HF object from its physical response receipt."""
    from core.collection_capture import read_document

    scope, job = observation.scope_run, observation.run.job
    kind = observation.observation_kind
    require(
        observation.projection_kind == HF_CAPTURE_KIND
        and job.source_id == "hf"
        and job.operation == "model_history"
        and job.purpose == "catalog"
        and scope is not None
        and scope.run_id == observation.run_id
        and scope.phase == HF_SCOPE_PHASE
        and kind in {"hf_metadata", "hf_commits", "hf_tree"}
        and observation.source_subject_kind == "repository"
        and observation.source_identifier
        in {p["native_identifier"] for p in _native_pins(job)},
        "typed HF native capture required",
    )
    group = "detail" if kind == "hf_metadata" else kind.removeprefix("hf_")
    require(
        scope.scope_kind
        == ("hf_history_head" if kind == "hf_metadata" else "hf_repository_history")
        and scope.scope_key
        == observation.source_identifier
        + ("" if kind == "hf_metadata" else ":" + group),
        "HF native object scope changed",
    )
    links = list(
        observation.inputs.filter(input_role="hf_native_object").select_related(
            "input_request__archive", "input_request__attempt"
        )
    )
    require(len(links) == 1, "one accepted HF native response required")
    (edge,) = links
    request = edge.input_request
    require(
        request is not None
        and request.attempt.run_id == observation.run_id
        and request.scope_run_id == scope.pk
        and request.transport_outcome == "received"
        and request.http_status == 200
        and request.error_code is None
        and request.request_group == group
        and request.archive_id is not None
        and edge.input_sha256 == request.archive.content_sha256,
        "HF native response ownership or checksum changed",
    )
    body = read_document(request.archive)
    endpoint = urlsplit(request.endpoint_url)
    path = "/api/models/" + observation.source_identifier
    if kind != "hf_metadata":
        require(
            isinstance(scope.requested_revision, str) and scope.requested_revision,
            "HF native requested revision changed",
        )
        path += "/" + group + "/" + scope.requested_revision
    require(
        endpoint.scheme == "https"
        and endpoint.netloc == "huggingface.co"
        and endpoint.path == path
        and not endpoint.fragment,
        "HF native request endpoint changed",
    )
    if kind == "hf_metadata":
        native_id = (
            (body.get("id") or body.get("modelId")) if isinstance(body, dict) else None
        )
        require(
            edge.row_locator == "object"
            and isinstance(native_id, str)
            and native_id.casefold() == observation.source_identifier.casefold()
            and request.request_revision is None,
            "HF native head identity changed",
        )
        raw = body
        revision = raw.get("sha")
    else:
        position = edge.row_locator
        require(
            isinstance(position, str)
            and position.isascii()
            and position.isdecimal()
            and str(int(position)) == position
            and isinstance(body, list)
            and int(position) < len(body),
            "HF native page position changed",
        )
        raw, revision = body[int(position)], scope.requested_revision
        parent = scope.resource_observation
        require(
            parent is not None
            and parent.run_id == observation.run_id
            and parent.source_identifier == observation.source_identifier
            and parent.resource_snapshot.revision == revision
            and request.request_revision == revision,
            "HF native requested revision changed",
        )
    require(
        isinstance(raw, dict)
        and digest(raw) == observation.payload_sha256
        and revision == observation.provider_revision,
        "HF native selected payload changed",
    )
    return (
        raw,
        {"kind": kind},
        {
            "projection_kind": HF_CAPTURE_KIND,
            "revision": revision,
            "historical_public_visibility_proven": observation.historical_visibility_proven,
            **(
                {"source_record_date": raw.get("date")} if kind != "hf_metadata" else {}
            ),
        },
    )


def _native_record(
    run, scoped, identifier, kind, payload, *, request, position=None, metadata=None
):
    from core.benchmark_metric_store import safe_payload
    from core.collection_capture import link_request
    from core.collection_resources import (
        observation_fact_values,
        project_observation_facts,
    )

    safe_payload(payload)
    resource = digest({"identifier": identifier, "kind": kind, "payload": payload})
    metadata = {**(metadata or {}), "projection_kind": HF_CAPTURE_KIND}
    draft = CollectionObservation(
        run=run, scope_run=scoped, source_identifier=identifier
    )
    observation, created = CollectionObservation.objects.get_or_create(
        run=run,
        observation_key=resource,
        defaults={
            "scope_run": scoped,
            "resource_key": resource,
            "source_identifier": identifier,
            "source_subject_kind": "repository",
            "observed_at": request.received_at,
            **observation_fact_values(
                draft, documents=(payload, {"kind": kind}, metadata)
            ),
        },
    )
    require(
        observation.scope_run_id == scoped.pk
        and observation.projection_kind == HF_CAPTURE_KIND
        and observation.payload_sha256 == digest(payload),
        "HF native capture identity changed",
    )
    if created:
        link_request(
            observation,
            request,
            role="hf_native_object",
            row_locator="object" if position is None else str(position),
        )
    snapshot = project_observation_facts(observation)
    publisher = get_publisher(
        source="hf", identifier=identifier.split("/", 1)[0], confirmed=True
    )
    require(
        snapshot.publisher_account_id in (None, publisher.account_id),
        "HF captured publisher changed",
    )
    if snapshot.publisher_account_id is None:
        snapshot.publisher_account_id = publisher.account_id
        snapshot.save(update_fields=["publisher_account"])
    return observation


def _hf_dated_head(run_id, identifier, job):
    return _latest_before_cutoff(
        CollectionObservation.objects.filter(
            run_id=run_id, source_identifier=identifier, observation_kind="hf_commits"
        )
        .select_related("resource_snapshot")
        .only("observation_key", "source_record_at", "resource_snapshot"),
        lambda row: row.source_record_at,
        aware_instant(job.scope["cutoff"]),
    )


def _hf_checkpoint(claim, *, resource_observation=None, write=None, **kwargs):
    current = CollectionScopeRun.objects.filter(
        run_id=claim.run_id,
        scope_kind=kwargs["scope_kind"],
        scope_key=kwargs["scope_key"],
    ).first()
    if current is not None:
        require(
            current.phase == HF_SCOPE_PHASE,
            "historical HF native scope requires typed migration",
        )
        resource_observation = resource_observation or current.resource_observation

    def save(run, scope):
        scope.phase = HF_SCOPE_PHASE
        fields = ["phase"]
        if resource_observation is not None:
            revision = resource_observation.resource_snapshot.revision
            require(
                scope.requested_revision in (None, revision),
                "HF history requested revision changed",
            )
            scope.requested_revision = revision
            fields.append("requested_revision")
        scope.save(update_fields=fields)
        if write is not None:
            write(run, scope)

    return checkpoint_scope(
        claim,
        typed=True,
        resource_observation=resource_observation,
        write=save,
        **kwargs,
    )


def _latest_before_cutoff(observations, date_of, cutoff):
    """Select a source-dated revision without materializing a repository history."""
    head, order = None, None
    for row in observations.iterator(chunk_size=100):
        value = date_of(row)
        if not value:
            continue
        try:
            instant = aware_instant(value)
        except (ValueError, TypeError):
            continue
        candidate = (instant, row.observation_key)
        if instant < cutoff and (order is None or candidate > order):
            head, order = row, candidate
    return head


def _github_history(claim, job, pins, budget, items):
    import os

    from core.github_catalog import (
        _events,
        _pinned_metadata,
        _prepare_capture,
        _queue_numeric,
        _record,
        _release_assets,
    )
    from core.github_catalog import (
        checkpoint_scope as github_checkpoint,
    )
    from core.github_metadata_client import GitHubMetadataClient

    client = GitHubMetadataClient(
        budget, key=os.environ.get("PUSHINWEIGHT_GITHUB_API_TOKEN")
    )
    from core.collection_capture import RequestCapture

    client.capture = RequestCapture(claim)
    for pin in pins:
        mapping = SourceSubjectMapping.objects.select_related("publisher_account").get(
            pk=pin["mapping_id"]
        )
        identifier = pin["native_identifier"]
        old = (
            CollectionRun.objects.get(pk=claim.run_id)
            .scopes.filter(scope_kind="repository_history", scope_key=identifier)
            .first()
        )
        require(
            old is None or old.phase == "typed-github-catalog-v1",
            "historical GitHub native scope requires typed migration",
        )
        if old and old.enumeration_complete:
            continue
        ownership = {
            "repository_id": identifier,
            "publisher_account_key": str(mapping.publisher_account_id),
            "mapping_hash": mapping.mapping_hash,
        }
        full_name = mapping.identifier_metadata.get(
            "current_full_name"
        ) or mapping.identity_snapshot.get("observed_full_name")
        require(full_name, "reviewed GitHub full-name alias required")
        _prepare_capture(
            claim, client, "repository_history", identifier, ownership, old
        )
        # A checkpoint preserves evidence, not today's access eligibility.
        result = client.repository(full_name)
        if result.status != 200:
            raise SourceError(f"http_{result.status}")
        data = result.payload
        if isinstance(data, dict) and data.get("private") is True:
            raise SourceError("private")
        require(
            isinstance(data, dict)
            and str(data.get("id")) == identifier
            and data.get("private") is False
            and str(data.get("owner", {}).get("id"))
            == mapping.publisher_account.normalized_identifier,
            "public reviewed repository identity mismatch",
        )
        created = []

        def write(
            run,
            scoped,
            created=created,
            identifier=identifier,
            data=data,
            result=result,
        ):
            created.append(
                _record(
                    run,
                    scoped,
                    identifier,
                    "repository",
                    data,
                    observed_at=result.observed_at,
                    request_id=result.collection_request_id,
                )
            )
            _queue_numeric(claim, run, created)

        github_checkpoint(
            claim,
            scope_kind="repository_history",
            scope_key=identifier,
            ownership=ownership,
            write=write,
        )
        repository = created[0]
        releases = _events(
            claim,
            client,
            repository,
            "releases",
            items,
            job.budgets["items"],
        )
        if job.scope.get("numeric_projection_policy") == SOURCE_STATISTICS_POLICY:
            _release_assets(
                claim,
                client,
                repository,
                releases,
                items,
                job.budgets["items"],
            )
        _events(claim, client, repository, "tags", items, job.budgets["items"])
        commits = _events(
            claim,
            client,
            repository,
            "commits",
            items,
            job.budgets["items"],
        )
        cutoff = aware_instant(job.scope["cutoff"])
        head = _latest_before_cutoff(
            commits.observations.select_related("resource_snapshot").only(
                "observation_key",
                "resource_snapshot",
            ),
            lambda o: o.resource_snapshot.committed_at,
            cutoff,
        )
        if head:
            _pinned_metadata(claim, client, repository, commits, head=head)
        github_checkpoint(
            claim,
            scope_kind="repository_history",
            scope_key=identifier,
            ownership=ownership,
            enumeration_complete=True,
            outcome="observed",
        )


def _hf_history(claim, job, pins, budget, items):
    from core.collection_capture import RequestCapture
    from core.hf_catalog import _accepted_request, _record_result
    from core.hf_metadata_client import HFMetadataClient

    budget.check()
    before = budget.remaining
    client = HFMetadataClient(
        budget.client,
        max_requests=budget.remaining,
        max_seconds=budget.deadline - budget.clock(),
        max_bytes=budget.max_bytes,
        max_total_bytes=budget.max_bytes - budget.total_bytes_read,
        clock=budget.clock,
        sleep=budget.sleep,
    )
    client.capture = RequestCapture(claim)
    try:
        for pin in pins:
            identifier = pin["native_identifier"]
            namespace = identifier.split("/", 1)[0]
            org = get_publisher(source="hf", identifier=namespace, confirmed=True)
            require(
                BrandCompany.objects.filter(
                    company_id=org.company_id,
                    brand_id=job.scope["brand_id"],
                ).exists(),
                "HF publisher ownership changed",
            )
            ownership = {
                "repository_id": identifier,
                "namespace": namespace,
                "company_id": org.company_id,
            }
            head = (
                CollectionRun.objects.get(pk=claim.run_id)
                .scopes.filter(scope_kind="hf_history_head", scope_key=identifier)
                .first()
            )
            if head is None or not head.enumeration_complete:
                client.collection_scope = _hf_checkpoint(
                    claim,
                    scope_kind="hf_history_head",
                    scope_key=identifier,
                    ownership=ownership,
                )
                result = client.model_group(identifier, "detail")
                _record_result(claim, client.collection_scope, result, "detail")
                if result.outcome != "ok":
                    raise SourceError(result.outcome)
                data = result.payload
                require(
                    isinstance(data, dict) and isinstance(data.get("sha"), str),
                    "native HF head revision required",
                )
                request = _accepted_request(result)
                require(request is not None, "HF native head response required")

                def capture_head(
                    run,
                    scoped,
                    identifier=identifier,
                    data=data,
                    request=request,
                ):
                    observation = _native_record(
                        run,
                        scoped,
                        identifier,
                        "hf_metadata",
                        data,
                        request=request,
                        metadata={
                            "revision": data["sha"],
                            "historical_public_visibility_proven": False,
                        },
                    )
                    if job.scope.get("numeric_contract_id"):
                        from core.models import MetricCollectionContract
                        from core.source_metric_projection import enqueue_projection

                        contract = MetricCollectionContract.objects.get(
                            pk=job.scope["numeric_contract_id"]
                        )
                        if contract.source_configuration["hf"].get(
                            "eligibility_policy"
                        ) == SOURCE_STATISTICS_POLICY and any(
                            key in data
                            for key in (
                                "downloads",
                                "downloadsAllTime",
                                "likes",
                                "trendingScore",
                            )
                        ):
                            enqueue_projection(
                                claim, contract=contract, evidence_ids=[observation.pk]
                            )

                head = _hf_checkpoint(
                    claim,
                    scope_kind="hf_history_head",
                    scope_key=identifier,
                    ownership=ownership,
                    enumeration_complete=True,
                    outcome="observed",
                    write=capture_head,
                )
                revision = data["sha"]
            else:
                require(
                    head.phase == HF_SCOPE_PHASE,
                    "historical HF native scope requires typed migration",
                )
                captured_head = head.observations.select_related(
                    "resource_snapshot"
                ).get(
                    observation_kind="hf_metadata",
                )
                revision = captured_head.resource_snapshot.revision
                require(
                    isinstance(revision, str) and revision,
                    "native HF head revision required",
                )
            for kind in ("commits", "tree"):
                parent = head.observations.select_related("resource_snapshot").get(
                    observation_kind="hf_metadata"
                )
                if kind == "tree":
                    dated_head = _hf_dated_head(claim.run_id, identifier, job)
                    if dated_head is None:
                        _hf_checkpoint(
                            claim,
                            scope_kind="hf_repository_history",
                            scope_key=identifier + ":tree",
                            ownership=ownership,
                            enumeration_complete=True,
                            outcome="history_unavailable",
                            write=lambda run, scope: CollectionScopeRun.objects.filter(
                                pk=scope.pk
                            ).update(error_code="no_qualified_commit_at_cutoff"),
                        )
                        continue
                    revision = dated_head.resource_snapshot.revision
                    parent = dated_head
                    require(
                        isinstance(revision, str) and revision,
                        "native HF commit revision required",
                    )
                key = identifier + ":" + kind
                scoped = (
                    CollectionRun.objects.get(pk=claim.run_id)
                    .scopes.filter(scope_kind="hf_repository_history", scope_key=key)
                    .first()
                )
                while scoped is None or not scoped.enumeration_complete:
                    if items[0] >= job.budgets["items"]:
                        raise SourceError("item_cap")
                    client.collection_scope = _hf_checkpoint(
                        claim,
                        scope_kind="hf_repository_history",
                        scope_key=key,
                        ownership=ownership,
                        resource_observation=parent,
                        cursor=scoped.cursor if scoped else None,
                        cursor_history=scoped.recorded_cursors if scoped else [],
                        outcome=scoped.outcome if scoped else "pending",
                    )
                    result = client.history_page(
                        identifier, revision, kind, scoped.cursor if scoped else None
                    )
                    _record_result(claim, client.collection_scope, result, kind)
                    if result.outcome != "ok":
                        raise SourceError(result.outcome)
                    require(
                        len(result.payload) <= job.budgets["items"] - items[0],
                        "HF history item budget exceeded",
                    )
                    history = [
                        *(scoped.recorded_cursors if scoped else []),
                        scoped.cursor if scoped and scoped.cursor else "first",
                    ]
                    require(
                        result.next_cursor is None or result.next_cursor not in history,
                        "HF history cursor loop",
                    )
                    request = _accepted_request(result)
                    require(request is not None, "HF native page response required")
                    RequestCapture.response_metadata(request, cursor=result.next_cursor)

                    def write(
                        run,
                        scope,
                        rows=result.payload,
                        kind=kind,
                        identifier=identifier,
                        revision=revision,
                        request=request,
                    ):
                        for position, row in enumerate(rows):
                            _native_record(
                                run,
                                scope,
                                identifier,
                                "hf_" + kind,
                                row,
                                request=request,
                                position=position,
                                metadata={
                                    "revision": revision,
                                    "source_record_date": row.get("date"),
                                    "historical_public_visibility_proven": False,
                                },
                            )

                    scoped = _hf_checkpoint(
                        claim,
                        scope_kind="hf_repository_history",
                        scope_key=key,
                        ownership=ownership,
                        cursor=result.next_cursor,
                        cursor_history=history,
                        enumeration_complete=result.next_cursor is None,
                        outcome="observed" if result.next_cursor is None else "partial",
                        raw_count=(scoped.raw_count if scoped else 0)
                        + len(result.payload),
                        write=write,
                    )
                    items[0] += len(result.payload)
    finally:
        budget.remaining = before - client.requests
        budget.total_bytes_read += client.bytes_received
