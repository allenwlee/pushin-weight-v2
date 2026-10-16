"""Native repository history with fenced, resumable public metadata evidence.

Numeric admission remains the reviewed history importer's responsibility. Missing
source evidence creates a coverage outcome, never a zero-valued metric row.
"""

from __future__ import annotations

import json

from core.benchmark_metric_store import aware_instant
from core.collection_state import (
    checkpoint_scope,
)
from core.measurement_taxonomy import digest, require
from core.models import (
    BrandCompany,
    CollectionObservation,
    CollectionRun,
    SourceSubjectMapping,
)
from core.publisher_accounts import get_publisher
from scripts.benchmark_download_collector.sources import (
    SourceError,
)


def _native_record(run, scoped, identifier, kind, payload, *, metadata=None):
    from core.benchmark_metric_store import safe_payload

    safe_payload(payload)
    resource = digest({"identifier": identifier, "kind": kind, "payload": payload})
    return CollectionObservation.objects.get_or_create(
        run=run,
        observation_key=resource,
        defaults={
            "scope_run": scoped,
            "resource_key": resource,
            "source_identifier": identifier,
            "source_subject_kind": "repository",
            "listing": payload,
            "dimensions": {"kind": kind},
            "source_metadata": metadata or {},
        },
    )[0]


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

    from core.github_catalog import _events, _pinned_metadata, _record
    from core.github_metadata_client import GitHubMetadataClient

    client = GitHubMetadataClient(
        budget, key=os.environ.get("PUSHINWEIGHT_GITHUB_API_TOKEN")
    )
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
                )
            )

        checkpoint_scope(
            claim,
            scope_kind="repository_history",
            scope_key=identifier,
            ownership=ownership,
            write=write,
        )
        repository = created[0]
        _events(
            claim,
            client,
            repository,
            "releases",
            items,
            job.definition["budgets"]["items"],
        )
        _events(
            claim, client, repository, "tags", items, job.definition["budgets"]["items"]
        )
        commits = _events(
            claim,
            client,
            repository,
            "commits",
            items,
            job.definition["budgets"]["items"],
        )
        cutoff = aware_instant(job.definition["scope"]["cutoff"])
        head = _latest_before_cutoff(
            commits.observations.all(),
            lambda o: o.source_metadata.get("clocks", {}).get("committer_at"),
            cutoff,
        )
        if head:
            _pinned_metadata(claim, client, repository, commits, head=head)
        checkpoint_scope(
            claim,
            scope_kind="repository_history",
            scope_key=identifier,
            ownership=ownership,
            enumeration_complete=True,
            outcome="observed",
        )


def _hf_history(claim, job, pins, budget, items):
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
    try:
        for pin in pins:
            identifier = pin["native_identifier"]
            namespace = identifier.split("/", 1)[0]
            org = get_publisher(source="hf", identifier=namespace, confirmed=True)
            require(
                BrandCompany.objects.filter(
                    company_id=org.company_id,
                    brand_id=job.definition["scope"]["brand_id"],
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
            if head is None:
                result = client.model_group(identifier, "detail")
                if result.outcome != "ok":
                    raise SourceError(result.outcome)
                data = result.payload
                require(
                    isinstance(data, dict) and isinstance(data.get("sha"), str),
                    "native HF head revision required",
                )
                from django.utils import timezone

                observed_at = timezone.now()

                def capture_head(
                    run,
                    scoped,
                    identifier=identifier,
                    data=data,
                    observed_at=observed_at,
                ):
                    observation = _native_record(
                        run,
                        scoped,
                        identifier,
                        "hf_metadata",
                        data,
                        metadata={
                            "revision": data["sha"],
                            "historical_public_visibility_proven": False,
                        },
                    )
                    observation.observed_at = observed_at
                    observation.save(update_fields=["observed_at", "updated_at"])
                    if job.definition["scope"].get("numeric_contract_id"):
                        from core.models import MetricCollectionContract
                        from core.source_metric_projection import enqueue_projection

                        contract = MetricCollectionContract.objects.get(
                            pk=job.definition["scope"]["numeric_contract_id"]
                        )
                        if any(
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

                checkpoint_scope(
                    claim,
                    scope_kind="hf_history_head",
                    scope_key=identifier,
                    ownership=ownership,
                    enumeration_complete=True,
                    outcome="observed",
                    envelopes=[
                        {
                            "revision": data["sha"],
                            "attempts": json.loads(json.dumps(result.attempts)),
                        }
                    ],
                    write=capture_head,
                )
                revision = data["sha"]
            else:
                revision = head.envelopes[0]["revision"]
            for kind in ("commits", "tree"):
                if kind == "tree":
                    commits = CollectionObservation.objects.filter(
                        run_id=claim.run_id,
                        source_identifier=identifier,
                        dimensions__kind="hf_commits",
                    )
                    dated_head = _latest_before_cutoff(
                        commits,
                        lambda o: o.source_metadata.get("source_record_date"),
                        aware_instant(job.definition["scope"]["cutoff"]),
                    )
                    if dated_head is None:
                        checkpoint_scope(
                            claim,
                            scope_kind="hf_repository_history",
                            scope_key=identifier + ":tree",
                            ownership=ownership,
                            enumeration_complete=True,
                            outcome="history_unavailable",
                            envelopes=[{"reason": "no_qualified_commit_at_cutoff"}],
                        )
                        continue
                    revision = dated_head.listing["id"]
                key = identifier + ":" + kind
                scoped = (
                    CollectionRun.objects.get(pk=claim.run_id)
                    .scopes.filter(scope_kind="hf_repository_history", scope_key=key)
                    .first()
                )
                while scoped is None or not scoped.enumeration_complete:
                    if items[0] >= job.definition["budgets"]["items"]:
                        raise SourceError("item_cap")
                    result = client.history_page(
                        identifier, revision, kind, scoped.cursor if scoped else None
                    )
                    if result.outcome != "ok":
                        raise SourceError(result.outcome)
                    require(
                        len(result.payload)
                        <= job.definition["budgets"]["items"] - items[0],
                        "HF history item budget exceeded",
                    )
                    history = [
                        *(scoped.cursor_history if scoped else []),
                        scoped.cursor if scoped and scoped.cursor else "first",
                    ]
                    require(
                        result.next_cursor is None or result.next_cursor not in history,
                        "HF history cursor loop",
                    )

                    def write(
                        run,
                        scope,
                        rows=result.payload,
                        kind=kind,
                        identifier=identifier,
                        revision=revision,
                    ):
                        for row in rows:
                            _native_record(
                                run,
                                scope,
                                identifier,
                                "hf_" + kind,
                                row,
                                metadata={
                                    "revision": revision,
                                    "source_record_date": row.get("date"),
                                    "historical_public_visibility_proven": False,
                                },
                            )

                    scoped = checkpoint_scope(
                        claim,
                        scope_kind="hf_repository_history",
                        scope_key=key,
                        ownership=ownership,
                        cursor=result.next_cursor,
                        cursor_history=history,
                        enumeration_complete=result.next_cursor is None,
                        outcome="observed" if result.next_cursor is None else "partial",
                        write=write,
                        envelopes=[
                            *(scoped.envelopes if scoped else []),
                            {"revision": revision, "attempts": result.attempts},
                        ],
                    )
                    items[0] += len(result.payload)
    finally:
        budget.remaining = before - client.requests
        budget.total_bytes_read += client.bytes_received
