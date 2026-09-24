import pytest

from core.models import Product
from core.product_metadata import apply_metadata

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def test_rich_metadata_survives_lean_refresh_and_curated_fields_survive():
    product = Product.objects.create(
        repo_id="lab/model",
        display_name="Reviewed name",
        raw={"review_evidence": "keep"},
    )
    identity = (product.pk, product.repo_id)
    apply_metadata(
        product,
        {
            "id": "lab/model",
            "siblings": [{"rfilename": "weights", "size": 900}],
            "cardData": {"license": "apache-2.0"},
        },
        group="detail",
    )
    apply_metadata(
        product,
        {
            "id": "lab/model",
            "siblings": [{"rfilename": "weights"}],
            "downloadsAllTime": 4_000_000_000,
            "future": {"false": False},
        },
        group="expanded",
    )
    apply_metadata(
        product,
        {"id": "lab/model", "siblings": [], "downloadsAllTime": 0},
        group="listing",
    )
    product.refresh_from_db()
    assert (product.pk, product.repo_id) == identity
    assert product.display_name == "Reviewed name"
    assert product.siblings == [{"rfilename": "weights", "size": 900}]
    assert product.downloads_all_time == 4_000_000_000
    assert product.raw["review_evidence"] == "keep"
    assert product.hf_metadata["fields"]["future"] == {"false": False}
    apply_metadata(
        product, {"id": "lab/model", "siblings": [], "cardData": None}, group="detail"
    )
    product.refresh_from_db()
    assert product.siblings == []
    assert product.card_data is None


def test_sparse_expansion_cannot_erase_detailed_files():
    product = Product.objects.create(repo_id="lab/model")
    apply_metadata(
        product,
        {
            "id": "lab/model",
            "siblings": [{"rfilename": "weights", "size": 10}],
            "downloads": 0,
        },
        group="detail",
    )
    apply_metadata(
        product,
        {"id": "lab/model", "siblings": [{"rfilename": "weights"}], "sha": "next"},
        group="expanded",
    )
    product.refresh_from_db()
    assert product.siblings[0]["size"] == 10
    assert product.downloads == 0
    assert product.sha == "next"


def test_pre_ledger_rich_columns_survive_first_listing():
    product = Product.objects.create(
        repo_id="lab/old",
        siblings=[{"rfilename": "w", "size": 10}],
        card_data={"license": "mit"},
    )
    apply_metadata(
        product,
        {"id": "lab/old", "siblings": [{"rfilename": "w"}], "cardData": None},
        group="listing",
    )
    product.refresh_from_db()
    assert product.siblings[0]["size"] == 10
    assert product.card_data == {"license": "mit"}


@pytest.mark.django_db(transaction=True)
def test_additive_migration_preserves_existing_products():
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connection)
    before = [("core", "0044_merge_20260918_1344")]
    after_hf = [("core", "0045_hf_catalog_observations")]
    after_merged = [("core", "0056_merge_hf_catalog_rare_types")]
    executor.migrate(before)
    try:
        old_product = executor.loader.project_state(before).apps.get_model(
            "core", "Product"
        )
        hf = old_product.objects.create(
            repo_id="lab/existing", downloads=2_147_483_647, raw={"review": "kept"}
        )
        other = old_product.objects.create(
            repo_id="lab/other", display_name="Curated name"
        )
        identities = [(hf.pk, hf.repo_id), (other.pk, other.repo_id)]
        executor = MigrationExecutor(connection)
        executor.migrate(after_hf)
        hf_product = executor.loader.project_state(after_hf).apps.get_model(
            "core", "Product"
        )
        assert hf_product.objects.get(pk=hf.pk).raw == {"review": "kept"}
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(after_merged)
    assert [
        (Product.objects.get(pk=pk).pk, Product.objects.get(pk=pk).repo_id)
        for pk, _ in identities
    ] == identities
    assert Product.objects.get(pk=hf.pk).raw == {"review": "kept"}
    Product.objects.filter(pk=hf.pk).update(downloads=4_000_000_000)
    assert Product.objects.get(pk=hf.pk).downloads == 4_000_000_000
