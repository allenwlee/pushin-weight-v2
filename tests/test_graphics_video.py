"""Saved-ID video polling must never submit another provider job."""
import json
from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import ContentPicture
from monitor.editorial.graphics_video import MAX_POLLS, poll_video_job
from tests.test_graphics_publication import (  # noqa: F401
    _video_job_case,
    publication_case,
)

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def test_missing_poll_key_stops_scheduled_poll_without_losing_job(publication_case, tmp_path):  # noqa: F811
    _, _, _, storage, _, job = _video_job_case(publication_case, tmp_path, status='pending')
    result = poll_video_job(job.pk, api_key='', storage=storage)
    job.refresh_from_db()
    assert result['state'] == 'unavailable' and result['run_id'] == job.run_id
    assert job.state == 'pending' and job.next_poll_at is None


def test_pending_poll_is_scheduled_and_repeated_early_poll_does_not_call(publication_case, tmp_path):  # noqa: F811
    _, _, _, storage, _, job = _video_job_case(publication_case, tmp_path, status='pending')
    calls = []
    def transport(url, key, body, **kwargs):
        calls.append((url, body, kwargs['method']))
        return 200, json.dumps({'status': 'pending'}).encode()
    result = poll_video_job(job.pk, api_key='fake', storage=storage, transport=transport)
    assert result['state'] == 'pending' and result['reschedule'] is True
    assert result['run_id'] == job.run_id and calls == [('https://api.x.ai/v1/videos/video-123', None, 'GET')]
    job.refresh_from_db()
    assert job.poll_count == 2 and job.next_poll_at > timezone.now() and job.state == 'pending'
    assert poll_video_job(job.pk, api_key='fake', storage=storage, transport=transport)['state'] == 'pending'
    assert len(calls) == 1


def test_definite_failure_saves_terminal_evidence(publication_case, tmp_path):  # noqa: F811
    from monitor.editorial.graphics_artifacts import validate_failed_video_job

    primary, call, _, storage, _, job = _video_job_case(publication_case, tmp_path, status='pending')
    def transport(_url, _key, _body, **_kwargs):
        return 200, json.dumps({'status': 'moderated'}).encode()
    result = poll_video_job(job.pk, api_key='fake', storage=storage, transport=transport)
    job.refresh_from_db()
    assert result['state'] == 'failed' and result['reschedule'] is False
    assert job.state == 'failed' and job.provenance['terminal_status'] == 'moderated'
    assert validate_failed_video_job(job, content=primary.narrative, primary_text=primary,
                                     producer_call=call, storage=storage)['terminal_status'] == 'moderated'


def test_unknown_provider_result_never_marks_definite_failure(publication_case, tmp_path):  # noqa: F811
    _, _, _, storage, _, job = _video_job_case(publication_case, tmp_path, status='pending')
    def transport(_url, _key, _body, **_kwargs):
        return 503, b'not available'
    result = poll_video_job(job.pk, api_key='fake', storage=storage, transport=transport)
    job.refresh_from_db()
    assert result['state'] == 'unknown' and result['reschedule'] is True
    assert job.state == 'pending' and job.provenance['terminal_status'] is None


def test_poll_limit_does_not_reschedule_forever(publication_case, tmp_path):  # noqa: F811
    _, _, _, storage, _, job = _video_job_case(publication_case, tmp_path, status='pending')
    ContentPicture.objects.filter(pk=job.pk).update(poll_count=MAX_POLLS, next_poll_at=timezone.now()-timedelta(seconds=1))
    def forbidden(*_args, **_kwargs):
        pytest.fail('poll budget exhausted')
    result = poll_video_job(job.pk, api_key='fake', storage=storage, transport=forbidden)
    job.refresh_from_db()
    assert result['state'] == 'unknown' and result['reschedule'] is False
    assert job.state == 'pending' and job.next_poll_at is None


def test_stale_poll_cannot_overwrite_newer_claim(publication_case, tmp_path):  # noqa: F811
    _, _, _, storage, _, job = _video_job_case(publication_case, tmp_path, status='pending')
    def transport(_url, _key, _body, **_kwargs):
        ContentPicture.objects.filter(pk=job.pk).update(poll_count=99)
        return 200, json.dumps({'status': 'failed'}).encode()
    result = poll_video_job(job.pk, api_key='fake', storage=storage, transport=transport)
    job.refresh_from_db()
    assert result['state'] == 'stale' and result['reschedule'] is False
    assert job.state == 'pending' and job.provenance['terminal_status'] is None


def _submission_case(publication_case, tmp_path):  # noqa: F811
    from core.models import OriginalContentCall
    from monitor.original_content import digest

    primary, previous, _, storage, _, job = _video_job_case(publication_case, tmp_path, status='pending')
    job.delete()
    previous.delete()
    run = primary.narrative.run
    run.workflow_key = 'graphics-package'
    run.execution_state = 'running'
    run.claim_owner = 'test-worker'
    run.fence = 1
    run.lease_until = timezone.now() + timedelta(minutes=5)
    run.config_snapshot = {'per_story_usd': '4', 'daily_usd': '40'}
    run.save()
    result = {'treatments': [{'candidate_id': 'A', 'aspect_ratio': '1:1', 'motion_prompt': 'Move slowly'}]}
    now = timezone.now()
    OriginalContentCall.objects.create(
        run=run, stage=f'gfx:{run.pk}:G1', workflow_key='social-brief',
        request_identity=f'graphics:{run.pk}:G1', request_hash='a'*64,
        response_hash=digest(result), response_payload=result, state='completed',
        reserved_at=now, sent_at=now, completed_at=now,
    )
    return primary, run, storage


def test_submission_saves_provider_id_and_restart_does_not_resubmit(publication_case, tmp_path):  # noqa: F811
    from monitor.editorial.graphics_video import submit_video_job

    primary, run, storage = _submission_case(publication_case, tmp_path)
    sent = []
    def transport(url, _key, body, **_kwargs):
        sent.append((url, body))
        return 200, json.dumps({'request_id': 'accepted-123'}).encode()
    kwargs = {'owner': 'test-worker', 'fence': 1, 'pack': publication_case[0],
              'api_key': 'fake', 'storage': storage, 'transport': transport}
    first = submit_video_job(run.pk, primary.pk, **kwargs)
    second = submit_video_job(run.pk, primary.pk, **kwargs)
    assert first['state'] == second['state'] == 'pending'
    assert first['job_id'] == second['job_id'] and len(sent) == 1
    job = ContentPicture.objects.get(pk=first['job_id'])
    assert job.provider_task_id == 'accepted-123' and job.state == 'pending'


def test_rejected_completion_is_ambiguous_and_never_resubmits(publication_case, tmp_path, monkeypatch):  # noqa: F811
    from core.models import OriginalContentCall
    from monitor.editorial import graphics_video

    primary, run, storage = _submission_case(publication_case, tmp_path)
    sent = []
    def transport(*_args, **_kwargs):
        sent.append(1)
        return 200, json.dumps({'request_id': 'accepted-123'}).encode()
    monkeypatch.setattr(graphics_video, 'complete_graphics_call', lambda *_args, **_kwargs: False)
    kwargs = {'owner': 'test-worker', 'fence': 1, 'pack': publication_case[0],
              'api_key': 'fake', 'storage': storage, 'transport': transport}
    result = graphics_video.submit_video_job(run.pk, primary.pk, **kwargs)
    assert result['state'] == 'ambiguous'
    call = OriginalContentCall.objects.get(request_identity=f'graphics:{run.pk}:V1')
    assert call.state == 'ambiguous' and call.error_code == 'result_persistence_unknown'
    assert graphics_video.submit_video_job(run.pk, primary.pk, **kwargs)['state'] == 'ambiguous'
    assert len(sent) == 1 and not ContentPicture.objects.filter(provider_task_id='accepted-123').exists()


def test_successful_poll_attaches_decoded_video_to_selected_text(publication_case, tmp_path, monkeypatch):  # noqa: F811
    from decimal import Decimal

    from monitor.editorial import graphics_video

    primary, call, _, storage, _, job = _video_job_case(publication_case, tmp_path, status='pending')
    data = b'fake decoded video bytes'
    import hashlib
    sha = hashlib.sha256(data).hexdigest()
    def transport(_url, _key, _body, **_kwargs):
        return 200, json.dumps({'status': 'done', 'video': {'url': 'https://example.test/video'},
                                'usage': {'cost_in_usd_ticks': 1600000000}}).encode()
    def fetch(_url, **_kwargs):
        return data, 'https://example.test/video', 'video/mp4'
    monkeypatch.setattr(graphics_video, 'reconstruct_request', lambda *_args, **_kwargs: {'model': 'fake'})
    monkeypatch.setattr(graphics_video, 'video_decode_receipt', lambda *_args, **_kwargs: {'sha256': sha})
    recorded = []
    def record(*args, **kwargs):
        recorded.append((args, kwargs))
        return True
    monkeypatch.setattr(graphics_video, 'record_graphics_video_cost', record)
    result = poll_video_job(job.pk, api_key='fake', storage=storage, transport=transport, fetch=fetch)
    job.refresh_from_db()
    assert result['state'] == 'completed' and job.state == 'complete'
    assert job.text_id == primary.pk and job.generated_sha256 == sha
    assert recorded == [((call.pk,), {'request_id': 'video-123', 'actual_usd': Decimal('0.16')})]
    assert storage.open(job.generated_storage_name, 'rb').read() == data


def test_missing_video_key_is_recorded_without_creating_a_call(publication_case, tmp_path):  # noqa: F811
    from monitor.editorial.graphics_video import submit_video_job

    primary, run, storage = _submission_case(publication_case, tmp_path)
    result = submit_video_job(run.pk, primary.pk, owner='test-worker', fence=1,
                              api_key='', storage=storage)
    run.refresh_from_db()
    assert result['state'] == 'unavailable'
    assert run.decisions['graphics_skipped_stages']['V1'] == 'credential_unavailable'


def test_unavailable_selected_still_stops_video_submission(publication_case, tmp_path, monkeypatch):  # noqa: F811
    from core.models import OriginalContentCall
    from monitor.editorial import graphics_video

    primary, run, storage = _submission_case(publication_case, tmp_path)
    def missing(*args, **kwargs):
        raise ValueError('video text is not the current selection')
    monkeypatch.setattr(graphics_video, '_selected', missing)
    result = graphics_video.submit_video_job(run.pk, primary.pk, owner='test-worker', fence=1,
                                             api_key='fake', storage=storage)
    run.refresh_from_db()
    assert result['state'] == 'unavailable'
    assert run.decisions['graphics_skipped_stages']['V1'] == 'selected_still_unavailable'
    assert not OriginalContentCall.objects.filter(request_identity=f'graphics:{run.pk}:V1').exists()
    assert not OriginalContentCall.objects.filter(request_identity=f'graphics:{run.pk}:V1').exists()


def test_enabled_daily_cap_applies_to_explicit_caller_limit(publication_case, tmp_path, monkeypatch):  # noqa: F811
    from types import SimpleNamespace

    from monitor.editorial import config, graphics_video
    from monitor.editorial.persistence import BudgetHeld

    primary, run, storage = _submission_case(publication_case, tmp_path)
    observed = []
    monkeypatch.setattr(config, 'load_editorial_config', lambda: SimpleNamespace(enabled=True, daily_usd='2'))
    def reserve(**kwargs):
        observed.append(kwargs['configured_daily_limit'])
        raise BudgetHeld('limit')
    monkeypatch.setattr(graphics_video, 'reserve_graphics_call', reserve)
    result = graphics_video.submit_video_job(run.pk, primary.pk, owner='test-worker', fence=1,
        pack=publication_case[0], api_key='fake', storage=storage, configured_daily_limit='10')
    run.refresh_from_db()
    assert result['state'] == 'unavailable' and str(observed[0]) == '2'
    assert run.decisions['graphics_skipped_stages']['V1'] == 'budget_or_capacity_unavailable'
