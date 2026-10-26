"""Native inventory clocks reach DB evidence without contaminating HF fields."""

import httpx
import pytest

from core.account_identity import upsert_account
from core.collection_capture import observation_object_documents
from core.collection_identity import review_catalog_mapping
from core.collection_jobs import register_job, set_job_state
from core.hf_catalog import resolve_scope
from core.model_inventory import execute_model_inventory
from core.models import (
    BrandAccount,
    CollectionRun,
    DataSource,
    MeasurementSubject,
    Product,
    Role,
)
from scripts.benchmark_download_collector.sources import Budget
from tests.product_factory import product_type_fields
from tests.test_model_history_cohort import freeze, inventory

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def inventory_job(source_id, scope):
    source, _ = DataSource.objects.get_or_create(
        pk=source_id, defaults={"name": source_id, "source_type": "model_adoption"}
    )
    source.enabled, source.adapter_key = True, source_id + "-catalog-v1"
    source.save()
    obj = register_job(
        job_key="inventory:" + source_id,
        source=source,
        purpose="catalog",
        operation="model_inventory",
        mode="manual",
        definition={
            "version": 1,
            "scope": scope,
            "schedule": {"kind": "manual", "driver": "manual"},
            "budgets": {"requests": 10, "seconds": 60, "bytes": 100000, "items": 1000},
        },
    )
    return set_job_state(obj.pk, "ready")


def test_openrouter_model_catalog_correlates_api_only_creation_through_reviewed_mapping():
    from core.collection_capture import archive_legacy

    brands, cutoff, _ = inventory()
    account = upsert_account(
        source="hf",
        external_identifier="Publisher",
        handle="Publisher",
        account_kind="organization",
    )
    BrandAccount.objects.create(
        brand_id=brands[-1], account=account, role=Role.objects.get_or_create(key="official")[0]
    )
    product = Product.objects.create(
        brand_id=brands[-1], **product_type_fields(Product, "llm-model"), display_name="API only"
    )
    subject = MeasurementSubject.objects.create(subject_kind="product", product=product)
    obj = inventory_job("openrouter", {"authors": ["publisher"]})
    review_catalog_mapping(
        source=obj.source,
        subject=subject,
        external_identifier="publisher/model",
        source_subject_kind="model",
        identifier_scope="model_id",
        publisher_account=account,
        role="dedicated_model",
        version_selector=None,
        evidence_url="https://openrouter.ai/publisher/model",
        reviewed_by="test",
        identity_snapshot={},
    )

    def handler(request):
        assert request.url.params["model_authors"] == "publisher"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "publisher/model",
                        "canonical_slug": "publisher/distinct",
                        "created": 1700000000,
                    }
                ],
                "links": {"next": None},
                "total_count": 1,
            },
        )

    run = execute_model_inventory(
        obj.pk,
        budget=Budget(httpx.Client(transport=httpx.MockTransport(handler))),
        key="test-project",
    )
    assert run.status == "success"
    observation = run.observations.get()
    assert (
        observation.source_identifier == "publisher/model"
        and observation_object_documents(observation)[0]["canonical_slug"] == "publisher/distinct"
    )
    assert observation.values.count() == 0
    assert run.attempts.get().requests.get().archive_id
    assert observation.inputs.get().input_request_id
    observation.legacy_archive = archive_legacy(dict(zip(
        ("listing", "dimensions", "source_metadata"), observation_object_documents(observation),
    )))
    observation.listing, observation.dimensions, observation.source_metadata = {}, {}, {}
    observation.save(update_fields=[
        "legacy_archive", "listing", "dimensions", "source_metadata",
    ])
    jobs = freeze(brands, cutoff)
    selected = next(
        j
        for j in jobs
        if j.source_id == "openrouter"
        and j.definition["scope"]["brand_id"] == brands[-1]
    )
    assert (
        selected.definition["scope"]["models"][0]["creation"]["source"] == "openrouter"
    )
    product.refresh_from_db()
    assert (
        product.repo_id is None and product.created_at is None and product.sha is None
    )


def test_hf_creation_inventory_uses_current_product_projection_under_shared_fence():
    brands, _, _ = inventory()
    scope = resolve_scope(brands=[brands[0]], companies=[], rules=[])
    obj = inventory_job("hf", {"hf_scope": scope})

    def response(request):
        namespace = request.url.params["author"]
        assert request.url.params["sort"] == "createdAt"
        return httpx.Response(
            200,
            json=[
                {
                    "id": namespace + "/NewModel",
                    "author": namespace,
                    "private": False,
                    "createdAt": "2026-09-01T00:00:00Z",
                    "sha": "a" * 40,
                }
            ],
        )

    run = execute_model_inventory(
        obj.pk, budget=Budget(httpx.Client(transport=httpx.MockTransport(response)))
    )
    assert run.status == "success" and run.observations.count() == 2
    assert run.scopes.filter(scope_kind="namespace", enumeration_complete=True).count() == 2
    assert (run.selected_count, run.success_count) == (2, 2)
    assert Product.objects.get(repo_id="Fixture0/NewModel").created_at.year == 2026
    assert CollectionRun.objects.count() == 1
    requests = run.attempts.get().requests.filter(transport_outcome="received")
    assert requests.count() == 2
    assert all(request.archive_id is not None for request in requests)
    assert all(observation.inputs.count() == 1 for observation in run.observations.all())
    assert all(observation.resource_snapshot.provider_created_at.year == 2026 for observation in run.observations.all())


def test_account_owned_typed_job_executes_real_hf_inventory_without_embedded_membership():
    from core.models import Account

    brands, _, _ = inventory()
    frozen = resolve_scope(brands=[brands[0]], companies=[], rules=[])
    entry = frozen["namespaces"][0]
    owner = Account.objects.get(data_source_id="hf", normalized_identifier=entry["namespace"].casefold())
    company_subject, _ = MeasurementSubject.objects.get_or_create(subject_kind="company", company_id=entry["company"])
    targets = [{"target_key": "company", "subject_id": company_subject.pk, "target_kind": "company", "target_role": "owner", "resolution_state": "resolved"}]
    for brand in entry["brands"]:
        subject, _ = MeasurementSubject.objects.get_or_create(subject_kind="brand", brand_id=brand)
        targets.append({"target_key": "brand:" + brand, "subject_id": subject.pk, "target_kind": "brand", "target_role": "selected", "resolution_state": "resolved"})
    source = DataSource.objects.get(pk="hf")
    source.enabled = True
    source.adapter_key = "hf-catalog-v1"
    source.save(update_fields=["enabled", "adapter_key"])
    job = register_job(
        job_key="typed-hf-inventory", source=source, purpose="catalog", operation="model_inventory", mode="historical",
        definition={"version": 2, "options": {}}, targets=targets,
        settings={"owner_kind": "account", "owner_account_id": owner.pk, "schedule_kind": "manual", "schedule_driver": "manual", "max_requests": 10, "max_bytes": 100000, "max_seconds": 60, "max_items": 100},
    )
    set_job_state(job.pk, "ready")

    def handler(request):
        assert request.url.params["author"] == entry["namespace"]
        return httpx.Response(200, json=[{"id": entry["namespace"] + "/TypedModel", "author": entry["namespace"], "private": False, "createdAt": "2026-09-01T00:00:00Z"}])

    run = execute_model_inventory(job.pk, budget=Budget(httpx.Client(transport=httpx.MockTransport(handler))))
    assert run.status == "success"
    assert run.attempts.get().requests.count() == 1
    assert run.observations.get().inputs.count() == 1
    snapshot = run.observations.get().resource_snapshot
    assert snapshot.publisher_account_id == owner.pk
    assert snapshot.native_stable_id is None  # HF's route/name can be renamed.
    job.refresh_from_db()
    assert job.definition == {"version": 2, "options": {}}
    assert job.last_success_id == run.pk
