"""Bounded current-versus-historical Stage 1 scalar reader tests."""

from __future__ import annotations

import pytest

from core.classification_contract import (
    CANONICAL_TAXONOMY_VERSION,
    CONTRACT_VERSION,
    TAXONOMY_VERSION,
)
from core.classification_readers import read_brand_scalars, read_brand_scalars_many
from core.models import (
    Brand,
    DiscourseKey,
    NationalismKey,
    Post,
    PostBrandClassificationState,
    PostBrandDiscourse,
    PostBrandSignal,
    PostTypeKey,
    SentimentKey,
)

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def seed_keys():
    for key in ("positive", "negative", "neutral"):
        SentimentKey.objects.get_or_create(key=key)
    for key in ("none", "pro", "anti"):
        NationalismKey.objects.get_or_create(key=key)
    PostTypeKey.objects.get_or_create(key="other")
    DiscourseKey.objects.get_or_create(key="")


def pair(suffix: str):
    brand = Brand.objects.create(
        nickname=f"reader-{suffix}",
        display_name=f"Reader {suffix}",
    )
    post = Post.objects.create(tweet_id=f"reader-{suffix}", text="text")
    return post, brand


def current_state(post, brand, **overrides):
    values = {
        "contract_version": CONTRACT_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "prompt_version": "prompt",
        "model": "model",
        "source_language": "en",
        "input_context_fingerprint": "0" * 64,
        "outcome": "context_missing",
        "sentiment_id": None,
        "china_nationalism_id": None,
        "us_nationalism_id": None,
    }
    values.update(overrides)
    return PostBrandClassificationState.objects.create(
        post=post,
        brand=brand,
        **values,
    )


def test_current_version_owns_explicit_nulls_without_legacy_fallthrough():
    seed_keys()
    post, brand = pair("current-null")
    current_state(post, brand)
    PostBrandSignal.objects.create(
        post=post,
        brand=brand,
        post_type_id="other",
        sentiment_id="positive",
    )
    PostBrandDiscourse.objects.create(
        post=post,
        brand=brand,
        discourse_id="",
        act_id=0,
        china_nationalism_id="pro",
        us_nationalism_id="anti",
    )

    result = read_brand_scalars(post_id=post.pk, brand_id=brand.pk)

    assert result.source == "current"
    assert result.sentiment is None
    assert result.china_nationalism is None
    assert result.us_nationalism is None
    assert result.conflicts == ()


def test_prompt_version_is_provenance_not_reader_currency():
    seed_keys()
    post, brand = pair("prompt-provenance")
    current_state(
        post,
        brand,
        prompt_version="different-prompt-same-contract",
        sentiment_id="neutral",
    )

    result = read_brand_scalars(post_id=post.pk, brand_id=brand.pk)

    assert result.source == "current"
    assert result.sentiment == "neutral"


def test_unrecognized_state_blocks_legacy_fallback():
    seed_keys()
    post, brand = pair("old-version")
    current_state(post, brand, taxonomy_version="old-taxonomy")
    PostBrandSignal.objects.create(
        post=post,
        brand=brand,
        post_type_id="other",
        sentiment_id="negative",
    )

    result = read_brand_scalars(post_id=post.pk, brand_id=brand.pk)

    assert result.source == "unrecognized"
    assert result.sentiment is None
    assert result.contract_version == CONTRACT_VERSION
    assert result.taxonomy_version == "old-taxonomy"


def test_v2_current_state_owns_explicit_nulls_without_legacy_fallthrough():
    seed_keys()
    post, brand = pair("v2-current-null")
    current_state(post, brand, taxonomy_version=CANONICAL_TAXONOMY_VERSION)
    PostBrandSignal.objects.create(
        post=post, brand=brand, post_type_id="other", sentiment_id="negative"
    )

    result = read_brand_scalars(post_id=post.pk, brand_id=brand.pk)

    assert result.source == "current"
    assert result.sentiment is None
    assert result.taxonomy_version == CANONICAL_TAXONOMY_VERSION


def test_historical_reader_accepts_one_distinct_value_regardless_of_row_order():
    seed_keys()
    post, brand = pair("unique")
    for act_id in (2, 0, 1):
        PostBrandDiscourse.objects.create(
            post=post,
            brand=brand,
            discourse_id="",
            act_id=act_id,
            china_nationalism_id="pro",
            us_nationalism_id="none",
        )

    result = read_brand_scalars(post_id=post.pk, brand_id=brand.pk)

    assert result.source == "historical"
    assert result.china_nationalism == "pro"
    assert result.us_nationalism == "none"
    assert result.conflicts == ()


def test_historical_conflicts_are_unknown_and_reported_per_axis():
    seed_keys()
    post, brand = pair("conflict")
    PostBrandSignal.objects.create(
        post=post,
        brand=brand,
        post_type_id="other",
        sentiment_id="positive",
    )
    PostBrandDiscourse.objects.create(
        post=post,
        brand=brand,
        discourse_id="",
        act_id=0,
        china_nationalism_id="pro",
        us_nationalism_id="none",
    )
    PostBrandDiscourse.objects.create(
        post=post,
        brand=brand,
        discourse_id="",
        act_id=1,
        china_nationalism_id="anti",
        us_nationalism_id="none",
    )

    result = read_brand_scalars(post_id=post.pk, brand_id=brand.pk)

    assert result.source == "historical"
    assert result.china_nationalism is None
    assert result.us_nationalism == "none"
    assert result.conflicts == ("china_nationalism",)


def test_bulk_reader_uses_three_queries_for_many_pairs(django_assert_num_queries):
    seed_keys()
    current_post, current_brand = pair("bulk-current")
    legacy_post, legacy_brand = pair("bulk-legacy")
    unknown_post, unknown_brand = pair("bulk-unknown")
    current_state(
        current_post,
        current_brand,
        sentiment_id="neutral",
        china_nationalism_id=None,
        us_nationalism_id="none",
    )
    PostBrandSignal.objects.create(
        post=legacy_post,
        brand=legacy_brand,
        post_type_id="other",
        sentiment_id="positive",
    )
    pairs = [
        (current_post.pk, current_brand.pk),
        (legacy_post.pk, legacy_brand.pk),
        (unknown_post.pk, unknown_brand.pk),
    ]

    with django_assert_num_queries(3):
        result = read_brand_scalars_many(pairs)

    assert result[pairs[0]].source == "current"
    assert result[pairs[1]].source == "historical"
    assert result[pairs[2]].source == "unknown"


def test_empty_bulk_read_uses_no_queries(django_assert_num_queries):
    with django_assert_num_queries(0):
        assert read_brand_scalars_many([]) == {}
