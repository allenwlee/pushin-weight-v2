"""Bounded public downloads and content-addressed storage with separate attribution."""

import hashlib
import io
import ipaddress
import socket
import time
import warnings
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import urllib3
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.db import transaction
from django.utils import timezone
from PIL import Image

from core.models import PersonMedia, StaffMediaObject
from core.person_names import digest

MAX_BYTES = 12 * 1024 * 1024
MAX_PIXELS = 40_000_000


def media_storage():
    return storages["staff_media"]


def local_bytes(asset_root, relative_path):
    root = Path(asset_root).resolve(strict=True)
    path = (root / relative_path).resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("Media path escapes the supplied asset root")
    with path.open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("Media exceeds byte limit")
    return data


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


def fetch_public(url):
    deadline = time.monotonic() + 45
    for _ in range(4):
        parsed, port, addresses = public_addresses(url)
        # Pin the validated IP; DNS is not resolved again during the connection.
        options = {
            "host": addresses[0],
            "port": port,
            "timeout": urllib3.Timeout(connect=5, read=10),
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
            for chunk in response.stream(65536, decode_content=True):
                body.extend(chunk)
                if len(body) > MAX_BYTES or time.monotonic() > deadline:
                    raise ValueError("Media download limit exceeded")
            return bytes(body)
        finally:
            if response:
                response.close()
            pool.close()
    raise ValueError("Too many media redirects")


def store_image(data):
    if len(data) > MAX_BYTES:
        raise ValueError("Media exceeds byte limit")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            if width * height > MAX_PIXELS or image.format not in {
                "JPEG",
                "PNG",
                "WEBP",
                "GIF",
            }:
                raise ValueError("Unsupported image format or dimensions")
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            extension = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "GIF": "gif"}[
                image.format
            ]
            content_type = Image.MIME[image.format]
    sha = hashlib.sha256(data).hexdigest()
    existing = StaffMediaObject.objects.filter(pk=sha).first()
    if existing:
        return existing
    storage = media_storage()
    path = f"sha256/{sha[:2]}/{sha}.{extension}"
    # Serialize local/storage writes by content hash, retaining every attribution.
    with transaction.atomic():
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [int(sha[:15], 16)])
        existing = StaffMediaObject.objects.filter(pk=sha).first()
        if existing:
            return existing
        if not storage.exists(path):
            path = storage.save(path, ContentFile(data))
        return StaffMediaObject.objects.create(
            sha256=sha,
            storage_name=path,
            media_type=content_type,
            byte_size=len(data),
            width=width,
            height=height,
        )


def record_media(person, entry, *, asset_root=None, observed_at=None):
    values = {
        key: entry[key]
        for key in (
            "source_url",
            "original_url",
            "source_kind",
            "discovery_provider",
            "kind",
            "evidence",
        )
        if key in entry
    }
    if not values.get("source_url") or not values.get("source_kind"):
        raise ValueError("Media requires publisher URL and source kind")
    fingerprint = digest(values)
    row, _ = PersonMedia.objects.get_or_create(
        person=person,
        fingerprint=fingerprint,
        defaults={**values, "observed_at": observed_at or timezone.now()},
    )
    if entry.get("path") and not row.media_id:
        if asset_root is None:
            raise ValueError("Explicit asset root required for local media")
        try:
            row.media = store_image(local_bytes(asset_root, entry["path"]))
            row.availability = "available"
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            row.availability = "unavailable"
            row.evidence = {**row.evidence, "download_error": type(exc).__name__}
        row.save()
    review = entry.get("review")
    if review:
        review_media(row, **review)
    return row


@transaction.atomic
def review_media(
    row,
    *,
    reviewer,
    reason,
    source_verified,
    individual_portrait,
    suitability="pending",
    reuse_status="unknown",
):
    if not reviewer or not reason:
        raise ValueError("Review requires reviewer and reason")
    if suitability not in {"pending", "approved", "rejected"} or reuse_status not in {
        "unknown",
        "permitted",
        "restricted",
    }:
        raise ValueError("Unknown media review state")
    row = PersonMedia.objects.select_for_update().get(pk=row.pk)
    review = {
        "reviewer": reviewer,
        "reason": reason,
        "source_verified": source_verified,
        "individual_portrait": individual_portrait,
        "suitability": suitability,
        "reuse_status": reuse_status,
    }
    if row.review_history and all(
        row.review_history[-1].get(k) == v for k, v in review.items()
    ):
        return row
    row.review_history.append({**review, "at": timezone.now().isoformat()})
    for key in (
        "source_verified",
        "individual_portrait",
        "suitability",
        "reuse_status",
    ):
        setattr(row, key, review[key])
    row.verification_reason = reason
    row.save()
    return row
