"""Saved profile observations use the shared snapshot writer without signals."""

from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import (
    Account,
    AccountProfileSnapshot,
    PersonBrandAffiliation,
    ProfileMovementCandidate,
    StaffCollectionWork,
)
from core.profile_snapshots import (
    profile_observation_from_payload,
    record_profile_snapshot,
)
from core.staff_assets.job_history_import import record_saved_profile_snapshot

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def observation(value):
    return profile_observation_from_payload(
        {"author_description": value, "_author_present_fields": ["author_description"]}
    )


def test_saved_profile_capture_is_source_only():
    account = Account.objects.create(
        author_id="saved-profile-only", handle="savedprofile"
    )
    when = timezone.now()
    result = record_saved_profile_snapshot(
        account=account, observation=observation("Researcher"), observed_at=when
    )
    assert result["action"] == "create"
    assert (
        AccountProfileSnapshot.objects.get(pk=result["snapshot_id"]).first_observed_at
        == when
    )
    assert not PersonBrandAffiliation.objects.exists()
    assert not ProfileMovementCandidate.objects.exists()
    assert not StaffCollectionWork.objects.exists()


def test_conflicting_saved_profile_is_held_with_original_observation():
    account = Account.objects.create(
        author_id="saved-profile-conflict", handle="savedconflict"
    )
    when = timezone.now()
    for offset in (0, 4):
        record_profile_snapshot(
            account=account,
            observation=observation("A"),
            observed_at=when + timedelta(hours=offset),
            source_kind="post",
        )
    incoming = observation("B")
    result = record_saved_profile_snapshot(
        account=account, observation=incoming, observed_at=when + timedelta(hours=2)
    )
    assert result["action"] == "hold"
    assert result["observation"] is incoming
    assert AccountProfileSnapshot.objects.filter(account=account).count() == 1


def test_concurrent_replay_creates_one_profile_snapshot():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import close_old_connections

    account = Account.objects.create(
        author_id="concurrent-profile", handle="concurrent"
    )
    when = timezone.now()
    gate = Barrier(2)

    def capture():
        close_old_connections()
        try:
            gate.wait(timeout=5)
            return record_saved_profile_snapshot(
                account=account, observation=observation("Same bio"), observed_at=when
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: capture(), range(2)))
    assert sorted(result["action"] for result in results) == ["create", "reuse"]
    assert AccountProfileSnapshot.objects.filter(account=account).count() == 1


def test_missing_profile_clock_is_held_without_writing():
    account = Account.objects.create(author_id="undated-profile", handle="undated")
    incoming = observation("Saved bio")
    result = record_saved_profile_snapshot(
        account=account, observation=incoming, observed_at=None
    )
    assert result["action"] == "hold"
    assert result["observation"] is incoming
    assert not AccountProfileSnapshot.objects.filter(account=account).exists()


def test_new_identical_source_is_held_without_losing_the_observation():
    from core.models import Post

    account = Account.objects.create(author_id="saved-source", handle="savedsource")
    first = Post.objects.create(tweet_id="saved-source-one", author=account, text="one")
    second = Post.objects.create(
        tweet_id="saved-source-two", author=account, text="two"
    )
    when = timezone.now()
    observed = observation("Same profile")
    result = record_saved_profile_snapshot(
        account=account, observation=observed, observed_at=when, source_post=first
    )
    assert result["action"] == "create"
    held = record_saved_profile_snapshot(
        account=account,
        observation=observed,
        observed_at=when + timedelta(minutes=1),
        source_post=second,
    )
    assert held["action"] == "hold"
    assert held["reason"] == "unrepresented_profile_source"
    assert held["observation"] is observed
    assert held["source_post_id"] == second.pk
    row = AccountProfileSnapshot.objects.get(account=account)
    assert row.observation_count == 1 and row.last_observed_at == when


def test_profile_source_post_for_another_account_is_held():
    from core.models import Post

    account = Account.objects.create(author_id="profile-subject", handle="subject")
    other = Account.objects.create(author_id="profile-other", handle="other")
    post = Post.objects.create(
        tweet_id="foreign-profile-post", author=other, text="post"
    )
    observed = observation("Bio")
    result = record_saved_profile_snapshot(
        account=account,
        observation=observed,
        observed_at=timezone.now(),
        source_post=post,
    )
    assert result["reason"] == "profile_source_account_mismatch"
    assert result["observation"] is observed
    assert not AccountProfileSnapshot.objects.filter(account=account).exists()


def test_same_hash_and_source_do_not_discard_distinct_raw_profile():
    from core.models import Post

    account = Account.objects.create(author_id="saved-raw", handle="savedraw")
    post = Post.objects.create(tweet_id="saved-raw-post", author=account, text="post")
    when = timezone.now()
    first, different = observation("Researcher"), observation("Researcher ")
    assert first.profile_hash == different.profile_hash
    assert (
        record_saved_profile_snapshot(
            account=account, observation=first, observed_at=when, source_post=post
        )["action"]
        == "create"
    )
    held = record_saved_profile_snapshot(
        account=account, observation=different, observed_at=when, source_post=post
    )
    assert held["reason"] == "unrepresented_profile_source"
    assert held["observation"] is different


def test_older_saved_profile_is_recorded_at_its_clock_without_overwriting_account():
    account = Account.objects.create(
        author_id="saved-older", handle="savedolder", description="Current bio"
    )
    now = timezone.now()
    latest = record_saved_profile_snapshot(
        account=account, observation=observation("Current bio"), observed_at=now
    )
    older_time = now - timedelta(days=4)
    earlier = record_saved_profile_snapshot(
        account=account, observation=observation("Old bio"), observed_at=older_time
    )
    assert latest["action"] == earlier["action"] == "create"
    account.refresh_from_db()
    assert account.description == "Current bio"
    assert list(
        AccountProfileSnapshot.objects.filter(account=account)
        .order_by("first_observed_at")
        .values_list("description", "first_observed_at", "last_observed_at")
    ) == [("Old bio", older_time, older_time), ("Current bio", now, now)]


def test_late_equal_historical_profile_does_not_extend_across_later_transition():
    account = Account.objects.create(
        author_id="saved-late-equal", handle="savedlate", description="New bio"
    )
    now = timezone.now()
    record_saved_profile_snapshot(
        account=account, observation=observation("Old bio"), observed_at=now
    )
    record_saved_profile_snapshot(
        account=account,
        observation=observation("New bio"),
        observed_at=now + timedelta(hours=2),
    )
    held = record_saved_profile_snapshot(
        account=account,
        observation=observation("Old bio"),
        observed_at=now + timedelta(hours=1),
    )
    assert held["reason"] == "unrepresented_profile_source"
    assert held["observed_at"] == now + timedelta(hours=1)
    account.refresh_from_db()
    assert account.description == "New bio"
    earlier = AccountProfileSnapshot.objects.get(account=account, description="Old bio")
    assert earlier.first_observed_at == earlier.last_observed_at == now


def test_empty_profile_observation_is_held_without_writing():
    account = Account.objects.create(author_id="empty-profile", handle="emptyprofile")
    result = record_saved_profile_snapshot(
        account=account,
        observation=profile_observation_from_payload({}),
        observed_at=timezone.now(),
    )
    assert result["reason"] == "no_profile_fields"
    assert not AccountProfileSnapshot.objects.filter(account=account).exists()
