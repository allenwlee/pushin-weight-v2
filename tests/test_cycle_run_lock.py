from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from io import StringIO
from types import SimpleNamespace

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


def test_live_write_entrypoints_stop_before_calls_or_state_writes_on_contention(
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

    import monitor.tasks as tasks_module

    monkeypatch.setattr(tasks_module, "load_config", forbidden)

    call_command("run_cycle", stdout=StringIO(), stderr=StringIO())
    tasks_module.run_cycle.run(dry_run=False)

    assert [call["entrypoint"] for call in invocations] == [
        "management.run_cycle",
        "celery.run_cycle",
    ]
    assert [call["execution_mode"] for call in invocations] == [
        "live",
        "live",
    ]


def test_backfill_contention_keeps_durable_job_pending_without_http(monkeypatch):
    from core.models import BackfillJob, HarvestBacklogWindow

    api = SimpleNamespace(max_retries=2, calls=[])

    @contextmanager
    def contended_lock(**kwargs):
        yield SimpleNamespace(acquired=False, contention=None)

    monkeypatch.setattr("monitor.run_lock.harvest_writer_lock", contended_lock)
    monkeypatch.setattr("x_monitor.apify.TwitterApiClient.from_env", lambda: api)
    monkeypatch.setattr(
        "x_monitor.reattribute.build_relevancy_client_from_env", lambda cfg: None
    )

    stdout = StringIO()
    call_command(
        "backfill",
        since="2026-08-01",
        until="2026-08-02",
        batch_size=1,
        pause=0,
        stdout=stdout,
        stderr=StringIO(),
    )

    job = BackfillJob.objects.get()
    assert "shared harvest writer lock is held" in stdout.getvalue()
    assert api.max_retries == 0
    assert api.calls == []
    assert job.windows.count() == 7
    assert not job.windows.exclude(state=HarvestBacklogWindow.State.PENDING).exists()


def test_backfill_dry_run_is_truly_read_only(monkeypatch):
    from core.models import BackfillJob, HarvestBacklogWindow

    monkeypatch.setattr(
        "x_monitor.apify.TwitterApiClient.from_env",
        lambda: pytest.fail("dry-run must not construct a provider client"),
    )

    call_command(
        "backfill",
        since="2026-08-01",
        until="2026-08-02",
        dry_run=True,
        stdout=StringIO(),
        stderr=StringIO(),
    )

    assert not BackfillJob.objects.exists()
    assert not HarvestBacklogWindow.objects.exists()
