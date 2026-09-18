"""Focused U18A current-write persistence coverage."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest


class _SelectedV4Transport:
    """A provider-free selected route; exactly two semantic role responses."""

    request_profile = "deepseek_0731"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def messages_create(self, **kwargs):
        payload = json.loads(kwargs["messages"][0]["content"])
        role = "content" if "CONTENT ROLE:" in kwargs["system"] else "brand_interpretation"
        self.calls.append(role)
        decisions = {}
        for packet in payload["cases"].values():
            for slot in packet["brand_decision_slots"]:
                if role == "content":
                    decisions[slot] = (
                        {
                            "outcome": "classified",
                            "post_types": ["results_analysis"],
                            "audience_topics": ["cost_performance"],
                        }
                        if slot == "D01"
                        else {
                            "outcome": "classified",
                            "post_types": ["news_reporting"],
                            "audience_topics": ["agents_tools"],
                        }
                    )
                else:
                    decisions[slot] = (
                        {
                            "product_labels": ["testimonial"],
                            "sentiment": "positive",
                            "geopolitical_modes": ["nationalism"],
                            "china_national_stance": "pro",
                            "us_national_stance": "none",
                        }
                        if slot == "D01"
                        else {
                            "product_labels": ["none"],
                            "sentiment": "neutral",
                            "geopolitical_modes": ["framework"],
                            "china_national_stance": "none",
                            "us_national_stance": "none",
                        }
                    )
        response = {"decisions": decisions}
        if role == "content":
            response.update(
                post_promotions={slot: ["general"] for slot in payload["cases"]},
                promoted_subjects={
                    slot: [
                        {
                            "name": "Example Harness",
                            "handle": "ExampleHarness",
                            "domain": "example.ai",
                            "account_handle": "example_promoter",
                            "evidence": "Try Example Harness today #AI",
                        }
                    ]
                    for slot in payload["cases"]
                },
            )
        return response


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_v4_publisher_persists_isolated_axes_subject_evidence_and_never_touches_legacy_flags():
    from django.core.management import call_command

    from core.models import (
        Account,
        Brand,
        BrandDiscoveryCandidate,
        Post,
        PostBrand,
        PostBrandAudienceTopic,
        PostBrandClassificationState,
        PostBrandGeopoliticalMode,
        PostBrandProductLabel,
        PostBrandSignal,
        PostEnrichmentState,
        PostUntrackedBrandPromotion,
        PostUnsanctionedFlag,
        UntrackedBrandPromotionEvidence,
    )
    from monitor.cycle import _parse_published_classifications, _publish_stage1_classification
    from core.targeted_extraction import _organization_candidate
    from x_monitor.attribution import BrandRow, _tracked_brand_catalog, classify_batch_pragmatics_full

    # Transactional migration tests flush reference rows after restoring the
    # latest schema. Seed this test's required catalog explicitly so it stays
    # deterministic in both focused and combined-suite execution.
    call_command("seed_i18n_labels", verbosity=0)

    author = Account.objects.create(author_id="v4-author", handle="example_promoter")
    post = Post.objects.create(
        tweet_id="u18a-v4-persistence", author=author,
        text="Try Example Harness today #AI. Brand A is faster.", lang_detected="en",
    )
    brands = [
        Brand.objects.create(nickname="v4-a", display_name="Brand A"),
        Brand.objects.create(nickname="v4-b", display_name="Brand B"),
    ]
    for brand in brands:
        PostBrand.objects.create(post=post, brand=brand)
    PostEnrichmentState.objects.create(post=post, claim_run_id="u18a-v4-run")
    # Existing legacy semantics remain historical, even when a v4 result is
    # explicitly an Untracked Brand Promotion.
    PostUnsanctionedFlag.objects.create(
        post=post, flags='["marketing_spam"]', flag_set=["marketing_spam"], evidence=None,
    )
    # A later targeted extraction has the same name+handle identity. The
    # promotion writer must reuse it rather than opening a parallel candidate.
    existing_candidate, _ = _organization_candidate(
        post=post, name="Example Harness", handle="ExampleHarness", confidence=None,
    )

    tweet = {
        "tweet_id": post.pk,
        "text": post.text,
        "brand_ids": [brand.pk for brand in brands],
        "context": [],
        "source_language": "en",
        "affiliations": [],
        "tracked_brand_catalog": [
            {
                "brand_id": "v4-a",
                "aliases": ["Brand A"],
                "handles": ["v4_a_official"],
                "domains": ["brand-a.ai"],
                "products": ["Tracked Product"],
                "keywords": ["Brand A Model"],
                "hashtags": ["#BrandA"],
                "accounts": [{"handle": "v4_a_official", "role": "official"}],
            },
            {
                "brand_id": "v4-b",
                "aliases": ["Brand B"],
                "handles": [],
                "domains": [],
                "products": [],
                "keywords": [],
                "hashtags": [],
                "accounts": [],
            },
        ],
    }
    registry = [
        BrandRow(
            brand_id=brand.pk,
            display_name=brand.display_name,
            accent_color="#111111",
            is_sentinel=False,
        )
        for brand in brands
    ]
    catalog = _tracked_brand_catalog(registry, [tweet])
    tweet["_classification_catalog_revision"] = catalog["revision"]
    transport = _SelectedV4Transport()
    result = classify_batch_pragmatics_full([tweet], registry, transport, model="u18a-v4-model")[0]

    assert result["valid"] is True
    assert sorted(transport.calls) == ["brand_interpretation", "content"]
    parsed = _parse_published_classifications(result["by_brand"], set(tweet["brand_ids"]))
    assert parsed == result["by_brand"], repr(result["by_brand"])
    outcome = _publish_stage1_classification(
        post_id=post.pk, result=result, tweet=tweet, model="u18a-v4-model", run_id="u18a-v4-run",
    )
    assert outcome.outcome == "persisted"

    states = list(PostBrandClassificationState.objects.filter(post=post).order_by("brand_id"))
    assert len(states) == 2
    state_by_brand = {state.brand_id: state for state in states}
    assert state_by_brand["v4-a"].china_national_stance_id == state_by_brand["v4-a"].china_nationalism_id == "pro"
    assert state_by_brand["v4-b"].china_national_stance_id == state_by_brand["v4-b"].china_nationalism_id == "none"
    assert all(state.us_national_stance_id == state.us_nationalism_id == "none" for state in states)
    assert set(PostBrandSignal.objects.filter(post=post).values_list("brand_id", "post_type_id")) == {
        ("v4-a", "results_analysis"), ("v4-b", "news_reporting"),
    }
    assert set(PostBrandProductLabel.objects.filter(post=post).values_list("brand_id", "product_label_id")) == {
        ("v4-a", "testimonial"),
    }
    assert set(PostBrandAudienceTopic.objects.filter(post=post).values_list("brand_id", "concept__key")) == {
        ("v4-a", "cost_performance"), ("v4-b", "agents_tools"),
    }
    assert set(PostBrandGeopoliticalMode.objects.filter(post=post).values_list("brand_id", "geopolitical_mode_id")) == {
        ("v4-a", "nationalism"), ("v4-b", "framework"),
    }
    assert PostUnsanctionedFlag.objects.get(post=post).flag_set == ["marketing_spam"]

    promotion = PostUntrackedBrandPromotion.objects.get(post=post)
    assert promotion.promotion_keys == ["general"]
    assert promotion.provider_role == "content"
    assert promotion.prompt_version == "stage1-content-0731-v4"
    evidence = UntrackedBrandPromotionEvidence.objects.get(promotion=promotion)
    assert evidence.exact_matched_account_id == author.pk
    assert evidence.handles == ["@example_promoter", "@exampleharness"]
    assert evidence.domains == ["example.ai"]
    assert evidence.hashtags == ["#AI"]
    assert evidence.recurrence_count == 1
    candidate = BrandDiscoveryCandidate.objects.get(pk=evidence.brand_discovery_candidate_id)
    assert candidate.pk == existing_candidate.pk
    assert candidate.source_post_id == post.pk

    # Same validated result is a retry, not a new promotion occurrence or a
    # third semantic model call.
    assert _publish_stage1_classification(
        post_id=post.pk, result=deepcopy(result), tweet=tweet, model="u18a-v4-model", run_id="u18a-v4-run",
    ).outcome == "persisted"
    assert BrandDiscoveryCandidate.objects.count() == 1
    assert UntrackedBrandPromotionEvidence.objects.count() == 1
    assert UntrackedBrandPromotionEvidence.objects.get().recurrence_count == 1

    # Invalid promotion subject output fails inside the publisher transaction;
    # last known v4 projection remains intact.
    malformed = deepcopy(result)
    malformed["promoted_subjects"] = []
    with pytest.raises(ValueError, match="subject_missing"):
        _publish_stage1_classification(
            post_id=post.pk, result=malformed, tweet=tweet, model="u18a-v4-model", run_id="u18a-v4-run",
        )
    assert PostUntrackedBrandPromotion.objects.get(post=post).promotion_keys == ["general"]
    assert PostBrandAudienceTopic.objects.filter(post=post).count() == 2

    # A promoted subject cannot silently duplicate a tracked subject.  Exact
    # product aliases and account handles are both authoritative catalog
    # evidence; each failed replay leaves the current projection intact.
    for subject in (
        {
            "name": "Tracked Product", "handle": None, "domain": None,
            "account_handle": None, "evidence": "Try Tracked Product today",
        },
        {
            "name": "Different Name", "handle": "v4_a_official", "domain": None,
            "account_handle": None, "evidence": "Try @v4_a_official today",
        },
    ):
        tracked_subject = deepcopy(result)
        tracked_subject["promoted_subjects"] = [subject]
        with pytest.raises(ValueError, match="subject_is_tracked"):
            _publish_stage1_classification(
                post_id=post.pk, result=tracked_subject, tweet=tweet,
                model="u18a-v4-model", run_id="u18a-v4-run",
            )
    assert BrandDiscoveryCandidate.objects.count() == 1
    assert UntrackedBrandPromotionEvidence.objects.count() == 1


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_promoted_subject_renames_reuse_exact_account_and_refresh_recurrence():
    from django.utils import timezone

    from core.models import (
        Account,
        BrandDiscoveryCandidate,
        Post,
        PostUntrackedBrandPromotion,
        UntrackedBrandPromotionEvidence,
    )
    from monitor.classification_persistence import _write_promoted_subject

    account = Account.objects.create(author_id="renamed-promoter", handle="same_handle")
    posts = [
        Post.objects.create(
            tweet_id=f"renamed-promotion-{index}",
            author=account,
            text=f"Try {name} at example.ai",
        )
        for index, name in enumerate(("Old Name", "New Name"), start=1)
    ]
    promotions = [
        PostUntrackedBrandPromotion.objects.create(
            post=post,
            promotion_keys=["general"],
            contract_version="classification/v4",
            taxonomy_version="taxonomy/v4",
            prompt_version="test",
            model="test",
            provider_role="content",
        )
        for post in posts
    ]
    observed_at = timezone.now()
    for promotion, post, name in zip(
        promotions, posts, ("Old Name", "New Name"), strict=True
    ):
        _write_promoted_subject(
            promotion=promotion,
            post=post,
            subject={
                "name": name,
                "handle": "same_handle",
                "account_handle": "same_handle",
                "domain": "example.ai",
                "evidence": f"Try {name} at example.ai",
            },
            observed_at=observed_at,
        )

    assert BrandDiscoveryCandidate.objects.count() == 1
    evidence = list(UntrackedBrandPromotionEvidence.objects.order_by("source_post_id"))
    assert len(evidence) == 2
    assert {row.brand_discovery_candidate_id for row in evidence} == {
        BrandDiscoveryCandidate.objects.get().pk
    }
    assert [row.recurrence_count for row in evidence] == [2, 2]
