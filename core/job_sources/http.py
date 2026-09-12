from __future__ import annotations

import time
from urllib.parse import urljoin, urlsplit

import requests


class SourceHttpError(RuntimeError):
    pass


class SourceHttpClient:
    """Small bounded HTTP client for public, preconfigured recruiting hosts."""

    def __init__(
        self,
        *,
        allowed_hosts: frozenset[str],
        session: requests.Session | None = None,
        timeout: tuple[float, float] = (5.0, 25.0),
        max_bytes: int = 12 * 1024 * 1024,
        retries: int = 2,
    ) -> None:
        self.allowed_hosts = allowed_hosts
        self.session = session or requests.Session()
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.retries = retries
        self.session.headers["User-Agent"] = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
        )

    def _validate(self, url: str) -> None:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in self.allowed_hosts:
            raise SourceHttpError("refusing untrusted recruiting URL")

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        current_url = url
        self._validate(current_url)
        for attempt in range(self.retries + 1):
            try:
                for _redirect in range(4):
                    self._validate(current_url)
                    response = self.session.request(
                        method,
                        current_url,
                        timeout=self.timeout,
                        allow_redirects=False,
                        stream=True,
                        **kwargs,
                    )
                    if response.is_redirect or response.is_permanent_redirect:
                        location = response.headers.get("Location")
                        if not location:
                            response.close()
                            raise SourceHttpError("redirect response omitted Location")
                        response.close()
                        current_url = urljoin(current_url, location)
                        self._validate(current_url)
                        if response.status_code == 303:
                            method, kwargs = "GET", {}
                        continue
                    if response.status_code == 429 or response.status_code >= 500:
                        response.close()
                        raise SourceHttpError(
                            f"upstream returned HTTP {response.status_code}"
                        )
                    if response.status_code >= 400:
                        response.close()
                        raise SourceHttpError(
                            f"upstream returned HTTP {response.status_code}"
                        )
                    if response.status_code >= 300:
                        response.close()
                        raise SourceHttpError(
                            f"upstream returned HTTP {response.status_code}"
                        )
                    content_length = response.headers.get("Content-Length")
                    if (
                        content_length
                        and content_length.isdigit()
                        and int(content_length) > self.max_bytes
                    ):
                        response.close()
                        raise SourceHttpError("upstream response exceeded size limit")
                    content = bytearray()
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        if not chunk:
                            continue
                        if len(content) + len(chunk) > self.max_bytes:
                            response.close()
                            raise SourceHttpError(
                                "upstream response exceeded size limit"
                            )
                        content.extend(chunk)
                    response._content = bytes(content)
                    response._content_consumed = True
                    return response
                raise SourceHttpError("upstream exceeded redirect limit")
            except requests.RequestException as exc:
                if attempt >= self.retries:
                    raise SourceHttpError(
                        f"upstream request failed ({type(exc).__name__})"
                    ) from exc
                time.sleep(0.25 * (2**attempt))
            except SourceHttpError:
                if attempt >= self.retries:
                    raise
                time.sleep(0.25 * (2**attempt))
        raise AssertionError("unreachable")

    def get_text(self, url: str, **kwargs) -> str:
        # Chinese ATS responses often omit or misstate their charset.
        return self.request("GET", url, **kwargs).content.decode("utf-8")

    def get_json(self, url: str, **kwargs):
        return self.request("GET", url, **kwargs).json()

    def post_json(self, url: str, payload: dict, **kwargs):
        return self.request("POST", url, json=payload, **kwargs).json()
