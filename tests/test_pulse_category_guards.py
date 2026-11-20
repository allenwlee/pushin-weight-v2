import pytest
from django.db import IntegrityError, connection, transaction

from core.models import Product, ProductType

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


@pytest.fixture(autouse=True)
def historical_category_rows():
    """Build old rows before the current guard, as an existing database would."""
    from django.db.migrations.executor import MigrationExecutor

    previous = [("core", "0226_chart_native_lookup_index")]
    current = [("core", "0232_pending_publication_admission_index")]
    MigrationExecutor(connection).migrate(previous)
    try:
        for code in ("llm-model", "other-ai-model", "agent-harness"):
            ProductType.objects.get_or_create(code=code)
    finally:
        MigrationExecutor(connection).migrate(current)


def test_current_categories_accept_assignments_and_legacy_inserts_fail():
    for code in ("model-llm", "model-other", "agent", "harness", "other"):
        product = Product.objects.create(
            display_name=code, product_type=ProductType.objects.get(code=code)
        )
        assert product.product_type.code == code
    legacy = ProductType.objects.get(code="llm-model")
    with pytest.raises((ValueError, IntegrityError)), transaction.atomic():
        Product.objects.create(display_name="old", product_type=legacy)


def test_raw_legacy_assignment_is_rejected():
    legacy = ProductType.objects.get(code="llm-model")
    product = Product.objects.create(display_name="pending")
    with (
        pytest.raises(IntegrityError),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "UPDATE products SET product_type_id = %s WHERE id = %s",
            [legacy.pk, product.pk],
        )


def test_model_validation_and_bulk_updates_reject_legacy_categories():
    from django.core.exceptions import ValidationError

    legacy = ProductType.objects.get(code="llm-model")
    with pytest.raises(ValidationError):
        Product(display_name="invalid", product_type=legacy).full_clean()
    first = Product.objects.create(display_name="one")
    second = Product.objects.create(display_name="two")
    first.product_type = legacy
    second.product_type = ProductType.objects.get(code="model-llm")
    with pytest.raises(IntegrityError), transaction.atomic():
        Product.objects.bulk_update([first, second], ["product_type"])
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.product_type_id is None and second.product_type_id is None


def test_legacy_value_is_readable_but_explicit_same_value_update_is_rejected():
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connection)
    previous = [("core", "0226_chart_native_lookup_index")]
    current = [("core", "0232_pending_publication_admission_index")]
    executor.migrate(previous)
    try:
        legacy = ProductType.objects.get(code="llm-model")
        product = Product.objects.create(display_name="historical", product_type=legacy)
    finally:
        MigrationExecutor(connection).migrate(current)
    product.refresh_from_db()
    assert product.product_type.code == "llm-model"
    Product.objects.filter(pk=product.pk).update(display_name="renamed")
    with pytest.raises(IntegrityError), transaction.atomic():
        Product.objects.filter(pk=product.pk).update(product_type=legacy)
    product.refresh_from_db()
    assert (
        product.display_name == "renamed" and product.product_type.code == "llm-model"
    )


@pytest.mark.parametrize("code", ["llm-model", "other-ai-model", "agent-harness"])
def test_legacy_codes_are_rejected_by_bulk_and_rare_category_writers(code):
    from core.models import Brand, Post, RareTypeCategoryAssignment

    legacy = ProductType.objects.get(code=code)
    with pytest.raises(IntegrityError), transaction.atomic():
        Product.objects.bulk_create(
            [Product(display_name="forbidden", product_type=legacy)]
        )
    post = Post.objects.create(tweet_id=f"category-{code}", text="test")
    brand = Brand.objects.create(nickname=f"category-{code}")
    with pytest.raises(IntegrityError), transaction.atomic():
        RareTypeCategoryAssignment.objects.create(
            post=post, brand=brand, category=code, classification_version="test"
        )


def test_all_current_category_codes_are_valid_rare_assignments():
    from core.models import Brand, Post, RareTypeCategoryAssignment

    post = Post.objects.create(tweet_id="current-category", text="test")
    brand = Brand.objects.create(nickname="current-category")
    for code in ("model-llm", "model-other", "agent", "harness", "other"):
        RareTypeCategoryAssignment.objects.create(
            post=post, brand=brand, category=code, classification_version="test"
        )
    assert RareTypeCategoryAssignment.objects.count() == 5


def test_catalogue_rejects_new_legacy_or_unknown_definition_and_legacy_reparent():
    current = ProductType.objects.get(code="model-llm")
    legacy = ProductType.objects.get(code="llm-model")
    with pytest.raises(IntegrityError), transaction.atomic():
        ProductType.objects.create(code="unsupported-model")
    with pytest.raises(IntegrityError), transaction.atomic():
        ProductType.objects.filter(pk=legacy.pk).update(parent=current)
    with pytest.raises(IntegrityError), transaction.atomic():
        ProductType.objects.filter(pk=current.pk).update(parent=legacy)
    ProductType.objects.get(code="other-ai-model").delete()
    with (
        pytest.raises(
            IntegrityError, match="Invalid current product category definition"
        ),
        transaction.atomic(),
    ):
        ProductType.objects.create(code="other-ai-model")


def test_copy_rejects_legacy_category():
    from django.utils import timezone
    from psycopg.errors import CheckViolation

    from core.models import Brand, Post

    post = Post.objects.create(tweet_id="copy-category", text="test")
    brand = Brand.objects.create(nickname="copy-category")
    with (
        pytest.raises(CheckViolation),
        transaction.atomic(),
        connection.cursor() as cursor,
        cursor.cursor.copy(
            "COPY rare_type_category_assignments (post_id, brand_id, category, source_evidence, classification_version, created_at) FROM STDIN"
        ) as copy,
    ):
        copy.write_row([post.pk, brand.pk, "llm-model", "{}", "test", timezone.now()])


def test_other_trigger_cannot_change_final_product_category_to_legacy():
    legacy = ProductType.objects.get(code="llm-model")
    product = Product.objects.create(display_name="guard-target")
    with (
        pytest.raises(IntegrityError),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            """CREATE FUNCTION pw_test_category_rewrite() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN NEW.product_type_id := %s; RETURN NEW; END $$""",
            [legacy.pk],
        )
        cursor.execute("""CREATE TRIGGER pw_test_category_rewrite BEFORE UPDATE OF display_name ON products
            FOR EACH ROW EXECUTE FUNCTION pw_test_category_rewrite()""")
        cursor.execute(
            "UPDATE products SET display_name='renamed' WHERE id=%s", [product.pk]
        )
    product.refresh_from_db()
    assert product.product_type_id is None and product.display_name == "guard-target"


@pytest.mark.parametrize("table", ["products", "rare_type_category_assignments"])
def test_later_insert_trigger_cannot_write_legacy_category(table):
    from core.models import Brand, Post, RareTypeCategoryAssignment

    legacy = ProductType.objects.get(code="llm-model")
    post = Post.objects.create(tweet_id=f"insert-{table}", text="test")
    brand = Brand.objects.create(nickname=f"insert-{table}")
    assignment = "NEW.product_type_id := %s" if table == "products" else "NEW.category := %s"
    value = legacy.pk if table == "products" else "llm-model"
    with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            f"CREATE FUNCTION pw_test_insert_rewrite() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN {assignment}; RETURN NEW; END $$",
            [value],
        )
        cursor.execute(
            f"CREATE TRIGGER zz_pulse_test_rewrite BEFORE INSERT ON {table} FOR EACH ROW EXECUTE FUNCTION pw_test_insert_rewrite()"
        )
        if table == "products":
            Product.objects.create(display_name="rewritten", product_type=ProductType.objects.get(code="model-llm"))
        else:
            RareTypeCategoryAssignment.objects.create(post=post, brand=brand, category="model-llm", classification_version="test")


def test_later_trigger_cannot_reparent_current_category():
    current = ProductType.objects.get(code="model-llm")
    legacy = ProductType.objects.get(code="llm-model")
    with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            "CREATE FUNCTION pw_test_reparent() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN NEW.parent_id := %s; RETURN NEW; END $$",
            [legacy.pk],
        )
        cursor.execute(
            "CREATE TRIGGER zz_test_reparent BEFORE UPDATE ON product_types FOR EACH ROW EXECUTE FUNCTION pw_test_reparent()"
        )
        ProductType.objects.filter(pk=current.pk).update(code="model-llm")
