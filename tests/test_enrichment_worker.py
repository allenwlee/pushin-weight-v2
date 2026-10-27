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
from tests.test_post_enrichment_queue import _cfg, _state
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


def test_classifier_pair_budget_denial_reserves_neither_role_and_spends_no_attempt():
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
        enrichment_window_kind="scheduled",
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
    guard = DispatchGuard(cfg=cfg, lease=SimpleNamespace(assert_held=lambda: None))
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
    state.save(update_fields=["source_collection_job"])
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


@pytest.mark.parametrize("failure", ["ambiguous", "malformed"])
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
    if failure == "ambiguous":
        monkeypatch.setattr(
            cycle,
            "_classification_tracked_brand_catalog",
            lambda: [
                {"brand_id": brand, "aliases": ["Muse"], "products": [], "keywords": []}
                for brand in ("deepseek", "another-brand")
            ],
        )

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
                            "evidence": "Try Muse." if failure == "ambiguous" else None,
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
