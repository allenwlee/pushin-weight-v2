import copy
from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import Account, OfficialCompanyAttempt, OfficialCompanyListIntent
from core.official_company_accounts import enqueue_account
from core.official_company_induction import induce_accounts, validate_manifest
from core.official_company_offerings import qualification_decision
from x_monitor.config import OfficialCompanyConfig

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


def manifest(account, state, *, kind="other"):
    citation = {
        "source_id": state.evidence["sources"][0]["id"],
        "quote": state.evidence["sources"][0]["text"],
    }
    screen = {
        "organization_name": "Example Lab",
        "account_presentation": "company_account",
        "identity_rationale": "Own organizational platform",
        "identity_citations": [citation],
        "products": [
            {
                "name": "Example offering",
                "type": kind,
                "contribution": "own_platform_service"
                if kind == "other"
                else "own_" + kind,
                "rationale": "Own developed product",
                "citations": [citation],
            }
        ],
        "uncertainties": [],
    }
    return {
        "approval_reference": "Owner approved frozen cohort 2026-10-08",
        "accounts": [
            {
                "native_x_id": account.author_id,
                "organization_name": "Example Lab",
                "evidence": state.evidence,
                "screen": screen,
            }
        ],
    }


def cfg():
    return OfficialCompanyConfig(
        enabled=True, registration_enabled=True, list_sync_enabled=True
    )


def test_owner_induction_is_native_id_bound_audited_and_idempotent():
    a = Account.objects.create(
        author_id="981001",
        handle="old_handle",
        bio="We are Example Lab and operate our own AI platform.",
    )
    s = enqueue_account(a)
    data = manifest(a, s)
    old_evidence = copy.deepcopy(s.evidence)
    a.handle = "new_handle"
    a.save()
    assert (
        induce_accounts(data, cfg=cfg(), expected_count=1)["accounts"][0]["status"]
        == "registered"
    )
    assert (
        induce_accounts(data, cfg=cfg(), expected_count=1)["accounts"][0]["status"]
        == "registered"
    )
    assert OfficialCompanyAttempt.objects.filter(status="owner_attested").count() == 1
    assert OfficialCompanyListIntent.objects.count() == 1
    s.refresh_from_db()
    assert s.model == "owner-attestation"
    assert s.decision["internal_offering_screen"]["evidence"] == old_evidence
    assert (
        s.decision["internal_offering_screen"]["screen"]["products"][0]["type"]
        == "other"
    )


@pytest.mark.parametrize(
    "bad", ["duplicate", "wrong_provider", "fabricated_quote", "wrong_count"]
)
def test_invalid_manifest_is_rejected_before_any_write(bad):
    a = Account.objects.create(
        author_id="981002", bio="We develop our own AI platform at Example Lab."
    )
    s = enqueue_account(a)
    data = manifest(a, s)
    if bad == "duplicate":
        data["accounts"].append(copy.deepcopy(data["accounts"][0]))
    if bad == "wrong_provider":
        data["accounts"][0]["evidence"]["provider"] = "hf"
    if bad == "fabricated_quote":
        data["accounts"][0]["screen"]["products"][0]["citations"][0]["quote"] = (
            "not present in actual stored evidence"
        )
    with pytest.raises(ValueError):
        validate_manifest(
            data,
            expected_count=2
            if bad == "duplicate"
            else 3
            if bad == "wrong_count"
            else 1,
        )
    assert (
        not OfficialCompanyAttempt.objects.exists()
        and not OfficialCompanyListIntent.objects.exists()
    )


@pytest.mark.parametrize("status", ["suppressed", "claimed"])
def test_owner_cohort_does_not_clear_suppression_or_active_claim(status):
    a = Account.objects.create(
        author_id="981003", bio="We operate an AI platform at Example Lab."
    )
    s = enqueue_account(a)
    s.status = status
    s.claim_expires_at = timezone.now() + timedelta(minutes=1)
    s.save()
    result = induce_accounts(manifest(a, s), cfg=cfg(), expected_count=1)
    assert result["accounts"][0]["status"] in {"missing_or_suppressed", "claim_busy"}
    assert (
        not OfficialCompanyAttempt.objects.exists()
        and not OfficialCompanyListIntent.objects.exists()
    )


def test_multi_offering_screen_is_internal_and_separate_from_personal_identity():
    a = Account.objects.create(
        author_id="981004",
        bio="We are Example Lab. We develop our own agent control runtime and AI cloud platform.",
    )
    s = enqueue_account(a)
    screen = manifest(a, s)["accounts"][0]["screen"]
    second = copy.deepcopy(screen["products"][0])
    second.update(type="harness", contribution="own_harness", name="Agent controls")
    screen["products"].append(second)
    result = qualification_decision(screen, s.evidence)
    assert (
        result["offering_categories"] == ["harness", "other"]
        and result["development_type"] == "harness"
    )
    screen["account_presentation"] = "personal_or_founder"
    assert qualification_decision(screen, s.evidence)["outcome"] == "rejected"


def test_cheap_screen_admits_agent_control_developers_without_model_wording():
    from types import SimpleNamespace

    from core.official_company_candidates import CandidateSignals

    a = SimpleNamespace(
        handle="controllab",
        display_name="Control Lab",
        bio="We build agent harnesses",
        verified_type=None,
    )
    signals = CandidateSignals(a)
    signals.add_profile(
        {
            "entities": {
                "url": {"urls": [{"expanded_url": "https://controllab.example"}]}
            }
        }
    )
    assert signals.priority() == 2
