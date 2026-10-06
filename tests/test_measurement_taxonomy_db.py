import pytest
from django.db import IntegrityError, transaction

from core.models import Brand, Product

pytestmark = pytest.mark.django_db


def product(name, brand):
    return Product.objects.create(repo_id=f"lab/{name}", brand=brand, type="llm-model")


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


def test_subject_constraint_rejects_mismatched_target():
    from core.models import MeasurementSubject

    brand = Brand.objects.create(nickname="lab", display_name="Lab")
    with pytest.raises(IntegrityError), transaction.atomic():
        MeasurementSubject.objects.create(subject_kind="product", brand=brand)


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
            {"kind": "product", "key": str(p.product_key)} for p in (a, b, c, d, derivative)
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
                "subjects": [{"kind": "product", "key": str(p.product_key)} for p in (a, b)],
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
