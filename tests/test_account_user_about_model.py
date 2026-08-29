from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from django.db import IntegrityError

from core.models import Account

pytestmark = pytest.mark.django_db


def test_account_model_exposes_typed_user_about_fields():
    expected = {
        "created_at",
        "protected",
        "affiliate_label_badge_url",
        "affiliate_label_description",
        "affiliate_label_url",
        "affiliate_label_url_type",
        "affiliate_label_user_label_display_type",
        "affiliate_label_user_label_type",
        "account_based_in",
        "location_accurate",
        "learn_more_url",
        "affiliate_username",
        "source",
        "username_changes_count",
        "username_changes_last_changed_at_msec",
        "created_country_accurate",
        "verification_info_id",
        "verification_info_is_identity_verified",
        "verification_info_reason_verified_since_msec",
        "unavailable",
        "unavailable_reason",
        "identity_profile_label_badge_url",
        "identity_profile_label_description",
        "identity_profile_label_url",
        "identity_profile_label_url_type",
        "identity_profile_label_user_label_display_type",
        "identity_profile_label_user_label_type",
        "country_code",
        "account_based_in_fetched_at",
    }
    fields = {field.name for field in Account._meta.get_fields()}
    assert expected <= fields
    assert not any("raw" in field for field in expected)


def test_live_user_about_fields_use_typed_deduplicated_destinations():
    Account.objects.create(author_id="42")
    outcome = Account.apply_observation(
        author_id="42",
        observed_author_id="42",
        source="user_about",
        observed_at=datetime(2026, 8, 30, tzinfo=UTC),
        candidates={
            "verified": True,
            "profile_picture": "https://cdn.example/avatar.png",
            "created_country_accurate": False,
            "username_changes_last_changed_at_msec": 1_784_691_635_000,
            "verification_info_id": "verification-42",
            "verification_info_is_identity_verified": True,
            "verification_info_reason_verified_since_msec": 1_784_691_635_000,
        },
        present_fields={
            "verified",
            "profile_picture",
            "created_country_accurate",
            "username_changes_last_changed_at_msec",
            "verification_info_id",
            "verification_info_is_identity_verified",
            "verification_info_reason_verified_since_msec",
        },
    )

    account = Account.objects.get(author_id="42")
    assert account.verified is True
    assert account.profile_picture.endswith("avatar.png")
    assert account.created_country_accurate is False
    assert account.username_changes_last_changed_at_msec == 1_784_691_635_000
    assert account.verification_info_id == "verification-42"
    assert account.verification_info_is_identity_verified is True
    assert account.verification_info_reason_verified_since_msec == 1_784_691_635_000
    assert outcome.rejected_fields == {}
    assert not hasattr(account, "is_verified")


def test_valid_observation_applies_and_invalid_sibling_is_contained():
    account = Account.objects.create(author_id="42", handle="good", followers_count=100)
    observed_at = datetime(2026, 8, 29, tzinfo=UTC)

    outcome = Account.apply_observation(
        author_id="42",
        observed_author_id="42",
        source="post",
        observed_at=observed_at,
        candidates={
            "handle": "bad handle",
            "display_name": "New Name",
            "followers_count": -1,
            "is_blue_verified": "false",
        },
        present_fields={
            "handle",
            "display_name",
            "followers_count",
            "is_blue_verified",
        },
    )

    account.refresh_from_db()
    assert account.handle == "good"
    assert account.display_name == "New Name"
    assert account.followers_count == 100
    assert account.is_blue_verified is None
    assert set(outcome.rejected_fields) == {
        "handle",
        "followers_count",
        "is_blue_verified",
    }


def test_unavailable_observation_requires_selected_handle_to_still_match():
    observed_at = datetime(2026, 8, 30, tzinfo=UTC)
    account = Account.objects.create(author_id="42", handle="current")

    outcome = Account.apply_observation(
        author_id="42",
        observed_author_id="42",
        source="user_about",
        observed_at=observed_at,
        candidates={
            "unavailable": True,
            "unavailable_reason": "Account unavailable",
            "account_based_in_fetched_at": observed_at,
        },
        present_fields={
            "unavailable",
            "unavailable_reason",
            "account_based_in_fetched_at",
        },
        expected_handle="stale-selection",
    )

    account.refresh_from_db()
    assert outcome.identity_rejected is True
    assert account.unavailable is None
    assert account.unavailable_reason is None
    assert account.account_based_in_fetched_at is None


def test_identity_mismatch_rejects_without_creating_or_writing():
    account = Account.objects.create(author_id="42", display_name="Before")
    outcome = Account.apply_observation(
        author_id="42",
        observed_author_id="99",
        source="user_about",
        observed_at=datetime(2026, 8, 29, tzinfo=UTC),
        candidates={"display_name": "After"},
        present_fields={"display_name"},
    )

    account.refresh_from_db()
    assert outcome.identity_rejected is True
    assert account.display_name == "Before"


def test_created_at_is_fill_once_and_conflicts_are_reported():
    first = datetime(2020, 1, 1, tzinfo=UTC)
    later = datetime(2021, 1, 1, tzinfo=UTC)
    Account.objects.create(author_id="42")

    Account.apply_observation(
        author_id="42",
        observed_author_id="42",
        source="user_about",
        observed_at=datetime(2026, 8, 29, tzinfo=UTC),
        candidates={"created_at": first},
        present_fields={"created_at"},
    )
    outcome = Account.apply_observation(
        author_id="42",
        observed_author_id="42",
        source="post",
        observed_at=datetime(2026, 8, 30, tzinfo=UTC),
        candidates={"created_at": later},
        present_fields={"created_at"},
    )

    account = Account.objects.get(author_id="42")
    assert account.created_at == first
    assert outcome.rejected_fields["created_at"] == "conflict"


def test_malformed_affiliate_group_preserves_existing_group():
    account = Account.objects.create(
        author_id="42",
        affiliate_label_description="Good label",
        affiliate_label_url="https://x.com/good",
    )
    outcome = Account.apply_observation(
        author_id="42",
        observed_author_id="42",
        source="post",
        observed_at=datetime(2026, 8, 29, tzinfo=UTC),
        candidates={
            "affiliate_label_description": "Bad replacement",
            "affiliate_label_url": "javascript:alert(1)",
        },
        present_fields={
            "affiliate_label_description",
            "affiliate_label_url",
        },
    )

    account.refresh_from_db()
    assert account.affiliate_label_description == "Good label"
    assert account.affiliate_label_url == "https://x.com/good"
    assert "affiliate_label_url" in outcome.rejected_fields


def test_complete_label_presence_with_missing_candidate_rejects_without_raising():
    account = Account.objects.create(
        author_id="42",
        affiliate_label_description="Good label",
    )
    fields = {
        "affiliate_label_badge_url",
        "affiliate_label_description",
        "affiliate_label_url",
        "affiliate_label_url_type",
        "affiliate_label_user_label_display_type",
        "affiliate_label_user_label_type",
    }

    outcome = Account.apply_observation(
        author_id="42",
        observed_author_id="42",
        source="post",
        observed_at=datetime(2026, 8, 29, tzinfo=UTC),
        candidates={field: None for field in fields - {"affiliate_label_url"}},
        present_fields=fields,
    )

    account.refresh_from_db()
    assert account.affiliate_label_description == "Good label"
    assert set(outcome.rejected_fields) == fields


def test_multiline_profile_text_is_a_valid_observation():
    Account.objects.create(author_id="42", description="Before")

    outcome = Account.apply_observation(
        author_id="42",
        observed_author_id="42",
        source="post",
        observed_at=datetime(2026, 8, 29, tzinfo=UTC),
        candidates={"description": "First line\nSecond line"},
        present_fields={"description"},
    )

    account = Account.objects.get(author_id="42")
    assert account.description == "First line\nSecond line"
    assert outcome.rejected_fields == {}


def test_handle_integrity_race_rejects_handle_but_applies_sibling():
    account = Account.objects.create(author_id="42", handle="before")
    original_save = Account.save
    raised = False

    def race_once(instance, *args, **kwargs):
        nonlocal raised
        if not raised and "handle" in (kwargs.get("update_fields") or []):
            raised = True
            raise IntegrityError("simulated concurrent handle claim")
        return original_save(instance, *args, **kwargs)

    with patch.object(Account, "save", race_once):
        outcome = Account.apply_observation(
            author_id="42",
            observed_author_id="42",
            source="post",
            observed_at=datetime(2026, 8, 29, tzinfo=UTC),
            candidates={"handle": "after", "display_name": "Accepted"},
            present_fields={"handle", "display_name"},
        )

    account.refresh_from_db()
    assert account.handle == "before"
    assert account.display_name == "Accepted"
    assert outcome.rejected_fields == {"handle": "conflict"}
