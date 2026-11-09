"""Queue handoff contracts; tests never contact a broker."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.conf import settings

from monitor import tasks
from monitor.editorial import graphics_dispatch


def test_creation_dispatch_uses_dedicated_queue(monkeypatch):
    task = SimpleNamespace(apply_async=Mock())
    monkeypatch.setattr(tasks, 'advance_graphics_package', task)
    assert graphics_dispatch.dispatch_creation(run_id=71, content_id=29)
    task.apply_async.assert_called_once_with(args=[71], queue='graphics-creation', expires=900, retry=False)


def test_broker_failure_reports_false(monkeypatch):
    task = SimpleNamespace(apply_async=Mock(side_effect=OSError('unavailable')))
    monkeypatch.setattr(tasks, 'advance_graphics_package', task)
    assert not graphics_dispatch.dispatch_creation(run_id=71, content_id=29)


def test_video_poll_and_review_have_separate_queues(monkeypatch):
    poll = SimpleNamespace(apply_async=Mock())
    review = SimpleNamespace(apply_async=Mock())
    monkeypatch.setattr(tasks, 'poll_graphics_video', poll)
    monkeypatch.setattr(tasks, 'review_graphics_package', review)
    assert graphics_dispatch.dispatch_video_poll('picture-id', countdown=30)
    assert graphics_dispatch.dispatch_review(71)
    poll.apply_async.assert_called_once_with(args=['picture-id'], queue='graphics-creation', expires=900, retry=False, countdown=30)
    review.apply_async.assert_called_once_with(args=[71], queue='graphics-review', expires=900, retry=False)


def test_routes_isolate_creation_and_review_from_existing_editorial():
    assert settings.CELERY_TASK_ROUTES['monitor.tasks.advance_graphics_package'] == {'queue': 'graphics-creation'}
    assert settings.CELERY_TASK_ROUTES['monitor.tasks.review_graphics_package'] == {'queue': 'graphics-review'}
    assert settings.CELERY_TASK_ROUTES['monitor.tasks.refresh_editorial'] == {'queue': 'trend-narratives'}


def test_reconcile_recovers_after_broker_reconnect(monkeypatch):
    import sys
    from types import ModuleType

    pipeline = ModuleType('monitor.editorial.graphics_pipeline')
    pipeline.pending_action = lambda run_id: {'action': 'advance', 'review_due': True}
    monkeypatch.setitem(sys.modules, pipeline.__name__, pipeline)
    monkeypatch.setattr(graphics_dispatch, '_recovery_candidates', lambda now, limit: ([71], ['picture-id']))
    # First scan's broker sends fail, second scan sees the same durable rows.
    create = Mock(side_effect=[False, True])
    review = Mock(side_effect=[False, True])
    poll = Mock(side_effect=[False, True])
    monkeypatch.setattr(graphics_dispatch, 'dispatch_creation', create)
    monkeypatch.setattr(graphics_dispatch, 'dispatch_review', review)
    monkeypatch.setattr(graphics_dispatch, 'dispatch_video_poll', poll)
    assert graphics_dispatch.reconcile_due()['dispatched'] == 0
    assert graphics_dispatch.reconcile_due()['dispatched'] == 3
    assert create.call_count == review.call_count == poll.call_count == 2


def test_busy_scan_does_not_dispatch(monkeypatch):
    import sys
    from types import ModuleType

    pipeline = ModuleType('monitor.editorial.graphics_pipeline')
    pipeline.pending_action = Mock()
    monkeypatch.setitem(sys.modules, pipeline.__name__, pipeline)
    monkeypatch.setattr(graphics_dispatch, '_recovery_candidates', lambda now, limit: None)
    result = graphics_dispatch.reconcile_due()
    assert result == {'state': 'busy', 'runs': 0, 'jobs': 0, 'dispatched': 0}
    pipeline.pending_action.assert_not_called()


def test_recovery_batch_is_bounded():
    import pytest

    with pytest.raises(ValueError, match='limit'):
        graphics_dispatch.reconcile_due(limit=21)


def test_staging_workers_are_isolated_from_existing_queues():
    from pathlib import Path

    import yaml

    blueprint = yaml.safe_load((Path(__file__).resolve().parents[1] / 'render-staging.yaml').read_text())
    services = {service['name']: service for service in blueprint['services']}
    for name in ('pushinweight-staging-graphics-a', 'pushinweight-staging-graphics-b'):
        service = services[name]
        assert '-Q graphics-creation --concurrency=1' in service['startCommand']
        assert {'key': 'GRAPHICS_RECONCILER_ENABLED', 'value': 'True'} in service['envVars']
        assert {'key': 'EXA_API_KEY', 'sync': False} in service['envVars']
    review = services['pushinweight-staging-graphics-review']
    assert '-Q graphics-review --concurrency=1' in review['startCommand']
    assert not any(item['key'] == 'EXA_API_KEY' for item in review['envVars'])
    assert {'key': 'GRAPHICS_RECONCILER_ENABLED', 'value': 'False'} in review['envVars']
    assert '-Q trend-narratives --concurrency=1' in services['pushinweight-staging-headlines']['startCommand']


def test_reconciler_is_disabled_by_default(settings):
    settings.GRAPHICS_RECONCILER_ENABLED = False
    assert not graphics_dispatch.start_reconciler()


def test_creation_task_sends_review_without_waiting_for_video(monkeypatch):
    import sys
    from types import ModuleType

    pipeline = ModuleType('monitor.editorial.graphics_pipeline')
    pipeline.advance_step = lambda run_id: {'state': 'published', 'next_action': 'video', 'text_id': 41, 'review_due': True}
    pipeline.finalize_if_done = Mock()
    monkeypatch.setitem(sys.modules, pipeline.__name__, pipeline)
    next_action, review = Mock(), Mock()
    monkeypatch.setattr(graphics_dispatch, 'dispatch_action', next_action)
    monkeypatch.setattr(graphics_dispatch, 'dispatch_review', review)
    result = tasks.advance_graphics_package.run(71)
    assert result['state'] == 'published'
    next_action.assert_called_once_with(71, result)
    review.assert_called_once_with(71)


@pytest.mark.django_db(transaction=True)
@pytest.mark.requires_postgres
def test_recovery_selects_due_work_and_releases_db_lock_before_broker(monkeypatch):
    import sys
    from datetime import timedelta
    from types import ModuleType
    from uuid import uuid4

    from django.db import connection
    from django.utils import timezone

    from core.models import ContentPicture, OriginalContentRun

    now = timezone.now()
    def run_with(state, lease=None):
        return OriginalContentRun.objects.create(
            source_cycle_id=str(uuid4()), workflow_key='graphics-package', scope_key=str(uuid4()),
            facts_as_of=now, packet_schema_version=1, snapshot={}, execution_state=state,
            lease_until=lease,
        )
    pending = run_with('pending')
    expired = run_with('running', now - timedelta(seconds=1))
    active = run_with('running', now + timedelta(seconds=30))
    def picture(run, count):
        return ContentPicture.objects.create(
            content_kind='chatter', content_id=str(uuid4()), revision_hash=uuid4().hex,
            run=run, mode='derived', state='pending', next_poll_at=now - timedelta(seconds=1),
            poll_count=count, provenance={'schema_version': 'graphics-video-job/v1'},
        )
    due = picture(pending, 39)
    exhausted = picture(pending, 40)
    pipeline = ModuleType('monitor.editorial.graphics_pipeline')
    pipeline.pending_action = lambda _run_id: {'action': 'advance'}
    monkeypatch.setitem(sys.modules, pipeline.__name__, pipeline)
    sent_runs, sent_jobs = [], []
    def send_run(*, run_id, content_id=None):
        assert not connection.in_atomic_block
        sent_runs.append(run_id)
        return True
    def send_poll(picture_id, *, countdown=0):
        assert not connection.in_atomic_block
        sent_jobs.append(str(picture_id))
        return True
    monkeypatch.setattr(graphics_dispatch, 'dispatch_creation', send_run)
    monkeypatch.setattr(graphics_dispatch, 'dispatch_video_poll', send_poll)
    result = graphics_dispatch.reconcile_due(now=now)
    assert set(sent_runs) == {pending.pk, expired.pk}
    assert active.pk not in sent_runs
    assert sent_jobs == [str(due.pk)] and str(exhausted.pk) not in sent_jobs
    assert result['dispatched'] == 3


def test_recovery_loop_survives_errors_and_closes_connections(monkeypatch):
    class StopAfterTwo:
        count = 0

        def is_set(self):
            return self.count >= 2

        def wait(self, timeout):
            self.count += 1

    stop = StopAfterTwo()
    reconcile = Mock(side_effect=[OSError('broker disconnected'), {'state': 'ok'}])
    close = Mock()
    monkeypatch.setattr(graphics_dispatch, '_stop', stop)
    monkeypatch.setattr(graphics_dispatch, 'reconcile_due', reconcile)
    monkeypatch.setattr(graphics_dispatch, 'close_old_connections', close)
    graphics_dispatch._recovery_loop()
    assert reconcile.call_count == 2
    assert close.call_count == 5


def test_shared_media_guard_rejects_missing_flags_and_local_storage(settings):
    settings.GRAPHICS_REQUIRE_SHARED_MEDIA = True
    settings.STAFF_MEDIA_DURABLE = False
    settings.EDITORIAL_MEDIA_DURABLE = True
    with pytest.raises(RuntimeError, match='STAFF_MEDIA_DURABLE'):
        graphics_dispatch.require_shared_media()
    settings.STAFF_MEDIA_DURABLE = True
    settings.STORAGES = {
        'staff_media': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'editorial_media': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    }
    with pytest.raises(RuntimeError, match='staff_media uses local'):
        graphics_dispatch.require_shared_media()


def test_shared_media_guard_accepts_configured_nonlocal_backends(settings):
    settings.GRAPHICS_REQUIRE_SHARED_MEDIA = True
    settings.STAFF_MEDIA_DURABLE = settings.EDITORIAL_MEDIA_DURABLE = True
    settings.STORAGES = {
        'staff_media': {'BACKEND': 'django.core.files.storage.Storage'},
        'editorial_media': {'BACKEND': 'django.core.files.storage.Storage'},
    }
    graphics_dispatch.require_shared_media()


def test_staging_admission_blocks_task_before_pipeline(settings, monkeypatch):
    settings.GRAPHICS_REQUIRE_SHARED_MEDIA = True
    settings.STAFF_MEDIA_DURABLE = False
    with pytest.raises(RuntimeError, match='STAFF_MEDIA_DURABLE'):
        tasks.advance_graphics_package.run(71)
