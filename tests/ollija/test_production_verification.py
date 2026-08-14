from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from scripts.ollija.render import RenderDeployment
from scripts.ollija.verification import (
    BrowserObservation,
    CdpBrowserProbe,
    RouteObservation,
    VerificationError,
    verify_production,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SHA = "a" * 40
NOW = datetime(2026, 8, 14, 5, 30, tzinfo=UTC)


def test_cdp_probe_observes_remote_page_without_closing_browser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed = []

    class Locator:
        first = None

        def wait_for(self, **kwargs):
            return None

        def inner_text(self):
            return "A real headline"

        def is_visible(self):
            return True

    locator = Locator()
    locator.first = locator

    class Page:
        url = "https://pushinweight-web.onrender.com/feed/"

        def goto(self, *args, **kwargs):
            return None

        def locator(self, selector):
            assert selector == "[data-pw-headline-body]"
            return locator

        def close(self):
            closed.append(True)

    class Browser:
        def __init__(self):
            self.contexts = [SimpleNamespace(new_page=lambda: Page())]

        def close(self):
            raise AssertionError("remote browser must remain open")

    class Chromium:
        def connect_over_cdp(self, cdp_url):
            assert cdp_url == "http://remote:9222"
            return Browser()

    class PlaywrightContext:
        chromium = Chromium()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    sync_api = ModuleType("playwright.sync_api")
    sync_api.sync_playwright = lambda: PlaywrightContext()
    playwright = ModuleType("playwright")
    monkeypatch.setitem(__import__("sys").modules, "playwright", playwright)
    monkeypatch.setitem(__import__("sys").modules, "playwright.sync_api", sync_api)

    observation = CdpBrowserProbe("http://remote:9222").observe_headline(
        url="https://pushinweight-web.onrender.com/feed/",
        selector="[data-pw-headline-body]",
        unavailable_text="Trend summary is unavailable.",
    )

    assert observation.visible is True
    assert closed == [True]


class _Browser:
    def observe_headline(self, *, url: str, selector: str, unavailable_text: str):
        return BrowserObservation(
            final_url=url,
            selector=selector,
            visible=True,
            text_fingerprint="f" * 64,
        )


def _deployment(sha: str = SHA) -> RenderDeployment:
    return RenderDeployment(
        resource_id="srv-web",
        deployment_id="dep-web",
        commit_sha=sha,
        status="live",
        created_at=NOW,
        finished_at=NOW,
    )


def test_production_verification_requires_exact_live_sha_visible_dom_and_dsv4(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scripts.ollija.verification.probe_route",
        lambda base, path: RouteObservation(
            url=base + path,
            status_code=200,
            final_url=base + path,
        ),
    )

    report = verify_production(
        root=REPO_ROOT,
        candidate_sha=SHA,
        deployments=[_deployment()],
        base_url="https://pushinweight-web.onrender.com",
        health_path="/accounts/login/",
        smoke_path="/accounts/login/",
        headline_path="/feed/",
        headline_selector="[data-pw-headline-body]",
        headline_unavailable_text="Trend summary is unavailable.",
        browser_probe=_Browser(),
    )

    assert report.headline_model == "deepseek-v4-pro"
    assert report.browser.visible is True


def test_wrong_sha_cannot_verify_even_when_browser_would_pass() -> None:
    with pytest.raises(VerificationError, match="exact_live_sha"):
        verify_production(
            root=REPO_ROOT,
            candidate_sha=SHA,
            deployments=[_deployment("b" * 40)],
            base_url="https://pushinweight-web.onrender.com",
            health_path="/accounts/login/",
            smoke_path="/accounts/login/",
            headline_path="/feed/",
            headline_selector="[data-pw-headline-body]",
            headline_unavailable_text="Trend summary is unavailable.",
            browser_probe=_Browser(),
        )
