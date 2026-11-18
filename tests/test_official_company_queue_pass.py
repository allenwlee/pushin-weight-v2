from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from core.models import Account, DataSource
from core.official_company_accounts import enqueue_account

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


def candidate(identifier, priority, status="pending"):
    DataSource.objects.get_or_create(
        pk="x", defaults={"name": "X", "source_type": "social"}
    )
    account = Account.objects.create(
        author_id=str(identifier), bio="We develop AI models"
    )
    state = enqueue_account(account)
    state.candidate_priority = priority
    state.status = status
    state.save()
    return state


def test_freeze_captures_all_queue_tiers_including_future_retry(tmp_path):
    from core.official_company_queue_pass import freeze_queue, read_manifest

    first = candidate(801, 1)
    delayed = candidate(802, 3, "retry_due")
    delayed.next_attempt_at = timezone.now() + timedelta(days=1)
    delayed.save()
    path = tmp_path / "manifest.json"
    manifest = freeze_queue(path=path, total_limit=Decimal(2))
    candidate(803, 2)
    assert read_manifest(path) == manifest
    assert {m["state_id"] for m in manifest["members"]} == {first.pk, delayed.pk}
    assert manifest["count"] == 2
    assert manifest["members"][1]["starting_status"] == "retry_due"
    assert not path.stat().st_mode & 0o077


def test_claim_guards_snapshot_identity_and_aggregate_budget():
    from core.models import OfficialCompanyBudget
    from core.official_company_accounts import claim_account
    from x_monitor.config import OfficialCompanyConfig

    state = candidate(804, 1)
    cfg = OfficialCompanyConfig(
        enabled=True, max_usd_per_cycle=Decimal(1), max_usd_per_day=Decimal(1)
    )
    assert (
        claim_account(
            state.pk,
            cfg=cfg,
            budget_scope="batch-1",
            expected_account_key=str(state.account_id),
            expected_evidence_hash="stale",
            run_budget=("queue-pass:test", Decimal(1)),
        )
        is None
    )
    attempt = claim_account(
        state.pk,
        cfg=cfg,
        budget_scope="batch-1",
        expected_account_key=str(state.account_id),
        expected_evidence_hash=state.evidence_hash,
        run_budget=("queue-pass:test", Decimal(1)),
    )
    assert attempt is not None
    budget = OfficialCompanyBudget.objects.get(pk="queue-pass:test")
    assert budget.reserved_usd == attempt.reserved_usd
    other = candidate(805, 2)
    assert (
        claim_account(
            other.pk,
            cfg=cfg,
            budget_scope="batch-2",
            expected_account_key=str(other.account_id),
            expected_evidence_hash=other.evidence_hash,
            run_budget=("queue-pass:test", budget.reserved_usd),
        )
        is None
    )


def test_frozen_runner_processes_one_snapshot_member_and_reconciles(tmp_path):
    from core.official_company_queue_pass import freeze_queue, report, run_batch
    from tests.test_official_company_cycle import accept
    from x_monitor.config import OfficialCompanyConfig

    first = candidate(806, 1)
    cfg = OfficialCompanyConfig(
        enabled=True, max_usd_per_cycle=Decimal(1), max_usd_per_day=Decimal(1)
    )
    manifest = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    candidate(807, 2)
    result = run_batch(
        manifest,
        cfg=cfg,
        call=accept,
        limit=1,
        seconds=60,
        receipt_path=tmp_path / "proof.json",
    )
    assert result["evaluator_invocations"] == 1
    reconciled = report(manifest)
    assert len(reconciled["members"]) == 1
    assert reconciled["members"][0]["state_id"] == first.pk
    assert reconciled["members"][0]["disposition"] == "completed"
    assert reconciled["members"][0]["outcome"] == "accepted"
    assert (
        run_batch(
            manifest,
            cfg=cfg,
            call=accept,
            limit=1,
            seconds=60,
            receipt_path=tmp_path / "proof.json",
        )["evaluator_invocations"]
        == 0
    )


def test_command_freeze_run_and_report_through_real_evaluator(tmp_path, monkeypatch):
    import json
    from io import StringIO
    from types import SimpleNamespace

    from django.core.management import call_command

    from tests.test_official_company_cycle import accept
    from x_monitor.config import OfficialCompanyConfig

    candidate(808, 1)
    cfg = OfficialCompanyConfig(
        enabled=True, max_usd_per_cycle=Decimal(1), max_usd_per_day=Decimal(1)
    )
    monkeypatch.setattr(
        "x_monitor.config.load_config",
        lambda path: SimpleNamespace(official_company=cfg),
    )
    monkeypatch.setattr(
        "core.official_company_discovery.build_discovery_call", lambda cfg: accept
    )
    path = str(tmp_path / "manifest.json")
    output = StringIO()
    call_command(
        "official_company_queue_pass",
        "freeze",
        manifest=path,
        total_limit_usd="2",
        stdout=output,
    )
    assert json.loads(output.getvalue())["count"] == 1
    output = StringIO()
    call_command(
        "official_company_queue_pass", "run", manifest=path, seconds=60, stdout=output
    )
    assert json.loads(output.getvalue())["reason"] == "verification_complete"
    output = StringIO()
    call_command("official_company_queue_pass", "report", manifest=path, stdout=output)
    assert json.loads(output.getvalue())["counts"] == {"completed": 1}


def test_active_attempt_at_cutoff_is_reconciled_on_completion(tmp_path):
    import json

    from core.official_company_accounts import claim_account, complete_attempt
    from core.official_company_queue_pass import freeze_queue, report
    from tests.test_official_company_cycle import accept
    from x_monitor.config import OfficialCompanyConfig

    state = candidate(809, 2)
    cfg = OfficialCompanyConfig(
        enabled=True, max_usd_per_cycle=Decimal(1), max_usd_per_day=Decimal(1)
    )
    attempt = claim_account(state.pk, cfg=cfg, budget_scope="existing-cycle")
    manifest = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    assert manifest["members"][0]["attempt_id"] == attempt.pk
    assert report(manifest)["members"][0]["disposition"] == "in_flight"
    response = accept(
        "model-llm model-other", json.dumps(attempt.evidence), "model", 100
    )
    complete_attempt(attempt.pk, cfg=cfg, response=response)
    assert report(manifest)["members"][0]["disposition"] == "completed"


def test_unknown_queue_pass_call_is_never_repeated_by_scheduled_caller(tmp_path):
    from unittest.mock import Mock

    from core.official_company_accounts import evaluate_account
    from core.official_company_queue_pass import freeze_queue, report, run_batch
    from x_monitor.config import OfficialCompanyConfig

    state = candidate(810, 1)
    cfg = OfficialCompanyConfig(
        enabled=True, max_usd_per_cycle=Decimal(1), max_usd_per_day=Decimal(1)
    )
    manifest = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    call = Mock(side_effect=TimeoutError())
    assert (
        run_batch(
            manifest,
            cfg=cfg,
            call=call,
            limit=1,
            seconds=60,
            receipt_path=tmp_path / "proof.json",
        )["reason"]
        == "evaluation_not_verified"
    )
    assert report(manifest)["members"][0]["disposition"] == "unknown_call"
    state.refresh_from_db()
    state.next_attempt_at = timezone.now() - timedelta(seconds=1)
    state.save()
    assert not evaluate_account(
        state.pk, cfg=cfg, call=call, budget_scope="later-scheduled"
    )
    assert call.call_count == 1


def test_queue_pass_runs_while_another_connection_holds_harvest_lock(tmp_path):
    import threading

    from django.db import connections

    from core.official_company_queue_pass import freeze_queue, run_batch
    from monitor.run_lock import harvest_writer_lock
    from tests.test_official_company_cycle import accept
    from x_monitor.config import OfficialCompanyConfig

    candidate(811, 1)
    manifest = freeze_queue(path=tmp_path / "manifest.json", total_limit=Decimal(2))
    cfg = OfficialCompanyConfig(
        enabled=True, max_usd_per_cycle=Decimal(1), max_usd_per_day=Decimal(1)
    )
    acquired = threading.Event()
    release = threading.Event()

    def hold_harvest():
        try:
            with harvest_writer_lock(
                execution_mode="scheduled", entrypoint="queue-test", run_id="harvest"
            ) as lease:
                assert lease.acquired
                acquired.set()
                release.wait(timeout=30)
        finally:
            connections.close_all()

    thread = threading.Thread(target=hold_harvest)
    thread.start()
    try:
        assert acquired.wait(timeout=10)
        result = run_batch(
            manifest,
            cfg=cfg,
            call=accept,
            limit=1,
            seconds=60,
            receipt_path=tmp_path / "proof.json",
        )
        assert result["reason"] == "verification_complete"
    finally:
        release.set()
        thread.join(timeout=30)
    assert not thread.is_alive()


def test_unknown_first_call_blocks_another_batch(tmp_path):
    from unittest.mock import Mock

    from core.official_company_queue_pass import freeze_queue, run_batch
    from x_monitor.config import OfficialCompanyConfig

    candidate(812, 1)
    candidate(813, 2)
    cfg = OfficialCompanyConfig(
        enabled=True, max_usd_per_cycle=Decimal(1), max_usd_per_day=Decimal(1)
    )
    manifest = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    call = Mock(side_effect=TimeoutError())
    assert (
        run_batch(
            manifest,
            cfg=cfg,
            call=call,
            limit=2,
            seconds=60,
            receipt_path=tmp_path / "proof.json",
        )["evaluator_invocations"]
        == 1
    )
    result = run_batch(
        manifest,
        cfg=cfg,
        call=call,
        limit=2,
        seconds=60,
        receipt_path=tmp_path / "proof.json",
    )
    assert result["reason"] == "unresolved_run_attempt"
    assert result["evaluator_invocations"] == 0
    assert call.call_count == 1


def test_manifest_cannot_be_overwritten_or_silently_changed(tmp_path):
    from core.official_company_queue_pass import freeze_queue, read_manifest

    candidate(814, 1)
    path = tmp_path / "queue.json"
    freeze_queue(path=path, total_limit=Decimal(2))
    with pytest.raises(FileExistsError):
        freeze_queue(path=path, total_limit=Decimal(3))
    path.write_text(
        path.read_text().replace('"total_limit_usd":"2"', '"total_limit_usd":"3"')
    )
    with pytest.raises(ValueError, match="checksum"):
        read_manifest(path)


def test_competing_discovery_worker_causes_no_model_call(tmp_path):
    import threading
    from unittest.mock import Mock

    from django.db import connections

    from core.official_company_lock import official_company_writer_lock
    from core.official_company_queue_pass import freeze_queue, run_batch
    from x_monitor.config import OfficialCompanyConfig

    candidate(815, 1)
    manifest = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    cfg = OfficialCompanyConfig(
        enabled=True, max_usd_per_cycle=Decimal(1), max_usd_per_day=Decimal(1)
    )
    acquired, release = threading.Event(), threading.Event()

    def hold_discovery():
        try:
            with official_company_writer_lock(
                execution_mode="scheduled", entrypoint="queue-test", run_id="scheduled"
            ) as lease:
                assert lease.acquired
                acquired.set()
                release.wait(timeout=30)
        finally:
            connections.close_all()

    thread = threading.Thread(target=hold_discovery)
    thread.start()
    try:
        assert acquired.wait(timeout=10)
        call = Mock()
        result = run_batch(
            manifest,
            cfg=cfg,
            call=call,
            limit=1,
            seconds=60,
            receipt_path=tmp_path / "proof.json",
        )
        assert result["reason"] == "discovery_busy"
        assert result["evaluator_invocations"] == 0
        call.assert_not_called()
    finally:
        release.set()
        thread.join(timeout=30)
    assert not thread.is_alive()


def test_aggregate_reservations_are_serialized_across_batches():
    import threading

    from django.db import connections, transaction

    from core.models import OfficialCompanyBudget
    from core.official_company_accounts import claim_account
    from x_monitor.config import OfficialCompanyConfig

    first, second = candidate(816, 1), candidate(817, 1)
    cfg = OfficialCompanyConfig(
        enabled=True, max_usd_per_cycle=Decimal(1), max_usd_per_day=Decimal(1)
    )
    with transaction.atomic():
        sample = claim_account(first.pk, cfg=cfg, budget_scope="sample")
        ceiling = sample.reserved_usd
        transaction.set_rollback(True)
    barrier = threading.Barrier(2)
    results = []
    errors = []

    def reserve(state, scope):
        try:
            barrier.wait(timeout=10)
            result = claim_account(
                state.pk,
                cfg=cfg,
                budget_scope=scope,
                run_budget=("queue-pass:race", ceiling),
            )
            results.append(result is not None)
        except Exception as exc:  # noqa: BLE001 - report worker failures in the test thread
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [
        threading.Thread(target=reserve, args=(first, "one")),
        threading.Thread(target=reserve, args=(second, "two")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert all(not thread.is_alive() for thread in threads)
    assert not errors
    assert sorted(results) == [False, True]
    assert (
        OfficialCompanyBudget.objects.get(pk="queue-pass:race").reserved_usd == ceiling
    )


def test_credential_rotation_requires_a_new_verification_even_if_gate_was_updated(
    tmp_path,
):
    from core.models import OfficialCompanyProviderState
    from core.official_company_queue_pass import freeze_queue, run_batch
    from tests.test_official_company_cycle import accept
    from x_monitor.config import OfficialCompanyConfig

    candidate(818, 1)
    candidate(819, 2)
    candidate(820, 3)
    manifest = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    cfg = OfficialCompanyConfig(
        enabled=True, max_usd_per_cycle=Decimal(1), max_usd_per_day=Decimal(1)
    )

    def call_v1(*args):
        return accept(*args)

    call_v1.credential_revision = "revision-one"

    def call_v2(*args):
        return accept(*args)

    call_v2.credential_revision = "revision-two"
    proof = tmp_path / "proof.json"
    first = run_batch(
        manifest, cfg=cfg, call=call_v1, limit=2, seconds=60, receipt_path=proof
    )
    assert first["reason"] == "verification_complete"
    OfficialCompanyProviderState.objects.filter(pk="deepinfra").update(
        credential_revision="revision-two", blocked_reason=""
    )
    second = run_batch(
        manifest, cfg=cfg, call=call_v2, limit=2, seconds=60, receipt_path=proof
    )
    assert second["reason"] == "verification_complete"
    assert second["evaluator_invocations"] == 1
    assert second["report"]["counts"] == {"completed": 2, "pending": 1}


def test_stale_concurrent_batch_rechecks_run_failure_under_lock(tmp_path, monkeypatch):
    import threading
    from unittest.mock import Mock

    from django.db import connections

    from core import official_company_queue_pass as queue
    from x_monitor.config import OfficialCompanyConfig

    candidate(821, 1)
    candidate(822, 2)
    manifest = queue.freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    cfg = OfficialCompanyConfig(
        enabled=True, max_usd_per_cycle=Decimal(1), max_usd_per_day=Decimal(1)
    )
    captured, resume = threading.Event(), threading.Event()
    original_report = queue.report
    observed = []

    def report_with_stale_view(value):
        result = original_report(value)
        if threading.current_thread().name == "stale" and not captured.is_set():
            captured.set()
            assert resume.wait(timeout=20)
        return result

    monkeypatch.setattr(queue, "report", report_with_stale_view)

    def stale_batch():
        try:
            call = Mock()
            result = queue.run_batch(
                manifest,
                cfg=cfg,
                call=call,
                limit=2,
                seconds=60,
                receipt_path=tmp_path / "proof.json",
            )
            observed.append((result["reason"], call.call_count))
        finally:
            connections.close_all()

    thread = threading.Thread(target=stale_batch, name="stale")
    thread.start()
    try:
        assert captured.wait(timeout=10)
        failing = Mock(side_effect=TimeoutError())
        first = queue.run_batch(
            manifest,
            cfg=cfg,
            call=failing,
            limit=1,
            seconds=60,
            receipt_path=tmp_path / "proof.json",
        )
        assert first["reason"] == "evaluation_not_verified"
    finally:
        resume.set()
        thread.join(timeout=30)
    assert not thread.is_alive()
    assert observed == [("unresolved_run_attempt", 0)]


def test_known_cost_failure_requires_acknowledgement_before_continuing(tmp_path):
    from core.official_company_queue_pass import (
        acknowledge_failure,
        freeze_queue,
        run_batch,
    )
    from tests.test_official_company_cycle import accept
    from x_monitor.config import OfficialCompanyConfig

    candidate(823, 1)
    candidate(824, 2)
    cfg = OfficialCompanyConfig(
        enabled=True, max_usd_per_cycle=Decimal(1), max_usd_per_day=Decimal(1)
    )
    manifest = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    proof = tmp_path / "proof.json"

    def invalid(*args):
        return {"usage": {"input_tokens": 10, "output_tokens": 2}}

    first = run_batch(
        manifest, cfg=cfg, call=invalid, limit=2, seconds=60, receipt_path=proof
    )
    assert first["reason"] == "evaluation_not_verified"
    failed_id = first["report"]["members"][0]["attempt_id"]
    assert (
        run_batch(
            manifest, cfg=cfg, call=accept, limit=2, seconds=60, receipt_path=proof
        )["reason"]
        == "evaluation_failed"
    )
    acknowledge_failure(
        manifest,
        attempt_id=failed_id,
        reason="invalid response reviewed",
        acknowledgement_path=str(proof) + ".acknowledged.json",
    )
    resumed = run_batch(
        manifest, cfg=cfg, call=accept, limit=2, seconds=60, receipt_path=proof
    )
    assert resumed["reason"] == "verification_complete"
    assert resumed["report"]["counts"] == {"failed": 1, "completed": 1}


def test_unknown_cost_failure_cannot_be_acknowledged(tmp_path):
    from unittest.mock import Mock

    from core.models import OfficialCompanyAttempt
    from core.official_company_queue_pass import (
        acknowledge_failure,
        freeze_queue,
        run_batch,
    )
    from x_monitor.config import OfficialCompanyConfig

    candidate(825, 1)
    cfg = OfficialCompanyConfig(
        enabled=True, max_usd_per_cycle=Decimal(1), max_usd_per_day=Decimal(1)
    )
    manifest = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    run_batch(
        manifest,
        cfg=cfg,
        call=Mock(side_effect=TimeoutError()),
        limit=1,
        seconds=60,
        receipt_path=tmp_path / "proof.json",
    )
    attempt = OfficialCompanyAttempt.objects.get()
    with pytest.raises(ValueError, match="known-cost"):
        acknowledge_failure(
            manifest,
            attempt_id=attempt.pk,
            reason="unknown",
            acknowledgement_path=tmp_path / "ack.json",
        )
    assert not (tmp_path / "ack.json").exists()
