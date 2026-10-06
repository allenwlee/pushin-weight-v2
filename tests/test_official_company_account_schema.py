import pytest
from django.db import IntegrityError, transaction

from core.models import (
    Account,
    OfficialCompanyAccountState,
    OfficialCompanyAttempt,
    OfficialCompanyBudget,
)

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


def test_work_state_is_unique_per_account_and_attempt_revision_is_immutable():
    account = Account.objects.create(author_id="991")
    state = OfficialCompanyAccountState.objects.create(
        account=account, evidence_hash="a" * 64
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        OfficialCompanyAccountState.objects.create(
            account=account, evidence_hash="b" * 64
        )
    attempt = OfficialCompanyAttempt.objects.create(
        state=state,
        evidence_hash=state.evidence_hash,
        claim_token="test",
        model="test",
        policy_version="test",
        reserved_usd="0.01",
    )
    state.evidence_hash = "b" * 64
    state.save()
    attempt.refresh_from_db()
    assert attempt.evidence_hash == "a" * 64


def test_funding_reservation_cannot_be_negative():
    with pytest.raises(IntegrityError), transaction.atomic():
        OfficialCompanyBudget.objects.create(key="test", reserved_usd="-0.01")


def configured():
    from x_monitor.config import OfficialCompanyConfig

    return OfficialCompanyConfig(
        enabled=True,
        max_usd_per_cycle="1",
        max_usd_per_day="2",
        initial_scan_max_usd="2",
    )


def state_for(identifier="992"):
    from core.official_company_accounts import enqueue_account

    account = Account.objects.create(
        author_id=identifier, handle="lab" + identifier, bio="We release audio models."
    )
    return enqueue_account(account)


def test_claim_reserves_once_and_stale_completion_cannot_replace_evidence():
    from core.official_company_accounts import claim_account, complete_attempt

    state = state_for()
    cfg = configured()
    attempt = claim_account(state.pk, cfg=cfg, budget_scope="cycle")
    assert attempt is not None
    assert claim_account(state.pk, cfg=cfg, budget_scope="cycle") is None
    assert OfficialCompanyAttempt.objects.count() == 1
    state.refresh_from_db()
    state.evidence_hash = "f" * 64
    state.claim_token = "new"
    state.save()
    assert not complete_attempt(
        attempt.pk,
        cfg=cfg,
        response={
            "outcome": "rejected",
            "rationale": "Individual",
            "contradictions": [],
            "usage": {"input_tokens": 200, "output_tokens": 20},
        },
    )
    state.refresh_from_db()
    assert state.claim_token == "new"
    attempt.refresh_from_db()
    assert attempt.actual_usd is not None
    assert all(b.reserved_usd == 0 for b in OfficialCompanyBudget.objects.all())


def test_zero_budget_sends_nothing_and_unknown_timeout_retains_reservation():
    from core.official_company_accounts import evaluate_account
    from x_monitor.config import OfficialCompanyConfig

    state = state_for("993")
    calls = []

    def call(*args):
        calls.append(args)
        raise TimeoutError("provider timeout")

    assert not evaluate_account(
        state.pk,
        cfg=OfficialCompanyConfig(enabled=True),
        call=call,
        budget_scope="zero",
    )
    assert calls == []
    assert evaluate_account(
        state.pk, cfg=configured(), call=call, budget_scope="funded"
    )
    state.refresh_from_db()
    assert state.status == "retry_due"
    assert len(calls) == 1
    assert all(b.reserved_usd > 0 for b in OfficialCompanyBudget.objects.all())


def test_invalid_citation_goes_to_review_and_cannot_register():
    from core.official_company_accounts import evaluate_account

    state = state_for("994")
    assert evaluate_account(
        state.pk,
        cfg=configured(),
        call=lambda *args: {
            "outcome": "accepted",
            "rationale": "Guess",
            "contradictions": [],
        },
        budget_scope="invalid",
    )
    state.refresh_from_db()
    assert state.status == "review_needed"
    assert state.registered_brand_id is None


def test_concurrent_claims_share_one_funded_attempt():
    from concurrent.futures import ThreadPoolExecutor

    from django.db import close_old_connections

    from core.official_company_accounts import claim_account

    state = state_for("995")
    cfg = configured()

    def claim():
        close_old_connections()
        try:
            attempt = claim_account(state.pk, cfg=cfg, budget_scope="race")
            return attempt.pk if attempt else None
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: claim(), range(2)))
    assert sum(x is not None for x in results) == 1
    assert OfficialCompanyAttempt.objects.count() == 1


def test_owner_settlement_is_versioned_once_and_not_a_classifier_handle_rule():
    from core.official_company_accounts import enqueue_account

    account = Account.objects.create(
        author_id="1800594921704898560",
        handle="renamed_reflection",
        bio="Make intelligence open",
    )
    state = enqueue_account(account)
    assert state.status == "accepted" and state.model == "owner-attestation"
    assert state.attempt_records.get().status == "owner_attested"
    enqueue_account(account)
    assert state.attempt_records.count() == 1
    account.bio = "Changed evidence"
    account.save()
    changed = enqueue_account(account)
    assert changed.status == "pending"
    assert not any(s["id"].startswith("owner:") for s in changed.evidence["sources"])


def test_model_auth_failure_blocks_other_accounts_until_credential_revision():
    from decimal import Decimal

    from core.official_company_accounts import enqueue_account, evaluate_account
    from x_monitor.config import OfficialCompanyConfig
    from x_monitor.deepinfra import DeepInfraPermanentError

    cfg = OfficialCompanyConfig(
        enabled=True, max_usd_per_cycle=Decimal(1), max_usd_per_day=Decimal(1)
    )
    first = enqueue_account(Account.objects.create(author_id="9001", bio="A model lab"))
    second = enqueue_account(
        Account.objects.create(author_id="9002", bio="Another model lab")
    )
    attempts = []

    def fail(*args):
        attempts.append(args)
        raise DeepInfraPermanentError("deepinfra_http_status_401")

    fail.credential_revision = "a" * 64
    assert evaluate_account(first.pk, cfg=cfg, call=fail, budget_scope="auth")
    assert not evaluate_account(second.pk, cfg=cfg, call=fail, budget_scope="auth")
    assert len(attempts) == 1
    fail.credential_revision = "b" * 64
    assert evaluate_account(second.pk, cfg=cfg, call=fail, budget_scope="repaired")
    assert len(attempts) == 2
