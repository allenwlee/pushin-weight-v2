"""Stage 1 contract and writer regression net. Synthetic cases are non-gold."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.classification_contract import (
    CANONICAL_POST_TYPE_KEYS,
    CANONICAL_PRODUCT_LABEL_KEYS,
    CANONICAL_PROMPT_VERSION,
    CANONICAL_TAXONOMY_VERSION,
    COMPATIBLE_TAXONOMY_VERSIONS,
    CONTRACT_VERSION,
    LEGACY_STAGE1_PROMPT_VERSION,
    LEGACY_STAGE1_TAXONOMY_VERSION,
    POST_TYPE_KEYS,
    PRODUCT_LABEL_KEYS,
    PROMPT_VERSION,
    TAXONOMY_KEY_CROSSWALK,
    TAXONOMY_VERSION,
    STAGE1_PROMPT_V3_VERSION,
    STAGE1_TAXONOMY_V2_POST_TYPE_KEYS,
    STAGE1_TAXONOMY_V2_VERSION,
    canonicalize_taxonomy_key,
    parse_stage1_classifications,
    taxonomy_crosswalk_rows,
)

FIXTURE_PATH = Path("tests/fixtures/classification_stage1_contract_v1.json")


def _contract_fixture():
    return json.loads(FIXTURE_PATH.read_text())


def test_contract_fixture_is_explicitly_synthetic_and_non_gold():
    fixture = _contract_fixture()

    assert fixture["provenance"]["kind"] == "synthetic"
    assert fixture["provenance"]["gold"] is False
    assert "accuracy" in fixture["provenance"]["note"]
    assert fixture["contract_version"] == "stage1-v1"
    assert fixture["taxonomy_version"] == "stage1-taxonomy-v3"


@pytest.mark.parametrize(
    "case",
    _contract_fixture()["cases"],
    ids=lambda case: case["name"],
)
def test_stored_fixture_matches_expected_contract_outcome(case):
    parsed = parse_stage1_classifications(
        case["classifications"], case["expected_brand_ids"]
    )

    assert (parsed is not None) is case["expected_valid"]
    if case["expected_valid"]:
        assert parsed == case["expected_canonical"]
    else:
        assert "expected_canonical" not in case


def test_stored_fixture_covers_taxonomy_languages_and_context_sources():
    cases = _contract_fixture()["cases"]
    valid_rows = [
        row
        for case in cases
        if case["expected_valid"]
        for row in case["classifications"]
    ]
    assert {
        post_type for row in valid_rows for post_type in row["post_types"]
    } == set(POST_TYPE_KEYS)
    assert {
        label for row in valid_rows for label in row["product_labels"]
    } == set(PRODUCT_LABEL_KEYS)
    assert {case["source_language"] for case in cases} >= {"en", "zh-Hans", "ja"}
    assert {
        source for case in cases for source in case["context_provenance"]
    } == {"stored_quote", "local_parent"}


def test_taxonomy_v3_versions_and_allowlists_are_the_active_write_target():
    assert CONTRACT_VERSION == "stage1-v1"
    assert LEGACY_STAGE1_TAXONOMY_VERSION == "stage1-taxonomy-v1"
    assert LEGACY_STAGE1_PROMPT_VERSION == "stage1-prompt-v2"
    assert TAXONOMY_VERSION == CANONICAL_TAXONOMY_VERSION
    assert PROMPT_VERSION == CANONICAL_PROMPT_VERSION
    assert POST_TYPE_KEYS is CANONICAL_POST_TYPE_KEYS
    assert PRODUCT_LABEL_KEYS is CANONICAL_PRODUCT_LABEL_KEYS
    assert STAGE1_TAXONOMY_V2_VERSION == "stage1-taxonomy-v2"
    assert STAGE1_PROMPT_V3_VERSION == "stage1-prompt-v3"
    assert CANONICAL_TAXONOMY_VERSION == "stage1-taxonomy-v3"
    assert CANONICAL_PROMPT_VERSION == "stage1-prompt-v13"
    assert COMPATIBLE_TAXONOMY_VERSIONS == (
        LEGACY_STAGE1_TAXONOMY_VERSION,
        STAGE1_TAXONOMY_V2_VERSION,
        CANONICAL_TAXONOMY_VERSION,
    )


def test_compatible_crosswalk_is_total_ordered_and_collision_free():
    expected_aliases = {
        ("post_type", "buzz_releases"): "releases_updates",
        ("post_type", "performance_comparisons"): "results_evaluations",
        ("post_type", "feedback_questions"): "questions_requests",
        ("post_type", "event_announcement"): "events_opportunities",
        ("product_label", "product_request"): "ideas_requests",
    }
    pairs = [(family, source) for family, source, _ in TAXONOMY_KEY_CROSSWALK]

    assert len(pairs) == len(set(pairs))
    assert {
        (family, source): canonical
        for family, source, canonical in TAXONOMY_KEY_CROSSWALK
        if source != canonical
    } == expected_aliases
    assert all(
        canonicalize_taxonomy_key("post_type", key) == key
        for key in (
            *STAGE1_TAXONOMY_V2_POST_TYPE_KEYS,
            *CANONICAL_POST_TYPE_KEYS,
        )
    )
    assert {
        canonicalize_taxonomy_key("product_label", key)
        for key in (*PRODUCT_LABEL_KEYS, *CANONICAL_PRODUCT_LABEL_KEYS)
    } == set(CANONICAL_PRODUCT_LABEL_KEYS)
    assert all(
        canonicalize_taxonomy_key(family, key) == key
        for family, keys in (
            ("post_type", CANONICAL_POST_TYPE_KEYS),
            ("product_label", CANONICAL_PRODUCT_LABEL_KEYS),
        )
        for key in keys
    )
    assert canonicalize_taxonomy_key("post_type", "unknown") is None
    assert canonicalize_taxonomy_key("unknown", "other") is None
    assert taxonomy_crosswalk_rows("post_type") == tuple(
        (source, canonical)
        for family, source, canonical in TAXONOMY_KEY_CROSSWALK
        if family == "post_type"
    )
    with pytest.raises(ValueError, match="Unknown taxonomy family"):
        taxonomy_crosswalk_rows("unknown")


def test_v3_parser_accepts_active_keys_and_rejects_earlier_provider_keys():
    row = {
        "brand_id": "deepseek",
        "outcome": "classified",
        "post_types": ["releases_updates"],
        "product_labels": [],
        "sentiment": "neutral",
        "china_nationalism": None,
        "us_nationalism": None,
    }
    assert parse_stage1_classifications([row], ["deepseek"]) is not None

    row["post_types"] = ["buzz_releases"]
    assert parse_stage1_classifications([row], ["deepseek"]) is None

    row["post_types"] = ["events_opportunities"]
    assert parse_stage1_classifications([row], ["deepseek"]) is None

    row["post_types"] = ["other"]
    row["product_labels"] = ["product_request"]
    assert parse_stage1_classifications([row], ["deepseek"]) is None


def test_contract_preserves_all_types_and_empty_product_labels():
    parsed = parse_stage1_classifications(
        [
            {
                "brand_id": "deepseek",
                "outcome": "classified",
                "post_types": [
                    "releases_updates",
                    "hands_on_usage",
                    "results_evaluations",
                    "questions_requests",
                    "advertising_marketing",
                    "events",
                    "opportunities",
                    "job_listings",
                    "personnel_changes",
                    "opinions_reactions",
                    "research_explanations",
                    "business_finance",
                ],
                "product_labels": [],
                "sentiment": "mixed",
                "china_nationalism": "none",
                "us_nationalism": None,
            }
        ],
        ["deepseek"],
    )
    assert parsed is not None
    assert len(parsed["deepseek"]["post_types"]) == 12
    assert parsed["deepseek"]["product_labels"] == []


@pytest.mark.parametrize(
    "row",
    [
        {
            "brand_id": "deepseek",
            "outcome": "classified",
            "post_types": [],
            "product_labels": [],
            "sentiment": "neutral",
            "china_nationalism": "none",
            "us_nationalism": "none",
        },
        {
            "brand_id": "deepseek",
            "outcome": "classified",
            "post_types": ["other", "hands_on_usage"],
            "product_labels": [],
            "sentiment": "neutral",
            "china_nationalism": "none",
            "us_nationalism": "none",
        },
        {
            "brand_id": "deepseek",
            "outcome": "classified",
            "post_types": ["bogus"],
            "product_labels": [],
            "sentiment": "neutral",
            "china_nationalism": "none",
            "us_nationalism": "none",
        },
        {
            "brand_id": "deepseek",
            "outcome": "classified",
            "post_types": ["other"],
            "product_labels": [],
            "sentiment": "neutral",
            "china_nationalism": "none",
        },
        {
            "brand_id": "deepseek",
            "outcome": "context_missing",
            "post_types": ["other"],
            "product_labels": [],
            "sentiment": None,
            "china_nationalism": None,
            "us_nationalism": None,
        },
    ],
)
def test_contract_rejects_missing_or_fabricated_judgments(row):
    assert parse_stage1_classifications([row], ["deepseek"]) is None


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_cycle_does_not_mark_flags_only_result_classified(monkeypatch):
    """Characterization: pre-cutover writer incorrectly succeeds here."""
    from core.models import (
        Brand,
        Post,
        PostBrand,
        PostEnrichmentState,
        UnsanctionedFlagKey,
    )
    from monitor.cycle import CycleRunner
    from x_monitor import attribution, reattribute, translator
    from x_monitor.config import Config

    brand = Brand.objects.create(nickname="stage1-red", display_name="Stage 1")
    post = Post.objects.create(tweet_id="stage1-flags-only", text="Stage 1")
    PostBrand.objects.create(post=post, brand=brand)
    PostEnrichmentState.objects.create(post=post)
    UnsanctionedFlagKey.objects.get_or_create(key="scam")
    client = object()
    monkeypatch.setattr(
        reattribute, "build_translator_client_from_env", lambda cfg: client
    )
    monkeypatch.setattr(
        reattribute, "build_anthropic_client_from_env", lambda cfg: client
    )
    monkeypatch.setattr(
        translator,
        "translate_batch_pragmatics",
        lambda tweets, locales, client, **kwargs: [
            {
                "tweet_id": tweet["tweet_id"],
                "text_en": tweet["text"],
                "text_zh_cn": "阶段一",
                "lang_detected": "en",
            }
            for tweet in tweets
        ],
    )
    monkeypatch.setattr(
        attribution,
        "classify_batch_pragmatics_full",
        lambda *args, **kwargs: [
            {"by_brand": {}, "unsanctioned_flags": ["scam"], "valid": False}
        ],
    )

    CycleRunner(
        cfg=Config(enabled_models=["deepseek"], daily_ceiling=100)
    )._run_post_fetch([], run_id="stage1-red")
    state = PostEnrichmentState.objects.get(post=post)
    assert state.classification_status == PostEnrichmentState.Status.PENDING


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_writer_replaces_one_brand_exactly_without_touching_another():
    from core.models import (
        Brand,
        NationalismKey,
        Post,
        PostBrand,
        PostBrandProductLabel,
        PostBrandSignal,
        PostEnrichmentState,
        PostTypeKey,
        ProductLabelKey,
        SentimentKey,
    )
    from monitor.cycle import _publish_stage1_classification

    for key in ("positive", "negative", "neutral", "mixed"):
        SentimentKey.objects.get_or_create(key=key)
    for key in ("none", "mild_pro", "pro", "constructive_critical", "anti", "mixed"):
        NationalismKey.objects.get_or_create(key=key)
    for key in ("hands_on_usage", "questions_requests", "business_finance"):
        PostTypeKey.objects.get_or_create(key=key)
    for key in ("bug", "complaint", "testimonial"):
        ProductLabelKey.objects.get_or_create(key=key)
    post = Post.objects.create(
        tweet_id="stage1-replace", text="text", lang_detected="en"
    )
    alpha = Brand.objects.create(nickname="stage1-alpha", display_name="Alpha")
    beta = Brand.objects.create(nickname="stage1-beta", display_name="Beta")
    PostBrand.objects.bulk_create(
        [PostBrand(post=post, brand=alpha), PostBrand(post=post, brand=beta)]
    )
    PostEnrichmentState.objects.create(post=post, claim_run_id="replace")
    tweet = {"text": "text", "context": []}
    old = {
        "valid": True,
        "unsanctioned_flags": [],
        "by_brand": {
            "stage1-alpha": {
                "outcome": "classified",
                "post_types": ["hands_on_usage", "questions_requests"],
                "product_labels": ["bug", "complaint"],
                "sentiment": "negative",
                "china_nationalism": "none",
                "us_nationalism": None,
            },
            "stage1-beta": {
                "outcome": "classified",
                "post_types": ["business_finance"],
                "product_labels": ["testimonial"],
                "sentiment": "positive",
                "china_nationalism": None,
                "us_nationalism": "none",
            },
        },
    }
    _publish_stage1_classification(
        post_id=post.pk, result=old, tweet=tweet, model="flash", run_id="replace"
    )
    replacement = {
        "valid": True,
        "unsanctioned_flags": [],
        "by_brand": {
            "stage1-alpha": {
                "outcome": "classified",
                "post_types": ["questions_requests"],
                "product_labels": [],
                "sentiment": "neutral",
                "china_nationalism": None,
                "us_nationalism": "none",
            },
            "stage1-beta": old["by_brand"]["stage1-beta"],
        },
    }
    _publish_stage1_classification(
        post_id=post.pk,
        result=replacement,
        tweet=tweet,
        model="flash",
        run_id="replace",
    )
    assert list(
        PostBrandSignal.objects.filter(post=post, brand=alpha).values_list(
            "post_type_id", flat=True
        )
    ) == ["questions_requests"]
    assert not PostBrandProductLabel.objects.filter(post=post, brand=alpha).exists()
    assert list(
        PostBrandSignal.objects.filter(post=post, brand=beta).values_list(
            "post_type_id", flat=True
        )
    ) == ["business_finance"]
    assert list(
        PostBrandProductLabel.objects.filter(post=post, brand=beta).values_list(
            "product_label_id", flat=True
        )
    ) == ["testimonial"]


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_writer_database_failure_rolls_back_stage1_rows(monkeypatch):
    from django.db import DatabaseError

    from core.models import (
        Brand,
        Post,
        PostBrand,
        PostBrandClassificationState,
        PostBrandSignal,
        PostEnrichmentState,
    )
    from monitor import unsanctioned_flags
    from monitor.cycle import _publish_stage1_classification

    post = Post.objects.create(tweet_id="stage1-atomic", text="text")
    brand = Brand.objects.create(nickname="stage1-atomic-brand", display_name="Atomic")
    PostBrand.objects.create(post=post, brand=brand)
    PostEnrichmentState.objects.create(post=post, claim_run_id="atomic")
    monkeypatch.setattr(
        unsanctioned_flags,
        "persist_classifier_flags",
        lambda **kwargs: (_ for _ in ()).throw(DatabaseError("forced")),
    )
    with pytest.raises(DatabaseError):
        _publish_stage1_classification(
            post_id=post.pk,
            tweet={"text": "text", "context": []},
            model="flash",
            run_id="atomic",
            result={
                "valid": True,
                "unsanctioned_flags": [],
                "by_brand": {
                    "stage1-atomic-brand": {
                        "outcome": "classified",
                        "post_types": ["other"],
                        "product_labels": [],
                        "sentiment": "neutral",
                        "china_nationalism": None,
                        "us_nationalism": None,
                    }
                },
            },
        )
    assert not PostBrandClassificationState.objects.filter(post=post).exists()
    assert not PostBrandSignal.objects.filter(post=post).exists()


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_writer_rejects_forged_valid_and_stale_claim():
    from core.models import (
        Brand,
        Post,
        PostBrand,
        PostBrandClassificationState,
        PostEnrichmentState,
    )
    from monitor.cycle import _publish_stage1_classification

    post = Post.objects.create(tweet_id="stage1-forged", text="text")
    brand = Brand.objects.create(nickname="stage1-forged-brand", display_name="Forged")
    PostBrand.objects.create(post=post, brand=brand)
    PostEnrichmentState.objects.create(post=post, claim_run_id="owner-a")
    malformed = {
        "valid": True,
        "unsanctioned_flags": [],
        "by_brand": {
            "stage1-forged-brand": {
                "outcome": "classified",
                "post_types": ["buzz_releases"],
                "product_labels": [],
                "sentiment": "neutral",
                "china_nationalism": None,
                "us_nationalism": None,
            }
        },
    }
    assert (
        _publish_stage1_classification(
            post_id=post.pk,
            result=malformed,
            tweet={"text": "text", "context": []},
            model="flash",
            run_id="owner-a",
        )
        is None
    )
    valid = {
        "valid": True,
        "unsanctioned_flags": [],
        "by_brand": {
            "stage1-forged-brand": {
                "outcome": "context_missing",
                "post_types": [],
                "product_labels": [],
                "sentiment": None,
                "china_nationalism": None,
                "us_nationalism": None,
            }
        },
    }
    assert (
        _publish_stage1_classification(
            post_id=post.pk,
            result=valid,
            tweet={"text": "text", "context": []},
            model="flash",
            run_id="owner-b",
        )
        is None
    )
    assert not PostBrandClassificationState.objects.filter(post=post).exists()


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_bulk_reader_current_precedence_nulls_and_historical_conflicts(
    django_assert_num_queries,
):
    from core.classification_contract import CONTRACT_VERSION, TAXONOMY_VERSION
    from core.classification_readers import read_brand_scalars_many
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

    for key in ("positive", "negative", "neutral"):
        SentimentKey.objects.get_or_create(key=key)
    for key in ("none", "anti"):
        NationalismKey.objects.get_or_create(key=key)
    PostTypeKey.objects.get_or_create(key="other")
    DiscourseKey.objects.get_or_create(key="")
    brand = Brand.objects.create(nickname="stage1-reader", display_name="Reader")
    current_post = Post.objects.create(tweet_id="stage1-reader-current", text="x")
    legacy_post = Post.objects.create(tweet_id="stage1-reader-legacy", text="x")
    PostBrandClassificationState.objects.create(
        post=current_post,
        brand=brand,
        contract_version=CONTRACT_VERSION,
        taxonomy_version=TAXONOMY_VERSION,
        prompt_version="p",
        model="m",
        source_language="en",
        input_context_fingerprint="0" * 64,
        outcome="context_missing",
        sentiment=None,
        china_nationalism=None,
        us_nationalism=None,
    )
    PostBrandSignal.objects.create(
        post=legacy_post, brand=brand, post_type_id="other", sentiment_id="positive"
    )
    PostBrandDiscourse.objects.create(
        post=legacy_post,
        brand=brand,
        discourse_id="",
        act_id=0,
        china_nationalism_id="none",
        us_nationalism_id=None,
    )
    PostBrandDiscourse.objects.create(
        post=legacy_post,
        brand=brand,
        discourse_id="",
        act_id=1,
        china_nationalism_id="anti",
        us_nationalism_id=None,
    )
    pairs = [(current_post.pk, brand.pk), (legacy_post.pk, brand.pk)]
    with django_assert_num_queries(3):
        result = read_brand_scalars_many(pairs)
    assert result[(current_post.pk, brand.pk)].source == "current"
    assert result[(current_post.pk, brand.pk)].china_nationalism is None
    assert result[(legacy_post.pk, brand.pk)].sentiment == "positive"
    assert result[(legacy_post.pk, brand.pk)].china_nationalism is None
    assert "china_nationalism" in result[(legacy_post.pk, brand.pk)].conflicts


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_context_missing_publishes_state_without_edges_or_discourse():
    from core.classification_contract import (
        CONTRACT_VERSION,
        PROMPT_VERSION,
        TAXONOMY_VERSION,
    )
    from core.models import (
        Brand,
        Post,
        PostBrand,
        PostBrandClassificationState,
        PostBrandDiscourse,
        PostBrandProductLabel,
        PostBrandSignal,
        PostEnrichmentState,
    )
    from monitor.cycle import _publish_stage1_classification
    from x_monitor.config import Config

    post = Post.objects.create(
        tweet_id="stage1-context-missing",
        text="What about this?",
        lang_detected="en",
    )
    brand = Brand.objects.create(
        nickname="stage1-context-brand",
        display_name="Context",
    )
    PostBrand.objects.create(post=post, brand=brand)
    PostEnrichmentState.objects.create(
        post=post,
        claim_run_id="context-run",
        classification_attempts=1,
    )
    result = {
        "valid": True,
        "unsanctioned_flags": [],
        "by_brand": {
            brand.pk: {
                "outcome": "context_missing",
                "post_types": [],
                "product_labels": [],
                "sentiment": None,
                "china_nationalism": None,
                "us_nationalism": None,
            }
        },
    }

    published = _publish_stage1_classification(
        post_id=post.pk,
        result=result,
        tweet={
            "text": post.text,
            "context": [{"provenance": "stored_quote", "text": "insufficient context"}],
        },
        model="deepseek-v4-flash",
        run_id="context-run",
        cfg=Config(enabled_models=["deepseek"], daily_ceiling=100).harvest.enrichment,
    )

    assert published.outcome == "cleared"
    state = PostBrandClassificationState.objects.get(post=post, brand=brand)
    assert state.contract_version == CONTRACT_VERSION
    assert state.taxonomy_version == TAXONOMY_VERSION
    assert state.prompt_version == PROMPT_VERSION
    assert state.model == "deepseek-v4-flash"
    assert state.source_language == "en"
    assert len(state.input_context_fingerprint) == 64
    assert "insufficient" not in state.input_context_fingerprint
    assert state.outcome == "context_missing"
    assert state.sentiment_id is None
    assert state.china_nationalism_id is None
    assert state.us_nationalism_id is None
    assert not PostBrandSignal.objects.filter(post=post).exists()
    assert not PostBrandProductLabel.objects.filter(post=post).exists()
    assert not PostBrandDiscourse.objects.filter(post=post).exists()
    enrichment = PostEnrichmentState.objects.get(post=post)
    assert enrichment.classification_status == PostEnrichmentState.Status.SUCCEEDED
    assert enrichment.classification_attempts == 1


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_missing_one_of_two_attributed_brands_publishes_nothing_partial():
    from core.models import (
        Brand,
        Post,
        PostBrand,
        PostBrandClassificationState,
        PostBrandSignal,
        PostEnrichmentState,
        PostTypeKey,
        SentimentKey,
    )
    from monitor.cycle import _publish_stage1_classification

    PostTypeKey.objects.get_or_create(key="other")
    SentimentKey.objects.get_or_create(key="neutral")
    post = Post.objects.create(tweet_id="stage1-two-brands", text="text")
    alpha = Brand.objects.create(nickname="stage1-two-alpha", display_name="Alpha")
    beta = Brand.objects.create(nickname="stage1-two-beta", display_name="Beta")
    PostBrand.objects.bulk_create(
        [
            PostBrand(post=post, brand=alpha),
            PostBrand(post=post, brand=beta),
        ]
    )
    PostEnrichmentState.objects.create(post=post, claim_run_id="two-brands")
    complete = {
        "valid": True,
        "unsanctioned_flags": [],
        "by_brand": {
            alpha.pk: {
                "outcome": "classified",
                "post_types": ["other"],
                "product_labels": [],
                "sentiment": "neutral",
                "china_nationalism": None,
                "us_nationalism": None,
            },
            beta.pk: {
                "outcome": "classified",
                "post_types": ["other"],
                "product_labels": [],
                "sentiment": "neutral",
                "china_nationalism": None,
                "us_nationalism": None,
            },
        },
    }
    assert (
        _publish_stage1_classification(
            post_id=post.pk,
            result=complete,
            tweet={"text": post.text, "context": []},
            model="model-a",
            run_id="two-brands",
        )
        is not None
    )

    incomplete = {
        "valid": True,
        "unsanctioned_flags": [],
        "by_brand": {alpha.pk: complete["by_brand"][alpha.pk]},
    }
    assert (
        _publish_stage1_classification(
            post_id=post.pk,
            result=incomplete,
            tweet={"text": "changed", "context": []},
            model="model-b",
            run_id="two-brands",
        )
        is None
    )

    assert set(
        PostBrandClassificationState.objects.filter(post=post).values_list(
            "brand_id", "model"
        )
    ) == {(alpha.pk, "model-a"), (beta.pk, "model-a")}
    assert set(
        PostBrandSignal.objects.filter(post=post).values_list(
            "brand_id", "post_type_id"
        )
    ) == {(alpha.pk, "other"), (beta.pk, "other")}


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_malformed_brand_value_finalizes_and_does_not_block_another_post(monkeypatch):
    from core.models import (
        Brand,
        Post,
        PostBrand,
        PostBrandClassificationState,
        PostEnrichmentState,
        PostTypeKey,
        SentimentKey,
    )
    from monitor.cycle import CycleRunner
    from x_monitor import attribution, reattribute, translator
    from x_monitor.config import Config

    PostTypeKey.objects.get_or_create(key="other")
    SentimentKey.objects.get_or_create(key="neutral")
    brand = Brand.objects.create(
        nickname="stage1-isolation-brand",
        display_name="Isolation",
    )
    failed_post = Post.objects.create(tweet_id="stage1-isolation-failed", text="failed")
    good_post = Post.objects.create(tweet_id="stage1-isolation-good", text="good")
    for post in (failed_post, good_post):
        PostBrand.objects.create(post=post, brand=brand)
        PostEnrichmentState.objects.create(post=post)

    client = object()
    monkeypatch.setattr(
        reattribute, "build_translator_client_from_env", lambda cfg: client
    )
    monkeypatch.setattr(
        reattribute, "build_anthropic_client_from_env", lambda cfg: client
    )
    monkeypatch.setattr(
        translator,
        "translate_batch_pragmatics",
        lambda tweets, locales, client, **kwargs: [
            {
                "tweet_id": tweet["tweet_id"],
                "text_en": tweet["text"],
                "text_zh_cn": "翻译",
                "en_equivalent": "Commentary",
                "cn_equivalent": "评论",
                "lang_detected": "en",
            }
            for tweet in tweets
        ],
    )

    def classify(tweets, brands, client, **kwargs):
        output = []
        for tweet in tweets:
            if tweet["tweet_id"] == failed_post.pk:
                output.append(
                    {
                        "by_brand": {brand.pk: "malformed"},
                        "unsanctioned_flags": [],
                        "valid": True,
                    }
                )
                continue
            output.append(
                {
                    "by_brand": {
                        brand.pk: {
                            "outcome": "classified",
                            "post_types": ["other"],
                            "product_labels": [],
                            "sentiment": "neutral",
                            "china_nationalism": None,
                            "us_nationalism": None,
                        }
                    },
                    "unsanctioned_flags": [],
                    "valid": True,
                }
            )
        return output

    monkeypatch.setattr(attribution, "classify_batch_pragmatics_full", classify)
    CycleRunner(
        cfg=Config(enabled_models=["deepseek"], daily_ceiling=100)
    )._run_post_fetch([], run_id="stage1-isolation")

    failed_state = PostEnrichmentState.objects.get(post=failed_post)
    good_state = PostEnrichmentState.objects.get(post=good_post)
    assert failed_state.classification_status == PostEnrichmentState.Status.PENDING
    assert good_state.classification_status == PostEnrichmentState.Status.SUCCEEDED
    assert not PostBrandClassificationState.objects.filter(post=failed_post).exists()
    assert PostBrandClassificationState.objects.filter(post=good_post).exists()


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_translator_exception_does_not_block_stage1_classification(monkeypatch):
    from core.models import (
        Brand,
        Post,
        PostBrand,
        PostBrandClassificationState,
        PostEnrichmentState,
        PostTypeKey,
        SentimentKey,
    )
    from monitor.cycle import CycleRunner
    from x_monitor import attribution, reattribute, translator
    from x_monitor.config import Config

    PostTypeKey.objects.get_or_create(key="other")
    SentimentKey.objects.get_or_create(key="neutral")
    brand = Brand.objects.create(
        nickname="stage1-translator-brand",
        display_name="Translator",
    )
    post = Post.objects.create(
        tweet_id="stage1-translator-failed",
        text="classify despite translation failure",
    )
    PostBrand.objects.create(post=post, brand=brand)
    PostEnrichmentState.objects.create(post=post)
    client = object()
    monkeypatch.setattr(
        reattribute, "build_translator_client_from_env", lambda cfg: client
    )
    monkeypatch.setattr(
        reattribute, "build_anthropic_client_from_env", lambda cfg: client
    )

    def fail_translation(*args, **kwargs):
        raise RuntimeError("synthetic translator failure")

    monkeypatch.setattr(translator, "translate_batch_pragmatics", fail_translation)
    monkeypatch.setattr(
        attribution,
        "classify_batch_pragmatics_full",
        lambda tweets, brands, client, **kwargs: [
            {
                "by_brand": {
                    brand.pk: {
                        "outcome": "classified",
                        "post_types": ["other"],
                        "product_labels": [],
                        "sentiment": "neutral",
                        "china_nationalism": None,
                        "us_nationalism": None,
                    }
                },
                "unsanctioned_flags": [],
                "valid": True,
            }
        ],
    )

    CycleRunner(
        cfg=Config(enabled_models=["deepseek"], daily_ceiling=100)
    )._run_post_fetch([], run_id="stage1-translator-failed")

    enrichment = PostEnrichmentState.objects.get(post=post)
    assert enrichment.translation_status == PostEnrichmentState.Status.PENDING
    assert enrichment.classification_status == PostEnrichmentState.Status.SUCCEEDED
    assert PostBrandClassificationState.objects.filter(post=post).exists()


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("bad_flags", ["not-an-array", [object()]])
def test_malformed_flags_roll_back_all_stage1_publication(bad_flags):
    from core.models import (
        Brand,
        Post,
        PostBrand,
        PostBrandClassificationState,
        PostBrandProductLabel,
        PostBrandSignal,
        PostEnrichmentState,
        PostTypeKey,
        SentimentKey,
    )
    from monitor.cycle import _publish_stage1_classification

    PostTypeKey.objects.get_or_create(key="other")
    SentimentKey.objects.get_or_create(key="neutral")
    post = Post.objects.create(tweet_id="stage1-bad-flags", text="text")
    brand = Brand.objects.create(
        nickname="stage1-bad-flags-brand",
        display_name="Bad flags",
    )
    PostBrand.objects.create(post=post, brand=brand)
    PostEnrichmentState.objects.create(post=post, claim_run_id="bad-flags")
    result = {
        "valid": True,
        "unsanctioned_flags": bad_flags,
        "by_brand": {
            brand.pk: {
                "outcome": "classified",
                "post_types": ["other"],
                "product_labels": [],
                "sentiment": "neutral",
                "china_nationalism": None,
                "us_nationalism": None,
            }
        },
    }

    with pytest.raises(ValueError, match="classifier_flags_invalid"):
        _publish_stage1_classification(
            post_id=post.pk,
            result=result,
            tweet={"text": post.text, "context": []},
            model="deepseek-v4-flash",
            run_id="bad-flags",
        )

    assert not PostBrandClassificationState.objects.filter(post=post).exists()
    assert not PostBrandSignal.objects.filter(post=post).exists()
    assert not PostBrandProductLabel.objects.filter(post=post).exists()
