from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone

from core.models import BackfillJob, CallState, HarvestBacklogWindow
from monitor.cycle import CycleRunner, _cursor_key
from x_monitor.config import BacklogConfig, Config, HarvestConfig
from x_monitor.query_plan import PlannedCall

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def _call() -> PlannedCall:
    return PlannedCall(
        call_id="B1",
        call_kind="brand_wide",
        brand_id="deepseek",
        bucket=None,
        query_string="deepseek",
        query_length=8,
    )


def _job(*, key: str = "a" * 64) -> BackfillJob:
    now = timezone.now().replace(microsecond=0)
    return BackfillJob.objects.create(
        key=key,
        requested_since=now - timedelta(hours=1),
        requested_until=now,
        selection_mode=BackfillJob.SelectionMode.EXPLICIT,
        selected_intervals=[],
        plan_signature="b" * 64,
    )


def _window(call: PlannedCall, *, job: BackfillJob | None):
    now = timezone.now().replace(microsecond=0)
    return HarvestBacklogWindow.objects.create(
        backfill_job=job,
        **_cursor_key(call),
        original_since=now - timedelta(minutes=15),
        original_until=now,
        remaining_since=now - timedelta(minutes=15),
        remaining_until=now,
        reason_code="backfill_explicit" if job else "page_cap",
    )


def _runner() -> CycleRunner:
    return CycleRunner(
        cfg=Config(
            enabled_models=["deepseek"],
            daily_ceiling=100,
            harvest=HarvestConfig(
                backlog=BacklogConfig(
                    max_attempts=8,
                    max_age_hours=24,
                    replays_per_cycle=5,
                )
            ),
        ),
        cycle_kind="backfill",
        _brand_filter=["deepseek"],
    )


class Deadline:
    def can_start(self, seconds):
        return True

    def remaining(self):
        return 60.0


class CapturingApi:
    timeout_s = 1
    max_retries = 0

    def __init__(self, response=([], False)):
        self.response = response
        self.calls = []

    def run_search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return self.response


def _replay(
    runner,
    *,
    call,
    api,
    job,
    kept_all=None,
    include_quarantined=False,
):
    return runner._replay_backlog(
        calls=[call],
        api=api,
        index=None,
        search_terms={},
        kept_all=kept_all if kept_all is not None else [],
        run_id="job-replay",
        deadline=Deadline(),
        include_quarantined=include_quarantined,
        quarantined_only=include_quarantined,
        backfill_job=job,
        replay_limit=1,
        single_page=True,
    )


def test_job_replay_is_scoped_one_request_and_retains_completed_audit_row():
    call = _call()
    job = _job()
    owned = _window(call, job=job)
    scheduled = _window(call, job=None)
    other_job = _job(key="c" * 64)
    other = _window(call, job=other_job)
    api = CapturingApi()

    reports = _replay(_runner(), call=call, api=api, job=job)

    assert reports[0]["status"] == "completed"
    assert len(api.calls) == 1
    assert api.calls[0][1]["max_results"] == 20
    assert api.calls[0][1]["max_pages"] == 1
    assert api.calls[0][1]["max_per_page"] == 20
    owned.refresh_from_db()
    assert owned.state == HarvestBacklogWindow.State.COMPLETED
    job.refresh_from_db()
    assert job.state == BackfillJob.State.COMPLETED
    assert job.completed_at is not None
    scheduled.refresh_from_db()
    other.refresh_from_db()
    assert scheduled.state == HarvestBacklogWindow.State.PENDING
    assert other.state == HarvestBacklogWindow.State.PENDING
    other_job.refresh_from_db()
    assert other_job.state == BackfillJob.State.ACTIVE


def test_job_truncation_narrows_only_job_row_and_never_mutates_live_cursor(monkeypatch):
    call = _call()
    job = _job()
    owned = _window(call, job=job)
    live_cursor_at = owned.remaining_since - timedelta(hours=1)
    live = CallState.objects.create(
        **_cursor_key(call), last_completed_at=live_cursor_at
    )
    oldest = int((owned.remaining_since + timedelta(minutes=4)).timestamp())
    api = CapturingApi(
        response=(
            [{"id": "tweet-1", "text": "DeepSeek", "created_at_epoch": oldest}],
            True,
        )
    )
    runner = _runner()
    monkeypatch.setattr(runner, "_attribute_items", lambda items, index, terms: 1)
    monkeypatch.setattr(
        runner,
        "_route_and_persist",
        lambda call, items: (items, 1, 0, 1, 0, 0, []),
    )

    reports = _replay(runner, call=call, api=api, job=job)

    assert reports[0]["status"] == "pending"
    owned.refresh_from_db()
    assert owned.state == HarvestBacklogWindow.State.PENDING
    assert owned.remaining_until == datetime.fromtimestamp(oldest + 1, tz=UTC)
    job.refresh_from_db()
    assert job.state == BackfillJob.State.ACTIVE
    live.refresh_from_db()
    assert live.last_completed_at == live_cursor_at


def test_provider_failure_quarantines_at_ceiling_and_explicit_retry_completes():
    from x_monitor.apify import TwitterApiAuthError

    call = _call()
    job = _job()
    owned = _window(call, job=job)
    HarvestBacklogWindow.objects.filter(pk=owned.pk).update(attempts=7)

    class AuthFailure(CapturingApi):
        def run_search(self, query, **kwargs):
            self.calls.append((query, kwargs))
            raise TwitterApiAuthError("tokens exhausted")

    failed = _replay(_runner(), call=call, api=AuthFailure(), job=job)

    assert failed[0]["status"] == "quarantined"
    owned.refresh_from_db()
    assert owned.state == HarvestBacklogWindow.State.QUARANTINED
    assert owned.quarantine_reason == "error"
    job.refresh_from_db()
    assert job.state == BackfillJob.State.ACTIVE

    retried = _replay(
        _runner(),
        call=call,
        api=CapturingApi(),
        job=job,
        include_quarantined=True,
    )

    assert retried[0]["status"] == "completed"
    owned.refresh_from_db()
    assert owned.state == HarvestBacklogWindow.State.COMPLETED
    job.refresh_from_db()
    assert job.state == BackfillJob.State.COMPLETED


def test_scheduled_success_still_deletes_its_row(monkeypatch):
    call = _call()
    scheduled = _window(call, job=None)
    runner = _runner()
    monkeypatch.setattr(runner, "_fetch_tweets", lambda *args, **kwargs: ([], "ok"))

    reports = runner._replay_backlog(
        calls=[call],
        api=CapturingApi(),
        index=None,
        search_terms={},
        kept_all=[],
        run_id="scheduled-replay",
        deadline=Deadline(),
        replay_limit=1,
    )

    assert reports[0]["status"] == "completed"
    assert not HarvestBacklogWindow.objects.filter(pk=scheduled.pk).exists()


def test_backfill_cycle_kind_skips_metrics_refresh_while_manual_cycle_keeps_it(
    monkeypatch,
):
    call = _call()
    api = CapturingApi()
    metric_calls = []
    monkeypatch.setattr(
        "monitor.cycle.TwitterApiClient.from_env",
        lambda: api,
    )
    monkeypatch.setattr(
        "monitor.metrics_refresh.run_metrics_refresh",
        lambda api, cfg: metric_calls.append((api, cfg)) or {"n_refreshed": 0},
    )

    for cycle_kind in ("backfill", "manual"):
        runner = _runner()
        runner.cycle_kind = cycle_kind
        monkeypatch.setattr(runner, "_plan_calls", lambda: [call])
        monkeypatch.setattr(
            runner, "_resolve_window", lambda *args, **kwargs: (1, 2, False)
        )
        monkeypatch.setattr(runner, "_fetch_tweets", lambda *args, **kwargs: ([], "ok"))
        monkeypatch.setattr(runner, "_run_post_fetch", lambda *args, **kwargs: {})
        monkeypatch.setattr(
            runner,
            "_finish_summary",
            lambda summary, **kwargs: {**summary, "wall_clock_sec": 0},
        )
        runner.run()

    assert len(metric_calls) == 1
    assert metric_calls[0][0] is api
