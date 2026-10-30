"""Targeted source lookup keeps each saved name separate from a verified release."""

import httpx

from core.hf_metadata_client import HFMetadataClient
from core.product_release_acquisition import search_saved_names
from core.product_release_intake import SourceRecord, TextEvidence, detect


def candidate(*names):
    return detect(
        SourceRecord(
            "post",
            "announcement",
            tuple(
                TextEvidence(f"claim/{i}", "release_extraction", name)
                for i, name in enumerate(names)
            ),
        )
    )


def test_search_reuses_duplicate_name_and_preserves_evidence_locators():
    calls = []

    def reply(request):
        calls.append(request)
        return httpx.Response(200, json=[{"id": "lab/Nanbeige4.3-33B"}])

    http = httpx.Client(transport=httpx.MockTransport(reply))
    hf = HFMetadataClient(http, max_requests=2, max_seconds=5)
    results = search_saved_names(candidate("Nanbeige4.3-33B", "Nanbeige4.3-33B"), hf)
    assert [row["locator"] for row in results] == ["claim/0", "claim/1"]
    assert all(row["outcome"] == "ok" for row in results)
    assert all(row["repository_ids"] == ["lab/Nanbeige4.3-33B"] for row in results)
    assert len(calls) == hf.requests == 1


def test_search_keeps_budget_exhaustion_and_ineligible_leads_unresolved():
    http = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[])))
    hf = HFMetadataClient(http, max_requests=1, max_seconds=5)
    results = search_saved_names(candidate("First", "Second", "x" * 257), hf)
    assert [row["outcome"] for row in results] == ["ok", "request_cap", "ineligible"]
    assert hf.requests == 1
