"""Curated presentation updates preserve Meta identity and classifier aliases."""

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from core.models import Account, Brand, BrandCompany, BrandSearchTerm, Company, Product
from core.publisher_accounts import get_publisher, register_publisher
from monitor.cycle import _classification_tracked_brand_catalog
from monitor.views import _clear_home_pulse_cache
from x_monitor.attribution import _tracked_brand_catalog

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


@pytest.fixture
def meta_brand():
    company = Company.objects.create(nickname="meta", description="Preserve company metadata")
    brand = Brand.objects.create(
        nickname="llama", display_name="Meta Llama", display_name_en="Meta Llama",
        accent_color="#123456",
    )
    BrandCompany.objects.create(brand=brand, company=company)
    publisher, _ = register_publisher(
        source="hf", identifier="meta-llama", company=company, confirmed=True,
    )
    Product.objects.create(
        repo_id="meta-llama/Llama-3.3-70B-Instruct", display_name="Llama-3.3-70B-Instruct",
        brand=brand, publisher_account=publisher.account,
    )
    BrandSearchTerm.objects.create(brand=brand, term="Existing reviewed alias")
    return brand


def apply_updates(*, commit=False):
    output = StringIO()
    call_command("apply_homepage_brand_updates", commit=commit, stdout=output)
    return output.getvalue()


def catalog():
    return _tracked_brand_catalog([], [{"tracked_brand_catalog": _classification_tracked_brand_catalog()}])


def test_preview_does_not_change_identity_or_register_publishers(meta_brand):
    before = catalog()
    output = apply_updates()
    meta_brand.refresh_from_db()
    assert meta_brand.display_name == "Meta Llama"
    assert meta_brand.accent_color == "#123456"
    assert catalog() == before
    assert not Account.objects.filter(data_source_id="hf", normalized_identifier="meta-models").exists()
    assert "meta-models" in output
    assert "preview" in output


def test_apply_is_idempotent_and_preserves_products_company_and_aliases(meta_brand):
    original_product = Product.objects.get(brand=meta_brand)
    identity = (original_product.pk, original_product.product_key, original_product.publisher_account_id)
    before = catalog()
    Brand.objects.create(nickname="deepseek", accent_color="#abcdef")
    Brand.objects.create(nickname="unrelated", display_name="Leave me", accent_color="#987654")
    apply_updates(commit=True)
    after = catalog()
    assert after["revision"] != before["revision"]
    meta = next(row for row in after["brands"] if row["brand_id"] == "llama")
    assert {"Llama", "Meta Llama", "Meta", "Muse", "Existing reviewed alias"} <= set(meta["aliases"])
    assert "meta-llama/Llama-3.3-70B-Instruct" in meta["products"]
    publisher = get_publisher(source="hf", identifier="meta-models", confirmed=True)
    assert publisher.company_id == "meta"
    account_key = publisher.account_id
    apply_updates(commit=True)
    assert catalog() == after
    assert get_publisher(source="hf", identifier="meta-models").account_id == account_key
    meta_brand.refresh_from_db()
    assert (meta_brand.pk, meta_brand.display_name, meta_brand.display_name_en, meta_brand.display_name_zh_cn) == (
        "llama", "Meta", "Meta", "Meta",
    )
    assert meta_brand.accent_color == "#0089f4"
    assert Brand.objects.get(pk="deepseek").accent_color == "#2243e6"
    assert Brand.objects.get(pk="unrelated").accent_color == "#987654"
    assert Company.objects.get(pk="meta").description == "Preserve company metadata"
    original_product.refresh_from_db()
    assert (original_product.pk, original_product.product_key, original_product.publisher_account_id) == identity
    assert Product.objects.count() == 1  # Registration does not invent a catalog or release.


def test_conflicting_namespace_ownership_rolls_back_all_changes(meta_brand):
    other = Company.objects.create(nickname="other-company")
    register_publisher(source="hf", identifier="meta-models", company=other, confirmed=True)
    with pytest.raises(CommandError, match="ownership"):
        apply_updates(commit=True)
    meta_brand.refresh_from_db()
    assert meta_brand.display_name == "Meta Llama"
    assert meta_brand.accent_color == "#123456"
    assert not BrandSearchTerm.objects.filter(brand=meta_brand, term="Muse").exists()


@pytest.mark.parametrize("locale", ("en", "zh_cn", "zh_hans", "ja"))
def test_updated_brand_reaches_real_home_and_chart_payloads(meta_brand, client, locale):
    apply_updates(commit=True)
    _clear_home_pulse_cache()
    response = client.get("/", {"locale": locale}, secure=True)
    assert response.status_code == 200
    row = next(row for row in response.context["brands"] if row["nickname"] == "llama")
    assert row["display_name"] == "Meta"
    assert "Meta Llama" not in response.content.decode()
    chart = client.get("/chart/", {"locale": locale}, secure=True)
    assert chart.status_code == 200
    entry = next(row for row in chart.json()["pulse"]["entries"] if row["nickname"] == "llama")
    assert entry["display_name"] == "Meta"
    assert entry["accent_color"] == "#0089f4"


@pytest.mark.usefixtures("company_country_catalogue")
@override_settings(KNOWN_MODELS=frozenset({"llama"}))
def test_reseed_keeps_meta_names_and_color(meta_brand):
    apply_updates(commit=True)
    call_command("load_seed", brands="llama", no_accounts=True, stdout=StringIO(), stderr=StringIO())
    meta_brand.refresh_from_db()
    assert (meta_brand.display_name, meta_brand.display_name_en, meta_brand.display_name_zh_cn) == ("Meta",) * 3
    assert meta_brand.accent_color == "#0089f4"
