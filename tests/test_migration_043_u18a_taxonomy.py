"""Additive migration proof for the U18A catalog and compatibility state."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from core.classification_labels import (
    AUDIENCE_TOPIC_LABELS,
    GEOPOLITICAL_MODE_LABELS,
    NATIONALISM_LABELS,
    POST_TYPE_LABELS,
    PRODUCT_LABEL_LABELS,
    UNTRACKED_BRAND_PROMOTION_LABELS,
)

BEFORE = [("core", "0042_u18_two_role_classification_lineage")]
AFTER = [("core", "0043_audiencetopicconcept_audiencetopicscheme_and_more")]
LOCALES = ("en", "zh-cn", "ja")

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_u18a_migration_seeds_catalogs_and_copies_v3_stances_exactly():
    executor = MigrationExecutor(connection)
    try:
        executor.migrate(BEFORE)
        old_apps = executor.loader.project_state(BEFORE).apps
        Brand = old_apps.get_model("core", "Brand")
        NationalismKey = old_apps.get_model("core", "NationalismKey")
        Post = old_apps.get_model("core", "Post")
        State = old_apps.get_model("core", "PostBrandClassificationState")

        brand = Brand.objects.create(nickname="u18a-schema", display_name="U18A")
        post = Post.objects.create(tweet_id="u18a-schema-post", text="source")
        for key in ("anti", "constructive_critical", "legacy_operator_key"):
            NationalismKey.objects.get_or_create(key=key)
        state = State.objects.create(
            post=post,
            brand=brand,
            contract_version="classification/v3",
            taxonomy_version="taxonomy/v3",
            prompt_version="prompt/v3",
            model="fixture",
            input_context_fingerprint="a" * 64,
            outcome="classified",
            china_nationalism_id="anti",
            us_nationalism_id="constructive_critical",
        )
        legacy_post = Post.objects.create(
            tweet_id="u18a-schema-legacy-post", text="legacy"
        )
        legacy_state = State.objects.create(
            post=legacy_post,
            brand=brand,
            contract_version="classification/v3",
            taxonomy_version="taxonomy/v3",
            prompt_version="prompt/v3",
            model="fixture",
            input_context_fingerprint="b" * 64,
            outcome="classified",
            china_nationalism_id="legacy_operator_key",
            us_nationalism_id="anti",
        )

        # PostgreSQL must flush the FK trigger work before migration DDL adds
        # the new compatibility-column indexes.
        transaction.commit()

        executor = MigrationExecutor(connection)
        executor.migrate(AFTER)
        apps = executor.loader.project_state(AFTER).apps
        State = apps.get_model("core", "PostBrandClassificationState")
        TopicScheme = apps.get_model("core", "AudienceTopicScheme")
        TopicConcept = apps.get_model("core", "AudienceTopicConcept")
        TopicLabel = apps.get_model("core", "AudienceTopicLabel")
        GeoKey = apps.get_model("core", "GeopoliticalModeKey")
        GeoLabel = apps.get_model("core", "GeopoliticalModeLabel")
        StanceKey = apps.get_model("core", "NationalStanceKey")
        StanceLabel = apps.get_model("core", "NationalStanceLabel")
        PromotionKey = apps.get_model("core", "UntrackedBrandPromotionKey")
        PromotionLabel = apps.get_model("core", "UntrackedBrandPromotionLabel")
        PostTypeLabel = apps.get_model("core", "PostTypeLabel")
        ProductLabelLabel = apps.get_model("core", "ProductLabelLabel")

        migrated = State.objects.get(post_id=state.post_id, brand_id=state.brand_id)
        assert migrated.china_nationalism_id == migrated.china_national_stance_id == "anti"
        assert (
            migrated.us_nationalism_id
            == migrated.us_national_stance_id
            == "constructive_critical"
        )
        migrated_legacy = State.objects.get(
            post_id=legacy_state.post_id, brand_id=legacy_state.brand_id
        )
        assert migrated_legacy.china_national_stance_id == "legacy_operator_key"
        assert StanceKey.objects.filter(key="legacy_operator_key").exists()

        scheme = TopicScheme.objects.get(key="ai_audience_topics/v1")
        assert scheme.revision == 1
        assert TopicConcept.objects.filter(scheme=scheme).count() == 7
        assert TopicLabel.objects.filter(concept__scheme=scheme, revision=1).count() == 21
        for key, labels in AUDIENCE_TOPIC_LABELS.items():
            concept = TopicConcept.objects.get(scheme=scheme, key=key)
            assert dict(
                TopicLabel.objects.filter(concept=concept, revision=1).values_list(
                    "lang", "label"
                )
            ) == labels

        for Key, Label, field, labels in (
            (GeoKey, GeoLabel, "geopolitical_mode", GEOPOLITICAL_MODE_LABELS),
            (StanceKey, StanceLabel, "national_stance", NATIONALISM_LABELS),
            (
                PromotionKey,
                PromotionLabel,
                "untracked_brand_promotion",
                UNTRACKED_BRAND_PROMOTION_LABELS,
            ),
        ):
            expected_keys = set(labels)
            if Key is StanceKey:
                expected_keys.add("legacy_operator_key")
            assert set(Key.objects.values_list("key", flat=True)) == expected_keys
            for key, expected in labels.items():
                assert dict(
                    Label.objects.filter(**{f"{field}_id": key}).values_list(
                        "lang", "label"
                    )
                ) == expected

        assert dict(
            PostTypeLabel.objects.filter(post_type_id="results_analysis").values_list(
                "lang", "label"
            )
        ) == POST_TYPE_LABELS["results_analysis"]
        assert dict(
            PostTypeLabel.objects.filter(post_type_id="news_reporting").values_list(
                "lang", "label"
            )
        ) == POST_TYPE_LABELS["news_reporting"]
        assert dict(
            ProductLabelLabel.objects.filter(
                product_label_id="investigate_claim"
            ).values_list("lang", "label")
        ) == PRODUCT_LABEL_LABELS["investigate_claim"]
    finally:
        MigrationExecutor(connection).migrate(
            MigrationExecutor(connection).loader.graph.leaf_nodes()
        )


def test_u18a_subject_evidence_is_post_bound_and_keeps_exact_account_optional():
    from core.models import (
        Account,
        BrandDiscoveryCandidate,
        Post,
        PostUntrackedBrandPromotion,
        UntrackedBrandPromotionEvidence,
    )

    now = timezone.now()
    account = Account.objects.create(author_id="u18a-account", handle="candidate")
    post = Post.objects.create(tweet_id="u18a-promotion", author=account, text="Promo")
    other_post = Post.objects.create(tweet_id="u18a-other", text="Other")
    candidate = BrandDiscoveryCandidate.objects.create(
        observed_name="XYZ Harness",
        aliases=["XYZ"],
        candidate_handles=["xyzharness"],
        candidate_identity="b" * 64,
        first_observed_at=now,
        last_observed_at=now,
    )
    promotion = PostUntrackedBrandPromotion.objects.create(
        post=post,
        promotion_keys=["general"],
        contract_version="classification/v4",
        taxonomy_version="taxonomy/v4",
        prompt_version="prompt/v4",
        model="fixture",
        provider_role="content",
    )
    evidence = UntrackedBrandPromotionEvidence.objects.create(
        promotion=promotion,
        brand_discovery_candidate=candidate,
        source_post=post,
        exact_matched_account=account,
        observed_name="XYZ Harness",
        aliases=["XYZ"],
        handles=["xyzharness"],
        domains=["xyz.example"],
        products=["Harness"],
        hashtags=["XYZ"],
        evidence_spans=[{"start": 0, "end": 3}],
        subject_identity="c" * 64,
        first_seen_at=now,
        last_seen_at=now + timedelta(minutes=1),
    )
    assert evidence.exact_matched_account_id == account.author_id
    assert evidence.promotion.post_id == evidence.source_post_id == post.tweet_id

    with pytest.raises(IntegrityError), transaction.atomic():
        UntrackedBrandPromotionEvidence.objects.create(
            promotion=promotion,
            brand_discovery_candidate=candidate,
            source_post=other_post,
            observed_name="Wrong post",
            subject_identity="d" * 64,
            first_seen_at=now,
            last_seen_at=now,
        )


def test_u18a_seed_command_restores_the_full_v4_catalog_idempotently():
    from django.core.management import call_command

    from core.models import (
        AudienceTopicConcept,
        AudienceTopicLabel,
        AudienceTopicScheme,
        PostTypeKey,
        PostTypeLabel,
        ProductLabelKey,
        ProductLabelLabel,
    )

    PostTypeLabel.objects.filter(post_type_id="news_reporting").delete()
    PostTypeKey.objects.filter(key="news_reporting").delete()
    ProductLabelLabel.objects.filter(product_label_id="investigate_claim").delete()
    ProductLabelKey.objects.filter(key="investigate_claim").delete()
    AudienceTopicLabel.objects.filter(concept__scheme_id="ai_audience_topics/v1").delete()
    AudienceTopicConcept.objects.filter(scheme_id="ai_audience_topics/v1").delete()
    AudienceTopicScheme.objects.filter(key="ai_audience_topics/v1").delete()

    call_command("seed_i18n_labels", verbosity=0)
    call_command("seed_i18n_labels", verbosity=0)

    assert dict(
        PostTypeLabel.objects.filter(post_type_id="news_reporting").values_list(
            "lang", "label"
        )
    ) == POST_TYPE_LABELS["news_reporting"]
    assert dict(
        ProductLabelLabel.objects.filter(
            product_label_id="investigate_claim"
        ).values_list("lang", "label")
    ) == PRODUCT_LABEL_LABELS["investigate_claim"]
    assert AudienceTopicLabel.objects.filter(
        concept__scheme_id="ai_audience_topics/v1", revision=1
    ).count() == 21
