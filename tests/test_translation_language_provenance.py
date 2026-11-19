"""Language metadata retains its source in feed JSON and legacy pages."""
import json
import re

import pytest
from django.utils import timezone
from django.test import override_settings

from core.models import Brand, Post, PostBrand

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_provider_language_is_not_reported_as_detected_or_translated(client, django_user_model):
    user = django_user_model.objects.create_user(username="language-provenance")
    client.force_login(user)
    brand = Brand.objects.create(nickname="provenance-test", display_name="Provenance Test")
    post = Post.objects.create(tweet_id="language-provenance", text="Original English text", lang="en", created_at=timezone.now())
    PostBrand.objects.create(post=post, brand=brand)
    response = client.get('/feed/', {'window': 1, 'filters': json.dumps({'lang': ['en'], 'window': 1})}, secure=True)
    row = next(row for row in response.json()['rows'] if row['tweet_id'] == post.pk)
    assert row['lang_detected'] is None
    assert row['effective_language'] == 'en'
    assert row['language_display'] == 'en'
    for route in ('/internal/', '/brands/provenance-test/'):
        response = client.get(route, secure=True)
        assert response.status_code == 200
        match = re.search(r'<tr[^>]*data-tweet-id="language-provenance".*?</tr>', response.content.decode(), re.S)
        assert match, route
        assert 'translated from:' not in match.group()
        assert 'Original English text' in match.group()


def test_detected_language_without_translation_has_no_translated_from_label(client, django_user_model):
    user = django_user_model.objects.create_user(username="detected-without-translation")
    client.force_login(user)
    post = Post.objects.create(tweet_id='detected-untranslated', text='Bonjour', lang_detected='fr', created_at=timezone.now())
    response = client.get('/internal/', secure=True)
    match = re.search(r'<tr[^>]*data-tweet-id="detected-untranslated".*?</tr>', response.content.decode(), re.S)
    assert match
    assert 'translated from:' not in match.group()


def test_actual_translation_with_detected_language_still_shows_label(client, django_user_model):
    user = django_user_model.objects.create_user(username='translated-with-detection')
    client.force_login(user)
    Post.objects.create(tweet_id='translated-detected', text='Bonjour', text_en='Hello', lang_detected='fr', created_at=timezone.now())
    response = client.get('/internal/?locale=en', secure=True)
    match = re.search(r'<tr[^>]*data-tweet-id="translated-detected".*?</tr>', response.content.decode(), re.S)
    assert match
    assert 'translated from:' in match.group()
    assert 'Hello' in match.group()


@override_settings(SECURE_SSL_REDIRECT=False)
def test_legacy_browser_does_not_label_source_as_translation(client, django_user_model, request):
    from playwright.sync_api import sync_playwright

    live_server = request.getfixturevalue('live_server')
    user = django_user_model.objects.create_user(username='provenance-browser')
    client.force_login(user)
    brand = Brand.objects.create(nickname='provenance-browser', display_name='Provenance Browser')
    post = Post.objects.create(tweet_id='provenance-browser', text='Original English', lang='en', created_at=timezone.now())
    PostBrand.objects.create(post=post, brand=brand)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            context = browser.new_context(viewport={'width': 1280, 'height': 800})
            context.add_cookies([{'name': 'sessionid', 'value': client.cookies['sessionid'].value, 'url': live_server.url}])
            page = context.new_page()
            for route in ('/internal/?locale=en', '/brands/provenance-browser/?locale=en'):
                page.goto(live_server.url + route, wait_until='networkidle')
                row = page.locator('tr[data-tweet-id="provenance-browser"]')
                assert row.count() == 1
                assert row.is_visible()
                assert 'Original English' in row.inner_text()
                assert row.locator('.lang-sub').count() == 0
            context.close()
        finally:
            browser.close()
