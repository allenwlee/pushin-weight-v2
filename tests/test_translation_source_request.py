import json

import pytest
from django.test import Client
from django.utils import timezone
from django.utils.crypto import salted_hmac

from core.models import Post, PostEnrichmentState, PostSynthesisRateLimitBucket, PostTranslationArtifact, PostTranslationText
from monitor.post_artifacts import source_content_fingerprint

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def request(post, locale):
    return Client().post('/api/v2/post-translation-demands/',
                         data=json.dumps({'post_ids': [post.pk], 'locale': locale}),
                         content_type='application/json', secure=True).json()['results'][0]


@pytest.mark.parametrize(('language', 'locale'), [('en', 'en'), ('ja', 'ja'), ('zh-Hans', 'zh-cn')])
@pytest.mark.parametrize('artifact_kind', ['none', 'stale', 'incomplete'])
def test_matching_source_never_creates_paid_demand(language, locale, artifact_kind):
    post = Post.objects.create(tweet_id='source-' + language + artifact_kind, text='Original source', lang_detected=language)
    if artifact_kind != 'none':
        artifact = PostTranslationArtifact.objects.create(
            post=post, source_content_fingerprint=('stale' if artifact_kind == 'stale' else source_content_fingerprint(post)),
            source_language=language, prompt_version='test', model='test', provider_role='literal_translation',
            state=PostTranslationArtifact.State.SUCCEEDED, is_current=True,
            started_at=timezone.now(), completed_at=timezone.now(),
        )
        PostTranslationText.objects.create(artifact=artifact, locale='en', text='Old artifact')
    result = request(post, locale)
    assert result['status'] == 'ready'
    assert result['literal'][locale] == post.text
    assert not PostEnrichmentState.objects.filter(post=post).exists()
    capacity_hash = salted_hmac('post-translation-capacity', 'all', algorithm='sha256').hexdigest()
    assert not PostSynthesisRateLimitBucket.objects.filter(scope_hash=capacity_hash, count__gt=0).exists()


def test_generic_chinese_does_not_claim_simplified_source():
    post = Post.objects.create(tweet_id='generic-chinese-source', text='原文', lang_detected='zh')
    result = request(post, 'zh-cn')
    assert result['status'] == 'pending'
    assert PostEnrichmentState.objects.get(post=post).translation_requested


@pytest.mark.parametrize(('language', 'locale'), [('en', 'en'), ('ja', 'ja')])
def test_untranslated_post_uses_trusted_provider_language(language, locale):
    post = Post.objects.create(tweet_id='provider-source-' + language, text='Original source', lang=language)
    result = request(post, locale)
    assert result['status'] == 'ready'
    assert result['literal'][locale] == post.text
    assert not PostEnrichmentState.objects.filter(post=post).exists()


def test_incomplete_current_artifact_serves_present_locale_without_demand():
    post = Post.objects.create(tweet_id='partial-valid', text='Bonjour', lang_detected='fr')
    artifact = PostTranslationArtifact.objects.create(
        post=post, source_content_fingerprint=source_content_fingerprint(post),
        source_language='fr', prompt_version='test', model='test', provider_role='literal_translation',
        state=PostTranslationArtifact.State.SUCCEEDED, is_current=True,
        started_at=timezone.now(), completed_at=timezone.now(),
    )
    PostTranslationText.objects.create(artifact=artifact, locale='en', text='Hello')
    result = request(post, 'en')
    assert result['status'] == 'ready'
    assert result['literal']['en'] == 'Hello'
    assert not PostEnrichmentState.objects.filter(post=post).exists()
