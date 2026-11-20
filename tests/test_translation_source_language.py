from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import Post
from monitor.views import (
    _filter_home_posts_queryset,
    _compact_language_display,
    _normalize_home_filters,
    _post_language,
)

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_untranslated_known_source_language_is_filterable_without_guessing_chinese_script():
    now = timezone.now()
    english = Post.objects.create(tweet_id='source-lang-en', text='Hello', lang=' En ', created_at=now)
    chinese = Post.objects.create(tweet_id='source-lang-zh', text='你好', lang='zh', created_at=now)
    japanese = Post.objects.create(tweet_id='source-lang-ja', text='こんにちは', lang='ja', created_at=now)
    german = Post.objects.create(tweet_id='source-lang-de', text='Ein Beispiel', lang='de', created_at=now)
    assert _post_language(None, english.lang) == 'en'
    assert _post_language(None, chinese.lang) == 'zh'
    assert _compact_language_display(_post_language(None, chinese.lang), 'en') == 'zh'
    assert _post_language('zh-Hant', 'zh') == 'zh-Hant'
    assert _post_language(None, 'zh-Hant') == 'zh-Hant'
    from x_monitor.translator import literal_source_language
    for tag in ("zh-CN", "zh-TW"):
        assert _post_language(None, tag) == "zh"
        assert literal_source_language(tag) is None
    def selected(value):
        filters = _normalize_home_filters({'lang': [value]})
        return set(_filter_home_posts_queryset(1, filters, now=now + timedelta(seconds=1)).values_list('pk', flat=True))
    assert english.pk in selected('en')
    assert japanese.pk in selected('ja')
    assert _post_language(None, german.lang) == 'de'
    assert german.pk in selected('other')
    assert german.pk not in selected('undetected')
    assert chinese.pk in selected('zh')
    assert chinese.pk not in selected('undetected')
    assert chinese.pk not in selected('zh-hans')
    assert _post_language(None, 'und') is None
    chinese.refresh_from_db()
    assert not chinese.lang_detected


def test_failed_demand_preserves_unknown_script_without_publishing_simplified():
    from monitor.post_artifacts import record_literal_translation_failure, source_text_fingerprint

    post = Post.objects.create(tweet_id="zh-detection-failure", text="臺灣使用這個軟體。", lang="zh")
    artifact = record_literal_translation_failure(post=post, expected_source_fingerprint=source_text_fingerprint(post.text),
        prompt_version="test", model="fixture", error_code="language_unresolved")
    assert artifact.source_language == "unknown"
    post.refresh_from_db()
    assert not post.lang_detected and not post.text_zh_cn
