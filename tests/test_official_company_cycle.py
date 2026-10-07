import json
from decimal import Decimal
from io import StringIO
from unittest.mock import Mock

import pytest
from django.core.management import call_command

from core.models import Account, OfficialCompanyAccountState, Post, PostBrand
from core.official_company_accounts import enqueue_account
from monitor.cycle import CycleRunner
from x_monitor.config import Config, OfficialCompanyConfig

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


def config():
    return Config(
        enabled_models=["deepseek"],
        daily_ceiling=100,
        official_company=OfficialCompanyConfig(
            enabled=True,
            registration_enabled=True,
            list_sync_enabled=True,
            max_usd_per_cycle=Decimal(1),
            max_usd_per_day=Decimal(1),
        ),
    )


def accept(system, user, model, max_tokens):
    evidence = json.loads(user)
    source = evidence["sources"][0]
    citation = {"source_id": source["id"], "quote": source["text"]}
    return {
        "outcome": "accepted",
        "organization_name": "Unseen Voice Lab",
        "model_types": ["speech"],
        "rationale": "Consistent first-party release evidence",
        "contradictions": [],
        "claims": {
            key: [citation]
            for key in ["organization", "official_account", "model_developer"]
        },
        "usage": {"input_tokens": 100, "output_tokens": 100},
    }


def test_model_positive_is_reviewed_without_registration_or_list_add():
    from core.models import BrandAccount, CompanyAccount, OfficialCompanyListIntent

    account = Account.objects.create(
        author_id="12345", handle="voice_lab",
        bio="We are Voice Lab. We release our own speech models.",
    )
    state = enqueue_account(account)
    client = Mock()
    client.members.return_value = (set(), True)
    runner = CycleRunner(
        cfg=config(), cycle_kind="scheduled",
        _official_company_call=accept, _official_list_client=client,
    )
    result = runner._run_official_company_discovery(
        run_id="cycle", deadline=runner.cfg.harvest.start_deadline()
    )
    assert result["attempted"] == 1 and result["registered"] == 0
    state.refresh_from_db()
    assert state.status == "review_needed"
    assert state.last_error == "human_review_required"
    assert state.decision["outcome"] == "accepted"
    assert state.attempt_records.get().decision["outcome"] == "accepted"
    assert not BrandAccount.objects.filter(account=account).exists()
    assert not CompanyAccount.objects.filter(account=account).exists()
    assert not OfficialCompanyListIntent.objects.exists()
    assert not client.add.called


def test_new_post_preserves_registered_owner_settlement_without_model_call():
    from core.official_company_accounts import register_account

    account = Account.objects.create(
        author_id="1800594921704898560", handle="reflection_ai",
        bio="We build AI models.",
    )
    state = enqueue_account(account)
    register_account(state.pk, cfg=config().official_company)
    state.refresh_from_db()
    saved = (state.evidence_hash, state.evidence, state.decision, state.policy_version)
    Post.objects.create(tweet_id="9401", author=account, text="A new research update")
    model_call = Mock(side_effect=AssertionError("Settled identity must not be reevaluated"))
    runner = CycleRunner(cfg=config(), cycle_kind="scheduled", _official_company_call=model_call)
    result = runner._run_official_company_discovery(
        run_id="new-owner-post", deadline=runner.cfg.harvest.start_deadline()
    )
    state.refresh_from_db()
    assert result["attempted"] == 0
    assert state.status == "registered" and state.model == "owner-attestation"
    assert (state.evidence_hash, state.evidence, state.decision, state.policy_version) == saved
    assert state.attempt_records.count() == 1
    model_call.assert_not_called()


def test_owner_settlement_to_list_observation_and_call_a_attribution():
    from x_monitor.attribution import compile_keyword_index
    from x_monitor.query_plan import PlannedCall

    account = Account.objects.create(
        author_id="1800594921704898560",
        handle="reflection_ai",
        bio="We are Voice Lab. We release our own speech models.",
    )
    enqueue_account(account)
    client = Mock()
    client.members.return_value = (set(), True)
    runner = CycleRunner(
        cfg=config(),
        cycle_kind="scheduled",
        _official_company_call=accept,
        _official_list_client=client,
    )
    result = runner._run_official_company_discovery(
        run_id="cycle", deadline=runner.cfg.harvest.start_deadline()
    )
    assert result["attempted"] == 0 and result["registered"] == 1
    assert result["list_sync"]["confirmed"] == 1
    item = {
        "id": "new-post",
        "author_id": "1800594921704898560",
        "author_handle": "reflection_ai",
        "text": "New release details",
        "created_at": "2026-10-06T12:00:00Z",
    }
    runner._prepare_call_a_roles(
        [item], list_id=int(runner.cfg.official_company.list_id)
    )
    runner._attribute_items([item], compile_keyword_index([]), {})
    assert item["brand_ids"] == ["reflection"]
    runner._route_and_persist(
        PlannedCall(
            call_id="A",
            call_kind="list",
            brand_id="*",
            bucket=None,
            query_string="A",
            query_length=1,
        ),
        [item],
    )
    assert Post.objects.filter(pk="new-post").exists()
    assert PostBrand.objects.filter(
        post_id="new-post", brand_id="reflection"
    ).exists()


def test_dry_run_command_and_manual_cycle_do_not_enqueue_or_dispatch():
    Account.objects.create(author_id="12345", bio="AI model lab")
    call = Mock()
    runner = CycleRunner(cfg=config(), cycle_kind="manual", _official_company_call=call)
    assert (
        runner._run_official_company_discovery(
            run_id="manual", deadline=runner.cfg.harvest.start_deadline()
        )["status"]
        == "disabled"
    )
    out = StringIO()
    call_command(
        "official_co_account_extraction", "initial-scan", dry_run=True, stdout=out
    )
    assert not OfficialCompanyAccountState.objects.exists()
    assert not call.called
    assert json.loads(out.getvalue())["enumerated"] == 0


def test_cycle_wide_exhaustion_and_deadline_preserve_unattempted_work():
    account = Account.objects.create(author_id="12345", bio="AI model lab")
    enqueue_account(account)
    call = Mock()
    runner = CycleRunner(
        cfg=config(), cycle_kind="scheduled", _official_company_call=call
    )
    runner._optional_calls_remaining = 0
    result = runner._run_official_company_discovery(
        run_id="exhausted", deadline=runner.cfg.harvest.start_deadline()
    )
    assert result["attempted"] == 0 and not call.called
    deadline = Mock()
    deadline.remaining.return_value = 0
    assert (
        runner._run_official_company_discovery(run_id="late", deadline=deadline)[
            "status"
        ]
        == "deferred_deadline"
    )
    assert not call.called


@pytest.mark.parametrize(
    "enabled,dry_run,expected_calls",
    [(True, False, 1), (False, False, 0), (True, True, 0)],
)
def test_real_scheduled_cycle_reaches_discovery_once_without_changing_queries(
    monkeypatch, seeded_policy_keywords, enabled, dry_run, expected_calls
):
    from pathlib import Path

    from django.test import override_settings

    from monitor import cycle as cycle_mod
    from monitor.list_membership import MembershipResult
    from scripts.harvest_cost import emit as cost_emit
    from x_monitor.config import load_config

    account = Account.objects.create(
        author_id="12345",
        handle="voice_lab",
        bio="We are Voice Lab. We release our own speech models.",
    )
    enqueue_account(account)

    class FakeApi:
        timeout_s = 30
        max_retries = 0

        def __init__(self):
            self.queries = []
            self._request_log = []

        def run_search(self, query, **kwargs):
            self.queries.append(query)
            return [], False

    api = FakeApi()
    monkeypatch.setattr(
        cycle_mod.TwitterApiClient, "from_env", classmethod(lambda cls, purpose: api)
    )
    monkeypatch.setattr(
        cycle_mod,
        "run_due_reconciliation",
        lambda **kwargs: MembershipResult(status="not_due"),
    )
    monkeypatch.setattr(
        "monitor.metrics_refresh.run_metrics_refresh", lambda *args, **kwargs: {}
    )
    monkeypatch.setattr(cost_emit, "finalize_and_persist", lambda *args, **kwargs: None)
    cfg = load_config(Path("config.yaml"))
    cfg.official_company = OfficialCompanyConfig(
        enabled=enabled, max_usd_per_cycle=Decimal(1), max_usd_per_day=Decimal(1)
    )
    model_call = Mock(side_effect=accept)
    with override_settings(
        X_MONITOR_CYCLE_SKIP_FETCH=False, X_MONITOR_LLM_PAUSE_SECONDS=0
    ):
        result = CycleRunner(
            cfg=cfg,
            cycle_kind="scheduled",
            dry_run=dry_run,
            _official_company_call=model_call,
        ).run()
    assert model_call.call_count == expected_calls
    if not dry_run:
        assert result["status"] != "aborted"
        assert len(result["planned_calls"]) == 7
        if enabled:
            assert result["official_company_discovery"]["attempted"] == 1
