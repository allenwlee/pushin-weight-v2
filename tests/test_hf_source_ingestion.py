"""HF acquisition and saved replay reach the shared numeric writer without HTTP replay."""

import httpx
import pytest

from core.collection_jobs import register_job, set_job_state
from core.hf_catalog import resolve_scope
from core.models import (
    CollectionObservation,
    CompanyAccount,
    MetricValue,
)
from scripts.benchmark_download_collector.sources import Budget
from tests.test_source_metric_projection import CAPTURED, configured, evidence

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def test_confirmed_publisher_with_unknown_kind_still_collects_public_profile():
    from core.model_inventory import execute_model_inventory

    contract, raw, product, _ = configured()
    assert product.publisher_account.account_kind == "unknown"
    job = ingestion_job(contract)
    seen = []

    def respond(request):
        seen.append(str(request.url))
        if request.url.path == "/api/models":
            return httpx.Response(200, json=[raw])
        if request.url.path.endswith("/overview"):
            return httpx.Response(200, json={"name": "lab", "numFollowers": 5})
        return httpx.Response(200, json=raw)

    run = execute_model_inventory(
        job.pk, budget=Budget(httpx.Client(transport=httpx.MockTransport(respond)))
    )
    assert run.status == "success"
    assert (
        MetricValue.objects.get(source_metric__metric_key="followers").integer_value
        == 5
    )
    product.publisher_account.refresh_from_db()
    assert product.publisher_account.account_kind == "unknown"
    assert sum("/overview" in url for url in seen) == 1


def ingestion_job(contract):
    scope = resolve_scope(
        brands=[],
        companies=[
            CompanyAccount.objects.get(
                account=contract.mappings.first().subject.account
            ).company_id
        ],
        rules=[],
    )
    job = register_job(
        job_key="hf:complete",
        source=contract.mappings.first().source,
        purpose="catalog",
        operation="hf_catalog",
        mode="manual",
        definition={
            "version": 1,
            "scope": {
                "hf_scope": scope,
                "numeric_contract_id": str(contract.pk),
                "ingest_metadata": True,
            },
            "schedule": {"kind": "manual", "driver": "manual"},
            "budgets": {"requests": 20, "seconds": 60, "bytes": 1000000, "items": 1000},
        },
    )
    return set_job_state(job.pk, "ready")


def test_facade_acquires_metadata_and_projects_without_importer():
    from core.collection_scheduling import execute_due_job

    contract, raw, product, _ = configured()
    job = ingestion_job(contract)
    calls = []

    def respond(request):
        calls.append(str(request.url))
        if request.url.path == "/api/models":
            return httpx.Response(
                200,
                json=[{**raw, "sha": "a" * 40, "createdAt": "2020-01-01T00:00:00Z"}],
            )
        if request.url.path.endswith("/overview"):
            return httpx.Response(200, json={"name": "lab", "numFollowers": 0})
        return httpx.Response(
            200,
            json={
                **raw,
                "sha": "a" * 40,
                "downloadsAllTime": 9,
                "siblings": [{"rfilename": "README.md", "blobId": "x"}],
            },
        )

    run = execute_due_job(
        job, {}, Budget(httpx.Client(transport=httpx.MockTransport(respond)))
    )
    assert run.status == "success", run.report
    assert MetricValue.objects.count() >= 3
    assert not run.observations.filter(values__isnull=False).exists()
    assert (
        run.scopes.filter(scope_kind="numeric_projection", outcome="pending").count()
        == 0
    )
    product.refresh_from_db()
    assert product.downloads_all_time == 9
    assert len(calls) <= 4
    assert all("/api/" in url and "/resolve/" not in url for url in calls)


def test_595_saved_native_snapshots_replay_twice_without_http(monkeypatch):
    from core.source_metric_projection import replay_saved_evidence

    contract, raw, _, _ = configured()
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda *args, **kwargs: pytest.fail("replay constructed an HTTP client"),
    )
    snapshots = [evidence("hf", {**raw, "id": f"lab/Model{i}"}) for i in range(595)]
    for attempt in range(2):
        job = register_job(
            job_key=f"hf:replay:{attempt}",
            source=contract.mappings.first().source,
            purpose="metric",
            operation="collect_metrics",
            mode="historical",
            contract=contract,
            definition={
                "version": 1,
                "scope": {"origin_run_ids": [str(s.run_id) for s in snapshots]},
                "schedule": {"kind": "manual", "driver": "manual"},
                "budgets": {
                    "requests": 1,
                    "seconds": 60,
                    "bytes": 1000000,
                    "items": 1000,
                },
            },
        )
        set_job_state(job.pk, "ready")
        run = replay_saved_evidence(job.pk)
        assert run.status == "success"
        assert run.request_count == 0
        assert MetricValue.objects.count() == 1190
        assert (
            not CollectionObservation.objects.filter(values__isnull=False)
            .exclude(observed_at=CAPTURED)
            .exists()
        )
    assert run.report["projection"]["written_values"] == 0


def test_committed_projection_recovers_after_crash_before_ack_without_refetch(
    monkeypatch,
):
    from datetime import timedelta

    from django.utils import timezone

    import core.source_metric_projection as projection
    from core.model_inventory import execute_model_inventory
    from core.models import CollectionRun

    contract, raw, _, _ = configured()
    job = ingestion_job(contract)
    real_project = projection.project_evidence

    def crash_after_commit(*args, **kwargs):
        real_project(*args, **kwargs)
        raise RuntimeError("worker stopped before queue acknowledgement")

    def respond(request):
        if request.url.path.endswith("/overview"):
            return httpx.Response(200, json={"name": "lab"})
        return httpx.Response(
            200, json=[raw] if request.url.path == "/api/models" else raw
        )

    monkeypatch.setattr(projection, "project_evidence", crash_after_commit)
    with pytest.raises(RuntimeError, match="acknowledgement"):
        execute_model_inventory(
            job.pk, budget=Budget(httpx.Client(transport=httpx.MockTransport(respond)))
        )
    assert MetricValue.objects.count() == 2
    assert CollectionRun.objects.filter(
        job__purpose="catalog",
        scopes__scope_kind="numeric_projection",
        scopes__outcome="pending",
    ).exists()
    CollectionRun.objects.filter(job=job, status="running").update(
        lease_expires_at=timezone.now() - timedelta(seconds=1)
    )
    monkeypatch.setattr(projection, "project_evidence", real_project)

    def forbidden(request):
        pytest.fail("resume must consume saved captures without HTTP")

    recovered = execute_model_inventory(
        job.pk, budget=Budget(httpx.Client(transport=httpx.MockTransport(forbidden)))
    )
    assert recovered.status == "success", recovered.report
    assert MetricValue.objects.count() == 2
    assert recovered.report["numeric_projection"]["pending"] is False
    assert not recovered.scopes.filter(
        scope_kind="numeric_projection", outcome="pending"
    ).exists()


def test_fresh_run_refreshes_unchanged_sha_and_observes_old_created_new_repo():
    from core.model_inventory import execute_model_inventory

    contract, raw, _, _ = configured()
    job = ingestion_job(contract)
    generation = 0

    def respond(request):
        if request.url.path.endswith("/overview"):
            return httpx.Response(200, json={"name": "lab"})
        row = {
            **raw,
            "downloads": generation,
            "sha": "a" * 40,
            "createdAt": "2020-01-01T00:00:00Z",
        }
        if request.url.path == "/api/models":
            rows = [row]
            if generation:
                rows.append({**row, "id": "lab/OldNewlyPublic"})
            return httpx.Response(200, json=rows)
        return httpx.Response(
            200, json={**row, "id": request.url.path.removeprefix("/api/models/")}
        )

    transport = httpx.MockTransport(respond)
    first = execute_model_inventory(
        job.pk, budget=Budget(httpx.Client(transport=transport))
    )
    generation = 1
    second = execute_model_inventory(
        job.pk, budget=Budget(httpx.Client(transport=transport))
    )
    assert first.status == second.status == "success"
    current = second.observations.get(
        dimensions__kind="creation_inventory", source_identifier="lab/OldNewlyPublic"
    )
    assert current.source_metadata["inventory_event"] == "newly_observed"
    assert current.listing["createdAt"].startswith("2020")
    downloads = MetricValue.objects.filter(
        source_metric__metric_key="downloads"
    ).order_by("observation__observed_at")
    assert [int(v.integer_value) for v in downloads] == [0, 1, 1]
    assert all(
        v.temporal_status == "unknown"
        and v.window_start_at is None
        and v.window_end_at is None
        for v in downloads
    )


def test_detail_partial_resumes_and_unsupported_expansion_is_terminal_gap():
    from core.model_inventory import execute_model_inventory

    contract, raw, _, _ = configured()
    job = ingestion_job(contract)
    attempts = []
    broken = True

    def respond(request):
        attempts.append(str(request.url))
        if request.url.path.endswith("/overview"):
            return httpx.Response(200, json={"name": "lab"})
        if request.url.path == "/api/models":
            return httpx.Response(200, json=[raw])
        if "blobs" in request.url.params and broken:
            return httpx.Response(404, json={"error": "temporarily absent"})
        if (
            "expand" in request.url.params
            and "childrenModelCount" in request.url.params.get_list("expand")
        ):
            return httpx.Response(400, json={"error": "unsupported expansion"})
        return httpx.Response(200, json=raw)

    first = execute_model_inventory(
        job.pk, budget=Budget(httpx.Client(transport=httpx.MockTransport(respond)))
    )
    assert first.status == "partial"
    assert MetricValue.objects.count() == 2
    broken = False
    attempts.clear()
    resumed = execute_model_inventory(
        job.pk, budget=Budget(httpx.Client(transport=httpx.MockTransport(respond)))
    )
    assert resumed.status == "success", resumed.report
    assert len(attempts) == 1 and "blobs=true" in attempts[0]
    assert (
        resumed.scopes.get(
            scope_kind="hf_metadata", scope_key="lab/Model:expanded"
        ).outcome
        == "partial_expansion"
    )
    assert MetricValue.objects.count() == 2


def test_supported_optional_account_counts_and_trending_share_writer_and_profile_fetch():
    from core.measurement_taxonomy import configure_taxonomy
    from core.model_inventory import execute_model_inventory
    from core.source_metric_projection import configure_source_statistics

    _, raw, product, spec = configured()
    account = product.publisher_account
    account.account_kind = "individual"
    account.save(update_fields=["account_kind"])
    taxonomy = configure_taxonomy(
        {
            "reviewed_by": "profile",
            "subjects": [{"kind": "account", "key": str(account.pk)}],
        }
    )
    spec["taxonomy_version"] = str(taxonomy.pk)
    spec["mappings"][0]["identifier_scope"] = "individual"
    spec["source_configuration"]["hf"]["metrics"] += [
        "trending_score",
        "models_count",
        "datasets_count",
        "spaces_count",
    ]
    contract = configure_source_statistics(spec)
    job = ingestion_job(contract)
    calls = []

    def respond(request):
        calls.append(str(request.url))
        if request.url.path == "/api/models":
            return httpx.Response(200, json=[raw, {**raw, "id": "lab/Second"}])
        if request.url.path.endswith("/overview"):
            return httpx.Response(
                200,
                json={
                    "user": "lab",
                    "numFollowers": "bad optional",
                    "numModels": 2,
                    "numDatasets": 0,
                    "numSpaces": 1,
                },
            )
        return httpx.Response(
            200,
            json={
                **raw,
                "id": request.url.path.removeprefix("/api/models/"),
                "trendingScore": 0.5,
            },
        )

    run = execute_model_inventory(
        job.pk, budget=Budget(httpx.Client(transport=httpx.MockTransport(respond)))
    )
    assert run.status == "success", run.report
    assert sum("/overview" in url for url in calls) == 1
    values = MetricValue.objects.filter(observation__source_subject_kind="account")
    assert {v.source_metric.metric_key: int(v.integer_value) for v in values} == {
        "models_count": 2,
        "datasets_count": 0,
        "spaces_count": 1,
    }
    assert (
        MetricValue.objects.filter(
            source_metric__metric_key="trending_score", float_value=0.5
        ).count()
        == 2
    )
    assert all(v.temporal_status == "unknown" and v.as_of_at is None for v in values)
