"""Real saved-story routes and rollback retain version UUIDs and citation sets."""

import pytest

from core.models import EditorialHero, Post
from monitor.editorial.config import EditorialConfig
from monitor.editorial.readers import feed_payload
from monitor.original_content_backfill import backfill_original_content
from tests.test_editorial_views import edition

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def test_shared_reader_uses_relational_citations_including_non_x_urls(
    monkeypatch, client
):
    cfg = EditorialConfig(public_enabled=True)
    Post.objects.create(tweet_id="1", text="Original source")
    Post.objects.create(tweet_id="2", text="Original second source")
    saved = edition(
        evidence={
            "sources": [
                {"id": "1", "url": "https://x.com/i/status/1"},
                {"id": "2", "url": "https://example.org/posts/2"},
            ]
        }
    )
    EditorialHero.objects.create(key="chatter:en", edition=saved)
    assert backfill_original_content(apply=True)["ready"]
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    monkeypatch.setattr("monitor.editorial.views.load_editorial_config", lambda: cfg)
    # Mutating the backup JSON cannot change accepted relational attribution.
    saved.evidence = {"sources": []}
    saved.save(update_fields=["evidence"])
    item = feed_payload(cfg)["hero"]
    assert item["id"] == str(saved.pk) and item["source_count"] == 2
    assert [source["url"] for source in item["sources"]] == [
        "https://x.com/i/status/1",
        "https://example.org/posts/2",
    ]
    assert client.get(item["url"], secure=True).status_code == 200
    assert (
        client.get("/api/v2/editorial-stories/", secure=True).json()["hero"][
            "source_count"
        ]
        == 2
    )


def test_shared_and_compatible_legacy_readers_keep_pinned_urls_and_copy(monkeypatch):
    Post.objects.create(tweet_id="1", text="Original source")
    saved = edition()
    EditorialHero.objects.create(key="chatter:en", edition=saved)
    cfg = EditorialConfig()
    before = feed_payload(cfg)
    assert backfill_original_content(apply=True)["ready"]
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    assert feed_payload(cfg) == before
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "legacy")
    assert feed_payload(cfg) == before


def test_incompatible_provider_consumer_prevents_cutover():
    from monitor.original_content_cutover import (
        ADAPTER_VERSION,
        CONSUMERS,
        validate_consumers,
    )

    candidate = "a" * 40
    receipts = {
        key: {"revision": candidate, "adapter_version": ADAPTER_VERSION}
        for key in CONSUMERS
    }
    validate_consumers(receipts, candidate)
    receipts["pictures"]["adapter_version"] = "old-provider"
    with pytest.raises(ValueError, match="incompatible consumer: pictures"):
        validate_consumers(receipts, candidate)


def test_cutover_blocks_a_missing_citation_after_import():
    from core.models import OriginalContentSource
    from monitor.original_content_cutover import readiness

    Post.objects.create(tweet_id="1", text="Original source")
    edition()
    assert backfill_original_content(apply=True)["ready"]
    assert readiness()["ready"]
    OriginalContentSource.objects.all().delete()
    report = readiness()
    assert not report["ready"]
    assert any(e["kind"] == "shared_edition_parity" for e in report["exceptions"])


def test_shared_source_reads_remain_bounded_by_page_count(monkeypatch):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    Post.objects.create(tweet_id="1", text="Original source")
    for _ in range(24):
        edition()
    assert backfill_original_content(apply=True)["ready"]
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    cfg = EditorialConfig()
    with CaptureQueriesContext(connection) as one:
        feed_payload(cfg, limit=1)
    with CaptureQueriesContext(connection) as many:
        result = feed_payload(cfg, limit=20)
    assert len(result["items"]) == 20
    assert len(many) <= len(one) + 1
