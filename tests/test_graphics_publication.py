"""Graphics publication preserves source ownership and an immutable A edition."""
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
from django.utils import timezone

from core.models import (
    OriginalContent,
    OriginalContentCall,
    OriginalContentRun,
    OriginalContentSelection,
    Post,
)
from monitor.editorial.graphics_contracts import build_task, load_pack
from monitor.editorial.graphics_publication import publish_primary
from monitor.original_content import digest

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


@pytest.fixture
def publication_case():
    pack = load_pack(Path(__file__).resolve().parents[1] / 'config/editorial_prompts/editorial-creative-roles-v1.json')
    now = timezone.now()
    run = OriginalContentRun.objects.create(source_cycle_id=str(uuid4()), workflow_key='editorial-dispatch', scope_key=str(uuid4()), facts_as_of=now, packet_schema_version=1, snapshot={})
    content = OriginalContent.objects.create(run=run, workflow_key='social-brief', output_key='story:A', subject_key='ram', story_id=uuid4(), status='prepared', attempted_at=now, brand_key_snapshot='')
    Post.objects.create(tweet_id='123', text='Saved source', author_handle='original')
    source = {'id': '123', 'url': 'https://x.com/i/status/123', 'original_text': 'Saved source', 'author_handle': 'original'}
    facts = [{'fact_id': 'F01', 'claim': 'Saved source', 'source_refs': [source['url']], 'source_post_id': '123', 'snapshot_hash': digest(source)}]
    candidates = [{'id': key, 'headline': title, 'byline': 'A source line', 'wordplay_meaning': 'Wordplay', 'cultural_reference': None, 'used_fact_ids': ['F01']} for key, title in [('A', 'Ram I Am'), ('B', 'Memory Lane')]]
    copy = {'schema_version': 'copy-proposals/v3', 'locale': 'en', 'candidates': candidates, 'article': 'Saved story.', 'used_fact_ids': ['F01'], 'evidence_gaps': []}
    schema = next(c['response_schema'] for c in pack['model_call_plan']['calls'] if c['id'] == 'C1')
    task = build_task('Write the story', {'fact_items': facts}, schema)
    wire = json.dumps({'messages': [{'role': 'user', 'content': task}]})
    call = OriginalContentCall.objects.create(run=run, stage=f'gfx:{run.pk}:C1', workflow_key=content.workflow_key, request_identity=f'graphics:{run.pk}:C1', request_hash=hashlib.sha256(wire.encode()).hexdigest(), request_packet={'schema_version':'graphics-request/v1','request_json':wire}, response_hash=digest(copy), response_payload=copy, state='completed', reserved_at=now, sent_at=now, completed_at=now)
    return pack, content, call


def test_primary_uses_persisted_producer_copy_and_real_citation(publication_case):
    pack, content, call = publication_case
    source = {'id': '123', 'url': 'https://x.com/i/status/123', 'original_text': 'Saved source', 'author_handle': 'original'}
    Post.objects.filter(pk='123').update(text='Edited after writing', author_handle='newhandle')
    text = publish_primary(content=content, producer=call, pack=pack, sources=[source], selected_scope='featured:social-brief:en')
    assert (text.headline, text.body, text.producing_call_id) == ('Ram I Am', 'Saved story.', call.pk)
    assert list(text.sources.values_list('post_id', flat=True)) == ['123']
    citation = text.sources.get()
    assert citation.source_hash == digest(source)
    assert citation.author_label_snapshot == 'original'
    assert OriginalContentSelection.objects.get(scope_key='featured:social-brief:en').text_id == text.pk


def test_missing_real_post_rolls_back_publication(publication_case):
    pack, content, call = publication_case
    Post.objects.filter(pk='123').delete()
    with pytest.raises(ValueError, match='missing cited posts'):
        publish_primary(content=content, producer=call, pack=pack, sources=[{'id':'123', 'url':'https://x.com/i/status/123', 'original_text':'Saved source', 'author_handle':'original'}])
    content.refresh_from_db()
    assert content.status == 'prepared'
    assert not content.localized_texts.exists()


def test_unrelated_citation_is_rejected(publication_case):
    pack, content, call = publication_case
    Post.objects.create(tweet_id='456', text='Unrelated')
    with pytest.raises(ValueError, match='citation.*handoff'):
        publish_primary(content=content, producer=call, pack=pack, sources=[{'post_id':'456', 'url':'https://x.com/i/status/456'}])


def test_changed_source_snapshot_is_rejected(publication_case):
    pack, content, call = publication_case
    with pytest.raises(ValueError, match='snapshot'):
        publish_primary(content=content, producer=call, pack=pack, sources=[{
            'id': '123', 'url': 'https://x.com/i/status/123',
            'original_text': 'Different text', 'author_handle': 'original',
        }])


def test_citations_follow_the_facts_used_by_each_edition():
    from monitor.editorial.graphics_publication import _used_citations
    from monitor.original_content import digest

    sources = [
        {'id': value, 'url': f'https://x.com/i/status/{value}', 'original_text': f'Source {value}'}
        for value in ('111', '222', '333')
    ]
    for source in sources:
        Post.objects.create(tweet_id=source['id'], text=source['original_text'])
    facts = [{'fact_id': f'F{index:02}', 'source_post_id': source['id'],
              'source_refs': [source['url']], 'snapshot_hash': digest(source)}
             for index, source in enumerate(sources, 1)]
    assert [item['post_id'] for item in _used_citations(sources, facts, ['F01', 'F02'])] == ['111', '222']
    assert [item['post_id'] for item in _used_citations(sources, facts, ['F01', 'F03'])] == ['111', '333']


def _fallback_case(publication_case, tmp_path):
    import io

    from django.core.files.storage import FileSystemStorage
    from PIL import Image

    from core.models import ContentPicture
    from monitor.editorial.graphics_publication import publish_primary

    pack, content, call = publication_case
    sources = [{'id': '123', 'url': 'https://x.com/i/status/123', 'original_text': 'Saved source', 'author_handle': 'original'}]
    primary = publish_primary(content=content, producer=call, pack=pack, sources=sources, selected_scope='featured:social-brief:en')
    now = timezone.now()
    failure = OriginalContentCall.objects.create(run=content.run, stage=f'gfx:{content.run_id}:I-A', workflow_key=content.workflow_key, kind='media', request_identity=f'graphics:{content.run_id}:I-A', request_hash='d'*64, state='failed', error_code='provider_failed', reserved_at=now, sent_at=now)
    image_call = OriginalContentCall.objects.create(run=content.run, stage=f'gfx:{content.run_id}:I-B', workflow_key=content.workflow_key, kind='media', request_identity=f'graphics:{content.run_id}:I-B', request_hash='e'*64, response_hash='f'*64, state='completed', reserved_at=now, sent_at=now, completed_at=now)
    file = tmp_path / 'reserve.png'
    img = Image.new('RGB', (2, 2), 'red')
    data = io.BytesIO()
    img.save(data, format='PNG')
    file.write_bytes(data.getvalue())
    picture = ContentPicture.objects.create(run=content.run, content_kind='chatter', content_id=str(content.pk), revision_hash='1'*64, mode='derive', state='complete', generated_storage_name='reserve.png', generated_sha256=hashlib.sha256(data.getvalue()).hexdigest(), provenance={'schema_version':'graphics-artifact/v1', 'role':'still', 'candidate_id':'B', 'mime':'image/png', 'producer_call_id':image_call.pk, 'content_id':str(content.pk)})
    return primary, failure, picture, FileSystemStorage(location=tmp_path), sources


def test_fallback_keeps_a_and_is_idempotent(publication_case, tmp_path):
    from monitor.editorial.graphics_publication import publish_fallback

    pack, _, _ = publication_case
    primary, failure, picture, storage, sources = _fallback_case(publication_case, tmp_path)
    kwargs = {'primary_text': primary, 'failure_call': failure, 'reserve_picture': picture, 'pack': pack, 'sources': sources, 'selected_scope': 'featured:social-brief:en', 'storage': storage}
    b = publish_fallback(**kwargs)
    assert b.headline == 'Memory Lane'
    assert b.body == primary.body
    assert b.narrative_id != primary.narrative_id
    assert b.narrative.provenance['predecessor_id'] == primary.narrative_id
    assert list(b.sources.values_list('post_id', 'source_hash')) == list(primary.sources.values_list('post_id', 'source_hash'))
    assert publish_fallback(**kwargs).pk == b.pk
    assert OriginalContentSelection.objects.get(scope_key='featured:social-brief:en').text_id == b.pk


def test_fallback_does_not_replace_another_equal_time_pointer(publication_case, tmp_path):
    from monitor.editorial.graphics_publication import publish_fallback

    pack, content, _ = publication_case
    primary, failure, picture, storage, sources = _fallback_case(publication_case, tmp_path)
    other = OriginalContent.objects.create(run=content.run, workflow_key='social-brief', output_key='other', subject_key='other', story_id=uuid4(), status='prepared', attempted_at=timezone.now(), brand_key_snapshot='')
    # Same cutoff, different edition: this is exactly the case publisher's
    # timestamp-only guard does not distinguish.
    from core.models import OriginalContentText
    text = OriginalContentText.objects.create(narrative=other, locale='en', headline='Newer', secondary='Other')
    OriginalContentSelection.objects.filter(scope_key='featured:social-brief:en').update(text=text)
    result = publish_fallback(primary_text=primary, failure_call=failure, reserve_picture=picture, pack=pack, sources=sources, selected_scope='featured:social-brief:en', storage=storage)
    assert result.pk == primary.pk
    assert OriginalContentSelection.objects.get(scope_key='featured:social-brief:en').text_id == text.pk
    assert not OriginalContent.objects.filter(output_key=f'graphics-fallback:{content.pk}').exists()


def test_invalid_reserve_file_keeps_primary(publication_case, tmp_path):
    from monitor.editorial.graphics_publication import publish_fallback

    pack, content, _ = publication_case
    primary, failure, picture, storage, sources = _fallback_case(publication_case, tmp_path)
    (tmp_path / 'reserve.png').write_bytes(b'changed')
    result = publish_fallback(primary_text=primary, failure_call=failure, reserve_picture=picture, pack=pack, sources=sources, selected_scope='featured:social-brief:en', storage=storage)
    assert result.pk == primary.pk
    assert OriginalContentSelection.objects.get(scope_key='featured:social-brief:en').text_id == primary.pk
    assert not OriginalContent.objects.filter(output_key=f'graphics-fallback:{content.pk}').exists()


def test_ambiguous_a_failure_cannot_trigger_reserve(publication_case, tmp_path):
    from monitor.editorial.graphics_publication import publish_fallback

    pack, _, _ = publication_case
    primary, failure, picture, storage, sources = _fallback_case(publication_case, tmp_path)
    failure.state = 'ambiguous'
    failure.save(update_fields=['state'])
    with pytest.raises(ValueError, match='definite same-run'):
        publish_fallback(primary_text=primary, failure_call=failure, reserve_picture=picture, pack=pack, sources=sources, selected_scope='featured:social-brief:en', storage=storage)


def _video_job_case(publication_case, tmp_path, *, status='failed'):
    from core.models import ContentPicture

    primary, initial_failure, reserve, storage, sources = _fallback_case(publication_case, tmp_path)
    initial_failure.delete()
    run = primary.narrative.run
    now = timezone.now()
    response = {'request_id': 'video-123'}
    call = OriginalContentCall.objects.create(
        run=run, stage=f'gfx:{run.pk}:V1', workflow_key='social-brief', kind='media',
        request_identity=f'graphics:{run.pk}:V1', request_hash='9'*64,
        state='completed', response_payload=response, response_hash=digest(response),
        reserved_at=now, sent_at=now, completed_at=now,
    )
    still_call = OriginalContentCall.objects.create(
        run=run, stage=f'gfx:{run.pk}:I-A', workflow_key='social-brief', kind='media',
        request_identity=f'graphics:{run.pk}:I-A', request_hash='8'*64,
        state='completed', response_hash='7'*64,
        reserved_at=now, sent_at=now, completed_at=now,
    )
    data = (tmp_path / 'reserve.png').read_bytes()
    still = ContentPicture.objects.create(
        run=run, text=primary, content_kind='chatter', content_id=str(primary.public_id),
        revision_hash='2'*64, mode='derive', state='complete',
        generated_storage_name='reserve.png', generated_sha256=hashlib.sha256(data).hexdigest(),
        provenance={'schema_version': 'graphics-artifact/v1', 'role': 'still',
                    'candidate_id': 'A', 'mime': 'image/png',
                    'producer_call_id': still_call.pk, 'content_id': str(primary.narrative_id)},
    )
    job = ContentPicture.objects.create(
        run=run, text=primary, content_kind='chatter', content_id=str(primary.public_id),
        revision_hash='3'*64, mode='derive', state=status,
        provider_task_id='video-123', poll_count=1,
        provenance={'schema_version': 'graphics-video-job/v1', 'candidate_id': 'A',
                    'content_id': str(primary.narrative_id), 'producer_call_id': call.pk,
                    'input_still_sha256': still.generated_sha256,
                    'terminal_status': status if status != 'pending' else None},
    )
    return primary, call, reserve, storage, sources, job


def test_definite_video_job_failure_keeps_submission_and_uses_b(publication_case, tmp_path):
    from monitor.editorial.graphics_publication import publish_fallback

    pack, _, _ = publication_case
    primary, call, reserve, storage, sources, job = _video_job_case(publication_case, tmp_path)
    kwargs = {'primary_text': primary, 'failure_call': call, 'video_job': job,
              'reserve_picture': reserve, 'pack': pack, 'sources': sources,
              'selected_scope': 'featured:social-brief:en', 'storage': storage}
    result = publish_fallback(**kwargs)
    assert result.headline == 'Memory Lane'
    call.refresh_from_db()
    assert call.state == 'completed'
    assert publish_fallback(**kwargs).pk == result.pk


@pytest.mark.parametrize('status', ['pending', 'unknown'])
def test_pending_or_unknown_video_never_activates_b(publication_case, tmp_path, status):
    from monitor.editorial.graphics_publication import publish_fallback

    pack, _, _ = publication_case
    primary, call, reserve, storage, sources, job = _video_job_case(publication_case, tmp_path, status=status)
    with pytest.raises(ValueError, match='definite same-run'):
        publish_fallback(primary_text=primary, failure_call=call, video_job=job,
                         reserve_picture=reserve, pack=pack, sources=sources,
                         selected_scope='featured:social-brief:en', storage=storage)


def test_video_job_with_mismatched_provider_id_cannot_activate_b(publication_case, tmp_path):
    from monitor.editorial.graphics_publication import publish_fallback

    pack, _, _ = publication_case
    primary, call, reserve, storage, sources, job = _video_job_case(publication_case, tmp_path)
    job.provider_task_id = 'another-job'
    job.save(update_fields=['provider_task_id'])
    with pytest.raises(ValueError, match='definite same-run'):
        publish_fallback(primary_text=primary, failure_call=call, video_job=job,
                         reserve_picture=reserve, pack=pack, sources=sources,
                         selected_scope='featured:social-brief:en', storage=storage)
