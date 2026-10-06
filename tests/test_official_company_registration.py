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
from core.official_company_accounts import register_account
from x_monitor.config import OfficialCompanyConfig

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


def accepted(identifier="880", name="New Speech Lab"):
    a = Account.objects.create(author_id=identifier, handle="lab" + identifier)
    return OfficialCompanyAccountState.objects.create(
        account=a,
        evidence_hash="a" * 64,
        status="accepted",
        decision={"outcome": "accepted", "organization_name": name},
    )


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
