import pytest
from django.db import IntegrityError, transaction

from core.models import Brand, Product
from tests.product_factory import product_type_fields

pytestmark = pytest.mark.django_db


def product(name, brand):
    return Product.objects.create(repo_id=f"lab/{name}", brand=brand, **product_type_fields(Product, "llm-model"))


def test_reviewed_successors_preserve_manual_exclusion_and_frozen_labels():
    from core.measurement_taxonomy import configure_taxonomy, resolve_products
    from core.models import ProductGroupMembership, TaxonomyVersion

    brand = Brand.objects.create(nickname="lab", display_name="Lab")
    root, child, quantized = [product(n, brand) for n in ("M2", "M3", "M3-q")]
    spec = {
        "reviewed_by": "test-reviewer",
        "subjects": [{"kind": "brand", "key": brand.pk}]
        + [
            {"kind": "product", "key": str(p.product_key)}
            for p in (root, child, quantized)
        ],
        "relationships": [
            {
                "parent": str(root.product_key),
                "child": str(child.product_key),
                "type": "new_version",
                "evidence": {"url": "https://example.org/successor"},
            },
            {
                "parent": str(child.product_key),
                "child": str(quantized.product_key),
                "type": "quantized",
                "evidence": {"url": "https://example.org/quantized"},
            },
        ],
        "groups": [
            {
                "key": "m-series",
                "name": "M series",
                "rule_kind": "new_version_chain",
                "root": str(root.product_key),
                "owner_brands": ["lab"],
                "exclude": [str(child.product_key)],
            }
        ],
        "affiliations": [],
    }
    version = configure_taxonomy(spec)
    assert configure_taxonomy(spec).pk == version.pk
    assert TaxonomyVersion.objects.count() == 1
    group = ProductGroupMembership.objects.get(
        taxonomy_version=version, membership_status="included"
    ).group
    assert resolve_products(version, group.subject.pk) == {str(root.product_key)}
    assert (
        ProductGroupMembership.objects.get(group=group, product=child).membership_status
        == "excluded"
    )
    assert not ProductGroupMembership.objects.filter(
        group=group, product=quantized
    ).exists()
    root.display_name = "Renamed"
    root.save()
    assert version.snapshot["products"][str(root.product_key)]["label"] != "Renamed"


def test_cycles_rejected_atomically():
    from core.measurement_taxonomy import configure_taxonomy
    from core.models import TaxonomyVersion

    brand = Brand.objects.create(nickname="lab", display_name="Lab")
    a, b = product("a", brand), product("b", brand)
    spec = {
        "reviewed_by": "reviewer",
        "subjects": [{"kind": "product", "key": str(p.product_key)} for p in (a, b)],
        "relationships": [
            {
                "parent": str(a.product_key),
                "child": str(b.product_key),
                "type": "new_version",
                "evidence": {"url": "https://example.org/a"},
            },
            {
                "parent": str(b.product_key),
                "child": str(a.product_key),
                "type": "new_version",
                "evidence": {"url": "https://example.org/b"},
            },
        ],
    }
    with pytest.raises(ValueError, match="cycle"):
        configure_taxonomy(spec)
    assert not TaxonomyVersion.objects.exists()


def test_company_snapshot_uses_owned_default_label_and_keeps_its_saved_meaning():
    from core.company_labels import set_company_label
    from core.measurement_taxonomy import configure_taxonomy, subject_id
    from tests.company_factory import company_with_label

    company = company_with_label("company", "Original company name")
    set_company_label(company, "en", "English company name")
    version = configure_taxonomy(
        {
            "reviewed_by": "fixture",
            "subjects": [{"kind": "company", "key": company.pk}],
        }
    )
    identity = str(subject_id("company", company.pk))
    assert version.snapshot["subjects"][identity]["label"] == "Original company name"
    set_company_label(company, "und", "Changed company name")
    version.refresh_from_db()
    assert version.snapshot["subjects"][identity]["label"] == "Original company name"


def test_subject_constraint_rejects_mismatched_target():
    from core.models import MeasurementSubject

    brand = Brand.objects.create(nickname="lab", display_name="Lab")
    with pytest.raises(IntegrityError), transaction.atomic():
        MeasurementSubject.objects.create(subject_kind="product", brand=brand)


@pytest.mark.requires_postgres
@pytest.mark.parametrize("kind", ["product", "account", "brand", "company"])
@pytest.mark.parametrize("preexisting", [True, False])
def test_taxonomy_reuses_target_subject_or_creates_deterministic_identity(
    kind, preexisting
):
    from core.account_identity import upsert_account
    from core.measurement_taxonomy import (
        configure_taxonomy,
        prepare_taxonomy,
        subject_id,
    )
    from core.models import Company, DataSource, MeasurementSubject, TaxonomyVersion

    brand = Brand.objects.create(nickname="lab", display_name="Lab")
    if kind == "product":
        target = product("model", brand)
        key = target.product_key
    elif kind == "account":
        DataSource.objects.get_or_create(
            id="hf", defaults={"name": "HF", "source_type": "model_adoption"}
        )
        target = upsert_account(
            source="hf", external_identifier="lab", account_kind="organization"
        )
        key = target.pk
    else:
        target = (
            brand if kind == "brand" else Company.objects.create(nickname="company")
        )
        key = target.pk
    previous = None
    expected = subject_id(kind, key)
    if preexisting:
        previous = MeasurementSubject.objects.create(
            subject_kind=kind, **{kind: target}
        )
        assert previous.pk != expected
        expected = previous.pk
    before = list(MeasurementSubject.objects.values())
    spec = {"reviewed_by": "fixture", "subjects": [{"kind": kind, "key": str(key)}]}

    snapshot = prepare_taxonomy(spec)
    assert set(snapshot["subjects"]) == {str(expected)}
    assert (
        list(MeasurementSubject.objects.values()) == before
    )  # Preparation is read-only.
    version = configure_taxonomy(spec)
    assert version.snapshot == snapshot
    assert configure_taxonomy(spec).pk == version.pk
    assert TaxonomyVersion.objects.count() == 1
    subject = MeasurementSubject.objects.get(**{f"{kind}_id": key})
    assert subject.pk == expected
    assert subject.subject_kind == kind
    assert MeasurementSubject.objects.count() == 1
    if previous:
        assert list(MeasurementSubject.objects.values()) == before


@pytest.mark.requires_postgres
@pytest.mark.parametrize("other_kind", ["product", "brand"])
def test_taxonomy_rejects_generated_id_already_assigned_to_another_target(other_kind):
    from core.measurement_taxonomy import configure_taxonomy, subject_id
    from core.models import MeasurementSubject, TaxonomyVersion

    brand = Brand.objects.create(nickname="lab")
    selected = product("selected", brand)
    other = product("other", brand) if other_kind == "product" else brand
    MeasurementSubject.objects.create(
        id=subject_id("product", selected.product_key),
        subject_kind=other_kind,
        **{other_kind: other},
    )
    before = list(MeasurementSubject.objects.values())
    with pytest.raises(ValueError, match="subject identity.*another target"):
        configure_taxonomy(
            {
                "reviewed_by": "fixture",
                "subjects": [{"kind": "product", "key": str(selected.product_key)}],
            }
        )
    assert list(MeasurementSubject.objects.values()) == before
    assert not TaxonomyVersion.objects.exists()


def test_merge_parents_and_successor_diamond_keep_one_membership_and_both_paths():
    from core.measurement_taxonomy import configure_taxonomy, resolve_products
    from core.models import ProductGroupMembership

    brand = Brand.objects.create(nickname="lab")
    a, b, c, d, derivative = [product(n, brand) for n in ("a", "b", "c", "d", "merge")]
    edges = [
        (a, b, "new_version"),
        (a, c, "new_version"),
        (b, d, "new_version"),
        (c, d, "new_version"),
        (a, derivative, "merge"),
        (d, derivative, "merge"),
    ]
    spec = {
        "reviewed_by": "fixture",
        "subjects": [
            {"kind": "product", "key": str(p.product_key)}
            for p in (a, b, c, d, derivative)
        ],
        "relationships": [
            {
                "parent": str(p.product_key),
                "child": str(q.product_key),
                "type": kind,
                "evidence": {"url": "https://example.org/card"},
            }
            for p, q, kind in edges
        ],
        "groups": [
            {
                "key": "line",
                "name": "Line",
                "rule_kind": "new_version_chain",
                "root": str(a.product_key),
                "owner_brands": ["lab"],
            }
        ],
    }
    version = configure_taxonomy(spec)
    member = ProductGroupMembership.objects.get(taxonomy_version=version, product=d)
    assert len(member.evidence["supporting_paths"]) == 2
    assert len(resolve_products(version, member.group.subject.pk)) == 4
    assert not ProductGroupMembership.objects.filter(
        taxonomy_version=version, product=derivative
    ).exists()


def test_relationship_evidence_cannot_name_a_different_repository():
    from core.measurement_taxonomy import configure_taxonomy

    brand = Brand.objects.create(nickname="lab")
    a, b = product("a", brand), product("b", brand)
    with pytest.raises(ValueError, match="evidence identity"):
        configure_taxonomy(
            {
                "reviewed_by": "fixture",
                "subjects": [
                    {"kind": "product", "key": str(p.product_key)} for p in (a, b)
                ],
                "relationships": [
                    {
                        "parent": str(a.product_key),
                        "child": str(b.product_key),
                        "type": "new_version",
                        "evidence": {"parent_repo_id": "other/model"},
                    }
                ],
            }
        )
