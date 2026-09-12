from django.db import migrations

CONTRACT_VERSION = "stage1-v1"
LEGACY_TAXONOMY_VERSION = "stage1-taxonomy-v1"
POST_TYPE_ALIASES = {
    "buzz_releases": "releases_updates",
    "performance_comparisons": "results_evaluations",
    "feedback_questions": "questions_requests",
    "event_announcement": "events_opportunities",
}
PRODUCT_LABEL_ALIASES = {"product_request": "ideas_requests"}


def canonicalize_stage1_edges(apps, schema_editor):
    database = schema_editor.connection.alias
    State = apps.get_model("core", "PostBrandClassificationState")
    Signal = apps.get_model("core", "PostBrandSignal")
    ProductLabel = apps.get_model("core", "PostBrandProductLabel")

    eligible_states = (
        State.objects.using(database)
        .filter(
            contract_version=CONTRACT_VERSION,
            taxonomy_version=LEGACY_TAXONOMY_VERSION,
            outcome="classified",
        )
        .values_list("post_id", "brand_id", "sentiment_id")
    )

    for post_id, brand_id, sentiment_id in eligible_states.iterator():
        signals = list(
            Signal.objects.using(database)
            .filter(post_id=post_id, brand_id=brand_id)
            .values_list("post_type_id", flat=True)
        )
        if signals:
            if sentiment_id is None:
                raise ValueError(
                    "eligible Stage 1 type edge has no authoritative state sentiment"
                )
            canonical_types = {
                POST_TYPE_ALIASES.get(post_type, post_type) for post_type in signals
            }
            Signal.objects.using(database).filter(
                post_id=post_id, brand_id=brand_id
            ).delete()
            Signal.objects.using(database).bulk_create(
                [
                    Signal(
                        post_id=post_id,
                        brand_id=brand_id,
                        post_type_id=post_type,
                        sentiment_id=sentiment_id,
                    )
                    for post_type in sorted(canonical_types)
                ]
            )

        product_labels = list(
            ProductLabel.objects.using(database)
            .filter(post_id=post_id, brand_id=brand_id)
            .values_list("product_label_id", flat=True)
        )
        if product_labels:
            canonical_labels = {
                PRODUCT_LABEL_ALIASES.get(product_label, product_label)
                for product_label in product_labels
            }
            ProductLabel.objects.using(database).filter(
                post_id=post_id, brand_id=brand_id
            ).delete()
            ProductLabel.objects.using(database).bulk_create(
                [
                    ProductLabel(
                        post_id=post_id,
                        brand_id=brand_id,
                        product_label_id=product_label,
                    )
                    for product_label in sorted(canonical_labels)
                ]
            )


class Migration(migrations.Migration):
    atomic = True
    dependencies = [("core", "0029_ai_enrichment_stage1_taxonomy_v2_labels")]
    operations = [migrations.RunPython(canonicalize_stage1_edges)]
