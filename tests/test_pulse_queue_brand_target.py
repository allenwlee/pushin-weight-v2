"""The scheduled worker waits for an attribution without blocking later work."""
import json
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from core import models
from monitor.enrichment_queue import claim_enrichment_states
from tests.test_classified_product_releases import setup_cycle

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


def test_pulse_queue_skips_unattributed_posts_until_a_brand_is_saved(monkeypatch):
    state, runner, transport = setup_cycle(monkeypatch, sentinel=True)
    tracked_post = models.Post.objects.create(tweet_id='tracked-post', text=state.post.text, lang='en')
    brand = models.Brand.objects.create(nickname='qwen', display_name='Qwen')
    models.PostBrand.objects.create(post=tracked_post, brand=brand)
    models.PostEnrichmentState.objects.create(post=tracked_post, translation_status='succeeded')
    for index in range(6):
        post = models.Post.objects.create(tweet_id=f'await-brand-{index}', text='Plain text.')
        models.PostEnrichmentState.objects.create(post=post, translation_status='succeeded')

    first = runner._run_post_fetch([], run_id='pulse-queue-first')
    assert first['n_enrichment_claimed'] == 2
    assert len(transport.calls) == 4
    assert set(models.PostBrandClassificationState.objects.values_list('post_id', flat=True)) == {
        state.post_id, tracked_post.pk,
    }
    future = timezone.now() + timedelta(seconds=65)
    monkeypatch.setattr(timezone, 'now', lambda: future)
    second = runner._run_post_fetch([], run_id='pulse-queue-second')
    assert second['n_enrichment_claimed'] == 0
    assert len(transport.calls) == 4
    output = StringIO()
    call_command('enrichment_health', stdout=output)
    health = json.loads(output.getvalue())
    assert health['due_posts'] == 0
    assert health['waiting_for_attribution_posts'] == 6
    assert health['future_retry_posts'] == 0
    models.PostBrand.objects.create(post_id='await-brand-0', brand=brand)
    claimed = claim_enrichment_states(cfg=runner.cfg.harvest.enrichment, run_id='later-attribution')
    assert {str(item.pk) for item in claimed.states} == {'await-brand-0'}


def test_scheduled_pulse_wakes_saved_acquisition_recovery(monkeypatch, settings):
    state, runner, _transport = setup_cycle(monkeypatch)
    settings.PRODUCT_RELEASE_BACKGROUND_ENABLED = True
    runner.cycle_kind = 'scheduled'
    monkeypatch.setattr('core.collection_matching.drain_pending_publication_scopes', lambda **kw: {'status': 'idle'})
    monkeypatch.setattr('monitor.pulse_processing.process_saved_findings', lambda **kw: {'status': 'running'})
    dispatched = []
    monkeypatch.setattr('core.product_release_acquisition.dispatch_due_recovery',
                        lambda: dispatched.append(True) or {'status': 'scheduled'})
    result = runner._run_post_fetch([], run_id='pulse-recovery-wakeup')
    assert result['product_release_acquisition_dispatch']['status'] == 'scheduled'
    assert dispatched == [True]
