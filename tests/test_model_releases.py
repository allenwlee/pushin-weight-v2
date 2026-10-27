"""Saved release reports use dossiers and preserve source evidence."""

from __future__ import annotations

import pytest

from core.collection_capture import read_document
from core.event_dossiers import read_current_evidence, read_dossier
from core.models import (
    Account,
    Brand,
    BrandDiscoveryCandidate,
    EventDossier,
    EventDossierClaim,
    Post,
    PostBrand,
    ProductVerificationProposal,
    RareTypeCategoryAssignment,
)
from core.targeted_extraction import run_targeted_extractions
from x_monitor.config import TargetedExtractionConfig

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def _post(tweet_id, text, *, brand="minimax", source_urls=()):
    account = Account.objects.create(author_id=f"author-{tweet_id}")
    post = Post.objects.create(
        tweet_id=tweet_id,
        author=account,
        text=text,
        entities={"urls": [{"expanded_url": url} for url in source_urls]},
    )
    if brand:
        row, _ = Brand.objects.get_or_create(
            nickname=brand, defaults={"display_name": brand}
        )
        PostBrand.objects.create(post=post, brand=row)
    return post


def _config():
    config = TargetedExtractionConfig()
    config.enabled = True
    return config


def _record(**overrides):
    return {
        "brand_id": "minimax",
        "organization_name": "MiniMax",
        "model_name": "MiniMax M2",
        "version": "M2-preview",
        "release_channel": "preview",
        "release_value": "2026-09-24",
        "release_precision": "day",
        "categories": ["llm-model", "other-ai-model"],
        **overrides,
    }


def _run(post, *records):
    return run_targeted_extractions(
        post=post,
        post_types={"releases_updates"},
        config=_config(),
        calls={"model_release_extraction": lambda *_args: {"records": list(records)}},
        max_calls=1,
    )


def _releases():
    return EventDossier.objects.filter(event_kind_reference__code="product_release")


def test_two_source_posts_share_pending_dossier_and_keep_source_claims():
    first = _post("release-1", "MiniMax announces M2-preview")
    second = _post("release-2", "MiniMax confirms M2-preview")
    assert _run(first, _record()).failed_roles == ()
    assert _run(second, _record()).failed_roles == ()
    dossier = _releases().get()
    claims = list(
        EventDossierClaim.objects.filter(event_dossier_source__event_dossier=dossier)
        .select_related("source_archive")
        .order_by("id")
    )
    assert len(claims) == 2
    assert {claim.release_maturity_reference.code for claim in claims} == {"preview"}
    assert {claim.event_dossier_source.post_id for claim in claims} == {
        first.pk,
        second.pk,
    }
    assert all(
        read_document(claim.source_archive)["schema"] == "product-release-intake-v1"
        for claim in claims
    )
    assert read_dossier(dossier.pk)["claims"] == []
    assert len(read_current_evidence(dossier.pk)["claims"]) == 2
    assert RareTypeCategoryAssignment.objects.count() == 4


def test_exact_repo_candidate_links_pending_proposal_to_dossier():
    post = _post("release-repo", "MiniMax announces MiniMaxAI/M2")
    assert _run(post, _record(candidate_repo_id="MiniMaxAI/M2")).failed_roles == ()
    proposal = ProductVerificationProposal.objects.get()
    assert proposal.source_post_id == post.pk
    assert proposal.source_dossier_id == _releases().get().pk
    assert proposal.hf_outcome == "pending"


def test_named_release_without_repo_remains_pending():
    post = _post("release-x-only", "MiniMax announces M2")
    assert _run(post, _record()).failed_roles == ()
    proposal = ProductVerificationProposal.objects.get()
    assert proposal.candidate_repo_id == ""
    assert proposal.hf_outcome == "deferred"
    assert proposal.review_status == "pending"
    assert _releases().get().current_review_id is None


def test_unknown_publisher_claim_retains_candidate_fk_without_product():
    post = _post("unknown-release", "Unknown AI announces A1", brand=None)
    result = _run(
        post, _record(brand_id=None, organization_name="Unknown AI", model_name="A1")
    )
    assert result.organization_candidates_written == 1
    claim = EventDossierClaim.objects.get()
    assert claim.reported_brand_id is None
    assert (
        claim.reported_brand_discovery_candidate_id
        == BrandDiscoveryCandidate.objects.get().pk
    )
    assert _releases().get().current_review_id is None


def test_identity_separates_owner_version_and_channel():
    post = _post("identity", "MiniMax and OpenAI announce previews")
    openai, _ = Brand.objects.get_or_create(nickname="openai")
    PostBrand.objects.create(post=post, brand=openai)
    result = _run(
        post,
        _record(),
        _record(version="M2-stable", release_channel="stable"),
        _record(brand_id="openai", organization_name="OpenAI"),
    )
    assert result.records_written == 3
    assert _releases().count() == 3
    assert set(
        RareTypeCategoryAssignment.objects.values_list("brand_id", flat=True)
    ) == {"minimax", "openai"}


def test_replay_is_idempotent_and_does_not_create_review():
    post = _post("replay", "MiniMax announces M2-preview")
    assert _run(post, _record()).failed_roles == ()
    assert _run(post, _record()).failed_roles == ()
    assert _releases().count() == 1
    assert EventDossierClaim.objects.count() == 1
    assert _releases().get().current_review_id is None


def test_invalid_second_record_rolls_back_all_role_writes():
    post = _post("rollback", "MiniMax releases models")
    result = _run(
        post, _record(), _record(model_name="bad", categories=["not-a-category"])
    )
    assert result.failed_roles == ("model_release_extraction",)
    assert not _releases().exists()
    assert not EventDossierClaim.objects.exists()
    assert not RareTypeCategoryAssignment.objects.exists()


def test_category_only_record_does_not_fabricate_release():
    post = _post("category-only", "MiniMax discusses model work")
    result = _run(post, _record(model_name="", version="", categories=["llm-model"]))
    assert result.failed_roles == ()
    assert RareTypeCategoryAssignment.objects.get().category == "llm-model"
    assert not _releases().exists()


def test_unversioned_identity_uses_source_url():
    urls = ("https://example.com/a", "https://example.com/b")
    posts = [
        _post("url-a1", f"Announcement {urls[0]}", source_urls=(urls[0],)),
        _post("url-a2", f"Recap {urls[0]}", source_urls=(urls[0],)),
        _post("url-b", f"Announcement {urls[1]}", source_urls=(urls[1],)),
    ]
    for post, source_url in zip(posts, (urls[0], urls[0], urls[1]), strict=True):
        assert _run(post, _record(version="", source_url=source_url)).failed_roles == ()
    assert _releases().count() == 2
    assert sorted(
        EventDossierClaim.objects.filter(
            event_dossier_source__event_dossier=dossier
        ).count()
        for dossier in _releases()
    ) == [1, 2]
