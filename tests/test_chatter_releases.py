"""Retained document releases join Chatter without synthetic posts or launch dates."""

import pytest
from django.utils import timezone

from core.models import OriginalContent, Post
from core.product_release_study import apply_study
from tests.test_original_content_consideration import consideration
from tests.test_product_release_documents import assessment, captured_document

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_required_document_release_uses_real_dossier_source(tmp_path):
    from monitor.editorial.chatter_chain import _consider
    from monitor.editorial.chatter_history import read_sources
    from monitor.editorial.chatter_releases import admit_releases, prepare_releases

    before = Post.objects.count()
    saved, _, _ = captured_document(tmp_path)
    apply_study(assessment(saved["observation_id"]))
    now = timezone.now()
    prepared = prepare_releases(now)
    entry = next(
        row
        for row in prepared.values()
        if row["dossier"]
        .sources.filter(collection_observation_id=saved["observation_id"])
        .exists()
    )
    prepared = {str(entry["story"].pk): entry}
    source = entry["sources"][0]
    assert source["kind"] == "dossier_source" and source["created_at"] is None
    assert "We announce Model Flash" in source["original_text"]
    row = consideration()
    row.run.facts_as_of = now
    row.run.snapshot = {"schema_version": 1, "sources": {}}
    row.run.save(update_fields=["facts_as_of", "snapshot"])
    admit_releases(row.run, None, _consider, prepared)
    candidate = OriginalContent.objects.get(run=row.run, development=entry["story"])
    assert (
        candidate.appearance_kind == "release"
        and candidate.consideration_state == "pending"
    )
    assert (
        read_sources(candidate)[0]["dossier_source_id"]
        == entry["dossier"].sources.get().pk
    )
    assert Post.objects.count() == before
