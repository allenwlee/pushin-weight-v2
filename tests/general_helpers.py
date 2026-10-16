"""Deterministic source records for the General reader and browser tests."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256

from core.classification_contract import (
    CONTRACT_VERSION,
    PROMPT_VERSION,
    TAXONOMY_VERSION,
)
from core.models import (
    Brand,
    Post,
    PostBrandClassificationState,
    PostBrandSignal,
    PostSynthesisArtifact,
    PostSynthesisText,
    PostTypeKey,
    SentimentKey,
)

NOW = datetime(2026, 10, 8, 6, 0, tzinfo=UTC)


def classified_post(
    key, category="job_listings", *, brand="qwen", age=1, taxonomy=TAXONOMY_VERSION
):
    owner, _ = Brand.objects.get_or_create(
        nickname=brand, defaults={"display_name": brand.title()}
    )
    post_type, _ = PostTypeKey.objects.get_or_create(key=category)
    sentiment, _ = SentimentKey.objects.get_or_create(key="neutral")
    post, _ = Post.objects.get_or_create(
        tweet_id=str(key),
        defaults={
            "text": f"Original source {key}",
            "commentary_en": f"Saved commentary {key}",
            "author_handle": "source_author",
            "tweet_url": f"https://x.com/source_author/status/{key}",
        },
    )
    Post.objects.filter(pk=post.pk).update(
        fetched_at=NOW - timedelta(hours=age), created_at=NOW - timedelta(days=10)
    )
    post.refresh_from_db()
    PostBrandSignal.objects.get_or_create(
        post=post, brand=owner, post_type=post_type, defaults={"sentiment": sentiment}
    )
    PostBrandClassificationState.objects.update_or_create(
        post=post,
        brand=owner,
        defaults={
            "contract_version": CONTRACT_VERSION,
            "taxonomy_version": taxonomy,
            "prompt_version": PROMPT_VERSION,
            "model": "fixture",
            "input_context_fingerprint": sha256(str(key).encode()).hexdigest(),
            "outcome": "classified",
        },
    )
    return post


def saved_commentary(post, *, current=True, revision="one"):
    artifact = PostSynthesisArtifact.objects.create(
        post=post,
        input_context_fingerprint=sha256(revision.encode()).hexdigest(),
        prompt_version="fixture-v1",
        model="fixture",
        provider_role="fixture",
        state="succeeded",
        is_current=current,
        started_at=NOW - timedelta(hours=2),
        completed_at=NOW - timedelta(hours=1),
    )
    for locale, text in [
        ("en", "Normalized commentary"),
        ("zh-cn", "已保存的评论"),
        ("ja", "保存された解説"),
    ]:
        PostSynthesisText.objects.create(artifact=artifact, locale=locale, text=text)
    return artifact
