"""Migration proof for the additive Stage 1 taxonomy schema."""

from __future__ import annotations

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from core.classification_contract import (
    LEGACY_POST_TYPE_KEYS,
    LEGACY_PRODUCT_LABEL_KEYS,
)

BEFORE = [("core", "0027_account_country_foreign_key")]
STAGE1 = [("core", "0028_ai_enrichment_stage1_taxonomy")]


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_stage1_migration_seeds_forward_and_reverse_keeps_legacy_rows():
    """The pre-publication reverse removes only additive Stage 1 schema."""
    executor = MigrationExecutor(connection)
    try:
        # The test database starts at the latest leaf. Migration 0030 is
        # intentionally irreversible and data-only, so establish this
        # historical pre-0030 fixture through the recorder before migrating
        # backwards through the older reversible migrations.
        executor.recorder.record_unapplied(
            "core", "0030_ai_enrichment_stage1_taxonomy_v2_edges"
        )
        executor = MigrationExecutor(connection)
        executor.migrate(BEFORE)
        old_apps = executor.loader.project_state(BEFORE).apps
        Brand = old_apps.get_model("core", "Brand")
        Post = old_apps.get_model("core", "Post")
        PostTypeKey = old_apps.get_model("core", "PostTypeKey")
        SentimentKey = old_apps.get_model("core", "SentimentKey")
        NationalismKey = old_apps.get_model("core", "NationalismKey")
        DiscourseKey = old_apps.get_model("core", "DiscourseKey")
        PostBrandSignal = old_apps.get_model("core", "PostBrandSignal")
        PostBrandDiscourse = old_apps.get_model("core", "PostBrandDiscourse")

        Brand.objects.create(nickname="migration-stage1", display_name="Migration")
        Post.objects.create(tweet_id="migration-stage1", text="legacy")
        PostTypeKey.objects.get_or_create(key="legacy_type")
        SentimentKey.objects.get_or_create(key="neutral")
        NationalismKey.objects.get_or_create(key="none")
        DiscourseKey.objects.get_or_create(key="legacy_discourse")
        PostBrandSignal.objects.create(
            post_id="migration-stage1",
            brand_id="migration-stage1",
            post_type_id="legacy_type",
            sentiment_id="neutral",
        )
        PostBrandDiscourse.objects.create(
            post_id="migration-stage1",
            brand_id="migration-stage1",
            discourse_id="legacy_discourse",
            act_id=0,
            china_nationalism_id="none",
            us_nationalism_id=None,
        )

        executor = MigrationExecutor(connection)
        executor.migrate(STAGE1)
        stage1_apps = executor.loader.project_state(STAGE1).apps
        ProductLabelKey = stage1_apps.get_model("core", "ProductLabelKey")
        ProductLabelLabel = stage1_apps.get_model("core", "ProductLabelLabel")
        ClassificationState = stage1_apps.get_model(
            "core", "PostBrandClassificationState"
        )
        ProductEdge = stage1_apps.get_model("core", "PostBrandProductLabel")
        Stage1PostTypeKey = stage1_apps.get_model("core", "PostTypeKey")
        assert set(ProductLabelKey.objects.values_list("key", flat=True)) == set(
            LEGACY_PRODUCT_LABEL_KEYS
        )
        assert (
            ProductLabelLabel.objects.filter(
                product_label_id__in=LEGACY_PRODUCT_LABEL_KEYS,
                lang__in=("en", "zh-cn"),
            ).count()
            == len(LEGACY_PRODUCT_LABEL_KEYS) * 2
        )
        assert set(
            Stage1PostTypeKey.objects.filter(key__in=LEGACY_POST_TYPE_KEYS).values_list(
                "key", flat=True
            )
        ) == set(LEGACY_POST_TYPE_KEYS)
        assert ClassificationState.objects.count() == 0
        assert ProductEdge.objects.count() == 0
        assert PostBrandSignal.objects.filter(post_id="migration-stage1").exists()
        assert PostBrandDiscourse.objects.filter(post_id="migration-stage1").exists()

        with connection.cursor() as cursor:
            state_constraints = connection.introspection.get_constraints(
                cursor, "posts_brands_classification_states"
            )
            product_constraints = connection.introspection.get_constraints(
                cursor, "posts_brands_product_labels"
            )
        assert state_constraints["idx_pb_cls_state_brand_outcome"]["index"]
        assert state_constraints["idx_pb_cls_state_contract"]["index"]
        assert product_constraints["idx_pb_product_brand_label"]["index"]

        executor = MigrationExecutor(connection)
        executor.migrate(BEFORE)
        restored_apps = executor.loader.project_state(BEFORE).apps
        assert (
            restored_apps.get_model("core", "PostBrandSignal")
            .objects.filter(post_id="migration-stage1")
            .exists()
        )
        assert (
            restored_apps.get_model("core", "PostBrandDiscourse")
            .objects.filter(post_id="migration-stage1")
            .exists()
        )
        # The reverse RunPython is intentionally a no-op, so shared post-type
        # lookup keys seeded by Stage 1 remain available to an application rollback.
        assert (
            restored_apps.get_model("core", "PostTypeKey")
            .objects.filter(key="hands_on_usage")
            .exists()
        )
    finally:
        MigrationExecutor(connection).migrate(
            MigrationExecutor(connection).loader.graph.leaf_nodes()
        )
