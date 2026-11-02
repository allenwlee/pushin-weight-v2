from __future__ import annotations

import httpx
import pytest

from core.hf_metadata_client import HFMetadataClient


def test_targeted_model_search_without_known_publisher_keeps_all_leads():
    requests = []

    def respond(request):
        requests.append(request)
        assert request.url.path == "/api/models"
        assert request.url.params["search"] == "Nanbeige4.3-33B"
        assert request.url.params["limit"] == "5"
        assert "author" not in request.url.params
        return httpx.Response(200, json=[{"id": "lab/Nanbeige4.3-33B"}, {"id": "other/Nanbeige4.3-33B"}])

    hf = client(respond)
    result = hf.search_models("Nanbeige4.3-33B", limit=5)
    assert result.outcome == "ok"
    assert [row["id"] for row in result.payload] == ["lab/Nanbeige4.3-33B", "other/Nanbeige4.3-33B"]
    assert len(requests) == hf.requests == 1


def test_targeted_model_search_rejects_invalid_input_before_request():
    hf = client(lambda _: pytest.fail("invalid input must not make a request"))
    assert hf.search_models(" ").outcome == "malformed"
    assert hf.search_models("x" * 257).outcome == "malformed"
    assert hf.search_models("model", limit=0).outcome == "malformed"
    assert hf.requests == 0


def test_targeted_model_search_reports_incomplete_page_without_following_it():
    hf = client(
        lambda _: httpx.Response(
            200,
            json=[{"id": "lab/model"}],
            headers={"link": '<https://huggingface.co/api/models?cursor=abc>; rel="next"'},
        )
    )
    result = hf.search_models("model", limit=1)
    assert result.outcome == "ok" and result.next_cursor == "abc"
    assert hf.requests == 1


def test_targeted_search_resume_preserves_term_and_opaque_cursor():
    def respond(request):
        assert request.url.params["search"] == "Nanbeige4.3-33B"
        assert request.url.params["cursor"] == "opaque+/="
        assert request.url.params["limit"] == "5"
        return httpx.Response(200, json=[{"id": "lab/second"}])

    result = client(respond).search_models("Nanbeige4.3-33B", limit=5, cursor="opaque+/=")
    assert result.outcome == "ok" and result.next_cursor is None


def test_targeted_model_search_rejects_untrusted_continuation_and_bad_rows():
    hf = client(
        lambda _: httpx.Response(
            200,
            json=[{"id": "lab/model"}],
            headers={"link": '<https://other.example/api/models?cursor=abc>; rel="next"'},
        )
    )
    assert hf.search_models("model").outcome == "invalid_continuation"
    hf = client(lambda _: httpx.Response(200, json=[{"id": "invalid"}]))
    assert hf.search_models("model").outcome == "malformed"


def test_history_rejects_an_unparseable_next_link():
    hf = client(lambda _: httpx.Response(200, json=[], headers={"link": 'rel="next"'}))
    result = hf.history_page("lab/model", "a" * 40, "commits")
    assert result.outcome == "invalid_continuation"


def test_legacy_commit_pages_keep_pinned_path_and_stop_without_next_link():
    calls = []
    path = "/api/models/01-ai/Yi-6B-Chat-4bits/commits/" + "a" * 40

    def respond(request):
        calls.append(request)
        assert request.url.host == "huggingface.co" and request.url.path == path
        assert "cursor" not in request.url.params
        page = int(request.url.params.get("p", "0"))
        if page:
            assert dict(request.url.params) == {"p": str(page), "limit": "50"}
        start, stop = [(1, 51), (51, 61), (61, 66)][page]
        return httpx.Response(
            200,
            json=[{"id": f"{i:040x}"} for i in range(start, stop)],
            headers={
                "link": f'<https://huggingface.co{path}?p={page + 1}&limit=50>; rel="next"'
            }
            if page < 2
            else {},
        )

    hf = client(respond)
    first = hf.history_page("01-ai/Yi-6B-Chat-4bits", "a" * 40, "commits")
    assert first.outcome == "ok" and len(first.payload) == 50
    assert first.next_cursor == "hf-commits-page:v1:1:50"
    second = hf.history_page(
        "01-ai/Yi-6B-Chat-4bits", "a" * 40, "commits", first.next_cursor
    )
    assert second.outcome == "ok" and len(second.payload) == 10
    assert second.next_cursor == "hf-commits-page:v1:2:50"
    final = hf.history_page(
        "01-ai/Yi-6B-Chat-4bits", "a" * 40, "commits", second.next_cursor
    )
    assert final.outcome == "ok" and final.next_cursor is None
    assert len(final.payload) == 5 and hf.requests == len(calls) == 3


@pytest.mark.parametrize("kind", ["commits", "tree"])
def test_history_opaque_cursor_stays_opaque(kind):
    calls = []
    path = f"/api/models/lab/model/{kind}/" + "a" * 40

    def respond(request):
        calls.append(request)
        assert request.url.path == path
        if len(calls) == 1:
            tuning = "&recursive=true&expand=true&limit=1000" if kind == "tree" else ""
            return httpx.Response(
                200,
                json=[],
                headers={
                    "link": f'<https://huggingface.co{path}?cursor=opaque%2B%2F%3D{tuning}>; rel="next"'
                },
            )
        assert request.url.params["cursor"] == "opaque+/="
        if kind == "tree":
            assert request.url.params["recursive"] == "true"
            assert request.url.params["expand"] == "true"
        return httpx.Response(200, json=[])

    hf = client(respond)
    first = hf.history_page("lab/model", "a" * 40, kind)
    assert first.outcome == "ok" and first.next_cursor == "opaque+/="
    final = hf.history_page("lab/model", "a" * 40, kind, first.next_cursor)
    assert final.outcome == "ok" and final.next_cursor is None


@pytest.mark.parametrize(
    "suffix",
    [
        "?p=0&limit=50",
        "?p=-1&limit=50",
        "?p=01&limit=50",
        "?p=%2B1&limit=50",
        "?p=%D9%A1&limit=50",
        "?p=100001&limit=50",
        "?p=1&limit=0",
        "?p=1&limit=101",
        "?p=1&limit=050",
        "?p=&limit=50",
        "?p=1&limit=",
        "?p=1",
        "?limit=50",
        "?p=1&p=2&limit=50",
        "?p=1&limit=50&limit=50",
        "?p=1&limit=50&cursor=opaque",
        "?p=1&limit=50&cursor=",
        "?cursor=opaque&p=&limit=",
        "?cursor=one&cursor=two",
        "?cursor=",
        "?p=1&limit=50&unknown=1",
        "?p=1&limit=50&broken",
        "?p=1&limit=50#fragment",
        ";params?p=1&limit=50",
    ],
)
def test_history_rejects_invalid_or_ambiguous_page_parameters(suffix):
    link = f'<https://huggingface.co/api/models/lab/model/commits/{"a" * 40}{suffix}>; rel="next"'
    hf = client(lambda _: httpx.Response(200, json=[], headers={"link": link}))
    assert hf.history_page("lab/model", "a" * 40, "commits").outcome == (
        "invalid_continuation"
    )
    assert hf.requests == 1


@pytest.mark.parametrize(
    "url",
    [
        "http://huggingface.co/api/models/lab/model/commits/" + "a" * 40,
        "https://evil.example/api/models/lab/model/commits/" + "a" * 40,
        "https://user@huggingface.co/api/models/lab/model/commits/" + "a" * 40,
        "https://huggingface.co:443/api/models/lab/model/commits/" + "a" * 40,
        "https://huggingface.co/api/models/other/model/commits/" + "a" * 40,
        "https://huggingface.co/api/models/lab/model/tree/" + "a" * 40,
        "https://huggingface.co/api/models/lab/model/commits/" + "b" * 40,
    ],
)
def test_legacy_history_links_cannot_change_origin_identity_kind_or_revision(url):
    hf = client(
        lambda _: httpx.Response(
            200, json=[], headers={"link": f'<{url}?p=1&limit=50>; rel="next"'}
        )
    )
    assert hf.history_page("lab/model", "a" * 40, "commits").outcome == (
        "invalid_continuation"
    )
    assert hf.requests == 1


@pytest.mark.parametrize(
    ("cursor", "query"),
    [
        ("hf-commits-page:v1:1:50", "p=1&limit=50"),
        ("hf-commits-page:v1:2:50", "p=1&limit=50"),
        ("hf-commits-page:v1:1:50", "p=3&limit=50"),
        ("hf-commits-page:v1:1:50", "p=2&limit=100"),
        ("hf-commits-page:v1:1:50", "cursor=opaque"),
        ("opaque", "p=1&limit=50"),
        ("opaque", "cursor=opaque"),
        (None, "cursor=hf-commits-page%3Av1%3A1%3A50"),
    ],
)
def test_history_rejects_protocol_switches_and_looping_continuations(cursor, query):
    link = f'<https://huggingface.co/api/models/lab/model/commits/{"a" * 40}?{query}>; rel="next"'
    hf = client(lambda _: httpx.Response(200, json=[], headers={"link": link}))
    assert hf.history_page("lab/model", "a" * 40, "commits", cursor).outcome == (
        "invalid_continuation"
    )


@pytest.mark.parametrize(
    ("kind", "token"),
    [
        ("commits", "hf-commits-page:v2:1:50"),
        ("commits", "hf-commits-page:v1:0:50"),
        ("commits", "hf-commits-page:v1:100001:50"),
        ("commits", "hf-commits-page:v1:1:101"),
        ("commits", "hf-commits-page:v1:01:50"),
        ("tree", "hf-commits-page:v1:1:50"),
    ],
)
def test_invalid_internal_history_page_tokens_never_reach_transport(kind, token):
    hf = client(lambda _: pytest.fail("unexpected request"))
    assert hf.history_page("lab/model", "a" * 40, kind, token).outcome == (
        "invalid_continuation"
    )
    assert hf.requests == 0


@pytest.mark.parametrize("kind", ["commits", "tree"])
def test_history_rejects_duplicate_next_links_and_legacy_tree_pages(kind):
    url = f'https://huggingface.co/api/models/lab/model/{kind}/{"a" * 40}'
    link = f'<{url}?cursor=one>; rel="next", <{url}?cursor=two>; rel="next"'
    hf = client(lambda _: httpx.Response(200, json=[], headers={"link": link}))
    assert hf.history_page("lab/model", "a" * 40, kind).outcome == (
        "invalid_continuation"
    )
    if kind == "tree":
        hf = client(
            lambda _: httpx.Response(
                200, json=[], headers={"link": f'<{url}?p=1&limit=50>; rel="next"'}
            )
        )
        assert hf.history_page("lab/model", "a" * 40, kind).outcome == (
            "invalid_continuation"
        )


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


def test_creation_order_is_explicit_and_legacy_modification_order_is_preserved():
    seen = []

    def response(request):
        seen.append(request.url.params["sort"])
        return httpx.Response(
            200,
            json=[
                {
                    "id": "lab/model",
                    "author": "lab",
                    "createdAt": "2026-09-01T00:00:00Z",
                }
            ],
        )

    hf = client(response)
    assert hf.list_page("lab", sort="createdAt").outcome == "ok"
    assert hf.list_page("lab").outcome == "ok"
    assert seen == ["createdAt", "lastModified"]


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


def test_organization_socials_remains_source_claim_with_identity_validation():
    hf = client(lambda request: httpx.Response(
        200, json={"org": "Other", "socialHandles": {"twitter": "someone"}}
    ))
    assert hf.organization_socials("lab").outcome == "identity_mismatch"
    assert hf.requests == 1
    hf = client(lambda request: httpx.Response(
        200, json={"org": "Lab", "socialHandles": {"twitter": "someone"}}
    ))
    assert hf.organization_socials("lab").outcome == "ok"
    assert hf.organization_socials("bad/path").outcome == "malformed"
    assert hf.requests == 1


def test_socials_fall_back_to_user_only_after_organization_not_found():
    calls = []
    def respond(request):
        calls.append(request.url.path)
        if "/organizations/" in request.url.path:
            return httpx.Response(404)
        return httpx.Response(200, json={"user": "Lab", "socialHandles": {"twitter": "owner"}})
    hf = client(respond)
    result = hf.organization_socials("lab")
    assert result.outcome == "ok" and result.payload["user"] == "Lab"
    assert calls == ["/api/organizations/lab/socials", "/api/users/lab/socials"]
    assert len(result.attempts) == hf.requests == 2
    hf = client(lambda _request: httpx.Response(403))
    assert hf.organization_socials("lab").outcome == "forbidden"
    assert hf.requests == 1
    hf = client(lambda request: httpx.Response(404) if "/organizations/" in request.url.path
                else httpx.Response(200, json={"user": "other", "socialHandles": {}}))
    assert hf.organization_socials("lab").outcome == "identity_mismatch"
    assert hf.requests == 2


def test_client_credentials_are_not_sent():
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(200, json={"id": "lab/model"})

    transport = httpx.Client(
        transport=httpx.MockTransport(respond),
        auth=("user", "secret"),
        headers={
            "Authorization": "Bearer secret",
            "X-Api-Key": "test-only-other-app-key",
        },
        cookies={"session": "secret"},
        params={"access_token": "test-only-other-app-key"},
    )
    hf = HFMetadataClient(transport, max_requests=1, max_seconds=10)
    assert hf.model_group("lab/model", "detail").outcome == "ok"
    assert "authorization" not in seen[0].headers
    assert "cookie" not in seen[0].headers
    assert "x-api-key" not in seen[0].headers
    assert "access_token" not in seen[0].url.params


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


def test_rate_limit_reset_controls_retry_delay():
    responses = iter(
        [
            httpx.Response(429, headers={"ratelimit": '"api";r=0;t=40'}),
            httpx.Response(200, json={"id": "lab/model"}),
        ]
    )
    sleeps = []
    hf = client(lambda r: next(responses))
    hf.sleep = sleeps.append
    assert hf.download_counts("lab/model").outcome == "ok"
    assert sum(sleeps) >= 40


def test_account_counts_rejects_wrong_identity():
    hf = client(
        lambda r: httpx.Response(200, json={"name": "other", "numFollowers": 12})
    )
    assert hf.account_counts("lab", "organization").outcome == "identity_mismatch"
