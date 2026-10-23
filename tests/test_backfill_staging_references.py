"""Frozen author roles must not spend credits before failing a staging FK."""
import copy

import pytest

from core.collection_jobs import register_job, set_job_state
from core.models import Brand, CollectionRequest, CollectionRun
from monitor.backfill_collection import execute_job
from tests.test_backfill_prefetch import http_pages, pipeline  # noqa: F401
from tests.test_backfill_staging import result_for, staged_job

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


@pytest.mark.parametrize("role", ["official_brands", "staff_brands"])
def test_missing_frozen_role_brand_stops_before_request_then_resumes(http_pages, monkeypatch, role):  # noqa: F811
    seed = staged_job(monkeypatch, 1)
    definition = copy.deepcopy(seed.definition)
    definition["scope"]["author_scope"] = {"contexts": {"123": {
        "official_brands": [], "staff_brands": [], role: ["missing-author-brand"],
    }}}
    job = register_job(job_key="missing-reference-test", source=seed.source, purpose="content",
                       operation="x_backfill", mode="historical", definition=definition)
    set_job_state(job.pk, "ready")
    with http_pages(result_for) as state:
        with pytest.raises(ValueError, match="staging brand references missing: missing-author-brand"):
            execute_job(job.pk, collection_options={"concurrency": 20})
        assert not state["requests"]
        assert not CollectionRequest.objects.exists()
        assert not CollectionRun.objects.filter(job=job).exists()
        Brand.objects.create(nickname="missing-author-brand", display_name="Fixture author brand")
        result = execute_job(job.pk, collection_options={"concurrency": 20})
    assert result["collection_drained"]
    assert len(state["requests"]) == 1
