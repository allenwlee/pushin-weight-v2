from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from core.models import EnrichmentBudgetWindow, PostEnrichmentState
from monitor.enrichment_budget import config_fingerprint, reserve_request
from monitor.enrichment_queue import (
    claim_enrichment_states,
    finish_enrichment_stage,
    mark_stage_started,
)
from tests.test_post_enrichment_queue import _cfg
from tests.test_post_enrichment_queue import _requested_state as _state
from x_monitor.attribution import LLMCallBudgetExhausted

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_waiting_two_days_is_not_a_failed_attempt():
    state = _state("two-days-old")
    PostEnrichmentState.objects.filter(pk=state.pk).update(
        created_at=timezone.now() - timedelta(days=2)
    )
    batch = claim_enrichment_states(
        cfg=_cfg().harvest.enrichment, run_id="worker", fair_queue=True
    )
    assert batch.carryover_post_ids == (state.pk,)
    state.refresh_from_db()
    assert state.translation_attempts == state.classification_attempts == 0
    assert state.translation_status == state.classification_status == "pending"


def test_worker_fairness_and_borrowing():
    cfg = _cfg().harvest.enrichment.model_copy(
        update={"batch_size": 10, "fresh_batch_size": 8}
    )
    old = [_state(f"old-{i}") for i in range(6)]
    PostEnrichmentState.objects.filter(pk__in=[s.pk for s in old]).update(
        created_at=timezone.now() - timedelta(hours=2)
    )
    fresh = [_state(f"fresh-{i}") for i in range(12)]
    first = claim_enrichment_states(cfg=cfg, run_id="first", fair_queue=True)
    assert len(first.current_cycle_states) == 8
    assert len(first.carryover_states) == 2
    second = claim_enrichment_states(cfg=cfg, run_id="second", fair_queue=True)
    assert len(second.states) == 8
    assert len(second.carryover_states) == 4
    assert set(first.current_cycle_post_ids + second.current_cycle_post_ids) == {
        s.pk for s in fresh
    }
    assert {s.pk for s in first.states}.isdisjoint(s.pk for s in second.states)


def test_future_retry_and_attempt_checkpoint_are_independent_per_stage():
    state = _state("future-classifier")
    now = timezone.now()
    future = now + timedelta(hours=1)
    PostEnrichmentState.objects.filter(pk=state.pk).update(
        classification_next_attempt_at=future
    )
    cfg = _cfg().harvest.enrichment
    claim_enrichment_states(cfg=cfg, run_id="checkpoint", now=now)
    with pytest.raises(LLMCallBudgetExhausted, match="claim_lost"):
        mark_stage_started(
            post_ids=[state.pk], run_id="checkpoint", stage="classification"
        )
    for _role in range(3):
        mark_stage_started(
            post_ids=[state.pk], run_id="checkpoint", stage="translation"
        )
    finish_enrichment_stage(
        post_ids=[state.pk],
        run_id="checkpoint",
        stage="translation",
        cfg=cfg,
        succeeded_ids=set(),
        error_code="provider_timeout",
        called_ids={state.pk},
        attempts_recorded=True,
    )
    state.refresh_from_db()
    assert state.translation_attempts == 1
    assert state.classification_attempts == 0
    assert state.classification_next_attempt_at == future
    assert state.translation_next_attempt_at >= now + timedelta(minutes=5)
    assert state.translation_error_code == "provider_timeout"


def test_expired_owner_cannot_start_or_finish_a_stage():
    state = _state("expired-owner")
    cfg = _cfg().harvest.enrichment
    claim_enrichment_states(cfg=cfg, run_id="expired")
    PostEnrichmentState.objects.filter(pk=state.pk).update(
        claim_expires_at=timezone.now() - timedelta(seconds=1)
    )
    with pytest.raises(LLMCallBudgetExhausted, match="claim_lost"):
        mark_stage_started(
            post_ids=[state.pk], run_id="expired", stage="classification"
        )
    finish_enrichment_stage(
        post_ids=[state.pk],
        run_id="expired",
        stage="classification",
        cfg=cfg,
        succeeded_ids={state.pk},
        error_code="invalid",
    )
    state.refresh_from_db()
    assert state.classification_status == "pending"
    assert state.classification_attempts == 0


def test_budget_restart_does_not_renew_or_reprice_allowance():
    cfg = _cfg()
    now = timezone.now()
    window = EnrichmentBudgetWindow.objects.create(
        enrichment_window_kind="scheduled",
        starts_at=now,
        ends_at=now + timedelta(hours=1),
        request_limit=1,
        usd_limit=Decimal(1),
        config_fingerprint=config_fingerprint(cfg),
    )
    request = {
        "model": "google/gemma-4-31B-it-turbo",
        "max_tokens": 100,
        "messages": [{"role": "user", "content": "Translate me"}],
    }
    reserve_request(
        window_id=window.pk,
        fingerprint=config_fingerprint(cfg),
        request=request,
        scope="scheduled",
    )
    with pytest.raises(LLMCallBudgetExhausted, match="budget_exhausted"):
        reserve_request(
            window_id=window.pk,
            fingerprint=config_fingerprint(cfg),
            request=request,
            scope="scheduled",
        )
    with pytest.raises(LLMCallBudgetExhausted, match="config_changed"):
        reserve_request(
            window_id=window.pk,
            fingerprint="changed",
            request=request,
            scope="scheduled",
        )
    window.refresh_from_db()
    assert window.reserved_requests == 1
    assert window.reserved_usd > 0


@pytest.mark.parametrize("fingerprint", ["", "a" * 63, "A" * 64, "g" * 64, "a" * 63 + "\n"])
def test_budget_database_rejects_invalid_fingerprint_from_bulk_writers(fingerprint):
    from django.db import IntegrityError, transaction

    now = timezone.now()
    with pytest.raises(IntegrityError, match="ck_enrich_budget_fingerprint"), transaction.atomic():
        EnrichmentBudgetWindow.objects.bulk_create([
            EnrichmentBudgetWindow(
                enrichment_window_kind="pilot", starts_at=now,
                ends_at=now + timedelta(hours=1), request_limit=10, usd_limit=1,
                config_fingerprint=fingerprint,
            ),
        ])


def test_budget_database_rejects_invalid_kind_and_fingerprint_updates():
    from django.db import IntegrityError, transaction

    now = timezone.now()
    window = EnrichmentBudgetWindow.objects.create(
        enrichment_window_kind="pilot", starts_at=now,
        ends_at=now + timedelta(hours=1), request_limit=10, usd_limit=1,
        config_fingerprint="a" * 64,
    )
    for changes, constraint in (
        ({"enrichment_window_kind": "other"}, "ck_enrich_budget_window_kind"),
        ({"config_fingerprint": "invalid"}, "ck_enrich_budget_fingerprint"),
    ):
        with pytest.raises(IntegrityError, match=constraint), transaction.atomic():
            EnrichmentBudgetWindow.objects.filter(pk=window.pk).update(**changes)


def test_pilot_classifier_pair_budget_denial_reserves_neither_role_and_spends_no_attempt():
    from types import SimpleNamespace

    from monitor.cycle import CycleRunner
    from monitor.enrichment_worker import DispatchGuard
    from tests.test_u18_runtime_0731 import FixedSlotTransport
    from x_monitor.config import DEEPSEEK_0731_MODEL

    state = _state("pair-denied")
    cfg = _cfg()
    cfg.llm.classifier_model = DEEPSEEK_0731_MODEL
    now = timezone.now()
    window = EnrichmentBudgetWindow.objects.create(
        enrichment_window_kind="pilot",
        starts_at=now,
        ends_at=now + timedelta(hours=1),
        request_limit=1,
        usd_limit=Decimal(10),
        config_fingerprint=config_fingerprint(cfg),
    )
    cfg.harvest.enrichment.budget_window_id = str(window.pk)
    cfg.harvest.enrichment.mode = "worker"
    state.translation_status = "succeeded"
    state.save(update_fields=["translation_status"])
    guard = DispatchGuard(
        cfg=cfg, lease=SimpleNamespace(assert_held=lambda: None), scope="pilot"
    )
    client = FixedSlotTransport()
    runner = CycleRunner(
        cfg=cfg, _post_fetch_clients={"translation": None, "classification": client}
    )
    runner._process_enrichment_claim_batch([], run_id="denied", dispatch_guard=guard)
    window.refresh_from_db()
    state.refresh_from_db()
    assert client.calls == []
    assert window.reserved_requests == 0
    assert window.reserved_usd == 0
    assert state.classification_attempts == 0
    assert state.classification_status == "pending"


@pytest.mark.parametrize("allowance", ["absent", "expired", "exhausted"])
def test_continuous_command_enriches_without_a_launch_allowance(monkeypatch, allowance):
    """The real command and publishers use the provider key after launch limits end."""
    import json
    from io import StringIO

    from django.core.management import call_command

    from core.models import PostBrandSignal
    from monitor.management.commands import run_enrichment_worker as worker
    from tests.test_literal_translation_plaintext import PlaintextClient, TextResponse
    from tests.test_u18_runtime_0731 import FixedSlotTransport
    from x_monitor import reattribute
    from x_monitor.config import DEEPSEEK_0731_MODEL

    call_command("seed_i18n_labels", verbosity=0)
    state = _state(f"continuous-{allowance}")
    state.post.lang = "en"
    state.post.save(update_fields=["lang"])
    cfg = _cfg()
    cfg.llm.literal_translation_v2_enabled = True
    cfg.llm.classifier_model = DEEPSEEK_0731_MODEL
    cfg.harvest.enrichment.mode = "worker"
    cfg.harvest.enrichment.provider_calls_active = True
    window = None
    if allowance != "absent":
        now = timezone.now()
        window = EnrichmentBudgetWindow.objects.create(
            enrichment_window_kind="scheduled",
            starts_at=now - timedelta(hours=2),
            ends_at=now + timedelta(hours=-1 if allowance == "expired" else 1),
            request_limit=1,
            reserved_requests=1,
            usd_limit=Decimal(1),
            reserved_usd=Decimal(1),
            config_fingerprint=config_fingerprint(cfg),
        )
        cfg.harvest.enrichment.budget_window_id = str(window.pk)
    translator = PlaintextClient(
        [TextResponse("深度求索发布"), TextResponse("DeepSeekのリリース")]
    )
    classifier = FixedSlotTransport()

    def translator_factory(config, **kwargs):
        assert config is cfg and kwargs == {}  # normal DEEPINFRA_API_KEY route
        return translator

    def classifier_factory(config, **kwargs):
        assert config is cfg and kwargs == {}
        return classifier

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "production")
    monkeypatch.setattr(worker, "load_config", lambda path: cfg)
    monkeypatch.setattr(reattribute, "build_translator_client_from_env", translator_factory)
    monkeypatch.setattr(reattribute, "build_classifier_client_from_env", classifier_factory)
    output = StringIO()
    call_command("run_enrichment_worker", once=True, stdout=output)
    assert json.loads(output.getvalue().splitlines()[0])["funding_mode"] == "provider_key"
    result = json.loads(output.getvalue().splitlines()[-1])
    state.refresh_from_db()
    assert state.translation_status == state.classification_status == "succeeded"
    assert state.translation_attempts == state.classification_attempts == 1
    assert not state.claim_run_id
    assert len(translator.calls) == len(classifier.calls) == 2
    assert PostBrandSignal.objects.filter(post_id=state.pk).exists()
    assert result["n_enrichment_succeeded"] == 1
    assert not result["enrichment_stop_reason"]
    if window:
        window.refresh_from_db()
        assert window.reserved_requests == window.reserved_usd == 1


def test_continuous_classifier_pair_still_respects_the_batch_call_limit():
    from types import SimpleNamespace

    from monitor.enrichment_worker import DispatchGuard

    cfg = _cfg()
    cfg.harvest.enrichment.mode = "worker"
    cfg.harvest.enrichment.max_calls_per_batch = 2
    guard = DispatchGuard(
        cfg=cfg, lease=SimpleNamespace(assert_held=lambda: None), scope="continuous"
    )
    guard.reserve_pair([{}, {}], attempts_per_role=1)
    for _ in range(2):
        guard({"_enrichment_budget_prepaid": True})
    with pytest.raises(LLMCallBudgetExhausted, match="batch_budget_exhausted"):
        guard({})
    assert guard.calls == 2
    assert guard.prepaid == 0


def test_manual_enrichment_keeps_its_expired_allowance_and_spends_no_attempt():
    from monitor.cycle import CycleRunner
    from tests.test_literal_translation_plaintext import PlaintextClient, TextResponse

    state = _state("manual-expired")
    state.post.lang = "en"
    state.post.save(update_fields=["lang"])
    state.classification_next_attempt_at = timezone.now() + timedelta(hours=1)
    state.save(update_fields=["classification_next_attempt_at"])
    cfg = _cfg()
    cfg.harvest.enrichment.mode = "worker"
    cfg.llm.literal_translation_v2_enabled = True
    cfg.llm.translator_model = "google/gemma-4-31B-it-turbo"
    now = timezone.now()
    window = EnrichmentBudgetWindow.objects.create(
        enrichment_window_kind="scheduled",
        starts_at=now - timedelta(hours=2),
        ends_at=now - timedelta(hours=1),
        request_limit=10,
        usd_limit=Decimal(1),
        config_fingerprint=config_fingerprint(cfg),
    )
    cfg.harvest.enrichment.budget_window_id = str(window.pk)
    client = PlaintextClient(
        [TextResponse("深度求索发布"), TextResponse("DeepSeekのリリース")]
    )
    result = CycleRunner(
        cfg=cfg, cycle_kind="manual",
        _post_fetch_clients={"translation": client, "classification": None},
    )._run_post_fetch([], run_id="manual-expired")
    state.refresh_from_db()
    window.refresh_from_db()
    assert client.calls == []
    assert state.translation_attempts == 0
    assert state.translation_status == "pending"
    assert window.reserved_requests == 0
    assert result["enrichment_stop_reason"] == "enrichment_budget_expired"


def test_pilot_command_requires_its_own_allowance(monkeypatch, tmp_path):
    from django.core.management import call_command
    from django.core.management.base import CommandError

    from monitor.management.commands import run_enrichment_worker as worker
    from x_monitor import reattribute

    cfg = _cfg()
    cfg.harvest.enrichment.mode = "worker"
    cfg.harvest.enrichment.provider_calls_active = True
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "staging")
    monkeypatch.setattr(worker, "load_config", lambda path: cfg)
    monkeypatch.setattr(
        reattribute, "build_translator_client_from_env",
        lambda *a, **k: pytest.fail("pilot constructed a client without an allowance"),
    )
    ids = tmp_path / "pilot-ids.json"
    ids.write_text('["pilot-post"]')
    with pytest.raises(CommandError, match="pilot requires an explicit budget window"):
        call_command("run_enrichment_worker", pilot=True, post_ids_file=ids, max_batches=1)


def test_worker_mode_collection_does_not_claim_or_construct_providers(monkeypatch):
    from monitor.cycle import CycleRunner

    state = _state("worker-owned")
    cfg = _cfg()
    cfg.harvest.enrichment.mode = "worker"
    monkeypatch.setattr(
        CycleRunner,
        "_process_enrichment_claim_batch",
        lambda *a, **k: pytest.fail("inline processing ran"),
    )
    result = CycleRunner(cfg=cfg, cycle_kind="scheduled")._run_post_fetch(
        [], run_id="collection"
    )
    assert result["enrichment_processed_externally"] is True
    state.refresh_from_db()
    assert not state.claim_run_id
    assert state.classification_attempts == 0


def test_real_translation_does_not_run_classifier_before_its_retry_time():
    from monitor.cycle import CycleRunner
    from tests.test_literal_translation_plaintext import PlaintextClient, TextResponse

    state = _state("translation-now-classifier-later")
    state.post.lang = "en"
    state.post.save(update_fields=["lang"])
    future = timezone.now() + timedelta(hours=1)
    state.classification_next_attempt_at = future
    state.save(update_fields=["classification_next_attempt_at"])
    cfg = _cfg()
    cfg.llm.literal_translation_v2_enabled = True
    client = PlaintextClient(
        [TextResponse("深度求索发布"), TextResponse("DeepSeekのリリース")]
    )

    class ForbiddenClassifier:
        def messages_create(self, **kwargs):
            pytest.fail("future classification was dispatched")

    CycleRunner(
        cfg=cfg,
        _post_fetch_clients={
            "translation": client,
            "classification": ForbiddenClassifier(),
        },
    )._run_post_fetch([], run_id="independent-stages")
    state.refresh_from_db()
    assert len(client.calls) == 2
    assert state.translation_status == "succeeded"
    assert state.translation_attempts == 1
    assert state.classification_attempts == 0
    assert state.classification_next_attempt_at == future


def test_scheduled_worker_excludes_backfill_owned_states(seeded_policy_keywords):
    from tests.test_backfill_collection import ready_job

    state = _state("backfill-owner")
    state.source_collection_job = ready_job()
    state.translation_requested = False
    state.save(update_fields=["source_collection_job", "translation_requested"])
    assert (
        claim_enrichment_states(
            cfg=_cfg().harvest.enrichment, run_id="scheduled", fair_queue=True
        ).states
        == ()
    )


def test_process_slots_limit_concurrency_without_blocking_harvest():
    from monitor.enrichment_worker import process_slot
    from monitor.run_lock import harvest_writer_lock

    cfg = _cfg().harvest.enrichment
    with process_slot(cfg, environment="worker-test") as first:
        assert first is not None
        first.assert_held()
        with process_slot(cfg, environment="worker-test") as second:
            assert second is None
        with harvest_writer_lock(
            execution_mode="live", entrypoint="test", environment="worker-test"
        ) as harvest:
            assert harvest.acquired
        expanded = cfg.model_copy(update={"max_worker_processes": 2})
        with process_slot(expanded, environment="worker-test") as second:
            assert second is not None
            assert second.keys != first.keys


@pytest.mark.parametrize("processes", [1, 2, 3])
def test_future_process_capacity_is_bounded_at_each_configured_size(processes):
    from contextlib import ExitStack

    from monitor.enrichment_worker import process_slot
    from x_monitor.config import EnrichmentConfig

    cfg = EnrichmentConfig(max_worker_processes=processes)
    with ExitStack() as stack:
        leases = [
            stack.enter_context(process_slot(cfg, environment="future-capacity"))
            for _ in range(processes)
        ]
        assert all(lease is not None for lease in leases)
        assert len({lease.keys for lease in leases}) == processes
        assert (
            stack.enter_context(process_slot(cfg, environment="future-capacity"))
            is None
        )


def test_worker_polls_immediately_after_work_and_only_waits_when_idle(monkeypatch):
    from types import SimpleNamespace

    from monitor.management.commands import run_enrichment_worker as worker
    from x_monitor import reattribute

    cfg = _cfg()
    cfg.harvest.enrichment.mode = "worker"
    cfg.harvest.enrichment.provider_calls_active = True
    cfg.harvest.enrichment.budget_window_id = "explicit-window"
    results = iter([{"n_enrichment_claimed": 2}, {"n_enrichment_claimed": 0}])
    waits = []
    stopped = SimpleNamespace(is_set=lambda: False, set=lambda: None, wait=waits.append)
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "production")
    monkeypatch.setattr(worker.threading, "Event", lambda: stopped)
    monkeypatch.setattr(worker, "load_config", lambda path: cfg)
    monkeypatch.setattr(worker, "close_old_connections", lambda: None)
    monkeypatch.setattr(
        reattribute, "build_translator_client_from_env", lambda *a, **k: object()
    )
    monkeypatch.setattr(
        reattribute, "build_classifier_client_from_env", lambda *a, **k: object()
    )
    monkeypatch.setattr(
        worker,
        "CycleRunner",
        lambda **kwargs: SimpleNamespace(_run_post_fetch=lambda *a, **k: next(results)),
    )
    with pytest.raises(StopIteration):
        worker.Command().handle(
            once=False, as_json=True, pilot=False, post_ids_file=None, max_batches=None
        )
    assert waits == [cfg.harvest.enrichment.poll_seconds]


@pytest.mark.parametrize(
    "subjects,expected,removed",
    [
        (["Muse"], [], 1),
        (["Independent Harness"], ["Independent Harness"], 0),
        (["Muse", "Independent Harness"], ["Independent Harness"], 1),
    ],
)
def test_real_classifier_and_publisher_preserve_labels_while_normalizing_tracked_subjects(
    monkeypatch, subjects, expected, removed
):
    import json

    from django.core.management import call_command

    from core.models import (
        PostBrandClassificationState,
        PostBrandSignal,
        UntrackedBrandPromotionEvidence,
    )
    from monitor import cycle
    from tests.test_u18a_v4_classification_persistence import _SelectedV4Transport

    call_command("seed_i18n_labels", verbosity=0)
    state = _state("promotion-chain")
    state.post.text = "Try Muse. Try Independent Harness. DeepSeek is faster."
    state.post.save(update_fields=["text"])
    state.translation_status = "succeeded"
    state.save(update_fields=["translation_status"])
    monkeypatch.setattr(
        cycle, "_requeue_recent_incomplete_translations", lambda **kwargs: 0
    )
    monkeypatch.setattr(
        cycle,
        "_classification_tracked_brand_catalog",
        lambda: [
            {
                "brand_id": "deepseek",
                "aliases": ["DeepSeek"],
                "products": ["Muse"],
                "handles": [],
                "domains": [],
                "keywords": [],
                "hashtags": [],
                "accounts": [],
            }
        ],
    )

    class Transport(_SelectedV4Transport):
        def messages_create(self, **kwargs):
            response = super().messages_create(**kwargs)
            if "promoted_subjects" in response:
                assert "reviewed aliases and products" in kwargs["system"]
                for slot in json.loads(kwargs["messages"][0]["content"])["cases"]:
                    response["promoted_subjects"][slot] = [
                        {
                            "name": name,
                            "handle": None,
                            "domain": None,
                            "account_handle": None,
                            "evidence": f"Try {name}.",
                        }
                        for name in subjects
                    ]
            return response

    transport = Transport()
    result = cycle.CycleRunner(
        cfg=_cfg(),
        _post_fetch_clients={"translation": None, "classification": transport},
    )._run_post_fetch([], run_id="promotion-test")
    state.refresh_from_db()
    assert state.classification_status == "succeeded"
    assert state.classification_attempts == 1  # Two semantic roles, one attempt.
    assert len(transport.calls) == 2
    assert result["n_tracked_promotion_subjects_removed"] == removed
    assert PostBrandClassificationState.objects.filter(post_id=state.pk).count() == 1
    assert list(
        PostBrandSignal.objects.filter(post_id=state.pk).values_list(
            "post_type_id", flat=True
        )
    ) == ["results_analysis"]
    assert (
        list(
            UntrackedBrandPromotionEvidence.objects.filter(
                source_post_id=state.pk
            ).values_list("observed_name", flat=True)
        )
        == expected
    )


def test_lost_process_lock_prevents_physical_dispatch_and_attempt():
    from monitor.cycle import CycleRunner
    from monitor.enrichment_worker import DispatchGuard, process_slot
    from tests.test_literal_translation_plaintext import PlaintextClient

    state = _state("lock-lost-before-dispatch")
    state.post.lang = "en"
    state.post.save(update_fields=["lang"])
    state.classification_status = "succeeded"
    state.save(update_fields=["classification_status"])
    cfg = _cfg()
    cfg.llm.literal_translation_v2_enabled = True
    client = PlaintextClient([])
    with process_slot(cfg.harvest.enrichment, environment="lost-lock-test") as lease:
        guard = DispatchGuard(cfg=cfg, lease=lease)
        lease.connection.close()
        runner = CycleRunner(
            cfg=cfg, _post_fetch_clients={"translation": client, "classification": None}
        )
        with pytest.raises(LLMCallBudgetExhausted, match="process_lock_lost"):
            runner._process_enrichment_claim_batch(
                [], run_id="lost-lock", dispatch_guard=guard
            )
    state.refresh_from_db()
    assert client.calls == []
    assert state.translation_attempts == 0
    assert state.translation_status == "pending"


@pytest.mark.parametrize("failure", ["malformed"])
def test_invalid_promotion_retry_preserves_previous_publication(monkeypatch, failure):
    import json

    from core.models import PostBrandSignal, UntrackedBrandPromotionEvidence
    from monitor import cycle
    from tests.test_u18a_v4_classification_persistence import _SelectedV4Transport

    test_real_classifier_and_publisher_preserve_labels_while_normalizing_tracked_subjects(
        monkeypatch,
        ["Muse", "Independent Harness"],
        ["Independent Harness"],
        1,
    )
    state = PostEnrichmentState.objects.get(pk="promotion-chain")
    prior_signal_ids = list(
        PostBrandSignal.objects.filter(post_id=state.pk).values_list("pk", flat=True)
    )
    prior_evidence_ids = list(
        UntrackedBrandPromotionEvidence.objects.filter(
            source_post_id=state.pk
        ).values_list("pk", flat=True)
    )
    state.classification_status = "pending"
    state.save(update_fields=["classification_status"])

    class InvalidPromotion(_SelectedV4Transport):
        def messages_create(self, **kwargs):
            response = super().messages_create(**kwargs)
            if "promoted_subjects" in response:
                for slot in json.loads(kwargs["messages"][0]["content"])["cases"]:
                    response["promoted_subjects"][slot] = [
                        {
                            "name": "Muse",
                            "handle": None,
                            "domain": None,
                            "account_handle": None,
                            "evidence": None,
                        }
                    ]
            return response

    cycle.CycleRunner(
        cfg=_cfg(),
        _post_fetch_clients={"translation": None, "classification": InvalidPromotion()},
    )._run_post_fetch([], run_id="invalid-promotion-retry")
    state.refresh_from_db()
    assert state.classification_status == "pending"
    assert state.classification_attempts == 2
    assert state.classification_error_code
    assert (
        list(
            PostBrandSignal.objects.filter(post_id=state.pk).values_list(
                "pk", flat=True
            )
        )
        == prior_signal_ids
    )
    assert (
        list(
            UntrackedBrandPromotionEvidence.objects.filter(
                source_post_id=state.pk
            ).values_list("pk", flat=True)
        )
        == prior_evidence_ids
    )


def test_shared_name_promotion_publishes_and_drops_only_that_subject(monkeypatch, caplog):
    """A promoted name owned by two tracked brands no longer discards the post.

    Before 2026-11-24 the legacy two_role path raised
    classification_promotion_identity_ambiguous and threw away the whole paid
    classification (146 pending posts on 2026-11-24). Now the subject is dropped
    from the untracked list, like a single-owner match, and the drop is logged
    with the matched term and both owners.
    """
    import json
    import logging

    from core.models import PostBrandSignal
    from monitor import cycle
    from tests.test_u18a_v4_classification_persistence import _SelectedV4Transport

    test_real_classifier_and_publisher_preserve_labels_while_normalizing_tracked_subjects(
        monkeypatch,
        ["Muse", "Independent Harness"],
        ["Independent Harness"],
        1,
    )
    state = PostEnrichmentState.objects.get(pk="promotion-chain")
    state.classification_status = "pending"
    state.save(update_fields=["classification_status"])
    monkeypatch.setattr(
        cycle,
        "_classification_tracked_brand_catalog",
        lambda: [
            {"brand_id": brand, "aliases": ["Muse"], "products": [], "keywords": []}
            for brand in ("deepseek", "another-brand")
        ] + [{"brand_id": "absent-new-brand", "aliases": ["Absent New Brand"]}],
    )

    class SharedNamePromotion(_SelectedV4Transport):
        def messages_create(self, **kwargs):
            packet = json.loads(kwargs["messages"][0]["content"])
            sent = {row["brand_id"] for row in packet["tracked_brands"]["brands"]}
            assert {"deepseek", "another-brand"} <= sent
            assert "absent-new-brand" not in sent
            response = super().messages_create(**kwargs)
            if "promoted_subjects" in response:
                for slot in json.loads(kwargs["messages"][0]["content"])["cases"]:
                    response["promoted_subjects"][slot] = [
                        {
                            "name": "Muse",
                            "handle": None,
                            "domain": None,
                            "account_handle": None,
                            "evidence": "Try Muse.",
                        }
                    ]
            return response

    caplog.set_level(logging.INFO, logger="monitor.cycle")
    caplog.clear()  # drop the setup run's single-owner log line
    cycle.CycleRunner(
        cfg=_cfg(), cycle_kind="enrichment",
        _post_fetch_clients={"translation": None, "classification": SharedNamePromotion()},
    )._run_post_fetch([], run_id="shared-name-promotion")
    state.refresh_from_db()
    assert state.classification_status == "succeeded"
    assert not state.classification_error_code
    assert PostBrandSignal.objects.filter(post_id=state.pk).exists()
    dropped = [r.getMessage() for r in caplog.records if "promoted subject dropped" in r.getMessage()]
    assert dropped, "the shared-name drop must be logged"
    assert "muse" in dropped[0].lower()
    assert "another-brand" in dropped[0] and "deepseek" in dropped[0]


@pytest.mark.parametrize("arrival_multiplier", [1, 2, 3])
def test_scaled_arrivals_keep_both_queue_lanes_moving(arrival_multiplier):
    from monitor.enrichment_queue import release_enrichment_claim

    cfg = _cfg().harvest.enrichment.model_copy(
        update={"batch_size": 10, "fresh_batch_size": 8}
    )
    fresh = [_state(f"fresh-load-{i}") for i in range(8 * arrival_multiplier)]
    old = [_state(f"old-load-{i}") for i in range(2 * arrival_multiplier)]
    PostEnrichmentState.objects.filter(pk__in=[s.pk for s in old]).update(
        created_at=timezone.now() - timedelta(days=2)
    )
    completed = set()
    for index in range(arrival_multiplier):
        run_id = f"arrival-batch-{index}"
        batch = claim_enrichment_states(cfg=cfg, run_id=run_id, fair_queue=True)
        ids = [s.pk for s in batch.states]
        assert len(batch.current_cycle_states) == 8
        assert len(batch.carryover_states) == 2
        assert completed.isdisjoint(ids)
        for stage in ("translation", "classification"):
            mark_stage_started(post_ids=ids, run_id=run_id, stage=stage)
            finish_enrichment_stage(
                post_ids=ids,
                run_id=run_id,
                stage=stage,
                succeeded_ids=set(ids),
                error_code="",
                cfg=cfg,
                called_ids=set(ids),
                attempts_recorded=True,
            )
        for post_id in ids:
            release_enrichment_claim(post_id, run_id=run_id)
        completed.update(ids)
    assert completed == {s.pk for s in fresh + old}
    assert not claim_enrichment_states(
        cfg=cfg, run_id="drained", fair_queue=True
    ).states


def test_capacity_validation_includes_commentary_deployment_overlap():
    from pydantic import ValidationError
    from x_monitor.config import EnrichmentConfig

    assert EnrichmentConfig().other_gemma_concurrency >= 2 * 2 + 3
    assert EnrichmentConfig(max_worker_processes=4).translation_concurrency == 3
    with pytest.raises(ValidationError, match="Gemma"):
        EnrichmentConfig(max_worker_processes=5)


def test_pulse_concurrency_is_bound_to_pulse_budget_only():
    from copy import deepcopy
    from monitor.enrichment_budget import config_fingerprint
    from tests.test_post_enrichment_queue import _cfg

    cfg = _cfg()
    changed = deepcopy(cfg)
    changed.harvest.enrichment.pulse_classification_concurrency = 9
    assert config_fingerprint(cfg) == config_fingerprint(changed)
    cfg.llm.classifier_pipeline = "compressed8_pulse_v1"
    changed.llm.classifier_pipeline = "compressed8_pulse_v1"
    assert config_fingerprint(cfg) != config_fingerprint(changed)


def test_worker_shares_fresh_slots_between_newest_and_oldest_posts():
    from core.models import Post

    cfg = _cfg().harvest.enrichment.model_copy(update={'batch_size': 10, 'fresh_batch_size': 8})
    now = timezone.now()
    fresh = [_state(f'priority-fresh-{index:02d}') for index in range(12)]
    publication_order = [8, 1, 10, 0, 7, 2, 11, None, 3, 10, 5, 6]
    for index, state in enumerate(fresh):
        PostEnrichmentState.objects.filter(pk=state.pk).update(created_at=now - timedelta(seconds=12-index))
        value = publication_order[index]
        Post.objects.filter(pk=state.pk).update(created_at=now - timedelta(seconds=12-value) if value is not None else None)
    old = [_state(f'priority-old-{index:02d}') for index in range(3)]
    PostEnrichmentState.objects.filter(pk__in=[state.pk for state in old]).update(created_at=now-timedelta(hours=2))
    batch = claim_enrichment_states(cfg=cfg, run_id='priority', now=now, fair_queue=True)
    assert batch.current_cycle_post_ids == tuple(fresh[index].pk for index in (6, 9, 2, 0, 1, 3, 4, 5))
    assert len(batch.carryover_states) == 2


def test_worker_dispatches_newest_and_oldest_fresh_posts_in_priority_order(monkeypatch):
    from core.models import Post
    from monitor.cycle import CycleRunner
    from x_monitor import attribution

    cfg = _cfg()
    cfg.harvest.enrichment.batch_size = 4
    cfg.harvest.enrichment.fresh_batch_size = 4
    now = timezone.now()
    states = [_state(f'worker-priority-{index}') for index in range(6)]
    for index, state in enumerate(states):
        PostEnrichmentState.objects.filter(pk=state.pk).update(
            created_at=now-timedelta(seconds=6-index), translation_status='succeeded',
        )
        Post.objects.filter(pk=state.pk).update(created_at=now-timedelta(seconds=6-index))
    captured = []

    def classify(tweets, *args, **kwargs):
        captured.extend(tweet['tweet_id'] for tweet in tweets)
        return [{'valid': False} for _ in tweets]

    monkeypatch.setattr(attribution, 'classify_batch_pragmatics_full', classify)
    runner = CycleRunner(cfg=cfg, _post_fetch_clients={'translation': None, 'classification': object()})
    runner._run_post_fetch([], run_id='worker-priority', fair_queue=True)
    assert captured == [states[index].pk for index in (5, 4, 0, 1)]


def test_worker_prioritizes_first_classification_in_recent_and_older_lanes():
    from core.models import Post

    now = timezone.now()
    cfg = _cfg().harvest.enrichment.model_copy(update={"batch_size": 10, "fresh_batch_size": 8})
    first = [_state(f"first-{i}") for i in range(10)]
    retry = [_state(f"retry-{i}") for i in range(10)]
    for states, attempts in ((first, 0), (retry, 1)):
        for i, state in enumerate(states):
            old = i >= 8
            # Retries are both older queued and newer published: neither
            # ordering should put them ahead of a missing first attempt.
            queued = now - timedelta(minutes=(60 if old else 10) + attempts)
            PostEnrichmentState.objects.filter(pk=state.pk).update(
                created_at=queued, classification_attempts=attempts,
                translation_requested=False,
            )
            Post.objects.filter(pk=state.pk).update(created_at=now-timedelta(seconds=100-i-50*attempts))
    batch = claim_enrichment_states(cfg=cfg, run_id="first-attempt", now=now, fair_queue=True)
    assert len(set(batch.current_cycle_post_ids) & {s.pk for s in first[:8]}) == 6
    assert len(set(batch.current_cycle_post_ids) & {s.pk for s in retry[:8]}) == 2
    assert len(set(batch.carryover_post_ids) & {s.pk for s in first[8:]}) == 1
    assert len(set(batch.carryover_post_ids) & {s.pk for s in retry[8:]}) == 1
    # Once first attempts have been claimed, retry work still uses the queue.
    following = claim_enrichment_states(cfg=cfg, run_id="retry-work", now=now, fair_queue=True)
    assert {s.pk for s in batch.states + following.states} == {s.pk for s in first + retry}


def test_worker_dispatches_first_attempts_before_retries(monkeypatch):
    from core.models import Post
    from monitor.cycle import CycleRunner
    from x_monitor import attribution

    now = timezone.now()
    cfg = _cfg()
    cfg.harvest.enrichment.batch_size = cfg.harvest.enrichment.fresh_batch_size = 4
    first = [_state(f"first-dispatch-{i}") for i in range(4)]
    retry = [_state(f"retry-dispatch-{i}") for i in range(4)]
    for states, attempts in ((first, 0), (retry, 1)):
        for i, state in enumerate(states):
            PostEnrichmentState.objects.filter(pk=state.pk).update(
                created_at=now-timedelta(minutes=2+attempts),
                translation_status="succeeded", classification_attempts=attempts,
            )
            Post.objects.filter(pk=state.pk).update(created_at=now-timedelta(seconds=100-i-50*attempts))
    captured = []
    def classify(tweets, *args, **kwargs):
        captured.extend(tweet["tweet_id"] for tweet in tweets)
        return [{"valid": False} for _ in tweets]
    monkeypatch.setattr(attribution, "classify_batch_pragmatics_full", classify)
    runner = CycleRunner(cfg=cfg, _post_fetch_clients={"translation": None, "classification": object()})
    runner._run_post_fetch([], run_id="first-dispatch", fair_queue=True)
    assert len(set(captured) & {state.pk for state in first}) == 2
    assert len(set(captured) & {state.pk for state in retry}) == 2


@pytest.mark.parametrize("blocked_reason", ["future_due", "no_brand", "historical_owner"])
def test_first_classification_priority_requires_runnable_classification(blocked_reason):
    from core.models import Post, PostBrand
    from tests.test_backfill_collection import ready_job

    now = timezone.now()
    cfg = _cfg().harvest.enrichment.model_copy(update={"batch_size": 4, "fresh_batch_size": 4})
    ready = [_state(f"ready-first-{i}") for i in range(4)]
    translation_only = [_state(f"translation-only-{i}") for i in range(4)]
    for states, offset in ((ready, 0), (translation_only, 1)):
        PostEnrichmentState.objects.filter(pk__in=[s.pk for s in states]).update(created_at=now-timedelta(minutes=2+offset))
        Post.objects.filter(pk__in=[s.pk for s in states]).update(created_at=now-timedelta(seconds=100-50*offset))
    ids = [s.pk for s in translation_only]
    if blocked_reason == "future_due":
        PostEnrichmentState.objects.filter(pk__in=ids).update(classification_next_attempt_at=now+timedelta(hours=1))
    elif blocked_reason == "no_brand":
        PostBrand.objects.filter(post_id__in=ids).delete()
    else:
        PostEnrichmentState.objects.filter(pk__in=ids).update(source_collection_job=ready_job())
    batch = claim_enrichment_states(cfg=cfg, run_id="runnable-first", now=now, fair_queue=True)
    assert len(set(batch.current_cycle_post_ids) & {s.pk for s in ready}) == 2
    assert len(set(batch.current_cycle_post_ids) & set(ids)) == 2


def test_retries_keep_a_share_while_first_attempts_continue_arriving():
    cfg = _cfg().harvest.enrichment.model_copy(update={"batch_size": 10, "fresh_batch_size": 8})
    now = timezone.now()
    for turn in range(3):
        for kind, attempts in (("first", 0), ("retry", 1)):
            for i in range(10):
                state = _state(f"steady-{turn}-{kind}-{i}")
                PostEnrichmentState.objects.filter(pk=state.pk).update(
                    classification_attempts=attempts, translation_requested=False,
                    created_at=now-timedelta(minutes=60 if i>=8 else 2),
                )
        batch = claim_enrichment_states(cfg=cfg, run_id=f"steady-{turn}", now=now, fair_queue=True)
        assert len(batch.states) == 10
        assert sum(s.classification_attempts == 0 for s in batch.states) == 7
        assert sum(s.classification_attempts > 0 for s in batch.states) == 3


def test_continuous_pairs_return_only_unused_slots_for_follow_on_work():
    from types import SimpleNamespace

    from monitor.cycle import _BoundedClassifierClient
    from monitor.enrichment_worker import DispatchGuard

    cfg = _cfg()
    cfg.harvest.enrichment.max_calls_per_batch = 600
    guard = DispatchGuard(cfg=cfg, lease=SimpleNamespace(assert_held=lambda: None), scope="continuous")
    class Provider:
        def messages_create(self, **kwargs):
            return {}

    client = _BoundedClassifierClient(Provider(), maximum_calls=600, pause_seconds=0,
        before_dispatch=guard, reserve_pair_budget=guard.reserve_pair,
        release_pair_budget=guard.release_unused_pair)
    for _ in range(100):
        pair = client.reserve_pair(attempts_per_role=3, request_bounds=[{}, {}])
        assert pair is not None
        for role in pair:
            client.messages_create(_classifier_reservation=role)
        client.release_reservations(*pair)
        client.release_reservations(*pair)
    assert (client.calls, guard.calls, guard.prepaid) == (200, 200, 0)
    for _ in range(400):
        guard({})
    with pytest.raises(LLMCallBudgetExhausted):
        guard({})


def test_due_requested_translation_has_room_among_older_classifier_retries():
    now = timezone.now()
    cfg = _cfg().harvest.enrichment.model_copy(update={"batch_size": 10, "fresh_batch_size": 0})
    for index in range(12):
        state = _state(f"older-{index}")
        PostEnrichmentState.objects.filter(pk=state.pk).update(
            translation_requested=False, classification_attempts=1, created_at=now - timedelta(hours=4))
    requested = _state("requested-after-retries")
    PostEnrichmentState.objects.filter(pk=requested.pk).update(
        classification_status="succeeded", created_at=now - timedelta(hours=2))
    claimed = claim_enrichment_states(cfg=cfg, run_id="translation-fairness", now=now, fair_queue=True)
    assert requested.pk in {row.pk for row in claimed.states}
    assert len(claimed.states) == 10


def test_new_translation_on_an_old_first_classification_uses_its_first_attempt_share():
    now = timezone.now()
    cfg = _cfg().harvest.enrichment.model_copy(update={"batch_size": 10, "fresh_batch_size": 0})
    for index in range(20):
        state = _state(f"first-or-retry-{index}")
        PostEnrichmentState.objects.filter(pk=state.pk).update(translation_requested=False,
            classification_attempts=int(index < 10), created_at=now - timedelta(hours=4))
    request = _state("classify-and-translate")
    PostEnrichmentState.objects.filter(pk=request.pk).update(created_at=now - timedelta(hours=2))
    claimed = claim_enrichment_states(cfg=cfg, run_id="two-stages", now=now, fair_queue=True)
    assert request.pk in {s.pk for s in claimed.states}
    assert sum(s.classification_attempts == 0 for s in claimed.states) == 8
    assert len(claimed.states) == 10


def test_unsent_reserved_call_releases_the_entire_continuous_allowance():
    from types import SimpleNamespace
    from monitor.cycle import _BoundedClassifierClient
    from monitor.enrichment_worker import DispatchGuard

    guard = DispatchGuard(cfg=_cfg(), lease=SimpleNamespace(assert_held=lambda: None), scope="continuous")
    def lost_claim(kwargs):
        raise LLMCallBudgetExhausted("claim expired")

    bounded = _BoundedClassifierClient(object(), maximum_calls=6, pause_seconds=0, before_dispatch=lost_claim,
        reserve_pair_budget=guard.reserve_pair, release_pair_budget=guard.release_unused_pair)
    pair = bounded.reserve_pair(attempts_per_role=3, request_bounds=[{}, {}])
    with pytest.raises(LLMCallBudgetExhausted, match="claim expired"):
        bounded.messages_create(_classifier_reservation=pair[0])
    bounded.release_reservations(*pair)
    assert (bounded.calls, guard.calls, guard.prepaid) == (0, 0, 0)


def test_failed_checkpoint_commit_preserves_both_active_pairs(monkeypatch):
    from types import SimpleNamespace
    from django.db import OperationalError, connection
    from monitor.cycle import _BoundedClassifierClient
    from monitor.enrichment_worker import DispatchGuard

    state = _state("commit-before-transport")
    guard = DispatchGuard(cfg=_cfg(), lease=SimpleNamespace(assert_held=lambda: None), scope="continuous")
    sent = []

    def checkpoint():
        PostEnrichmentState.objects.filter(pk=state.pk).update(classification_error_code="started")

    def refuse_commit():
        raise OperationalError("checkpoint commit failed")

    def provider(**kwargs):
        sent.append(kwargs)
        return {}

    client = _BoundedClassifierClient(
        SimpleNamespace(messages_create=provider), maximum_calls=12, pause_seconds=0,
        before_dispatch=lambda request: guard(request, record_start=checkpoint),
        reserve_pair_budget=guard.reserve_pair, release_pair_budget=guard.release_unused_pair,
    )
    first = client.reserve_pair(attempts_per_role=3, request_bounds=[{}, {}])
    sibling = client.reserve_pair(attempts_per_role=3, request_bounds=[{}, {}])
    with monkeypatch.context() as failing:
        failing.setattr(connection, "_commit", refuse_commit)
        with pytest.raises(OperationalError, match="checkpoint commit failed"):
            client.messages_create(_classifier_reservation=first[0])
    state.refresh_from_db()
    assert state.classification_error_code == "" and not sent
    client.release_reservations(*first)
    client.messages_create(_classifier_reservation=sibling[0])
    client.release_reservations(*sibling)
    assert len(sent) == client.calls == guard.calls == 1
    assert guard.prepaid == 0
