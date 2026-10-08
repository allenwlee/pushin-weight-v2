from copy import deepcopy

import httpx
import pytest

from scripts.benchmark_download_collector.sources import (
    ARENA_URL,
    OPENROUTER_URL,
    Budget,
    SourceError,
    arena,
    openrouter,
)


def budget(handler, **kwargs):
    return Budget(
        httpx.Client(
            transport=httpx.MockTransport(handler),
            headers={"Authorization": "inherited-secret"},
            cookies={"session": "cookie"},
        ),
        sleep=lambda _: None,
        **kwargs,
    )


def arena_row(model="alpha-1", date="2026-10-01"):
    return {
        "model_name": model,
        "leaderboard_publish_date": date,
        "category": "overall",
        "rating": 1400.0,
        "rating_lower": 1390.0,
        "rating_upper": 1410.0,
        "vote_count": 4932.0,
    }


def arena_page(rows, total=None, **kwargs):
    return {
        "num_rows_total": len(rows) if total is None else total,
        "partial": False,
        "rows": [
            {"row_idx": i, "row": row, "truncated_cells": []}
            for i, row in enumerate(rows)
        ],
        **kwargs,
    }


def or_payload(rows=None):
    return {
        "data": rows
        if rows is not None
        else [
            {
                "date": "2026-10-01",
                "model_permaslug": "maker/alpha-1",
                "total_tokens": "9007199254740993",
            },
            {
                "date": "2026-10-01",
                "model_permaslug": "maker/alpha-1:free",
                "total_tokens": "23",
            },
            {"date": "2026-10-01", "model_permaslug": "other", "total_tokens": "98"},
        ],
        "meta": {
            "version": "v1",
            "as_of": "2026-10-02T03:00:00Z",
            "start_date": "2026-10-01",
            "end_date": "2026-10-01",
        },
    }


def test_arena_paginates_exactly_and_accepts_official_float64_votes():
    requests = []

    def respond(request):
        requests.append(request)
        assert (
            "authorization" not in request.headers and "cookie" not in request.headers
        )
        offset = int(request.url.params["offset"])
        return httpx.Response(
            200,
            json=arena_page(
                [
                    arena_row(f"model-{i}")
                    for i in range(offset, min(offset + 100, 101))
                ],
                total=101,
            ),
        )

    result = arena(budget(respond), "2026-10-01", "2026-10-02", history=True)
    assert len(result["rows"]) == 101
    assert [r.url.params["offset"] for r in requests] == ["0", "100"]
    assert requests[0].url.params["config"] == "text"
    assert "\"category\"='overall'" in requests[0].url.params["where"]


@pytest.mark.parametrize(
    "problem",
    [
        "duplicate",
        "truncated",
        "partial",
        "nan",
        "negative_votes",
        "wrong_category",
        "changed_total",
        "empty_page",
        "page_cap",
    ],
)
def test_arena_rejects_incomplete_or_invalid_publications(problem):
    calls = 0

    def respond(request):
        nonlocal calls
        calls += 1
        result = arena_page([arena_row()], total=2)
        if problem == "truncated":
            result["rows"][0]["truncated_cells"] = ["model_name"]
        elif problem == "partial":
            result["partial"] = True
        elif problem == "nan":
            result["rows"][0]["row"]["rating"] = "NaN"
        elif problem == "negative_votes":
            result["rows"][0]["row"]["vote_count"] = -1
        elif problem == "wrong_category":
            result["rows"][0]["row"]["category"] = "coding"
        elif problem == "changed_total" and calls > 1:
            result["num_rows_total"] = 3
        elif problem == "empty_page":
            result["rows"] = []
        return httpx.Response(200, json=result)

    with pytest.raises(ValueError):
        arena(
            budget(respond),
            "2026-10-01",
            "2026-10-02",
            max_pages=1 if problem == "page_cap" else 5,
            history=True,
        )


@pytest.mark.parametrize("status,attempts", [(401, 1), (302, 1), (429, 3), (503, 3)])
def test_http_failures_respect_retry_and_credential_boundaries(status, attempts):
    calls = []

    def respond(request):
        calls.append(request)
        assert request.headers["authorization"] == "Bearer dedicated-key"
        assert "cookie" not in request.headers
        return httpx.Response(
            status,
            headers={"Location": "https://example.com/steal"},
            text="dedicated-key",
        )

    with pytest.raises(SourceError, match=f"http_{status}"):
        budget(respond).get(OPENROUTER_URL, {}, key="dedicated-key")
    assert len(calls) == attempts
    assert all(r.url.host == "openrouter.ai" for r in calls)


def test_global_budget_counts_hf_retries_before_next_provider():
    client = budget(lambda _: httpx.Response(503), max_requests=2)
    with pytest.raises(SourceError):
        client.hf_counts("maker/Alpha-1")
    assert client.remaining == 0
    with pytest.raises(SourceError, match="request_cap"):
        client.get(ARENA_URL, {})


@pytest.mark.parametrize(
    "content,error", [(b"xxx", "malformed_json"), (b"x" * 101, "response_size_cap")]
)
def test_bounded_body_and_malformed_json(content, error):
    with pytest.raises(SourceError, match=error):
        budget(lambda _: httpx.Response(200, content=content), max_bytes=100).get(
            ARENA_URL, {}
        )


def test_timeout_is_retried_within_budget():
    def respond(request):
        raise httpx.ReadTimeout("secret response", request=request)

    with pytest.raises(SourceError, match="request_error"):
        budget(respond, max_requests=1).get(ARENA_URL, {})


def test_hf_narrow_counter_read_keeps_all_time_optional_and_identity_exact():
    seen = []

    def respond(request):
        seen.append(request)
        assert (
            "authorization" not in request.headers and "cookie" not in request.headers
        )
        assert request.url.params.get_list("expand") == [
            "downloads",
            "downloadsAllTime",
            "likes",
        ]
        return httpx.Response(200, json={"id": "maker/Alpha-1", "downloads": 0})

    assert budget(respond).hf_counts("maker/Alpha-1")["downloads"] == 0
    assert len(seen) == 1
    with pytest.raises(SourceError, match="identity_mismatch"):
        budget(respond).hf_counts("maker/Alpha-2")


def test_openrouter_keeps_variants_exact_and_large_token_strings():
    result = openrouter(
        budget(lambda _: httpx.Response(200, json=or_payload())),
        "2026-10-01",
        "2026-10-01",
        key="test",
    )
    assert result["rows"][0]["total_tokens"] == "9007199254740993"
    assert result["rows"][1]["model_permaslug"] == "maker/alpha-1:free"
    assert result["rows"][-1]["model_permaslug"] == "other"


@pytest.mark.parametrize(
    "problem",
    [
        "missing_key",
        "duplicate",
        "negative",
        "wrong_date",
        "version",
        "metadata_range",
    ],
)
def test_openrouter_rejects_untrustworthy_totals(problem):
    payload = deepcopy(or_payload())
    if problem == "duplicate":
        payload["data"].append(payload["data"][0])
    elif problem == "negative":
        payload["data"][0]["total_tokens"] = "-10"
    elif problem == "wrong_date":
        payload["data"][0]["date"] = "2026-10-02"
    elif problem == "version":
        payload["meta"]["version"] = "v2"
    elif problem == "metadata_range":
        payload["meta"]["start_date"] = "2026-09-01"
    with pytest.raises(ValueError):
        openrouter(
            budget(lambda _: httpx.Response(200, json=payload)),
            "2026-10-01",
            "2026-10-01",
            key=None if problem == "missing_key" else "test",
        )


def test_current_utc_day_rejected_before_request():
    from datetime import date

    with pytest.raises(ValueError, match="completed"):
        openrouter(
            budget(lambda _: pytest.fail("no request expected")),
            "2026-10-01",
            "2026-10-01",
            key="test",
            today=date(2026, 10, 1),
        )


def test_latest_official_parquet_and_signed_cdn_redirect():
    import pyarrow as pa
    import pyarrow.parquet as pq

    output = pa.BufferOutputStream()
    non_overall = {**arena_row("coding-only"), "category": "coding"}
    pq.write_table(pa.Table.from_pylist([arena_row(), non_overall]), output)
    calls = []

    def respond(request):
        calls.append(request)
        assert (
            "authorization" not in request.headers and "cookie" not in request.headers
        )
        if len(calls) == 1:
            return httpx.Response(
                302,
                headers={
                    "location": "https://cas-bridge.xethub.hf.co/file?signature=public-signature"
                },
            )
        assert request.url.params["signature"] == "public-signature"
        return httpx.Response(200, content=output.getvalue().to_pybytes())

    result = arena(budget(respond), "2026-09-01", "2026-10-02")
    assert len(result["rows"]) == 1
    assert result["coverage"] == "latest_publication_only"
    assert len(result["artifact_sha256"]) == 64
    assert len(calls) == 2


@pytest.mark.parametrize(
    "target",
    [
        "http://cas-bridge.xethub.hf.co/file",
        "https://evil.example/file",
        "https://huggingface.co.evil.example/file",
        "https://user:password@huggingface.co/file",
    ],
)
def test_arena_rejects_redirect_outside_public_hf_cdn(target):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(302, headers={"location": target})

    with pytest.raises(ValueError, match="redirect"):
        arena(budget(respond), "2026-10-01", "2026-10-02")
    assert len(calls) == 1


def test_latest_file_retains_publication_after_openrouter_window():
    import pyarrow as pa
    import pyarrow.parquet as pq

    output = pa.BufferOutputStream()
    pq.write_table(pa.Table.from_pylist([arena_row()]), output)
    result = arena(
        budget(lambda _: httpx.Response(200, content=output.getvalue().to_pybytes())),
        "2026-09-01",
        "2026-09-30",
    )
    assert result["rows"] == [arena_row()]
    assert result["as_of"] == "2026-10-01"


def test_openrouter_accepts_small_population_without_other():
    payload = deepcopy(or_payload())
    payload["data"] = [r for r in payload["data"] if r["model_permaslug"] != "other"]
    result = openrouter(budget(lambda _: httpx.Response(200, json=payload)), "2026-10-01", "2026-10-01", key="test")
    assert result["rows"] == payload["data"]
