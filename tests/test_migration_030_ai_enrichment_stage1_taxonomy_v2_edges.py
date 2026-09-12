"""Release B eligible-only taxonomy edge migration proof."""

from __future__ import annotations

import pytest
from django.db import connection
from django.db.migrations.exceptions import IrreversibleError
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("core", "0029_ai_enrichment_stage1_taxonomy_v2_labels")]
RELEASE_B = [("core", "0030_ai_enrichment_stage1_taxonomy_v2_edges")]
POST_TYPE_ALIASES = {
    "buzz_releases": "releases_updates",
    "performance_comparisons": "results_evaluations",
    "feedback_questions": "questions_requests",
    "event_announcement": "events_opportunities",
}
STATE_PROVENANCE_FIELDS = (
    "contract_version",
    "taxonomy_version",
    "prompt_version",
    "model",
    "source_language",
    "input_context_fingerprint",
    "outcome",
    "classified_at",
    "sentiment_id",
    "china_nationalism_id",
    "us_nationalism_id",
)


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_release_b_rewrites_only_v1_state_edges_and_preserves_provenance():
    executor = MigrationExecutor(connection)
    try:
        # pytest-django creates the database at the leaf. This migration is
        # data-only, so remove only its recorder row to establish the real
        # pre-0030 fixture without attempting the intentionally forbidden
        # reverse operation.
        executor.recorder.record_unapplied(
            "core", "0030_ai_enrichment_stage1_taxonomy_v2_edges"
        )
        executor = MigrationExecutor(connection)
        executor.migrate(BEFORE)
        apps = executor.loader.project_state(BEFORE).apps
        Brand = apps.get_model("core", "Brand")
        Post = apps.get_model("core", "Post")
        PostTypeKey = apps.get_model("core", "PostTypeKey")
        ProductLabelKey = apps.get_model("core", "ProductLabelKey")
        SentimentKey = apps.get_model("core", "SentimentKey")
        EnrichmentState = apps.get_model("core", "PostEnrichmentState")
        State = apps.get_model("core", "PostBrandClassificationState")
        Signal = apps.get_model("core", "PostBrandSignal")
        ProductEdge = apps.get_model("core", "PostBrandProductLabel")

        SentimentKey.objects.get_or_create(key="positive")
        SentimentKey.objects.get_or_create(key="negative")
        for key in (*POST_TYPE_ALIASES, *POST_TYPE_ALIASES.values(), "hands_on_usage"):
            PostTypeKey.objects.get_or_create(key=key)
        for key in ("product_request", "ideas_requests"):
            ProductLabelKey.objects.get_or_create(key=key)

        fixtures = (
            ("eligible", "stage1-v1", "stage1-taxonomy-v1", "stage1-prompt-v2"),
            ("v2", "stage1-v1", "stage1-taxonomy-v2", "stage1-prompt-v2"),
            (
                "unknown-contract",
                "unknown-contract",
                "stage1-taxonomy-v1",
                "stage1-prompt-v2",
            ),
            (
                "unknown-taxonomy",
                "stage1-v1",
                "unknown-taxonomy",
                "stage1-prompt-v2",
            ),
            ("old-prompt", "stage1-v1", "stage1-taxonomy-v1", "arbitrary-prompt"),
            ("unversioned", None, None, None),
        )
        for suffix, contract, taxonomy, prompt in fixtures:
            Brand.objects.create(nickname=suffix, display_name=suffix)
            Post.objects.create(tweet_id=suffix, text=suffix)
            Signal.objects.create(
                post_id=suffix,
                brand_id=suffix,
                post_type_id="buzz_releases",
                sentiment_id="negative",
            )
            ProductEdge.objects.create(
                post_id=suffix,
                brand_id=suffix,
                product_label_id="product_request",
            )
            if contract is not None:
                State.objects.create(
                    post_id=suffix,
                    brand_id=suffix,
                    contract_version=contract,
                    taxonomy_version=taxonomy,
                    prompt_version=prompt,
                    model=f"preserved-model-{suffix}",
                    source_language="en",
                    input_context_fingerprint=suffix[0] * 64,
                    outcome="classified",
                    sentiment_id="positive",
                )

        EnrichmentState.objects.create(
            post_id="eligible",
            translation_status="succeeded",
            classification_status="succeeded",
            classification_attempts=2,
        )

        # Every renamed type has both its alias and canonical membership. The
        # migration must collapse all four collisions and rebuild the complete
        # set with authoritative state sentiment.
        Signal.objects.filter(post_id="eligible").delete()
        for post_type in (*POST_TYPE_ALIASES, *POST_TYPE_ALIASES.values()):
            Signal.objects.create(
                post_id="eligible",
                brand_id="eligible",
                post_type_id=post_type,
                sentiment_id="negative",
            )
        Signal.objects.create(
            post_id="eligible",
            brand_id="eligible",
            post_type_id="hands_on_usage",
            sentiment_id="negative",
        )
        ProductEdge.objects.create(
            post_id="eligible",
            brand_id="eligible",
            product_label_id="ideas_requests",
        )
        before_state = tuple(
            State.objects.filter(post_id="eligible")
            .values_list(*STATE_PROVENANCE_FIELDS)
            .get()
        )
        before_old_prompt_state = tuple(
            State.objects.filter(post_id="old-prompt")
            .values_list(*STATE_PROVENANCE_FIELDS)
            .get()
        )
        before_enrichment = tuple(
            EnrichmentState.objects.filter(post_id="eligible")
            .values_list(
                "translation_status",
                "classification_status",
                "classification_attempts",
                "updated_at",
            )
            .get()
        )

        MigrationExecutor(connection).migrate(RELEASE_B)
        apps = MigrationExecutor(connection).loader.project_state(RELEASE_B).apps
        EnrichmentState = apps.get_model("core", "PostEnrichmentState")
        State = apps.get_model("core", "PostBrandClassificationState")
        Signal = apps.get_model("core", "PostBrandSignal")
        ProductEdge = apps.get_model("core", "PostBrandProductLabel")

        assert set(
            Signal.objects.filter(post_id="eligible").values_list(
                "post_type_id", "sentiment_id"
            )
        ) == {
            ("events_opportunities", "positive"),
            ("hands_on_usage", "positive"),
            ("questions_requests", "positive"),
            ("releases_updates", "positive"),
            ("results_evaluations", "positive"),
        }
        assert list(
            ProductEdge.objects.filter(post_id="eligible").values_list(
                "product_label_id", flat=True
            )
        ) == ["ideas_requests"]
        assert (
            tuple(
                State.objects.filter(post_id="eligible")
                .values_list(*STATE_PROVENANCE_FIELDS)
                .get()
            )
            == before_state
        )
        assert list(
            Signal.objects.filter(post_id="old-prompt").values_list(
                "post_type_id", "sentiment_id"
            )
        ) == [("releases_updates", "positive")]
        assert list(
            ProductEdge.objects.filter(post_id="old-prompt").values_list(
                "product_label_id", flat=True
            )
        ) == ["ideas_requests"]
        assert (
            tuple(
                State.objects.filter(post_id="old-prompt")
                .values_list(*STATE_PROVENANCE_FIELDS)
                .get()
            )
            == before_old_prompt_state
        )
        assert (
            tuple(
                EnrichmentState.objects.filter(post_id="eligible")
                .values_list(
                    "translation_status",
                    "classification_status",
                    "classification_attempts",
                    "updated_at",
                )
                .get()
            )
            == before_enrichment
        )

        for suffix in ("v2", "unknown-contract", "unknown-taxonomy", "unversioned"):
            assert list(
                Signal.objects.filter(post_id=suffix).values_list(
                    "post_type_id", "sentiment_id"
                )
            ) == [("buzz_releases", "negative")]
            assert list(
                ProductEdge.objects.filter(post_id=suffix).values_list(
                    "product_label_id", flat=True
                )
            ) == ["product_request"]

        before_reverse = list(
            Signal.objects.order_by("post_id", "post_type_id").values_list(
                "post_id", "brand_id", "post_type_id", "sentiment_id"
            )
        )
        with pytest.raises(IrreversibleError):
            MigrationExecutor(connection).migrate(BEFORE)
        assert (
            list(
                Signal.objects.order_by("post_id", "post_type_id").values_list(
                    "post_id", "brand_id", "post_type_id", "sentiment_id"
                )
            )
            == before_reverse
        )
        assert (
            MigrationExecutor(connection)
            .recorder.applied_migrations()
            .get(("core", "0030_ai_enrichment_stage1_taxonomy_v2_edges"))
            is not None
        )
    finally:
        MigrationExecutor(connection).migrate(
            MigrationExecutor(connection).loader.graph.leaf_nodes()
        )
