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
    releases = second.observations.filter(dimensions__kind="releases")
    commits = second.observations.filter(dimensions__kind="commits")
    assert releases.count() == 2 and commits.count() == 2
    assert releases.first().publication_precision == "instant"
    assert (
        commits.first().source_metadata["clocks"]["author_at"]
        != commits.first().source_metadata["clocks"]["committer_at"]
    )
    assert MetricValue.objects.count() == 0


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
    captured = later.observations.get(dimensions__kind="repository")
    assert captured.source_metadata["reused_from"]["run_id"] == str(initial.pk)
    assert later.scopes.get(scope_kind="publisher_repos").raw_count == 1


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
        CollectionObservation.objects.filter(dimensions__kind="repository").count() == 0
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
    private[0] = True
    run = execute_github_catalog(obj.pk, client=reader(response, 20))
    assert (
        run.scopes.get(scope_kind="repository_access", scope_key="123").outcome
        == "inaccessible"
    )
    assert not run.observations.filter(dimensions__kind="releases").exists()


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
    assert run.observations.filter(dimensions__kind="releases").count() == 2
    for scope in run.scopes.all():
        assert "UNPUBLISHED_SENTINEL" not in json.dumps(scope.envelopes)
    for row in run.observations.all():
        assert "UNPUBLISHED_SENTINEL" not in json.dumps(row.listing)
