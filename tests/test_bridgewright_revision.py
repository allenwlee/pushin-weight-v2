from __future__ import annotations

from django.http import HttpResponse
from django.test import RequestFactory

from project.revision import BridgewrightRevisionMiddleware, deployed_revision


def test_deployed_revision_prefers_render_commit(monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", "A" * 40)
    monkeypatch.setenv("BRIDGEWRIGHT_TARGET_REVISION", "b" * 40)
    assert deployed_revision() == "a" * 40


def test_deployed_revision_uses_local_full_sha_fallback(monkeypatch):
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    monkeypatch.setenv("BRIDGEWRIGHT_TARGET_REVISION", "B" * 40)
    assert deployed_revision() == "b" * 40


def test_deployed_revision_rejects_short_or_unsafe_values(monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", "not-a-revision")
    monkeypatch.setenv("BRIDGEWRIGHT_TARGET_REVISION", "c" * 40)
    assert deployed_revision() is None


def test_revision_header_is_scoped_to_homepage(monkeypatch):
    monkeypatch.setenv("BRIDGEWRIGHT_TARGET_REVISION", "c" * 40)
    factory = RequestFactory()
    middleware = BridgewrightRevisionMiddleware(lambda request: HttpResponse("ok"))

    home = middleware(factory.get("/?__bridgewright_revision_probe=before"))
    static = middleware(factory.get("/static/country-flags.svg"))

    assert home["X-Bridgewright-Revision"] == "c" * 40
    assert "X-Bridgewright-Revision" not in static
