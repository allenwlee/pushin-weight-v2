"""Actual PostgreSQL content readers for the combined performance seed."""
import os
from datetime import timedelta
from urllib.parse import urlparse

import pytest
from django.db import connection
from django.utils import timezone

from core.models import Post
from monitor.post_artifacts import read_post_content_many
from tests import general_helpers
from tests.each_performance_fixture import seed_each_performance_orm

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


def require_task_test_database():
    # Verify Django selected its test target, never the configured application
    # BASE. An explicit shared TEST.NAME may reuse an existing test_* database.
    source_name = urlparse(os.environ["DATABASE_URL"]).path.removeprefix("/")
    configured_test = connection.settings_dict.get("TEST", {}).get("NAME")
    expected = str(configured_test or "test_" + source_name)
    worker = os.environ.get("PYTEST_XDIST_WORKER", "")
    if worker and worker != "master" and not expected.endswith("_" + worker):
        expected += "_" + worker
    actual = connection.settings_dict["NAME"]
    assert actual == expected
    assert actual != source_name or (configured_test and actual.startswith("test_"))


def test_saved_commentary_default_is_unchanged_and_custom_texts_are_read_verbatim():
    require_task_test_database()
    original = general_helpers.classified_post("perf-helper-default")
    default = general_helpers.saved_commentary(original)
    custom = general_helpers.classified_post("perf-helper-custom")
    texts = {"en": "Keep the original English.", "zh-cn": "保留原来的中文。", "ja": "保存されたテスト用解説。"}
    general_helpers.saved_commentary(custom, texts=texts)
    results = read_post_content_many([original, custom])
    assert results[str(original.pk)].synthesis == {
        "en": "Normalized commentary", "zh-cn": "已保存的评论", "ja": "保存された解説",
    }
    assert default.started_at == general_helpers.NOW - timedelta(hours=2)
    assert default.completed_at == general_helpers.NOW - timedelta(hours=1)
    assert results[str(custom.pk)].synthesis == texts
    assert all(result.synthesis_status == "ready" for result in results.values())


def test_combined_seed_has_ready_trilingual_content_without_changing_base_english_or_chinese():
    require_task_test_database()
    before = timezone.now()
    anchor = seed_each_performance_orm(now=before)
    assert anchor == before
    posts = list(Post.objects.all())
    base_posts = [post for post in posts if post.pk.startswith("u3-post-")]
    assert base_posts
    assert len([post for post in posts if post.pk.startswith("each-area-")]) == 62
    results = read_post_content_many(posts)
    assert all(result.synthesis_status == "ready" for result in results.values())
    assert all(result.synthesis_source == "normalized" for result in results.values())
    for post in base_posts:
        index = post.pk.removeprefix("u3-post-")
        assert post.commentary_en == f"Integrated commentary {index}"
        assert post.commentary_zh_cn == f"综合评论 {index}"
        content = results[str(post.pk)]
        assert content.synthesis["en"] == post.commentary_en
        assert content.synthesis["zh-cn"] == post.commentary_zh_cn
        assert content.synthesis["ja"] == f"保存されたテスト用解説 {post.pk}"
    assert general_helpers.NOW != before, "The historical helper default leaked the preview clock"
