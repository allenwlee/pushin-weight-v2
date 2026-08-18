from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urljoin, urlsplit

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


def _required_string(values: Mapping[str, object], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value.strip():
        raise VerificationError(f"production_verification_{key}_invalid")
    return value.strip()


def _same_origin_url(base_url: str, path: str, *, error_code: str) -> str:
    try:
        parsed_base = urlsplit(base_url)
        base_port = parsed_base.port
    except ValueError as exc:
        raise VerificationError(
            "production_verification_production_base_url_invalid"
        ) from exc
    try:
        parsed_path = urlsplit(path)
        stripped_path = urlsplit(path.lstrip("/"))
    except ValueError as exc:
        raise VerificationError(error_code) from exc
    if (
        parsed_base.scheme != "https"
        or not parsed_base.hostname
        or parsed_base.username
        or parsed_base.password
    ):
        raise VerificationError("production_verification_production_base_url_invalid")
    if (
        not path.startswith("/")
        or parsed_path.scheme
        or parsed_path.netloc
        or stripped_path.scheme
        or stripped_path.netloc
        or "\\" in path
        or any(ord(char) < 32 or ord(char) == 127 for char in path)
    ):
        raise VerificationError(error_code)
    url = urljoin(base_url.rstrip("/") + "/", path)
    parsed_url = urlsplit(url)
    if (
        parsed_url.scheme,
        parsed_url.hostname,
        parsed_url.port,
    ) != (
        parsed_base.scheme,
        parsed_base.hostname,
        base_port,
    ):
        raise VerificationError(error_code)
    return url


def production_browser_probe(
    verification: Mapping[str, object],
    *,
    storage_state: Path | None = None,
    browser_cdp_url: str | None = None,
) -> BrowserProbe:
    """Validate the production browser contract before production mutation."""

    base_url = _required_string(verification, "production_base_url")
    for key in ("health_path", "smoke_path", "headline_path"):
        _same_origin_url(
            base_url,
            _required_string(verification, key),
            error_code=f"production_verification_{key}_invalid",
        )
    _required_string(verification, "headline_selector")
    _required_string(verification, "headline_unavailable_text")

    storage_env = _required_string(verification, "browser_storage_state_env")
    configured_storage = os.environ.get(storage_env, "")
    selected_storage = storage_state or (
        Path(configured_storage) if configured_storage else None
    )
    cdp_env = _required_string(verification, "browser_cdp_url_env")
    configured_cdp = os.environ.get(cdp_env, "")
    selected_cdp = browser_cdp_url or configured_cdp or None
    if selected_storage is not None and selected_cdp is not None:
        raise VerificationError("production_browser_probe_selection_ambiguous")
    if selected_storage is None and selected_cdp is None:
        raise VerificationError("production_browser_session_missing")
    if selected_storage is not None:
        resolved_storage = selected_storage.expanduser().resolve()
        if not resolved_storage.is_file():
            raise VerificationError("production_browser_storage_state_missing")
        return PlaywrightBrowserProbe(resolved_storage)

    assert selected_cdp is not None
    parsed_cdp = urlsplit(selected_cdp)
    if parsed_cdp.scheme not in {"http", "https", "ws", "wss"} or not parsed_cdp.hostname:
        raise VerificationError("production_browser_cdp_url_invalid")
    return CdpBrowserProbe(selected_cdp)


def observe_configured_headline(
    verification: Mapping[str, object],
    browser_probe: BrowserProbe,
) -> BrowserObservation:
    base_url = _required_string(verification, "production_base_url")
    headline_path = _required_string(verification, "headline_path")
    return browser_probe.observe_headline(
        url=_same_origin_url(
            base_url,
            headline_path,
            error_code="production_verification_headline_path_invalid",
        ),
        selector=_required_string(verification, "headline_selector"),
        unavailable_text=_required_string(
            verification,
            "headline_unavailable_text",
        ),
    )


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


class CdpBrowserProbe:
    """Probe an authenticated browser without copying its session state."""

    def __init__(self, cdp_url: str) -> None:
        self.cdp_url = cdp_url

    def observe_headline(
        self,
        *,
        url: str,
        selector: str,
        unavailable_text: str,
    ) -> BrowserObservation:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise VerificationError("playwright_unavailable") from exc

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.connect_over_cdp(self.cdp_url)
                if not browser.contexts:
                    raise VerificationError("production_remote_browser_context_missing")
                page = browser.contexts[0].new_page()
                try:
                    page.goto(url, wait_until="networkidle", timeout=60_000)
                    locator = page.locator(selector).first
                    locator.wait_for(state="visible", timeout=30_000)
                    text = locator.inner_text().strip()
                    final_url = page.url
                    visible = locator.is_visible()
                finally:
                    page.close()
                # The remote browser owns its context and remains open.
        except VerificationError:
            raise
        except Exception as exc:
            raise VerificationError("production_remote_browser_probe_failed") from exc

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
    url = _same_origin_url(
        base_url,
        path,
        error_code="production_verification_route_path_invalid",
    )
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
    headline_url = _same_origin_url(
        base_url,
        headline_path,
        error_code="production_verification_headline_path_invalid",
    )
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
