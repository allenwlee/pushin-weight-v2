from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts.ollija.render import RenderDeployment
from scripts.ollija.verification import (
    BrowserObservation,
    RouteObservation,
    VerificationError,
    verify_production,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SHA = "a" * 40
NOW = datetime(2026, 8, 14, 5, 30, tzinfo=UTC)


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
