from __future__ import annotations

import httpx
import pytest

from core.hf_metadata_client import HFMetadataClient


def client(handler, **kwargs):
    return HFMetadataClient(
        httpx.Client(transport=httpx.MockTransport(handler)),
        max_requests=kwargs.pop("max_requests", 10),
        max_seconds=120,
        sleep=lambda _: None,
        **kwargs,
    )


def test_short_page_keeps_provider_continuation():
    hf = client(
        lambda r: httpx.Response(
            200,
            json=[{"id": "lab/model"}],
            headers={
                "link": '<https://huggingface.co/api/models?cursor=abc>; rel="next"'
            },
        )
    )
    result = hf.list_page("lab")
    assert result.outcome == "ok"
    assert result.next_cursor == "abc"
    assert len(result.payload) == 1


@pytest.mark.parametrize(
    "link",
    [
        '<https://evil.example/api/models?cursor=abc>; rel="next"',
        '<https://huggingface.co/other?cursor=abc>; rel="next"',
        '<https://huggingface.co/api/models>; rel="next"',
    ],
)
def test_bad_continuations_are_incomplete(link):
    hf = client(lambda r: httpx.Response(200, json=[], headers={"link": link}))
    assert hf.list_page("lab").outcome == "invalid_continuation"
    assert hf.requests == 1


def test_complementary_detail_requests_preserve_unknown_and_false_values():
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "id": "lab/model",
                "private": False,
                "downloadsAllTime": 0,
                "futureField": {"nested": [False, None, 4_000_000_000]},
            },
        )

    hf = client(respond)
    detail = hf.model_group("lab/model", "detail")
    expanded = hf.model_group("lab/model", "expanded")
    assert detail.payload["futureField"]["nested"][2] == 4_000_000_000
    assert expanded.payload["downloadsAllTime"] == 0
    assert calls[0].url.params["blobs"] == "true"
    assert calls[0].url.params["securityStatus"] == "true"
    assert "expand" not in calls[0].url.params
    assert "downloadsAllTime" in calls[1].url.params.get_list("expand")
    assert "blobs" not in calls[1].url.params
    assert all("authorization" not in r.headers for r in calls)


def test_retries_share_physical_budget_and_keep_attempt_evidence():
    hf = client(lambda r: httpx.Response(503), max_requests=2)
    result = hf.model_group("lab/model", "detail")
    assert hf.requests == 2
    assert result.outcome == "request_cap"
    assert len(result.attempts) == 2
    assert [a["http_status"] for a in result.attempts] == [503, 503]


@pytest.mark.parametrize(
    "status,outcome",
    [
        (401, "unauthorized"),
        (403, "forbidden"),
        (404, "not_found"),
    ],
)
def test_access_failures_are_not_retried(status, outcome):
    hf = client(lambda r: httpx.Response(status))
    assert hf.model_group("lab/model", "detail").outcome == outcome
    assert hf.requests == 1


@pytest.mark.parametrize(
    "payload,outcome",
    [
        ({"id": "other/model"}, "identity_mismatch"),
        ({"id": "lab/model", "private": True}, "private"),
        ([{"id": "lab/model"}], "malformed"),
    ],
)
def test_untrusted_model_payloads_are_rejected(payload, outcome):
    hf = client(lambda r: httpx.Response(200, json=payload))
    assert hf.model_group("lab/model", "detail").outcome == outcome


def test_oversized_response_is_explicit():
    hf = client(lambda r: httpx.Response(200, content=b"x" * 100), max_bytes=50)
    result = hf.model_group("lab/model", "detail")
    assert result.outcome == "response_size_cap"
    assert result.payload is None


def test_foreign_redirect_is_never_followed():
    hf = client(
        lambda r: httpx.Response(302, headers={"location": "https://evil.example"})
    )
    assert hf.model_group("lab/model", "detail").outcome == "redirect"
    assert hf.requests == 1


def test_malformed_json_is_not_empty_success():
    hf = client(lambda r: httpx.Response(200, content=b"not json"))
    assert hf.list_page("lab").outcome == "malformed"


def test_namespace_falls_back_to_user_and_keeps_both_attempts():
    def respond(request):
        if "/organizations/" in request.url.path:
            return httpx.Response(404)
        return httpx.Response(200, json={"name": "Lab", "fullname": "Research Lab"})

    hf = client(respond)
    result = hf.namespace_info("lab")
    assert result.outcome == "ok"
    assert [a["http_status"] for a in result.attempts] == [404, 200]
    assert hf.requests == 2


def test_missing_namespace_is_not_verified_empty():
    hf = client(lambda r: httpx.Response(404))
    result = hf.namespace_info("missing")
    assert result.outcome == "not_found"
    assert len(result.attempts) == 2


def test_wrong_namespace_identity_is_rejected():
    hf = client(lambda r: httpx.Response(200, json={"name": "other"}))
    assert hf.namespace_info("lab").outcome == "identity_mismatch"


def test_client_credentials_are_not_sent():
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(200, json={"id": "lab/model"})

    transport = httpx.Client(
        transport=httpx.MockTransport(respond),
        auth=("user", "secret"),
        headers={"Authorization": "Bearer secret"},
        cookies={"session": "secret"},
    )
    hf = HFMetadataClient(transport, max_requests=1, max_seconds=10)
    assert hf.model_group("lab/model", "detail").outcome == "ok"
    assert "authorization" not in seen[0].headers
    assert "cookie" not in seen[0].headers


def test_retry_after_past_deadline_stops_without_sleep():
    sleeps = []
    hf = HFMetadataClient(
        httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(429, headers={"retry-after": "3600"})
            )
        ),
        max_requests=10,
        max_seconds=120,
        sleep=sleeps.append,
    )
    result = hf.model_group("lab/model", "detail")
    assert result.outcome == "time_cap"
    assert hf.requests == 1
    assert sleeps == []
    assert result.attempts[0]["outcome"] == "throttled"


def test_expired_deadline_sends_no_request():
    now = [0.0]
    hf = HFMetadataClient(
        httpx.Client(
            transport=httpx.MockTransport(lambda r: pytest.fail("unexpected request"))
        ),
        max_requests=10,
        max_seconds=1,
        clock=lambda: now[0],
    )
    now[0] = 2
    assert hf.list_page("lab").outcome == "time_cap"
    assert hf.requests == 0


def test_transient_retry_then_success_preserves_both_attempts():
    responses = iter(
        [httpx.Response(503), httpx.Response(200, json={"id": "lab/model"})]
    )
    hf = client(lambda r: next(responses))
    result = hf.model_group("lab/model", "detail")
    assert result.outcome == "ok"
    assert len(result.attempts) == 2
    assert hf.requests == 2
    assert hf.retries == 1


@pytest.mark.parametrize("repo", ["../other", "lab/../model", "lab/model?token=x"])
def test_invalid_repository_never_reaches_transport(repo):
    hf = client(lambda r: pytest.fail("unexpected request"))
    assert hf.model_group(repo, "detail").outcome == "malformed"
    assert hf.requests == 0


def test_rejected_optional_expansion_has_bounded_partial_fallback():
    calls = []

    def respond(request):
        calls.append(request)
        if "resourceGroup" in request.url.params.get_list("expand"):
            return httpx.Response(400, json={"error": "unsupported projection"})
        return httpx.Response(200, json={"id": "lab/model", "downloads": 0})

    hf = client(respond)
    result = hf.model_group("lab/model", "expanded")
    assert result.outcome == "partial_expansion"
    assert result.payload["downloads"] == 0
    assert len(calls) == 2
    assert result.attempts[0]["payload"] == {"error": "unsupported projection"}


def test_mismatched_author_is_not_an_owned_model():
    hf = client(
        lambda r: httpx.Response(200, json={"id": "lab/model", "author": "other"})
    )
    assert hf.model_group("lab/model", "detail").outcome == "identity_mismatch"


def test_captured_live_payloads_keep_complementary_fields():
    import json
    from pathlib import Path

    capture = json.loads(
        (
            Path(__file__).parent
            / "fixtures/hf_catalog/2026-09-24-minimax-public-metadata.json"
        ).read_text()
    )
    detail = capture["detail"]["payload"]
    expanded = capture["expanded"]["payload"]
    assert "securityRepoStatus" in detail
    assert "downloadsAllTime" in expanded
    assert capture["physical_requests"] == 4
    assert detail["id"] == expanded["id"]


def test_valid_underscore_model_name_does_not_block_namespace_page():
    hf = client(lambda r: httpx.Response(200, json=[{"id": "lab/_model"}]))
    assert hf.list_page("lab").outcome == "ok"
