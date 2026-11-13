"""Exercise the real selected-story pipeline with fake provider transports."""
import json
from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone

from core.models import OriginalContent, OriginalContentCall, OriginalContentRun, Post
from monitor.editorial.graphics_entry import prepare_selected_story
from monitor.editorial.graphics_packages import materialize_package
from tests.editorial_support import (
    editorial_storage as editorial_storage,  # noqa: PLC0414
)

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def selected_run():
    now = timezone.now()
    post = Post.objects.create(tweet_id='12345', text='current text')
    source = {'id': post.pk, 'url': 'https://x.com/i/status/12345', 'original_text': 'saved text',
              'author_handle': 'alice', 'created_at': (now - timedelta(minutes=2)).isoformat()}
    parent = OriginalContentRun.objects.create(source_cycle_id=str(uuid4()), workflow_key='editorial-dispatch',
        scope_key=str(uuid4()), facts_as_of=now, packet_schema_version=1,
        snapshot={'posts': [source], 'context': []}, execution_state='complete')
    content = OriginalContent.objects.create(run=parent, workflow_key='social-brief', output_key=str(uuid4()),
        subject_key='selected', story_id=uuid4(), status='prepared', attempted_at=now,
        brand_key_snapshot='', selection={'post_ids': [post.pk], 'person_ids': []})
    request = prepare_selected_story(content_id=content.pk, run_id=parent.pk, locale='en')
    return materialize_package(request)


def c1():
    return {'schema_version': 'copy-proposals/v3', 'locale': 'en', 'article': 'Shared article.',
      'used_fact_ids': ['F01'], 'evidence_gaps': [], 'candidates': [
          {'id': label, 'headline': headline, 'byline': 'A supported byline.', 'wordplay_meaning': 'A pun.',
           'cultural_reference': None, 'used_fact_ids': ['F01']}
          for label, headline in [('A', 'Primary'), ('B', 'Reserve')]]}


def test_c1_runs_once_and_recovery_moves_forward():
    from monitor.editorial.graphics_pipeline import advance_step

    run, _ = selected_run()
    captures = []
    def transport(endpoint, key, body, **kwargs):
        captures.append((endpoint, body))
        return 200, json.dumps({'model': 'openai/gpt-6-sol', 'usage': {'estimated_cost': '0.01'},
          'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(c1())}}]}).encode()
    result = advance_step(run.pk, owner='worker', keys={'OPENROUTER_API_KEY': 'fake'},
                          transport=transport, configured_daily_limit=40)
    assert result['next_action'] == 'advance'
    call = OriginalContentCall.objects.get(run=run, request_identity=f'graphics:{run.pk}:C1')
    assert call.state == 'completed' and call.response_payload['article'] == 'Shared article.'
    assert len(captures) == 1
    assert result['stage'] == 'C1'


@pytest.mark.parametrize(('usage', 'expected_actual', 'expected_reserved'), [
    ({'cost': '0.0123', 'estimated_cost': '0.001'}, '0.012300', '0.012300'),
    ({'estimated_cost': '0.001'}, None, '0.250000'),
    ({}, None, '0.250000'),
])
def test_openrouter_receipt_releases_only_confirmed_cost(usage, expected_actual, expected_reserved):
    from decimal import Decimal

    from monitor.editorial.graphics_pipeline import advance_step

    run, _ = selected_run()
    def transport(*args, **kwargs):
        return 200, json.dumps({'model': 'openai/gpt-6-sol', 'usage': usage,
            'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(c1())}}]}).encode()
    result = advance_step(run.pk, owner='worker', keys={'OPENROUTER_API_KEY': 'fake'}, transport=transport)
    assert result['state'] == 'completed'
    call = OriginalContentCall.objects.get(request_identity=f'graphics:{run.pk}:C1')
    assert call.actual_usd == (Decimal(expected_actual) if expected_actual is not None else None)
    assert call.reserved_usd == Decimal(expected_reserved)


def test_openrouter_wire_cost_retains_all_decimal_digits():
    from decimal import Decimal

    from monitor.editorial.graphics_pipeline import advance_step

    run, _ = selected_run()
    def transport(*args, **kwargs):
        encoded = json.dumps({'model': 'openai/gpt-6-sol', 'usage': {'cost': 'COST_MARKER'},
            'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(c1())}}]})
        return 200, encoded.replace('"COST_MARKER"', '0.1234567890123456789').encode()
    assert advance_step(run.pk, owner='worker', keys={'OPENROUTER_API_KEY': 'fake'}, transport=transport)['state'] == 'completed'
    call = OriginalContentCall.objects.get(request_identity=f'graphics:{run.pk}:C1')
    assert call.actual_usd == Decimal('0.123457')
    assert call.provenance['graphics_billing_receipt'] == {
        'schema_version': 'graphics-billing-receipt/v1', 'provider': 'openrouter',
        'unit': 'usd', 'amount': '0.1234567890123456789',
    }


def test_corrupt_saved_response_stops_recovery_without_another_call():
    from monitor.editorial.graphics_pipeline import (
        advance_step,
        finalize_if_done,
        pending_action,
    )

    run, _ = selected_run()
    def transport(*args, **kwargs):
        return 200, json.dumps({'model': 'openai/gpt-6-sol', 'usage': {'estimated_cost': '0.01'},
            'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(c1())}}]}).encode()
    advance_step(run.pk, owner='worker', keys={'OPENROUTER_API_KEY': 'fake'}, transport=transport)
    OriginalContentCall.objects.filter(run=run, request_identity=f'graphics:{run.pk}:C1').update(response_payload={})
    result = advance_step(run.pk, owner='worker', keys={'OPENROUTER_API_KEY': 'fake'}, transport=transport)
    assert result['state'] == 'invalid_saved_response'
    assert pending_action(run.pk) is None
    assert finalize_if_done(run.pk)
    run.refresh_from_db()
    assert run.execution_state == 'suspended'
    assert OriginalContentCall.objects.filter(run=run).count() == 1


def test_recovery_finalizes_expired_claim_but_not_live_claim():
    from monitor.editorial.graphics_pipeline import finalize_if_done

    run, _ = selected_run()
    run.decisions = {'graphics_skipped_stages': {'C1': 'credential_unavailable'}}
    run.execution_state = 'running'
    run.claim_owner = 'worker'
    run.lease_until = timezone.now() + timedelta(minutes=1)
    run.save(update_fields=['decisions', 'execution_state', 'claim_owner', 'lease_until'])
    assert not finalize_if_done(run.pk)
    run.lease_until = timezone.now() - timedelta(seconds=1)
    run.save(update_fields=['lease_until'])
    assert finalize_if_done(run.pk)
    run.refresh_from_db()
    assert run.execution_state == 'suspended' and not run.claim_owner and run.lease_until is None


def test_missing_credential_does_not_reserve_or_claim_publication():
    from monitor.editorial.graphics_pipeline import advance_step

    run, _ = selected_run()
    result = advance_step(run.pk, owner='worker', keys={}, configured_daily_limit=40)
    assert result['state'] == 'credential_unavailable'
    assert not OriginalContentCall.objects.filter(run=run).exists()


def test_capacity_contention_leaves_unsent_copy_ready_for_recovery(monkeypatch):
    from monitor.editorial.graphics_pipeline import advance_step, pending_action
    from monitor.editorial.persistence import CapacityHeld

    run, _ = selected_run()
    def busy(*args, **kwargs):
        raise CapacityHeld('graphics creation capacity exhausted')
    monkeypatch.setattr('monitor.editorial.graphics_pipeline._run_text_stage', busy)
    result = advance_step(run.pk, owner='worker', keys={'OPENROUTER_API_KEY': 'fake'})
    run.refresh_from_db()
    assert result['state'] == 'capacity_unavailable'
    assert 'C1' not in run.decisions.get('graphics_skipped_stages', {})
    assert pending_action(run.pk) == {'action': 'advance'}


def test_g0_carries_saved_copy_and_facts_forward_without_extra_c1_call():
    from monitor.editorial.graphics_pipeline import advance_step

    run, _ = selected_run()
    seen = []
    g0 = {'schema_version': 'graphics-discovery/v3', 'queries': [],
          'preferred_sites': [], 'reuse_asset_refs': [], 'approaches': [
              {'candidate_id': label, 'approach': 'original_visual_concept',
               'reason': 'Original idea.', 'reference_target': None}
              for label in ('A', 'B')]}
    def transport(endpoint, key, body, **kwargs):
        seen.append(body)
        response = c1() if len(seen) == 1 else g0
        return 200, json.dumps({'model': 'openai/gpt-6-sol', 'usage': {'estimated_cost': '0.01'},
            'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(response)}}]}).encode()
    first = advance_step(run.pk, owner='worker', keys={'OPENROUTER_API_KEY': 'fake'},
                         transport=transport, configured_daily_limit=40)
    second = advance_step(run.pk, owner='worker', keys={'OPENROUTER_API_KEY': 'fake'},
                          transport=transport, configured_daily_limit=40)
    assert first['stage'] == 'C1' and second['stage'] == 'G0'
    assert second['next_action'] == 'advance'
    assert len(seen) == 2
    assert 'Primary' in json.dumps(seen[1]) and 'saved text' in json.dumps(seen[1])
    assert OriginalContentCall.objects.filter(run=run, state='completed').count() == 2


def test_active_daily_cap_cannot_be_overridden_by_looser_caller(monkeypatch):
    from types import SimpleNamespace

    from monitor.editorial.graphics_pipeline import advance_step

    monkeypatch.setattr('monitor.editorial.graphics_pipeline.load_editorial_config',
                        lambda: SimpleNamespace(enabled=True, daily_usd=0))
    run, _ = selected_run()
    result = advance_step(run.pk, owner='worker', keys={'OPENROUTER_API_KEY': 'fake'},
                          configured_daily_limit=40)
    assert result['state'] == 'budget_or_capacity_unavailable'
    assert not OriginalContentCall.objects.filter(run=run).exists()


def test_copy_is_published_with_original_citation_when_image_key_unavailable():
    from core.models import OriginalContentText
    from monitor.editorial.graphics_pipeline import advance_step

    run, _ = selected_run()
    discovery = {'schema_version': 'graphics-discovery/v3', 'queries': [],
        'preferred_sites': [], 'reuse_asset_refs': [], 'approaches': [
        {'candidate_id': label, 'approach': 'original_visual_concept',
         'reason': 'Original idea.', 'reference_target': None} for label in ('A', 'B')]}
    design = {'schema_version': 'graphics-treatments/v2', 'source_gaps': [], 'treatments': [
        {'candidate_id': label, 'idea': 'A graphic.', 'why_it_bites': 'A joke.', 'input_asset_refs': [],
         'aspect_ratio': '1:1', 'still_prompt': 'Draw it.', 'motion_prompt': 'Move it.'}
        for label in ('A', 'B')]}
    outputs = iter([c1(), discovery, design])
    def transport(endpoint, key, body, **kwargs):
        return 200, json.dumps({'model': 'openai/gpt-6-sol', 'usage': {'estimated_cost': '0.01'},
            'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(next(outputs))}}]}).encode()
    results = [advance_step(run.pk, owner='worker', keys={'OPENROUTER_API_KEY': 'fake'},
                            transport=transport, configured_daily_limit=40) for _ in range(5)]
    assert [r['stage'] for r in results] == ['C1', 'G0', 'source_lookup', 'G1', 'publication']
    assert results[-1]['state'] == 'published'
    text = OriginalContentText.objects.get(pk=results[-1]['text_id'])
    assert text.headline == 'Primary' and text.body == 'Shared article.'
    assert text.sources.exists()
    from monitor.editorial.graphics_pipeline import (
        finalize_if_done,
        pending_action,
        review_step,
    )
    assert pending_action(run.pk)['action'] == 'review'
    failure = review_step(run.pk, owner='review', keys={'OPENROUTER_API_KEY': 'fake'},
        transport=lambda *a, **kw: (400, b'{}'), configured_daily_limit=40)
    assert failure['state'] == 'failed'
    text.refresh_from_db()
    assert text.headline == 'Primary' and text.sources.exists()
    assert pending_action(run.pk) is None
    assert finalize_if_done(run.pk)
    run.refresh_from_db()
    assert run.execution_state == 'complete' and run.outcome['graphics_state'] == 'finished'


def test_real_image_result_is_saved_published_and_dispatchable(editorial_storage):
    import base64
    import io

    from PIL import Image

    from core.models import ContentPicture
    from monitor.editorial.graphics_artifacts import validate_still
    from monitor.editorial.graphics_pipeline import advance_step, pending_action

    run, _ = selected_run()
    discovery = {'schema_version': 'graphics-discovery/v3', 'queries': [],
        'preferred_sites': [], 'reuse_asset_refs': [], 'approaches': [
        {'candidate_id': label, 'approach': 'original_visual_concept',
         'reason': 'Original idea.', 'reference_target': None} for label in ('A', 'B')]}
    design = {'schema_version': 'graphics-treatments/v2', 'source_gaps': [], 'treatments': [
        {'candidate_id': label, 'idea': 'A graphic.', 'why_it_bites': 'A joke.', 'input_asset_refs': [],
         'aspect_ratio': '1:1', 'still_prompt': 'Draw it.', 'motion_prompt': 'Move it.'}
        for label in ('A', 'B')]}
    outputs = iter([c1(), discovery, design])
    image = io.BytesIO()
    Image.new('RGB', (8, 8), 'red').save(image, format='PNG')
    calls = []
    def transport(endpoint, key, body, **kwargs):
        calls.append(endpoint)
        if '/images/' in endpoint:
            return 200, json.dumps({'data': [{'b64_json': base64.b64encode(image.getvalue()).decode()}],
                                    'usage': {'cost_in_usd_ticks': 600000000}}).encode()
        return 200, json.dumps({'model': 'openai/gpt-6-sol', 'usage': {'estimated_cost': '0.01'},
            'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(next(outputs))}}]}).encode()
    results = [advance_step(run.pk, owner='worker', keys={'OPENROUTER_API_KEY': 'fake', 'XAI_API_KEY_PW': 'fake'},
                            transport=transport, configured_daily_limit=40) for _ in range(6)]
    assert [r['stage'] for r in results] == ['C1', 'G0', 'source_lookup', 'G1', 'I-A', 'publication']
    assert results[4]['state'] == 'completed', results
    image_call = OriginalContentCall.objects.get(request_identity=f'graphics:{run.pk}:I-A')
    assert str(image_call.actual_usd) == '0.060000'
    assert results[-1]['next_action'] == 'video' and not results[-1]['review_due']
    picture = ContentPicture.objects.get(run=run, provenance__role='still')
    content = OriginalContent.objects.get(run=run, output_key='graphics-primary/v1')
    validate_still(picture, content=content, candidate='A')
    assert pending_action(run.pk) == {'action': 'video', 'text_id': results[-1]['text_id'], 'review_due': False}
    assert len(calls) == 4
    from monitor.editorial.graphics_packages import claim_package, release_package
    from monitor.editorial.graphics_pipeline import review_step
    from monitor.editorial.graphics_video import submit_video_job
    assert advance_step(run.pk, owner='duplicate', keys={})['next_action'] == 'video'
    assert review_step(run.pk, owner='early-review', keys={})['state'] == 'waiting_for_media'
    claim = claim_package(run.pk, owner='video')
    assert submit_video_job(run.pk, results[-1]['text_id'], owner='video', fence=claim.fence,
                            api_key='')['state'] == 'unavailable'
    assert release_package(run.pk, owner='video', fence=claim.fence)
    def review_transport(endpoint, key, body, **kwargs):
        content = body['messages'][1]['content']
        prompt = content[0]['text'] if isinstance(content, list) else content
        inputs, _ = json.JSONDecoder().raw_decode(prompt.split('\n\nSUPPLIED INPUTS:\n', 1)[1])
        score = {'schema_version': 'eic-scorecard/v1', 'text_id': inputs['text_id'],
            'content_revision': inputs['content_revision'], 'summary': 'Reviewed.',
            'scores': {name: 4 for name in ('factual_support', 'attribution_uncertainty', 'headline_craft',
                'clarity_context', 'image_claim_fit', 'likeness', 'lettering')},
            'findings': [], 'reviewed_asset_refs': ['published:still'], 'not_reviewed': [],
            'suggested_admin_follow_up': []}
        return 200, json.dumps({'model': 'openai/gpt-6-sol', 'usage': {'estimated_cost': '0.01'},
            'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(score)}}]}).encode()
    reviewed = review_step(run.pk, owner='reviewer', keys={'OPENROUTER_API_KEY': 'fake'},
                           transport=review_transport, configured_daily_limit=40)
    assert reviewed['state'] == 'completed'
    assert pending_action(run.pk) is None
    assert review_step(run.pk, owner='reviewer', keys={}, configured_daily_limit=40)['state'] == 'completed'


@pytest.mark.parametrize('first_status,expect_fallback', [(400, True), (503, False)])
def test_reserve_is_used_only_for_definite_image_failure(editorial_storage, first_status, expect_fallback):
    import base64
    import io

    from PIL import Image

    from monitor.editorial.graphics_pipeline import advance_step, pending_action

    run, _ = selected_run()
    discovery = {'schema_version': 'graphics-discovery/v3', 'queries': [], 'preferred_sites': [],
        'reuse_asset_refs': [], 'approaches': [{'candidate_id': label, 'approach': 'original_visual_concept',
        'reason': 'Original idea.', 'reference_target': None} for label in ('A', 'B')]}
    design = {'schema_version': 'graphics-treatments/v2', 'source_gaps': [], 'treatments': [
        {'candidate_id': label, 'idea': 'A graphic.', 'why_it_bites': 'A joke.', 'input_asset_refs': [],
         'aspect_ratio': '1:1', 'still_prompt': 'Draw it.', 'motion_prompt': 'Move it.'}
        for label in ('A', 'B')]}
    outputs = iter([c1(), discovery, design])
    image = io.BytesIO()
    Image.new('RGB', (8, 8), 'red').save(image, format='PNG')
    image_calls = []
    def transport(endpoint, key, body, **kwargs):
        if '/images/' in endpoint:
            image_calls.append(body)
            if len(image_calls) == 1:
                return first_status, b'{}'
            return 200, json.dumps({'data': [{'b64_json': base64.b64encode(image.getvalue()).decode()}]}).encode()
        return 200, json.dumps({'model': 'openai/gpt-6-sol', 'usage': {'estimated_cost': '0.01'},
            'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(next(outputs))}}]}).encode()
    def step():
        return advance_step(run.pk, owner='worker', keys={'OPENROUTER_API_KEY': 'fake', 'XAI_API_KEY_PW': 'fake'},
                            transport=transport, configured_daily_limit=40)
    results = [step() for _ in range(6)]
    assert results[-1]['stage'] == 'publication'
    assert results[-1]['state'] == 'published'
    if expect_fallback:
        assert results[-1]['next_action'] == 'advance'
        assert pending_action(run.pk)['action'] == 'advance'
        assert step()['stage'] == 'I-B'
        result = step()
        assert result['stage'] == 'fallback' and result['next_action'] == 'video'
        assert len(image_calls) == 2
    else:
        assert results[-1]['next_action'] == 'review'
        assert pending_action(run.pk)['action'] == 'review'
        assert len(image_calls) == 1
        from monitor.editorial.graphics_pipeline import finalize_if_done, review_step
        assert review_step(run.pk, owner='review', keys={})['state'] == 'credential_unavailable'
        assert pending_action(run.pk) is None and finalize_if_done(run.pk)
        run.refresh_from_db()
        assert run.execution_state == 'suspended'
        assert run.outcome['graphics_state'] == 'attention_required'


def test_failed_video_replaces_a_only_after_saved_terminal_evidence(editorial_storage):
    import base64
    import io

    from PIL import Image

    from monitor.editorial.graphics_packages import claim_package, release_package
    from monitor.editorial.graphics_pipeline import advance_step, pending_action
    from monitor.editorial.graphics_video import poll_video_job, submit_video_job

    run, _ = selected_run()
    discovery = {'schema_version': 'graphics-discovery/v3', 'queries': [], 'preferred_sites': [],
        'reuse_asset_refs': [], 'approaches': [{'candidate_id': label, 'approach': 'original_visual_concept',
        'reason': 'Original idea.', 'reference_target': None} for label in ('A', 'B')]}
    design = {'schema_version': 'graphics-treatments/v2', 'source_gaps': [], 'treatments': [
        {'candidate_id': label, 'idea': 'A graphic.', 'why_it_bites': 'A joke.', 'input_asset_refs': [],
         'aspect_ratio': '1:1', 'still_prompt': 'Draw it.', 'motion_prompt': 'Move it.'}
        for label in ('A', 'B')]}
    outputs = iter([c1(), discovery, design])
    data = io.BytesIO()
    Image.new('RGB', (8, 8), 'red').save(data, format='PNG')
    image_calls = []
    def creation(endpoint, key, body, **kwargs):
        if '/images/' in endpoint:
            image_calls.append(1)
            return 200, json.dumps({'data': [{'b64_json': base64.b64encode(data.getvalue()).decode()}]}).encode()
        return 200, json.dumps({'model': 'openai/gpt-6-sol', 'usage': {'estimated_cost': '0.01'},
            'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(next(outputs))}}]}).encode()
    def step():
        return advance_step(run.pk, owner='worker', keys={'OPENROUTER_API_KEY': 'fake', 'XAI_API_KEY_PW': 'fake'},
                            transport=creation, configured_daily_limit=40)
    results = [step() for _ in range(6)]
    assert results[-1]['next_action'] == 'video'
    claim = claim_package(run.pk, owner='video')
    submission = submit_video_job(run.pk, results[-1]['text_id'], owner='video', fence=claim.fence,
        api_key='fake', transport=lambda *a, **kw: (200, b'{"request_id":"job-123"}'), configured_daily_limit=40)
    release_package(run.pk, owner='video', fence=claim.fence)
    assert submission['state'] == 'pending'
    poll = poll_video_job(submission['job_id'], api_key='fake',
                          transport=lambda *a, **kw: (200, b'{"status":"failed"}'))
    assert poll['state'] == 'failed'
    assert pending_action(run.pk)['action'] == 'advance'
    assert step()['stage'] == 'I-B'
    fallback = step()
    assert fallback['stage'] == 'fallback' and fallback['next_action'] == 'video'
    assert fallback['text_id'] != results[-1]['text_id']
    assert len(image_calls) == 2


def test_search_reserves_before_transport_and_timeout_never_repeats():
    from decimal import Decimal

    from monitor.editorial.graphics_pipeline import advance_step
    from monitor.original_content import budget_totals

    run, _ = selected_run()
    discovery = {'schema_version': 'graphics-discovery/v3', 'queries': ['作品アート'],
        'preferred_sites': [], 'reuse_asset_refs': [], 'approaches': [
        {'candidate_id': label, 'approach': 'original_visual_concept',
         'reason': 'Original idea.', 'reference_target': None} for label in ('A', 'B')]}
    outputs = iter([c1(), discovery])
    def transport(endpoint, key, body, **kwargs):
        return 200, json.dumps({'model': 'openai/gpt-6-sol', 'usage': {'estimated_cost': '0.01'},
            'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(next(outputs))}}]}).encode()
    seen = []
    def search(query, *, api_key):
        import hashlib

        from monitor.editorial.graphics_search import search_exa_query
        call = OriginalContentCall.objects.get(run=run, request_identity=f'graphics:{run.pk}:S1')
        assert call.state == 'sent' and call.reserved_usd == Decimal('0.020000')
        assert budget_totals('editorial', call.budget_day)['calls'] == 2
        def transport(request, timeout):
            assert hashlib.sha256(request.data).hexdigest() == call.request_hash
            seen.append(query)
            raise TimeoutError('unknown provider outcome')
        return search_exa_query(query, api_key=api_key, transport=transport)
    keys = {'OPENROUTER_API_KEY': 'fake', 'EXA_API_KEY': 'fake'}
    for _ in range(3):
        result = advance_step(run.pk, owner='worker', keys=keys, transport=transport,
                              configured_daily_limit=40, search=search)
    assert result['stage'] == 'source_lookup' and seen == ['作品アート']
    call = OriginalContentCall.objects.get(run=run, request_identity=f'graphics:{run.pk}:S1')
    assert call.state == 'ambiguous' and call.reserved_usd == Decimal('0.020000')
    run.refresh_from_db()
    assert run.decisions['graphics_source_search']['evidence']['query_outcomes'][0]['state'] == 'ambiguous'
    advance_step(run.pk, owner='worker', keys={}, configured_daily_limit=40, search=search)
    assert seen == ['作品アート']
