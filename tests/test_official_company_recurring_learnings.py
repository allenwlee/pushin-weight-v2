"""Exercise discovery learnings through the recurring scheduled harvest caller.

All providers are fakes. These checks use a real isolated PostgreSQL test DB,
without running an initial inventory or making paid/provider requests.
"""

import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from django.test import override_settings

from core.models import (
    Account,
    Brand,
    BrandAccount,
    OfficialCompanyAccountState,
    OfficialCompanyAttempt,
    OfficialCompanyBudget,
    OfficialCompanyListIntent,
    Post,
    Role,
)
from core.official_company_accounts import (
    BLOCKCHAIN_POLICY_VERSION,
    POLICY_VERSION,
    enqueue_account,
)
from monitor.cycle import CycleRunner
from x_monitor.config import OfficialCompanyConfig, load_config

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


def nomination(system, user, model, max_tokens):
    evidence = json.loads(user)
    source = evidence["sources"][0]
    citation = {"source_id": source["id"], "quote": source["text"]}
    return {
        "outcome": "accepted",
        "organization_name": "Unverified Example Lab",
        "model_types": ["speech"],
        "rationale": "Supplied organization and development evidence.",
        "contradictions": [],
        "claims": {
            claim: [citation]
            for claim in ["organization", "official_account", "model_developer"]
        },
        "usage": {"input_tokens": 100, "output_tokens": 100},
    }


@pytest.fixture
def recurring_cycle(monkeypatch, seeded_policy_keywords):
    monkeypatch.setenv("PUSHINWEIGHT_OFFICIAL_COMPANY_HF_SIGNING_KEY", "isolated-recurring-test-key")
    from monitor import cycle as cycle_module
    from monitor.list_membership import MembershipResult
    from scripts.harvest_cost import emit as cost_emit

    class FakeApi:
        timeout_s = 30
        max_retries = 0

        def __init__(self):
            self._request_log = []
            self.queries = []

        def run_search(self, query, **kwargs):
            self.queries.append(query)
            return [], False

    api = FakeApi()
    monkeypatch.setattr(
        cycle_module.TwitterApiClient, "from_env",
        classmethod(lambda cls, purpose: api),
    )
    monkeypatch.setattr(
        cycle_module, "run_due_reconciliation",
        lambda **kwargs: MembershipResult(status="not_due"),
    )
    monkeypatch.setattr(
        "monitor.metrics_refresh.run_metrics_refresh", lambda *args, **kwargs: {},
    )
    monkeypatch.setattr(cost_emit, "finalize_and_persist", lambda *args, **kwargs: None)

    def run(call, *, limit=2, hf_client=None, allow_list_add=False):
        cfg = load_config(Path("config.yaml"))
        cfg.official_company = OfficialCompanyConfig(
            enabled=True, registration_enabled=True, list_sync_enabled=True,
            hf_verification_enabled=hf_client is not None,
            max_calls_per_cycle=limit,
            max_usd_per_cycle=Decimal("0.01"), max_usd_per_day=Decimal(1),
        )
        lists = Mock()
        lists.members.return_value = (set(), True)
        if not allow_list_add:
            lists.add.side_effect = AssertionError("Unsettled nominations cannot join Call A")
        if hf_client is not None:
            from core import official_company_hf

            real_verify = official_company_hf.verify
            monkeypatch.setattr(
                official_company_hf, "verify",
                lambda evidence, decision, **kwargs: real_verify(
                    evidence, decision, client=hf_client, **kwargs,
                ),
            )
        with override_settings(
            X_MONITOR_CYCLE_SKIP_FETCH=False, X_MONITOR_LLM_PAUSE_SECONDS=0,
        ):
            result = CycleRunner(
                cfg=cfg, cycle_kind="scheduled", _official_company_call=call,
                _official_list_client=lists,
            ).run()
        assert result["status"] != "aborted"
        assert len(result["planned_calls"]) == 7
        assert lists.add.called == allow_list_add
        return result["official_company_discovery"]

    return run


@pytest.mark.parametrize("index", range(3))
def test_recurring_discovery_admits_each_settled_pattern_from_one_post(
    recurring_cycle, index,
):
    # Substitute native IDs so the three owner attestations cannot shortcut
    # discovery. No badge or minimum post count may exclude these patterns.
    example = json.loads(
        Path("tests/fixtures/official_company_accounts.json").read_text()
    )[index]["evidence"]
    account = Account.objects.create(
        author_id=str(97500 + index), handle=example["handle"],
        display_name=example["display_name"],
    )
    bios = [s["text"] for s in example["sources"] if s["id"].endswith(":bio")]
    urls = [s["text"] for s in example["sources"] if ":bio:url:" in s["id"]]
    Post.objects.create(
        tweet_id=str(97600 + index), author=account, text="One research update",
        author_profile_bio={
            "description": " ".join(bios),
            "entities": {"url": {"urls": [{"expanded_url": u} for u in urls]}},
        },
    )
    call = Mock(side_effect=nomination)
    result = recurring_cycle(call)
    state = OfficialCompanyAccountState.objects.get(account=account)
    assert result["attempted"] == 1 and call.call_count == 1
    assert state.candidate_priority == 2 and state.initial_scan_id is None
    assert state.model != "owner-attestation"
    assert state.status == "review_needed"
    assert not OfficialCompanyListIntent.objects.exists()


@pytest.mark.parametrize("kind", ["model", "agent", "harness"])
def test_recurring_caller_uses_amended_product_rule_without_hf(recurring_cycle, kind):
    a = Account.objects.create(
        author_id="97811", handle="new_company", verified_type="business",
        bio=f"We are New Company. We develop our own {kind}; our speech model is closed-weight with no HF page.",
    )

    def accepted(system, user, model, max_tokens):
        assert "An AI model: proprietary/closed-weight" in system
        assert "No HF page, public weights" in system
        assert "Their own proprietary harness" in system
        source = json.loads(user)["sources"][0]
        citation = {"source_id": source["id"], "quote": source["text"]}
        return {
            "outcome": "accepted", "organization_name": "New Company", "development_type": kind,
            "model_types": ["speech"] if kind == "model" else [], "rationale": "First-party own development",
            "contradictions": [], "claims": {key: [citation] for key in ["organization", "official_account", "product_developer"]},
        }

    result = recurring_cycle(accepted)
    state = OfficialCompanyAccountState.objects.get(account=a)
    assert result["attempted"] == 1 and state.decision["development_type"] == kind
    assert state.status == "review_needed" and not OfficialCompanyListIntent.objects.exists()
    assert state.attempt_records.get().policy_version == POLICY_VERSION


def test_gold_alone_enters_recurring_queue_before_older_lower_priority_retry(recurring_cycle):
    lower = Account.objects.create(author_id="97510", bio="We develop speech models")
    Post.objects.create(
        tweet_id="97610", author=lower, text="Research update",
        author_profile_bio={
            "description": lower.bio,
            "entities": {"url": {"urls": [{"expanded_url": "https://example.ai"}]}},
        },
    )
    retry = enqueue_account(lower, candidate_priority=2)
    retry.status = "retry_due"
    retry.save()
    gold = Account.objects.create(author_id="97511", verified_type="Business")
    observed = []

    def call(system, user, model, max_tokens):
        observed.append(json.loads(user)["external_identifier"])
        return {
            "outcome": "review_needed", "organization_name": None,
            "model_types": [], "rationale": "Badge alone is not ownership proof.",
            "contradictions": [], "claims": {},
            "usage": {"input_tokens": 100, "output_tokens": 100},
        }

    assert recurring_cycle(call, limit=1)["attempted"] == 1
    assert observed == [gold.author_id]
    assert OfficialCompanyAccountState.objects.get(account=gold).candidate_priority == 1
    retry.refresh_from_db()
    assert retry.status == "retry_due" and retry.attempts == 0


def test_recurring_known_multibrand_account_avoids_paid_rediscovery(recurring_cycle):
    account = Account.objects.create(
        author_id="97520", handle="known_ai", verified_type="Business",
        bio="We develop AI models.",
    )
    role, _ = Role.objects.get_or_create(key="official")
    for nickname in ["known-vision", "known-speech"]:
        brand = Brand.objects.create(nickname=nickname)
        BrandAccount.objects.create(brand=brand, account=account, role=role)
    call = Mock(side_effect=AssertionError("Existing official edges must be reused"))
    result = recurring_cycle(call)
    state = OfficialCompanyAccountState.objects.get(account=account)
    assert result["attempted"] == 0
    assert state.last_error == "already_tracked" and state.attempts == 0
    assert BrandAccount.objects.filter(account=account).count() == 2
    assert not OfficialCompanyAttempt.objects.exists()
    assert not OfficialCompanyBudget.objects.exists()
    assert not OfficialCompanyListIntent.objects.exists()
    call.assert_not_called()


@pytest.mark.parametrize(
    "bio,policy",
    [
        ("We develop our own speech models.", POLICY_VERSION),
        ("We develop AI models for blockchain and web3.", BLOCKCHAIN_POLICY_VERSION),
    ],
)
def test_recurring_evaluation_uses_conditional_hurdle_and_keeps_unverified_positives_held(
    recurring_cycle, bio, policy,
):
    account = Account.objects.create(author_id="97530", bio=bio, verified_type="Business")
    call = Mock(side_effect=nomination)
    result = recurring_cycle(call)
    state = OfficialCompanyAccountState.objects.get(account=account)
    attempt = state.attempt_records.get()
    assert result["attempted"] == 1 and result["registered"] == 0
    assert state.policy_version == attempt.policy_version == policy
    assert ("higher technical-evidence hurdle" in call.call_args.args[0]) == (policy == BLOCKCHAIN_POLICY_VERSION)
    assert state.status == "review_needed" and state.last_error == "human_review_required"
    assert attempt.decision["outcome"] == "accepted"
    assert not BrandAccount.objects.filter(account=account).exists()
    assert not OfficialCompanyListIntent.objects.exists()


def test_unchanged_recurring_evidence_does_not_repeat_paid_evaluation(recurring_cycle):
    account = Account.objects.create(
        author_id="97540", bio="We develop our own speech models.", verified_type="Business",
    )
    call = Mock(side_effect=nomination)
    assert recurring_cycle(call)["attempted"] == 1
    state = OfficialCompanyAccountState.objects.get(account=account)
    original = (state.evidence_hash, state.decision)
    account.followers_count = 1234
    account.save()
    assert recurring_cycle(call)["attempted"] == 0
    state.refresh_from_db()
    assert call.call_count == 1 and state.attempt_records.count() == 1
    assert (state.evidence_hash, state.decision) == original


@pytest.mark.parametrize(
    "case", ["passed", "mirror", "unverified", "wrong_account", "unavailable", "empty"],
)
def test_recurring_hf_proof_controls_automatic_registration_and_call_a_list_intent(
    recurring_cycle, case,
):
    from core.models import CompanyAccount
    from core.official_company_hf import approved

    account = Account.objects.create(
        author_id="97550", handle="examplelab", verified_type="Business",
        bio="We are Example Lab. We develop our own speech models.",
    )
    sha = "a" * 40
    requests = []

    def transport(request):
        # HF verification traverses its real public client/parser/receipt code;
        # responses are isolated fixtures, not claims about a real publisher.
        assert request.url.host == "huggingface.co"
        requests.append(request)
        path = request.url.path
        if path == "/api/quicksearch":
            return httpx.Response(200, json={"orgs": [{"name": "examplelab"}]})
        if path == "/api/organizations/examplelab/overview":
            return httpx.Response(200, json={
                "name": "examplelab", "fullname": "Example Lab", "isVerified": case != "unverified",
            })
        if path == "/examplelab":
            handle = "another_account" if case == "wrong_account" else account.handle
            return httpx.Response(200, text=(
                f'<a class="leading-snug" href="https://x.com/{handle}">X</a>'
                '<a class="leading-snug" href="https://example.ai">Company</a>'
            ))
        if path == "/api/models":
            return httpx.Response(200, json=[] if case == "empty" else [{
                "id": "examplelab/Speech-1", "sha": sha, "private": False, "tags": [],
                "siblings": [{"rfilename": "model.safetensors"}],
            }])
        if path == f"/examplelab/Speech-1/raw/{sha}/README.md":
            if case == "unavailable":
                return httpx.Response(503)
            developer = "Meta" if case == "mirror" else "Example Lab"
            return httpx.Response(200, text=f"Speech-1 was developed by {developer}.")
        raise AssertionError(f"Unexpected fixture endpoint: {path}")

    def call(*args):
        response = nomination(*args)
        response["organization_name"] = "Example Lab"
        return response

    passed = case == "passed"
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        result = recurring_cycle(call, hf_client=client, allow_list_add=passed)
    state = OfficialCompanyAccountState.objects.get(account=account)
    assert result["hf_verification"] == {"checked": 1, "approved": int(passed)}
    assert result["registered"] == int(passed)
    assert approved(state) == passed
    assert state.attempt_records.get().decision["outcome"] == "accepted"
    assert CompanyAccount.objects.filter(account=account).exists() == passed
    assert BrandAccount.objects.filter(account=account).exists() == passed
    assert OfficialCompanyListIntent.objects.filter(account=account).exists() == passed
    assert state.status == ("registered" if passed else "review_needed")
    assert len(requests) <= 12
    if passed:
        intent = OfficialCompanyListIntent.objects.get(account=account)
        assert intent.status == "confirmed"
        assert state.decision["hf_verification"]["sha"] == sha
