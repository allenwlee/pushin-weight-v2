"""MiniMax H3 task lifecycle. A query resumes a task; it never creates one."""

import base64
import hashlib
import json
import os
import re
import struct
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.db import transaction
from django.utils import timezone

from core.models import EditorialCall, EditorialPicture
from core.staff_assets.media import fetch_public, media_storage
from x_monitor.provider_http import https_request

from .contracts import digest
from .persistence import call_once
from .pictures import assignment_eligible


@dataclass(frozen=True)
class PollResult:
    picture: EditorialPicture
    reschedule: bool = False


def project_key():
    value = os.environ.get("PUSHINWEIGHT_MINIMAX_API_KEY", "")
    if not value:
        raise ValueError("PUSHINWEIGHT_MINIMAX_API_KEY is required")
    return value


def source_bytes(row, cfg):
    if not assignment_eligible(row, cfg):
        raise ValueError("source or affiliation no longer eligible")
    with media_storage().open(row.source_media.storage_name, "rb") as stream:
        data = stream.read(12 * 1024 * 1024 + 1)
    if (
        len(data) > 12 * 1024 * 1024
        or hashlib.sha256(data).hexdigest() != row.source_media_id
    ):
        raise ValueError("source hash mismatch or too large")
    return data


def start_derivative(row, assessment, cfg, *, transport=https_request):
    if (
        cfg.picture_mode(row.content_kind, row.source_platform) != "derive"
        or not row.source_media_id
    ):
        return row
    if row.provider_task_id or row.state in {
        "complete",
        "ambiguous",
        "failed",
        "exhausted",
    }:
        return row
    key = project_key()
    if not settings.EDITORIAL_MEDIA_DURABLE or not settings.STAFF_MEDIA_DURABLE:
        raise ValueError("durable worker storage must be configured")
    data = source_bytes(row, cfg)
    if min(row.source_media.width or 0, row.source_media.height or 0) < 256:
        raise ValueError("H3 source image is too small")
    cache_key = digest(
        [
            row.source_media_id,
            row.revision_hash,
            row.treatment,
            "MiniMax-H3",
            cfg.media_duration,
        ]
    )
    cached = (
        EditorialPicture.objects.filter(
            provenance__cache_key=cache_key, state="complete"
        )
        .exclude(pk=row.pk)
        .first()
    )
    if cached and storages["editorial_media"].exists(cached.generated_storage_name):
        row.generated_storage_name = cached.generated_storage_name
        row.generated_sha256 = cached.generated_sha256
        row.state = "complete"
        row.save()
        return row
    payload = {
        "model": "MiniMax-H3",
        "duration": cfg.media_duration,
        "resolution": "768P",
        "ratio": "adaptive",
        "content": [
            {"type": "text", "text": row.treatment},
            {
                "type": "image_url",
                "image_url": f"data:{row.source_media.media_type};base64,"
                + base64.b64encode(data).decode(),
                "role": "first_frame",
            },
        ],
    }

    def send():
        status, body = transport(
            "https://api.minimax.io/v2/video_generation", key, payload, timeout=60
        )
        result = json.loads(body)
        task_id = str(result.get("task_id", ""))
        if not 200 <= status < 300 or not re.fullmatch(
            r"[A-Za-z0-9_-]{1,160}", task_id
        ):
            raise ValueError("media create failed or task ID missing")
        return {"task_id": task_id}

    try:
        result = call_once(
            assessment,
            f"media:{row.pk}",
            "media",
            cfg.media_cost_ceiling_usd,
            cfg,
            send,
        )
    except Exception:
        # Reservation failures are not sent; ledger distinguishes the two for recovery.
        if EditorialCall.objects.filter(
            kind="media", stage=f"media:{row.pk}", state="ambiguous"
        ).exists():
            EditorialPicture.objects.filter(pk=row.pk).update(state="ambiguous")
        raise
    row.provider_task_id = result["task_id"]
    row.state = "pending"
    row.next_poll_at = timezone.now() + timedelta(seconds=30)
    row.provenance = {
        **row.provenance,
        "cache_key": cache_key,
        "provider": "MiniMax-H3",
        "duration": cfg.media_duration,
    }
    row.save()
    return row


def validate_mp4(data):
    if len(data) > 50 * 1024 * 1024:
        raise ValueError("video too large")
    pos = 0
    boxes = set()
    while pos + 8 <= len(data):
        size, kind = struct.unpack(">I4s", data[pos : pos + 8])
        header = 8
        if size == 1:
            if pos + 16 > len(data):
                raise ValueError("invalid MP4")
            size = struct.unpack(">Q", data[pos + 8 : pos + 16])[0]
            header = 16
        elif size == 0:
            size = len(data) - pos
        if size < header or pos + size > len(data):
            raise ValueError("invalid MP4")
        boxes.add(kind)
        pos += size
    if pos != len(data) or not {b"ftyp", b"moov", b"mdat"} <= boxes:
        raise ValueError("invalid MP4 container")


def poll_derivative(picture_id, cfg, *, transport=https_request, download=fetch_public):
    now = timezone.now()
    with transaction.atomic():
        row = EditorialPicture.objects.select_for_update().get(pk=picture_id)
        if (
            row.state != "pending"
            or row.next_poll_at > now
            or (row.poll_lease_until and row.poll_lease_until > now)
        ):
            return PollResult(row)
        if row.poll_count >= cfg.media_max_polls:
            row.state = "exhausted"
            row.save(update_fields=["state"])
            return PollResult(row)
        row.poll_count += 1
        row.poll_lease_until = now + timedelta(minutes=3)
        row.save(update_fields=["poll_count", "poll_lease_until"])
        generation = row.poll_count
    # Already submitted tasks can be collected after disable, but readers hide attachments.
    try:
        status, body = transport(
            f"https://api.minimax.io/v2/query/video_generation/{row.provider_task_id}",
            project_key(),
            None,
            method="GET",
            timeout=45,
        )
        task = json.loads(body).get("task", {})
        if (
            status != 200
            or str(task.get("id")) != row.provider_task_id
            or task.get("model") != "MiniMax-H3"
        ):
            raise ValueError("media query identity mismatch")
        if task.get("status") == "succeeded":
            url = task.get("content", {}).get("url", "")
            parsed = urlsplit(url)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or not (
                    parsed.hostname == "hailuoai.com"
                    or parsed.hostname.endswith(".hailuoai.com")
                    or parsed.hostname.endswith(".minimax.io")
                )
            ):
                raise ValueError("unexpected media download host")
            data = download(url, max_bytes=50 * 1024 * 1024)
            validate_mp4(data)
            sha = hashlib.sha256(data).hexdigest()
            storage = storages["editorial_media"]
            name = f"generated/{sha}.mp4"
            if not storage.exists(name):
                name = storage.save(name, ContentFile(data))
            row.generated_storage_name = name
            row.generated_sha256 = sha
            row.state = "complete"
        elif task.get("status") in {"failed", "canceled", "cancelled", "expired"}:
            row.state = "failed"
    except Exception as exc:  # noqa: BLE001 - persist bounded worker failure, never report success
        row.provenance = {**row.provenance, "last_error": type(exc).__name__}
    with transaction.atomic():
        current = EditorialPicture.objects.select_for_update().get(pk=picture_id)
        if current.state == "pending" and current.poll_count == generation:
            current.state = row.state
            current.generated_storage_name = row.generated_storage_name
            current.generated_sha256 = row.generated_sha256
            current.provenance = row.provenance
            current.next_poll_at = timezone.now() + timedelta(seconds=30)
            current.poll_lease_until = None
            current.save()
            return PollResult(current, reschedule=current.state == "pending")
        return PollResult(current)
