import pytest
from django.utils import timezone

from core.models import OriginalContentCall, OriginalContentText
from monitor.editorial.graphics_status import graphics_status
from monitor.original_content import digest
from tests.test_graphics_pipeline import selected_run

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def test_status_only_returns_scorecard_for_the_exact_saved_revision():
    run, content = selected_run()
    assert graphics_status(run.pk)['review_state'] == 'pending'
    text = OriginalContentText.objects.create(narrative=content, locale='en', headline='Saved',
                                               secondary='Byline', body='Article')
    publication = {'locale': text.locale, 'headline': text.headline, 'byline': text.byline, 'article': text.body}
    scorecard = {'text_id': text.pk, 'content_revision': digest({'text_id': text.pk, 'publication': publication})}
    call = OriginalContentCall.objects.create(run=run, stage=f'gfx:{run.pk}:E1', workflow_key=content.workflow_key,
        kind='text', request_identity=f'graphics:{run.pk}:E1', request_hash='a'*64,
        response_hash=digest(scorecard), response_payload=scorecard, state='completed',
        reserved_at=timezone.now(), sent_at=timezone.now(), completed_at=timezone.now())
    assert graphics_status(run.pk)['scorecard'] == scorecard
    text.headline = 'Changed'
    text.save(update_fields=['headline'])
    assert graphics_status(run.pk)['review_state'] == 'different_revision'
    call.response_payload = {}
    call.save(update_fields=['response_payload'])
    assert graphics_status(run.pk)['review_state'] == 'invalid_saved_response'
