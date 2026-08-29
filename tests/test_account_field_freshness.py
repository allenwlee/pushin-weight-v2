from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.models import Account
from monitor.cycle import _upsert_account, _upsert_post

pytestmark = pytest.mark.django_db


def test_equal_follower_observation_advances_freshness():
    t1 = datetime(2026, 8, 28, tzinfo=UTC)
    t2 = t1 + timedelta(days=1)
    Account.objects.create(
        author_id="42", followers_count=1_000, followers_fetched_at=t1
    )

    outcome = Account.apply_observation(
        author_id="42",
        observed_author_id="42",
        source="post",
        observed_at=t2,
        candidates={"followers_count": 1_000},
        present_fields={"followers_count"},
    )

    account = Account.objects.get(author_id="42")
    assert account.followers_count == 1_000
    assert account.followers_fetched_at == t2
    assert "followers_fetched_at" in outcome.applied_fields


@pytest.mark.parametrize("value", [None, -1, True, "1000"])
def test_missing_or_invalid_follower_value_does_not_advance_freshness(value):
    t1 = datetime(2026, 8, 28, tzinfo=UTC)
    Account.objects.create(
        author_id="42", followers_count=1_000, followers_fetched_at=t1
    )
    present = set() if value is None else {"followers_count"}

    Account.apply_observation(
        author_id="42",
        observed_author_id="42",
        source="post",
        observed_at=t1 + timedelta(days=1),
        candidates={"followers_count": value},
        present_fields=present,
    )

    account = Account.objects.get(author_id="42")
    assert account.followers_count == 1_000
    assert account.followers_fetched_at == t1


def test_post_upsert_preserves_missing_values_and_advances_equal_follower():
    t1 = datetime(2026, 8, 28, tzinfo=UTC)
    account = Account.objects.create(
        author_id="42",
        handle="existing",
        followers_count=1_000,
        followers_fetched_at=t1,
        is_blue_verified=True,
    )

    returned = _upsert_account(
        {
            "author_id": "42",
            "author_name": "Updated Name",
            "author_followers_count": 1_000,
        }
    )

    account.refresh_from_db()
    assert returned == account
    assert account.handle == "existing"
    assert account.display_name == "Updated Name"
    assert account.followers_count == 1_000
    assert account.followers_fetched_at > t1
    assert account.is_blue_verified is True


def test_post_upsert_contains_invalid_fields_without_raising():
    account = Account.objects.create(
        author_id="42",
        handle="existing",
        followers_count=1_000,
    )

    returned = _upsert_account(
        {
            "author_id": "42",
            "author_handle": "bad handle",
            "author_name": "Still Accepted",
            "author_followers_count": -10,
            "author_is_blue_verified": "false",
        }
    )

    account.refresh_from_db()
    assert returned == account
    assert account.handle == "existing"
    assert account.display_name == "Still Accepted"
    assert account.followers_count == 1_000
    assert account.is_blue_verified is None


def test_invalid_account_fields_do_not_block_related_post_write():
    raw = {
        "id": "tweet-1",
        "text": "post still lands",
        "author_id": "42",
        "author_handle": "bad handle",
        "author_name": "Accepted Name",
        "author_followers_count": -1,
        "author_is_blue_verified": "false",
    }

    account = _upsert_account(raw)
    post, created = _upsert_post(raw, account=account)

    assert created is True
    assert post is not None
    assert post.author_id == "42"
    assert post.text == "post still lands"
    account.refresh_from_db()
    assert account.handle is None
    assert account.display_name == "Accepted Name"


def test_duplicate_handle_does_not_block_related_post_write():
    Account.objects.create(author_id="existing", handle="claimed")
    raw = {
        "id": "tweet-handle-conflict",
        "text": "post still lands",
        "author_id": "42",
        "author_handle": "CLAIMED",
        "author_name": "Accepted Name",
    }

    account = _upsert_account(raw)
    post, created = _upsert_post(raw, account=account)

    assert created is True
    assert post is not None
    assert post.author_id == "42"
    account.refresh_from_db()
    assert account.handle is None
    assert account.display_name == "Accepted Name"


def test_post_affiliate_label_refresh_preserves_about_only_country():
    account = Account.objects.create(
        author_id="42",
        country_code="US",
        account_based_in="United States",
        affiliate_label_description="Old",
    )

    _upsert_account(
        {
            "author_id": "42",
            "author_affiliates_highlighted_label": {
                "label": {
                    "description": "New",
                    "badge": {"url": "https://cdn.example/badge.png"},
                    "url": {"url": "https://x.com/new", "urlType": "DeepLink"},
                    "userLabelDisplayType": "Badge",
                    "userLabelType": "BusinessLabel",
                }
            },
        }
    )

    account.refresh_from_db()
    assert account.affiliate_label_description == "New"
    assert account.country_code == "US"
    assert account.account_based_in == "United States"
