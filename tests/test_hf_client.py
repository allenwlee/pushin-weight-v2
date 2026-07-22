# {{AGENT_ATTRIBUTION}}
"""Tests for x_monitor.hf_client — HF Hub HTTP contract.

All network is mocked via httpx.MockTransport; no live HF calls.
"""

from __future__ import annotations

import httpx
import pytest

from x_monitor import hf_client


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


# --- auth headers ------------------------------------------------------


def test_hf_headers_anonymous(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    assert "Authorization" not in hf_client.hf_headers()


def test_hf_headers_authed(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "tok-123")
    assert hf_client.hf_headers()["Authorization"] == "Bearer tok-123"


# --- list_models_by_org: pagination ------------------------------------


def test_list_models_by_org_paginates(monkeypatch):
    monkeypatch.setattr(hf_client, "_sleep", lambda s: None)
    seen_cursors = []

    def handler(req):
        assert req.url.params.get("author") == "deepseek-ai"
        cursor = req.url.params.get("cursor")
        seen_cursors.append(cursor)
        if cursor is None:
            body = [{"id": "deepseek-ai/m1"}, {"id": "deepseek-ai/m2"}]
            return httpx.Response(
                200,
                json=body,
                headers={
                    "link": '<https://huggingface.co/api/models?author=deepseek-ai&cursor=NEXT>; rel="next"'
                },
            )
        body = [{"id": "deepseek-ai/m3"}]
        return httpx.Response(200, json=body)  # no next → stop

    models = hf_client.list_models_by_org("deepseek-ai", client=_client(handler), limit=2)
    assert [m["id"] for m in models] == ["deepseek-ai/m1", "deepseek-ai/m2", "deepseek-ai/m3"]
    assert seen_cursors == [None, "NEXT"]


def test_list_models_by_org_empty():
    def handler(req):
        return httpx.Response(200, json=[])

    assert hf_client.list_models_by_org("empty-org", client=_client(handler)) == []


def test_list_models_by_org_stops_without_next_link(monkeypatch):
    """A full page with no rel=next link stops (no infinite loop)."""
    monkeypatch.setattr(hf_client, "_sleep", lambda s: None)
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(200, json=[{"id": "o/m1"}, {"id": "o/m2"}])

    models = hf_client.list_models_by_org("o", client=_client(handler), limit=2)
    assert len(models) == 2
    assert calls["n"] == 1


def test_list_models_by_org_breaks_on_repeating_cursor(monkeypatch):
    """A server that always emits the SAME rel=next cursor must not loop."""
    monkeypatch.setattr(hf_client, "_sleep", lambda s: None)
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(
            200,
            json=[{"id": "o/m1"}, {"id": "o/m2"}],
            headers={"link": '<https://huggingface.co/api/models?author=o&cursor=SAME>; rel="next"'},
        )

    models = hf_client.list_models_by_org("o", client=_client(handler), limit=2)
    # A stuck cursor is detectable only after it repeats once → bounded at 2
    # pages (not the _MAX_PAGES=1000 cap), proving the guard terminates the loop.
    assert calls["n"] == 2
    assert len(models) == 4  # two identical pages before the guard broke


def test_list_models_by_org_max_cap(monkeypatch):
    monkeypatch.setattr(hf_client, "_sleep", lambda s: None)

    def handler(req):
        return httpx.Response(200, json=[{"id": f"o/m{i}"} for i in range(5)])

    models = hf_client.list_models_by_org("o", client=_client(handler), limit=10, max=2)
    assert [m["id"] for m in models] == ["o/m0", "o/m1"]


# --- hf_get: retry / error contract ------------------------------------


def test_hf_get_retries_on_500_then_succeeds(monkeypatch):
    monkeypatch.setattr(hf_client, "_sleep", lambda s: None)
    state = {"n": 0}

    def handler(req):
        state["n"] += 1
        if state["n"] == 1:
            return httpx.Response(500, text="boom")
        return httpx.Response(200, json={"ok": True})

    data, err = hf_client.hf_get("/models/x", client=_client(handler), retries=3)
    assert data == {"ok": True}
    assert err is None
    assert state["n"] == 2


def test_hf_get_404_returns_not_found_no_retry(monkeypatch):
    monkeypatch.setattr(hf_client, "_sleep", lambda s: None)
    state = {"n": 0}

    def handler(req):
        state["n"] += 1
        return httpx.Response(404, text="nf")

    data, err = hf_client.hf_get("/models/x", client=_client(handler), retries=3)
    assert data is None
    assert err == "not_found"
    assert state["n"] == 1  # 404 never retries


def test_hf_get_persistent_500_exhausts(monkeypatch):
    monkeypatch.setattr(hf_client, "_sleep", lambda s: None)
    state = {"n": 0}

    def handler(req):
        state["n"] += 1
        return httpx.Response(500, text="boom")

    data, err = hf_client.hf_get("/models/x", client=_client(handler), retries=2)
    assert data is None
    assert err == "http_500"
    assert state["n"] == 2


# --- get_model / search_organizations ----------------------------------


def test_get_model_returns_dict():
    def handler(req):
        assert req.url.path == "/api/models/org/repo"
        return httpx.Response(200, json={"id": "org/repo", "downloads": 5})

    m = hf_client.get_model("org/repo", client=_client(handler))
    assert m["id"] == "org/repo"
    assert m["downloads"] == 5


def test_get_model_404_returns_none():
    def handler(req):
        return httpx.Response(404)

    assert hf_client.get_model("org/missing", client=_client(handler)) is None


def test_search_organizations_returns_list():
    def handler(req):
        assert req.url.path == "/api/organizations"
        assert req.url.params.get("search") == "Qwen"
        return httpx.Response(200, json=[{"name": "Qwen"}])

    res = hf_client.search_organizations("Qwen", client=_client(handler))
    assert res == [{"name": "Qwen"}]


def test_search_organizations_returns_empty_on_error():
    """A failed search (404/5xx) returns [] rather than raising."""
    client = _client(lambda req: httpx.Response(404))
    assert hf_client.search_organizations("Anything", client=client) == []


# --- org_has_models sanity probe ---------------------------------------


def test_org_has_models_true():
    def handler(req):
        return httpx.Response(
            200, json=[{"id": "deepseek-ai/x", "author": "deepseek-ai"}]
        )

    ok, sample = hf_client.org_has_models("deepseek-ai", client=_client(handler))
    assert ok is True
    assert len(sample) == 1


def test_org_has_models_false_when_empty():
    def handler(req):
        return httpx.Response(200, json=[])

    ok, sample = hf_client.org_has_models("deepseek-ai", client=_client(handler))
    assert ok is False
    assert sample == []


def test_org_has_models_false_on_author_mismatch():
    """Silent-fallback guard: models returned for a different namespace → not ok."""
    def handler(req):
        return httpx.Response(200, json=[{"id": "other/x", "author": "other"}])

    ok, _ = hf_client.org_has_models("deepseek-ai", client=_client(handler))
    assert ok is False


def test_org_has_models_true_via_id_namespace():
    """author absent but the id namespace matches → ok (the gate's fallback path)."""
    def handler(req):
        return httpx.Response(200, json=[{"id": "deepseek-ai/x"}])  # no author

    ok, _ = hf_client.org_has_models("deepseek-ai", client=_client(handler))
    assert ok is True
