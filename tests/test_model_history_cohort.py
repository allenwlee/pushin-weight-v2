from core.publisher_accounts import get_publisher
from tests.publisher_fixtures import hf_publisher

"""One creation-ordered cohort is frozen in DB jobs for all four providers."""

from datetime import timedelta

import httpx
import pytest
from django.utils import timezone

from core.model_history_cohort import cohort_report, freeze_model_history
from core.models import Brand, BrandCompany, CollectionJob, Company, Product
from scripts.benchmark_download_collector.sources import Budget, openrouter_catalog_page

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def test_google_company_alias_is_outside_the_requested_historical_scope():
    from core.model_history_cohort import build_cohort

    brands, cutoff, _ = inventory()
    google, _ = Company.objects.get_or_create(nickname="google")
    BrandCompany.objects.create(brand_id=brands[1], company=google)
    with pytest.raises(ValueError, match="Google"):
        build_cohort(brand_ids=brands, cutoff=cutoff)


def inventory():
    brands = [Brand.objects.create(nickname=f"fixture-{i}") for i in range(21)]
    company = Company.objects.create(nickname="fixture-company")
    BrandCompany.objects.create(brand=brands[0], company=company)
    namespaces = [
        hf_publisher(namespace=f"Fixture{i}", company=company, confirmed=True)
        for i in range(2)
    ]
    cutoff = timezone.now()
    products = [
        Product(
            brand=brands[0],
            publisher_account=namespaces[i % 2].account,
            repo_id=f"Fixture{i % 2}/Model{i}",
            type="llm-model",
            private=False,
            created_at=cutoff - timedelta(days=i + 1),
        )
        for i in range(130)
    ]
    Product.objects.bulk_create(products)
    Product.objects.create(
        brand=brands[0], type="llm-model", display_name="unknown creation"
    )
    Product.objects.create(brand=brands[0], type="agent-harness", display_name="agent")
    return [b.pk for b in brands], cutoff, products


def freeze(brands, cutoff):
    return freeze_model_history(
        brand_ids=brands,
        cutoff=cutoff,
        job_key_prefix="test-history",
        budgets={"requests": 20, "bytes": 1000000, "seconds": 60, "items": 1000},
    )


def test_company_wide_cap_and_all_brand_reports_are_persisted():
    brands, cutoff, products = inventory()
    jobs = freeze(brands, cutoff)
    report = cohort_report(jobs)
    assert len(report["brands"]) == 21
    assert CollectionJob.objects.count() == 84
    first = report["brands"][brands[0]]
    assert first["selected_count"] == 100
    assert first["unranked_count"] == 1
    assert first["selection_complete"] is False
    for source in ("github", "hf", "openrouter", "arena"):
        obj = next(
            j
            for j in jobs
            if j.source_id == source and j.definition["scope"]["brand_id"] == brands[0]
        )
        assert obj.state == "paused"
        assert [m["product_key"] for m in obj.definition["scope"]["models"]] == [
            str(p.product_key) for p in products[:100]
        ]
    assert [j.pk for j in freeze(brands, cutoff)] == [j.pk for j in jobs]


def test_company_family_repo_creation_cannot_date_model_version():
    brands, cutoff, _ = inventory()
    from tests.test_collection_identity import admit, identities

    brand, _, subject, repo = identities()
    # Make the family-linked model part of an otherwise valid 21-brand scope.
    brands[-1] = brand.pk
    mapping = admit(subject, {**repo, "created_at": "2000-01-01T00:00:00Z"})
    mapping.identifier_metadata = {
        **mapping.identifier_metadata,
        "creation_record": {"created_at": "2000-01-01T00:00:00Z", "source": "github"},
    }
    mapping.save()
    report = cohort_report(freeze(brands, cutoff))
    assert report["brands"][brand.pk]["selected_count"] == 0
    assert report["brands"][brand.pk]["unranked_count"] == 1


def test_incomplete_or_google_scope_is_rejected_without_jobs():
    brands, cutoff, _ = inventory()
    with pytest.raises(ValueError, match="21"):
        freeze(brands[:20], cutoff)
    google = Brand.objects.create(nickname="google")
    brands[-1] = google.pk
    with pytest.raises(ValueError, match="Google"):
        freeze(brands, cutoff)
    assert CollectionJob.objects.count() == 0


def test_openrouter_catalog_keeps_native_ids_and_creation_separate_from_rankings():
    seen = []

    def response(request):
        seen.append(request)
        assert request.url.path == "/api/v1/models"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "publisher/model",
                        "canonical_slug": "publisher/model-alias",
                        "created": 1700000000,
                    }
                ],
                "links": {"next": None},
                "total_count": 1,
            },
        )

    budget = Budget(httpx.Client(transport=httpx.MockTransport(response)))
    result = openrouter_catalog_page(budget, key="test-project-key")
    assert result["rows"][0]["id"] != result["rows"][0]["canonical_slug"]
    assert result["complete"] is True
    assert seen[0].headers["authorization"] == "Bearer test-project-key"


def test_reviewed_first_party_mirror_collapses_before_cap_and_uses_earliest_creation():
    brands, cutoff, products = inventory()
    from core.account_identity import upsert_account
    from core.collection_identity import review_catalog_mapping
    from core.models import BrandAccount, DataSource, MeasurementSubject, Role

    account = upsert_account(
        source="hf",
        external_identifier="Fixture0",
        handle="Fixture0",
        account_kind="organization",
    )
    BrandAccount.objects.create(
        brand_id=brands[0], account=account, role=Role.objects.get_or_create(key="official")[0]
    )
    mirror = Product.objects.create(
        brand_id=brands[0],
        publisher_account=get_publisher(source="hf", identifier="Fixture0").account,
        repo_id="Fixture0/Mirror",
        type="llm-model",
        private=False,
        created_at=cutoff - timedelta(hours=1),
    )
    subject = MeasurementSubject.objects.create(
        subject_kind="product", product=products[0]
    )
    review_catalog_mapping(
        source=DataSource.objects.get(pk="hf"),
        subject=subject,
        external_identifier=mirror.repo_id,
        source_subject_kind="repository",
        identifier_scope="model",
        publisher_account=account,
        role="dedicated_model",
        version_selector=None,
        evidence_url="https://huggingface.co/Fixture0/Mirror",
        reviewed_by="test",
        identity_snapshot={},
    )
    report = cohort_report(freeze(brands, cutoff))["brands"][brands[0]]
    assert report["dated_count"] == 130 and report["selected_count"] == 100
    assert report["models"][0]["product_key"] == str(products[0].product_key)
    assert len(report["models"][0]["aliases"]) == 2
    assert report["models"][0]["creation"]["native_identifier"] == products[0].repo_id


def test_creation_ties_use_product_uuid_deterministically():
    brands, cutoff, products = inventory()
    Product.objects.filter(pk=products[1].pk).update(created_at=products[0].created_at)
    report = cohort_report(freeze(brands, cutoff))["brands"][brands[0]]
    assert [row["product_key"] for row in report["models"][:2]] == sorted(
        str(p.product_key) for p in products[:2]
    )
