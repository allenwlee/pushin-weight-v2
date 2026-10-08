import pytest

from core.measurement_taxonomy import configure_taxonomy, subject_id
from core.models import Brand, Company, Post, Product

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def test_two_product_mentions_count_once_for_company_and_broad_stays_broad():
    from core.measurement_attribution import record_attribution, subject_posts

    brand = Brand.objects.create(nickname="minimax")
    company = Company.objects.create(nickname="minimax")
    a = Product.objects.create(repo_id="MiniMaxAI/M2", type="llm-model", brand=brand)
    b = Product.objects.create(repo_id="MiniMaxAI/M3", type="llm-model", brand=brand)
    subjects = [
        {"kind": "company", "key": company.pk},
        {"kind": "brand", "key": brand.pk},
    ] + [{"kind": "product", "key": str(p.product_key)} for p in (a, b)]
    edges = [
        {
            "parent": str(subject_id("company", company.pk)),
            "child": str(subject_id("brand", brand.pk)),
            "kind": "owns",
            "evidence": {"review": "fixture"},
        }
    ] + [
        {
            "parent": str(subject_id("brand", brand.pk)),
            "child": str(subject_id("product", p.product_key)),
            "kind": "offers",
            "evidence": {"review": "fixture"},
        }
        for p in (a, b)
    ]
    version = configure_taxonomy(
        {"reviewed_by": "fixture", "subjects": subjects, "affiliations": edges}
    )
    post = Post.objects.create(tweet_id="1", text="M2 and M3")
    for product, name, start in [(a, "M2", 0), (b, "M3", 7)]:
        record_attribution(
            version,
            post,
            subject_id("product", product.product_key),
            observed_name=name,
            policy_version="fixture",
            evidence={
                "reviewed_by": "fixture",
                "span_start": start,
                "span_end": start + 2,
            },
        )
    broad = Post.objects.create(tweet_id="2", text="MiniMax")
    record_attribution(
        version,
        broad,
        subject_id("company", company.pk),
        observed_name="MiniMax",
        policy_version="fixture",
        evidence={"reviewed_by": "fixture", "span_start": 0, "span_end": 7},
    )
    assert (
        subject_posts(
            version, subject_id("company", company.pk), policy_version="fixture"
        ).count()
        == 2
    )
    assert (
        subject_posts(
            version, subject_id("product", a.product_key), policy_version="fixture"
        ).count()
        == 1
    )
    assert (
        not subject_posts(
            version, subject_id("product", a.product_key), policy_version="fixture"
        )
        .filter(pk="2")
        .exists()
    )
