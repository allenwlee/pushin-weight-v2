"""Shared source codes retain their namespace and database-enforced identity."""

import pytest
from django.db import IntegrityError, transaction

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def test_library_identity_is_source_qualified_and_keeps_exact_provider_code():
    from core.models import DataSource, SoftwareLibrary
    from core.source_vocabulary import reference_id

    for source in ("hf", "github"):
        DataSource.objects.get_or_create(
            pk=source, defaults={"name": source, "source_type": "model_adoption"}
        )
    first = reference_id("software_libraries", "hf", "Model Optimizer")
    assert reference_id("software_libraries", "hf", "Model Optimizer") == first
    other = reference_id("software_libraries", "github", "Model Optimizer")
    assert first != other
    assert SoftwareLibrary.objects.get(pk=first).code == "Model Optimizer"
    assert reference_id("software_libraries", "hf", None) is None
    assert reference_id("software_libraries", "hf", "") is None
    with pytest.raises(ValueError, match="code"):
        reference_id("software_libraries", "hf", " Model Optimizer ")
    with pytest.raises(IntegrityError), transaction.atomic():
        SoftwareLibrary.objects.filter(pk=first).update(code="renamed")


def test_identifier_namespace_distinguishes_resource_kind_and_unscoped_identity():
    from core.models import DataSource, SourceIdentifierNamespace
    from core.source_vocabulary import reference_id

    DataSource.objects.get_or_create(
        pk="hf", defaults={"name": "Hugging Face", "source_type": "model_adoption"}
    )
    repository = reference_id(
        "source_identifier_namespaces", "hf", "", subject_kind="repository"
    )
    model = reference_id("source_identifier_namespaces", "hf", "", subject_kind="model")
    assert repository != model
    assert SourceIdentifierNamespace.objects.get(pk=repository).code == ""
    with pytest.raises(ValueError, match="subject kind"):
        reference_id("source_identifier_namespaces", "hf", "model")


def test_product_category_parent_can_change_but_cycles_and_identity_edits_fail():
    from core.models import ProductType

    root = ProductType.objects.create(code="ai-model")
    leaf = ProductType.objects.create(code="test-language-model", parent=root)
    other = ProductType.objects.create(code="language-model")
    ProductType.objects.filter(pk=leaf.pk).update(parent=other)
    leaf.refresh_from_db()
    assert leaf.parent_id == other.pk
    with pytest.raises(IntegrityError), transaction.atomic():
        ProductType.objects.filter(pk=other.pk).update(parent=leaf)
    with pytest.raises(IntegrityError), transaction.atomic():
        ProductType.objects.filter(pk=leaf.pk).update(code="renamed")
