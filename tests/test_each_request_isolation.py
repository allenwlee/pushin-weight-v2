"""Real HTTP/SQL callers for bounded Each work and provider-free headlines."""
from time import monotonic
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.db import connection, transaction
from django.template.loader import render_to_string
from django.utils import timezone

from core.models import Brand
from monitor.each_request_budget import EachChartUnavailable, EachRequestBudget

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


@pytest.fixture(autouse=True)
def local_http(settings):
    settings.SECURE_SSL_REDIRECT = False


def narrative():
    return {
        'window_days': 30, 'computed_at': timezone.now().isoformat(),
        'schema_version': 3, 'state_label': 'Saved',
        'body': '<script>unsafe</script>', 'selection': {}, 'items': [],
    }


def test_narrow_headline_uses_shared_partial_and_never_builds_full_dashboard(client):
    Brand.objects.create(nickname='llama', display_name='Meta')
    saved = narrative()
    def forbidden(*args, **kwargs):
        raise AssertionError('narrow headline called a full dashboard reader')
    with patch('monitor.each_headline.load_config', return_value=SimpleNamespace(
        headline_narrative=SimpleNamespace(demand_shaping_enabled=False))), patch(
        'monitor.each_headline.project_trend_narrative', return_value=saved), patch(
        'monitor.views._feed_page_wire', side_effect=forbidden), patch(
        'monitor.views._build_home_pulse_payload', side_effect=forbidden), patch(
        'monitor.views._each_chart_payload', side_effect=forbidden):
        response = client.get('/api/v2/dashboard/each/headline/', {
            'brand': 'llama', 'window': '30', 'locale': 'en',
        })
    assert response.status_code == 200
    data = response.json()
    assert data['brand'] == 'llama' and data['window_days'] == 30 and data['locale'] == 'en'
    assert response['Cache-Control'] == 'no-store'
    expected = render_to_string('monitor/_each_headline.html', {
        'trend_narrative': saved, 'top_voices': [], 'active_locale': 'en',
        'is_zh_chrome': False, 'is_ja_chrome': False,
    })
    assert data['html'] == expected
    assert '&lt;script&gt;unsafe&lt;/script&gt;' in data['html']
    assert '<script>unsafe</script>' not in data['html']


@pytest.mark.parametrize('params', [
    {'brand': 'missing', 'window': '30'},
    {'brand': 'llama', 'window': '17'},
])
def test_narrow_headline_rejects_unknown_selection(client, params):
    Brand.objects.get_or_create(nickname='llama', defaults={'display_name': 'Meta'})
    assert client.get('/api/v2/dashboard/each/headline/', params).status_code == 400


def test_http_chart_timeout_is_controlled_and_worker_can_serve_next_request(client):
    Brand.objects.create(nickname='llama', display_name='Meta')
    with patch('monitor.views._each_tab_entries', return_value={'sentiment': []}), patch(
        'monitor.views._each_chart_payload', side_effect=EachChartUnavailable):
        response = client.get('/dashboard/each/chart/', {'brand': 'llama'})
    assert response.status_code == 503
    assert response.json() == {'error': 'chart_timeout'}
    assert response['Retry-After'] == '60'
    assert client.get('/api/v2/dashboard/each/headline/', {'brand': 'missing'}).status_code == 400


def test_sequential_sql_consumes_one_deadline_and_restores_caller_settings():
    with connection.cursor() as cursor:
        cursor.execute('SHOW statement_timeout'); original = cursor.fetchone()[0]
        cursor.execute('SHOW lock_timeout'); original_lock = cursor.fetchone()[0]
    started = monotonic()
    with (pytest.raises(EachChartUnavailable), EachRequestBudget(seconds=.1) as budget,
          budget.query_scope(), transaction.atomic(), connection.cursor() as cursor):
        cursor.execute('SELECT pg_sleep(.06)')
        cursor.execute('SELECT pg_sleep(.06)')
    assert monotonic() - started < .5
    with connection.cursor() as cursor:
        cursor.execute('SHOW statement_timeout'); assert cursor.fetchone()[0] == original
        cursor.execute('SHOW lock_timeout'); assert cursor.fetchone()[0] == original_lock


def test_latency_fix_preserves_current_production_brand_presentation():
    from monitor.views import _HOME_CHART_BRAND_PRIORITY, _live_brand_projection
    for key in ('llama', 'nemo_megatron', 'deepseek', 'qwen'):
        Brand.objects.create(nickname=key, display_name=key)
    rows = _live_brand_projection('en', tracked_only=True)
    keys = [row['nickname'] for row in rows]
    assert keys[:4] == ['llama', 'deepseek', 'qwen', 'nemo_megatron']
    assert _HOME_CHART_BRAND_PRIORITY.count('nemo_megatron') == 1


def test_request_guard_never_extends_shorter_caller_statement_limit():
    with pytest.raises(EachChartUnavailable), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET LOCAL statement_timeout='20ms'")
        with EachRequestBudget(seconds=1) as budget, budget.query_scope():
            cursor.execute('SELECT pg_sleep(.05)')


def test_nested_query_scopes_install_only_one_configuration_guard():
    from django.test.utils import CaptureQueriesContext

    with (EachRequestBudget() as outer, outer.query_scope(),
          EachRequestBudget(seconds=3) as inner, inner.query_scope(),
          CaptureQueriesContext(connection) as queries, connection.cursor() as cursor):
        cursor.execute('SELECT 1')
    configurations = [q for q in queries.captured_queries if "set_config('statement_timeout'" in q['sql']]
    assert len(configurations) == 1


def test_visible_demand_lock_is_skipped_without_changing_saved_demand():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from django.db import connections

    from core.models import TrendNarrativeDemand
    from monitor.trend_narrative_demand import (
        record_trend_narrative_demand,
        record_visible_trend_narrative_demand,
    )
    from x_monitor.config import HeadlineNarrativeConfig

    Brand.objects.create(nickname='each-demand-lock', display_name='Lock')
    config = HeadlineNarrativeConfig(demand_shaping_enabled=True)
    record_trend_narrative_demand(
        brand_keys=['each-demand-lock'], window_days=30, reason='visible', config=config,
    )
    before = TrendNarrativeDemand.objects.values().get(brand_id='each-demand-lock')
    entered, release = Event(), Event()
    def hold():
        try:
            with transaction.atomic():
                TrendNarrativeDemand.objects.select_for_update().get(brand_id='each-demand-lock')
                entered.set()
                assert release.wait(3)
        finally:
            connections['default'].close()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(hold)
        try:
            assert entered.wait(3)
            started = monotonic()
            assert record_visible_trend_narrative_demand(
                brand_keys=['each-demand-lock'], window_days=30, config=config,
            ) == 0
            assert monotonic() - started < .6
        finally:
            release.set()
        future.result(timeout=3)
    assert TrendNarrativeDemand.objects.values().get(brand_id='each-demand-lock') == before


def test_narrow_headline_keeps_staging_owner_wall(client, settings):
    settings.OLLIJA_STAGING_MODE = True
    settings.OLLIJA_STAGING_ALLOWED_EMAILS = {'owner@example.test'}
    response = client.get('/api/v2/dashboard/each/headline/', {'brand': 'llama'})
    assert response.status_code == 302
    assert '/accounts/login/' in response['Location']


def test_real_sql_error_can_roll_back_savepoint_before_live_retry():
    from django.db import ProgrammingError

    with transaction.atomic(), EachRequestBudget() as budget, budget.query_scope():
        with pytest.raises(ProgrammingError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute('SELECT * FROM each_missing_relation_for_fallback_test')
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            assert cursor.fetchone() == (1,)


@pytest.mark.parametrize(('cookie', 'query', 'message'), [
    ('ja', {}, '読み込みがタイムアウトしました。'),
    ('', {}, '页面加载超时'),
    ('', {'locale': 'zh-Hans'}, '页面加载超时'),
])
def test_page_timeout_uses_the_page_locale_policy(client, cookie, query, message):
    from django.utils import translation

    if cookie:
        client.cookies['locale'] = cookie
    with translation.override('en'), patch(
        'monitor.each_request_budget.EachRequestBudget.query_scope',
        side_effect=EachChartUnavailable,
    ):
        response = client.get('/dashboard/each', query)
    assert response.status_code == 503
    assert message in response.content.decode()


def test_headline_rejects_non_get_before_budget_or_projection(client):
    with patch('monitor.each_request_budget.EachRequestBudget.query_scope') as scope, patch(
        'monitor.each_headline.headline_context', side_effect=AssertionError('unsupported method read headline'),
    ):
        response = client.options('/api/v2/dashboard/each/headline/', {'brand': 'llama'})
    assert response.status_code == 405
    assert response['Allow'] == 'GET'
    scope.assert_not_called()


def test_narrow_http_headline_serves_saved_html_while_demand_row_is_locked(client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from django.db import connections

    from core.models import TrendNarrativeDemand
    from monitor.trend_narrative_demand import record_trend_narrative_demand
    from x_monitor.config import HeadlineNarrativeConfig

    Brand.objects.create(nickname='llama', display_name='Meta')
    config = HeadlineNarrativeConfig(demand_shaping_enabled=True)
    record_trend_narrative_demand(brand_keys=['llama'], window_days=30, reason='visible', config=config)
    before = TrendNarrativeDemand.objects.values().get(brand_id='llama')
    entered, release = Event(), Event()

    def hold():
        try:
            with transaction.atomic():
                TrendNarrativeDemand.objects.select_for_update().get(brand_id='llama')
                entered.set()
                assert release.wait(4)
        finally:
            connections['default'].close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(hold)
        try:
            assert entered.wait(3)
            started = monotonic()
            with patch('monitor.each_headline.load_config', return_value=SimpleNamespace(
                headline_narrative=config)), patch(
                'monitor.each_headline.project_trend_narrative', return_value=narrative(),
            ):
                response = client.get('/api/v2/dashboard/each/headline/', {
                    'brand': 'llama', 'window': '30', 'locale': 'en',
                })
            assert response.status_code == 200
            assert '&lt;script&gt;unsafe&lt;/script&gt;' in response.json()['html']
            assert monotonic() - started < .8
        finally:
            release.set()
        future.result(timeout=3)
    assert TrendNarrativeDemand.objects.values().get(brand_id='llama') == before


def test_narrow_http_slow_projection_returns_controlled_timeout(client):
    Brand.objects.create(nickname='llama', display_name='Meta')

    def slow_projection(*args, **kwargs):
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_sleep(4)')
        return narrative()

    started = monotonic()
    with patch('monitor.each_headline.load_config', return_value=SimpleNamespace(
        headline_narrative=SimpleNamespace(demand_shaping_enabled=False))), patch(
        'monitor.each_headline.project_trend_narrative', side_effect=slow_projection,
    ):
        response = client.get('/api/v2/dashboard/each/headline/', {'brand': 'llama', 'locale': 'en'})
    assert response.status_code == 503
    assert response.json() == {'error': 'headline_timeout'}
    assert response['Cache-Control'] == 'no-store'
    assert monotonic() - started < 3.6
