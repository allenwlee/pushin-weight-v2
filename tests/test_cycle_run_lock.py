from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from io import StringIO

import pytest
from django.core.management import call_command
from django.db import connections

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


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

    import monitor.management.commands.backfill as backfill_module
    import monitor.tasks as tasks_module

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
    monkeypatch.setattr(
        "monitor.cycle.plan_calls_for_cycle", lambda _cfg: []
    )

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
