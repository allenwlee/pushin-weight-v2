"""Bounded public downloads with validated and pinned network destinations."""

import ipaddress
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from urllib.parse import urljoin, urlsplit

import urllib3

MAX_BYTES = 12 * 1024 * 1024
_deadline_fetches = ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="public-source"
)


def fetch_before_deadline(url, *, max_bytes, deadline, max_requests=4):
    """Bound the caller's wait including DNS and a server that drips body bytes."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Reference-fetch deadline exceeded")
    future = _deadline_fetches.submit(
        fetch_public_response, url, max_bytes=max_bytes, deadline=deadline,
        **({"max_requests": max_requests} if max_requests != 4 else {}),
    )
    try:
        return future.result(timeout=remaining)
    finally:
        future.cancel()  # A queued request must not start after its caller timed out.


def public_addresses(url):
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Only unauthenticated public HTTP(S) media URLs are supported")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if port != (443 if parsed.scheme == "https" else 80):
        raise ValueError("Nonstandard media ports are not supported")
    addresses = sorted(
        {
            info[4][0]
            for info in socket.getaddrinfo(
                parsed.hostname, port, type=socket.SOCK_STREAM
            )
        }
    )
    if not addresses or any(
        not ipaddress.ip_address(address).is_global for address in addresses
    ):
        raise ValueError("Non-public network destination rejected")
    return parsed, port, addresses


def fetch_public_response(url, *, max_bytes=MAX_BYTES, deadline=None, resolver=None, max_requests=4):
    deadline = (
        min(deadline, time.monotonic() + 45)
        if deadline is not None
        else time.monotonic() + 45
    )
    resolver = resolver or public_addresses
    for _ in range(min(max_requests, 4)):
        if time.monotonic() >= deadline:
            raise TimeoutError("Reference-fetch deadline exceeded")
        parsed, port, addresses = resolver(url)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Reference-fetch deadline exceeded")
        # Pin the validated IP; DNS is not resolved again during the connection.
        options = {
            "host": addresses[0],
            "port": port,
            "timeout": urllib3.Timeout(
                total=remaining, connect=min(5, remaining), read=min(10, remaining)
            ),
            "retries": False,
        }
        if parsed.scheme == "https":
            pool = urllib3.HTTPSConnectionPool(
                **options,
                server_hostname=parsed.hostname,
                assert_hostname=parsed.hostname,
                cert_reqs="CERT_REQUIRED",
            )
        else:
            pool = urllib3.HTTPConnectionPool(**options)
        response = None
        try:
            response = pool.request(
                "GET",
                parsed.path + ("?" + parsed.query if parsed.query else ""),
                headers={
                    "Host": parsed.hostname,
                    "User-Agent": "PushinWeight-StaffResearch/1",
                },
                preload_content=False,
                redirect=False,
            )
            if response.status in {301, 302, 303, 307, 308}:
                url = urljoin(url, response.headers.get("Location", ""))
                continue
            if response.status != 200:
                raise ValueError(f"Media HTTP status {response.status}")
            body = bytearray()
            # read1 returns available decoded bytes without waiting to fill a
            # full chunk. Recheck the deadline during a slow response stream.
            read1 = getattr(response, "read1", None)
            chunks = (
                iter(partial(read1, 65536, decode_content=True), b"")
                if read1
                else response.stream(65536, decode_content=True)
            )
            for chunk in chunks:
                body.extend(chunk)
                if len(body) > max_bytes or time.monotonic() > deadline:
                    raise ValueError("Media download limit exceeded")
            if time.monotonic() > deadline:
                raise TimeoutError("Reference-fetch deadline exceeded")
            return bytes(body), url, response.headers.get("Content-Type", "")
        finally:
            if response:
                response.close()
            pool.close()
    raise ValueError("Too many media redirects")
