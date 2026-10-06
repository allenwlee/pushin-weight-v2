from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import Account, OfficialCompanyAccountState
from core.official_company_discovery import (
    coverage,
    enqueue_incremental,
    scan_initial_batch,
)

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


def test_full_inventory_has_no_age_cutoff_and_resumes_without_duplicates():
    for identifier in ["1", "2", "3"]:
        Account.objects.create(author_id=identifier, bio="AI model research lab")
    Account.objects.filter(author_id="1").update(
        first_seen_at=timezone.now() - timedelta(days=900)
    )
    assert scan_initial_batch(limit=2)["enumerated"] == 2
    assert scan_initial_batch(limit=2)["enumerated"] == 3
    assert scan_initial_batch(limit=2)["enumeration_complete"]
    assert OfficialCompanyAccountState.objects.count() == 3
    report = coverage()
    assert report["population"] == 3
    assert report["outcomes"]["pending"] == 3
    assert report["coverage_complete"] is False


def test_no_evidence_is_explicit_and_arrivals_during_initial_are_incremental():
    Account.objects.create(author_id="1")
    scan_initial_batch(limit=1)
    Account.objects.create(author_id="2", bio="We develop our own speech models")
    enqueue_incremental(limit=100)
    assert (
        OfficialCompanyAccountState.objects.get(account_id="1").status == "no_evidence"
    )
    assert OfficialCompanyAccountState.objects.get(account_id="2").status == "pending"


def test_material_profile_change_is_reenqueued_but_followers_are_not():
    account = Account.objects.create(author_id="1", bio="Voice research")
    enqueue_incremental(limit=10)
    state = OfficialCompanyAccountState.objects.get(account=account)
    state.status = "rejected"
    state.save()
    account.followers_count = 100
    account.save()
    enqueue_incremental(limit=10)
    state.refresh_from_db()
    assert state.status == "rejected"
    account.bio = "We develop voice models"
    account.save()
    enqueue_incremental(limit=10)
    state.refresh_from_db()
    assert state.status == "pending"
