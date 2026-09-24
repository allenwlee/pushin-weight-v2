import pytest

from core.hf_catalog import resolve_brand, resolve_scope
from core.models import Brand, BrandCompany, Company, HFOrg

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def publisher(name="lab", brands=("first",)):
    company, _ = Company.objects.get_or_create(nickname=name)
    for nickname in brands:
        brand, _ = Brand.objects.get_or_create(nickname=nickname)
        BrandCompany.objects.get_or_create(brand=brand, company=company)
    return HFOrg.objects.create(namespace=name, company=company, confirmed=True)


def test_scope_deduplicates_and_does_not_infer_brand_from_filtered_subset():
    publisher(brands=("first", "second"))
    scope = resolve_scope(brands=["first"], companies=["lab"], rules=[])
    assert len(scope["namespaces"]) == 1
    entry = scope["namespaces"][0]
    assert entry["brands"] == ["first", "second"]
    assert resolve_brand("lab/model", entry, []) is None
    assert scope["gaps"] == []


def test_scope_reports_missing_edges_and_unconfirmed_namespaces():
    Brand.objects.create(nickname="orphan")
    org = publisher()
    org.confirmed = False
    org.save()
    scope = resolve_scope(
        brands=["missing", "orphan", "first"], companies=["absent"], rules=[]
    )
    assert {gap["reason"] for gap in scope["gaps"]} == {
        "missing_brand",
        "missing_company_edge",
        "missing_company",
        "unconfirmed_namespace",
    }
    assert scope["namespaces"] == []


def test_rules_are_frozen_and_ambiguous_rules_rejected():
    publisher(brands=("first", "second"))
    rule = {
        "namespace": "lab",
        "prefix": "A-",
        "brand": "first",
        "source": "https://lab.example/models",
    }
    scope = resolve_scope(brands=["first"], companies=[], rules=[rule])
    assert (
        resolve_brand("lab/A-test", scope["namespaces"][0], scope["rules"]) == "first"
    )
    assert resolve_brand("lab/B-test", scope["namespaces"][0], scope["rules"]) is None
    with pytest.raises(ValueError, match="overlapping"):
        resolve_scope(
            brands=["first"],
            companies=[],
            rules=[rule, {**rule, "prefix": "A-long", "brand": "second"}],
        )


def test_frontier_companies_are_included_independent_of_tracked_brands():
    for name in ("openai", "anthropic", "google", "xai"):
        publisher(name, brands=(name,))
    scope = resolve_scope(brands=[], rules=[])
    assert {row["company"] for row in scope["namespaces"]} == {
        "openai",
        "anthropic",
        "google",
        "xai",
    }
