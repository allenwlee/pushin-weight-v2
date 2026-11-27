"""Actual PostgreSQL content readers for the combined performance seed."""
import os
from datetime import timedelta
from html.parser import HTMLParser
from unittest.mock import patch
from urllib.parse import urlparse

import pytest
from django.db import connection
from django.test import Client, override_settings
from django.utils import timezone

from core.models import (
    Post,
    PostBrandClassificationState,
    PostEnrichmentState,
    PostSynthesisDemand,
)
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


@override_settings(SECURE_SSL_REDIRECT=False)
def test_terminal_translation_fixture_renders_failed_sprite_without_pending_work_or_synthesis_demand():
    require_task_test_database()
    anchor = seed_each_performance_orm()
    state = PostEnrichmentState.objects.get(post_id="u3-post-0")
    assert state.translation_requested and state.translation_status == "failed"
    assert state.translation_attempts == 3
    assert state.translation_error_code == "fixture_terminal_translation_failure"
    assert state.translation_next_attempt_at is None
    assert state.classification_status == "succeeded"
    assert state.classification_next_attempt_at is None
    assert not state.claim_owner and state.claim_expires_at is None
    previous = list(PostBrandClassificationState.objects.filter(post_id=state.post_id).values())
    assert previous and all(row["outcome"] == "classified" for row in previous)

    class FailedFixtureRow(HTMLParser):
        def __init__(self):
            super().__init__()
            self.depth = 0
            self.row = None
            self.elements = []

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "div":
                if self.depth:
                    self.depth += 1
                elif attrs.get("data-tweet-id") == "u3-post-0":
                    self.depth = 1
                    self.row = attrs
            if self.depth:
                self.elements.append((tag, attrs))

        def handle_endtag(self, tag):
            if tag == "div" and self.depth:
                self.depth -= 1

    with patch("django.utils.timezone.now", return_value=anchor):
        response = Client().get("/", {"locale": "en", "window": "365"})
    assert response.status_code == 200
    parsed = FailedFixtureRow()
    parsed.feed(response.content.decode())
    assert parsed.row is not None, "The synthetic terminal fixture must be in the real visible feed"
    assert parsed.row["data-enrichment-status"] == "failed"
    assert parsed.row["data-translation-status"] == "failed"
    assert parsed.row["data-synthesis-status"] == "ready"
    assert any(tag == "use" and attrs.get("href", "").endswith("#icon-failed-stop")
               and "pw-processing-glyphs" in attrs["href"] for tag, attrs in parsed.elements)
    assert any(tag == "button" and attrs.get("data-process") == "translation"
               and "enrichment-status-failed" in attrs.get("class", "")
               and "No more attempts are scheduled" in attrs.get("aria-label", "")
               for tag, attrs in parsed.elements)
    assert list(PostBrandClassificationState.objects.filter(post_id=state.post_id).values()) == previous
    assert all(content.synthesis_status == "ready" for content in read_post_content_many(list(Post.objects.all())).values())
    from monitor.enrichment_queue import stage_due_q
    assert not PostEnrichmentState.objects.filter(stage_due_q("translation", anchor) | stage_due_q("classification", anchor)).exists()
    assert not PostSynthesisDemand.objects.filter(state__in=["pending", "processing"]).exists()


@override_settings(SECURE_SSL_REDIRECT=False)
def test_each_general_panel_has_a_real_continuation_in_performance_fixture():
    require_task_test_database()
    anchor = seed_each_performance_orm()
    from monitor.general_readers import general_feed
    for section in ("calendar", "free", "jobs", "moving"):
        first = general_feed(section, brands=["qwen"], as_of=anchor)
        assert len(first["items"]) == 20 and first["next_cursor"]
        second = general_feed(section, brands=["qwen"], cursor=first["next_cursor"])
        assert second["items"]
        assert not {item["id"] for item in first["items"]} & {item["id"] for item in second["items"]}
