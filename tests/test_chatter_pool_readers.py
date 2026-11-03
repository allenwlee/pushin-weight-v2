"""Source-language pools stay separate from each other and publication locale."""

import pytest
from django.utils import timezone

from core.models import OriginalContentSelection, Post
from monitor.editorial.readers import feed_payload
from monitor.original_content import publish_content
from tests.editorial_support import active_config
from tests.test_original_content_consideration import consideration, text_spec

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def published(group, post_id):
    content = consideration(consideration_state="selected", editorial_group=group)
    post = Post.objects.create(tweet_id=post_id, text="A company announced a model.", created_at=timezone.now())
    (text,) = publish_content(
        content, [text_spec(content, post, "en")], fence=content.run.fence,
        selected_scope=f"featured:social-brief:en:{group}:en",
    )
    return text


def test_pool_isolation_and_independent_publication_language(monkeypatch):
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    cfg = active_config(pictures={})
    rest = published("rest", "884001")
    giant = published("giant", "884002")
    feed = feed_payload(cfg, source_locale="en", editorial_group="rest")
    assert feed["hero"]["id"] == str(rest.public_id)
    assert {row["id"] for row in feed["items"]} == {str(rest.public_id)}
    other = feed_payload(cfg, source_locale="en", editorial_group="giant")
    assert other["hero"]["id"] == str(giant.public_id)
    empty = feed_payload(cfg, source_locale="ja", editorial_group="rest")
    assert empty["hero"] is None and empty["items"] == []
    fallback = feed_payload(cfg, locale="ja", source_locale="en", editorial_group="rest")
    assert fallback["hero"]["id"] == str(rest.public_id)
    assert fallback["requested_locale"] == "ja" and fallback["locale"] == "en"


def test_cursor_cannot_move_between_editorial_pools(monkeypatch):
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    cfg = active_config(pictures={})
    published("rest", "884003")
    published("rest", "884004")
    published("giant", "884005")
    first = feed_payload(cfg, source_locale="en", editorial_group="rest", limit=1)
    assert first["next_cursor"]
    with pytest.raises(ValueError, match="cursor"):
        feed_payload(cfg, source_locale="en", editorial_group="giant", cursor=first["next_cursor"])


def test_old_feed_does_not_mix_new_pools_and_pointer_cannot_cross_pool(monkeypatch):
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    cfg = active_config(pictures={})
    rest = published("rest", "884006")
    giant = published("giant", "884007")
    legacy = feed_payload(cfg)
    assert legacy["items"] == [] and legacy["hero"] is None
    OriginalContentSelection.objects.filter(
        scope_key="featured:social-brief:en:rest:en"
    ).update(text=giant)
    feed = feed_payload(cfg, source_locale="en", editorial_group="rest")
    assert feed["hero"] is None
    assert {row["id"] for row in feed["items"]} == {str(rest.public_id)}


def test_legacy_storage_rejects_pool_request(monkeypatch):
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "legacy")
    with pytest.raises(ValueError, match="pool"):
        feed_payload(active_config(pictures={}), source_locale="en", editorial_group="rest")


@pytest.mark.parametrize("pool", [
    {"source_locale": "fr", "editorial_group": "rest"},
    {"source_locale": "en", "editorial_group": "untracked"},
    {"source_locale": "en"},
])
def test_unknown_or_incomplete_pool_is_rejected(monkeypatch, pool):
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    with pytest.raises(ValueError, match="pool"):
        feed_payload(active_config(pictures={}), **pool)
