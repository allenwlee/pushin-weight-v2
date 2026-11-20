"""Old source classifications remain readable without rewriting their evidence."""
from types import SimpleNamespace

import pytest
from django.db import transaction
from django.db.migrations.executor import MigrationExecutor

from core.models import Brand, Post, Product, ProductType, RareTypeCategoryAssignment
from core.product_verification import _proposal_categories, _upsert_hf_product

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


@pytest.mark.parametrize('legacy,current', [('llm-model', 'model-llm'), ('other-ai-model', 'model-other'), ('agent-harness', None)])
def test_old_assignment_is_interpreted_without_changing_original(legacy, current):
    executor = MigrationExecutor(__import__('django.db', fromlist=['connection']).connection)
    previous, latest = [('core', '0234_each_signal_aggregation')], [('core', '0241_pulse_category_evidence_guard')]
    executor.migrate(previous)
    try:
        post = Post.objects.create(tweet_id='old-' + legacy, text='release')
        brand = Brand.objects.create(nickname='old-' + legacy)
        row = RareTypeCategoryAssignment.objects.create(post=post, brand=brand, category=legacy,
                                                        classification_version='historical')
    finally:
        MigrationExecutor(__import__('django.db', fromlist=['connection']).connection).migrate(latest)
    proposal = SimpleNamespace(source_post_id=post.pk, proposed_brand_id=brand.pk, proposed_candidate_id=None)
    translated = _proposal_categories(proposal)
    assert translated == ([current] if current else ['agent', 'harness'])
    row.refresh_from_db()
    assert row.category == legacy


@pytest.mark.parametrize('legacy,current', [('llm-model', 'model-llm'), ('other-ai-model', 'model-other')])
def test_existing_legacy_product_accepts_equivalent_verification_without_retyping(legacy, current):
    from django.db import connection

    previous, latest = [('core', '0234_each_signal_aggregation')], [('core', '0241_pulse_category_evidence_guard')]
    MigrationExecutor(connection).migrate(previous)
    try:
        brand = Brand.objects.create(nickname='legacy-product-' + legacy)
        old_type, _ = ProductType.objects.get_or_create(code=legacy)
        product = Product.objects.create(repo_id='owner/model', display_name='model', brand=brand, product_type=old_type)
    finally:
        MigrationExecutor(connection).migrate(latest)
    with transaction.atomic():
        updated = _upsert_hf_product(repo_id='owner/model', brand=brand, hf_org=None, metadata={}, product_type=current)
    assert updated.pk == product.pk and updated.product_type.code == legacy
