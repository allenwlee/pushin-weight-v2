from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from core.models import Account, DataSource
from core.official_company_accounts import enqueue_account

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


@pytest.fixture(autouse=True)
def ignore_clock_window(monkeypatch):
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "test")
    monkeypatch.setattr(
        "core.official_company_queue_pass._near_scheduled_tick", lambda timeout: False
    )


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
    assert reconciled["members"][0]["input_tokens"] == 100
    assert reconciled["members"][0]["output_tokens"] == 100
    assert Decimal(reconciled["members"][0]["actual_usd"]) > 0
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
    credential_envs = []
    def build_call(cfg, *, credential_env):
        credential_envs.append(credential_env)
        return accept
    monkeypatch.setattr("core.official_company_discovery.build_discovery_call", build_call)
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
    assert credential_envs == ["DEEPINFRA_ON_DEMAND"]
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


def test_queue_pass_yields_while_another_connection_holds_harvest_lock(tmp_path):
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
        assert result["reason"] == "harvest_active"
        assert result["evaluator_invocations"] == 0
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
    OfficialCompanyProviderState.objects.filter(pk="deepinfra-on-demand").update(
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


def test_precutoff_unknown_attempt_is_not_redispatched(tmp_path):
    from unittest.mock import Mock

    from core.official_company_accounts import evaluate_account
    from core.official_company_queue_pass import freeze_queue, report, run_batch
    from x_monitor.config import OfficialCompanyConfig

    state = candidate(826, 1)
    cfg = OfficialCompanyConfig(
        enabled=True, max_usd_per_cycle=Decimal(1), max_usd_per_day=Decimal(1)
    )
    call = Mock(side_effect=TimeoutError())
    assert evaluate_account(state.pk, cfg=cfg, call=call, budget_scope="old")
    state.refresh_from_db()
    state.next_attempt_at = timezone.now() - timedelta(seconds=1)
    state.save()
    manifest = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    assert report(manifest)["members"][0]["disposition"] == "unknown_call"
    result = run_batch(
        manifest,
        cfg=cfg,
        call=call,
        limit=1,
        seconds=60,
        receipt_path=tmp_path / "proof.json",
    )
    assert result["evaluator_invocations"] == 0
    assert call.call_count == 1


def test_snapshot_detects_attempt_committed_after_snapshot(tmp_path):
    import json
    import threading

    from django.db import connections, transaction

    from core.official_company_accounts import claim_account, complete_attempt
    from core.official_company_queue_pass import freeze_queue, report
    from tests.test_official_company_cycle import accept
    from x_monitor.config import OfficialCompanyConfig

    state = candidate(827, 1)
    cfg = OfficialCompanyConfig(
        enabled=True, max_usd_per_cycle=Decimal(1), max_usd_per_day=Decimal(1)
    )
    claimed, release = threading.Event(), threading.Event()
    errors = []

    def concurrent_claim():
        try:
            with transaction.atomic():
                attempt = claim_account(state.pk, cfg=cfg, budget_scope="concurrent")
                claimed.set()
                assert release.wait(timeout=20)
            complete_attempt(
                attempt.pk,
                cfg=cfg,
                response=accept(
                    "model-llm model-other", json.dumps(attempt.evidence), "model", 100
                ),
            )
        except Exception as exc:  # noqa: BLE001 - report worker failures in the test thread
            errors.append(exc)
        finally:
            connections.close_all()

    thread = threading.Thread(target=concurrent_claim)
    thread.start()
    try:
        assert claimed.wait(timeout=10)
        manifest = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    finally:
        release.set()
        thread.join(timeout=30)
    assert not thread.is_alive() and not errors
    assert manifest["members"][0]["baseline_attempt_ids"] == []
    assert report(manifest)["members"][0]["disposition"] == "completed"


def test_waiting_only_snapshot_never_claims_complete(tmp_path):
    from unittest.mock import Mock

    from core.official_company_queue_pass import freeze_queue, run_batch
    from x_monitor.config import OfficialCompanyConfig

    state = candidate(828, 1, "retry_due")
    state.next_attempt_at = timezone.now() + timedelta(hours=1)
    state.save()
    manifest = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    cfg = OfficialCompanyConfig(
        enabled=True, max_usd_per_cycle=Decimal(1), max_usd_per_day=Decimal(1)
    )
    result = run_batch(
        manifest,
        cfg=cfg,
        call=Mock(),
        limit=5,
        seconds=60,
        receipt_path=tmp_path / "proof.json",
    )
    assert result["reason"] == "batch_finished"
    assert result["report"]["counts"] == {"waiting_retry": 1}


def test_command_completes_and_resumes_frozen_three_tier_pass(tmp_path, monkeypatch):
    import json
    import time
    from io import StringIO
    from types import SimpleNamespace
    from unittest.mock import Mock

    from django.core.management import call_command

    from core.models import (
        BrandAccount,
        CompanyAccount,
        OfficialCompanyAttempt,
        OfficialCompanyListIntent,
    )
    from tests.test_official_company_cycle import accept
    from x_monitor.config import OfficialCompanyConfig

    states = [candidate(829, 1), candidate(830, 2), candidate(831, 3)]
    cfg = OfficialCompanyConfig(
        enabled=True, max_usd_per_cycle=Decimal(1), max_usd_per_day=Decimal(1)
    )
    call = Mock(side_effect=accept)
    monkeypatch.setattr(
        "x_monitor.config.load_config",
        lambda path: SimpleNamespace(official_company=cfg),
    )
    monkeypatch.setattr(
        "core.official_company_discovery.build_discovery_call", lambda cfg, **kwargs: call
    )
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    path = str(tmp_path / "manifest.json")
    call_command(
        "official_company_queue_pass",
        "freeze",
        manifest=path,
        total_limit_usd="2",
        stdout=StringIO(),
    )
    arrival = candidate(832, 1)
    for limit in (1, 1, 2):
        call_command(
            "official_company_queue_pass",
            "run",
            manifest=path,
            limit=limit,
            seconds=60,
            stdout=StringIO(),
        )
    output = StringIO()
    call_command("official_company_queue_pass", "report", manifest=path, stdout=output)
    result = json.loads(output.getvalue())
    assert result["count"] == 3 and result["counts"] == {"completed": 3}
    assert result["outcomes_by_starting_priority"] == {
        "1": {"accepted": 1},
        "2": {"accepted": 1},
        "3": {"accepted": 1},
    }
    assert {row["state_id"] for row in result["members"]} == {s.pk for s in states}
    assert call.call_count == 3
    assert OfficialCompanyAttempt.objects.filter(state__in=states).count() == 3
    assert not OfficialCompanyAttempt.objects.filter(state=arrival).exists()
    assert not BrandAccount.objects.exists() and not CompanyAccount.objects.exists()
    assert not OfficialCompanyListIntent.objects.exists()


def test_uncertain_cost_reconciliation_is_audited_and_idempotent(tmp_path):
    from unittest.mock import Mock

    from core.models import OfficialCompanyAttempt, OfficialCompanyBudget
    from core.official_company_queue_pass import (
        freeze_queue,
        reconcile_uncertain,
        run_batch,
    )
    from x_monitor.config import OfficialCompanyConfig

    candidate(833, 1)
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
    keys = attempt.budget_keys
    assert all(OfficialCompanyBudget.objects.get(pk=k).reserved_usd > 0 for k in keys)
    kwargs = {
        "attempt_id": attempt.pk,
        "actual_usd": "0.0001",
        "evidence": "provider receipt abc",
        "reconciliation_path": tmp_path / "reconciled.json",
    }
    assert not reconcile_uncertain(manifest, **kwargs)["already_reconciled"]
    assert reconcile_uncertain(manifest, **kwargs)["already_reconciled"]
    attempt.refresh_from_db()
    assert attempt.actual_usd == Decimal("0.0001")
    assert all(OfficialCompanyBudget.objects.get(pk=k).reserved_usd == 0 for k in keys)
    assert all(
        OfficialCompanyBudget.objects.get(pk=k).spent_usd == Decimal("0.0001")
        for k in keys
    )
    with pytest.raises(ValueError, match="different reconciliation"):
        reconcile_uncertain(manifest, **{**kwargs, "actual_usd": "0"})


def test_scheduled_drain_skips_unresolved_claim_and_advances_next_retry(monkeypatch):
    from core.official_company_accounts import claim_account
    from core.official_company_discovery import drain_accounts
    from x_monitor.config import OfficialCompanyConfig

    blocked = candidate(834, 1)
    other = candidate(835, 1, "retry_due")
    cfg = OfficialCompanyConfig(
        enabled=True, max_usd_per_cycle=Decimal(1), max_usd_per_day=Decimal(1)
    )
    claim_account(blocked.pk, cfg=cfg, budget_scope="old-reservation")
    blocked.refresh_from_db()
    blocked.claim_expires_at = timezone.now() - timedelta(seconds=1)
    blocked.save()
    seen = []
    monkeypatch.setattr(
        "core.official_company_discovery.evaluate_account",
        lambda pk, **kwargs: seen.append(pk) or True,
    )
    result = drain_accounts(cfg=cfg, call=object(), limit=1, budget_scope="scheduled")
    assert result["attempted"] == 1
    assert seen == [other.pk]


def test_batch_yields_scheduled_window_and_real_scheduled_lane_proceeds(
    tmp_path, monkeypatch
):
    from unittest.mock import Mock

    from core.official_company_queue_pass import freeze_queue, run_batch
    from monitor.cycle import CycleRunner
    from tests.test_official_company_cycle import accept, config

    candidate(836, 1)
    manifest = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    cfg = config()
    call = Mock(side_effect=accept)
    monkeypatch.setattr(
        "core.official_company_queue_pass._near_scheduled_tick", lambda timeout: True
    )
    batch = run_batch(
        manifest,
        cfg=cfg.official_company,
        call=call,
        limit=1,
        seconds=60,
        receipt_path=tmp_path / "proof.json",
    )
    assert batch["reason"] == "scheduled_harvest_window"
    assert batch["evaluator_invocations"] == 0
    runner = CycleRunner(
        cfg=cfg,
        cycle_kind="scheduled",
        _official_company_call=call,
        _official_list_client=Mock(),
    )
    scheduled = runner._run_official_company_discovery(
        run_id="scheduled-after-yield", deadline=cfg.harvest.start_deadline()
    )
    assert scheduled["attempted"] == 1
    assert call.call_count == 1


def test_concurrent_completed_decision_preserves_earlier_unknown_cost(tmp_path):
    from unittest.mock import Mock

    from core.models import OfficialCompanyAttempt
    from core.official_company_accounts import evaluate_account
    from core.official_company_queue_pass import freeze_queue, report
    from tests.test_official_company_cycle import accept
    from x_monitor.config import OfficialCompanyConfig

    state = candidate(837, 1)
    cfg = OfficialCompanyConfig(
        enabled=True, max_usd_per_cycle=Decimal(1), max_usd_per_day=Decimal(1)
    )
    assert evaluate_account(
        state.pk, cfg=cfg, call=Mock(side_effect=TimeoutError()), budget_scope="old"
    )
    old_attempt = OfficialCompanyAttempt.objects.get()
    state.refresh_from_db()
    state.next_attempt_at = timezone.now() - timedelta(seconds=1)
    state.save()
    manifest = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    assert evaluate_account(
        state.pk, cfg=cfg, call=accept, budget_scope="scheduled-later"
    )
    row = report(manifest)["members"][0]
    assert row["disposition"] == "completed" and row["outcome"] == "accepted"
    assert row["unresolved_attempt_ids"] == [old_attempt.pk]


def test_superseded_legacy_reservation_does_not_block_scheduled_claim():
    from core.official_company_accounts import claim_account
    from x_monitor.config import OfficialCompanyConfig

    state = candidate(838, 1)
    cfg = OfficialCompanyConfig(
        enabled=True, max_usd_per_cycle=Decimal(1), max_usd_per_day=Decimal(1)
    )
    assert claim_account(state.pk, cfg=cfg, budget_scope="old")
    state.account.bio = "We develop a new reasoning model"
    state.account.save()
    current = enqueue_account(state.account)
    assert current.claim_token == "" and current.status == "pending"
    assert claim_account(current.pk, cfg=cfg, budget_scope="scheduled-new") is not None


def test_scheduled_drain_skips_queue_timeout_after_new_evidence(tmp_path, monkeypatch):
    from unittest.mock import Mock

    from core.official_company_discovery import drain_accounts
    from core.official_company_queue_pass import freeze_queue, run_batch
    from x_monitor.config import OfficialCompanyConfig

    state = candidate(839, 1)
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
    state.account.bio = "We develop a new reasoning model"
    state.account.save()
    state = enqueue_account(state.account)
    assert state.status == "pending"
    other = candidate(840, 1, "retry_due")
    seen = []
    monkeypatch.setattr(
        "core.official_company_discovery.evaluate_account",
        lambda pk, **kwargs: seen.append(pk) or True,
    )
    drain_accounts(cfg=cfg, call=object(), limit=1, budget_scope="scheduled")
    assert seen == [other.pk]


def test_environment_mismatch_blocks_before_any_model_call(tmp_path, monkeypatch):
    from unittest.mock import Mock

    from core.official_company_queue_pass import freeze_queue, read_manifest, run_batch
    from x_monitor.config import OfficialCompanyConfig

    candidate(841, 1)
    path = tmp_path / "queue.json"
    manifest = freeze_queue(path=path, total_limit=Decimal(2))
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "production")
    call = Mock()
    with pytest.raises(ValueError, match="environment"):
        read_manifest(path)
    with pytest.raises(ValueError, match="environment"):
        run_batch(
            manifest,
            cfg=OfficialCompanyConfig(enabled=True),
            call=call,
            limit=1,
            seconds=60,
            receipt_path=tmp_path / "proof.json",
        )
    call.assert_not_called()


def test_batch_rechecks_yield_immediately_before_dispatch(tmp_path, monkeypatch):
    from unittest.mock import Mock

    from core.official_company_queue_pass import freeze_queue, run_batch
    from x_monitor.config import OfficialCompanyConfig

    candidate(842, 1)
    manifest = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    cfg = OfficialCompanyConfig(
        enabled=True, max_usd_per_cycle=Decimal(1), max_usd_per_day=Decimal(1)
    )
    checks = iter([None, None, "scheduled_harvest_window"])
    monkeypatch.setattr(
        "core.official_company_queue_pass._harvest_yield_reason",
        lambda timeout: next(checks),
    )
    call = Mock()
    result = run_batch(
        manifest,
        cfg=cfg,
        call=call,
        limit=1,
        seconds=60,
        receipt_path=tmp_path / "proof.json",
    )
    assert result["reason"] == "scheduled_harvest_window"
    call.assert_not_called()


def test_concurrent_owner_attestation_is_not_a_model_failure(tmp_path):
    from core.models import OfficialCompanyAttempt
    from core.official_company_queue_pass import freeze_queue, report

    state = candidate(843, 1)
    manifest = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    state.status = "accepted"
    state.save()
    OfficialCompanyAttempt.objects.create(
        state=state,
        evidence_hash=state.evidence_hash,
        claim_token="owner-test",
        model="owner-attestation",
        policy_version="owner:test",
        status="owner_attested",
        reserved_usd=0,
        actual_usd=0,
    )
    assert report(manifest)["members"][0]["disposition"] == "owner_settled"


def test_report_observes_one_database_snapshot_during_concurrent_change(
    tmp_path, monkeypatch
):
    import threading

    from django.db import connections

    from core.models import OfficialCompanyAttempt
    from core.official_company_queue_pass import freeze_queue, report

    state = candidate(844, 1)
    manifest = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    captured, resume = threading.Event(), threading.Event()
    original_filter = OfficialCompanyAttempt.objects.filter

    def controlled_filter(*args, **kwargs):
        if threading.current_thread().name == "report-reader" and not captured.is_set():
            captured.set()
            assert resume.wait(timeout=20)
        return original_filter(*args, **kwargs)

    monkeypatch.setattr(OfficialCompanyAttempt.objects, "filter", controlled_filter)
    results, errors = [], []

    def read_report():
        try:
            results.append(report(manifest))
        except Exception as exc:  # noqa: BLE001 - report worker failures in the test thread
            errors.append(exc)
        finally:
            connections.close_all()

    thread = threading.Thread(target=read_report, name="report-reader")
    thread.start()
    try:
        assert captured.wait(timeout=10)
        state.status = "suppressed"
        state.save()
    finally:
        resume.set()
        thread.join(timeout=30)
    assert not thread.is_alive() and not errors
    assert results[0]["members"][0]["disposition"] == "pending"
    assert results[0]["observed_at"]
    assert report(manifest)["members"][0]["disposition"] == "suppressed"


def test_wrong_database_environment_is_refused_at_snapshot(tmp_path, monkeypatch):
    from core.official_company_queue_pass import freeze_queue

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "staging")
    with pytest.raises(ValueError, match="database identity"):
        freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    assert not (tmp_path / "queue.json").exists()


def test_zero_provider_prices_block_before_evaluation(tmp_path):
    from unittest.mock import Mock

    from core.official_company_queue_pass import freeze_queue, run_batch
    from x_monitor.config import OfficialCompanyConfig

    candidate(845, 1)
    manifest = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    cfg = OfficialCompanyConfig(
        enabled=True,
        max_usd_per_cycle=Decimal(1),
        max_usd_per_day=Decimal(1),
        input_usd_per_million=Decimal(0),
    )
    call = Mock()
    with pytest.raises(ValueError, match="positive configured"):
        run_batch(
            manifest,
            cfg=cfg,
            call=call,
            limit=1,
            seconds=60,
            receipt_path=tmp_path / "proof.json",
        )
    call.assert_not_called()


def test_completed_decision_with_unknown_cost_can_be_reconciled(tmp_path):
    from core.models import OfficialCompanyAttempt
    from core.official_company_queue_pass import (
        freeze_queue,
        reconcile_uncertain,
        report,
        run_batch,
    )
    from tests.test_official_company_cycle import accept
    from x_monitor.config import OfficialCompanyConfig

    state = candidate(846, 1)
    manifest = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    cfg = OfficialCompanyConfig(
        enabled=True, max_usd_per_cycle=Decimal(1), max_usd_per_day=Decimal(1)
    )

    def no_usage(*args):
        result = accept(*args)
        result.pop("usage")
        return result

    result = run_batch(
        manifest,
        cfg=cfg,
        call=no_usage,
        limit=1,
        seconds=60,
        receipt_path=tmp_path / "proof.json",
    )
    assert result["reason"] == "evaluation_not_verified"
    attempt = OfficialCompanyAttempt.objects.get()
    assert attempt.status == "completed" and attempt.actual_usd is None
    reconcile_uncertain(
        manifest,
        attempt_id=attempt.pk,
        actual_usd="0.0002",
        evidence="provider bill 123",
        reconciliation_path=tmp_path / "reconcile.json",
    )
    state.refresh_from_db()
    assert state.decision["outcome"] == "accepted"
    row = report(manifest)["members"][0]
    assert row["disposition"] == "completed" and row["actual_usd"] == "0.0002000000"


def test_price_change_requires_another_verification(tmp_path):
    from core.official_company_queue_pass import freeze_queue, run_batch
    from tests.test_official_company_cycle import accept
    from x_monitor.config import OfficialCompanyConfig

    candidate(847, 1)
    candidate(848, 2)
    candidate(849, 3)
    manifest = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    cfg = OfficialCompanyConfig(
        enabled=True, max_usd_per_cycle=Decimal(1), max_usd_per_day=Decimal(1)
    )
    proof = tmp_path / "proof.json"
    first = run_batch(
        manifest, cfg=cfg, call=accept, limit=2, seconds=60, receipt_path=proof
    )
    assert first["reason"] == "verification_complete"
    changed = cfg.model_copy(update={"input_usd_per_million": Decimal("0.12")})
    second = run_batch(
        manifest, cfg=changed, call=accept, limit=2, seconds=60, receipt_path=proof
    )
    assert second["reason"] == "verification_complete"
    assert second["evaluator_invocations"] == 1
    assert second["report"]["counts"] == {"completed": 2, "pending": 1}


def test_missing_provider_is_reported_before_claim(tmp_path, monkeypatch):
    from io import StringIO
    from types import SimpleNamespace

    from django.core.management import call_command
    from django.core.management.base import CommandError

    from core.models import OfficialCompanyAttempt
    from core.official_company_queue_pass import freeze_queue
    from x_monitor.config import OfficialCompanyConfig

    candidate(850, 1)
    path = tmp_path / "queue.json"
    freeze_queue(path=path, total_limit=Decimal(2))
    cfg = OfficialCompanyConfig(enabled=True)
    monkeypatch.setattr(
        "x_monitor.config.load_config",
        lambda path: SimpleNamespace(official_company=cfg),
    )
    monkeypatch.setattr(
        "core.official_company_discovery.build_discovery_call", lambda cfg, **kwargs: None
    )
    with pytest.raises(CommandError, match="provider is not configured"):
        call_command(
            "official_company_queue_pass", "run", manifest=str(path), stdout=StringIO()
        )
    assert not OfficialCompanyAttempt.objects.exists()


def test_production_name_on_wrong_cluster_cannot_use_production_locks(monkeypatch):
    from core.official_company_queue_pass import _environment

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "production")
    monkeypatch.setattr(
        "core.official_company_queue_pass._database_identity",
        lambda: {
            "name": "pushinweight_shadow",
            "system_identifier": "7673769124639031347",
        },
    )
    with pytest.raises(ValueError, match="database identity"):
        _environment()


def test_on_demand_gate_does_not_clear_scheduled_provider_block(tmp_path):
    from core.models import OfficialCompanyProviderState
    from core.official_company_queue_pass import freeze_queue, run_batch
    from tests.test_official_company_cycle import accept
    from x_monitor.config import OfficialCompanyConfig

    candidate(30001, 1)
    OfficialCompanyProviderState.objects.create(
        key="deepinfra", credential_revision="scheduled",
        blocked_reason="deepinfra_http_status_402",
    )
    def on_demand(*args):
        return accept(*args)
    on_demand.credential_revision = "on-demand-revision"
    cfg = OfficialCompanyConfig(
        enabled=True, max_usd_per_cycle=Decimal(1), max_usd_per_day=Decimal(1)
    )
    manifest = freeze_queue(path=tmp_path / "queue.json", total_limit=Decimal(2))
    result = run_batch(
        manifest, cfg=cfg, call=on_demand, limit=1, seconds=60,
        receipt_path=tmp_path / "proof.json",
    )
    assert result["reason"] == "verification_complete"
    scheduled = OfficialCompanyProviderState.objects.get(pk="deepinfra")
    assert scheduled.credential_revision == "scheduled"
    assert scheduled.blocked_reason == "deepinfra_http_status_402"
    assert OfficialCompanyProviderState.objects.get(pk="deepinfra-on-demand").credential_revision == "on-demand-revision"
