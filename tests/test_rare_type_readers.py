from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.intelligence_readers import model_release_document, rare_type_post_document
from core.models import (
    Account,
    Brand,
    BrandDiscoveryCandidate,
    ModelRelease,
    ModelReleaseEvidence,
    Post,
    PostBrandProduct,
    Product,
    ProductVerificationProposal,
    RareTypeCategoryAssignment,
)

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
NOW = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
CONTRACT = (
    Path(__file__).resolve().parents[1]
    / "tests/fixtures/rare_type_intelligence_read_contract_v1.json"
)


def test_versioned_rare_type_read_contract_pins_reader_and_command_shapes():
    contract = json.loads(CONTRACT.read_text())

    assert contract["schema_version"] == "rare-type-intelligence-read-contract-v1"
    assert set(contract["documents"]) == {
        "model_release_document",
        "rare_type_post_document",
        "rare_type_status",
        "rare_type_replay",
    }
    assert contract["documents"]["rare_type_status"]["security"].startswith(
        "No raw post text"
    )


def test_release_reader_counts_canonical_record_evidence_and_posts_separately():
    brand = Brand.objects.create(nickname="minimax", display_name="MiniMax")
    posts = [
        Post.objects.create(tweet_id="release-source-1", text="MiniMax M3 released"),
        Post.objects.create(tweet_id="release-source-2", text="More M3 details"),
    ]
    release = ModelRelease.objects.create(
        brand=brand,
        observed_model_name="M3",
        version="3.0",
        release_channel="stable",
        release_value="2026-09-24",
        release_precision="day",
        release_identity="release-reader-m3",
        first_seen_at=NOW,
        last_seen_at=NOW,
        extraction_version="release-extract-v1",
    )
    for index, post in enumerate(posts):
        ModelReleaseEvidence.objects.create(
            release=release,
            source_post=post,
            observed_at=NOW,
            observed_claim={"model_name": "M3", "source": index},
            evidence_hash=f"evidence-{index}",
            extraction_version="release-extract-v1",
        )

    document = model_release_document(release.pk)

    assert document["counts"] == {
        "canonical_records": 1,
        "evidence": 2,
        "posts": 2,
    }
    assert [row["source_post_id"] for row in document["evidence"]] == [
        "release-source-1",
        "release-source-2",
    ]


def test_post_reader_keeps_brand_candidate_categories_and_product_evidence_distinct():
    brand = Brand.objects.create(nickname="minimax", display_name="MiniMax")
    post = Post.objects.create(
        tweet_id="rare-reader-post",
        text="MiniMax released M3 and an image model",
        source_query_id="RARE_EXTRA",
    )
    candidate = BrandDiscoveryCandidate.objects.create(
        observed_name="Unknown Lab",
        aliases=[],
        candidate_handles=["unknown_lab"],
        source_post=post,
        source_identities=[],
        candidate_identity="unknown-lab-reader",
        first_observed_at=NOW,
        last_observed_at=NOW,
    )
    for category in ("llm-model", "other-ai-model"):
        RareTypeCategoryAssignment.objects.create(
            post=post,
            brand=brand,
            category=category,
            source_evidence={"span": category},
            classification_version="rare-category-v1",
        )
    RareTypeCategoryAssignment.objects.create(
        post=post,
        brand_discovery_candidate=candidate,
        category="agent-harness",
        source_evidence={"span": "harness"},
        classification_version="rare-category-v1",
    )
    product = Product.objects.create(
        brand=brand,
        display_name="MiniMax M3",
        repo_id="MiniMaxAI/M3",
        type="llm-model",
    )
    PostBrandProduct.objects.create(
        post=post,
        brand=brand,
        product=product,
        observed_name="M3",
        source_evidence={"span": "M3"},
        verification_policy_version="x-hf-product-v1",
    )
    account = Account.objects.create(author_id="reader-author", handle="minimax")
    ProductVerificationProposal.objects.create(
        proposal_key="reader-proposal",
        source_post=post,
        proposed_candidate=candidate,
        account=account,
        account_handle_snapshot="minimax",
        observed_name="Unknown Harness",
        candidate_repo_id="UnknownLab/Harness",
        hf_outcome="missing",
        policy_version="x-hf-product-v1",
        rule_trace=["publisher_needs_review"],
    )

    document = rare_type_post_document(post.pk)

    assert document["exists"] is True
    assert document["source_query_id"] == "RARE_EXTRA"
    assert {
        (row["brand_id"], row["candidate_id"], row["category"])
        for row in document["categories"]
    } == {
        ("minimax", None, "llm-model"),
        ("minimax", None, "other-ai-model"),
        (None, candidate.pk, "agent-harness"),
    }
    assert document["products"] == [
        {
            "brand_id": "minimax",
            "product_id": product.pk,
            "product_key": str(product.product_key),
            "repo_id": "MiniMaxAI/M3",
            "name": "M3",
            "type": "llm-model",
            "policy_version": "x-hf-product-v1",
            "source_evidence": {"span": "M3"},
        }
    ]
    assert document["product_proposals"][0]["review_status"] == "pending"
    assert document["product_proposals"][0]["candidate_id"] == candidate.pk
    assert document["product_proposals"][0]["rule_trace"] == ["publisher_needs_review"]
