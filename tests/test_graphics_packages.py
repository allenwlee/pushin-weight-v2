"""A selected story receives an isolated, recoverable Graphics run."""
from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone

from core.models import OriginalContent, OriginalContentRun, Post
from monitor.editorial.graphics_entry import prepare_selected_story

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


@pytest.fixture
def selected():
    now = timezone.now()
    post = Post.objects.create(tweet_id='12345', text='current text')
    source = {'id': post.pk, 'url': 'https://x.com/i/status/12345',
              'original_text': 'snapshot text', 'created_at': (now - timedelta(minutes=2)).isoformat()}
    run = OriginalContentRun.objects.create(
        source_cycle_id=str(uuid4()), workflow_key='editorial-dispatch', scope_key=str(uuid4()),
        facts_as_of=now, packet_schema_version=1, snapshot={'posts': [source], 'context': []},
        execution_state='complete',
    )
    content = OriginalContent.objects.create(
        run=run, workflow_key='social-brief', output_key=str(uuid4()), subject_key='selected',
        story_id=uuid4(), status='prepared', attempted_at=now, brand_key_snapshot='',
        selection={'post_ids': [post.pk], 'person_ids': []},
    )
    return content, run


def _request(selected, locale='en', **limits):
    content, run = selected
    return prepare_selected_story(content_id=content.pk, run_id=run.pk, locale=locale, **limits)


def test_materialization_is_idempotent_and_never_modifies_source(selected):
    from monitor.editorial.graphics_packages import materialize_package

    content, source_run = selected
    request = _request(selected)
    before = deepcopy(source_run.snapshot)
    run, output = materialize_package(request)
    again, same_output = materialize_package(request)
    assert (run.pk, output.pk) == (again.pk, same_output.pk)
    assert run.pk != source_run.pk and output.pk != content.pk
    assert run.snapshot['request'] == request
    assert output.run_id == run.pk and output.story_id == content.story_id
    assert output.workflow_key == content.workflow_key
    source_run.refresh_from_db()
    content.refresh_from_db()
    assert source_run.execution_state == 'complete' and source_run.snapshot == before
    assert content.status == 'prepared'


def test_locale_has_independent_run_and_forged_request_fails(selected):
    from monitor.editorial.graphics_packages import materialize_package

    first, _ = materialize_package(_request(selected))
    second, _ = materialize_package(_request(selected, locale='ja'))
    assert first.pk != second.pk
    forged = _request(selected)
    forged['handoff']['fact_items'][0]['supporting_passage'] = 'invented'
    with pytest.raises(ValueError, match='selected story'):
        materialize_package(forged)


def test_claims_expire_and_fence_stale_workers(selected):
    from monitor.editorial.graphics_packages import (
        claim_package,
        materialize_package,
        release_package,
    )

    run, _ = materialize_package(_request(selected))
    now = timezone.now()
    first = claim_package(run.pk, owner='worker-a', now=now, lease_seconds=30)
    assert first is not None
    assert claim_package(run.pk, owner='worker-b', now=now + timedelta(seconds=1), lease_seconds=30) is None
    second = claim_package(run.pk, owner='worker-b', now=now + timedelta(seconds=31), lease_seconds=30)
    assert second is not None and second.fence > first.fence
    assert not release_package(run.pk, owner='worker-a', fence=first.fence, now=now + timedelta(seconds=32))
    assert release_package(run.pk, owner='worker-b', fence=second.fence, now=now + timedelta(seconds=32))


def test_unconfigured_or_failed_dispatch_never_claims_publication(selected):
    from monitor.editorial.graphics_packages import advance_package

    request = _request(selected)
    with pytest.raises(RuntimeError, match='dispatch'):
        advance_package(request)
    result = advance_package(request, dispatch=lambda **kwargs: False)
    assert result['state'] == 'pending_dispatch'
    assert not result['dispatched']
    assert 'published' not in result


def test_two_stories_in_same_source_run_never_share_calls(selected):
    from monitor.editorial.graphics_packages import materialize_package

    content, source_run = selected
    first, first_output = materialize_package(_request(selected))
    other = OriginalContent.objects.create(
        run=source_run, workflow_key='social-brief', output_key=str(uuid4()),
        subject_key='other-story', story_id=uuid4(), status='prepared',
        attempted_at=content.attempted_at, brand_key_snapshot='', selection=deepcopy(content.selection),
    )
    other_request = prepare_selected_story(content_id=other.pk, run_id=source_run.pk, locale='en')
    second, second_output = materialize_package(other_request)
    assert first.pk != second.pk
    assert first_output.story_id != second_output.story_id


def test_expired_claim_cannot_release_before_reclaim(selected):
    from monitor.editorial.graphics_packages import (
        claim_package,
        materialize_package,
        release_package,
    )

    run, _ = materialize_package(_request(selected))
    now = timezone.now()
    claim = claim_package(run.pk, owner='old', now=now, lease_seconds=1)
    assert not release_package(run.pk, owner='old', fence=claim.fence, now=now + timedelta(seconds=2))
    assert claim_package(run.pk, owner='new', now=now + timedelta(seconds=2), lease_seconds=2).fence > claim.fence


def test_dispatch_exception_preserves_pending_run(selected):
    from monitor.editorial.graphics_packages import advance_package

    def failed_dispatch(**kwargs):
        raise OSError('broker unavailable')

    result = advance_package(_request(selected), dispatch=failed_dispatch)
    assert result['state'] == 'pending_dispatch'
    assert OriginalContentRun.objects.get(pk=result['run_id']).execution_state == 'pending'
