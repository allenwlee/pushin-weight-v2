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


def test_unchanged_evidence_preserves_queue_priority_and_scan_can_attach():
    from core.models import OfficialCompanyScan
    from core.official_company_accounts import enqueue_account

    account = Account.objects.create(author_id="1", bio="We develop speech models")
    state = enqueue_account(account)
    previous = state.updated_at
    scan = OfficialCompanyScan.objects.create(key="attachment-test")
    again = enqueue_account(account, initial_scan=scan)
    assert again.updated_at == previous
    assert again.initial_scan_id == scan.pk
    again.refresh_from_db()
    assert again.initial_scan_id == scan.pk
    assert again.updated_at == previous


@pytest.mark.parametrize("limit", [1, 2, 3, 4, 7])
def test_incremental_account_work_never_exceeds_requested_limit(limit, monkeypatch):
    from core import official_company_discovery as discovery
    from core.models import OfficialCompanyScan

    for key in ["account-observations", "post-observations", "profile-observations"]:
        OfficialCompanyScan.objects.create(
            key=key, started_at=timezone.now() - timedelta(days=1)
        )
    for i in range(10):
        Account.objects.create(author_id=str(i + 1), bio="AI lab")
    calls = []
    original = discovery.enqueue_account

    def observe(account, **kwargs):
        calls.append(account.pk)
        return original(account, **kwargs)

    monkeypatch.setattr(discovery, "enqueue_account", observe)
    enqueue_incremental(limit=limit)
    assert 0 < len(calls) <= limit


def test_retry_and_new_evidence_each_receive_a_slot(monkeypatch):
    from core import official_company_discovery as discovery
    from core.official_company_accounts import enqueue_account
    from x_monitor.config import OfficialCompanyConfig

    states = []
    for i, status in enumerate(["pending", "retry_due", "retry_due"]):
        account = Account.objects.create(author_id=str(i + 1), bio="AI model lab")
        state = enqueue_account(account)
        state.status = status
        state.save()
        states.append(state)
    calls = []
    monkeypatch.setattr(
        discovery, "evaluate_account", lambda pk, **kwargs: calls.append(pk) or True
    )
    discovery.drain_accounts(
        cfg=OfficialCompanyConfig(enabled=True), call=object(), limit=2,
        budget_scope="fairness-test",
    )
    assert calls == [states[1].pk, states[0].pk]
