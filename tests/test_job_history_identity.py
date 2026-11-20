"""Identity and prose imports preserve source evidence and avoid enrollment."""

from copy import deepcopy
from datetime import timedelta

import pytest
from django.db import transaction
from django.utils import timezone

from core.models import (
    Account,
    AccountProfileSnapshot,
    Person,
    PersonAccount,
    PersonNameSelection,
    Post,
    StaffCollectionWork,
)
from core.staff_assets.arrivals import catch_up
from core.staff_assets.job_history_identity import IdentityHold, apply_identity_records

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def prepared():
    when = timezone.now().isoformat()
    name = "王明"
    identity = {
        "account_action": "create",
        "person_action": "create",
        "person_id": None,
        "account_key": None,
    }
    item = {
        "native_id": "938578241",
        "handle": "savedwang",
        "names": [name],
        "identity": identity,
        "name_source": {
            "source_kind": "saved_account_name",
            "source_text": name,
            "source_reference": "https://x.com/savedwang",
            "observed_at": when,
        },
        "sources": [
            {
                "key": "bio:0",
                "kind": "saved_bio",
                "text": "Former university engineer",
                "observations": [
                    {"observed": when, "handle": "savedwang", "post_id": None}
                ],
            }
        ],
        "language_proposal": {
            "action": "propose",
            "value": "zh-Hans",
            "exclusion_reason": None,
        },
    }
    ref = "person:938578241/name:und"
    actions = [
        {
            "table": "people_names",
            "action": "create",
            "key": ref,
            "fields": {
                "person_id": "person:938578241",
                "full_name": name,
                "locale_id": "und",
            },
        },
        {
            "table": "people_name_evidence",
            "action": "create",
            "key": ref,
            "fields": {
                "name_id": ref,
                "source_text": name,
                "source_reference": "https://x.com/savedwang",
                "observed_at": when,
                "source_kind": "saved_account_name",
            },
        },
        {
            "table": "person_name_selections",
            "action": "create",
            "fields": {"name_id": ref},
        },
        {
            "table": "people_texts",
            "action": "compare_or_create",
            "fields": {
                "kind": "biography",
                "origin": "summary",
                "language": "und",
                "text": "University engineer (former)",
                "source_reference": "https://x.com/savedwang",
                "source_keys": ["bio:0"],
                "observed_at": when,
                "review_status": "pending",
                "action": "compare_or_create",
            },
        },
    ]
    provenance = {
        "review_sha256": "a" * 64,
        "source_audit_sha256": "b" * 64,
        "name_audit_sha256": "c" * 64,
        "authorized_by": "Allen",
        "reviewed_at": when,
    }
    return item, actions, provenance


def test_new_identity_sourced_name_language_and_text_replay_without_work():
    item, actions, provenance = prepared()
    with transaction.atomic():
        person, account, counts = apply_identity_records(item, actions, provenance)
    assert (
        counts["accounts_created"],
        counts["people_created"],
        counts["names_created"],
        counts["language_updated"],
        counts["texts_created"],
    ) == (1, 1, 1, 1, 1)
    assert person.primary_language == "zh-Hans"
    assert PersonNameSelection.objects.filter(
        person=person, name__full_name="王明"
    ).exists()
    assert account.author_id == item["native_id"]
    assert person.account_links.get(account=account).resolution_status == "pending"
    with transaction.atomic():
        person_again, _, repeated = apply_identity_records(item, actions, provenance)
    assert person_again.pk == person.pk
    assert (
        repeated["accounts_reused"],
        repeated["people_reused"],
        repeated["names_reused"],
        repeated["language_retained"],
        repeated["texts_reused"],
    ) == (1, 1, 1, 1, 1)
    assert person.names.count() == 1 and person.texts.count() == 1
    catch_up(list_id="999999")
    assert not StaffCollectionWork.objects.filter(person=person).exists()


def test_stale_handle_conflict_rolls_back_new_identity():
    item, actions, provenance = prepared()
    Account.x.create(author_id="999999", handle=item["handle"])
    with pytest.raises(IdentityHold, match="another account"), transaction.atomic():
        apply_identity_records(item, actions, provenance)
    assert not Account.x.filter(author_id=item["native_id"]).exists()
    assert not PersonAccount.objects.exists()


@pytest.mark.parametrize("evidence", ["post", "profile"])
def test_verified_historical_handle_reuses_native_account_without_renaming(evidence):
    item, actions, provenance = prepared()
    account = Account.x.create(author_id=item["native_id"], handle="newwang")
    item["identity"].update(account_action="reuse", account_key=str(account.pk))
    item["name_source"]["native_id"] = item["native_id"]
    when = timezone.datetime.fromisoformat(item["name_source"]["observed_at"])
    if evidence == "post":
        Post.objects.create(
            tweet_id="123456789", author=account, author_handle="savedwang",
            text="Saved source", created_at=when,
        )
    else:
        AccountProfileSnapshot.objects.create(
            account=account, profile_hash="a" * 64, handle="savedwang",
            first_observed_at=when, last_observed_at=when,
            first_source_kind="profile",
        )
    with transaction.atomic():
        person, reused, counts = apply_identity_records(item, actions, provenance)
    account.refresh_from_db()
    assert reused.pk == account.pk and account.handle == "newwang"
    assert counts["accounts_reused"] == 1 and counts["people_created"] == 1
    assert person.names.get().evidence.get().source_reference.endswith("/savedwang")


@pytest.mark.parametrize("conflict", ["unproven", "other_account", "reassigned"])
def test_historical_handle_requires_same_native_account_and_no_current_owner(conflict):
    item, actions, provenance = prepared()
    account = Account.x.create(author_id=item["native_id"], handle="newwang")
    other = Account.x.create(author_id="999999", handle="someoneelse")
    item["identity"].update(account_action="reuse", account_key=str(account.pk))
    item["name_source"]["native_id"] = item["native_id"]
    if conflict != "unproven":
        Post.objects.create(
            tweet_id="123456789", author=other if conflict == "other_account" else account,
            author_handle="savedwang", text="Saved source", created_at=timezone.now(),
        )
    if conflict == "reassigned":
        other.handle = "savedwang"
        other.save(update_fields=["handle"])
    with pytest.raises(IdentityHold, match="Saved handle conflicts"), transaction.atomic():
        apply_identity_records(item, actions, provenance)
    assert not PersonAccount.objects.exists()


def test_bad_name_and_summary_source_are_held_without_mutating_selections():
    item, actions, provenance = prepared()
    item["language_proposal"]["action"] = "no_proposal"
    actions[1]["fields"]["source_reference"] = "https://x.com/someoneelse"
    actions[3]["fields"]["observed_at"] = (
        timezone.now() - timedelta(days=3)
    ).isoformat()
    with transaction.atomic():
        person, _, counts = apply_identity_records(item, actions, provenance)
    assert counts["names_held"] == 1 and counts["texts_held"] == 1
    assert not person.names.exists() and not person.texts.exists()
    assert not PersonNameSelection.objects.filter(person=person).exists()


def test_invalid_language_provenance_rolls_back_entire_person():
    item, actions, provenance = prepared()
    provenance = {**provenance, "review_sha256": "invalid"}
    with pytest.raises(IdentityHold, match="Language proposal"), transaction.atomic():
        apply_identity_records(item, actions, provenance)
    assert not Account.x.filter(author_id=item["native_id"]).exists()


def test_repeated_name_source_keeps_each_original_observation_time():
    item, actions, provenance = prepared()
    later = (
        timezone.datetime.fromisoformat(item["name_source"]["observed_at"])
        + timedelta(hours=1)
    ).isoformat()
    item["sources"].append(
        {
            "key": "bio:1",
            "kind": "saved_bio",
            "text": "王明",
            "observations": [
                {"observed": later, "handle": item["handle"], "post_id": None}
            ],
        }
    )
    second = deepcopy(actions[1])
    second["fields"]["observed_at"] = later
    actions.append(second)
    with transaction.atomic():
        person, _, _ = apply_identity_records(item, actions, provenance)
    name = person.names.get(full_name="王明")
    assert set(name.evidence.values_list("observed_at", flat=True)) == {
        _time
        for _time in (
            timezone.datetime.fromisoformat(item["name_source"]["observed_at"]),
            timezone.datetime.fromisoformat(later),
        )
    }
    with transaction.atomic():
        apply_identity_records(item, actions, provenance)
    assert name.evidence.count() == 2


def test_existing_language_and_selection_are_preserved_on_import():
    item, actions, provenance = prepared()
    with transaction.atomic():
        person, _, _ = apply_identity_records(item, actions, provenance)
    original_name = PersonNameSelection.objects.get(
        person=person, display_locale_id="und"
    ).name
    Person.objects.filter(pk=person.pk).update(primary_language="en")
    with transaction.atomic():
        current, _, counts = apply_identity_records(item, actions, provenance)
    assert current.primary_language == "en"
    assert counts["language_retained"] == 1
    assert (
        PersonNameSelection.objects.get(person=person, display_locale_id="und").name
        == original_name
    )
