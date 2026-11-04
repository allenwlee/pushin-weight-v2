"""Chatter starts beside harvesting, with no second scheduler or broker dependency."""

from unittest.mock import Mock, patch

import pytest
from django.utils import timezone

from tests.test_chatter_chain import chain_config

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def test_normal_cycle_notifies_chatter_before_harvest_planning(monkeypatch):
    from monitor.cycle import CycleRunner

    order = []
    runner = CycleRunner(cycle_kind="scheduled")
    monkeypatch.setattr(
        "monitor.editorial.dispatch.dispatch_chatter_cycle",
        lambda *args, **kwargs: order.append((args, kwargs)),
    )

    def abort_plan():
        assert order and order[0][1] == {"kind": "scheduled", "dry_run": False}
        raise ValueError("fixture harvest failure after independent start")

    monkeypatch.setattr(runner, "_plan_calls", abort_plan)
    monkeypatch.setattr(runner, "_finish_summary", lambda summary, **kwargs: summary)
    result = runner.run()
    assert result["status"] == "aborted"
    assert order[0][0][0] == result["run_id"]
    assert order[0][0][1].isoformat(timespec="seconds") == result["started_at"]


def test_cycle_start_dispatch_is_nonblocking_and_does_not_run_for_dry_or_backfill(
    django_capture_on_commit_callbacks,
):
    from monitor.editorial.dispatch import dispatch_chatter_cycle

    task = Mock()
    with patch(
        "monitor.editorial.dispatch.load_editorial_config", return_value=chain_config()
    ):
        for kind, dry in (("backfill", False), ("scheduled", True), ("manual", False)):
            assert (
                dispatch_chatter_cycle(
                    "source-1", timezone.now(), kind=kind, dry_run=dry, task=task
                )["status"]
                == "ineligible"
            )
        with django_capture_on_commit_callbacks(execute=True):
            result = dispatch_chatter_cycle(
                "source-2", timezone.now(), kind="scheduled", dry_run=False, task=task
            )
        assert result["status"] == "enqueued"
        request = task.apply_async.call_args.kwargs
        assert request["queue"] == "trend-narratives" and request["priority"] == 0
        assert (
            request["args"][1]["credential_purpose"] == "on-demand"
        )  # A finite trial never uses the recurring key.
        task.apply_async.side_effect = ConnectionError("fixture broker unavailable")
        with django_capture_on_commit_callbacks(execute=True):
            dispatch_chatter_cycle(
                "source-3", timezone.now(), kind="scheduled", dry_run=False, task=task
            )


def test_stage_routing_uses_existing_queue_and_default_writer_first(
    django_capture_on_commit_callbacks,
):
    from monitor.editorial.dispatch import dispatch_chatter_stage

    task = Mock()
    with (
        patch("monitor.tasks.chatter_stage", task),
        django_capture_on_commit_callbacks(execute=True),
    ):
        dispatch_chatter_stage("select", 1)
        dispatch_chatter_stage("write", 1, "en")
        dispatch_chatter_stage("write", 1, "ja")
        dispatch_chatter_stage("review", 1)
    assert [call.kwargs["priority"] for call in task.apply_async.call_args_list] == [
        0,
        3,
        6,
        9,
    ]
