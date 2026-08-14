from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urljoin

import requests
import yaml

from .render import RenderDeployment


class VerificationError(ValueError):
    """Production could not be proven healthy and visibly correct."""


@dataclass(frozen=True, slots=True)
class RouteObservation:
    url: str
    status_code: int
    final_url: str


@dataclass(frozen=True, slots=True)
class BrowserObservation:
    final_url: str
    selector: str
    visible: bool
    text_fingerprint: str

    def to_receipt_payload(self) -> dict[str, str | bool]:
        return {
            "final_url": self.final_url,
            "selector": self.selector,
            "visible": self.visible,
            "text_fingerprint": self.text_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class ProductionVerification:
    deployments: tuple[RenderDeployment, ...]
    health: RouteObservation
    smoke: RouteObservation
    browser: BrowserObservation
    headline_model: str

    def to_receipt_payload(self) -> dict[str, object]:
        return {
            "deployments": [item.to_receipt_payload() for item in self.deployments],
            "health_passed": True,
            "health_status_code": self.health.status_code,
            "smoke_passed": True,
            "smoke_status_code": self.smoke.status_code,
            "headline_visible": self.browser.visible,
            "headline_browser": self.browser.to_receipt_payload(),
            "headline_model": self.headline_model,
        }


class BrowserProbe(Protocol):
    def observe_headline(
        self,
        *,
        url: str,
        selector: str,
        unavailable_text: str,
    ) -> BrowserObservation: ...


class PlaywrightBrowserProbe:
    """Exercise the real authenticated page with an ignored storage-state file."""

    def __init__(self, storage_state: Path) -> None:
        self.storage_state = storage_state.expanduser().resolve()

    def observe_headline(
        self,
        *,
        url: str,
        selector: str,
        unavailable_text: str,
    ) -> BrowserObservation:
        if not self.storage_state.is_file():
            raise VerificationError("production_browser_storage_state_missing")
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise VerificationError("playwright_unavailable") from exc

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(storage_state=str(self.storage_state))
                page = context.new_page()
                page.goto(url, wait_until="networkidle", timeout=60_000)
                locator = page.locator(selector).first
                locator.wait_for(state="visible", timeout=30_000)
                text = locator.inner_text().strip()
                final_url = page.url
                visible = locator.is_visible()
                browser.close()
        except VerificationError:
            raise
        except Exception as exc:
            raise VerificationError("production_browser_probe_failed") from exc

        if not visible or not text or unavailable_text.casefold() in text.casefold():
            raise VerificationError("production_headline_not_visible")
        return BrowserObservation(
            final_url=final_url,
            selector=selector,
            visible=True,
            text_fingerprint=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )


def probe_route(
    base_url: str,
    path: str,
    *,
    timeout_seconds: int = 30,
) -> RouteObservation:
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    try:
        response = requests.get(url, timeout=timeout_seconds, allow_redirects=True)
    except requests.RequestException as exc:
        raise VerificationError("production_http_probe_failed") from exc
    if response.status_code != 200:
        raise VerificationError(
            f"production_http_status_invalid:{response.status_code}"
        )
    return RouteObservation(
        url=url,
        status_code=response.status_code,
        final_url=response.url,
    )


def verify_dsv4_configuration(root: Path) -> str:
    try:
        application = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
        blueprint = yaml.safe_load((root / "render.yaml").read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise VerificationError("headline_configuration_unavailable") from exc
    if not isinstance(application, Mapping) or not isinstance(blueprint, Mapping):
        raise VerificationError("headline_configuration_invalid")
    headline = application.get("headline_narrative")
    if not isinstance(headline, Mapping):
        raise VerificationError("headline_configuration_invalid")
    if headline.get("provider") != "deepseek":
        raise VerificationError("headline_provider_not_deepseek")
    model = headline.get("model")
    if model != "deepseek-v4-pro":
        raise VerificationError("headline_model_not_dsv4")

    services = blueprint.get("services")
    if not isinstance(services, list):
        raise VerificationError("production_blueprint_invalid")
    worker = next(
        (
            item
            for item in services
            if isinstance(item, Mapping) and item.get("name") == "pushinweight-headlines"
        ),
        None,
    )
    if not isinstance(worker, Mapping):
        raise VerificationError("headline_worker_missing")
    env_vars = worker.get("envVars")
    if not isinstance(env_vars, list):
        raise VerificationError("headline_worker_environment_invalid")
    keyed = {
        str(item.get("key")): item
        for item in env_vars
        if isinstance(item, Mapping) and isinstance(item.get("key"), str)
    }
    if keyed.get("DEEPSEEK_API_KEY", {}).get("sync") is not False:
        raise VerificationError("headline_dsv4_credential_not_scoped")
    if keyed.get("X_MONITOR_HEADLINE_PROVIDER_CALLS_ENABLED", {}).get("value") != "True":
        raise VerificationError("headline_provider_calls_not_enabled")
    if "ANTHROPIC_API_KEY" in keyed:
        raise VerificationError("headline_anthropic_credential_forbidden")
    return str(model)


def verify_production(
    *,
    root: Path,
    candidate_sha: str,
    deployments: Sequence[RenderDeployment],
    base_url: str,
    health_path: str,
    smoke_path: str,
    headline_path: str,
    headline_selector: str,
    headline_unavailable_text: str,
    browser_probe: BrowserProbe,
) -> ProductionVerification:
    observed = tuple(deployments)
    if not observed:
        raise VerificationError("production_service_set_empty")
    if any(
        item.commit_sha != candidate_sha or item.status != "live"
        for item in observed
    ):
        raise VerificationError("production_service_set_not_exact_live_sha")
    model = verify_dsv4_configuration(root)
    health = probe_route(base_url, health_path)
    smoke = probe_route(base_url, smoke_path)
    headline_url = urljoin(base_url.rstrip("/") + "/", headline_path.lstrip("/"))
    browser = browser_probe.observe_headline(
        url=headline_url,
        selector=headline_selector,
        unavailable_text=headline_unavailable_text,
    )
    if not browser.visible:
        raise VerificationError("production_headline_not_visible")
    return ProductionVerification(
        deployments=observed,
        health=health,
        smoke=smoke,
        browser=browser,
        headline_model=model,
    )
