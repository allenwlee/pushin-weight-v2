"""Real GitHub acquisition and saved evidence reach native numeric storage."""

import copy

import httpx
import pytest

from core.collection_jobs import register_job, set_job_state
from core.github_catalog import execute_github_catalog
from core.models import MetricValue, TimeZone
from core.source_metric_projection import configure_source_statistics
from tests.test_github_catalog import reader, responses
from tests.test_source_metric_projection import configured, evidence, project

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


@pytest.fixture(autouse=True)
def seed_utc_timezone():
    TimeZone.objects.get_or_create(pk="UTC")


def source_job(*, role="inventory", key="fresh", requests=30):
    _, repo, product, spec = configured("github")
    spec["source_configuration"]["github"]["metrics"] += [
        "repository_size_kb",
        "asset_size_bytes",
        "followers",
        "following",
        "public_repos",
    ]
    contract = configure_source_statistics(spec)
    account = product.brand.accounts.get(role_id="official").account
    obj = register_job(
        job_key=key,
        source=account.data_source,
        purpose="catalog",
        operation="github_catalog",
        mode="manual",
        definition={
            "version": 1,
            "scope": {
                "numeric_contract_id": str(contract.pk),
                "github_role": role,
                "publishers": [
                    {
                        "account_key": str(account.pk),
                        "native_id": "42",
                        "login": "publisher",
                        "account_kind": "organization",
                    }
                ],
            },
            "schedule": {"kind": "manual", "driver": "manual"},
            "budgets": {
                "requests": requests,
                "bytes": 200000,
                "seconds": 60,
                "items": 100,
            },
        },
    )
    return set_job_state(obj.pk, "ready"), repo, contract


def fresh_responses(repo, seen, *, assets=False):
    def response(request):
        seen.append(str(request.url))
        path = request.url.path
        if path == "/users/publisher":
            return httpx.Response(
                200,
                json={
                    "id": 42,
                    "login": "publisher",
                    "type": "Organization",
                    "followers": 8,
                    "following": 0,
                    "public_repos": 1,
                },
            )
        if path == "/orgs/publisher/repos":
            return httpx.Response(200, json=[repo])
        if path == "/repos/publisher/family":
            return httpx.Response(
                200, json={**repo, "subscribers_count": 7, "size": 10}
            )
        if assets and path.endswith("/releases"):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 5,
                        "draft": False,
                        "published_at": "2026-10-01T00:00:00Z",
                        "assets": [],
                    }
                ],
            )
        if assets and path.endswith("/releases/5/assets"):
            second = request.url.params.get("page") == "2"
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 502 if second else 501,
                        "size": 100,
                        "download_count": 0 if second else 4,
                    }
                ],
                headers={}
                if second
                else {
                    "Link": '<https://api.github.com/repositories/123/releases/5/assets?page=2&per_page=100>; rel="next"'
                },
            )
        raise AssertionError(
            "fresh discovery must not enter deep history or download binaries: " + path
        )

    return response


def test_fresh_inventory_writes_repo_account_numbers_and_preserves_access_payload():
    obj, repo, _ = source_job()
    seen = []
    run = execute_github_catalog(obj.pk, client=reader(fresh_responses(repo, seen), 30))
    assert run.status == "success"
    access = run.observations.get(dimensions__kind="repository_access")
    assert access.listing["subscribers_count"] == 7
    values = MetricValue.objects.filter(observation__run__job__source_id="github")
    assert set(values.values_list("source_metric__metric_key", flat=True)) >= {
        "stars",
        "forks",
        "open_issues",
        "subscribers",
        "followers",
        "repository_size_kb",
    }
    assert (
        values.filter(source_metric__metric_key="subscribers").get().integer_value == 7
    )
    assert not values.filter(observation__product__isnull=False).exists()
    assert {
        v.source_metric.metric_key: v.integer_value
        for v in values.filter(observation__source_subject_kind="account")
    } == {"followers": 8, "following": 0, "public_repos": 1}
    assert len(seen) == 3


def test_release_assets_paginate_and_stay_distinct_without_binary_requests():
    obj, repo, _ = source_job(role="release_watch")
    repo["watchers_count"] = 99  # This stars alias must never become subscribers.
    seen = []
    run = execute_github_catalog(
        obj.pk, client=reader(fresh_responses(repo, seen, assets=True), 30)
    )
    assert run.status == "success"
    assets = run.observations.filter(dimensions__kind="release_asset")
    assert set(assets.values_list("dimensions__asset_id", flat=True)) == {501, 502}
    downloads = MetricValue.objects.filter(source_metric__metric_key="asset_downloads")
    assert sorted(downloads.values_list("integer_value", flat=True)) == [0, 4]
    assert {v.observation.dimensions["asset_id"] for v in downloads} == {501, 502}
    assert set(
        MetricValue.objects.filter(source_metric__metric_key="stars").values_list(
            "integer_value", flat=True
        )
    ) == {3}
    assert len(seen) == 6


def test_saved_140_repository_listings_replay_420_values_without_http(monkeypatch):
    contract, repo, _, _ = configured("github")
    saved = [
        evidence("github", {**repo, "id": 1000 + i, "full_name": f"publisher/model{i}"})
        for i in range(140)
    ]
    monkeypatch.setattr(
        httpx, "Client", lambda **_: pytest.fail("replay constructed a provider client")
    )
    first = project(contract, "github", saved[:100])
    tail = project(contract, "github", saved[100:], key="projection-tail")
    assert (
        first.report["projection"]["written_values"]
        + tail.report["projection"]["written_values"]
        == 420
    )
    assert MetricValue.objects.count() == 420
    second = project(contract, "github", saved[:100], key="replay-other-job")
    repeated_tail = project(contract, "github", saved[100:], key="replay-other-tail")
    assert (
        second.report["projection"]["written_values"]
        + repeated_tail.report["projection"]["written_values"]
        == 0
    )
    assert MetricValue.objects.count() == 420


def test_deep_partial_job_cannot_prevent_independent_fresh_discovery():
    obj, repo, _ = source_job(role="full", requests=5)
    partial = execute_github_catalog(obj.pk, client=reader(responses(repo, []), 5))
    assert partial.status == "partial"

    fresh = register_job(
        job_key="independent-fresh",
        source=obj.source,
        purpose="catalog",
        operation="github_catalog",
        mode="manual",
        definition={
            **copy.deepcopy(obj.definition),
            "scope": {**obj.definition["scope"], "github_role": "inventory"},
        },
    )
    set_job_state(fresh.pk, "ready")
    seen = []
    complete = execute_github_catalog(
        fresh.pk, client=reader(fresh_responses(repo, seen), 5)
    )
    assert complete.status == "success" and len(seen) == 3
    partial.refresh_from_db()
    assert partial.status == "partial"


def test_repository_becoming_unavailable_has_terminal_coverage_without_deep_fetch():
    obj, repo, _ = source_job()
    seen = []
    fallback = fresh_responses(repo, seen)

    def response(request):
        if request.url.path == "/repos/publisher/family":
            seen.append(str(request.url))
            return httpx.Response(404)
        return fallback(request)

    run = execute_github_catalog(obj.pk, client=reader(response, 30))
    assert run.status == "success"
    assert run.report["inaccessible_repositories"] == ["123"]
    assert not run.observations.filter(dimensions__kind="repository_access").exists()
    assert len(seen) == 3
