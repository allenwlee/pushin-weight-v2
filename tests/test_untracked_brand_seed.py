import importlib

import pytest
from django.apps import apps

from core.models import Brand, BrandCompany, Company

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_untracked_canonical_brands_and_company_edges_are_seeded_without_harvest_membership():
    migration = importlib.import_module("core.migrations.0049_rare_type_domain_records")
    migration.seed_untracked_organization_brands(apps, None)
    migration.seed_untracked_organization_brands(apps, None)
    expected = {
        "openai": "openai",
        "anthropic": "anthropic",
        "spacexai": "xai",
        "gemini": "google",
    }
    assert set(Brand.objects.filter(pk__in=expected).values_list("nickname", flat=True)) == set(expected)
    assert {
        brand_id: company_id
        for brand_id, company_id in BrandCompany.objects.filter(
            brand_id__in=expected
        ).values_list("brand_id", "company_id")
    } == expected


def test_seed_fails_closed_on_conflicting_existing_company_link():
    migration = importlib.import_module("core.migrations.0049_rare_type_domain_records")
    brand = Brand.objects.create(nickname="openai")
    company = Company.objects.create(nickname="conflicting-owner")
    BrandCompany.objects.create(brand=brand, company=company)
    with pytest.raises(RuntimeError, match="conflicting Company"):
        migration.seed_untracked_organization_brands(apps, None)
    assert list(brand.companies.values_list("company_id", flat=True)) == [
        "conflicting-owner"
    ]
