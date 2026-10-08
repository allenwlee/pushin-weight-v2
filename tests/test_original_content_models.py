"""Shared authored content supports non-brand output and relational citations."""
from uuid import uuid4

import pytest
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from core.models import (
    OriginalContent, OriginalContentRun, OriginalContentSource,
    OriginalContentText, OriginalContentSelection, Post,
)

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def saved_text(locale="en"):
    now = timezone.now()
    run = OriginalContentRun.objects.create(
        source_cycle_id=str(uuid4()), workflow_key="editorial-dispatch",
        scope_key=str(uuid4()), facts_as_of=now, window_days=None,
        packet_schema_version=1, snapshot={},
    )
    content = OriginalContent.objects.create(
        run=run, workflow_key="social-brief", output_key=str(uuid4()),
        subject_key="historical-chonk", story_id=uuid4(), status="prepared",
        attempted_at=now, brand_key_snapshot="", brand_name_en_snapshot="",
        brand_name_zh_cn_snapshot="",
    )
    return OriginalContentText.objects.create(
        narrative=content, locale=locale, headline="LECHONK RETURNS",
        secondary="A recurrent model nickname", body="Saved context.",
    )


def test_sources_are_unique_per_saved_text_and_protect_post():
    text = saved_text()
    post = Post.objects.create(tweet_id="source-1", text="writing-time text")
    source = OriginalContentSource.objects.create(
        text=text, post=post, position=0,
        url_snapshot="https://example.org/posts/1", source_hash="a" * 64,
        hash_basis="writing_packet",
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        OriginalContentSource.objects.create(
            text=text, post=post, position=1, url_snapshot=source.url_snapshot,
            source_hash="a" * 64, hash_basis="writing_packet",
        )
    with pytest.raises(ProtectedError):
        post.delete()
    post.text = "edited later"
    post.save()
    source.refresh_from_db()
    assert source.source_hash == "a" * 64
    assert source.url_snapshot == "https://example.org/posts/1"
    other = saved_text("ja")
    OriginalContentSource.objects.create(
        text=other, post=post, position=0, url_snapshot=source.url_snapshot,
        hash_basis="legacy_unavailable",
    )
    assert text.sources.count() == other.sources.count() == 1


def test_featured_selection_has_text_and_no_window():
    text = saved_text()
    pointer = OriginalContentSelection.objects.create(
        scope_key="featured:social-brief:en", text=text,
        facts_as_of=timezone.now(), activated_at=timezone.now(),
    )
    assert pointer.run_id is None and pointer.window_days is None
    with pytest.raises(IntegrityError), transaction.atomic():
        OriginalContentSelection.objects.create(
            scope_key="featured:social-brief:ja", text=text, run=text.narrative.run,
            facts_as_of=timezone.now(), activated_at=timezone.now(),
        )


def test_source_requires_url_and_honest_hash_basis():
    text = saved_text()
    post = Post.objects.create(tweet_id="bad-source")
    with pytest.raises(IntegrityError), transaction.atomic():
        OriginalContentSource.objects.create(
            text=text, post=post, position=0, url_snapshot="",
            hash_basis="writing_packet",
        )


def test_publish_failure_leaves_no_partial_copy_citation_or_pointer():
    from monitor.original_content import publish_content

    existing = saved_text()
    content = existing.narrative
    existing.delete()
    with pytest.raises(ValueError, match="requires citations"):
        publish_content(content, [{"locale": "en", "headline": "A saved headline",
            "byline": "Saved byline", "sources": []}])
    content.refresh_from_db()
    assert content.status == "prepared"
    assert not content.localized_texts.exists()
    assert not OriginalContentSelection.objects.exists()


def test_editorial_publication_preserves_safe_non_x_urls_and_exact_producer():
    from core.models import OriginalContentCall
    from monitor.original_content import publish_content, source_payload

    old_text = saved_text()
    content = old_text.narrative
    old_text.delete()
    now = timezone.now()
    call = OriginalContentCall.objects.create(
        run=content.run, stage="write:story:en", workflow_key="social-brief",
        request_identity=str(uuid4()), request_hash="b" * 64, response_hash="c" * 64,
        state="completed", reserved_at=now, sent_at=now, completed_at=now,
    )
    post = Post.objects.create(tweet_id="forum-post", text="saved evidence")
    text, = publish_content(content, [{"locale": "en", "headline": "A headline",
        "byline": "A byline", "body": "The body", "producing_call": call,
        "sources": [{"id": post.pk, "url": "https://example.org/posts/123",
                     "original_text": post.text}]}], selected_scope="featured:social-brief:en")
    assert text.producing_call_id == call.pk
    assert source_payload(text) == [{"url": "https://example.org/posts/123", "label": "Source"}]
    assert OriginalContentSelection.objects.get().text_id == text.pk
