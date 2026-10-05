from datetime import UTC, datetime

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from core.models import Brand, BrandCompany, Company, HFOrg, Post, PostBrand, Product
from monitor.management.commands.export_benchmark_inputs import export_inputs

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_export_preserves_canonical_products_utc_counts_and_never_writes():
    company = Company.objects.create(nickname="maker")
    alpha = Brand.objects.create(nickname="alpha", display_name="Alpha")
    beta = Brand.objects.create(nickname="beta", display_name="Beta")
    for brand in (alpha, beta):
        BrandCompany.objects.create(brand=brand, company=company)
    org = HFOrg.objects.create(namespace="maker", company=company, confirmed=True)
    opened = Product.objects.create(
        repo_id="maker/Alpha-1", brand=alpha, hf_org=org, type="llm-model"
    )
    closed = Product.objects.create(
        repo_id=None, display_name="Beta Closed", brand=beta, type="llm-model"
    )
    Product.objects.create(
        repo_id="maker/private", brand=alpha, hf_org=org, type="llm-model", private=True
    )
    Product.objects.create(
        repo_id="maker/vision", brand=alpha, hf_org=org, type="other-ai-model"
    )
    for name, time in (
        ("before", "2026-09-30T23:59:59+00:00"),
        ("first", "2026-10-01T00:00:00+00:00"),
        ("last", "2026-10-01T23:59:59+00:00"),
        ("after", "2026-10-02T00:00:00+00:00"),
    ):
        post = Post.objects.create(
            tweet_id=name, created_at=datetime.fromisoformat(time)
        )
        PostBrand.objects.create(post=post, brand=alpha)
        if name == "last":
            PostBrand.objects.create(post=post, brand=beta)
    before = list(Product.objects.values())
    with CaptureQueriesContext(connection) as captured:
        result = export_inputs(["alpha", "beta"], "2026-10-01", "2026-10-01")
    assert list(Product.objects.values()) == before
    assert {p["product_key"] for p in result["products"]} == {
        str(opened.product_key),
        str(closed.product_key),
    }
    assert {p["brand_id"]: p["repo_id"] for p in result["products"]} == {
        "alpha": "maker/Alpha-1",
        "beta": None,
    }
    assert result["posts"]["counts"] == [
        {"date": "2026-10-01", "brand_id": "alpha", "count": 2},
        {"date": "2026-10-01", "brand_id": "beta", "count": 1},
    ]
    sql = [query["sql"].upper() for query in captured]
    assert any("READ ONLY" in q and "REPEATABLE READ" in q for q in sql)
    assert not any(q.startswith(("INSERT", "UPDATE", "DELETE", "ALTER")) for q in sql)
    assert datetime.fromisoformat(result["exported_at"]).tzinfo == UTC


def test_export_rejects_unknown_and_sentinel_brands():
    Brand.objects.create(nickname="sentinel", is_sentinel=True)
    for brand in ("sentinel", "missing"):
        with pytest.raises(ValueError, match="unknown or sentinel"):
            export_inputs([brand], "2026-10-01", "2026-10-01")
