"""Real GitHub writes and reads with all retiring collection columns denied."""

import json
from io import StringIO

import httpx
import pytest
from django.core.management import call_command

from core.collection_capture import observation_object_documents, run_report_document
from core.github_catalog import (
    catalog_report,
    execute_github_catalog,
    validate_typed_scope,
)
from core.models import CollectionObservationInput, CollectionRun, MetricValue, TimeZone
from tests.test_github_catalog import configured, reader, responses
from tests.test_github_source_ingestion import fresh_responses, source_job
from tests.test_hf_catalog_retirement import denied_retirement_columns

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_failure_before_first_provider_scope_still_has_a_typed_report(monkeypatch):
    from scripts.benchmark_download_collector.sources import SourceError

    job, _ = configured()

    def stop(*args):
        raise SourceError("time_cap")

    monkeypatch.setattr("core.github_catalog._publisher_inventory", stop)
    with denied_retirement_columns():
        run = execute_github_catalog(
            job.pk, client=reader(lambda _: pytest.fail("unexpected HTTP"), 20)
        )
        assert run.status == "partial" and run.request_count == 0
        assert run.selected_count == run.success_count == 0
        assert run.scopes.get().scope_kind == "catalog_execution"
        assert run_report_document(run)["stop_reason"] == "time_cap"
        assert run_report_document(run)["inventory_complete"] == {}


def test_command_and_operator_status_return_typed_catalog_report(monkeypatch):
    from core.collection_reports import job_status

    job, repo = configured()
    original = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **_: original(transport=httpx.MockTransport(responses(repo, []))),
    )
    output = StringIO()
    with denied_retirement_columns():
        call_command(
            "collect_github_catalog", job=str(job.pk), execute=True, stdout=output
        )
        result = json.loads(output.getvalue())
        run = CollectionRun.objects.get(pk=result["run_id"])
        assert result["status"] == "success"
        assert result["report"] == catalog_report(run)
        assert result["report"]["inventory_complete"] == {"42": True}
        status = job_status(job.pk)
        assert status["last_attempt"]["success_count"] == run.success_count
        assert status["last_success"]["selected_count"] == run.selected_count


def test_full_catalog_resume_pins_metadata_and_reports_without_retiring_columns():
    job, repo = configured()
    seen = []
    with denied_retirement_columns():
        first = execute_github_catalog(job.pk, client=reader(responses(repo, seen), 2))
        assert first.status == "partial" and first.error_code == "request_cap"
        first_report = run_report_document(first)
        assert first_report["items_this_invocation"] == 1
        assert first_report["inventory_complete"] == {"42": False}
        resumed = execute_github_catalog(
            job.pk, client=reader(responses(repo, seen), 20)
        )
        assert resumed.pk == first.pk and resumed.status == "success"
        assert resumed.request_count == len(seen)
        assert catalog_report(resumed) == run_report_document(resumed)
        assert catalog_report(resumed)["physical_accounting_complete"] is True
        assert catalog_report(resumed)["items_this_invocation"] == 4
        assert resumed.attempts.count() == 2
        tree = resumed.scopes.get(scope_kind="repository_tree")
        file = resumed.scopes.get(scope_kind="repository_file")
        head = tree.resource_observation
        assert head.observation_kind == "commits"
        assert head.resource_snapshot.revision == "a" * 40
        assert head.resource_snapshot.tree_revision == "c" * 40
        assert file.resource_observation_id == head.pk
        assert file.requested_revision == tree.requested_revision == "a" * 40
        assert file.resource_path == "README.md"
        selected = file.observations.get(observation_kind="file")
        assert observation_object_documents(selected)[1]["coordinate"] == {
            "revision": "a" * 40,
            "filename": "README.md",
        }
        assert (
            selected.inputs.get(
                input_role="github_source_object"
            ).input_request.scope_run_id
            == file.pk
        )
        assert all(
            observation_object_documents(row)[0] for row in resumed.observations.all()
        )


def test_release_assets_keep_parent_identity_zero_values_and_projection_report():
    TimeZone.objects.get_or_create(pk="UTC")
    job, repo, _ = source_job(role="release_watch")
    seen = []
    with denied_retirement_columns():
        run = execute_github_catalog(
            job.pk, client=reader(fresh_responses(repo, seen, assets=True), 30)
        )
        assert run.status == "success", run.error_code
        assert len(seen) == run.request_count == 6
        downloads = MetricValue.objects.filter(
            source_metric__metric_key="asset_downloads"
        )
        assert sorted(downloads.values_list("integer_value", flat=True)) == [0, 4]
        assets = list(run.observations.filter(observation_kind="release_asset"))
        assert {int(row.resource_snapshot.native_stable_id) for row in assets} == {
            501,
            502,
        }
        for asset in assets:
            parent = asset.scope_run.resource_observation
            assert parent.observation_kind == "releases"
            assert parent.resource_snapshot.native_stable_id == "5"
            assert (
                asset.inputs.get(input_role="release_asset_parent").input_observation_id
                == parent.pk
            )
            assert observation_object_documents(asset)[1]["release_id"] == 5
        report = run_report_document(run)
        assert (
            report["numeric_projection"]["written_values"]
            == MetricValue.objects.count()
        )
        assert report["numeric_projection"]["acknowledged"] == 5
        assert report["numeric_projection"]["pending"] is False
        assert report["numeric_projection"]["pending_resources"] == 0
        later = execute_github_catalog(
            job.pk, client=reader(fresh_responses(repo, [], assets=True), 30)
        )
        assert later.status == "success" and later.pk != run.pk
        assert catalog_report(run) == report


def test_repeated_304_reuses_original_clock_body_and_requires_validation_receipt():
    job, repo = configured()
    fallback = responses(repo, [])

    def cached(request):
        if (
            request.url.path == "/orgs/publisher/repos"
            and request.url.params.get("page") is None
        ):
            assert request.headers["if-none-match"] == '"page1"'
            return httpx.Response(304, headers={"ETag": '"page1"'})
        return fallback(request)

    with denied_retirement_columns():
        original = execute_github_catalog(job.pk, client=reader(fallback, 20))
        assert original.status == "success"
        prior = original.observations.get(observation_kind="repository")
        for _ in range(2):
            run = execute_github_catalog(job.pk, client=reader(cached, 20))
            assert run.status == "success", run.error_code
            current = run.observations.get(observation_kind="repository")
            assert current.observed_at == prior.observed_at
            assert (
                observation_object_documents(current)[0]
                == observation_object_documents(prior)[0]
            )
            assert (
                current.inputs.get(input_role="cached_response").input_observation_id
                == prior.pk
            )
            assert current.values.count() == 0
            prior = current
        validation = current.inputs.get(input_role="cache_validation").input_request
        validation.http_status = 200
        validation.save(update_fields=["http_status"])
        with pytest.raises(ValueError, match="cache validation receipt"):
            observation_object_documents(current)


@pytest.mark.parametrize("status", [404, 429])
def test_access_absence_and_rate_limit_have_typed_reports(status):
    TimeZone.objects.get_or_create(pk="UTC")
    job, repo, _ = source_job()
    seen = []
    fallback = fresh_responses(repo, seen)

    def unavailable(request):
        if request.url.path == "/repos/publisher/family":
            seen.append(str(request.url))
            return httpx.Response(
                status, headers={"Retry-After": "300"} if status == 429 else {}
            )
        return fallback(request)

    with denied_retirement_columns():
        run = execute_github_catalog(job.pk, client=reader(unavailable, 30))
        report = run_report_document(run)
        assert run.status == ("success" if status == 404 else "partial")
        assert report["stop_reason"] == (None if status == 404 else "http_429")
        assert report["inaccessible_repositories"] == (["123"] if status == 404 else [])
        assert not run.observations.filter(
            observation_kind="repository_access"
        ).exists()
        assert not MetricValue.objects.filter(
            source_metric__metric_key="subscribers"
        ).exists()
        assert run.request_count == len(seen) == 3


@pytest.mark.parametrize("corruption", ["ownership", "parent", "locator", "checksum"])
def test_typed_github_ownership_and_exact_source_selection_fail_closed(corruption):
    job, repo = configured()
    with denied_retirement_columns():
        run = execute_github_catalog(job.pk, client=reader(responses(repo, []), 20))
        assert run.status == "success"
        repository = run.observations.get(observation_kind="repository")
        if corruption in {"ownership", "parent"}:
            owner = {"repository_id": "123", "owner_id": "42"}
            if corruption == "ownership":
                owner["owner_id"] = "99"
            else:
                repository = run.observations.filter(observation_kind="commits").first()
            with pytest.raises(ValueError, match="ownership changed"):
                validate_typed_scope(
                    run.job, run, "repository_access", "123", owner, repository
                )
        else:
            edge = repository.inputs.get(input_role="github_source_object")
            CollectionObservationInput.objects.filter(pk=edge.pk).update(
                **(
                    {"row_locator": "999"}
                    if corruption == "locator"
                    else {"input_sha256": "a" * 64}
                )
            )
            with pytest.raises(ValueError, match="page row is absent|checksum changed"):
                observation_object_documents(repository)
