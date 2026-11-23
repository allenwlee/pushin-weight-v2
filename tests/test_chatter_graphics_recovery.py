"""The existing worker clock recovers provider-safe Chatter handoffs."""

from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.utils import timezone

from core.models import OriginalContentCall
from tests.test_chatter_trends import configured as configured  # noqa: PLC0414
from tests.test_chatter_trends import discover, start

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def ready(run, phase):
    run.refresh_from_db()
    run.outcome["phase"] = phase
    run.outcome["trends"]["last_enqueue_at"] = (timezone.now() - timedelta(minutes=2)).isoformat()
    run.lease_until = timezone.now() - timedelta(seconds=1)
    run.claim_owner = ""
    run.discovery_state = "complete" if phase in {"discovered", "selected"} else "pending"
    run.save(update_fields=["outcome", "lease_until", "claim_owner", "discovery_state"])


@pytest.mark.parametrize("phase,stage", [("ranked", "discover"), ("discovered", "select"), ("selected", "select")])
def test_saved_next_stage_recovers_dropped_delivery_without_resending_prior_calls(configured, django_capture_on_commit_callbacks, phase, stage):
    from monitor.editorial.dispatch import recover_chatter_starts

    run = start(configured)
    assert discover(run, configured)[0]["status"] == "ranked"
    ready(run, phase)
    task = Mock()
    with django_capture_on_commit_callbacks(execute=True):
        result = recover_chatter_starts(cfg=configured, task=task)
    assert result == {"enqueued": 1}
    assert task.apply_async.call_args.kwargs["args"][0] == stage
    assert OriginalContentCall.objects.filter(run=run).count() == 1
    with django_capture_on_commit_callbacks(execute=True):
        assert recover_chatter_starts(cfg=configured, task=task) == {"enqueued": 0}
    assert task.apply_async.call_count == 1


def test_uncertain_selector_is_held_instead_of_automatically_retried(configured, django_capture_on_commit_callbacks):
    from monitor.editorial.dispatch import recover_chatter_starts

    run = start(configured)
    assert discover(run, configured)[0]["status"] == "ranked"
    ready(run, "discovered")
    OriginalContentCall.objects.create(run=run, workflow_key="chatter-discovery", stage="selector:0",
        request_identity="uncertain-selector", request_hash="a" * 64,
        state="ambiguous", reserved_at=timezone.now(), sent_at=timezone.now())
    task = Mock()
    with django_capture_on_commit_callbacks(execute=True):
        assert recover_chatter_starts(cfg=configured, task=task) == {"enqueued": 0}
    task.apply_async.assert_not_called()
    run.refresh_from_db()
    assert run.outcome["phase"] == "held"
    assert run.outcome["error_code"] == "model_send_requires_reconciliation"


def test_worker_recovery_clock_keeps_graphics_scanning_after_chatter_failure(monkeypatch):
    from monitor.editorial import graphics_dispatch

    stop = Mock()
    stop.is_set.side_effect = [False, True]
    monkeypatch.setattr(graphics_dispatch, "_stop", stop)
    monkeypatch.setattr(graphics_dispatch, "close_old_connections", Mock())
    chatter = Mock(side_effect=ValueError("invalid saved Chatter configuration"))
    graphics = Mock()
    monkeypatch.setattr("monitor.editorial.dispatch.recover_chatter_starts", chatter)
    monkeypatch.setattr(graphics_dispatch, "reconcile_due", graphics)
    graphics_dispatch._recovery_loop()
    chatter.assert_called_once_with()
    graphics.assert_called_once_with()
    stop.wait.assert_called_once_with(graphics_dispatch.RECOVERY_INTERVAL)


def test_unfinished_source_send_is_held_without_dispatching_another_request(configured, django_capture_on_commit_callbacks):
    from monitor.editorial.chatter_sources import SourceSession
    from monitor.editorial.dispatch import recover_chatter_starts
    from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose

    run = start(configured)
    assert discover(run, configured)[0]["status"] == "ranked"
    run.refresh_from_db()
    session = SourceSession(run, configured, purpose=TwitterApiCredentialPurpose.ON_DEMAND)
    session.start("/twitter/tweet/advanced_search", {"query": '"Original headline 1"', "queryType": "Latest"})
    ready(run, "ranked")
    from core.models import CollectionRun

    CollectionRun.objects.filter(pk=session.claim.run_id).update(
        lease_expires_at=timezone.now() - timedelta(seconds=1))
    task = Mock()
    with django_capture_on_commit_callbacks(execute=True):
        assert recover_chatter_starts(cfg=configured, task=task) == {"enqueued": 0}
    task.apply_async.assert_not_called()
    run.refresh_from_db()
    assert run.outcome["phase"] == "held"
    assert run.outcome["error_code"] == "source_send_requires_reconciliation"
