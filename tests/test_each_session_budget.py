"""Regression candidates for the normal public session lifecycle."""
from threading import Event, Thread
from time import monotonic

import psycopg
import pytest
from django.conf import settings
from django.contrib.sessions.backends.db import SessionStore
from django.db import connection
from django.test import Client, RequestFactory, override_settings

from monitor import views
from monitor.each_request_budget import EachChartUnavailable


@pytest.mark.django_db(transaction=True)
@pytest.mark.requires_postgres
@override_settings(SECURE_SSL_REDIRECT=False)
def test_normal_chart_session_save_obeys_public_lock_allowance(monkeypatch):
    from django.utils import timezone

    from core.models import Brand, Post, PostBrand

    assert connection.settings_dict['NAME'].startswith('test_')
    brand = Brand.objects.create(nickname='each-session-budget', display_name='Fixture')
    post = Post.objects.create(tweet_id='each-session-budget', created_at=timezone.now())
    PostBrand.objects.create(post=post, brand=brand)
    monkeypatch.setattr(views, '_tracked_home_brand_nicknames', lambda: (brand.pk,))
    client = Client()
    session = client.session
    session['proof'] = 'normal-db-session'
    session.save()
    client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key
    config = connection.settings_dict
    blocker = psycopg.connect(dbname=config['NAME'], host=config['HOST'], port=config['PORT'],
                              user=config['USER'], password=config['PASSWORD'])
    blocker.execute('SELECT session_key FROM django_session WHERE session_key=%s FOR UPDATE', [session.session_key])
    release = Event()
    worker = Thread(target=lambda: (release.wait(1), blocker.rollback()))
    worker.start()
    try:
        started = monotonic()
        response = client.get('/dashboard/each/chart/', {'brand': brand.pk, 'tab': 'sentiment',
                              'window': '7', 'locale': 'en'})
        elapsed = monotonic()-started
    finally:
        release.set()
        worker.join(timeout=3)
        blocker.close()
    assert response.status_code == 503, response.content[:300]
    assert response.json() == {'error': 'chart_timeout'}
    assert response['Retry-After'] == '60'
    assert elapsed < .85
    # A later ordinary request still persists the selected language normally.
    response = client.get('/dashboard/each/chart/', {'brand': brand.pk, 'locale': 'ja'})
    assert response.status_code == 200
    assert SessionStore(session_key=client.cookies[settings.SESSION_COOKIE_NAME].value)['_language'] == 'ja'


@pytest.mark.django_db
@pytest.mark.requires_postgres
@pytest.mark.parametrize('locale,copy', [('en', 'This page took too long'),
                                      ('zh_cn', '页面加载超时'), ('ja', '読み込みがタイムアウト')])
def test_page_timeout_never_retries_failed_session_access(locale, copy):
    request = RequestFactory().get('/dashboard/each', {'locale': locale})
    attempts = []

    class FailedSession:
        def __setitem__(self, key, value):
            attempts.append((key, value))
            raise EachChartUnavailable('Session database is unavailable')

    request.session = FailedSession()
    response = views.dashboard_each(request)
    assert response.status_code == 503
    assert copy in response.content.decode()
    assert len(attempts) == 1
