from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import (
    Account,
    Brand,
    BrandDiscoveryCandidateToken,
    BrandDiscoveryCandidateTokenEvidence,
    PersonBrandAffiliation,
    Post,
    PostBrandSignal,
    ProfileMovementCandidate,
    TargetedExtractionState,
)
from core.profile_snapshots import capture_post_profile_snapshot
from core.targeted_extraction import run_targeted_extractions
from x_monitor.config import TargetedExtractionConfig

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def _post(account, tweet_id, observed_at):
    post = Post.objects.create(tweet_id=tweet_id, author=account, text="carrier product post")
    Post.objects.filter(pk=post.pk).update(fetched_at=observed_at)
    post.refresh_from_db()
    return post


def _capture(post, **fields):
    present = list(fields)
    raw = {"author_id": post.author_id, "_author_present_fields": present}
    raw.update(fields)
    return capture_post_profile_snapshot(post=post, raw=raw)


def _config():
    config = TargetedExtractionConfig()
    config.enabled = True
    return config


def test_baseline_stable_empty_avatar_and_name_only_do_not_create_movement():
    account = Account.objects.create(author_id="no-movement")
    start = timezone.now()
    _capture(_post(account, "baseline", start), author_description="Researcher at OpenAI")
    _capture(_post(account, "stable", start + timedelta(minutes=1)), author_description="Researcher at OpenAI")
    _capture(_post(account, "empty", start + timedelta(minutes=2)), author_description="")
    _capture(_post(account, "avatar", start + timedelta(minutes=3)), author_profile_image_url="https://example.com/a.jpg")
    _capture(_post(account, "name", start + timedelta(minutes=4)), author_name="New Name")
    assert not ProfileMovementCandidate.objects.exists()


def test_a_b_a_creates_two_source_bound_candidates_without_relabeling_posts():
    Brand.objects.create(nickname="openai", display_name="OpenAI")
    Brand.objects.get_or_create(
        nickname="anthropic", defaults={"display_name": "Anthropic"}
    )
    account = Account.objects.create(author_id="a-b-a", handle="person")
    start = timezone.now()
    posts = [_post(account, f"carrier-{i}", start + timedelta(minutes=i)) for i in range(3)]
    for post, description in zip(
        posts,
        ("OpenAI researcher", "Anthropic researcher", "OpenAI researcher"),
        strict=True,
    ):
        _capture(post, author_description=description)
    rows = list(ProfileMovementCandidate.objects.order_by("observed_at"))
    assert [(row.prior_description, row.new_description) for row in rows] == [
        ("OpenAI researcher", "Anthropic researcher"),
        ("Anthropic researcher", "OpenAI researcher"),
    ]
    assert all(row.effective_date is None and row.effective_date_precision == "unknown" for row in rows)
    assert not PostBrandSignal.objects.filter(post__in=posts).exists()


def test_avatar_only_intervening_snapshot_does_not_hide_later_bio_change():
    Brand.objects.create(nickname="openai", display_name="OpenAI")
    Brand.objects.create(nickname="anthropic", display_name="Anthropic")
    account = Account.objects.create(author_id="avatar-between")
    start = timezone.now()
    _capture(_post(account, "bio-old", start), author_description="OpenAI researcher")
    _capture(
        _post(account, "bio-avatar", start + timedelta(minutes=1)),
        author_profile_image_url="https://example.com/new.jpg",
    )
    post = _post(account, "bio-new", start + timedelta(minutes=2))
    _capture(post, author_description="Anthropic researcher")
    movement = ProfileMovementCandidate.objects.get()
    assert movement.prior_description == "OpenAI researcher"
    assert movement.new_description == "Anthropic researcher"


def test_short_brand_alias_inside_unrelated_word_is_not_a_movement():
    Brand.objects.create(nickname="meta", display_name="Meta")
    account = Account.objects.create(author_id="substring")
    start = timezone.now()
    _capture(_post(account, "substring-1", start), author_description="I study metadata")
    _capture(
        _post(account, "substring-2", start + timedelta(minutes=1)),
        author_description="I study metamaterials",
    )
    assert not ProfileMovementCandidate.objects.exists()


def test_provider_failure_retries_and_exact_unknown_tokens_use_movement_evidence():
    account = Account.objects.create(author_id="unknown-destination", handle="person")
    start = timezone.now()
    _capture(_post(account, "unknown-before", start), author_description="Researcher at OpenAI")
    post = _post(account, "unknown-after", start + timedelta(minutes=1))
    _capture(post, author_description="Joined Moonshot AI @Kimi_Moonshot")
    failed = run_targeted_extractions(
        post=post, post_types=set(), config=_config(),
        calls={"profile_affiliation_extraction": lambda *_args: (_ for _ in ()).throw(RuntimeError("down"))},
        max_calls=1,
    )
    assert failed.failed_roles == ("profile_affiliation_extraction",)
    movement = ProfileMovementCandidate.objects.get()
    assert movement.status == "failed" and movement.attempts == 1

    response = {"records": [{
        "person_name": "Person", "person_handle": "person",
        "brand_id": None, "organization_name": "Moonshot AI",
        "organization_handle": "@Kimi_Moonshot", "affiliation_type": "employment",
        "status": "current", "start_date": "2026-09", "start_date_precision": "month",
        "end_date": None, "end_date_precision": "unknown", "confidence": 0.9,
    }]}
    retried = run_targeted_extractions(
        post=post, post_types=set(), config=_config(),
        calls={"profile_affiliation_extraction": lambda *_args: response}, max_calls=1,
    )
    assert retried.failed_roles == ()
    movement.refresh_from_db()
    assert movement.status == "succeeded" and movement.attempts == 2
    affiliation = PersonBrandAffiliation.objects.get()
    assert (affiliation.start_date, affiliation.start_date_precision) == ("2026-09", "month")
    assert set(BrandDiscoveryCandidateToken.objects.values_list("form", flat=True)) == {
        "Moonshot AI", "@Kimi_Moonshot"
    }
    assert set(
        BrandDiscoveryCandidateTokenEvidence.objects.values_list(
            "source_profile_movement_id", flat=True
        )
    ) == {movement.pk}

    later = _post(account, "unknown-later", start + timedelta(minutes=2))
    _capture(later, author_description="Now at Moonshot AI @Kimi_Moonshot")
    result = run_targeted_extractions(
        post=later, post_types=set(), config=_config(),
        calls={"profile_affiliation_extraction": lambda *_args: response}, max_calls=1,
    )
    movements = set(ProfileMovementCandidate.objects.values_list("pk", flat=True))
    assert BrandDiscoveryCandidateTokenEvidence.objects.count() == 4
    assert set(
        BrandDiscoveryCandidateTokenEvidence.objects.values_list(
            "source_profile_movement_id", flat=True
        )
    ) == movements
    assert all(
        token.last_observed_at == later.fetched_at
        for token in BrandDiscoveryCandidateToken.objects.all()
    )


@pytest.mark.parametrize(("value", "precision"), [("2026", "year"), ("2026-09", "month")])
def test_source_stated_effective_date_precision_is_not_promoted_to_observed_day(
    value, precision
):
    Brand.objects.get_or_create(
        nickname="anthropic", defaults={"display_name": "Anthropic"}
    )
    account = Account.objects.create(author_id=f"date-{precision}", handle=f"date{precision}")
    start = timezone.now()
    _capture(_post(account, f"date-old-{precision}", start), author_description="OpenAI researcher")
    post = _post(account, f"date-new-{precision}", start + timedelta(minutes=1))
    _capture(post, author_description="Joined Anthropic")
    response = {"records": [{
        "person_name": "Date Person", "person_handle": f"date{precision}",
        "brand_id": "anthropic", "organization_name": "Anthropic",
        "affiliation_type": "employment", "status": "current",
        "start_date": value, "start_date_precision": precision,
        "end_date": None, "end_date_precision": "unknown",
    }]}
    result = run_targeted_extractions(
        post=post, post_types=set(), config=_config(),
        calls={"profile_affiliation_extraction": lambda *_args: response}, max_calls=1,
    )
    assert result.failed_roles == (), list(
        TargetedExtractionState.objects.values_list("last_error_code", flat=True)
    )
    affiliation = PersonBrandAffiliation.objects.exclude(start_date__isnull=True).get()
    assert (affiliation.start_date, affiliation.start_date_precision) == (value, precision)
    movement = ProfileMovementCandidate.objects.get()
    assert movement.effective_date is None
    assert movement.effective_date_precision == "unknown"
