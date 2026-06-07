# {{AGENT_ATTRIBUTION}}
"""Thin wrapper around automation-lab/twitter-scraper (R16, D5, D6)."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import requests

from .cookies import CookieMissingError, load_cookies

log = logging.getLogger(__name__)


APIFY_BASE = "https://api.apify.com/v2"
DEFAULT_ACTOR = "automation-lab/twitter-scraper"

# A known-active handle used by the cookie probe search. R19: not just file
# existence — we must validate cookies are ACCEPTED by X via a 1-tweet probe.
PROBE_HANDLE = "MiniMaxAI"


class ApifyAuthError(RuntimeError):
    """Raised on HTTP 401 (cookies rejected or token bad)."""


class ApifyRateLimitError(RuntimeError):
    """Raised on HTTP 429 (caller should retry with backoff)."""


class ApifyServerError(RuntimeError):
    """Raised on HTTP 5xx."""


@dataclass
class ApifyClient:
    token: str
    actor: str = DEFAULT_ACTOR
    timeout_s: int = 90
    max_retries: int = 2

    @classmethod
    def from_env(cls, actor: str = DEFAULT_ACTOR) -> "ApifyClient":
        token = os.environ.get("APIFY_API_TOKEN")
        if not token:
            raise CookieMissingError("APIFY_API_TOKEN not in environment")
        return cls(token=token, actor=actor)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{APIFY_BASE}/acts/{self.actor}/{path}"
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                r = requests.post(
                    url,
                    json=body,
                    headers=self._headers(),
                    timeout=self.timeout_s,
                )
            except requests.RequestException as e:
                last_exc = e
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)
                    continue
                raise
            if r.status_code == 401:
                raise ApifyAuthError(f"Apify auth failed: {r.text[:200]}")
            if r.status_code == 429:
                if attempt < self.max_retries:
                    time.sleep(2 ** (attempt + 2))
                    continue
                raise ApifyRateLimitError(f"Apify rate limit: {r.text[:200]}")
            if 500 <= r.status_code < 600:
                last_exc = ApifyServerError(f"Apify 5xx: {r.status_code}")
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)
                    continue
                raise last_exc
            if r.status_code >= 400:
                raise RuntimeError(f"Apify error {r.status_code}: {r.text[:200]}")
            return r.json()
        if last_exc:
            raise last_exc
        raise RuntimeError("Apify call failed without a recorded exception")

    def _get_run(self, run_id: str) -> dict[str, Any]:
        url = f"{APIFY_BASE}/actor-runs/{run_id}"
        r = requests.get(url, headers=self._headers(), timeout=self.timeout_s)
        if r.status_code == 401:
            raise ApifyAuthError(f"Apify auth failed: {r.text[:200]}")
        r.raise_for_status()
        return r.json()

    def _wait_for_run(self, run_id: str, poll_s: int = 3, max_wait_s: int = 180) -> dict[str, Any]:
        elapsed = 0
        while elapsed < max_wait_s:
            data = self._get_run(run_id)
            status = data.get("status")
            if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
                return data
            time.sleep(poll_s)
            elapsed += poll_s
        raise TimeoutError(f"Apify run {run_id} did not finish in {max_wait_s}s")

    def _fetch_dataset(self, dataset_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        url = f"{APIFY_BASE}/datasets/{dataset_id}/items"
        params: dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit
        r = requests.get(url, headers=self._headers(), params=params, timeout=self.timeout_s)
        if r.status_code == 401:
            raise ApifyAuthError(f"Apify auth failed: {r.text[:200]}")
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []

    def run_search(
        self,
        query: str,
        max_results: int = 50,
        since: str | None = None,
        cookies: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Run an X advanced-search query via the actor's search mode.

        `since` is an ISO date string (YYYY-MM-DD) passed as the search
        `since:` filter — R-institutional learning: time-bound cursors are
        robust to new accounts.
        """
        body: dict[str, Any] = {
            "searchTerms": [query],
            "maxItems": max_results,
            "mode": "search",
        }
        if since:
            body["since"] = since
        if cookies:
            body["twitterCookies"] = [
                {"name": "auth_token", "value": cookies["auth_token"]},
                {"name": "ct0", "value": cookies["ct0"]},
            ]
        run = self._post("run-sync", body)
        run_id = run.get("id")
        if not run_id:
            return []
        ds = run.get("defaultDatasetId")
        if ds:
            return self._fetch_dataset(ds, limit=max_results)
        # No dataset yet — wait for the run, then fetch.
        finished = self._wait_for_run(run_id)
        ds = finished.get("defaultDatasetId")
        if not ds:
            return []
        return self._fetch_dataset(ds, limit=max_results)

    def run_followers(
        self,
        handle: str,
        max_results: int = 200,
        cookies: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Run a profile-followers scrape for one handle.

        D6: gated on first-call success. If this fails, the operator
        degrades to the R12 'official + commenters' spine.
        """
        body: dict[str, Any] = {
            "mode": "followers",
            "handles": [handle],
            "maxItems": max_results,
        }
        if cookies:
            body["twitterCookies"] = [
                {"name": "auth_token", "value": cookies["auth_token"]},
                {"name": "ct0", "value": cookies["ct0"]},
            ]
        run = self._post("run-sync", body)
        run_id = run.get("id")
        if not run_id:
            return []
        ds = run.get("defaultDatasetId")
        if ds:
            items = self._fetch_dataset(ds, limit=max_results)
            return [_normalize_follower(it) for it in items]
        finished = self._wait_for_run(run_id)
        ds = finished.get("defaultDatasetId")
        if not ds:
            return []
        items = self._fetch_dataset(ds, limit=max_results)
        return [_normalize_follower(it) for it in items]

    def probe_cookie(
        self,
        cookies: dict[str, str] | None = None,
        handle: str = PROBE_HANDLE,
    ) -> bool:
        """Validate the cookies are accepted by X (not just present on disk).

        Runs a 1-tweet search against a known-active handle. Returns True
        iff 200 + >=1 result. False on 401 OR 200 + 0 results.
        """
        if cookies is None:
            try:
                cookies = load_cookies()
            except CookieMissingError as e:
                log.warning("probe_cookie: %s", e)
                return False
        try:
            items = self.run_search(f"from:{handle}", max_results=5, cookies=cookies)
        except ApifyAuthError:
            return False
        except (ApifyRateLimitError, ApifyServerError, requests.RequestException):
            # Transient errors are NOT a cookie-rot signal.
            return True
        except Exception:
            return False
        return len(items) >= 1


def _normalize_follower(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize Apify's follower response into {handle, display_name, follower_count}."""
    handle = (
        item.get("userName")
        or item.get("screen_name")
        or item.get("handle")
        or ""
    )
    display_name = item.get("name") or item.get("display_name") or ""
    follower_count = (
        item.get("followers_count")
        or item.get("followerCount")
        or item.get("followers")
        or 0
    )
    return {
        "handle": str(handle),
        "display_name": str(display_name),
        "follower_count": int(follower_count) if follower_count else 0,
    }
