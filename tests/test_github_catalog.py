"""Documentation-derived responses traverse client, command and real DB storage.

Fixtures are deterministic API-schema examples, not claimed live captures.
"""

import json
from datetime import timedelta
from io import StringIO

import httpx
import pytest
from django.core.management import call_command
from django.utils import timezone

from core.collection_capture import observation_object_documents, run_report_document
from core.collection_jobs import register_job, set_job_state
from core.collection_state import StaleClaim, claim_job
from core.github_catalog import execute_github_catalog
from core.github_metadata_client import GitHubMetadataClient
from core.models import CollectionObservation, CollectionRun, MetricValue
from scripts.benchmark_download_collector.sources import Budget
from tests.test_collection_identity import identities

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def configured():
    _, account, _, repo = identities()
    source = account.data_source
    source.enabled, source.adapter_key = True, "github-catalog-v1"
    source.save()
    obj = register_job(
        job_key="github-catalog",
        source=source,
        purpose="catalog",
        operation="github_catalog",
        mode="manual",
        definition={
            "version": 1,
            "scope": {
                "publishers": [
                    {
                        "account_key": str(account.pk),
                        "native_id": "42",
                        "login": "publisher",
                        "account_kind": "organization",
                    }
                ]
            },
            "schedule": {"kind": "manual", "driver": "manual"},
            "budgets": {"requests": 30, "bytes": 100000, "seconds": 60, "items": 100},
        },
    )
    return set_job_state(obj.pk, "ready"), repo


def responses(repo, seen):
    def handle(request):
        seen.append(str(request.url))
        path = request.url.path
        if path == "/users/publisher":
            return httpx.Response(
                200, json={"id": 42, "login": "publisher", "type": "Organization"}
            )
        if path == "/repos/" + repo["full_name"]:
            return httpx.Response(200, json=repo)
        if path == "/orgs/publisher/repos":
            if request.url.params.get("page") == "2":
                return httpx.Response(200, json=[])
            return httpx.Response(
                200,
                json=[{**repo, "created_at": "2026-08-01T00:00:00Z"}],
                headers={
                    "Link": '<https://api.github.com/orgs/publisher/repos?page=2&per_page=100>; rel="next"',
                    "ETag": '"page1"',
                },
            )
        if path.endswith("/releases"):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": n,
                        "published_at": "2026-09-01T00:00:00Z",
                        "updated_at": "2026-09-01T00:00:00Z",
                        "draft": False,
                    }
                    for n in (1, 2)
                ],
            )
        if path.endswith("/commits"):
            return httpx.Response(
                200,
                json=[
                    {
                        "sha": c * 40,
                        "commit": {
                            "author": {"date": "2026-09-02T00:00:00Z"},
                            "committer": {"date": "2026-09-03T00:00:00Z"},
                            "tree": {"sha": "c" * 40},
                        },
                    }
                    for c in ("a", "b")
                ],
            )
        if path.endswith("/tags"):
            return httpx.Response(200, json=[])
        if "/git/trees/" in path:
            assert path.endswith("c" * 40), (
                "tree requests must use the recorded tree SHA"
            )
            return httpx.Response(
                200,
                json={
                    "sha": "c" * 40,
                    "truncated": False,
                    "tree": [
                        {
                            "path": "README.md",
                            "sha": "d" * 40,
                            "type": "blob",
                            "size": 2,
                        }
                    ],
                },
            )
        if "/contents/" in path:
            return httpx.Response(
                200,
                json={
                    "type": "file",
                    "encoding": "base64",
                    "size": 2,
                    "sha": "d" * 40,
                    "content": "e30=",
                },
            )
        raise AssertionError("unexpected endpoint")

    return handle


def reader(handler, requests):
    return GitHubMetadataClient(
        Budget(
            httpx.Client(transport=httpx.MockTransport(handler)),
            max_requests=requests,
            max_bytes=100000,
        )
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("enabled", [False, True])
def test_public_release_capture_hands_off_to_dossier_detection(settings, monkeypatch, enabled):
    from django.db import transaction

    from core import models
    from core.product_release_source_queue import (
        drain_observations,
        enqueue_github_release,
        enqueue_saved_observations,
    )

    settings.PRODUCT_RELEASE_BACKGROUND_ENABLED = enabled
    wakes = []
    monkeypatch.setattr("core.product_release_acquisition.dispatch_due_recovery", lambda: wakes.append(True))
    job, repo = configured()
    seen = []
    original = responses(repo, seen)

    def respond(request):
        if request.url.path.endswith("/releases"):
            seen.append(str(request.url))
            return httpx.Response(200, json=[
                {"id": 1, "tag_name": "v1.0", "name": "Agent 1.0",
                 "body": "Release of Agent 1.0", "draft": False,
                 "published_at": "2026-09-01T00:00:00Z",
                 "html_url": "https://github.com/publisher/family/releases/tag/v1.0"},
                {"id": 2, "tag_name": "draft", "draft": True,
                 "published_at": "2026-09-01T00:00:00Z"},
                {"id": 3, "draft": False, "published_at": "2026-09-01T01:00:00Z"},
            ])
        return original(request)

    run = execute_github_catalog(job.pk, client=reader(respond, 30))
    assert run.status == "success"
    collection_scopes = run.scopes.exclude(scope_kind__in={"numeric_projection_item", "catalog_execution", "release_detection"})
    assert run.selected_count == collection_scopes.count()
    assert run.success_count == collection_scopes.filter(enumeration_complete=True).count()
    release = run.observations.get(observation_kind="releases", resource_snapshot__native_stable_id="1")
    no_tag = run.observations.get(observation_kind="releases", resource_snapshot__native_stable_id="3")
    markers = models.CollectionScopeRun.objects.filter(scope_kind="release_detection")
    assert markers.count() == 2 * int(enabled)
    assert len(wakes) == int(enabled)
    if not enabled:
        assert not models.EventDossier.objects.exists()
        with pytest.raises(RuntimeError), transaction.atomic():
            enqueue_github_release(release)
            raise RuntimeError("abort capture")
        assert not markers.exists()
        selected = enqueue_saved_observations([
            release.pk, release.pk, 999999999, release.scope_run.resource_observation_id,
        ])
        assert [row["outcome"] for row in selected["observations"]] == ["pending", "missing", "ineligible"]
        assert drain_observations(observation_ids=[release.pk])["candidates"] == 1
        assert not wakes
        return
    marker = markers.get(resource_observation=release)
    assert marker.resource_observation_id == release.pk and marker.outcome == "pending"
    prior_calls = len(seen)
    import threading

    from django.db import connection

    from core.event_dossiers import _digest

    locked, unlock = threading.Event(), threading.Event()
    lock_key = int(_digest(["github-release-detection-v1", "123", "1"])[:15], 16)
    def hold_identity():
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_key])
            locked.set()
            assert unlock.wait(10)
    worker = threading.Thread(target=hold_identity)
    worker.start()
    try:
        assert locked.wait(5)
        busy = drain_observations(observation_ids=[release.pk])
        assert busy["busy"] == 1 and busy["failed"] == 0 and busy["due_remaining"]
        marker.refresh_from_db()
        assert marker.raw_count == 0 and marker.retry_at is None
    finally:
        unlock.set()
        worker.join(10)
    assert not worker.is_alive()
    from core import product_release_pipeline

    original_persist = product_release_pipeline.persist_source
    def transient_failure(_source):
        raise RuntimeError("temporary detection failure")
    monkeypatch.setattr(product_release_pipeline, "persist_source", transient_failure)
    failed = drain_observations(observation_ids=[release.pk])
    marker.refresh_from_db()
    assert failed["failed"] == 1 and marker.raw_count == 1 and marker.retry_at is not None
    assert not models.EventDossier.objects.exists()
    models.CollectionScopeRun.objects.filter(pk=marker.pk).update(retry_at=timezone.now() - timedelta(seconds=1))
    monkeypatch.setattr(product_release_pipeline, "persist_source", original_persist)
    result = drain_observations(observation_ids=[release.pk])
    assert result["processed"] == result["candidates"] == 1
    assert not result["due_remaining"] and len(seen) == prior_calls
    dossier = models.EventDossier.objects.get(event_kind_reference__code="product_release")
    assert dossier.sources.filter(collection_observation=release).exists()
    assert dossier.sources.filter(collection_observation=release.scope_run.resource_observation).exists()
    assert dossier.sources.filter(claims__scope_key__startswith="github_repository:").exists()
    published = dossier.sources.get(collection_observation=release).claims.get(scope_key__startswith="github_published:")
    assert published.effective_at == release.published_at and published.effective_precision == "datetime"
    assert not models.ProductReleaseDetail.objects.exists()
    assert drain_observations(observation_ids=[release.pk])["processed"] == 0
    assert markers.get(resource_observation=no_tag).outcome == "pending"
    assert drain_observations(observation_ids=[no_tag.pk])["candidates"] == 1
    assert models.EventDossier.objects.filter(event_kind_reference__code="product_release").count() == 2
    assert len(seen) == prior_calls
    # A later collector run sees the same native release IDs in new observation
    # rows. They must add source evidence, not make duplicate dossiers.
    later_job = register_job(job_key="github-catalog-next", source=job.source, purpose="catalog",
                             operation="github_catalog", mode="manual", definition=job.definition)
    set_job_state(later_job.pk, "ready")
    later_run = execute_github_catalog(later_job.pk, client=reader(respond, 30))
    later_releases = list(later_run.observations.filter(observation_kind="releases").order_by("pk"))
    assert len(later_releases) == 2 and len(wakes) == 2
    calls_after_collection = len(seen)
    assert drain_observations(observation_ids=[row.pk for row in later_releases])["candidates"] == 2
    assert len(seen) == calls_after_collection
    assert models.EventDossier.objects.filter(event_kind_reference__code="product_release").count() == 2
    assert dossier.sources.filter(collection_observation__observation_kind="releases").count() == 2
    marker.refresh_from_db()
    assert marker.outcome == "complete" and marker.enumeration_complete


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("role,linked,late", [
    ("dedicated_product", True, False), ("dedicated_product", True, True),
    ("family_repository", False, False),
])
def test_catalog_release_reuses_only_reviewed_dedicated_product(settings, role, linked, late):
    from core import models
    from core.collection_identity import review_github_mapping
    from core.product_release_source_queue import drain_observations, enqueue_saved_observations

    settings.PRODUCT_RELEASE_BACKGROUND_ENABLED = False
    job, repo = configured()
    subject = models.MeasurementSubject.objects.get(subject_kind="product", product__repo_id="HFPublisher/Model")
    run = execute_github_catalog(job.pk, client=reader(responses(repo, []), 30))
    release = run.observations.filter(observation_kind="releases").first()
    repository = release.scope_run.resource_observation
    if late:
        enqueue_saved_observations([release.pk])
        assert drain_observations(observation_ids=[release.pk])["processed"] == 1
        release.refresh_from_db()
        assert release.product_id is None
        assert enqueue_saved_observations([release.pk])["observations"][0]["outcome"] == "complete"
    mapping = review_github_mapping(subject=subject, repo=repo, role=role,
        version_selector="v2" if role == "family_repository" else None,
        evidence_url="https://github.com/publisher/family", reviewed_by="reviewer")
    enqueue_saved_observations([release.pk], reconcile=late)
    assert drain_observations(observation_ids=[release.pk])["processed"] == 1
    for observation in (repository, release):
        observation.refresh_from_db()
        assert observation.product_id == (subject.product.pk if linked else None)
        assert observation.mapping_id == (mapping.pk if linked else None)
    assert not models.ProductReleaseDetail.objects.exists()
    assert models.Product.objects.count() == 1
    assert models.EventDossier.objects.filter(event_kind_reference__code="product_release").count() == 1


@pytest.fixture
def captured_release_assets():
    from copy import deepcopy

    base, repo = configured()
    definition = deepcopy(base.definition)
    definition["scope"]["include_release_assets"] = True
    job = register_job(
        job_key="asset-parent-proof", source=base.source, purpose="catalog",
        operation="github_catalog", mode="manual", definition=definition,
    )
    set_job_state(job.pk, "ready")
    seen = []
    original = responses(repo, seen)

    def respond(request):
        if request.url.path.endswith("/assets"):
            seen.append(str(request.url))
            release_id = int(request.url.path.split("/")[-2])
            return httpx.Response(200, json=[{
                "id": 70 + release_id, "name": "weights.bin", "size": 1024,
                "download_count": release_id * 10,
            }])
        return original(request)

    run = execute_github_catalog(job.pk, client=reader(respond, 30))
    assert run.status == "success"
    return run, repo


def test_release_assets_keep_typed_publisher_and_distinct_release_parents(monkeypatch, captured_release_assets):
    from core.benchmark_metric_identity import register_definitions
    from core.collection_capture import observation_object_documents
    from core.measurement_taxonomy import configure_taxonomy, subject_id
    from core.models import Account, TimeZone
    from core.source_metric_projection import configure_source_statistics, evidence_rows
    from tests.test_benchmark_use_policy import decision
    from tests.test_source_metric_projection import project

    run, repo = captured_release_assets
    assets = list(run.observations.filter(observation_kind="release_asset").order_by("pk"))
    assert len(assets) == 2
    publisher = Account.objects.get(data_source_id="github", normalized_identifier="42")
    expected_parents = {}
    for asset in assets:
        edge = asset.inputs.get(input_role="release_asset_parent")
        release = edge.input_observation
        release_id = int(asset.inputs.get(input_role="release_asset_parent").row_locator)
        assert release.observation_kind == "releases"
        assert release.resource_snapshot.native_stable_id == str(release_id)
        assert release.source_identifier == asset.source_identifier == str(repo["id"])
        assert edge.input_sha256 == release.observation_key
        assert asset.resource_snapshot.native_stable_id == str(70 + release_id)
        assert asset.resource_snapshot.publisher_account_id == publisher.pk
        expected_parents[asset.pk] = release.pk
    assert len(set(expected_parents.values())) == 2
    publisher.data_source.metadata = {
        "use_policy": {use: decision() for use in ("collection", "retention")},
    }
    publisher.data_source.save(update_fields=["metadata"])
    taxonomy = configure_taxonomy({
        "reviewed_by": "fixture", "subjects": [{"kind": "account", "key": str(publisher.pk)}],
    })
    TimeZone.objects.get_or_create(pk="UTC")
    register_definitions()
    contract = configure_source_statistics({
        "taxonomy_version": str(taxonomy.pk), "reviewed_by": "fixture",
        "mappings": [{
            "source": "github", "source_subject_kind": "account",
            "identifier_scope": publisher.account_kind,
            "external_identifier": publisher.normalized_identifier,
            "subject_id": str(subject_id("account", publisher.pk)),
            "publisher_account_key": str(publisher.pk),
            "evidence_url": "https://example.com/publisher",
        }],
        "source_configuration": {"github": {"metrics": ["asset_downloads", "asset_size_bytes"]}},
    })
    with monkeypatch.context() as old_selector:
        old_selector.setattr("core.source_metric_projection._evidence_documents", observation_object_documents)
        original_rows = [list(evidence_rows(contract, "github", asset)) for asset in assets]
    assert [list(evidence_rows(contract, "github", asset)) for asset in assets] == original_rows
    first = project(contract, "github", assets[:1], key="asset-original")
    assert first.status == "success", run_report_document(first)
    before = list(MetricValue.objects.order_by("pk").values())
    assert len(before) == 2
    run.observations.update(listing={}, source_metadata={}, dimensions={})
    for asset in run.observations.filter(observation_kind="release_asset"):
        assert asset.inputs.get(input_role="release_asset_parent").input_observation_id == expected_parents[asset.pk]
        assert asset.resource_snapshot.publisher_account_id == publisher.pk
    refreshed_assets = list(run.observations.filter(observation_kind="release_asset").order_by("pk"))
    assert [list(evidence_rows(contract, "github", asset)) for asset in refreshed_assets] == original_rows
    monkeypatch.setattr(httpx, "Client", lambda *a, **kw: pytest.fail("HTTP during replay"))
    replay = project(contract, "github", refreshed_assets, key="asset-after-clear")
    assert replay.status == "success", run_report_document(replay)
    # The first asset is idempotent; the pending second asset gets its first
    # measurements only after all retiring observation documents are cleared.
    assert run_report_document(replay)["projection"]["written_values"] == 2
    assert list(MetricValue.objects.filter(
        pk__in=[row["id"] for row in before],
    ).order_by("pk").values()) == before
    assert sorted(MetricValue.objects.filter(
        source_metric__metric_key="asset_downloads",
    ).values_list("integer_value", flat=True)) == [10, 20]
    assert not run.observations.filter(values__isnull=False).exists()
    after = list(MetricValue.objects.order_by("pk").values())
    repeated = project(contract, "github", refreshed_assets, key="asset-idempotent")
    assert repeated.status == "success", run_report_document(repeated)
    assert run_report_document(repeated)["projection"]["written_values"] == 0
    assert list(MetricValue.objects.order_by("pk").values()) == after


@pytest.mark.parametrize("corruption, message", [
    ("missing_parent", "one captured release parent"),
    ("parent_coordinate", "release parent identity mismatch"),
    ("parent_repository", "release parent identity mismatch"),
    ("parent_hash", "release parent identity mismatch"),
    ("reply_hash", "response identity mismatch"),
    ("payload_hash", "absent or conflicting"),
])
def test_asset_replay_refuses_conflicting_typed_evidence(captured_release_assets, corruption, message):
    from core.github_resource_evidence import asset_documents

    run, _ = captured_release_assets
    asset = run.observations.filter(observation_kind="release_asset").first()
    parent = asset.inputs.get(input_role="release_asset_parent")
    if corruption == "missing_parent":
        parent.delete()
    elif corruption == "parent_coordinate":
        type(parent).objects.filter(pk=parent.pk).update(row_locator="999")
    elif corruption == "parent_repository":
        type(asset).objects.filter(pk=parent.input_observation_id).update(source_identifier="999")
    elif corruption == "parent_hash":
        type(parent).objects.filter(pk=parent.pk).update(input_sha256="a" * 64)
    elif corruption == "reply_hash":
        asset.inputs.filter(input_request__isnull=False).update(input_sha256="a" * 64)
    elif corruption == "payload_hash":
        asset.payload_sha256 = "a" * 64
    with pytest.raises(ValueError, match=message):
        asset_documents(asset)


def test_two_page_inventory_resumes_and_distinct_events_keep_native_clocks():
    obj, repo = configured()
    seen = []
    first = execute_github_catalog(obj.pk, client=reader(responses(repo, seen), 2))
    assert first.status == "partial"
    scope = first.scopes.get(scope_kind="publisher_repos")
    assert "page=2" in scope.cursor and not scope.enumeration_complete
    second = execute_github_catalog(obj.pk, client=reader(responses(repo, seen), 20))
    assert second.pk == first.pk and second.status == "success"
    assert (
        sum("/orgs/publisher/repos?" in url and "page=2" not in url for url in seen)
        == 1
    )
    releases = second.observations.filter(observation_kind="releases")
    commits = second.observations.filter(observation_kind="commits")
    assert releases.count() == 2 and commits.count() == 2
    assert releases.first().publication_precision == "instant"
    assert (
        commits.first().resource_snapshot.authored_at
        != commits.first().resource_snapshot.committed_at
    )
    assert MetricValue.objects.count() == 0
    assert second.attempts.count() == 2
    assert sum(attempt.requests.count() for attempt in second.attempts.all()) == len(
        seen
    )
    assert (
        commits.first().resource_snapshot.authored_at
        != commits.first().resource_snapshot.committed_at
    )


def test_native_repository_commit_pagination_checkpoints_and_resumes():
    obj, repo = configured()
    seen = []
    ordinary = responses(repo, seen)
    continuation = "https://api.github.com/repositories/123/commits?per_page=100&page=2"

    def response(request):
        if request.url.path in {
            "/repos/publisher/family/commits",
            "/repositories/123/commits",
        }:
            seen.append(str(request.url))
            second = request.url.path == "/repositories/123/commits"
            return httpx.Response(
                200,
                json=[
                    {
                        "sha": ("b" if second else "a") * 40,
                        "commit": {
                            "author": {"date": "2026-09-02T00:00:00Z"},
                            "tree": {"sha": "c" * 40},
                        },
                    }
                ],
                headers={} if second else {"Link": f'<{continuation}>; rel="next"'},
            )
        return ordinary(request)

    first = execute_github_catalog(obj.pk, client=reader(response, 7))
    assert first.status == "partial" and first.error_code == "request_cap"
    scope = first.scopes.get(scope_key="123:commits")
    assert scope.cursor == continuation and not scope.enumeration_complete
    original = first.observations.get(observation_kind="commits")
    assert observation_object_documents(original)[0]["sha"] == "a" * 40

    second = execute_github_catalog(obj.pk, client=reader(response, 20))
    assert second.pk == first.pk and second.status == "success"
    assert second.observations.filter(observation_kind="commits").count() == 2
    original.refresh_from_db()
    assert observation_object_documents(original)[0]["sha"] == "a" * 40
    assert seen.count(continuation) == 1
    assert sum("/repos/publisher/family/commits?" in url for url in seen) == 1
    assert MetricValue.objects.count() == 0


def test_numeric_queue_items_do_not_inflate_github_scope_counts():
    from core.models import TimeZone
    from tests.test_source_metric_projection import configured as statistics

    contract, repo, _, _ = statistics("github")
    TimeZone.objects.get_or_create(pk="UTC")
    publisher = contract.mappings.get(source_subject_kind="account").subject.account
    job = register_job(
        job_key="github-typed-queue", source=publisher.data_source,
        purpose="catalog", operation="github_catalog", mode="manual",
        definition={
            "version": 1,
            "scope": {
                "publishers": [{
                    "account_key": str(publisher.pk), "native_id": "42",
                    "login": "publisher", "account_kind": "organization",
                }],
                "numeric_contract_id": str(contract.pk), "include_release_assets": False,
            },
            "schedule": {"kind": "manual", "driver": "manual"},
            "budgets": {"requests": 30, "bytes": 100000, "seconds": 60, "items": 100},
        },
    )
    set_job_state(job.pk, "ready")
    run = execute_github_catalog(job.pk, client=reader(responses(repo, []), 30))
    assert run.status == "success", run_report_document(run)
    assert run.selected_count == run.success_count == 9
    assert run.scopes.filter(scope_kind="numeric_projection_item", outcome="complete").count() == 2
    assert MetricValue.objects.count() == 6


def test_dry_run_command_never_constructs_provider_or_writes(monkeypatch):
    obj, _ = configured()
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **_: (_ for _ in ()).throw(AssertionError("provider constructed")),
    )
    output = StringIO()
    call_command("collect_github_catalog", job=str(obj.pk), stdout=output)
    assert json.loads(output.getvalue())["writes"] == 0
    assert CollectionRun.objects.count() == 0


def test_rate_limit_retains_checkpoint_and_cooldown():
    obj, repo = configured()
    seen = []

    def response(request):
        if request.url.path.endswith("/repos"):
            return httpx.Response(429, headers={"Retry-After": "300"})
        return responses(repo, seen)(request)

    run = execute_github_catalog(obj.pk, client=reader(response, 20))
    obj.refresh_from_db()
    assert run.status == "partial" and obj.next_retry_at is not None
    assert run.scopes.get(scope_kind="publisher_repos").cursor is None
    assert run.scopes.get(scope_kind="publisher_repos").outcome == "http_429"


def test_command_executes_same_fixture_to_database_path(monkeypatch):
    obj, repo = configured()
    seen = []
    original = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **_: original(transport=httpx.MockTransport(responses(repo, seen))),
    )
    output = StringIO()
    call_command("collect_github_catalog", job=str(obj.pk), execute=True, stdout=output)
    run = CollectionRun.objects.get(pk=json.loads(output.getvalue())["run_id"])
    assert run.status == "success" and run.observations.count() > 4
    assert CollectionObservation.objects.filter(
        run=run, source_identifier="123"
    ).exists()


def test_not_modified_page_reuses_evidence_without_treating_inventory_as_empty():
    obj, repo = configured()
    initial = execute_github_catalog(obj.pk, client=reader(responses(repo, []), 20))
    assert initial.status == "success"
    initial.scopes.update(envelopes=[])

    def response(request):
        if (
            request.url.path == "/orgs/publisher/repos"
            and request.url.params.get("page") is None
        ):
            assert request.headers["if-none-match"] == '"page1"'
            return httpx.Response(304, headers={"ETag": '"page1"'})
        return responses(repo, [])(request)

    later = execute_github_catalog(obj.pk, client=reader(response, 20))
    assert later.status == "success"
    captured = later.observations.get(observation_kind="repository")
    assert str(captured.inputs.get(input_role="cached_response").input_observation.run_id) == str(initial.pk)
    assert later.scopes.get(scope_kind="publisher_repos").raw_count == 1
    prior = initial.observations.get(observation_kind="repository")
    assert captured.observed_at == prior.observed_at
    reused_input = captured.inputs.get(input_role="cached_response")
    assert reused_input.input_observation_id == prior.pk
    validation = captured.inputs.get(input_role="cache_validation").input_request
    assert validation.http_status == 304 and validation.archive_id is None
    assert validation.scope_run.run_id == later.pk
    assert captured.input_set_sha256 and captured.values.count() == 0
    assert validation.etag == validation.response_etag == '"page1"'
    later.scopes.update(envelopes=[])
    third = execute_github_catalog(obj.pk, client=reader(response, 20))
    assert third.status == "success"
    newest = third.observations.get(observation_kind="repository")
    assert newest.observed_at == prior.observed_at
    assert newest.inputs.get(input_role="cached_response").input_observation_id == captured.pk
    assert newest.inputs.get(input_role="cache_validation").input_request.http_status == 304


def test_late_provider_response_cannot_write_after_reclaim():
    obj, repo = configured()
    successor = []

    def response(request):
        if request.url.path == "/orgs/publisher/repos":
            obj.refresh_from_db()
            CollectionRun.objects.filter(pk=obj.active_run_id).update(
                lease_expires_at=timezone.now() - timedelta(seconds=1)
            )
            successor.append(claim_job(obj.pk))
        return responses(repo, [])(request)

    with pytest.raises(StaleClaim):
        execute_github_catalog(obj.pk, client=reader(response, 20))
    obj.refresh_from_db()
    assert obj.active_run_id == successor[0].run_id
    assert (
        CollectionObservation.objects.filter(observation_kind="repository").count() == 0
    )


def test_catalog_resume_rechecks_access_before_using_cached_public_inventory():
    obj, repo = configured()
    seen = []
    private = [False]
    fallback = responses(repo, seen)

    def response(request):
        if request.url.path == "/repos/" + repo["full_name"]:
            seen.append(str(request.url))
            return httpx.Response(200, json={**repo, "private": private[0]})
        assert not private[0], "content fetched from now-private cached repository"
        return fallback(request)

    first = execute_github_catalog(obj.pk, client=reader(response, 3))
    assert first.status == "partial"
    repositories = list(first.observations.filter(observation_kind="repository"))
    assert repositories
    # Resume uses the public body and typed ownership even with no old documents.
    first.observations.update(listing={}, dimensions={}, source_metadata={})
    private[0] = True
    run = execute_github_catalog(obj.pk, client=reader(response, 20))
    assert (
        run.scopes.get(scope_kind="repository_access", scope_key="123").outcome
        == "inaccessible"
    )
    assert not run.observations.filter(observation_kind="releases").exists()


def test_authenticated_draft_releases_never_enter_saved_public_evidence():
    obj, repo = configured()
    seen = []
    fallback = responses(repo, seen)

    def response(request):
        if request.url.path == "/repos/" + repo["full_name"]:
            return httpx.Response(200, json=repo)
        result = fallback(request)
        if request.url.path.endswith("/releases"):
            return httpx.Response(
                200,
                json=[
                    *result.json(),
                    {
                        "id": 99,
                        "draft": True,
                        "published_at": None,
                        "body": "UNPUBLISHED_SENTINEL",
                    },
                ],
            )
        return result

    run = execute_github_catalog(obj.pk, client=reader(response, 30))
    assert run.status == "success"
    assert run.observations.filter(observation_kind="releases").count() == 2
    for scope in run.scopes.all():
        assert "UNPUBLISHED_SENTINEL" not in json.dumps(scope.envelopes)
    for row in run.observations.all():
        assert "UNPUBLISHED_SENTINEL" not in json.dumps(observation_object_documents(row)[0])
    from core.models import CollectionEvidenceArchive

    assert CollectionEvidenceArchive.objects.exists()
    assert all(
        b"UNPUBLISHED_SENTINEL" not in bytes(archive.body)
        for archive in CollectionEvidenceArchive.objects.all()
    )
