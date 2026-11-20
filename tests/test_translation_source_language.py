from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import Post
from monitor.views import (
    _filter_home_posts_queryset,
    _normalize_home_filters,
    _post_language,
)

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_untranslated_known_source_language_is_filterable_without_guessing_chinese_script():
    now = timezone.now()
    english = Post.objects.create(tweet_id='source-lang-en', text='Hello', lang=' En ', created_at=now)
    chinese = Post.objects.create(tweet_id='source-lang-zh', text='你好', lang='zh', created_at=now)
    japanese = Post.objects.create(tweet_id='source-lang-ja', text='こんにちは', lang='ja', created_at=now)
    assert _post_language(None, english.lang) == 'en'
    assert _post_language(None, chinese.lang) is None
    assert _post_language('zh-Hant', 'zh') == 'zh-Hant'
    def selected(value):
        filters = _normalize_home_filters({'lang': [value]})
        return set(_filter_home_posts_queryset(1, filters, now=now + timedelta(seconds=1)).values_list('pk', flat=True))
    assert english.pk in selected('en')
    assert japanese.pk in selected('ja')
    assert chinese.pk in selected('undetected')
    assert chinese.pk not in selected('zh-hans')
