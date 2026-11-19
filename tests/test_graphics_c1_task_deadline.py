"""Saved native C1 routes fit the real task deadline and fenced claims."""

import json
from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.utils import timezone

from core.models import OriginalContentCall
from monitor import tasks
from monitor.editorial import graphics_dispatch, graphics_pipeline
from monitor.editorial.graphics_packages import materialize_package
from tests.test_graphics_chatter_adapter import (
    copy_result,
    prepared,
)
from tests.test_graphics_chatter_adapter import (
    frozen_chatter as frozen_chatter,  # noqa: PLC0414
)
from tests.test_graphics_entry import selected_story as selected_story  # noqa: PLC0414

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


@pytest.mark.parametrize("timeout", [90, 140, 300])
def test_saved_c1_timeout_fits_dispatch_and_live_claims(frozen_chatter, monkeypatch, timeout):
    row, _, _ = frozen_chatter
    route = row.run.config_snapshot["editorial"]["locale_routes"]["chatter:ja"]
    route["timeout_seconds"] = timeout
    row.run.save(update_fields=["config_snapshot"])
    run, _ = materialize_package(prepared(row, "ja"))
    task = tasks.advance_graphics_package
    enqueue = Mock()
    monkeypatch.setattr(task, "apply_async", enqueue)
    assert graphics_dispatch.dispatch_creation(run_id=run.pk)
    options = enqueue.call_args.kwargs
    soft = options.get("soft_time_limit", task.soft_time_limit)
    hard = options.get("time_limit", task.time_limit)
    assert (soft, hard) == (max(145, timeout + 10), max(150, timeout + 15))

    clock = [timezone.now()]
    monkeypatch.setattr(timezone, "now", lambda: clock[0])
    calls = []

    def transport(endpoint, key, body, **kwargs):
        calls.append((endpoint, key, kwargs["timeout"]))
        call = OriginalContentCall.objects.get(run=run, request_identity=f"graphics:{run.pk}:C1")
        run.refresh_from_db()
        assert call.state == "sent" and call.sent_at == clock[0]
        assert call.claim_expires_at == clock[0] + timedelta(seconds=max(160, timeout + 20))
        assert run.lease_until == clock[0] + timedelta(seconds=max(180, timeout + 40))
        assert call.claim_expires_at > clock[0] + timedelta(seconds=hard)
        assert run.lease_until > call.claim_expires_at
        # Simulate a valid near-deadline reply without waiting for the provider.
        clock[0] += timedelta(seconds=timeout - 1)
        return 200, json.dumps({"model": body["model"], "usage": {}, "choices": [
            {"finish_reason": "stop", "message": {"content": json.dumps(copy_result("ja"))}},
        ]}).encode()

    advance = graphics_pipeline.advance_step
    monkeypatch.setattr(graphics_pipeline, "advance_step", lambda run_id: advance(
        run_id, keys={route["key_env"]: "fixture-only"}, transport=transport,
    ))
    monkeypatch.setattr(graphics_dispatch, "dispatch_action", Mock(return_value=True))
    result = task.run(run.pk)
    assert result["state"] == "completed" and result["stage"] == "C1"
    assert calls == [(route["endpoint"], "fixture-only", timeout)]
    call = OriginalContentCall.objects.get(run=run, request_identity=f"graphics:{run.pk}:C1")
    assert call.state == "completed" and call.response_payload == copy_result("ja")

    # The next graphics stage uses its original limits even on a native package.
    enqueue.reset_mock()
    assert graphics_dispatch.dispatch_creation(run_id=run.pk)
    enqueue.assert_called_once_with(args=[run.pk], queue="graphics-creation", expires=900, retry=False)


@pytest.mark.parametrize("state", ["reserved", "sent", "ambiguous", "completed", "failed"])
def test_dispatch_distinguishes_never_sent_c1_from_saved_outcomes(frozen_chatter, monkeypatch, state):
    row, _, _ = frozen_chatter
    run, _ = materialize_package(prepared(row, "ja"))
    now = timezone.now()
    OriginalContentCall.objects.create(
        run=run, stage=f"gfx:{run.pk}:C1", request_identity=f"graphics:{run.pk}:C1",
        request_hash="a" * 64, reserved_at=now, state=state,
        sent_at=None if state == "reserved" else now,
        completed_at=now if state == "completed" else None,
        response_hash="b" * 64 if state == "completed" else "",
    )
    enqueue = Mock()
    monkeypatch.setattr(tasks.advance_graphics_package, "apply_async", enqueue)
    assert graphics_dispatch.dispatch_creation(run_id=run.pk)
    expected = {"soft_time_limit": 310, "time_limit": 315} if state == "reserved" else {}
    enqueue.assert_called_once_with(args=[run.pk], queue="graphics-creation", expires=900, retry=False, **expected)


def test_manual_creation_keeps_existing_deadlines(selected_story, monkeypatch):
    from monitor.editorial.graphics_entry import prepare_selected_story

    content, source_run, _ = selected_story
    run, _ = materialize_package(prepare_selected_story(content_id=content.pk, run_id=source_run.pk, locale="en"))
    enqueue = Mock()
    monkeypatch.setattr(tasks.advance_graphics_package, "apply_async", enqueue)
    assert graphics_dispatch.dispatch_creation(run_id=run.pk)
    enqueue.assert_called_once_with(args=[run.pk], queue="graphics-creation", expires=900, retry=False)
    assert (tasks.advance_graphics_package.soft_time_limit, tasks.advance_graphics_package.time_limit) == (145, 150)
