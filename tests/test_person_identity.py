"""Identity boundaries exercised through the real import and profile writers."""

import pytest
from django.utils import timezone

from core.models import Account, Person, PersonAccount, Post, StaffIntake
from core.profile_snapshots import (
    BrandReference,
    capture_post_profile_snapshot,
    person_id_for_account,
)
from core.staff_assets.intake import ingest_record
from tests.test_staff_library import record

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def link(person, account, status="pending"):
    now = timezone.now()
    return PersonAccount.objects.create(
        person=person,
        account=account,
        resolution_status=status,
        first_observed_at=now,
        last_observed_at=now,
    )


def profile(account):
    record()  # establish the tracked brand
    post = Post.objects.create(tweet_id="identity-post", author=account, text="Hello")
    return capture_post_profile_snapshot(
        post=post,
        raw={
            "author_id": account.pk,
            "author_description": "Researcher at DeepSeek",
            "_author_present_fields": ["author_description"],
        },
        references=[BrandReference("deepseek", "DeepSeek", (), ("DeepSeek",))],
    )


def test_new_biography_does_not_use_a_pending_account_match():
    account = Account.objects.create(author_id="pending-match", handle="researcher")
    wrong = Person.objects.create(display_name="A different person")
    link(wrong, account)
    payload = record(account_id=account.pk)
    intake, _ = ingest_record(payload)
    assert intake.person_id is None
    assert intake.eligibility == "needs_review"
    assert intake.payload == payload
    assert not wrong.brand_affiliations.exists()
    assert not wrong.names.exists()


def test_profile_observation_does_not_follow_a_guessed_person_link():
    account = Account.objects.create(author_id="self-observation", handle="researcher")
    wrong = Person.objects.create(display_name="A different person")
    link(wrong, account)
    profile(account)
    assert not wrong.brand_affiliations.exists()
    expected = Person.objects.get(pk=person_id_for_account(account.pk))
    assert expected.brand_affiliations.get().brand_id == "deepseek"


def test_confirmed_account_identity_is_shared_by_profile_and_import():
    account = Account.objects.create(author_id="confirmed-match", handle="researcher")
    person = Person.objects.create(display_name="The researcher")
    link(person, account, "confirmed")
    profile(account)
    intake, _ = ingest_record(record(account_id=account.pk))
    assert intake.person_id == person.pk
    assert Person.objects.count() == 1
    assert person.brand_affiliations.count() == 2


def test_held_intake_can_replay_after_account_confirmation():
    account = Account.objects.create(author_id="held-match", handle="researcher")
    person = Person.objects.create(display_name="The researcher")
    candidate = link(person, account)
    payload = record(account_id=account.pk)
    held, _ = ingest_record(payload)
    assert held.person_id is None
    candidate.resolution_status = "confirmed"
    candidate.save(update_fields=["resolution_status"])
    applied, _ = ingest_record(payload)
    assert applied.pk == held.pk
    assert applied.person_id == person.pk
    assert StaffIntake.objects.count() == 1
    assert person.names.filter(language="zh-Hans").exists()


def test_account_only_intake_uses_the_common_account_identity():
    account = Account.objects.create(author_id="new-account", handle="researcher")
    intake, _ = ingest_record(
        record(
            source_key="account:" + account.pk,
            account_id=account.pk,
            eligibility="db_staff",
            names=[],
            affiliations=[],
        )
    )
    assert intake.person_id == person_id_for_account(account.pk)
    again, created = ingest_record(
        record(
            source_key="account:" + account.pk,
            account_id=account.pk,
            eligibility="db_staff",
            names=[],
            affiliations=[],
        )
    )
    assert not created and again.pk == intake.pk


def test_site_first_then_account_discovery_retains_the_conflict_for_review():
    payload = record()
    site, _ = ingest_record(payload)
    account = Account.objects.create(
        author_id="site-later-account", handle="researcher"
    )
    profile(account)
    held, _ = ingest_record({**payload, "account_id": account.pk})
    assert held.person_id is None and held.eligibility == "needs_review"
    assert Person.objects.count() == 2
    assert StaffIntake.objects.get(pk=site.pk).person_id == site.person_id


def test_multiple_pending_accounts_do_not_pick_the_first_person():
    account = Account.objects.create(author_id="many-pending", handle="researcher")
    for name in ("One", "Two"):
        link(Person.objects.create(display_name=name), account)
    intake, _ = ingest_record(record(account_id=account.pk))
    assert intake.person_id is None and intake.eligibility == "needs_review"
    assert not Person.objects.filter(brand_affiliations__isnull=False).exists()


def test_renamed_handle_keeps_real_account_identity():
    from core.person_identity import subject_person

    account = Account.objects.create(author_id="renamed", handle="oldhandle")
    before = subject_person(
        handle="oldhandle", display_name="Name", source_key="post:1"
    )
    account.handle = "newhandle"
    account.save(update_fields=["handle"])
    after = subject_person(handle="newhandle", display_name="Name", source_key="post:2")
    assert before.pk == after.pk


def test_concurrent_account_import_uses_one_person():
    from concurrent.futures import ThreadPoolExecutor

    from django.db import close_old_connections

    account = Account.objects.create(author_id="concurrent", handle="researcher")
    payload = record(
        source_key="account:concurrent",
        account_id=account.pk,
        eligibility="db_staff",
        affiliations=[],
        names=[],
    )

    def run():
        close_old_connections()
        try:
            return ingest_record(payload)[0].person_id
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: run(), range(2)))
    assert ids[0] == ids[1] == person_id_for_account(account.pk)
    assert Person.objects.count() == StaffIntake.objects.count() == 1
