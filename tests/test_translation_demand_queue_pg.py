from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import PostEnrichmentState
from monitor.enrichment_queue import (
    claim_enrichment_states,
    release_enrichment_claim,
    request_post_translation,
)
from tests.test_post_enrichment_queue import _cfg, _state

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_unrequested_translation_is_never_claimed_after_classification():
    state = _state('translation-not-requested')
    PostEnrichmentState.objects.filter(pk=state.pk).update(classification_status='succeeded')
    batch = claim_enrichment_states(cfg=_cfg().harvest.enrichment, run_id='read')
    assert not batch.states
    state.refresh_from_db()
    assert state.translation_status == 'pending'
    assert not state.translation_requested


def test_request_is_coalesced_and_waits_for_active_classification():
    state = _state('translation-request-during-classification')
    cfg = _cfg().harvest.enrichment
    first = claim_enrichment_states(cfg=cfg, run_id='classify')
    assert first.states
    request_post_translation(str(state.pk))
    request_post_translation(str(state.pk))
    assert not claim_enrichment_states(cfg=cfg, run_id='second').states
    PostEnrichmentState.objects.filter(pk=state.pk).update(classification_status='succeeded')
    release_enrichment_claim(state.pk, run_id='classify')
    batch = claim_enrichment_states(cfg=cfg, run_id='translate')
    assert [str(item.pk) for item in batch.states] == [str(state.pk)]
    state.refresh_from_db()
    assert state.translation_requested
    assert state.translation_attempts == 0


def test_legacy_unrequested_exhausted_translation_does_not_quarantine():
    state = _state('translation-old-pending')
    PostEnrichmentState.objects.filter(pk=state.pk).update(
        classification_status='succeeded', translation_attempts=8,
        created_at=timezone.now() - timedelta(days=1),
    )
    cfg = _cfg().harvest.enrichment
    assert not claim_enrichment_states(cfg=cfg, run_id='idle').states
    request_post_translation(str(state.pk))
    state.refresh_from_db()
    assert state.translation_requested and state.translation_attempts == 0
    assert claim_enrichment_states(cfg=cfg, run_id='requested').states


def test_classification_runs_before_requested_translation_of_another_post(monkeypatch):
    from monitor.cycle import CycleRunner
    from tests.test_post_enrichment_queue import (
        _classification_results,
        _complete_translation,
    )
    from x_monitor import attribution, reattribute, translator

    translation = _state('mixed-translation')
    _state('mixed-classification')
    PostEnrichmentState.objects.filter(pk=translation.pk).update(
        translation_requested=True, classification_status='succeeded',
    )
    order = []
    client = object()
    monkeypatch.setattr(reattribute, 'build_translator_client_from_env', lambda cfg: client)
    monkeypatch.setattr(reattribute, 'build_classifier_client_from_env', lambda cfg: client)
    def fake_translate(tweets, locales, client, **kwargs):
        order.append('translation')
        return [_complete_translation(t['tweet_id'], t['text']) for t in tweets]
    def fake_classify(tweets, brands, client, **kwargs):
        order.append('classification')
        return _classification_results(tweets)
    monkeypatch.setattr(translator, 'translate_batch_pragmatics', fake_translate)
    monkeypatch.setattr(attribution, 'classify_batch_pragmatics_full', fake_classify)
    CycleRunner(cfg=_cfg())._process_enrichment_claim_batch([], run_id='mixed-priority')
    assert order == ['classification', 'translation']
