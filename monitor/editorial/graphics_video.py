"""Persist one video submission and poll its saved provider job without resubmission."""

import hashlib
import os
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.db import transaction
from django.utils import timezone

from core.models import (
    ContentPicture,
    OriginalContentCall,
    OriginalContentSelection,
    OriginalContentText,
)
from monitor.original_content import WORKFLOWS, advisory_lock, digest
from monitor.trend_narrative_lifecycle import (
    fail_trend_narrative_provider_call,
    mark_trend_narrative_provider_call_ambiguous,
    mark_trend_narrative_provider_call_sent,
)
from x_monitor.provider_http import https_request

from .graphics_artifacts import (
    VIDEO_JOB_FIELDS,
    VIDEO_TERMINAL_FAILURES,
    validate_still,
)
from .graphics_contracts import load_pack, normalize_treatments
from .graphics_generation import (
    MAX_INPUT_BYTES,
    build_video_request,
    create_request_recipe,
    poll_video,
    reconstruct_request,
    submit_once,
    video_decode_receipt,
)
from .graphics_reading import _source_content
from .persistence import (
    BudgetHeld,
    complete_graphics_call,
    fail_graphics_presend_call,
    reserve_graphics_call,
)

MAX_POLLS = 40
POLL_DELAY = timedelta(seconds=5)
POLL_LEASE = timedelta(seconds=120)


def _store(storage=None):
    return storage if storage is not None else storages['editorial_media']


def _current(text):
    scope = f'featured:{text.narrative.workflow_key}:{text.locale}'
    pointer = OriginalContentSelection.objects.filter(scope_key=scope).first()
    return pointer is None or pointer.text_id == text.pk


def _selected(run_id, text_id, storage):
    text = OriginalContentText.objects.select_related('narrative__run').get(pk=text_id)
    if text.narrative.run_id != run_id or text.narrative.status != 'approved' or not text.public_id:
        raise ValueError('video requires published text in the selected run')
    source, candidate = _source_content(text)
    track = next((name for name, workflow in WORKFLOWS.items() if workflow == source.workflow_key), None)
    if not track or not _current(text):
        raise ValueError('video text is not the current selection')
    stills = []
    for picture in ContentPicture.objects.filter(run_id=run_id, text=text, content_kind=track,
                                                  content_id=str(text.public_id), state='complete'):
        try:
            validate_still(picture, content=source, candidate=candidate, storage=storage)
        except (ValueError, TypeError, KeyError, OSError):
            continue
        stills.append(picture)
    if len(stills) != 1:
        raise ValueError('video requires exactly one valid selected still')
    return text, source, candidate, track, stills[0]


def _live_claim(run, owner, fence, now):
    return (run.workflow_key == 'graphics-package' and run.execution_state == 'running'
            and run.claim_owner == owner and run.fence == fence
            and run.lease_until is not None and run.lease_until > now)


def _job_for(call, text, source, candidate, track, still, *, now):
    response = call.response_payload
    if (call.state != 'completed' or not isinstance(response, dict)
            or not isinstance(response.get('request_id'), str)
            or call.response_hash != digest(response)):
        raise ValueError('video submission has no saved provider job')
    job_id = response['request_id']
    metadata = {'schema_version': 'graphics-video-job/v1', 'candidate_id': candidate,
                'content_id': str(source.pk), 'producer_call_id': call.pk,
                'input_still_sha256': still.generated_sha256, 'terminal_status': None}
    revision = hashlib.sha256(f'graphics-video-job:{call.pk}:{text.pk}'.encode()).hexdigest()
    job, _created = ContentPicture.objects.get_or_create(
        content_kind=track, content_id=str(text.public_id), revision_hash=revision,
        defaults={'run_id': call.run_id, 'text': text, 'mode': 'derive', 'state': 'pending',
                  'provider_task_id': job_id, 'next_poll_at': now, 'provenance': metadata},
    )
    if job.run_id != call.run_id or job.text_id != text.pk or job.provider_task_id != job_id:
        raise ValueError('video job identity collision')
    if job.state in {'pending', 'failed'}:
        actual = job.provenance
        if not isinstance(actual, dict) or set(actual) != VIDEO_JOB_FIELDS:
            raise ValueError('video job identity collision')
        if any(actual[key] != metadata[key] for key in VIDEO_JOB_FIELDS if key != 'terminal_status'):
            raise ValueError('video job identity collision')
        if ((job.state == 'pending' and actual['terminal_status'] is not None)
                or (job.state == 'failed' and actual['terminal_status'] not in VIDEO_TERMINAL_FAILURES)):
            raise ValueError('video job identity collision')
    elif job.state == 'complete':
        if (not isinstance(job.provenance, dict) or job.provenance.get('schema_version') != 'graphics-artifact/v1'
                or job.provenance.get('producer_call_id') != call.pk):
            raise ValueError('video job identity collision')
    else:
        raise ValueError('video job identity collision')
    return job


def _skip_video(run, stage, owner, fence, reason):
    with transaction.atomic():
        current = type(run).objects.select_for_update().get(pk=run.pk)
        if not _live_claim(current, owner, fence, timezone.now()):
            return False
        decisions = dict(current.decisions)
        skipped = dict(decisions.get('graphics_skipped_stages', {}))
        skipped[stage] = reason
        decisions['graphics_skipped_stages'] = skipped
        current.decisions = decisions
        current.save(update_fields=['decisions'])
        return True


def submit_video_job(run_id, text_id, *, owner, fence, pack=None, api_key=None,
                     transport=https_request, storage=None, configured_daily_limit=None):
    """Submit the selected still once and durably save the accepted provider ID."""
    storage = _store(storage)
    text, source, candidate, track, still = _selected(run_id, text_id, storage)
    run = text.narrative.run
    now = timezone.now()
    if not _live_claim(run, owner, fence, now):
        return {'state': 'stale'}
    stage = 'V1' if candidate == 'A' else 'V-B'
    key = api_key if api_key is not None else os.environ.get('XAI_API_KEY_PW', '')
    if not key:
        skipped = _skip_video(run, stage, owner, fence, 'credential_unavailable')
        return {'state': 'unavailable' if skipped else 'stale', 'run_id': run_id, 'error': 'missing_xai_credential'}
    pack = pack or load_pack(Path(settings.BASE_DIR) / 'config/editorial_prompts/editorial-creative-roles-v1.json')
    design = OriginalContentCall.objects.filter(run_id=run_id, request_identity=f'graphics:{run_id}:G1',
                                                workflow_key=source.workflow_key, state='completed').first()
    if not design or design.response_hash != digest(design.response_payload):
        raise ValueError('video requires a saved matching Graphics treatment')
    treatments, _ = normalize_treatments(pack, design.response_payload)
    treatment = next((item for item in treatments['treatments'] if item['candidate_id'] == candidate), None)
    if not treatment:
        raise ValueError('video treatment missing')
    with storage.open(still.generated_storage_name, 'rb') as stream:
        data = stream.read(MAX_INPUT_BYTES + 1)
    asset = {'data': data, 'mime': still.provenance['mime'], 'sha256': still.generated_sha256}
    request = build_video_request(pack, stage, treatment, asset)
    refs = [{'storage_alias': 'editorial_media', 'storage_name': still.generated_storage_name,
             'mime': asset['mime'], 'sha256': asset['sha256']}]
    def loader(alias, name):
        if alias != 'editorial_media' or name != still.generated_storage_name:
            raise ValueError('invalid selected still reference')
        with storage.open(name, 'rb') as stream:
            return stream.read(MAX_INPUT_BYTES + 1)
    packet, request_hash = create_request_recipe(request['body'], refs, load_bytes=loader)
    config = run.config_snapshot
    from .config import load_editorial_config
    editorial_config = load_editorial_config()
    if editorial_config.enabled:
        configured_daily_limit = (editorial_config.daily_usd if configured_daily_limit is None else
                                  min(Decimal(str(configured_daily_limit)), Decimal(str(editorial_config.daily_usd))))
    saved = {}
    def reserve(packet_value, hash_value):
        return reserve_graphics_call(run=run, stage=stage, kind='media', request_hash=hash_value,
            request_packet=packet_value, provider='xai', model=request['body']['model'], ceiling='0.20',
            owner=owner, lease_seconds=150, workflow_key=source.workflow_key,
            per_run_limit=config['per_story_usd'], daily_limit=config['daily_usd'],
            configured_daily_limit=configured_daily_limit, load_bytes=loader)
    def mark(call):
        with transaction.atomic():
            current = type(run).objects.select_for_update().get(pk=run_id)
            return _live_claim(current, owner, fence, timezone.now()) and mark_trend_narrative_provider_call_sent(
                call.pk, owner=owner, fence=call.claim_fence, now=timezone.now())
    def complete(call, payload, _image_bytes, _usage):
        with transaction.atomic():
            if not complete_graphics_call(call.pk, owner=owner, fence=call.claim_fence,
                                          response_hash=digest(payload), response_payload=payload):
                return False
            call.refresh_from_db()
            saved['job'] = _job_for(call, text, source, candidate, track, still, now=timezone.now())
            return True
    def ambiguous(call, code):
        return mark_trend_narrative_provider_call_ambiguous(call.pk, owner=owner, fence=call.claim_fence,
                                                             error_code=code, now=timezone.now())
    def fail(call, code):
        if code.startswith('pre_send:'):
            return fail_graphics_presend_call(call.pk, owner=owner, fence=call.claim_fence, error_code=code)
        return fail_trend_narrative_provider_call(call.pk, owner=owner, fence=call.claim_fence,
                                                  error_code=code, now=timezone.now())
    try:
        result = submit_once(stage, request, packet, request_hash, key, pack, reserve=reserve, mark_sent=mark,
                             complete=complete, ambiguous=ambiguous, fail=fail, transport=transport, load_bytes=loader)
    except BudgetHeld:
        skipped = _skip_video(run, stage, owner, fence, 'budget_or_capacity_unavailable')
        return {'state': 'unavailable' if skipped else 'stale', 'run_id': run_id,
                'error': 'budget_or_capacity_unavailable'}
    if result['state'] == 'completed':
        return {'state': 'pending', 'job_id': str(saved['job'].pk), 'run_id': run_id}
    if result['state'] == 'already_reserved':
        call = result['call']
        if call.state == 'completed':
            with transaction.atomic():
                job = _job_for(call, text, source, candidate, track, still, now=timezone.now())
            return {'state': 'completed' if job.state == 'complete' else job.state, 'job_id': str(job.pk), 'run_id': run_id}
        return {'state': call.state, 'run_id': run_id}
    return {'state': result['state'], 'run_id': run_id}


def poll_video_job(picture_id, *, api_key=None, transport=https_request, fetch=None, storage=None):
    """Poll one saved job once. A poll never creates or resubmits a video job."""
    key = api_key if api_key is not None else os.environ.get('XAI_API_KEY_PW', '')
    if not key:
        with transaction.atomic():
            job = ContentPicture.objects.select_for_update().get(pk=picture_id)
            if job.state == 'pending' and not (job.poll_lease_until and job.poll_lease_until > timezone.now()):
                job.next_poll_at = None
                job.save(update_fields=['next_poll_at'])
        return {'state': 'unavailable', 'job_id': str(job.pk), 'run_id': job.run_id, 'reschedule': False}
    storage = _store(storage)
    now = timezone.now()
    # Read and decode the still outside transaction locks; check its DB identity
    # again under the job claim before issuing the provider poll.
    preview = ContentPicture.objects.select_related('text__narrative').get(pk=picture_id)
    if preview.state != 'pending':
        return {'state': 'completed' if preview.state == 'complete' else preview.state, 'job_id': str(preview.pk), 'run_id': preview.run_id, 'reschedule': False}
    if not preview.text_id:
        raise ValueError('invalid pending video job')
    try:
        text, source, candidate, track, still = _selected(preview.run_id, preview.text_id, storage)
    except (ValueError, TypeError, KeyError, OSError):
        # Missing/corrupt input cannot justify another submission. Stop boundedly;
        # retaining the published text/still is safer than an endless poison poll.
        with transaction.atomic():
            current = ContentPicture.objects.select_for_update(of=('self',)).select_related('text__narrative').get(pk=picture_id)
            if current.state != 'pending':
                return {'state': current.state, 'job_id': str(current.pk), 'run_id': current.run_id, 'reschedule': False}
            if current.poll_lease_until and current.poll_lease_until > timezone.now():
                return {'state': 'pending', 'job_id': str(current.pk), 'run_id': current.run_id,
                        'reschedule': True, 'countdown': 5}
            current.next_poll_at = None
            current.poll_lease_until = None
            current.save(update_fields=['next_poll_at', 'poll_lease_until'])
        return {'state': 'unknown', 'job_id': str(current.pk), 'run_id': current.run_id,
                'error': 'selected_still_unavailable', 'reschedule': False}
    still_identity = (still.generated_storage_name, still.generated_sha256, still.provenance)
    with transaction.atomic():
        job = ContentPicture.objects.select_for_update(of=('self',)).select_related('text__narrative').get(pk=picture_id)
        if job.state != 'pending':
            return {'state': 'completed' if job.state == 'complete' else job.state, 'job_id': str(job.pk), 'run_id': job.run_id, 'reschedule': False}
        metadata = job.provenance
        if (not isinstance(metadata, dict) or set(metadata) != VIDEO_JOB_FIELDS
                or metadata.get('schema_version') != 'graphics-video-job/v1'
                or metadata.get('terminal_status') is not None or not job.text_id or not job.provider_task_id):
            raise ValueError('invalid pending video job')
        if (job.next_poll_at and job.next_poll_at > now) or (job.poll_lease_until and job.poll_lease_until > now):
            return {'state': 'pending', 'job_id': str(job.pk), 'run_id': job.run_id, 'reschedule': True, 'countdown': 5}
        if job.poll_count >= MAX_POLLS:
            job.next_poll_at = None
            job.save(update_fields=['next_poll_at'])
            return {'state': 'unknown', 'job_id': str(job.pk), 'run_id': job.run_id, 'error': 'poll_limit', 'reschedule': False}
        if job.run_id != preview.run_id or job.text_id != preview.text_id:
            raise ValueError('video job changed during claim')
        still = ContentPicture.objects.select_for_update().get(pk=still.pk)
        if (still.generated_storage_name, still.generated_sha256, still.provenance) != still_identity:
            return {'state': 'stale', 'job_id': str(job.pk), 'run_id': job.run_id, 'reschedule': False}
        call = OriginalContentCall.objects.get(pk=metadata['producer_call_id'])
        stage = 'V1' if candidate == 'A' else 'V-B'
        if (job.text_id != text.pk or job.content_kind != track or job.content_id != str(text.public_id)
                or metadata['candidate_id'] != candidate or metadata['content_id'] != str(source.pk)
                or metadata['input_still_sha256'] != still.generated_sha256 or still.text_id != text.pk
                or still.state != 'complete' or still.run_id != job.run_id or call.run_id != job.run_id
                or call.workflow_key != source.workflow_key or call.state != 'completed'
                or call.kind != 'media' or call.request_identity != f'graphics:{job.run_id}:{stage}'
                or call.stage != f'gfx:{job.run_id}:{stage}' or not isinstance(call.response_payload, dict)
                or call.response_hash != digest(call.response_payload)
                or call.response_payload.get('request_id') != job.provider_task_id):
            raise ValueError('pending video job identity mismatch')
        job.poll_count += 1
        fence = job.poll_count
        job.poll_lease_until = now + POLL_LEASE
        job.save(update_fields=['poll_count', 'poll_lease_until'])
        request_id, call_id, still_hash = job.provider_task_id, call.pk, still.generated_sha256
    try:
        kwargs = {'transport': transport}
        if fetch is not None:
            kwargs['fetch'] = fetch
        outcome = poll_video(request_id, key, **kwargs)
    except Exception:  # noqa: BLE001 -- unknown polling results never cause another submission
        outcome = {'state': 'unknown', 'error': 'poll_unavailable'}
    file_name = None
    receipt = None
    if outcome.get('state') == 'completed':
        try:
            call = OriginalContentCall.objects.get(pk=call_id)
            def loader(alias, name):
                if alias != 'editorial_media' or name != still.generated_storage_name:
                    raise ValueError('invalid video input reference')
                with storage.open(name, 'rb') as stream:
                    return stream.read(MAX_INPUT_BYTES + 1)
            sent_request = reconstruct_request(call.request_packet, call.request_hash, load_bytes=loader)
            data = outcome['data']
            receipt = video_decode_receipt(data, run_id=job.run_id, producer_call_id=call_id,
                                           input_still_sha256=still_hash, sent_request=sent_request)
            file_name = storage.save(f'graphics/{job.run_id}/{receipt["sha256"]}.mp4', ContentFile(data))
        except Exception:  # noqa: BLE001 -- invalid/missing output retains the still
            outcome = {'state': 'unknown', 'error': 'video_decode_or_storage_failed'}
    with transaction.atomic():
        current = ContentPicture.objects.select_for_update(of=('self',)).select_related('text__narrative').get(pk=picture_id)
        if current.state != 'pending' or current.poll_count != fence:
            return {'state': 'stale', 'job_id': str(current.pk), 'run_id': current.run_id, 'reschedule': False}
        current.poll_lease_until = None
        scope = f'featured:{current.text.narrative.workflow_key}:{current.text.locale}'
        advisory_lock('selection:' + scope)
        pointer = OriginalContentSelection.objects.select_for_update().filter(scope_key=scope).first()
        selected_still = ContentPicture.objects.select_for_update().get(pk=still.pk)
        if ((pointer is not None and pointer.text_id != current.text_id)
                or selected_still.state != 'complete' or selected_still.text_id != current.text_id
                or (selected_still.generated_storage_name, selected_still.generated_sha256,
                    selected_still.provenance) != still_identity):
            current.next_poll_at = None
            current.save(update_fields=['poll_lease_until', 'next_poll_at'])
            return {'state': 'stale', 'job_id': str(current.pk), 'run_id': current.run_id, 'reschedule': False}
        state = outcome.get('state')
        if state == 'failed' and outcome.get('provider_status') in VIDEO_TERMINAL_FAILURES:
            current.state = 'failed'
            current.next_poll_at = None
            current.provenance = {**current.provenance, 'terminal_status': outcome['provider_status']}
            current.save(update_fields=['state', 'next_poll_at', 'poll_lease_until', 'provenance'])
            return {'state': 'failed', 'job_id': str(current.pk), 'run_id': current.run_id, 'reschedule': False}
        if state == 'completed' and receipt and file_name:
            current.state = 'complete'
            current.next_poll_at = None
            current.generated_storage_name = file_name
            current.generated_sha256 = receipt['sha256']
            current.provenance = {'schema_version': 'graphics-artifact/v1', 'role': 'video',
                                  'candidate_id': candidate, 'mime': 'video/mp4',
                                  'producer_call_id': call_id, 'content_id': str(source.pk),
                                  'decode_receipt': receipt}
            current.save(update_fields=['state', 'next_poll_at', 'poll_lease_until', 'generated_storage_name', 'generated_sha256', 'provenance'])
            return {'state': 'completed', 'job_id': str(current.pk), 'run_id': current.run_id, 'reschedule': False}
        current.next_poll_at = timezone.now() + POLL_DELAY if current.poll_count < MAX_POLLS else None
        current.save(update_fields=['next_poll_at', 'poll_lease_until'])
        reschedule = current.next_poll_at is not None
        return {'state': 'pending' if state == 'pending' else 'unknown', 'job_id': str(current.pk),
                'run_id': current.run_id, 'reschedule': reschedule, 'countdown': 5 if reschedule else None}
