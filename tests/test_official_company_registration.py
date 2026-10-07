import pytest

from core.models import (
    Account,
    Brand,
    BrandAccount,
    BrandCompany,
    Company,
    CompanyAccount,
    OfficialCompanyAccountState,
    OfficialCompanyListIntent,
    Role,
)
from core.official_company_accounts import MODEL, POLICY_VERSION, register_account
from x_monitor.config import OfficialCompanyConfig

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


def accepted(identifier="880", name="New Speech Lab"):
    a = Account.objects.create(author_id=identifier, handle="lab" + identifier)
    return OfficialCompanyAccountState.objects.create(
        account=a,
        evidence_hash="a" * 64,
        status="accepted",
        model="owner-attestation",
        policy_version=POLICY_VERSION,
        decision={"outcome": "accepted", "organization_name": name},
    )


@pytest.mark.parametrize("policy", [POLICY_VERSION, "legacy-evaluator"])
def test_model_acceptance_requires_human_review_even_with_registration_enabled(policy):
    state = accepted()
    state.model = MODEL
    state.policy_version = policy
    state.attempts = 3
    state.save()
    old_hash, old_decision = state.evidence_hash, state.decision
    counts = (Brand.objects.count(), Company.objects.count())
    assert register_account(
        state.pk, cfg=OfficialCompanyConfig(enabled=True, registration_enabled=True)
    ) is None
    state.refresh_from_db()
    assert state.status == "review_needed"
    assert state.last_error == "human_review_required"
    assert state.attempts == 3
    assert (state.evidence_hash, state.decision) == (old_hash, old_decision)
    assert (Brand.objects.count(), Company.objects.count()) == counts
    assert not BrandAccount.objects.filter(account=state.account).exists()
    assert not CompanyAccount.objects.filter(account=state.account).exists()
    assert not OfficialCompanyListIntent.objects.exists()


def test_owner_settlement_survives_evaluator_policy_change():
    state = accepted()
    state.model = "owner-attestation"
    state.policy_version = "owner:2026-10-06:preverified-model-labs:v1"
    state.save()
    assert register_account(
        state.pk, cfg=OfficialCompanyConfig(enabled=True, registration_enabled=True)
    )
    state.refresh_from_db()
    assert state.status == "registered"
    assert state.model == "owner-attestation"


def test_registration_is_idempotent_and_creates_no_ownership_or_product_claim():
    state = accepted()
    cfg = OfficialCompanyConfig(enabled=True, registration_enabled=True)
    first = register_account(state.pk, cfg=cfg)
    second = register_account(state.pk, cfg=cfg)
    assert first == second
    assert Brand.objects.count() == Company.objects.count() == 1
    assert BrandAccount.objects.count() == CompanyAccount.objects.count() == 1
    assert BrandCompany.objects.count() == 0
    assert OfficialCompanyListIntent.objects.count() == 1
    state.refresh_from_db()
    assert state.status == "registered"


def test_ambiguous_name_does_not_merge_or_enqueue():
    Brand.objects.create(nickname="new-speech-lab", display_name="New Speech Lab")
    state = accepted()
    assert (
        register_account(
            state.pk, cfg=OfficialCompanyConfig(enabled=True, registration_enabled=True)
        )
        is None
    )
    state.refresh_from_db()
    assert state.status == "review_needed"
    assert not OfficialCompanyListIntent.objects.exists()


def test_nonaccepted_and_disabled_registration_have_no_side_effects():
    state = accepted()
    state.status = "review_needed"
    state.save()
    assert (
        register_account(
            state.pk, cfg=OfficialCompanyConfig(enabled=True, registration_enabled=True)
        )
        is None
    )
    state.status = "accepted"
    state.save()
    assert register_account(state.pk, cfg=OfficialCompanyConfig(enabled=True)) is None
    assert not Brand.objects.exists()


def test_existing_stable_official_edges_are_reused_after_handle_change():
    state = accepted()
    role = Role.objects.create(key="official")
    brand = Brand.objects.create(nickname="established")
    company = Company.objects.create(nickname="established-company")
    BrandAccount.objects.create(brand=brand, account=state.account, role=role)
    CompanyAccount.objects.create(company=company, account=state.account, role=role)
    state.account.handle = "renamed"
    state.account.save()
    assert register_account(
        state.pk, cfg=OfficialCompanyConfig(enabled=True, registration_enabled=True)
    )
    state.refresh_from_db()
    assert (state.registered_brand_id, state.registered_company_id) == (
        brand.pk,
        company.pk,
    )
    assert Brand.objects.count() == Company.objects.count() == 1


def test_intent_failure_rolls_back_all_new_organization_records(monkeypatch):
    from django.db import IntegrityError

    state = accepted()

    def fail(**kwargs):
        raise IntegrityError("simulated race")

    monkeypatch.setattr(OfficialCompanyListIntent.objects, "get_or_create", fail)
    assert (
        register_account(
            state.pk, cfg=OfficialCompanyConfig(enabled=True, registration_enabled=True)
        )
        is None
    )
    assert not Brand.objects.exists()
    assert not Company.objects.exists()
    assert not BrandAccount.objects.exists()
    state.refresh_from_db()
    assert state.status == "review_needed"


def test_confirmed_candidate_with_stable_evidence_reuses_brand():
    from django.utils import timezone

    from core.models import BrandDiscoveryCandidate

    state = accepted()
    brand = Brand.objects.create(nickname="reviewed-lab")
    now = timezone.now()
    BrandDiscoveryCandidate.objects.create(
        candidate_identity="c" * 64,
        observed_name="New Speech Lab",
        verification_status="confirmed",
        reviewed_brand=brand,
        source_identities=[f"official-company-state:{state.pk}"],
        first_observed_at=now,
        last_observed_at=now,
    )
    assert register_account(
        state.pk, cfg=OfficialCompanyConfig(enabled=True, registration_enabled=True)
    )
    state.refresh_from_db()
    assert state.registered_brand_id == brand.pk
    assert Brand.objects.count() == 1


@pytest.mark.parametrize("status", ["verify_needed", "claimed", "pending", "retry_due"])
def test_new_accepted_evidence_resumes_unresolved_intent(status):
    state = accepted()
    cfg = OfficialCompanyConfig(enabled=True, registration_enabled=True)
    register_account(state.pk, cfg=cfg)
    intent = OfficialCompanyListIntent.objects.get(state=state)
    intent.status = status
    intent.claim_token = "obsolete-claim"
    intent.attempts = 4
    intent.save()
    state.status = "accepted"
    state.evidence_hash = "b" * 64
    state.save()
    register_account(state.pk, cfg=cfg)
    intent.refresh_from_db()
    assert intent.evidence_hash == state.evidence_hash
    assert intent.status == "verify_needed"
    assert intent.claim_token == ""
    assert intent.attempts == 0


@pytest.mark.parametrize("status", ["confirmed", "suppressed", "review_needed"])
def test_new_evidence_preserves_settled_or_manually_stopped_intent(status):
    state = accepted()
    cfg = OfficialCompanyConfig(enabled=True, registration_enabled=True)
    register_account(state.pk, cfg=cfg)
    intent = OfficialCompanyListIntent.objects.get(state=state)
    intent.status = status
    intent.save()
    state.status = "accepted"
    state.evidence_hash = "b" * 64
    state.save()
    register_account(state.pk, cfg=cfg)
    intent.refresh_from_db()
    assert intent.status == status
