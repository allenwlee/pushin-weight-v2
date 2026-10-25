"""Exercise catalog ownership, immutable snapshots and concurrent reparenting."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import psycopg
import pytest
from django.db import IntegrityError, connection, transaction

from core.measurement_taxonomy import configure_taxonomy
from core.models import DataSource, Product, ProductType
from core.product_metadata import apply_metadata
from core.source_vocabulary import reference_id
from tests.product_factory import product_type_fields

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def test_metadata_keeps_original_gating_and_cannot_use_another_sources_library():
    for code in ("hf", "github"):
        DataSource.objects.get_or_create(
            pk=code, defaults={"name": code, "source_type": "model_adoption"}
        )
    product = Product.objects.create(repo_id="rg5/model")
    apply_metadata(
        product,
        {
            "gated": False,
            "library_name": "transformers",
            "pipeline_tag": "text-generation",
        },
        group="detail",
    )
    product.refresh_from_db()
    assert product.gating_state.code == "public"
    assert product.raw["gated"] is False
    assert product.hf_metadata["fields"]["gated"] is False
    assert product.library_name.code == "transformers"
    assert product.library_name.data_source_id == "hf"
    before = (product.gating_state_id, product.library_name_id, product.pipeline_tag_id)
    apply_metadata(product, {"downloads": 3}, group="listing")
    product.refresh_from_db()
    assert (
        product.gating_state_id,
        product.library_name_id,
        product.pipeline_tag_id,
    ) == before
    other = reference_id("software_libraries", "github", "transformers")
    with pytest.raises(IntegrityError), transaction.atomic():
        Product.objects.filter(pk=product.pk).update(library_name_id=other)


def test_reparenting_changes_only_new_taxonomy_snapshots():
    product = Product.objects.create(
        repo_id="rg5/taxonomy", **product_type_fields(Product, "llm-model")
    )
    spec = {
        "reviewed_by": "fixture",
        "subjects": [{"kind": "product", "key": str(product.product_key)}],
    }
    original = configure_taxonomy(spec)
    original_snapshot, original_hash = original.snapshot, original.version_hash
    assert (
        "category_ancestry"
        not in original.snapshot["products"][str(product.product_key)]
    )
    parent = ProductType.objects.create(code="ai-model")
    ProductType.objects.filter(pk=product.product_type_id).update(parent=parent)
    revised = configure_taxonomy(spec)
    assert revised.pk != original.pk
    assert revised.snapshot["products"][str(product.product_key)][
        "category_ancestry"
    ] == [
        "llm-model",
        "ai-model",
    ]
    original.refresh_from_db()
    assert (original.snapshot, original.version_hash) == (
        original_snapshot,
        original_hash,
    )


@pytest.mark.django_db(transaction=True)
def test_concurrent_opposite_category_edges_cannot_both_commit():
    first = ProductType.objects.create(code="concurrent-first")
    second = ProductType.objects.create(code="concurrent-second")
    started = Event()
    parameters = connection.get_connection_params()

    def opposite_edge():
        with psycopg.connect(**parameters) as db:
            db.execute("SET statement_timeout='10s'")
            started.set()
            try:
                db.execute(
                    "UPDATE product_types SET parent_id=%s WHERE id=%s",
                    [first.pk, second.pk],
                )
                db.commit()
                return "committed"
            except psycopg.errors.CheckViolation:
                db.rollback()
                return "cycle-rejected"

    with ThreadPoolExecutor(max_workers=1) as executor:
        with transaction.atomic():
            ProductType.objects.filter(pk=first.pk).update(parent=second)
            future = executor.submit(opposite_edge)
            assert started.wait(5)
            assert not future.done()
        assert future.result(timeout=12) == "cycle-rejected"
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.parent_id == second.pk and second.parent_id is None
