from __future__ import annotations

import hashlib
import http.server
import threading
from contextlib import contextmanager
from typing import ClassVar
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from tests.ui_assurance import local_preview


class _Upstream(http.server.BaseHTTPRequestHandler):
    home = (
        b'<html><head><script src="https://unpkg.com/htmx.org@1.9.10" defer></script>'
        b'<script src="https://unpkg.com/chart.js@4.4.0" defer></script>'
        b'<script src="/static/app.js" defer></script></head><body>unchanged</body></html>'
    )
    methods: ClassVar[list[tuple[str, str]]] = []

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_GET(self) -> None:
        type(self).methods.append(("GET", self.path))
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/target")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(self.home)))
        self.end_headers()
        self.wfile.write(self.home)

    def do_HEAD(self) -> None:
        type(self).methods.append(("HEAD", self.path))
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(self.home)))
        self.end_headers()


@contextmanager
def _upstream():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Upstream)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _fake_assets(monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    payloads = (b"exact htmx fixture bytes", b"exact chart fixture bytes")
    assets = tuple(
        local_preview.PinnedAsset(
            source_url=f"https://unpkg.test/{name}",
            download_url=f"https://unpkg.test/{name}",
            local_path=f"/__bridgewright_assets/{name}",
            filename=name,
            sha256=hashlib.sha256(payload).hexdigest(),
        )
        for name, payload in zip(("htmx.js", "chart.js"), payloads, strict=True)
    )
    monkeypatch.setattr(local_preview, "PINNED_ASSETS", assets)
    monkeypatch.setattr(
        local_preview, "_ASSETS_BY_PATH", {asset.local_path: asset for asset in assets}
    )
    monkeypatch.setattr(
        _Upstream,
        "home",
        f'<script src="{assets[0].source_url}" defer></script>'
        f'<script src="{assets[1].source_url}" defer></script><body>unchanged</body>'.encode(),
    )
    return {
        asset.local_path: payload
        for asset, payload in zip(assets, payloads, strict=True)
    }


def test_rewrite_home_html_replaces_only_the_two_pinned_src_attributes() -> None:
    original = _Upstream.home
    rewritten = local_preview.rewrite_home_html(original)

    assert b'src="/__bridgewright_assets/htmx-1.9.10.js"' in rewritten
    assert b'src="/__bridgewright_assets/chart-4.4.0.js"' in rewritten
    assert b'<script src="/static/app.js" defer></script>' in rewritten
    assert (
        rewritten.replace(
            b'src="/__bridgewright_assets/htmx-1.9.10.js"',
            b'src="https://unpkg.com/htmx.org@1.9.10"',
        ).replace(
            b'src="/__bridgewright_assets/chart-4.4.0.js"',
            b'src="https://unpkg.com/chart.js@4.4.0"',
        )
        == original
    )


def test_rewrite_home_html_rejects_missing_or_unexpected_cdn_script() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        local_preview.rewrite_home_html(b"<html></html>")
    with pytest.raises(ValueError, match="unexpected unpkg"):
        local_preview.rewrite_home_html(
            _Upstream.home.replace(
                b"</head>",
                b'<script src="https://unpkg.com/unexpected.js"></script></head>',
            )
        )


def test_read_asset_uses_verified_cache_without_network(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asset = local_preview.PinnedAsset(
        source_url="https://unpkg.test/fixture.js",
        download_url="https://unpkg.test/fixture.js",
        local_path="/fixture.js",
        filename="fixture.js",
        sha256=hashlib.sha256(b"exact").hexdigest(),
    )
    (tmp_path / asset.filename).write_bytes(b"exact")
    monkeypatch.setattr(
        local_preview._NO_REDIRECT_OPENER,
        "open",
        lambda *_args, **_kwargs: pytest.fail("network"),
    )

    assert local_preview._read_asset(asset, tmp_path) == b"exact"


def test_read_asset_rejects_mismatched_download(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asset = local_preview.PinnedAsset(
        source_url="https://unpkg.test/fixture.js",
        download_url="https://unpkg.test/fixture.js",
        local_path="/fixture.js",
        filename="fixture.js",
        sha256=hashlib.sha256(b"exact").hexdigest(),
    )

    @contextmanager
    def wrong_bytes(*_args, **_kwargs):
        class Response:
            def read(self, _limit: int) -> bytes:
                return b"wrong"

        yield Response()

    monkeypatch.setattr(local_preview._NO_REDIRECT_OPENER, "open", wrong_bytes)
    with pytest.raises(RuntimeError, match="identity mismatch"):
        local_preview._read_asset(asset, tmp_path)


def test_preview_serves_verified_bytes_and_blocks_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assets = _fake_assets(monkeypatch)
    with _upstream() as upstream:
        _Upstream.methods = []
        _, upstream_port = upstream.server_address[:2]
        with local_preview.LocalPreviewServer(
            assets=assets, upstream_origin=f"http://127.0.0.1:{upstream_port}", port=0
        ) as preview:
            with local_preview._NO_REDIRECT_OPENER.open(
                f"{preview.origin}/", timeout=5
            ) as response:
                homepage = response.read()
            assert b"/__bridgewright_assets/htmx.js" in homepage
            assert b"unchanged" in homepage

            asset_path, expected = next(iter(assets.items()))
            with local_preview._NO_REDIRECT_OPENER.open(
                f"{preview.origin}{asset_path}", timeout=5
            ) as response:
                payload = response.read()
                assert response.headers["Cache-Control"] == "no-store"
            assert payload == expected

            with local_preview._NO_REDIRECT_OPENER.open(
                Request(f"{preview.origin}/", method="HEAD"), timeout=5
            ) as response:
                assert response.headers["Content-Length"] == str(len(_Upstream.home))
                assert response.read() == b""
            with pytest.raises(HTTPError) as redirect:
                local_preview._NO_REDIRECT_OPENER.open(
                    f"{preview.origin}/redirect", timeout=5
                )
            assert redirect.value.code == 302
            assert ("GET", "/target") not in _Upstream.methods
            with pytest.raises(HTTPError) as method:
                local_preview._NO_REDIRECT_OPENER.open(
                    Request(f"{preview.origin}/", method="POST"), timeout=5
                )
            assert method.value.code == 501


def test_preview_returns_bounded_failure_for_unrewritable_home(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assets = _fake_assets(monkeypatch)
    monkeypatch.setattr(_Upstream, "home", b"<html>missing pinned scripts</html>")
    with _upstream() as upstream:
        _, upstream_port = upstream.server_address[:2]
        with (
            local_preview.LocalPreviewServer(
                assets=assets,
                upstream_origin=f"http://127.0.0.1:{upstream_port}",
                port=0,
            ) as preview,
            pytest.raises(HTTPError) as error,
        ):
            local_preview._NO_REDIRECT_OPENER.open(f"{preview.origin}/", timeout=5)
    assert error.value.code == 502


@pytest.mark.parametrize(
    "origin",
    ("http://localhost:8763", "https://127.0.0.1:8763", "http://10.0.0.1:8763"),
)
def test_preview_rejects_non_explicit_loopback_upstreams(origin: str) -> None:
    with pytest.raises(ValueError, match="127.0.0.1"):
        local_preview._loopback_origin(origin)


def test_preview_rejects_non_loopback_listener(monkeypatch: pytest.MonkeyPatch) -> None:
    assets = _fake_assets(monkeypatch)
    with pytest.raises(ValueError, match="bind 127.0.0.1"):
        local_preview.LocalPreviewServer(assets=assets, host="0.0.0.0", port=0)
