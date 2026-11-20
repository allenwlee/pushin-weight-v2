import json
from io import StringIO

import pytest
from django.core.management import call_command

from core.models import Post, PostEnrichmentState

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_health_does_not_count_unrequested_translation_as_pending():
    post = Post.objects.create(tweet_id='health-no-translation', text='source')
    PostEnrichmentState.objects.create(
        post=post, translation_requested=False, translation_status='pending',
        classification_status='succeeded',
    )
    out = StringIO()
    call_command('enrichment_health', stdout=out)
    result = json.loads(out.getvalue())
    assert result['pending_posts'] == 0
    assert result['completed_last_hour'] == 1


def test_health_counts_explicitly_requested_pending_translation():
    post = Post.objects.create(tweet_id='health-requested-translation', text='source')
    PostEnrichmentState.objects.create(
        post=post, translation_requested=True, translation_status='pending',
        classification_status='succeeded',
    )
    out = StringIO()
    call_command('enrichment_health', stdout=out)
    result = json.loads(out.getvalue())
    assert result['pending_posts'] == 1
    assert result['completed_last_hour'] == 0
