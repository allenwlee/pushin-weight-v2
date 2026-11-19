"""Read a Graphics run and its revision-bound advisory scorecard."""

from core.models import (
    OriginalContent,
    OriginalContentCall,
    OriginalContentRun,
)
from monitor.original_content import digest

from .graphics_chatter import published_text


def graphics_status(run_id):
    run = OriginalContentRun.objects.get(pk=run_id, workflow_key='graphics-package')
    content = OriginalContent.objects.get(run=run, output_key='graphics-primary/v1')
    text = published_text(run, content)
    call = OriginalContentCall.objects.filter(run=run, request_identity=f'graphics:{run.pk}:E1').first()
    skipped = run.decisions.get('graphics_skipped_stages', {})
    status = {'run_id': run.pk, 'execution_state': run.execution_state,
              'outcome': run.outcome, 'text_id': text.pk if text else None,
              'review_state': call.state if call else ('skipped' if 'E1' in skipped else 'pending')}
    if not call or call.state != 'completed':
        if call and call.error_code:
            status['review_error'] = call.error_code
        elif 'E1' in skipped:
            status['review_error'] = skipped['E1']
        return status
    payload = call.response_payload
    if not isinstance(payload, dict) or call.response_hash != digest(payload):
        status['review_state'] = 'invalid_saved_response'
        return status
    if not text:
        status['review_state'] = 'different_revision'
        return status
    publication = {'locale': text.locale, 'headline': text.headline, 'byline': text.byline, 'article': text.body}
    revision = digest({'text_id': text.pk, 'publication': publication})
    if payload.get('text_id') != text.pk or payload.get('content_revision') != revision:
        status['review_state'] = 'different_revision'
        return status
    status['scorecard'] = payload
    return status
