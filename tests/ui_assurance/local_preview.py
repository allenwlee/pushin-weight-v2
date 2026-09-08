"""Loopback-only transport for the fixture-backed local performance preview."""

from __future__ import annotations

import hashlib
import http.server
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Self
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

UPSTREAM_ORIGIN: Final = "http://127.0.0.1:8763"
LISTEN_HOST: Final = "127.0.0.1"
LISTEN_PORT: Final = 8764
MAX_ASSET_BYTES: Final = 2_000_000


@dataclass(frozen=True)
class PinnedAsset:
    source_url: str
    download_url: str
    local_path: str
    filename: str
    sha256: str
    content_type: str = "application/javascript; charset=utf-8"


PINNED_ASSETS: Final = (
    PinnedAsset(
        source_url="https://unpkg.com/htmx.org@1.9.10",
        download_url="https://unpkg.com/htmx.org@1.9.10/dist/htmx.min.js",
        local_path="/__bridgewright_assets/htmx-1.9.10.js",
        filename="htmx-1.9.10.js",
        sha256="b3bdcf5c741897a53648b1207fff0469a0d61901429ba1f6e88f98ebd84e669e",
    ),
    PinnedAsset(
        source_url="https://unpkg.com/chart.js@4.4.0",
        download_url="https://unpkg.com/chart.js@4.4.0/dist/chart.umd.js",
        local_path="/__bridgewright_assets/chart-4.4.0.js",
        filename="chart-4.4.0.js",
        sha256="321e3a3fa98da4aaa957d10be57cbb514de0989eed8f9d726b5d05902cd01904",
    ),
)
_ASSETS_BY_PATH: Final = {asset.local_path: asset for asset in PINNED_ASSETS}


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


_NO_REDIRECT_OPENER = build_opener(_RejectRedirects())


def _cache_root() -> Path:
    return Path(__file__).resolve().parents[2] / ".pytest-tmp" / "local-preview-assets"


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_asset(asset: PinnedAsset, cache_dir: Path) -> bytes:
    path = cache_dir / asset.filename
    if path.is_file():
        payload = path.read_bytes()
        if _digest(payload) == asset.sha256:
            return payload
        path.unlink()

    request = Request(
        asset.download_url, headers={"User-Agent": "pushinweight-local-preview/1"}
    )
    try:
        with _NO_REDIRECT_OPENER.open(request, timeout=20) as response:
            payload = response.read(MAX_ASSET_BYTES + 1)
    except (HTTPError, URLError, TimeoutError) as error:
        raise RuntimeError(
            f"could not fetch pinned local-preview asset: {asset.filename}"
        ) from error
    if len(payload) > MAX_ASSET_BYTES or _digest(payload) != asset.sha256:
        raise RuntimeError(
            f"pinned local-preview asset identity mismatch: {asset.filename}"
        )
    path.write_bytes(payload)
    return payload


def load_pinned_assets(cache_dir: Path | None = None) -> dict[str, bytes]:
    """Load exact public asset bytes, using only the task-scoped cache."""

    directory = cache_dir or _cache_root()
    directory.mkdir(parents=True, exist_ok=True)
    return {asset.local_path: _read_asset(asset, directory) for asset in PINNED_ASSETS}


def rewrite_home_html(payload: bytes) -> bytes:
    """Replace only the two declared external script URLs in a homepage body."""

    text = payload.decode("utf-8")
    rewritten = text
    for asset in PINNED_ASSETS:
        source = f'src="{asset.source_url}"'
        replacement = f'src="{asset.local_path}"'
        count = text.count(source)
        if count != 1:
            raise ValueError(
                f"expected exactly one pinned script URL: {asset.source_url}"
            )
        rewritten = rewritten.replace(source, replacement)
    if "https://unpkg.com/" in rewritten:
        raise ValueError("unexpected unpkg script URL in homepage")
    return rewritten.encode("utf-8")


def _loopback_origin(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.port is None:
        raise ValueError(
            "local preview upstream must be an explicit 127.0.0.1 HTTP origin"
        )
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("local preview upstream must be an origin")
    return value.rstrip("/")


class LocalPreviewServer:
    """A tiny GET/HEAD-only proxy with two locally served pinned assets."""

    def __init__(
        self,
        *,
        assets: dict[str, bytes],
        upstream_origin: str = UPSTREAM_ORIGIN,
        host: str = LISTEN_HOST,
        port: int = LISTEN_PORT,
    ) -> None:
        if host != LISTEN_HOST:
            raise ValueError("local preview listener must bind 127.0.0.1")
        self.assets = assets
        self.upstream_origin = _loopback_origin(upstream_origin)
        self._server = http.server.ThreadingHTTPServer((host, port), self._handler())
        self._thread: threading.Thread | None = None

    @property
    def origin(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def _handler(self) -> type[http.server.BaseHTTPRequestHandler]:
        assets = self.assets
        upstream_origin = self.upstream_origin

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, _format: str, *_args: object) -> None:
                return

            def do_GET(self) -> None:
                self._respond(include_body=True)

            def do_HEAD(self) -> None:
                self._respond(include_body=False)

            def _respond(self, *, include_body: bool) -> None:
                parsed = urlsplit(self.path)
                if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
                    self.send_error(400, "invalid local-preview path")
                    return
                if parsed.path in _ASSETS_BY_PATH:
                    asset = _ASSETS_BY_PATH[parsed.path]
                    payload = assets.get(parsed.path)
                    if payload is None or _digest(payload) != asset.sha256:
                        self.send_error(503, "pinned local-preview asset unavailable")
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", asset.content_type)
                    self.send_header("Content-Length", str(len(payload)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    if include_body:
                        self.wfile.write(payload)
                    return

                request = Request(
                    f"{upstream_origin}{self.path}",
                    method="GET" if include_body else "HEAD",
                    headers={
                        name: value
                        for name, value in self.headers.items()
                        if name.lower()
                        in {"accept", "accept-language", "cookie", "if-modified-since"}
                    },
                )
                try:
                    with _NO_REDIRECT_OPENER.open(request, timeout=20) as response:
                        body = response.read() if include_body else b""
                        content_type = response.headers.get("Content-Type", "")
                        if (
                            parsed.path == "/"
                            and content_type.lower().startswith("text/html")
                            and include_body
                        ):
                            try:
                                body = rewrite_home_html(body)
                            except (UnicodeDecodeError, ValueError):
                                self.send_error(
                                    502, "local-preview home rewrite rejected"
                                )
                                return
                        self.send_response(response.status)
                        for name in (
                            "Content-Type",
                            "Cache-Control",
                            "Last-Modified",
                            "ETag",
                            "Location",
                            "X-Bridgewright-Revision",
                        ):
                            value = response.headers.get(name)
                            if value:
                                self.send_header(name, value)
                        content_length = (
                            len(body)
                            if include_body
                            else response.headers.get("Content-Length", "0")
                        )
                        self.send_header("Content-Length", content_length)
                        self.end_headers()
                        if include_body:
                            self.wfile.write(body)
                except HTTPError as error:
                    self.send_error(error.code, "local-preview upstream response")
                except (URLError, TimeoutError):
                    self.send_error(502, "local-preview upstream unavailable")

        return Handler

    def start(self) -> LocalPreviewServer:
        if self._thread is None:
            self._thread = threading.Thread(
                target=self._server.serve_forever, daemon=True
            )
            self._thread.start()
        return self

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def __enter__(self) -> Self:
        return self.start()

    def __exit__(self, *_args: object) -> None:
        self.close()


def start_local_preview(cache_dir: Path | None = None) -> LocalPreviewServer:
    """Start the fixed 127.0.0.1:8764 preview after loading pinned bytes."""

    return LocalPreviewServer(assets=load_pinned_assets(cache_dir)).start()
