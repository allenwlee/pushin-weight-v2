from __future__ import annotations

import requests

from core.job_sources.http import SourceHttpClient, SourceHttpError


class FakeResponse:
    def __init__(self, status_code=200, *, headers=None, chunks=()):
        self.status_code = status_code
        self.headers = headers or {}
        self._chunks = chunks
        self.closed = False

    @property
    def is_redirect(self):
        return self.status_code in {301, 302, 303, 307, 308}

    @property
    def is_permanent_redirect(self):
        return self.status_code in {301, 308}

    def iter_content(self, *, chunk_size):
        assert chunk_size == 64 * 1024
        yield from self._chunks

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, responses):
        self.headers = {}
        self.responses = iter(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def _client(session, **kwargs):
    return SourceHttpClient(
        allowed_hosts=frozenset({"jobs.example.com"}),
        session=session,
        retries=kwargs.pop("retries", 0),
        **kwargs,
    )


def test_response_body_is_bounded_while_streaming():
    response = FakeResponse(chunks=(b"1234", b"5678"))
    session = FakeSession([response])

    try:
        _client(session, max_bytes=7).request("GET", "https://jobs.example.com/list")
    except SourceHttpError as exc:
        assert str(exc) == "upstream response exceeded size limit"
    else:
        raise AssertionError("oversized response was accepted")

    assert response.closed is True
    assert session.calls[0][2]["stream"] is True


def test_content_length_rejects_response_before_reading_chunks():
    response = FakeResponse(headers={"Content-Length": "9"}, chunks=(b"ignored",))

    try:
        _client(FakeSession([response]), max_bytes=8).request(
            "GET", "https://jobs.example.com/list"
        )
    except SourceHttpError as exc:
        assert str(exc) == "upstream response exceeded size limit"
    else:
        raise AssertionError("oversized Content-Length was accepted")

    assert response.closed is True


def test_redirect_to_unapproved_host_is_rejected_without_retrying_it(monkeypatch):
    response = FakeResponse(302, headers={"Location": "https://evil.example/jobs"})
    session = FakeSession([response])
    monkeypatch.setattr("core.job_sources.http.time.sleep", lambda _seconds: None)

    try:
        _client(session, retries=2).request("GET", "https://jobs.example.com/list")
    except SourceHttpError as exc:
        assert "refusing untrusted recruiting URL" in str(exc)
    else:
        raise AssertionError("unapproved redirect was followed")

    assert response.closed is True
    assert len(session.calls) == 1


def test_http_error_is_status_only_and_retries_are_bounded(monkeypatch):
    responses = [FakeResponse(503), FakeResponse(503), FakeResponse(503)]
    session = FakeSession(responses)
    monkeypatch.setattr("core.job_sources.http.time.sleep", lambda _seconds: None)

    try:
        _client(session, retries=2).request(
            "GET", "https://jobs.example.com/list?_csrf=secret-token"
        )
    except SourceHttpError as exc:
        assert str(exc) == "upstream returned HTTP 503"
        assert "secret-token" not in str(exc)
    else:
        raise AssertionError("HTTP 503 was accepted")

    assert len(session.calls) == 3
    assert all(response.closed for response in responses)


def test_request_exception_does_not_copy_url_or_secret_into_error():
    session = FakeSession(
        [requests.ConnectionError("failed https://jobs.example.com/?token=secret")]
    )

    try:
        _client(session).request("GET", "https://jobs.example.com/?token=secret")
    except SourceHttpError as exc:
        assert str(exc) == "upstream request failed (ConnectionError)"
        assert "secret" not in str(exc)
    else:
        raise AssertionError("request exception was accepted")
