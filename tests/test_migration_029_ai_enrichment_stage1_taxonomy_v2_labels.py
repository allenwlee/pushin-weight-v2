"""Release A additive taxonomy-v2 lookup and label migration proof."""

from __future__ import annotations

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from core.classification_contract import (
    CANONICAL_PRODUCT_LABEL_KEYS,
    CONTRACT_VERSION,
    LEGACY_POST_TYPE_KEYS,
    LEGACY_PRODUCT_LABEL_KEYS,
    NATIONALISM_KEYS,
    SENTIMENT_KEYS,
    STAGE1_TAXONOMY_V2_POST_TYPE_KEYS,
)
from core.classification_labels import CLASSIFICATION_LABELS

BEFORE = [("core", "0028_ai_enrichment_stage1_taxonomy")]
RELEASE_A = [("core", "0029_ai_enrichment_stage1_taxonomy_v2_labels")]


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_release_a_labels_are_additive_idempotent_and_preserve_state_and_edges():
    executor = MigrationExecutor(connection)
    try:
        # Migration 0030 is deliberately irreversible and data-only. Remove
        # only its recorder row so this Release A test can build its genuine
        # pre-0029 fixture without reversing Release B data.
        executor.recorder.record_unapplied(
            "core", "0030_ai_enrichment_stage1_taxonomy_v2_edges"
        )
        executor = MigrationExecutor(connection)
        executor.migrate(BEFORE)
        apps = executor.loader.project_state(BEFORE).apps
        Brand = apps.get_model("core", "Brand")
        Post = apps.get_model("core", "Post")
        PostTypeKey = apps.get_model("core", "PostTypeKey")
        PostTypeLabel = apps.get_model("core", "PostTypeLabel")
        ProductLabelKey = apps.get_model("core", "ProductLabelKey")
        ProductLabelLabel = apps.get_model("core", "ProductLabelLabel")
        SentimentLabel = apps.get_model("core", "SentimentLabel")
        NationalismLabel = apps.get_model("core", "NationalismLabel")
        SentimentKey = apps.get_model("core", "SentimentKey")
        State = apps.get_model("core", "PostBrandClassificationState")
        Signal = apps.get_model("core", "PostBrandSignal")
        ProductEdge = apps.get_model("core", "PostBrandProductLabel")

        new_post_type_keys = set(STAGE1_TAXONOMY_V2_POST_TYPE_KEYS) - set(
            LEGACY_POST_TYPE_KEYS
        )
        new_product_keys = set(CANONICAL_PRODUCT_LABEL_KEYS) - set(
            LEGACY_PRODUCT_LABEL_KEYS
        )
        PostTypeLabel.objects.filter(post_type_id__in=new_post_type_keys).delete()
        ProductLabelLabel.objects.filter(product_label_id__in=new_product_keys).delete()
        PostTypeKey.objects.filter(key__in=new_post_type_keys).delete()
        ProductLabelKey.objects.filter(key__in=new_product_keys).delete()
        PostTypeLabel.objects.filter(lang="ja").delete()
        ProductLabelLabel.objects.filter(lang="ja").delete()
        SentimentLabel.objects.filter(lang="ja").delete()
        NationalismLabel.objects.filter(lang="ja").delete()
        assert not PostTypeKey.objects.filter(key__in=new_post_type_keys).exists()
        assert not ProductLabelKey.objects.filter(key__in=new_product_keys).exists()
        assert not any(
            Label.objects.filter(lang="ja").exists()
            for Label in (
                PostTypeLabel,
                ProductLabelLabel,
                SentimentLabel,
                NationalismLabel,
            )
        )

        Brand.objects.create(nickname="u7-migration", display_name="U7")
        Post.objects.create(tweet_id="u7-migration", text="preserve")
        PostTypeKey.objects.get_or_create(key="buzz_releases")
        ProductLabelKey.objects.get_or_create(key="product_request")
        SentimentKey.objects.get_or_create(key="positive")
        PostTypeLabel.objects.update_or_create(
            post_type_id="buzz_releases",
            lang="en",
            defaults={"label": "Preserved custom release label"},
        )
        ProductLabelLabel.objects.update_or_create(
            product_label_id="product_request",
            lang="zh-cn",
            defaults={"label": "保留的旧请求标签"},
        )
        Signal.objects.create(
            post_id="u7-migration",
            brand_id="u7-migration",
            post_type_id="buzz_releases",
            sentiment_id="positive",
        )
        State.objects.create(
            post_id="u7-migration",
            brand_id="u7-migration",
            contract_version=CONTRACT_VERSION,
            taxonomy_version="stage1-taxonomy-v1",
            prompt_version="stage1-prompt-v2",
            model="preserved-model",
            source_language="en",
            input_context_fingerprint="9" * 64,
            outcome="classified",
            sentiment_id="positive",
        )
        ProductEdge.objects.create(
            post_id="u7-migration",
            brand_id="u7-migration",
            product_label_id="product_request",
        )
        before_state = tuple(
            State.objects.filter(post_id="u7-migration").values_list(
                "contract_version", "taxonomy_version", "prompt_version", "model",
                "classified_at", "sentiment_id", "china_nationalism_id",
                "us_nationalism_id",
            ).get()
        )
        before_edges = list(
            Signal.objects.filter(post_id="u7-migration").values_list(
                "post_id", "brand_id", "post_type_id", "sentiment_id"
            )
        )
        before_product_edges = list(
            ProductEdge.objects.filter(post_id="u7-migration").values_list(
                "post_id", "brand_id", "product_label_id"
            )
        )

        for pass_number in range(2):
            MigrationExecutor(connection).migrate(RELEASE_A)
            if pass_number == 0:
                MigrationExecutor(connection).migrate(BEFORE)
        apps = MigrationExecutor(connection).loader.project_state(RELEASE_A).apps

        family_specs = (
            (
                "post_type",
                "PostTypeLabel",
                "post_type_id",
                STAGE1_TAXONOMY_V2_POST_TYPE_KEYS,
            ),
            (
                "product_label", "ProductLabelLabel", "product_label_id",
                CANONICAL_PRODUCT_LABEL_KEYS,
            ),
            ("sentiment", "SentimentLabel", "sentiment_id", SENTIMENT_KEYS),
            ("nationalism", "NationalismLabel", "nationalism_id", NATIONALISM_KEYS),
        )
        ja_count = 0
        for family, model_name, foreign_key, keys in family_specs:
            Label = apps.get_model("core", model_name)
            for key in keys:
                rows = list(
                    Label.objects.filter(**{foreign_key: key}).values_list(
                        "lang", "label"
                    )
                )
                assert dict(rows) == CLASSIFICATION_LABELS[family][key]
                ja_count += sum(lang == "ja" for lang, _label in rows)
        assert ja_count == 25

        State = apps.get_model("core", "PostBrandClassificationState")
        Signal = apps.get_model("core", "PostBrandSignal")
        assert tuple(
            State.objects.filter(post_id="u7-migration").values_list(
                "contract_version", "taxonomy_version", "prompt_version", "model",
                "classified_at", "sentiment_id", "china_nationalism_id",
                "us_nationalism_id",
            ).get()
        ) == before_state
        assert list(
            Signal.objects.filter(post_id="u7-migration").values_list(
                "post_id", "brand_id", "post_type_id", "sentiment_id"
            )
        ) == before_edges
        assert list(
            apps.get_model("core", "PostBrandProductLabel")
            .objects.filter(post_id="u7-migration")
            .values_list("post_id", "brand_id", "product_label_id")
        ) == before_product_edges
        assert apps.get_model("core", "PostTypeKey").objects.filter(
            key="buzz_releases"
        ).exists()
        assert apps.get_model("core", "ProductLabelKey").objects.filter(
            key="product_request"
        ).exists()
        assert apps.get_model("core", "PostTypeLabel").objects.get(
            post_type_id="buzz_releases", lang="en"
        ).label == "Preserved custom release label"
        assert apps.get_model("core", "ProductLabelLabel").objects.get(
            product_label_id="product_request", lang="zh-cn"
        ).label == "保留的旧请求标签"
        assert not apps.get_model("core", "PostTypeLabel").objects.filter(
            post_type_id="buzz_releases", lang="ja"
        ).exists()
        assert not apps.get_model("core", "ProductLabelLabel").objects.filter(
            product_label_id="product_request", lang="ja"
        ).exists()
    finally:
        MigrationExecutor(connection).migrate(
            MigrationExecutor(connection).loader.graph.leaf_nodes()
        )
