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
    assert not OfficialCompanyAccountState.objects.filter(account_id="1").exists()
    assert coverage()["deferred"] == 1
    assert OfficialCompanyAccountState.objects.get(account_id="2").status == "pending"


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
