from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


SINCE = "2026-08-10T00:00"
UNTIL = "2026-08-10T04:00"


def test_explicit_dry_run_shows_current_fanout_and_cost_without_writes_or_clients(
    monkeypatch,
):
    from core.models import BackfillJob

    monkeypatch.setattr(
        "monitor.cycle.TwitterApiClient.from_env",
        lambda: pytest.fail("dry-run must not construct a provider client"),
    )
    stdout = StringIO()

    call_command(
        "backfill",
        since=SINCE,
        until=UNTIL,
        dry_run=True,
        stdout=stdout,
    )

    output = stdout.getvalue()
    assert "explicit range" in output
    assert "2026-08-10T00:00:00+00:00" in output
    assert "Calls (7): A, B1, C1, C2, C3, B2, B3" in output
    assert "TwitterAPI credits" in output
    assert "additional requests may be required" in output
    assert BackfillJob.objects.count() == 0


def test_detected_gap_dry_run_labels_inference_and_partial_outage_limit():
    from core.models import Post

    occupied = (
        [datetime(2026, 8, 10, 0, minute, tzinfo=UTC) for minute in (1, 16, 31, 46)]
        + [datetime(2026, 8, 10, 2, minute, tzinfo=UTC) for minute in (1, 16, 31, 46)]
        + [datetime(2026, 8, 10, 3, minute, tzinfo=UTC) for minute in (1, 16, 31, 46)]
    )
    for i, created_at in enumerate(occupied):
        Post.objects.create(tweet_id=f"coverage-{i}", text="x", created_at=created_at)
    stdout = StringIO()

    call_command(
        "backfill",
        since=SINCE,
        until=UNTIL,
        detect_gaps=True,
        dry_run=True,
        stdout=stdout,
    )

    output = stdout.getvalue()
    assert "inferred zero-coverage gaps" in output
    assert "2026-08-10T01:00:00+00:00 → 2026-08-10T02:00:00+00:00" in output
    assert "Partial outages are not detectable" in output


def test_execute_uses_one_runner_budget_and_releases_lock_before_pause(monkeypatch):
    from core.models import BackfillJob, HarvestBacklogWindow

    lock_active = False
    lock_entries = []
    pauses = []
    runner_inits = []
    replay_calls = []

    @contextmanager
    def lock(**kwargs):
        nonlocal lock_active
        lock_active = True
        lock_entries.append(kwargs)
        try:
            yield SimpleNamespace(acquired=True, contention=None)
        finally:
            lock_active = False

    class Runner:
        def __init__(self, **kwargs):
            runner_inits.append(kwargs)

        def replay_backlog_only(self, *, backfill_job, request_limit, **kwargs):
            assert lock_active is True
            assert request_limit == 1
            replay_calls.append(backfill_job.pk)
            row = backfill_job.windows.filter(state="pending").order_by("pk").first()
            assert row is not None
            row.state = HarvestBacklogWindow.State.COMPLETED
            row.save(update_fields=["state", "last_seen_at"])
            if not backfill_job.windows.exclude(state="completed").exists():
                backfill_job.state = BackfillJob.State.COMPLETED
                backfill_job.completed_at = datetime.now(UTC)
                backfill_job.save(update_fields=["state", "completed_at", "updated_at"])
            return {
                "backlog_replays": [
                    {"window_id": row.pk, "call_id": row.call_id, "status": "completed"}
                ],
                "llm_calls": 0,
                "errors": [],
            }

    def pause(seconds):
        assert lock_active is False
        pauses.append(seconds)

    monkeypatch.setattr("monitor.run_lock.harvest_writer_lock", lock)
    monkeypatch.setattr("monitor.cycle.CycleRunner", Runner)
    monkeypatch.setattr("time.sleep", pause)

    call_command(
        "backfill",
        since=SINCE,
        until=UNTIL,
        batch_size=2,
        pause=1,
        max_llm_calls=3,
        stdout=StringIO(),
    )

    job = BackfillJob.objects.get()
    assert len(runner_inits) == 1
    assert runner_inits[0]["_max_llm_calls"] == 3
    assert len(replay_calls) == 2
    assert len(lock_entries) == 2
    assert pauses == [1]
    assert job.windows.filter(state="completed").count() == 2
    assert job.windows.filter(state="pending").count() == 5


def test_plan_drift_refuses_before_lock_or_provider(monkeypatch):
    from core.models import BackfillJob
    from monitor.backfill import build_plan, persist_plan
    from x_monitor.config import load_config

    plan = build_plan(
        load_config(Path("config.yaml")),
        since=datetime(2026, 8, 10, tzinfo=UTC),
        until=datetime(2026, 8, 10, 4, tzinfo=UTC),
        detect_gaps=False,
    )
    job = persist_plan(plan)
    job.plan_signature = "0" * 64
    job.save(update_fields=["plan_signature", "updated_at"])
    monkeypatch.setattr(
        "monitor.run_lock.harvest_writer_lock",
        lambda **kwargs: pytest.fail("drift must stop before lock acquisition"),
    )

    with pytest.raises(CommandError, match="no longer matches"):
        call_command("backfill", since=SINCE, until=UNTIL)
    assert BackfillJob.objects.count() == 1


def test_pricing_failure_happens_before_job_creation(monkeypatch):
    from core.models import BackfillJob
    from scripts.harvest_cost import PricingError

    monkeypatch.setattr(
        "scripts.harvest_cost.load_pricing",
        lambda **kwargs: (_ for _ in ()).throw(PricingError("missing pricing")),
    )

    with pytest.raises(CommandError, match="missing pricing"):
        call_command("backfill", since=SINCE, until=UNTIL)
    assert BackfillJob.objects.count() == 0


def test_exact_reset_removes_only_matching_job_and_never_scheduled_rows():
    from core.models import BackfillJob, HarvestBacklogWindow
    from monitor.backfill import build_plan, persist_plan
    from monitor.cycle import _cursor_key
    from x_monitor.config import load_config

    cfg = load_config(Path("config.yaml"))
    first_plan = build_plan(
        cfg,
        since=datetime(2026, 8, 10, tzinfo=UTC),
        until=datetime(2026, 8, 10, 4, tzinfo=UTC),
        detect_gaps=False,
    )
    second_plan = build_plan(
        cfg,
        since=datetime(2026, 8, 11, tzinfo=UTC),
        until=datetime(2026, 8, 11, 4, tzinfo=UTC),
        detect_gaps=False,
    )
    first = persist_plan(first_plan)
    second = persist_plan(second_plan)
    call = first_plan.calls[0]
    now = datetime.now(UTC)
    scheduled = HarvestBacklogWindow.objects.create(
        **_cursor_key(call),
        original_since=now - timedelta(minutes=15),
        original_until=now,
        remaining_since=now - timedelta(minutes=15),
        remaining_until=now,
        reason_code="page_cap",
    )

    call_command(
        "backfill",
        since=SINCE,
        until=UNTIL,
        reset=True,
        stdout=StringIO(),
    )

    assert not BackfillJob.objects.filter(pk=first.pk).exists()
    assert BackfillJob.objects.filter(pk=second.pk).exists()
    assert HarvestBacklogWindow.objects.filter(pk=scheduled.pk).exists()
