"""The shared manifest-driven, seven-day ORM cohort for Each browser evidence.

Call after seeding the base fixture in an isolated test/preview database. The
manifest cohort replaces DeepSeek's base associations and keeps its exact count.
"""

from datetime import timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from core.classification_contract import (
    CONTRACT_VERSION,
    PROMPT_VERSION,
    TAXONOMY_VERSION,
)
from core.models import (
    Account,
    AudienceTopicConcept,
    AudienceTopicScheme,
    BrandAccount,
    GeopoliticalModeKey,
    Post,
    PostBrand,
    PostBrandAudienceTopic,
    PostBrandClassificationState,
    PostBrandGeopoliticalMode,
    PostBrandProductLabel,
    PostBrandSignal,
    PostSynthesisArtifact,
    PostSynthesisText,
    PostTypeKey,
    PostUntrackedBrandPromotion,
    ProductLabelKey,
    Role,
    SentimentKey,
)


def seed_each_area_orm(seed: dict) -> int:
    """Create the exact Each manifest cohort and return its persisted post count."""
    # A real seven-day cohort gives every classifier a changing, filled stack.
    # One isolated populated bucket would exercise the controls but draw no area.
    sent_keys = seed["sentiments"]
    type_keys = seed["post_types"]
    product_keys = seed["products"]
    geo_keys = seed["geopolitical_modes"]
    topic_keys = seed["topics"]
    for key in sent_keys:
        SentimentKey.objects.get_or_create(key=key)
    for key in type_keys:
        PostTypeKey.objects.get_or_create(key=key)
    for key in product_keys:
        ProductLabelKey.objects.get_or_create(key=key)
    for key in geo_keys:
        GeopoliticalModeKey.objects.get_or_create(key=key)
    scheme, _ = AudienceTopicScheme.objects.get_or_create(
        key="ai_audience_topics/v1",
        defaults={"revision": 1, "manifest_hash": "0" * 64},
    )
    concepts = [
        AudienceTopicConcept.objects.get_or_create(scheme=scheme, key=key)[0]
        for key in topic_keys
    ]
    authors = []
    for role_key in seed["roles"]:
        account = Account.objects.create(
            author_id=f"each-area-{role_key}",
            handle=f"each_area_{role_key}",
            display_name=f"Each area {role_key}",
        )
        if role_key != "other":
            role, _ = Role.objects.get_or_create(key=role_key)
            BrandAccount.objects.create(brand_id="deepseek", account=account, role=role)
        authors.append(account)
    local_now = timezone.now().astimezone(ZoneInfo("Asia/Tokyo"))
    today = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    elapsed_today = local_now - today
    identity = {
        "taxonomy_version": TAXONOMY_VERSION,
        "prompt_version": PROMPT_VERSION,
        "model": "fixture-stage1",
        "provider_role": "classifier",
        "evidence": {"fixture": "each-area-seven-day"},
    }
    # Keep the real chart cohort exactly the 62 manifest posts.
    PostBrand.objects.filter(brand_id="deepseek").delete()
    for day, count in enumerate(seed["counts"]):
        for ordinal in range(count):
            # All timestamps precede the current clock and stay inside the
            # intended Japan calendar day, including a run near midnight.
            created_at = today - timedelta(days=6 - day) + (
                elapsed_today * (ordinal + 1) / (count + 1)
            )
            language = seed["languages"][(ordinal + day) % 3]
            author = authors[(ordinal + day) % len(authors)]
            post = Post.objects.create(
                tweet_id=f"each-area-{day}-{ordinal}",
                author=author,
                author_handle=author.handle,
                created_at=created_at,
                lang_detected=language,
                text=f"Synthetic chart fixture day {day}, post {ordinal}.",
                text_en="Synthetic chart fixture.",
                text_zh_cn="图表测试数据。",
            )
            PostBrand.objects.create(post=post, brand_id="deepseek")
            # Keep normal feed observers active, with already-complete saved
            # commentary. Otherwise their independent 2/4/8-second polling can
            # overlap chart emphasis and contaminate its strict request count.
            artifact = PostSynthesisArtifact.objects.create(
                post=post, input_context_fingerprint=f"{day * 100 + ordinal + 1:064x}",
                prompt_version="fixture-v1", model="fixture", provider_role="fixture",
                state=PostSynthesisArtifact.State.SUCCEEDED, is_current=True,
                started_at=local_now, completed_at=local_now,
            )
            PostSynthesisText.objects.bulk_create([
                PostSynthesisText(artifact=artifact, locale=locale, text=text)
                for locale, text in seed["saved_commentary"].items()
            ])
            PostUntrackedBrandPromotion.objects.create(
                post=post,
                promotion_keys=[seed["promotions"][(ordinal + day) % 3]],
                contract_version=CONTRACT_VERSION,
                **identity,
            )
            if ordinal == count - 1 and day % 2 == 0:
                continue  # Keep genuine Unclassified areas in the fixture.
            sentiment = (
                "positive" if ordinal < 2 + day % 4
                else "negative" if ordinal % 3 == 0
                else "mixed" if ordinal % 3 == 1
                else "neutral"
            )
            PostBrandClassificationState.objects.create(
                post=post,
                brand_id="deepseek",
                contract_version=CONTRACT_VERSION,
                taxonomy_version=TAXONOMY_VERSION,
                prompt_version=PROMPT_VERSION,
                model="fixture-stage1",
                source_language=language,
                input_context_fingerprint=f"{day * 100 + ordinal + 1:064x}",
                outcome=PostBrandClassificationState.Outcome.CLASSIFIED,
                sentiment_id=sentiment,
            )
            PostBrandSignal.objects.create(
                post=post, brand_id="deepseek",
                post_type_id=type_keys[(ordinal + day) % 3], sentiment_id=sentiment,
            )
            if ordinal % 4 != 2:
                product = "bug" if ordinal < 2 + day % 3 else product_keys[ordinal % 3]
                PostBrandProductLabel.objects.create(
                    post=post, brand_id="deepseek", product_label_id=product,
                )
            if ordinal % 4:
                PostBrandAudienceTopic.objects.create(
                    post=post, brand_id="deepseek", concept=concepts[(ordinal + day) % 3],
                    scheme=scheme, scheme_revision=scheme.revision,
                    **{key: value for key, value in identity.items() if key != "taxonomy_version"},
                )
            PostBrandGeopoliticalMode.objects.create(
                post=post, brand_id="deepseek",
                geopolitical_mode_id=geo_keys[(ordinal + day) % 3], **identity,
            )
    return Post.objects.filter(tweet_id__startswith="each-area-").count()
