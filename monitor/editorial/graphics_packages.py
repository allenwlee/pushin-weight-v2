"""Materialize one selected story as a durable, independently leased package.

The provider and queue adapters are separate; materializing work does not claim
that a model ran, a message reached the broker, or an edition was published.
"""

from copy import deepcopy
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.timezone import is_aware

from core.models import OriginalContent, OriginalContentRun
from monitor.original_content import advisory_lock, digest

from .graphics_entry import prepare_selected_story


@dataclass(frozen=True)
class PackageClaim:
    run_id: int
    owner: str
    fence: int


def _time(value):
    result = value if value is not None else timezone.now()
    if not is_aware(result):
        raise ValueError('aware claim time required')
    return result


def materialize_package(request):
    """Copy a verified, selected story into its own idempotent Graphics run.

    Re-read the selected source under row locks rather than trusting a caller's
    JSON. The source record and its run are never updated by this function.
    """
    if not isinstance(request, dict):
        raise TypeError('invalid selected story request')
    try:
        content_id = request['content_id']
        run_id = request['run_id']
        locale = request['locale']
        per_story = request['per_story_usd']
        daily = request['daily_usd']
    except KeyError as exc:
        raise ValueError('invalid selected story request') from exc
    if type(content_id) is not int or type(run_id) is not int or content_id <= 0 or run_id <= 0:
        raise ValueError('invalid selected story identity')
    with transaction.atomic():
        source_run = OriginalContentRun.objects.select_for_update().filter(pk=run_id).first()
        source = OriginalContent.objects.select_for_update().filter(pk=content_id).first()
        if source_run is None or source is None or source.run_id != source_run.pk:
            raise ValueError('invalid selected story identity')
        verified = prepare_selected_story(
            content_id=content_id, run_id=run_id, locale=locale,
            per_story_usd=per_story, daily_usd=daily,
        )
        if request != verified:
            raise ValueError('selected story request differs from saved evidence')
        identity = digest({'source_run_id': run_id, 'source_content_id': content_id,
                           'source_revision': source.revision, 'locale': locale})
        key = f'graphics:{identity}'
        advisory_lock('graphics-package:' + identity)
        snapshot = {'schema_version': 'graphics-run/v1', 'request': deepcopy(verified)}
        config = {'schema_version': 'graphics-limits/v1', 'locale': locale,
                  'per_story_usd': verified['per_story_usd'], 'daily_usd': verified['daily_usd']}
        run, created = OriginalContentRun.objects.get_or_create(
            source_cycle_id=key, workflow_key='graphics-package', scope_key=key,
            defaults={'facts_as_of': source_run.facts_as_of, 'packet_schema_version': 1,
                      'snapshot': snapshot, 'workflow_version': 'graphics-package/v1',
                      'config_snapshot': config, 'execution_state': 'pending'},
        )
        if not created and (run.snapshot != snapshot or run.config_snapshot != config
                            or run.facts_as_of != source_run.facts_as_of
                            or run.workflow_version != 'graphics-package/v1'):
            raise ValueError('existing Graphics run differs from selected story')
        provenance = {'schema_version': 'graphics-source/v1', 'source_run_id': run_id,
                      'source_content_id': content_id, 'source_revision': source.revision,
                      'snapshot_hash': digest(verified)}
        output, made = OriginalContent.objects.get_or_create(
            run=run, workflow_key=source.workflow_key, output_key='graphics-primary/v1',
            defaults={'subject_key': source.subject_key, 'story_id': source.story_id,
                      'revision': source.revision, 'occurred_at': source.occurred_at,
                      'importance': source.importance, 'fingerprint': source.fingerprint,
                      'brand_id': source.brand_id, 'brand_key_snapshot': source.brand_key_snapshot,
                      'selection': deepcopy(source.selection), 'status': 'prepared',
                      'attempted_at': source.attempted_at, 'provenance': provenance},
        )
        if not made and (output.story_id != source.story_id or output.provenance != provenance
                         or output.selection != source.selection):
            raise ValueError('existing Graphics output differs from selected story')
        return run, output


def claim_package(run_id, *, owner, now=None, lease_seconds=180):
    """Claim pending or expired work with a monotonically increasing fence."""
    now = _time(now)
    if not isinstance(owner, str) or not owner or len(owner) > 128:
        raise ValueError('invalid package owner')
    if type(lease_seconds) is not int or not 1 <= lease_seconds <= 3600:
        raise ValueError('invalid package lease')
    with transaction.atomic():
        run = OriginalContentRun.objects.select_for_update().get(pk=run_id)
        if run.workflow_key != 'graphics-package':
            raise ValueError('not a Graphics run')
        if run.execution_state not in {'pending', 'preparing', 'running'}:
            return None
        if run.lease_until is not None and run.lease_until > now:
            return None
        run.fence += 1
        run.execution_state = 'running'
        run.claim_owner = owner
        run.lease_until = now + timedelta(seconds=lease_seconds)
        run.save(update_fields=['fence', 'execution_state', 'claim_owner', 'lease_until', 'updated_at'])
        return PackageClaim(run.pk, owner, run.fence)


def release_package(run_id, *, owner, fence, now=None):
    """Release only the current live claim; a stale worker cannot change it."""
    now = _time(now)
    with transaction.atomic():
        run = OriginalContentRun.objects.select_for_update().get(pk=run_id)
        if (run.workflow_key != 'graphics-package' or run.execution_state != 'running'
                or run.claim_owner != owner or run.fence != fence
                or run.lease_until is None or run.lease_until <= now):
            return False
        run.execution_state = 'pending'
        run.claim_owner = ''
        run.lease_until = None
        run.save(update_fields=['execution_state', 'claim_owner', 'lease_until', 'updated_at'])
        return True


def advance_package(request, *, dispatch=None):
    """Persist selected work, then ask an explicitly supplied dispatcher to run it.

    A broker error or rejected dispatch leaves the durable run pending for a
    reconciler. No default dispatcher exists until the queue integration lands.
    """
    if dispatch is None:
        raise RuntimeError('Graphics package dispatcher is not available')
    run, content = materialize_package(request)
    try:
        sent = bool(dispatch(run_id=run.pk, content_id=content.pk))
    except Exception:  # noqa: BLE001 -- the saved run remains available for reconciliation
        sent = False
    return {'run_id': run.pk, 'content_id': content.pk,
            'state': 'queued' if sent else 'pending_dispatch', 'dispatched': sent}
