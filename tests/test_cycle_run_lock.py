from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from io import StringIO

import pytest
from django.core.management import call_command
from django.db import connections

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def wait_for_live_queue():
    import time

    from monitor.run_lock import backfill_yield_requested

    until = time.monotonic() + 3
    while time.monotonic() < until:
        if backfill_yield_requested():
            return
        time.sleep(0.005)
    pytest.fail("live writer did not join the actual PostgreSQL lock queue")


def test_writer_lock_is_nonstealing_and_exposes_repeated_contention_context():
    from monitor.run_lock import harvest_writer_lock

    events = []

    def contend(run_id):
        with harvest_writer_lock(
            execution_mode="backfill",
            entrypoint="test.backfill",
            run_id=run_id,
            environment="u9-shared-lock",
            on_contention=events.append,
        ) as lease:
            return lease

    with harvest_writer_lock(
        execution_mode="live",
        entrypoint="test.scheduled",
        run_id="holder-run",
        environment="u9-shared-lock",
    ) as holder:
        assert holder.acquired
        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(contend, "loser-1").result()
            second = pool.submit(contend, "loser-2").result()

        assert not first.acquired
        assert not second.acquired
        assert first.contention is not None
        assert first.contention.owner_backend_pid == holder.backend_pid
        assert "holder-run" in first.contention.owner_context
        # Each Render cron run can start in a fresh process, so the first
        # observed contention must already be alert-worthy. The local count is
        # useful context but cannot be the only alert trigger.
        assert first.contention.alert_required is True
        assert second.contention is not None
        assert second.contention.alert_required is True
        assert second.contention.consecutive_count == 2

    assert len(events) == 2
    with harvest_writer_lock(
        execution_mode="backfill",
        entrypoint="test.backfill",
        run_id="after-release",
        environment="u9-shared-lock",
    ) as after_release:
        assert after_release.acquired


def test_closing_owner_connection_releases_advisory_lock():
    from monitor.run_lock import harvest_writer_lock

    with harvest_writer_lock(
        execution_mode="live",
        entrypoint="test.crash",
        run_id="closing-owner",
        environment="u9-connection-close",
    ) as owner:
        assert owner.acquired
        connections["default"].close()

    with harvest_writer_lock(
        execution_mode="live",
        entrypoint="test.recovery",
        run_id="new-owner",
        environment="u9-connection-close",
    ) as recovered:
        assert recovered.acquired


def test_all_write_entrypoints_stop_before_calls_or_state_writes_on_contention(
    monkeypatch,
):
    # Import module-level aliases before replacing their source functions.
    # Importing tasks after patching x_monitor.config.load_config would bind the
    # fake as the value monkeypatch later "restores", leaking it to later tests.
    import monitor.management.commands.backfill as backfill_module
    import monitor.tasks as tasks_module
    from monitor.run_lock import WriterLockContention, WriterLockLease

    invocations = []
    contention = WriterLockContention(
        kind="writer_lock_contended",
        environment="production",
        execution_mode="live",
        entrypoint="holder",
        run_id="loser",
        owner_backend_pid=123,
        owner_context="harvest:live:holder:owner-run",
        consecutive_count=1,
        alert_required=False,
    )

    @contextmanager
    def contended_lock(**kwargs):
        invocations.append(kwargs)
        yield WriterLockLease(
            acquired=False,
            environment="production",
            execution_mode=kwargs["execution_mode"],
            entrypoint=kwargs["entrypoint"],
            run_id="loser",
            backend_pid=456,
            contention=contention,
        )

    def forbidden(*args, **kwargs):
        raise AssertionError("contended entrypoint performed work")

    monkeypatch.setattr("monitor.run_lock.harvest_writer_lock", contended_lock)
    monkeypatch.setattr("monitor.cycle.CycleRunner", forbidden)
    monkeypatch.setattr("x_monitor.config.load_config", forbidden)

    monkeypatch.setattr(backfill_module, "load_config", forbidden)
    monkeypatch.setattr(backfill_module, "_save_state", forbidden)
    monkeypatch.setattr(tasks_module, "load_config", forbidden)

    call_command("run_cycle", stdout=StringIO(), stderr=StringIO())
    tasks_module.run_cycle.run(dry_run=False)
    call_command(
        "backfill",
        "--since",
        "2026-08-01",
        "--until",
        "2026-08-02",
        stdout=StringIO(),
        stderr=StringIO(),
    )

    assert [call["entrypoint"] for call in invocations] == [
        "management.run_cycle",
        "celery.run_cycle",
        "management.backfill",
    ]
    assert [call["execution_mode"] for call in invocations] == [
        "live",
        "live",
        "backfill",
    ]


def test_backfill_dry_run_is_truly_read_only(monkeypatch, tmp_path):
    import monitor.management.commands.backfill as backfill_module

    state_file = tmp_path / "backfill-state.json"
    state_file.write_text("{}")

    monkeypatch.setattr(backfill_module, "_state_path", lambda *_: state_file)
    monkeypatch.setattr(backfill_module, "load_config", lambda *_: object())
    monkeypatch.setattr("monitor.cycle.plan_calls_for_cycle", lambda _cfg: [])

    call_command(
        "backfill",
        "--since",
        "2026-08-01",
        "--until",
        "2026-08-02",
        "--dry-run",
        "--reset",
        stdout=StringIO(),
        stderr=StringIO(),
    )

    assert state_file.read_text() == "{}"


def test_scheduled_command_waits_for_backfill_then_executes(monkeypatch):
    """A busy historical page must delay a live tick, never discard it."""
    import threading
    import time

    from monitor.management.commands.run_cycle import Command
    from monitor.run_lock import harvest_writer_lock

    entered = threading.Event()
    attempted = threading.Event()
    observed = []

    def execute(self, *args, **options):
        observed.append(options)
        entered.set()

    monkeypatch.setattr(Command, "_handle", execute)

    def scheduled():
        try:
            attempted.set()
            call_command("run_cycle", scheduled=True, stdout=StringIO(), stderr=StringIO())
        finally:
            connections["default"].close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with harvest_writer_lock(execution_mode="backfill", entrypoint="test.historical.page") as owner:
            assert owner.acquired
            future = pool.submit(scheduled)
            assert attempted.wait(2)
            time.sleep(0.15)
            assert not entered.is_set(), "live work must never overlap the historical writer"
        future.result(timeout=5)
    assert entered.is_set(), "scheduled live tick was discarded instead of waiting for backfill"
    assert len(observed) == 1
    assert observed[0]["_collection_window_end"].tzinfo is not None
    assert observed[0]["_cycle_started_monotonic"] > 0


@pytest.mark.parametrize("kind", ["api", "llm"])
def test_live_waiter_stops_new_paid_work_and_wins_next_lock(kind):
    import threading

    from monitor.backfill_resources import BackfillBudget, BackfillBudgetExhausted
    from monitor.run_lock import backfill_yield_requested, harvest_writer_lock

    entered, release = threading.Event(), threading.Event()
    budget = BackfillBudget(max_api_requests=3, max_llm_calls=3, run_seconds=30)

    def live():
        try:
            with harvest_writer_lock(execution_mode="live", entrypoint="test.scheduled",
                                     wait_for_backfill_seconds=3) as lease:
                assert lease.acquired
                entered.set()
                assert release.wait(5)
                return lease
        finally:
            connections["default"].close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        try:
            with harvest_writer_lock(execution_mode="backfill", entrypoint="test.page") as holder:
                assert holder.acquired
                future = pool.submit(live)
                wait_for_live_queue()
                assert not entered.is_set()
                with pytest.raises(BackfillBudgetExhausted, match="yielding to queued live"):
                    getattr(budget, f"claim_{kind}_request")(1)
                assert budget.snapshot()["api_requests"] == budget.snapshot()["llm_requests"] == 0
                # A response already received is retained despite yielding.
                budget.record_api_response({"raw_results": 20})
            # The queued live lock must win even if this process immediately
            # attempts another page. Repeat attempts cannot barge ahead.
            for _ in range(12):
                with harvest_writer_lock(execution_mode="backfill", entrypoint="test.next-page") as next_page:
                    assert not next_page.acquired
            assert entered.wait(3)
        finally:
            release.set()
        assert future.result(timeout=5).waited_seconds > 0
    with harvest_writer_lock(execution_mode="backfill", entrypoint="test.resumed") as resumed:
        assert resumed.acquired
        assert not backfill_yield_requested()
        getattr(budget, f"claim_{kind}_request")(1)
    assert budget.snapshot()[f"{kind}_requests"] == 1
    assert budget.snapshot()["api_responses"] == [{"raw_results": 20}]


def test_live_wait_timeout_is_bounded_and_restores_session_settings():
    import time

    from monitor.run_lock import harvest_writer_lock

    def live():
        db = connections["default"]
        try:
            with db.cursor() as cursor:
                cursor.execute("SELECT set_config('application_name', 'test-original', false)")
                cursor.execute("SELECT set_config('lock_timeout', '1234ms', false)")
            started = time.monotonic()
            with harvest_writer_lock(execution_mode="live", entrypoint="test.timeout",
                                     wait_for_backfill_seconds=0.05) as lease:
                assert not lease.acquired
                assert lease.contention.kind == "writer_lock_wait_timeout"
                assert lease.contention.alert_required
            elapsed = time.monotonic() - started
            with db.cursor() as cursor:
                cursor.execute("SHOW application_name")
                assert cursor.fetchone()[0] == "test-original"
                cursor.execute("SHOW lock_timeout")
                assert cursor.fetchone()[0] == "1234ms"
            assert 0.04 <= elapsed < 2
        finally:
            db.close()

    with harvest_writer_lock(execution_mode="backfill", entrypoint="test.slow-page") as holder:
        assert holder.acquired
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(live).result(timeout=5)
    with harvest_writer_lock(execution_mode="live", entrypoint="test.after-timeout") as after:
        assert after.acquired


def test_scheduled_timeout_is_nonzero_and_never_calls_runner(monkeypatch):
    from django.core.management.base import CommandError

    import monitor.run_lock as locking
    from monitor.management.commands.run_cycle import Command

    real_lock = locking.harvest_writer_lock

    def short_wait(**kwargs):
        assert kwargs["wait_for_backfill_seconds"] == 120
        return real_lock(**{**kwargs, "wait_for_backfill_seconds": 0.03})

    monkeypatch.setattr(locking, "harvest_writer_lock", short_wait)
    monkeypatch.setattr(Command, "_handle", lambda *_a, **_k: pytest.fail("timed out command executed"))

    def scheduled():
        try:
            with pytest.raises(CommandError, match="live_harvest_backfill_writer_wait_timeout"):
                call_command("run_cycle", scheduled=True, stdout=StringIO(), stderr=StringIO())
        finally:
            connections["default"].close()

    with real_lock(execution_mode="backfill", entrypoint="test.timeout-owner") as holder:
        assert holder.acquired
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(scheduled).result(timeout=5)


def test_waiting_never_steals_from_live_or_other_writer():
    import time

    from monitor.run_lock import harvest_writer_lock

    def another_live():
        try:
            started = time.monotonic()
            with harvest_writer_lock(execution_mode="live", entrypoint="test.duplicate",
                                     wait_for_backfill_seconds=2) as lease:
                assert not lease.acquired
                assert lease.contention.kind == "writer_lock_contended"
                assert lease.waited_seconds == 0
            assert time.monotonic() - started < 1
        finally:
            connections["default"].close()

    for mode in ("live", "manual-repair"):
        with harvest_writer_lock(execution_mode=mode, entrypoint="test.owner") as holder:
            assert holder.acquired
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(another_live).result(timeout=5)


def test_backfill_connection_death_hands_lock_to_waiting_live_writer():
    from monitor.run_lock import backfill_yield_requested, harvest_writer_lock

    def live():
        try:
            with harvest_writer_lock(execution_mode="live", entrypoint="test.crash-recovery",
                                     wait_for_backfill_seconds=3) as lease:
                return lease.acquired
        finally:
            connections["default"].close()

    with (
        ThreadPoolExecutor(max_workers=1) as pool,
        harvest_writer_lock(execution_mode="backfill", entrypoint="test.crashing") as owner,
    ):
        assert owner.acquired
        future = pool.submit(live)
        wait_for_live_queue()
        connections["default"].close()
        assert future.result(timeout=5)
    assert not backfill_yield_requested()


@pytest.mark.parametrize("mode", ["backfill", "live"])
def test_writer_body_exception_releases_lock_and_cooperative_context(mode):
    from monitor.run_lock import backfill_yield_requested, harvest_writer_lock

    with (
        pytest.raises(RuntimeError, match="test-body"),
        harvest_writer_lock(execution_mode=mode, entrypoint="test.exception") as owner,
    ):
        assert owner.acquired
        raise RuntimeError("test-body")
    assert not backfill_yield_requested()
    with harvest_writer_lock(execution_mode="live", entrypoint="test.next") as next_writer:
        assert next_writer.acquired


@pytest.mark.parametrize("value", [-1, 121, float("inf"), float("nan")])
def test_writer_wait_rejects_unbounded_or_invalid_values(value):
    from monitor.run_lock import harvest_writer_lock

    with (
        pytest.raises(ValueError, match="between 0 and 120"),
        harvest_writer_lock(execution_mode="live", entrypoint="test.invalid", wait_for_backfill_seconds=value),
    ):
        pytest.fail("invalid wait acquired lock")


def test_provider_worker_thread_honors_owner_live_priority():
    from monitor.backfill_resources import BackfillBudget, BackfillBudgetExhausted
    from monitor.run_lock import harvest_writer_lock

    budget = BackfillBudget(max_api_requests=2, max_llm_calls=2, run_seconds=30)

    def live():
        try:
            with harvest_writer_lock(execution_mode="live", entrypoint="test.queued",
                                     wait_for_backfill_seconds=3) as lease:
                assert lease.acquired
        finally:
            connections["default"].close()

    def model_worker():
        try:
            with pytest.raises(BackfillBudgetExhausted, match="yielding to queued live"):
                budget.claim_llm_request(1)
        finally:
            connections["default"].close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        with harvest_writer_lock(execution_mode="backfill", entrypoint="test.page"):
            budget.claim_api_request(1)
            pending = pool.submit(live)
            wait_for_live_queue()
            pool.submit(model_worker).result(timeout=3)
        pending.result(timeout=5)
    assert budget.snapshot()["api_requests"] == 1
    assert budget.snapshot()["llm_requests"] == 0


def test_contention_callback_exception_restores_database_session():
    from monitor.run_lock import harvest_writer_lock

    def callback(_event):
        raise RuntimeError("callback-failed")

    def contend():
        db = connections["default"]
        try:
            with db.cursor() as cursor:
                cursor.execute("SELECT set_config('application_name', 'before-callback', false)")
            with (
                pytest.raises(RuntimeError, match="callback-failed"),
                harvest_writer_lock(execution_mode="backfill", entrypoint="test.callback", on_contention=callback),
            ):
                pytest.fail("contender acquired lock")
            with db.cursor() as cursor:
                cursor.execute("SHOW application_name")
                assert cursor.fetchone()[0] == "before-callback"
        finally:
            db.close()

    with (
        harvest_writer_lock(execution_mode="live", entrypoint="test.original"),
        ThreadPoolExecutor(max_workers=1) as pool,
    ):
        pool.submit(contend).result(timeout=5)


def test_live_tick_survives_owner_releasing_between_try_and_inspection(monkeypatch):
    import threading

    import monitor.run_lock as locking

    held, release = threading.Event(), threading.Event()
    inspect_owner = locking._owner_context
    inspections = []

    def historical():
        try:
            with locking.harvest_writer_lock(execution_mode="backfill", entrypoint="test.last-page"):
                held.set()
                assert release.wait(5)
        finally:
            connections["default"].close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        owner = pool.submit(historical)
        assert held.wait(3)

        def disappearing_owner(*args):
            if not inspections:
                inspections.append(True)
                release.set()
                owner.result(timeout=3)
            return inspect_owner(*args)

        monkeypatch.setattr(locking, "_owner_context", disappearing_owner)
        try:
            with locking.harvest_writer_lock(execution_mode="live", entrypoint="test.scheduled",
                                             wait_for_backfill_seconds=3) as lease:
                assert lease.acquired, "a released background owner must not discard the live tick"
        finally:
            release.set()
        owner.result(timeout=3)
