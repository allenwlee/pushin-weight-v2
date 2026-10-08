"""Freeze saved editions and their independent locale/version attribution."""

import json
from pathlib import Path

import pytest

from core.models import EditorialEdition, EditorialStory
from monitor.editorial.config import EditorialConfig
from monitor.editorial.readers import edition_payload
from tests.test_editorial_views import edition

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def test_saved_locale_and_revision_citations_do_not_merge():
    fixture = json.loads(
        Path("tests/fixtures/original_content_migration.json").read_text()
    )
    story = EditorialStory.objects.create(development_key="frozen-multilingual")
    for n, version in enumerate(fixture["versions"]):
        sources = [
            {"id": key, "url": f"https://x.com/i/status/{key}"}
            for key in version["post_ids"]
        ]
        saved = edition(
            f"Saved headline {n}",
            story=story,
            track=version["track"],
            locale=version["locale"],
            revision=version["revision"],
            fingerprint=str(n),
            evidence={"sources": sources},
        )
        result = edition_payload(saved, EditorialConfig())
        assert result["id"] == str(saved.pk)
        assert result["source_count"] == len(version["post_ids"])
        assert [s["url"] for s in result["sources"]] == [s["url"] for s in sources]
        assert f"edition={saved.pk}" in result["url"]
    assert EditorialEdition.objects.filter(story=story).count() == 4
