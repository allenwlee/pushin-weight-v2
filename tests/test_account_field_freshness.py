from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.models import Account
from monitor.cycle import _upsert_account, _upsert_post

pytestmark = pytest.mark.django_db


@pytest.mark.requires_postgres
@pytest.mark.parametrize(
    ("snake_value", "camel_value", "expected"),
    [(0, None, 0), (0, 99, 0), (7, 99, 7), (None, 0, 0), (None, 9, 9)],
)
def test_post_engagement_counters_preserve_values_on_insert_and_update(
    snake_value, camel_value, expected
):
    fields = {
        "like_count": "likeCount",
        "retweet_count": "retweetCount",
        "reply_count": "replyCount",
        "quote_count": "quoteCount",
    }
    counters = {key: snake_value for key in fields}
    if camel_value is not None:
        counters.update({key: camel_value for key in fields.values()})

    post, created = _upsert_post({"id": "counter-create", **counters})
    assert created is True
    post.refresh_from_db()
    assert [getattr(post, key) for key in fields] == [expected] * 4

    post, _ = _upsert_post({"id": "counter-update", **dict.fromkeys(fields, 12)})
    post, created = _upsert_post({"id": post.tweet_id, **counters})
    assert created is False
    post.refresh_from_db()
    assert [getattr(post, key) for key in fields] == [expected] * 4


@pytest.mark.requires_postgres
@pytest.mark.parametrize(
    "missing",
    [{}, dict.fromkeys(["like_count", "retweet_count", "reply_count", "quote_count"])],
)
def test_sparse_post_update_preserves_known_engagement_and_unknown_optional_counts(missing):
    fields = ["like_count", "retweet_count", "reply_count", "quote_count"]
    sparse_post, _ = _upsert_post({"id": "sparse-create", **missing})
    sparse_post.refresh_from_db()
    assert [getattr(sparse_post, key) for key in fields] == [None] * 4

    post, _ = _upsert_post({"id": "sparse-counters", **dict.fromkeys(fields, 12)})

    post, created = _upsert_post({"id": post.tweet_id, **missing})

    assert created is False
    post.refresh_from_db()
    assert [getattr(post, key) for key in fields] == [12] * 4
    assert post.view_count is None
    assert post.bookmark_count is None


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
    assert post.author.author_id == "42"
    assert post.author_id == post.author.account_key
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
    assert post.author.author_id == "42"
    assert post.author_id == post.author.account_key
    account.refresh_from_db()
    assert account.handle is None
    assert account.display_name == "Accepted Name"


def test_post_affiliate_label_refresh_preserves_about_only_country(company_country_catalogue):
    from core.geolocation_evidence import source_evidence, write_source_evidence

    account = Account.objects.create(
        author_id="42",
        based_in_location_id=company_country_catalogue["US"],
        affiliate_label_description="Old",
    )
    write_source_evidence(account.x_details, reported_based_in="United States")

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
    assert account.based_in_location_id == company_country_catalogue["US"]
    assert source_evidence(account.x_details).reported_based_in == "United States"


def test_post_refreshes_shared_live_about_fields_and_preserves_about_only_fields():
    account = Account.objects.create(
        author_id="42",
        verified=True,
        profile_picture="https://cdn.example/about.png",
        created_country_accurate=True,
        verification_info_id="verification-42",
    )

    _upsert_account(
        {
            "author_id": "42",
            "author_verified": False,
            "author_profile_picture": "https://cdn.example/post.png",
        }
    )

    account.refresh_from_db()
    assert account.verified is False
    assert account.profile_picture.endswith("post.png")
    assert account.created_country_accurate is True
    assert account.verification_info_id == "verification-42"
