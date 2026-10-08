import io
import json
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.core.management import call_command
from django.utils import timezone

from core.models import Account, OfficialCompanyAccountState, OfficialCompanyAttempt
from core.official_company_accounts import BLOCKCHAIN_POLICY_VERSION, POLICY_VERSION
from core.official_company_candidates import CANDIDATE_POLICY
from core.official_company_requalification import cohort_report
from x_monitor.config import OfficialCompanyConfig

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


@pytest.fixture
def cohort_command(monkeypatch, tmp_path):
    from monitor.management.commands import official_co_account_extraction as command

    cfg = OfficialCompanyConfig(enabled=True, initial_scan_max_usd=Decimal(1))
    monkeypatch.setattr(command, "load_config", lambda path: SimpleNamespace(official_company=cfg))
    path = tmp_path / "cohort.json"

    def run(call, manifest=None, *, limit=20):
        monkeypatch.setattr(command, "build_discovery_call", lambda config: call)
        kwargs = {"limit": limit, "seconds": 120}
        if manifest is not None:
            path.write_text(json.dumps(manifest))
            kwargs["cohort_manifest"] = str(path)
        output = io.StringIO()
        call_command("official_co_account_extraction", "requalify", stdout=output, **kwargs)
        return json.loads(output.getvalue().splitlines()[-1])

    return run


def state(number, kind="agent", **kwargs):
    quote = f"We are Example Company {number}. We develop our own {kind} using third-party models."
    return OfficialCompanyAccountState.objects.create(
        account=Account.objects.create(author_id=str(number), handle=f"company_{number}"),
        evidence_hash="a" * 64, candidate_priority=1, candidate_policy_version=CANDIDATE_POLICY,
        evidence={"identity": "a" * 64, "sources": [{"id": "post:1", "text": quote}], "domains": []},
        status=kwargs.pop("status", "review_needed"), policy_version="official-model-developer-v2",
        decision={"outcome": "review_needed", "rationale": "Old narrower result"}, **kwargs,
    )


def manifest(states):
    return {"frozen_at": timezone.now().isoformat(), "failed": [], "review": [{
        "id": s.pk, "account_id": str(s.account_id), "evidence_hash": s.evidence_hash,
        "decision": s.decision,
    } for s in states]}


def nomination(system, user, model, max_tokens):
    evidence = json.loads(user)
    quote = evidence["sources"][0]["text"]
    kind = "harness" if "harness" in quote else "agent"
    assert "harness" in system and "third-party" in system
    citation = {"source_id": "post:1", "quote": quote}
    return {
        "organization_name": "Example Company", "account_presentation": "company_account",
        "identity_rationale": "Supplied own-product development evidence", "identity_citations": [citation],
        "products": [{"name": "Own product", "type": kind, "contribution": "own_" + kind,
                      "rationale": "Developed product", "citations": [citation]}],
        "uncertainties": [], "usage": {"input_tokens": 100, "output_tokens": 100},
    }



def test_command_rerun_has_fixed_population_and_preserves_old_results(cohort_command):
    a, b, outside = state(99101), state(99102, "harness"), state(99103)
    old = OfficialCompanyAttempt.objects.create(
        state=a, evidence_hash=a.evidence_hash, claim_token="original-attempt",
        model="old", policy_version="official-model-developer-v2", status="completed",
        decision=a.decision, reserved_usd=0,
    )
    call = Mock(side_effect=nomination)
    cohort = manifest([a, b])
    result = cohort_command(call, cohort, limit=1)
    assert result["population"] == 2 and result["completed"] == 1
    assert result["qualified"] == result["newly_qualified"] == 1
    result = cohort_command(call, cohort, limit=1)
    assert result["complete"] and result["qualified"] == 2
    assert result["agent"] == result["harness"] == 1
    assert Decimal(result["spent_usd"]) > 0
    assert cohort_command(call, cohort)["attempted"] == 0 and call.call_count == 2
    old.refresh_from_db()
    assert old.decision == {"outcome": "review_needed", "rationale": "Old narrower result"}
    outside.refresh_from_db()
    assert outside.status == "review_needed" and not outside.attempt_records.exists()
    a.refresh_from_db()
    assert a.status == "review_needed" and a.last_error == "human_review_required"
    assert a.attempt_records.filter(policy_version=POLICY_VERSION, status="completed").count() == 1


def test_cohort_failure_and_protected_rows_remain_distinct(cohort_command):
    failed, suppressed, settled, changed = [state(99201 + n) for n in range(4)]
    cohort = manifest([failed, suppressed, settled, changed])
    suppressed.status = "suppressed"
    suppressed.save()
    settled.status = "registered"
    settled.save()
    changed.evidence_hash = "b" * 64
    changed.save()
    result = cohort_command(Mock(return_value={"invalid": True}), cohort)
    assert result["complete"] and result["failed"] == 1 and result["excluded"] == 3
    assert result["qualified"] == 0
    assert cohort_report()["population"] == 4
    with pytest.raises(ValueError, match="mismatch"):
        cohort_command(Mock(), manifest([failed]))


def test_web3_agent_is_evaluated_for_actual_agent_contribution(cohort_command):
    a = state(99301)
    a.evidence["sources"][0]["text"] += " Blockchain and Web3 are part of our product."
    a.save()
    call = Mock(side_effect=nomination)
    result = cohort_command(call, manifest([a]))
    assert result["agent"] == 1
    assert a.attempt_records.get().policy_version == BLOCKCHAIN_POLICY_VERSION
    assert "higher technical-evidence hurdle" in call.call_args.args[0]


def test_cohort_retry_preserves_unknown_spend_and_prior_positive_baseline(cohort_command):
    a = state(99401)
    a.decision = {"outcome": "accepted"}
    a.save()
    cohort = manifest([a])
    call = Mock(side_effect=TimeoutError())
    result = cohort_command(call, cohort)
    assert result["retry_pending"] == 1 and not result["complete"]
    assert Decimal(result["reserved_usd"]) > 0
    assert cohort_command(call)["attempted"] == 0 and call.call_count == 1
    a.refresh_from_db()
    a.next_attempt_at = timezone.now() - timedelta(seconds=1)
    a.save()
    result = cohort_command(Mock(side_effect=nomination))
    assert result["qualified"] == 1 and result["newly_qualified"] == 0
    assert result["complete"] and Decimal(result["reserved_usd"]) > 0
    assert a.attempt_records.count() == 2


def test_active_lease_and_changed_queued_evidence_cannot_dispatch(cohort_command):
    a = state(99501, status="claimed", claim_token="another-writer",
              claim_expires_at=timezone.now() + timedelta(minutes=5))
    call = Mock(side_effect=nomination)
    result = cohort_command(call, manifest([a]))
    assert result["pending"] == 1 and call.call_count == 0
    a.refresh_from_db()
    assert a.claim_token == "another-writer"
    a.claim_expires_at = timezone.now() - timedelta(seconds=1)
    a.save()
    result = cohort_command(Mock(side_effect=TimeoutError()))
    assert result["retry_pending"] == 1
    a.refresh_from_db()
    a.evidence_hash = "b" * 64
    a.next_attempt_at = timezone.now() - timedelta(seconds=1)
    a.save()
    result = cohort_command(call)
    assert result["complete"] and result["excluded"] == 1 and call.call_count == 0


def test_registered_hf_verification_does_not_remain_a_failed_finding(cohort_command):
    a = state(99601)
    result = cohort_command(Mock(return_value={"invalid": True}), manifest([a]))
    assert result["failed"] == 1
    a.refresh_from_db()
    a.status = "registered"
    a.decision = {"outcome": "accepted", "organization_name": "Example Company", "hf_verification": {
        "version": "official-hf-model-developer-v3", "outcome": "passed",
        "evidence_hash": a.evidence_hash, "observed_at": timezone.now().isoformat(),
    }}
    a.save()
    result = cohort_report()
    assert result["qualified"] == result["newly_qualified"] == result["hf_verified"] == 1
    assert result["failed"] == 0 and result["model"] == 1
    assert a.attempt_records.get().status == "failed"


def test_envelope_block_finishes_without_a_paid_attempt(cohort_command):
    a = state(99701)
    a.evidence["sources"][0]["text"] = "x" * 300_000
    a.save()
    call = Mock()
    result = cohort_command(call, manifest([a]))
    assert result["complete"] and result["failed"] == 1 and result["qualified"] == 0
    assert call.call_count == 0 and not a.attempt_records.exists()


def test_completed_v3_cohort_report_does_not_follow_v4_or_owner_induction():
    from core.models import OfficialCompanyScan
    from core.official_company_requalification import COHORT_KEY

    a = state(981098)
    started = timezone.now() - timedelta(minutes=1)
    members = [{"state_id": a.pk, "account_id": str(a.account_id), "evidence_hash": a.evidence_hash, "baseline_outcome": "review_needed"}]
    OfficialCompanyScan.objects.create(key=COHORT_KEY, started_at=started, population=1,
        cursor=json.dumps({"identity": "frozen", "policy_version": "official-ai-product-developer-v3", "members": members, "queued": [a.pk], "excluded": {}}))
    old = {"outcome": "accepted", "organization_name": "Example Company", "development_type": "agent"}
    OfficialCompanyAttempt.objects.create(state=a, evidence_hash=a.evidence_hash, claim_token="v3", model="old", policy_version="official-ai-product-developer-v3", status="completed", decision=old, reserved_usd=0, actual_usd=0)
    before = cohort_report()
    OfficialCompanyAttempt.objects.create(state=a, evidence_hash=a.evidence_hash, claim_token="v4", model="new", policy_version=POLICY_VERSION, status="completed", decision={"outcome": "rejected"}, reserved_usd=0, actual_usd=0)
    OfficialCompanyAttempt.objects.create(state=a, evidence_hash=a.evidence_hash, claim_token="owner", model="owner-attestation", policy_version="owner-cohort:test", status="owner_attested", decision={"outcome": "accepted"}, reserved_usd=0, actual_usd=0)
    a.status = "registered"
    a.model = "owner-attestation"
    a.save()
    assert cohort_report() == before
    assert before["qualified"] == 1 and before["agent"] == 1


def test_new_offering_cohort_counts_own_services(cohort_command):
    a = state(99701, "AI platform service")
    def own_service(*args):
        response = nomination(*args)
        response["products"][0].update(type="other", contribution="own_platform_service")
        return response
    result = cohort_command(Mock(side_effect=own_service), manifest([a]))
    assert result["complete"] and result["qualified"] == result["other"] == 1
