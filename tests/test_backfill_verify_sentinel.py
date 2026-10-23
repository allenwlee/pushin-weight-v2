"""The full acceptance check respects the same sentinel rule as collection."""
from pathlib import Path

import pytest

from core.models import Brand, PostBrand, PostBrandMention
from monitor.backfill_collection import execute_job
from scripts.backfill_verify import verify_posts
from tests.test_backfill_prefetch import http_pages, pipeline  # noqa: F401
from tests.test_backfill_staging import result_for, staged_job
from x_monitor.config import load_config

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


@pytest.mark.parametrize("collection_only", [False, True])
def test_missing_real_brand_mention_fails_but_sentinel_needs_no_mention(http_pages, monkeypatch, collection_only):  # noqa: F811
    job = staged_job(monkeypatch, 1)
    with http_pages(result_for):
        report = execute_job(job.pk)
    ids = report["recovered_post_ids"]
    assert len(ids) == 1
    cfg = load_config(Path("config.yaml"))
    PostBrandMention.objects.filter(post_id__in=ids).delete()
    broken = verify_posts(ids, cfg=cfg, collection_only=collection_only)
    assert "brand_mention_missing" in broken["errors"][ids[0]]
    sentinel, _ = Brand.objects.get_or_create(nickname="_unattributed", defaults={"is_sentinel": True})
    assert sentinel.is_sentinel
    PostBrand.objects.filter(post_id__in=ids).delete()
    PostBrand.objects.create(post_id=ids[0], brand=sentinel, weight=1)
    valid_sentinel = verify_posts(ids, cfg=cfg, collection_only=collection_only)
    assert "brand_mention_missing" not in valid_sentinel["errors"].get(ids[0], [])
    # Other incomplete enrichment still fails; sentinel handling cannot hide it.
    if not collection_only:
        assert "durable_enrichment_incomplete" in valid_sentinel["errors"][ids[0]]
