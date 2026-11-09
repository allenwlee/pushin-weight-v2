"""Bounded broker handoff and recovery for saved Graphics work.

Reconciliation is run by dedicated creation workers, never the harvest cron or
Celery beat. Database scan locks are released before broker calls.
"""

import logging
import threading

from django.conf import settings
from django.db import close_old_connections, connection, transaction
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)
CREATION_QUEUE = 'graphics-creation'
REVIEW_QUEUE = 'graphics-review'
MAX_RECOVERY_BATCH = 20
RECOVERY_INTERVAL = 30
# Separate from all other project advisory locks.
RECOVERY_LOCK = 3891341261926
_stop = threading.Event()
_thread = None



def require_shared_media():
    """Reject staging media work unless both configured stores are nonlocal."""
    if not getattr(settings, 'GRAPHICS_REQUIRE_SHARED_MEDIA', False):
        return
    from django.core.files.storage import FileSystemStorage
    from django.utils.module_loading import import_string

    for alias, flag in (('staff_media', 'STAFF_MEDIA_DURABLE'),
                        ('editorial_media', 'EDITORIAL_MEDIA_DURABLE')):
        if not getattr(settings, flag, False):
            raise RuntimeError(f'Graphics shared media unavailable: {flag} must be true')
        try:
            backend = import_string(settings.STORAGES[alias]['BACKEND'])
            local = issubclass(backend, FileSystemStorage)
        except (KeyError, ImportError, TypeError, AttributeError) as exc:
            raise RuntimeError(f'Graphics shared media unavailable: invalid {alias} backend') from exc
        if local:
            raise RuntimeError(f'Graphics shared media unavailable: {alias} uses local filesystem storage')

def _enqueue(task, args, *, queue, countdown=0):
    options = {'args': args, 'queue': queue, 'expires': 900, 'retry': False}
    if countdown:
        options['countdown'] = countdown
    try:
        task.apply_async(**options)
    except Exception:
        logger.exception('Graphics broker dispatch failed')
        return False
    return True


def dispatch_creation(*, run_id, content_id=None):
    from monitor.tasks import advance_graphics_package

    return _enqueue(advance_graphics_package, [run_id], queue=CREATION_QUEUE)


def dispatch_video(*, run_id, text_id):
    from monitor.tasks import submit_graphics_video

    return _enqueue(submit_graphics_video, [run_id, text_id], queue=CREATION_QUEUE)


def dispatch_video_poll(picture_id, *, countdown=0):
    from monitor.tasks import poll_graphics_video

    return _enqueue(poll_graphics_video, [str(picture_id)], queue=CREATION_QUEUE, countdown=countdown)


def dispatch_review(run_id):
    from monitor.tasks import review_graphics_package

    return _enqueue(review_graphics_package, [run_id], queue=REVIEW_QUEUE)


def dispatch_action(run_id, decision):
    """Route one action derived from persisted state, not task memory."""
    if not decision:
        return False
    action = decision.get('action') or decision.get('next_action')
    if action == 'advance':
        return dispatch_creation(run_id=run_id)
    if action == 'video':
        return dispatch_video(run_id=run_id, text_id=decision['text_id'])
    if action == 'review':
        return dispatch_review(run_id)
    if action == 'poll':
        return dispatch_video_poll(decision['picture_id'], countdown=decision.get('countdown', 0))
    return False


def _recovery_candidates(now, limit):
    """Select candidates under a nonblocking transaction lock; no broker I/O."""
    from core.models import ContentPicture, OriginalContentRun

    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_try_advisory_xact_lock(%s)', [RECOVERY_LOCK])
            if not cursor.fetchone()[0]:
                return None
        runs = list(OriginalContentRun.objects.filter(
            workflow_key='graphics-package',
        ).filter(
            Q(execution_state__in=['pending', 'preparing'])
            | Q(execution_state='running', lease_until__lte=now),
        ).order_by('updated_at', 'pk').values_list('pk', flat=True)[:limit])
        jobs = list(ContentPicture.objects.filter(
            run__workflow_key='graphics-package', state='pending',
            provenance__schema_version='graphics-video-job/v1', next_poll_at__lte=now, poll_count__lt=40,
        ).filter(Q(poll_lease_until__isnull=True) | Q(poll_lease_until__lte=now))
                    .order_by('next_poll_at', 'pk').values_list('pk', flat=True)[:limit])
    return runs, jobs


def reconcile_due(*, now=None, limit=MAX_RECOVERY_BATCH):
    """Redispatch a bounded set after worker start, broker recovery, or manually."""
    if type(limit) is not int or not 1 <= limit <= MAX_RECOVERY_BATCH:
        raise ValueError('invalid Graphics recovery limit')
    from .graphics_pipeline import finalize_if_done, pending_action

    selected = _recovery_candidates(now or timezone.now(), limit)
    if selected is None:
        return {'state': 'busy', 'runs': 0, 'jobs': 0, 'dispatched': 0}
    runs, jobs = selected
    count = 0
    for run_id in runs:
        try:
            decision = pending_action(run_id)
            if decision is None:
                finalize_if_done(run_id)
                continue
            count += bool(dispatch_action(run_id, decision))
            if decision and decision.get('review_due') and decision.get('action') != 'review':
                count += bool(dispatch_review(run_id))
        except Exception:
            logger.exception('Graphics run reconciliation failed')
    for picture_id in jobs:
        count += bool(dispatch_video_poll(picture_id))
    return {'state': 'scanned', 'runs': len(runs), 'jobs': len(jobs), 'dispatched': count}


def _recovery_loop():
    try:
        while not _stop.is_set():
            try:
                close_old_connections()
                reconcile_due()
            except Exception:
                logger.exception('Graphics recovery scan failed')
            finally:
                close_old_connections()
            _stop.wait(RECOVERY_INTERVAL)
    finally:
        close_old_connections()


def start_reconciler():
    """Start once per dedicated worker process, only when explicitly enabled."""
    global _thread
    if not getattr(settings, 'GRAPHICS_RECONCILER_ENABLED', False):
        return False
    try:
        require_shared_media()
    except RuntimeError:
        logger.exception('Graphics reconciler disabled until shared media is configured')
        return False
    if _thread is not None and _thread.is_alive():
        return False
    _stop.clear()
    _thread = threading.Thread(target=_recovery_loop, name='graphics-reconciler', daemon=True)
    _thread.start()
    return True


def stop_reconciler():
    global _thread
    _stop.set()
    if _thread is not None and _thread.is_alive():
        _thread.join(timeout=10)
    _thread = None
