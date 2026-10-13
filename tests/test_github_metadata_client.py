"""GitHub requests stay public, bounded and on the admitted endpoint."""

import httpx
import pytest

from core.github_metadata_client import GitHubMetadataClient
from scripts.benchmark_download_collector.sources import Budget, SourceError


def client(handler, **limits):
    return GitHubMetadataClient(
        Budget(httpx.Client(transport=httpx.MockTransport(handler)), **limits)
    )


def test_page_retains_native_ids_and_checked_next_link():
    calls = []

    def response(request):
        calls.append(request)
        return httpx.Response(
            200,
            json=[{"id": 123}],
            headers={
                "Link": '<https://api.github.com/orgs/publisher/repos?page=2&per_page=100>; rel="next"',
                "ETag": '"revision"',
            },
        )

    result = client(response).repositories("publisher", "organization")
    assert result.payload == [{"id": 123}]
    assert result.next_url.endswith("page=2&per_page=100")
    assert result.etag == '"revision"'
    assert "authorization" not in calls[0].headers
    assert calls[0].headers["user-agent"] == "PushinWeight-public-metadata"


def test_untrusted_pagination_cannot_receive_credentials():
    sent = []

    def response(request):
        sent.append(request)
        return httpx.Response(
            200,
            json=[],
            headers={"Link": '<https://example.com/repos?page=2>; rel="next"'},
        )

    with pytest.raises(ValueError, match="pagination"):
        client(response).repositories("publisher", "organization")
    assert len(sent) == 1


def test_304_preserves_conditional_state_and_rate_limit_has_cooldown():
    def response(request):
        assert request.headers["if-none-match"] == '"known"'
        return httpx.Response(304, headers={"ETag": '"known"'})

    result = client(response).repositories("publisher", "organization", etag='"known"')
    assert result.status == 304 and result.payload is None
    result = client(
        lambda _: httpx.Response(429, headers={"Retry-After": "300"})
    ).repositories("publisher", "organization")
    assert result.retry_at is not None and result.status == 429


def test_request_and_total_byte_budgets_are_enforced():
    reader = client(lambda _: httpx.Response(200, json=[]), max_requests=1)
    reader.repositories("publisher", "organization")
    with pytest.raises(SourceError, match="request_cap"):
        reader.repositories("publisher", "organization")
    reader = client(
        lambda _: httpx.Response(200, json={"value": "x" * 20}), max_bytes=50
    )
    reader.repository("publisher/model")
    with pytest.raises(SourceError, match="response_size_cap"):
        reader.repository("publisher/model")


def test_file_reads_require_pinned_revision_and_allowlisted_small_metadata():
    reader = client(lambda _: httpx.Response(200, json={}))
    with pytest.raises(ValueError, match="revision"):
        reader.file("publisher/model", "README.md", "main")
    with pytest.raises(ValueError, match="metadata"):
        reader.file("publisher/model", "weights.safetensors", "a" * 40)
