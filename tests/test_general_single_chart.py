from datetime import date
from unittest.mock import patch

import pytest

from core.models import Product

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def test_public_chart_uses_selected_product_and_release_without_writes(client):
    product = Product.objects.create(display_name="A model", repo_id="lab/model")
    payload = {
        "product": {
            "key": str(product.product_key),
            "label": "A model",
            "release_date": "2026-08-13",
        },
        "lines": [],
        "notes": [],
    }
    with patch(
        "monitor.single_brand_chart._calculate_chart", return_value=payload
    ) as build:
        response = client.get(
            "/general/chart/",
            {"product": product.product_key, "release_date": "2026-08-13"},
            secure=True,
        )
    assert response.status_code == 200
    assert response.json() == payload
    assert build.call_args.args[0].target.product_key == product.product_key
    assert build.call_args.args[0].target.date == date(2026, 8, 13)


@pytest.mark.parametrize(
    "params",
    [
        {"product": "bad", "release_date": "2026-08-13"},
        {"product": "91a2cc4f-33dc-418c-8ed8-bcc30a099451", "release_date": "bad"},
        {"product": "91a2cc4f-33dc-418c-8ed8-bcc30a099451", "release_date": "20260813"},
        {"product": "91a2cc4f-33dc-418c-8ed8-bcc30a099451"},
    ],
)
def test_public_chart_rejects_invalid_requests(client, params):
    assert client.get("/general/chart/", params, secure=True).status_code == 400


def test_public_chart_reports_unknown_product(client):
    response = client.get(
        "/general/chart/",
        {
            "product": "91a2cc4f-33dc-418c-8ed8-bcc30a099451",
            "release_date": "2026-08-13",
        },
        secure=True,
    )
    assert response.status_code == 404


def test_public_chart_keeps_catalogued_private_and_retired_products(client):
    private = Product.objects.create(display_name="Private model", private=True)
    retired = Product.objects.create(display_name="Retired model", disabled=True)
    assert client.get("/general/chart/products/", {"q": "Private"}, secure=True).json()[
        "products"
    ][0]["key"] == str(private.product_key)
    assert client.get("/general/chart/products/", {"q": "Retired"}, secure=True).json()[
        "products"
    ][0]["key"] == str(retired.product_key)


def test_public_product_search_includes_repository_identifier(client):
    product = Product.objects.create(
        display_name="Example", repo_id="research/model-name"
    )
    response = client.get("/general/chart/products/", {"q": "model-name"}, secure=True)
    assert response.status_code == 200
    assert response.json()["products"] == [
        {"key": str(product.product_key), "label": "Example"}
    ]
    assert (
        client.get("/general/chart/products/", {"q": "m"}, secure=True).status_code
        == 400
    )
