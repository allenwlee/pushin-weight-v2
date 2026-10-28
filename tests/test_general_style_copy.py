"""Server-rendered General-style copy, and the pages the restyle must leave alone."""

from __future__ import annotations

import re

import pytest
from django.contrib.auth import get_user_model

from monitor.views import _clear_home_pulse_cache
from tests.general_helpers import classified_post, saved_commentary
from tests.v22_support import fixture_from_oracle, seed_real_home_orm

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]

COPY = {
    "en": {"lens": ("Others", "Giant"), "lang": "Language", "promotions": "3rd Party Brand Promotions"},
    "zh_cn": {"lens": ("其他", "巨头"), "lang": "语言", "promotions": "第三方品牌推广"},
    "ja": {"lens": ("その他", "大手"), "lang": "言語", "promotions": "サードパーティのブランドプロモーション"},
}
RETIRED = (
    "Untracked Brand Promotion",
    "未跟踪品牌推广",
    "未追跡ブランドのプロモーション",
    '<span class="title" data-i18n="pill_lang">Lang</span>',
    "走个量",
    "首次成功处理的历史平均时间",
    "初回成功処理の過去平均",
)
GENERAL_STYLE_MARKERS = ("pro-general.css", "pw-rail", "pw-wordmark", "pw-general")


@pytest.fixture
def home_data(settings):
    settings.SECURE_SSL_REDIRECT = False
    seed_real_home_orm(fixture_from_oracle())
    _clear_home_pulse_cache()


@pytest.mark.parametrize("locale", sorted(COPY))
@pytest.mark.parametrize("path", ["/", "/dashboard/each?brand=deepseek"])
def test_new_copy_renders_and_retired_copy_is_gone(client, home_data, locale, path):
    separator = "&" if "?" in path else "?"
    response = client.get(f"{path}{separator}locale={locale}")
    assert response.status_code == 200
    html = response.content.decode()
    expected = COPY[locale]
    assert "<title>PUSHINWEIGHT</title>" in html
    for retired in RETIRED:
        assert retired not in html, retired
    if path == "/":
        others, giant = expected["lens"]
        # Labels change; the stored lens values do not.
        assert re.search(rf'data-lens="open"[^>]*><span data-i18n="lens_open">{others}</span>', html)
        assert re.search(rf'data-lens="closed"[^>]*><span data-i18n="lens_closed">{giant}</span>', html)
        assert f'<span class="title" data-i18n="pill_lang">{expected["lang"]}</span>' in html
        # The geopolitical help trigger keeps its explanation but loses the globe icon.
        trigger = re.search(r'<span class="filter-help-trigger[^>]*>(.*?)</span>', html, re.S)
        assert trigger is not None
        assert trigger.group(1) == ""
    else:
        tabs = re.findall(r'data-each-tab="(\w+)"[^>]*>\s*(.*?)\s*</button>', html, re.S)
        labels = dict((tab, re.sub(r"\s+", " ", label)) for tab, label in tabs)
        assert labels["lang"] == expected["lang"]
        assert labels["untracked_brand_promotions"] == expected["promotions"]


def test_legacy_pages_keep_their_own_chrome(client, home_data, settings):
    user = get_user_model().objects.create_user(username="legacy-pages", password="test-only")
    client.force_login(user)
    post = classified_post("legacy-detail-1", "events", brand="deepseek")
    saved_commentary(post)
    for path in ("/internal/", "/brands/deepseek/", f"/posts/{post.pk}/?lang=en"):
        response = client.get(path)
        assert response.status_code == 200, path
        html = response.content.decode()
        for marker in GENERAL_STYLE_MARKERS:
            assert marker not in html, (path, marker)
        # Only the shared mark and favicon change on these pages.
        assert "favicon.svg" in html, path
    detail = client.get(f"/posts/{post.pk}/?lang=en").content.decode()
    assert "data-audience" not in detail
