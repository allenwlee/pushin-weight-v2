"""Initial and narrow responses render the same saved, localized publication."""
from datetime import timedelta
from types import SimpleNamespace

import pytest

from monitor import views
from monitor.trend_narrative_lifecycle import activate_trend_narrative_run
from tests.test_trend_narrative_projection import (
    NOW,
    _brand,
    _config,
    _per_brand_outcome,
    _per_brand_run,
)


@pytest.mark.django_db
@pytest.mark.requires_postgres
@pytest.mark.parametrize('locale,headline,secondary', [
    ('zh_cn', '中文发布标题', '中文详细说明'),
    ('ja', '日本語の発表', '保存された日本語の詳細'),
])
def test_saved_thirty_day_headline_matches_initial_page_and_narrow_fragment(
    client, settings, monkeypatch, locale, headline, secondary,
):
    settings.SECURE_SSL_REDIRECT = False
    brand = _brand('deepseek', 'DeepSeek')
    run = _per_brand_run([brand], cycle='each-localized-fragment')
    run.window_days = 30
    run.save(update_fields=['window_days'])
    _per_brand_outcome(run, brand, headline_en='English source title',
                      headline_zh_cn='中文发布标题', secondary_zh_cn='中文详细说明',
                      headline_ja='日本語の発表', secondary_ja='保存された日本語の詳細')
    assert activate_trend_narrative_run(run.pk, now=NOW+timedelta(seconds=1))
    # Serving is enabled only for this fixture. Saved projection, URL handling,
    # normal DB sessions and both render paths remain real; providers stay off.
    config = _config().model_copy(update={'demand_shaping_enabled': False})
    monkeypatch.setattr('monitor.each_headline.load_config',
                        lambda _path: SimpleNamespace(headline_narrative=config))
    monkeypatch.setattr(views, '_dashboard_now', lambda: NOW+timedelta(minutes=5))
    params = {'brand': brand.pk, 'window': '30', 'locale': locale}
    initial = client.get('/dashboard/each', params)
    fragment = client.get('/api/v2/dashboard/each/headline/', params)
    assert initial.status_code == fragment.status_code == 200
    data = fragment.json()
    assert data['brand'] == brand.pk and data['window_days'] == 30 and data['locale'] == locale
    assert data['html'].strip() in initial.content.decode()
    assert headline in data['html'] and secondary in data['html']
    assert 'English source title' not in data['html']
