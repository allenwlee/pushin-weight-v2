"""PostgreSQL regression net for deterministic profile history."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from core.models import (
    Account,
    AccountProfileSnapshot,
    Brand,
    BrandAccount,
    PersonBrandAffiliation,
    PersonBrandAffiliationEvidence,
    Post,
    Role,
    TwitterListMembership,
)
from core.profile_snapshots import (
    BrandReference,
    build_account_affiliation_contexts,
    classify_affiliation_signals,
    persist_affiliation_candidates,
    profile_observation_from_payload,
    record_profile_snapshot,
)
from monitor.cycle import CycleRunner
from x_monitor.apify import _normalize_tweet

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def _post(account: Account, tweet_id: str, observed_at):
    post = Post.objects.create(tweet_id=tweet_id, author=account, text=tweet_id)
    Post.objects.filter(pk=post.pk).update(fetched_at=observed_at)
    post.refresh_from_db()
    return post


def _observation(description: str):
    return profile_observation_from_payload(
        {
            "author_id": "profile-account",
            "author_description": description,
            "_author_present_fields": ["author_description"],
        }
    )


def test_profile_history_collapses_consecutive_values_and_keeps_a_b_a():
    account = Account.objects.create(author_id="profile-account", handle="profile")
    start = timezone.now()
    posts = [
        _post(account, f"profile-{index}", start + timedelta(minutes=index))
        for index in range(4)
    ]
    values = ["A", "A", "B", "A"]
    for post, value in zip(posts, values, strict=True):
        record_profile_snapshot(
            account=account,
            observation=_observation(value),
            observed_at=post.fetched_at,
            source_kind="post",
            source_post=post,
        )

    snapshots = list(AccountProfileSnapshot.objects.order_by("first_observed_at"))
    assert [row.description for row in snapshots] == ["A", "B", "A"]
    assert [row.observation_count for row in snapshots] == [2, 1, 1]
    assert snapshots[0].last_observed_at == posts[1].fetched_at

    # A full chronological replay is idempotent, including the collapsed p2
    # observation whose source post is not the first source of its snapshot.
    for post, value in zip(posts, values, strict=True):
        record_profile_snapshot(
            account=account,
            observation=_observation(value),
            observed_at=post.fetched_at,
            source_kind="post",
            source_post=post,
        )
    assert list(
        AccountProfileSnapshot.objects.order_by("first_observed_at").values_list(
            "observation_count", flat=True
        )
    ) == [2, 1, 1]


def test_normalizer_preserves_absent_vs_explicit_null_profile_fields():
    normalized = _normalize_tweet(
        {
            "id": "presence",
            "author": {
                "id": "presence-author",
                "userName": "present",
                "description": None,
            },
        }
    )
    observation = profile_observation_from_payload(normalized)

    assert "description" in observation.present_fields
    assert observation.profile_data["description"] is None
    assert "location" not in observation.present_fields
    assert "author_description" in normalized["_author_present_fields"]
    assert "author_location" not in normalized["_author_present_fields"]


def test_minimax_business_badge_is_retained_without_image_processing():
    observation = profile_observation_from_payload(
        {
            "author_affiliates_highlighted_label": {
                "label": {
                    "description": "MiniMax (official)",
                    "badge": {
                        "url": "https://pbs.twimg.com/profile_images/VxHk9HyU_bigger.jpg"
                    },
                    "url": {
                        "url": "https://x.com/MiniMax_AI",
                        "urlType": "DeepLink",
                    },
                    "userLabelDisplayType": "Badge",
                    "userLabelType": "BusinessLabel",
                }
            },
            "_author_present_fields": ["author_affiliates_highlighted_label"],
        }
    )

    assert observation.profile_data["affiliate_target_username"] == "MiniMax_AI"
    assert (
        observation.profile_data["affiliate_label_description"] == "MiniMax (official)"
    )
    assert observation.profile_data["affiliate_label_type"] == "BusinessLabel"
    assert observation.profile_data["affiliate_display_type"] == "Badge"
    assert observation.profile_data["affiliate_badge_image_url"].endswith(
        "VxHk9HyU_bigger.jpg"
    )


def test_ranked_rules_keep_staff_community_former_and_bare_handle_distinct():
    brand = Brand.objects.create(nickname="minimax", display_name="MiniMax")
    reference = BrandReference(
        brand_id=brand.pk,
        display_name="MiniMax",
        handles=("minimax_ai",),
        aliases=("MiniMax",),
    )
    cases = (
        ("Researcher at @MiniMax_AI", "staff", "employment", "current"),
        ("MiniMax ambassador @MiniMax_AI", "community", "ambassador", "current"),
        ("Former intern at @MiniMax_AI", "staff", "employment", "former"),
        ("@MiniMax_AI", "unknown", "other", "unknown"),
    )
    for index, (description, role, affiliation_type, status) in enumerate(cases):
        account = Account.objects.create(author_id=f"rule-{index}")
        signals = classify_affiliation_signals(
            account=account,
            observation=_observation(description),
            references=(reference,),
        )
        assert len(signals) == 1
        assert (
            signals[0].candidate_role,
            signals[0].affiliation_type,
            signals[0].status,
        ) == (role, affiliation_type, status)


def test_relationship_words_are_scoped_to_each_brand_in_a_multi_brand_bio():
    deepmind = Brand.objects.create(nickname="deepmind", display_name="Google DeepMind")
    anthropic = Brand.objects.create(nickname="anthropic", display_name="Anthropic")
    references = (
        BrandReference(
            brand_id=deepmind.pk,
            display_name="Google DeepMind",
            handles=("googledeepmind",),
            aliases=("Google DeepMind",),
        ),
        BrandReference(
            brand_id=anthropic.pk,
            display_name="Anthropic",
            handles=("anthropicai",),
            aliases=("Anthropic",),
        ),
    )
    account = Account.objects.create(author_id="multi-brand")

    signals = classify_affiliation_signals(
        account=account,
        observation=_observation("I worked at Google DeepMind and now at Anthropic."),
        references=references,
    )

    by_brand = {signal.brand_id: signal for signal in signals}
    assert (by_brand[deepmind.pk].candidate_role, by_brand[deepmind.pk].status) == (
        "staff",
        "former",
    )
    assert (by_brand[anthropic.pk].candidate_role, by_brand[anthropic.pk].status) == (
        "staff",
        "current",
    )


def test_call_a_is_positive_evidence_but_inactive_membership_never_closes_claim():
    now = timezone.now()
    brand = Brand.objects.create(nickname="call-a-brand", display_name="Call A Brand")
    official = Account.objects.create(author_id="official", handle="CallABrand")
    role = Role.objects.create(key="official")
    BrandAccount.objects.create(brand=brand, account=official, role=role)
    account = Account.objects.create(author_id="list-person", handle="person")
    membership = TwitterListMembership.objects.create(
        list_id=42,
        account=account,
        active=True,
        source="call_a",
        first_seen_at=now,
        last_seen_at=now,
    )
    observation = _observation("@CallABrand")
    reference = BrandReference(
        brand_id=brand.pk,
        display_name="Call A Brand",
        handles=("callabrand",),
        aliases=("Call A Brand",),
    )
    signal = classify_affiliation_signals(
        account=account, observation=observation, references=(reference,)
    )[0]
    assert signal.candidate_role == "staff"
    assert signal.call_a_active is True

    post = _post(account, "list-person-source", now)
    snapshot, *_ = record_profile_snapshot(
        account=account,
        observation=observation,
        observed_at=now,
        source_kind="post",
        source_post=post,
    )
    persist_affiliation_candidates(
        account=account,
        snapshot=snapshot,
        signals=(signal,),
        observed_at=now,
    )
    affiliation = PersonBrandAffiliation.objects.get()
    assert affiliation.start_date is None
    assert affiliation.end_date is None
    assert affiliation.review_status == "pending"

    membership.active = False
    membership.save(update_fields=["active"])
    assert PersonBrandAffiliation.objects.get().status == "current"


def test_affiliation_contexts_batch_reviewed_roles_and_call_a_membership(
    django_assert_num_queries,
):
    now = timezone.now()
    brand = Brand.objects.create(nickname="batch-brand", display_name="Batch Brand")
    role = Role.objects.create(key="staff")
    first = Account.objects.create(author_id="batch-one")
    second = Account.objects.create(author_id="batch-two")
    BrandAccount.objects.create(brand=brand, account=first, role=role)
    TwitterListMembership.objects.create(
        list_id=99,
        account=second,
        active=True,
        source="call_a",
        first_seen_at=now,
        last_seen_at=now,
    )

    with django_assert_num_queries(2):
        contexts = build_account_affiliation_contexts((first.pk, second.pk))

    assert contexts[first.pk].reviewed_edges == ((brand.pk, "staff"),)
    assert contexts[first.pk].call_a_active is False
    assert contexts[second.pk].reviewed_edges == ()
    assert contexts[second.pk].call_a_active is True


def test_backfill_checkpoint_resume_and_full_rerun_are_idempotent(tmp_path, capsys):
    start = timezone.now()
    for index in range(2):
        account = Account.objects.create(
            author_id=f"account-{index}",
            handle=f"handle-{index}",
            display_name=f"Person {index}",
        )
        post = _post(account, f"backfill-{index}", start + timedelta(minutes=index))
        Post.objects.filter(pk=post.pk).update(
            author_handle=account.handle,
            author_name=account.display_name,
            author_description=f"bio-{index}",
        )
        account.description = f"bio-{index}"
        account.save(update_fields=["description"])

    checkpoint = tmp_path / "checkpoint.json"
    call_command(
        "backfill_account_profile_snapshots",
        checkpoint=checkpoint,
        limit_accounts=1,
    )
    first = json.loads(capsys.readouterr().out)
    assert first["accounts_processed"] == 1
    assert checkpoint.exists()

    call_command("backfill_account_profile_snapshots", checkpoint=checkpoint)
    second = json.loads(capsys.readouterr().out)
    assert second["accounts_processed"] == 1
    count_after_resume = AccountProfileSnapshot.objects.count()

    call_command("backfill_account_profile_snapshots")
    capsys.readouterr()
    assert AccountProfileSnapshot.objects.count() == count_after_resume


def test_production_persist_call_chain_captures_profile_without_provider_call():
    runner = CycleRunner.__new__(CycleRunner)
    runner._errors = []
    runner._clock = timezone.now
    item = {
        "id": "live-profile",
        "text": "hello",
        "author_id": "live-author",
        "author_handle": "live",
        "author_name": "Live Person",
        "author_description": "Independent researcher",
        "_author_present_fields": [
            "author_handle",
            "author_name",
            "author_description",
        ],
        "brand_ids": [],
        "mentions": [],
        "classifications": {},
    }

    assert runner._persist_items([item]) == (1, 0, 0, 0)
    snapshot = AccountProfileSnapshot.objects.get(account_id="live-author")
    assert snapshot.description == "Independent researcher"
    assert snapshot.first_source_post_id == "live-profile"
    assert runner._errors == []
    assert PersonBrandAffiliationEvidence.objects.count() == 0
