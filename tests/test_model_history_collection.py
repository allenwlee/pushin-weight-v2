"""Historical windows, source gaps and reviewed numbers remain attributable."""

from datetime import datetime

import pytest
from django.utils import timezone

from core.collection_jobs import register_job, set_job_state
from core.collection_state import claim_job
from core.model_history_collection import (
    execute_model_history,
    history_windows,
    import_selected_history,
)
from core.models import CollectionRun, DataSource, MetricValue
from tests.test_benchmark_download_history import manifest
from tests.test_benchmark_download_persistence import configured

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def history_job(
    source, brand, product, *, pins=(), creation=None, extra=None, requests=30
):
    obj = register_job(
        job_key="history:" + source.pk,
        source=source,
        purpose="catalog",
        operation="model_history",
        mode="historical",
        definition={
            "version": 1,
            "scope": {
                "brand_id": brand.pk,
                "cohort_hash": "e" * 64,
                "cutoff": "2026-09-12T00:00:00Z",
                "global_start_at": "2026-09-01T00:00:00Z",
                "models": [
                    {
                        "product_key": str(product.product_key),
                        "creation": creation or {"at": "2026-09-01T00:00:00Z"},
                        "provider_pins": list(pins),
                    }
                ],
                **(extra or {}),
            },
            "schedule": {"kind": "manual", "driver": "manual"},
            "budgets": {
                "requests": requests,
                "seconds": 60,
                "bytes": 1000000,
                "items": 1000,
            },
        },
    )
    return set_job_state(obj.pk, "ready")


def test_native_hf_history_pins_revision_and_resumes_without_weight_download():
    import httpx

    from core.models import DataSource, Product
    from scripts.benchmark_download_collector.sources import Budget
    from tests.test_hf_catalog_runner import scope

    scope()
    product = Product.objects.create(
        brand_id="lab", repo_id="lab/model", type="llm-model"
    )
    source = DataSource.objects.get(pk="hf")
    source.enabled, source.adapter_key = True, "hf-catalog-v1"
    source.save()
    job = history_job(
        source,
        product.brand,
        product,
        creation={
            "at": "2026-09-01T00:00:00Z",
            "source": "hf",
            "native_identifier": "lab/model",
        },
    )
    seen = []

    def respond(request):
        seen.append(str(request.url))
        path = request.url.path
        if path == "/api/models/lab/model":
            return httpx.Response(
                200, json={"id": "lab/model", "private": False, "sha": "a" * 40}
            )
        assert path.endswith("a" * 40)
        if "/commits/" in path:
            if request.url.params.get("cursor"):
                return httpx.Response(200, json=[])
            return httpx.Response(
                200,
                json=[{"id": "b" * 40, "date": "2026-09-03T00:00:00Z"}],
                headers={
                    "Link": f'<https://huggingface.co{path}?cursor=next>; rel="next"'
                },
            )
        assert "/tree/" in path
        return httpx.Response(
            200,
            json=[{"type": "file", "path": "weights.safetensors", "size": 10000000000}],
        )

    def budget(n):
        return Budget(
            httpx.Client(transport=httpx.MockTransport(respond)),
            max_requests=n,
            max_bytes=1000000,
        )

    first = execute_model_history(job.pk, budget=budget(2))
    assert first.status == "partial"
    second = execute_model_history(job.pk, budget=budget(8))
    assert second.pk == first.pk and second.status == "success"
    assert (
        sum(
            "/api/models/lab/model?" in url or url.endswith("/api/models/lab/model")
            for url in seen
        )
        == 1
    )
    assert not any("/resolve/" in url for url in seen)
    assert second.observations.filter(dimensions__kind="hf_commits").count() == 1
    assert MetricValue.objects.count() == 0


def test_github_history_uses_reviewed_native_repo_and_pinned_tree():
    import httpx

    from core.collection_identity import review_github_mapping
    from scripts.benchmark_download_collector.sources import Budget
    from tests.test_collection_identity import identities
    from tests.test_github_catalog import responses

    brand, account, subject, repo = identities()
    source = account.data_source
    source.enabled = True
    source.adapter_key = "github-catalog-v1"
    source.save()
    mapping = review_github_mapping(
        subject=subject,
        repo=repo,
        role="dedicated_model",
        version_selector=None,
        evidence_url="https://github.com/publisher/family",
        reviewed_by="test",
    )
    pin = {
        "mapping_id": str(mapping.pk),
        "mapping_hash": mapping.mapping_hash,
        "source": "github",
        "native_identifier": "123",
        "identifier_scope": "repository_id",
    }
    job = history_job(source, brand, subject.product, pins=[pin])
    seen = []
    handler = responses(repo, seen)

    def respond(request):
        if request.url.path == "/repos/publisher/family":
            seen.append(str(request.url))
            return httpx.Response(200, json=repo)
        return handler(request)

    run = execute_model_history(
        job.pk,
        budget=Budget(
            httpx.Client(transport=httpx.MockTransport(respond)),
            max_requests=30,
            max_bytes=1000000,
        ),
    )
    assert (
        run.status == "success"
        and run.observations.filter(dimensions__kind="releases").count() == 2
    )
    assert all("c" * 40 in url for url in seen if "/git/trees/" in url)
    assert MetricValue.objects.count() == 0


def test_archive_acquisition_to_numeric_writer_keeps_zero_and_missing_distinct():
    import io
    import re

    import httpx
    import pyarrow as pa
    import pyarrow.parquet as pq

    from core.benchmark_metric_identity import configure_collection
    from core.model_history_collection import acquire_hf_archives
    from scripts.benchmark_download_collector.sources import Budget
    from tests.test_benchmark_download_db_identity import setup_spec

    _, spec = setup_spec()
    spec["source_configuration"]["hf"]["metric_versions"] = {"downloads_all_time": 2}
    contract = configure_collection(spec)
    product = contract.mappings.get(source_id="hf").subject.product
    source = DataSource.objects.get(pk="hf")
    source.enabled = True
    source.save()
    archive = {
        "dataset_id": "cfahlgren1/hub-stats",
        "archive_publisher": "cfahlgren1",
        "revisions": [
            {
                "id": "a" * 40,
                "date": "2026-09-10T00:00:00Z",
                "snapshot_date": "2026-09-10",
            }
        ],
    }
    job = history_job(
        source,
        product.brand,
        product,
        creation={
            "at": "2026-09-01T00:00:00Z",
            "source": "hf",
            "native_identifier": "lab/Model",
        },
        extra={"numeric_contract_id": str(contract.pk), "hf_archive": archive},
    )
    out = io.BytesIO()
    pq.write_table(
        pa.Table.from_pylist(
            [
                {
                    "id": "lab/Model",
                    "downloads": 0,
                    "downloadsAllTime": None,
                    "likes": None,
                }
            ]
        ),
        out,
    )
    binary = out.getvalue()
    calls = []

    def respond(request):
        calls.append(request)
        a, b = map(
            int, re.fullmatch(r"bytes=(\d+)-(\d+)", request.headers["range"]).groups()
        )
        return httpx.Response(
            206,
            content=binary[a : b + 1],
            headers={"content-range": f"bytes {a}-{b}/{len(binary)}"},
        )

    budget = Budget(
        httpx.Client(transport=httpx.MockTransport(respond)),
        max_requests=30,
        max_bytes=1000000,
    )
    claim = claim_job(job.pk)
    result = acquire_hf_archives(claim, job, budget)
    assert result["snapshots"] == 1
    assert MetricValue.objects.count() == 1
    value = MetricValue.objects.get()
    assert value.integer_value == 0 and value.temporal_status == "unknown"
    assert value.observation.source_metadata["archive_snapshot_date"] == "2026-09-10"
    count = len(calls)
    acquire_hf_archives(claim, job, budget)
    assert len(calls) == count and MetricValue.objects.count() == 1


def test_long_campaign_splits_without_inventing_supported_openrouter_history():
    windows, gaps = history_windows(
        "2024-01-01T00:00:00Z", "2026-09-01T00:00:00Z", "openrouter"
    )
    assert gaps[0]["outcome"] == "outside_provider_coverage"
    assert windows[0][0] == "2025-01-01" and windows[-1][1] == "2026-08-31"
    assert all(
        (datetime.fromisoformat(end) - datetime.fromisoformat(start)).days < 366
        for start, end in windows
    )


def test_each_selected_model_has_a_durable_source_gap_without_synthetic_values():
    from tests.test_collection_identity import identities

    brand, _, subject, _ = identities()
    for source_id in ("github", "hf", "openrouter", "arena"):
        source, _ = DataSource.objects.get_or_create(
            pk=source_id, defaults={"name": source_id, "source_type": "model_adoption"}
        )
        source.enabled, source.adapter_key = True, "test-history-v1"
        source.save()
        obj = register_job(
            job_key="gap:" + source_id,
            source=source,
            purpose="catalog",
            operation="model_history",
            mode="historical",
            definition={
                "version": 1,
                "scope": {
                    "brand_id": brand.pk,
                    "cohort_hash": "a" * 64,
                    "cutoff": timezone.now().isoformat(),
                    "models": [
                        {
                            "product_key": str(subject.product_id),
                            "creation": {"at": "2026-09-01T00:00:00Z"},
                            "provider_pins": [],
                        }
                    ],
                },
                "schedule": {"kind": "manual", "driver": "manual"},
                "budgets": {"requests": 5, "seconds": 30, "bytes": 10000, "items": 100},
            },
        )
        set_job_state(obj.pk, "ready")
        run = execute_model_history(obj.pk)
        cell = run.scopes.get(scope_kind="model_coverage")
        assert cell.outcome == "unmapped" and cell.enumeration_complete
        assert run.report["coverage"][0]["product_key"] == str(subject.product_id)
    assert MetricValue.objects.count() == 0


def test_reviewed_archive_import_retains_sparse_snapshots_and_unknown_flow_time():
    contract = configured()
    source = DataSource.objects.get(pk="hf")
    source.enabled, source.adapter_key = True, "hf-engagement-v1"
    source.save()
    product_key = str(contract.mappings.get(source_id="hf").subject.product_id)
    obj = register_job(
        job_key="archive",
        source=source,
        purpose="catalog",
        operation="model_history",
        mode="historical",
        definition={
            "version": 1,
            "scope": {
                "brand_id": contract.mappings.get(
                    source_id="hf"
                ).subject.product.brand_id,
                "cohort_hash": "b" * 64,
                "cutoff": "2026-09-12T00:00:00Z",
                "numeric_contract_id": str(contract.pk),
                "models": [
                    {
                        "product_key": product_key,
                        "creation": {"at": "2026-09-01T00:00:00Z"},
                        "provider_pins": [],
                    }
                ],
            },
            "schedule": {"kind": "manual", "driver": "manual"},
            "budgets": {"requests": 10, "seconds": 60, "bytes": 100000, "items": 100},
        },
    )
    set_job_state(obj.pk, "ready")
    claim = claim_job(obj.pk)
    imported = import_selected_history(claim, manifest(contract))
    assert imported.purpose == "metric" and imported.contract_id == contract.pk
    assert imported.observations.count() == 2 and MetricValue.objects.count() == 4
    assert all(
        v.temporal_status == "unknown" and v.window_end_at is None
        for v in MetricValue.objects.all()
    )
    assert import_selected_history(claim, manifest(contract)).pk == imported.pk
    assert MetricValue.objects.count() == 4
    assert CollectionRun.objects.get(pk=claim.run_id).report["numeric_run_ids"] == [
        str(imported.pk)
    ]


def test_shared_openrouter_window_is_fetched_once_and_other_never_fills_missing_model():
    import httpx

    from core.collection_identity import review_catalog_mapping
    from core.models import Brand, BrandAccount, MeasurementSubject, Product, Role
    from scripts.benchmark_download_collector.sources import Budget
    from tests.test_collection_identity import identities

    _brand, account, subject, _ = identities()
    other_brand = Brand.objects.create(nickname="other-fixture")
    BrandAccount.objects.create(
        brand=other_brand, account=account, role=Role.objects.get(pk="official")
    )
    other_product = Product.objects.create(
        brand=other_brand, type="llm-model", display_name="missing from ranking"
    )
    other_subject = MeasurementSubject.objects.create(
        subject_kind="product", product=other_product
    )
    source = DataSource.objects.create(
        pk="openrouter",
        name="OpenRouter",
        source_type="model_adoption",
        enabled=True,
        adapter_key="openrouter-v1",
    )
    jobs = []
    for idx, target in enumerate((subject, other_subject)):
        mapping = review_catalog_mapping(
            source=source,
            subject=target,
            external_identifier=f"publisher/model{idx + 1}",
            source_subject_kind="model",
            identifier_scope="rankings_permaslug",
            publisher_account=account,
            role="dedicated_model",
            version_selector=None,
            evidence_url=f"https://openrouter.ai/publisher/model{idx + 1}",
            reviewed_by="test",
            identity_snapshot={},
        )
        obj = register_job(
            job_key=f"rank-history-{idx}",
            source=source,
            purpose="catalog",
            operation="model_history",
            mode="historical",
            definition={
                "version": 1,
                "scope": {
                    "brand_id": target.product.brand_id,
                    "cohort_hash": "c" * 64,
                    "cutoff": "2026-09-02T00:00:00Z",
                    "global_start_at": "2026-09-01T00:00:00Z",
                    "models": [
                        {
                            "product_key": str(target.product_id),
                            "creation": {"at": "2026-09-01T00:00:00Z"},
                            "provider_pins": [
                                {
                                    "mapping_id": str(mapping.pk),
                                    "mapping_hash": mapping.mapping_hash,
                                    "source": "openrouter",
                                    "native_identifier": mapping.external_identifier,
                                    "identifier_scope": "rankings_permaslug",
                                }
                            ],
                        }
                    ],
                },
                "schedule": {"kind": "manual", "driver": "manual"},
                "budgets": {
                    "requests": 5,
                    "seconds": 60,
                    "bytes": 100000,
                    "items": 100,
                },
            },
        )
        jobs.append(set_job_state(obj.pk, "ready"))
    calls = []

    def response(request):
        calls.append(request)
        start, end = request.url.params["start_date"], request.url.params["end_date"]
        return httpx.Response(
            200,
            json={
                "meta": {
                    "version": "v1",
                    "start_date": start,
                    "end_date": end,
                    "as_of": "2026-09-03T00:00:00Z",
                },
                "data": [
                    {
                        "date": start,
                        "model_permaslug": "publisher/model1",
                        "total_tokens": "42",
                    },
                    {"date": start, "model_permaslug": "other", "total_tokens": "999"},
                ],
            },
        )

    budget = Budget(
        httpx.Client(transport=httpx.MockTransport(response)),
        max_requests=5,
        max_bytes=100000,
    )
    first = execute_model_history(jobs[0].pk, budget=budget, key="test-project")
    second = execute_model_history(jobs[1].pk, budget=budget, key="test-project")
    assert len(calls) == 1
    assert first.report["coverage"][0]["outcome"] == "observed"
    assert second.report["coverage"][0]["outcome"] == "history_unavailable"
    assert second.report["coverage"][0]["evidence"][0]["matched_rows"] == []
    assert MetricValue.objects.count() == 0
