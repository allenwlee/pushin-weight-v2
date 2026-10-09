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


def test_existing_official_brand_link_skips_paid_discovery_without_list_writes():
    from core.models import (
        Brand,
        BrandAccount,
        OfficialCompanyAttempt,
        OfficialCompanyListIntent,
        Role,
    )
    from core.official_company_accounts import enqueue_account, evaluate_account
    from x_monitor.config import OfficialCompanyConfig

    a = Account.objects.create(author_id="1034844617261248512", handle="AIatMeta", bio="Official AI research", verified_type="Business")
    brand = Brand.objects.create(nickname="llama")
    role, _ = Role.objects.get_or_create(key="official")
    BrandAccount.objects.create(brand=brand, account=a, role=role)
    brand_count = Brand.objects.count()
    state = enqueue_account(a)
    calls = []
    assert not evaluate_account(state.pk, cfg=OfficialCompanyConfig(enabled=True), call=lambda *args: calls.append(args), budget_scope="known-brand")
    state.refresh_from_db()
    assert state.status == "review_needed" and state.last_error == "already_tracked"
    assert state.attempts == 0 and calls == []
    assert OfficialCompanyAttempt.objects.count() == 0
    assert OfficialCompanyListIntent.objects.count() == 0
    assert Brand.objects.count() == brand_count


def test_blockchain_prompt_and_provenance_follow_actual_call():
    from core.models import OfficialCompanyAttempt, OfficialCompanyBudget
    from core.official_company_accounts import (
        BLOCKCHAIN_POLICY_VERSION,
        enqueue_account,
        evaluate_account,
        evaluator_prompt,
    )
    from x_monitor.config import OfficialCompanyConfig

    a = Account.objects.create(author_id="944255537121656833", handle="iotex_io", bio="The blockchain platform for Real-World AI.", verified_type="Business")
    state = enqueue_account(a)
    OfficialCompanyBudget.objects.create(key="initial-total")
    calls = []

    def call(*args):
        calls.append(args)
        return {"outcome": "review_needed", "organization_name": "IoTeX", "model_types": [], "rationale": "No direct model development evidence.", "contradictions": [], "claims": {}, "usage": {"input_tokens": 10, "output_tokens": 10}}

    assert evaluate_account(state.pk, cfg=OfficialCompanyConfig(enabled=True, initial_scan_max_usd=1), call=call, budget_scope="risk", initial=True)
    attempt = OfficialCompanyAttempt.objects.get(state=state)
    state.refresh_from_db()
    assert calls[0][0] == evaluator_prompt(state.evidence)[0]
    assert "higher technical-evidence hurdle" in calls[0][0]
    assert attempt.policy_version == state.policy_version == BLOCKCHAIN_POLICY_VERSION
    assert state.status == "review_needed"


def test_full_inventory_has_no_age_cutoff_and_resumes_without_duplicates():
    for identifier in ["1", "2", "3"]:
        Account.objects.create(
            author_id=identifier, bio="AI model research lab", verified_type="Business"
        )
    Account.objects.filter(author_id="1").update(
        first_seen_at=timezone.now() - timedelta(days=900)
    )
    while not coverage()["gold_staging_complete"]:
        scan_initial_batch(limit=2)
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
    Account.objects.create(
        author_id="2", bio="We develop our own speech models", verified_type="Business"
    )
    enqueue_incremental(limit=100)
    assert not OfficialCompanyAccountState.objects.filter(account__author_id="1").exists()
    assert coverage()["deferred"] == 1
    assert OfficialCompanyAccountState.objects.get(account__author_id="2").status == "pending"


def test_material_profile_change_is_reenqueued_but_followers_are_not():
    account = Account.objects.create(
        author_id="1", bio="Voice research", verified_type="Business"
    )
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
        Account.objects.create(
            author_id=str(i + 1), bio="AI lab", verified_type="Business"
        )
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
        cfg=OfficialCompanyConfig(enabled=True),
        call=object(),
        limit=2,
        budget_scope="fairness-test",
    )
    assert calls == [states[1].pk, states[0].pk]


def test_scheduled_lane_filters_out_commentators_without_model_calls(monkeypatch):
    from core.official_company_discovery import run_discovery_lane
    from x_monitor.config import OfficialCompanyConfig

    Account.objects.create(
        author_id="9001", handle="model_fan", bio="I discuss AI models"
    )
    calls = []
    from decimal import Decimal

    cfg = OfficialCompanyConfig(
        enabled=True, max_usd_per_cycle=Decimal(1), max_usd_per_day=Decimal(1)
    )
    result = run_discovery_lane(
        cfg=cfg, run_id="filtered", call=lambda **kw: calls.append(kw)
    )
    assert result["attempted"] == 0
    assert calls == []
    assert not OfficialCompanyAccountState.objects.filter(status="pending").exists()


def test_gold_without_bio_or_posts_is_candidate_and_beats_old_retry(monkeypatch):
    from core import official_company_discovery as discovery
    from core.official_company_accounts import enqueue_account
    from x_monitor.config import OfficialCompanyConfig

    older = enqueue_account(
        Account.objects.create(author_id="8001", bio="AI model research")
    )
    older.status = "retry_due"
    older.save()
    gold = Account.objects.create(
        author_id="8002",
        verified_type="Business",
        verified=False,
        is_blue_verified=False,
    )
    discovery.enqueue_incremental()
    gold_state = OfficialCompanyAccountState.objects.get(account=gold)
    assert gold_state.status == "pending"
    assert gold_state.candidate_priority == 1
    calls = []
    monkeypatch.setattr(
        discovery, "evaluate_account", lambda pk, **kw: calls.append(pk) or True
    )
    discovery.drain_accounts(
        cfg=OfficialCompanyConfig(enabled=True),
        call=object(),
        limit=2,
        budget_scope="gold-first",
    )
    assert calls[0] == gold_state.pk


def test_nested_bio_single_post_is_candidate_and_reentry_is_not_rejection():
    from core.models import Post
    from core.official_company_discovery import enqueue_incremental

    account = Account.objects.create(
        author_id="8003", handle="small_lab", display_name="Small Lab"
    )
    enqueue_incremental()
    assert not OfficialCompanyAccountState.objects.filter(account=account).exists()
    Post.objects.create(
        tweet_id="8004",
        author=account,
        text="One research update",
        author_profile_bio={
            "description": "We build specialized speech models",
            "entities": {
                "url": {"urls": [{"expanded_url": "https://small-lab.example"}]}
            },
        },
    )
    enqueue_incremental()
    state = OfficialCompanyAccountState.objects.get(account=account)
    assert state.candidate_priority == 2
    assert state.status == "pending"


def test_legacy_unscreened_states_cannot_spend_and_nonmatches_are_deferred():
    from decimal import Decimal

    from core.official_company_accounts import claim_account
    from core.official_company_candidates import CANDIDATE_POLICY
    from x_monitor.config import OfficialCompanyConfig

    account = Account.objects.create(author_id="9100", bio="I discuss AI models")
    state = OfficialCompanyAccountState.objects.create(
        account=account, evidence_hash="old", evidence={"sources": []}
    )
    assert (
        claim_account(
            state.pk,
            cfg=OfficialCompanyConfig(
                enabled=True,
                max_usd_per_cycle=Decimal(1),
                max_usd_per_day=Decimal(1),
            ),
            budget_scope="old",
        )
        is None
    )
    scan_initial_batch()
    state.refresh_from_db()
    assert state.status == "deferred"
    assert state.candidate_priority is None
    assert state.candidate_policy_version == CANDIDATE_POLICY
    assert coverage()["deferred"] == 1


def test_registered_and_suppressed_decisions_survive_screening():
    from core.official_company_accounts import enqueue_account

    accounts = [
        Account.objects.create(author_id=str(i), bio="Old settled evidence")
        for i in [9101, 9102]
    ]
    registered = enqueue_account(accounts[0])
    registered.status = "registered"
    registered.save()
    suppressed = enqueue_account(accounts[1])
    suppressed.status = "suppressed"
    suppressed.save()
    scan_initial_batch()
    registered.refresh_from_db()
    suppressed.refresh_from_db()
    assert registered.status == "registered"
    assert suppressed.status == "suppressed"


def test_badge_change_between_batches_does_not_double_count_inventory():
    account = Account.objects.create(
        author_id="9103", verified_type="Business", bio="AI lab"
    )
    Account.objects.create(author_id="9104")
    scan_initial_batch(limit=1)
    Account.objects.filter(pk=account.pk).update(verified_type="")
    for _ in range(4):
        report = scan_initial_batch(limit=1)
    assert report["enumerated"] == report["population"] == 2
    assert report["enumeration_complete"]


@pytest.mark.parametrize("index", [0, 1, 2])
def test_all_three_settled_patterns_pass_without_id_overrides_or_gold(index):
    import json
    from pathlib import Path

    from core.models import Post
    from core.official_company_candidates import candidate_priorities

    example = json.loads(
        Path("tests/fixtures/official_company_accounts.json").read_text()
    )[index]["evidence"]
    account = Account.objects.create(
        author_id=str(9200 + index),
        handle=example["handle"],
        display_name=example["display_name"],
    )
    sources = example["sources"]
    bios = [s["text"] for s in sources if s["id"].endswith(":bio")]
    urls = [s["text"] for s in sources if ":bio:url:" in s["id"]]
    Post.objects.create(
        tweet_id=str(9300 + index),
        author=account,
        text="One research update",
        author_profile_bio={
            "description": " ".join(bios),
            "entities": {"url": {"urls": [{"expanded_url": u} for u in urls]}},
        },
    )
    assert candidate_priorities([account])[account.pk] == 2


def test_drain_holds_existing_model_positives_when_registration_is_disabled():
    from unittest.mock import Mock

    from core.official_company_accounts import MODEL, POLICY_VERSION, enqueue_account
    from core.official_company_discovery import drain_accounts
    from x_monitor.config import OfficialCompanyConfig

    account = Account.objects.create(author_id="9400", bio="We build AI models")
    state = enqueue_account(account)
    state.status = "accepted"
    state.model = MODEL
    state.policy_version = POLICY_VERSION
    state.decision = {"outcome": "accepted", "organization_name": "Candidate Lab"}
    state.attempts = 1
    state.save()
    old_hash = state.evidence_hash
    call = Mock()
    result = drain_accounts(
        cfg=OfficialCompanyConfig(enabled=True), call=call,
        limit=1, budget_scope="hold-only",
    )
    state.refresh_from_db()
    assert result["held_for_review"] == 1 and result["attempted"] == 0
    assert state.status == "review_needed"
    assert state.decision["outcome"] == "accepted"
    assert state.evidence_hash == old_hash and state.attempts == 1
    call.assert_not_called()


@pytest.mark.parametrize("registration", [False, True])
def test_review_only_command_evaluates_while_harvest_writer_is_owned(monkeypatch, registration):
    import json
    from concurrent.futures import ThreadPoolExecutor
    from decimal import Decimal
    from io import StringIO
    from types import SimpleNamespace

    from django.core.management import call_command
    from django.db import connections

    from core.official_company_accounts import enqueue_account
    from monitor.management.commands import official_co_account_extraction as command
    from monitor.run_lock import harvest_writer_lock
    from tests.test_official_company_cycle import accept
    from x_monitor.config import OfficialCompanyConfig

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "official-independent-test")
    cfg = OfficialCompanyConfig(
        enabled=True, registration_enabled=registration, max_usd_per_cycle=Decimal(1), max_usd_per_day=Decimal(1),
    )
    account = Account.objects.create(
        author_id="92501", handle="independent_lab",
        bio="We are Voice Lab. We release our own speech models.",
    )
    enqueue_account(account)
    calls = []

    def evaluator(*args):
        calls.append(args)
        return accept(*args)

    monkeypatch.setattr(command, "load_config", lambda path: SimpleNamespace(official_company=cfg))
    monkeypatch.setattr(command, "build_discovery_call", lambda cfg: evaluator)

    def run_command():
        try:
            inventory = StringIO()
            call_command("official_co_account_extraction", "initial-scan", limit=10, stdout=inventory)
            assert json.loads(inventory.getvalue())["enumerated"] == 1
            out = StringIO()
            call_command("official_co_account_extraction", "drain", evaluate_only=True, limit=1, stdout=out)
            return json.loads(out.getvalue())
        finally:
            connections["default"].close()

    with harvest_writer_lock(execution_mode="live", entrypoint="scheduled-harvest") as lease:
        assert lease.acquired
        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(run_command).result(timeout=15)
        assert result.get("attempted") == 1
        assert len(calls) == 1
    state = OfficialCompanyAccountState.objects.get(account=account)
    assert state.status == "review_needed" and state.last_error == "human_review_required"


def test_competing_discovery_command_dispatches_nothing(monkeypatch):
    import json
    from concurrent.futures import ThreadPoolExecutor
    from decimal import Decimal
    from io import StringIO
    from types import SimpleNamespace
    from unittest.mock import Mock

    from django.core.management import call_command
    from django.db import connections

    from core.models import OfficialCompanyAttempt
    from core.official_company_accounts import enqueue_account
    from core.official_company_lock import official_company_writer_lock
    from monitor.management.commands import official_co_account_extraction as command
    from x_monitor.config import OfficialCompanyConfig

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "official-competing-test")
    cfg = OfficialCompanyConfig(enabled=True, max_usd_per_cycle=Decimal(1), max_usd_per_day=Decimal(1))
    state = enqueue_account(Account.objects.create(author_id="92502", bio="AI model research lab"))
    call = Mock(side_effect=AssertionError("Concurrent evaluator must not dispatch"))
    monkeypatch.setattr(command, "load_config", lambda path: SimpleNamespace(official_company=cfg))
    monkeypatch.setattr(command, "build_discovery_call", lambda cfg: call)

    def contender():
        try:
            output = StringIO()
            call_command("official_co_account_extraction", "drain", limit=1, stdout=output)
            return json.loads(output.getvalue())
        finally:
            connections["default"].close()

    with official_company_writer_lock(execution_mode="manual", entrypoint="initial-worker") as lease:
        assert lease.acquired
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(contender).result(timeout=15)["status"] == "discovery_busy"
    state.refresh_from_db()
    assert state.status == "pending" and not call.called
    assert not OfficialCompanyAttempt.objects.exists()


def test_legacy_account_cursor_replays_timestamp_boundary_without_losing_ties():
    import json
    from uuid import UUID

    from core.models import OfficialCompanyScan
    from core.official_company_discovery import _observations

    at = timezone.now() - timedelta(hours=1)
    accounts = [
        Account.objects.create(
            account_key=UUID(int=i), author_id=str(200 - i),
            bio="AI model lab", verified_type="Business",
        )
        for i in [1, 2, 3]
    ]
    Account.objects.filter(pk__in=[a.pk for a in accounts]).update(last_seen_at=at)
    scan = OfficialCompanyScan.objects.create(
        key="account-observations", cursor=json.dumps({"at": at.isoformat(), "pk": "198"}),
    )
    assert _observations("account-observations", Account, "last_seen_at", limit=2) == 2
    scan.refresh_from_db()
    assert json.loads(scan.cursor) == {"at": at.isoformat(), "pk": str(accounts[1].pk)}
    assert _observations("account-observations", Account, "last_seen_at", limit=2) == 1
    assert _observations("account-observations", Account, "last_seen_at", limit=2) == 0
    scan.refresh_from_db()
    assert scan.enumerated == 3
    assert set(OfficialCompanyAccountState.objects.values_list("account_id", flat=True)) == {a.pk for a in accounts}
