from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction

from core.models import (
    Account,
    Brand,
    BrandDiscoveryCandidate,
    ModelRelease,
    ModelReleaseEvidence,
    Post,
    PostBrand,
    RareTypeCategoryAssignment,
)
from core.targeted_extraction import run_targeted_extractions
from x_monitor.config import TargetedExtractionConfig

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def _post(
    tweet_id: str,
    text: str,
    *,
    brand: str | None = "minimax",
    source_urls: tuple[str, ...] = (),
) -> Post:
    account = Account.objects.create(author_id=f"author-{tweet_id}")
    post = Post.objects.create(
        tweet_id=tweet_id,
        author=account,
        text=text,
        entities={"urls": [{"expanded_url": url} for url in source_urls]},
    )
    if brand:
        row, _ = Brand.objects.get_or_create(nickname=brand, defaults={"display_name": brand})
        PostBrand.objects.create(post=post, brand=row)
    return post


def _config() -> TargetedExtractionConfig:
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


def test_two_source_posts_share_release_and_keep_two_evidence_rows():
    first = _post("release-1", "MiniMax announces M2-preview")
    second = _post("release-2", "MiniMax confirms M2-preview")
    provider = lambda *_args: {"records": [_record()]}
    for post in (first, second):
        result = run_targeted_extractions(
            post=post,
            post_types={"releases_updates"},
            config=_config(),
            calls={"model_release_extraction": provider},
            max_calls=1,
            eligible_rare_types={"model_releases"},
        )
        assert result.failed_roles == ()
    assert ModelRelease.objects.count() == 1
    assert ModelReleaseEvidence.objects.count() == 2
    assert RareTypeCategoryAssignment.objects.count() == 4


def test_unknown_publisher_stays_candidate_owned():
    post = _post("unknown-release", "Unknown AI announces A1", brand=None)
    result = run_targeted_extractions(
        post=post,
        post_types={"releases_updates"},
        config=_config(),
        calls={"model_release_extraction": lambda *_args: {"records": [_record(
            brand_id=None, organization_name="Unknown AI", model_name="A1"
        )]}},
        max_calls=1,
        eligible_rare_types={"model_releases"},
    )
    assert result.organization_candidates_written == 1
    release = ModelRelease.objects.get()
    assert release.brand_id is None
    assert release.brand_discovery_candidate_id == BrandDiscoveryCandidate.objects.get().pk
    assert set(
        RareTypeCategoryAssignment.objects.values_list(
            "brand_discovery_candidate_id", flat=True
        )
    ) == {release.brand_discovery_candidate_id}


def test_owner_constraints_reject_missing_or_double_owner():
    post = _post("constraint", "source")
    candidate = BrandDiscoveryCandidate.objects.create(
        observed_name="Candidate", candidate_identity="c" * 64,
        first_observed_at=post.fetched_at, last_observed_at=post.fetched_at,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        RareTypeCategoryAssignment.objects.create(
            post=post, category="llm-model", classification_version="v1"
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        RareTypeCategoryAssignment.objects.create(
            post=post, brand_id="minimax", brand_discovery_candidate=candidate,
            category="llm-model", classification_version="v1",
        )


def test_release_identity_separates_owner_version_and_channel():
    post = _post("identity", "MiniMax and OpenAI announce previews")
    openai, _ = Brand.objects.get_or_create(nickname="openai")
    PostBrand.objects.create(post=post, brand=openai)
    records = [
        _record(),
        _record(version="M2-stable", release_channel="stable"),
        _record(brand_id="openai", organization_name="OpenAI"),
    ]
    result = run_targeted_extractions(
        post=post, post_types={"releases_updates"}, config=_config(),
        calls={"model_release_extraction": lambda *_args: {"records": records}},
        max_calls=1, eligible_rare_types={"model_releases"},
    )
    assert result.records_written == 3
    assert ModelRelease.objects.count() == 3
    assert set(
        RareTypeCategoryAssignment.objects.values_list("brand_id", flat=True)
    ) == {"minimax", "openai"}


def test_event_route_never_creates_model_release():
    post = _post("event-only", "MiniMax presents at AI Conf")
    run_targeted_extractions(
        post=post, post_types={"events"}, config=_config(),
        calls={"event_extraction": lambda *_args: {"records": []}}, max_calls=1,
    )
    assert not ModelRelease.objects.exists()


def test_ordinary_release_classification_without_jev_route_makes_no_release_call():
    post = _post("ordinary-release", "ordinary A/B/C release post")
    called = []
    result = run_targeted_extractions(
        post=post, post_types={"releases_updates"}, config=_config(),
        calls={"model_release_extraction": lambda *_args: called.append(True)},
        max_calls=1,
    )
    assert result.calls_made == 0
    assert called == []


def test_replay_preserves_review_and_evidence_is_idempotent():
    first = _post("review-1", "MiniMax announces M2-preview")
    second = _post("review-2", "MiniMax confirms M2-preview")
    provider = lambda *_args: {"records": [_record()]}
    run_targeted_extractions(
        post=first, post_types={"releases_updates"}, config=_config(),
        calls={"model_release_extraction": provider}, max_calls=1,
        eligible_rare_types={"model_releases"},
    )
    release = ModelRelease.objects.get()
    release.review_status = "confirmed"
    release.save(update_fields=["review_status", "updated_at"])
    run_targeted_extractions(
        post=second, post_types={"releases_updates"}, config=_config(),
        calls={"model_release_extraction": provider}, max_calls=1,
        eligible_rare_types={"model_releases"},
    )
    release.refresh_from_db()
    assert release.review_status == "confirmed"
    assert release.evidence.count() == 2


def test_malformed_release_rolls_back_all_role_writes():
    post = _post("rollback", "MiniMax releases models")
    result = run_targeted_extractions(
        post=post, post_types={"releases_updates"}, config=_config(),
        calls={"model_release_extraction": lambda *_args: {"records": [
            _record(), _record(model_name="bad", categories=["not-a-category"])
        ]}}, max_calls=1, eligible_rare_types={"model_releases"},
    )
    assert result.failed_roles == ("model_release_extraction",)
    assert not ModelRelease.objects.exists()
    assert not ModelReleaseEvidence.objects.exists()
    assert not RareTypeCategoryAssignment.objects.exists()


def test_category_only_record_does_not_fabricate_release():
    post = _post("category-only", "MiniMax discusses model work")
    result = run_targeted_extractions(
        post=post, post_types={"releases_updates"}, config=_config(),
        calls={"model_release_extraction": lambda *_args: {"records": [
            _record(model_name="", version="", categories=["llm-model"])
        ]}}, max_calls=1, eligible_rare_types={"model_releases"},
    )
    assert result.failed_roles == ()
    assert RareTypeCategoryAssignment.objects.get().category == "llm-model"
    assert not ModelRelease.objects.exists()


def test_unversioned_release_identity_uses_source_url():
    urls = ("https://example.com/a", "https://example.com/b")
    posts = [
        _post("url-a1", f"Announcement {urls[0]}", source_urls=(urls[0],)),
        _post("url-a2", f"Recap {urls[0]}", source_urls=(urls[0],)),
        _post("url-b", f"Announcement {urls[1]}", source_urls=(urls[1],)),
    ]
    for post, source_url in zip(posts, (urls[0], urls[0], urls[1]), strict=True):
        run_targeted_extractions(
            post=post, post_types={"releases_updates"}, config=_config(),
            calls={"model_release_extraction": lambda *_args, url=source_url: {
                "records": [_record(version="", source_url=url)]
            }}, max_calls=1, eligible_rare_types={"model_releases"},
        )
    assert ModelRelease.objects.count() == 2
    assert sorted(release.evidence.count() for release in ModelRelease.objects.all()) == [1, 2]
