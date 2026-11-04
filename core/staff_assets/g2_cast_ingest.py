"""Import reviewed cast-image entries into the existing staff-media contract.

The caller must resolve identity before supplying a person. This module never
creates people or upgrades identity, suitability, or reuse review states.
"""

import hashlib
import io
import re
from pathlib import Path
from urllib.parse import urlsplit

from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.db import connection, transaction
from PIL import Image

from core.media_storage import PrivateR2Storage
from core.models import PersonMedia, StaffMediaObject
from core.person_names import digest
from core.staff_assets.media import MAX_BYTES, MAX_PIXELS
from monitor.editorial.media import validate_mp4


def _validated_image(filename, expected_sha256, roots):
    path = Path(filename).resolve(strict=True)
    if not any(path.is_relative_to(root) for root in roots) or not path.is_file():
        raise ValueError("image_outside_source_roots")
    with path.open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if not data or len(data) > MAX_BYTES:
        raise ValueError("invalid_image_size")
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError("source_hash_mismatch")
    with Image.open(io.BytesIO(data)) as image:
        if image.format not in {"JPEG", "PNG", "WEBP", "GIF", "MPO"}:
            raise ValueError("unsupported_image_format")
        width, height = image.size
        if width * height > MAX_PIXELS:
            raise ValueError("image_dimensions_too_large")
        image.verify()
    with Image.open(io.BytesIO(data)) as image:
        fmt = image.format
        if fmt == "MPO":
            frames = image.n_frames
            if not 1 <= frames <= 10:
                raise ValueError("too_many_mpo_frames")
            total_pixels = 0
            for index in range(frames):
                image.seek(index)
                total_pixels += image.width * image.height
                if total_pixels > MAX_PIXELS:
                    raise ValueError("image_dimensions_too_large")
                image.load()
        else:
            image.load()
        extension = {
            "JPEG": "jpg",
            "PNG": "png",
            "WEBP": "webp",
            "GIF": "gif",
            "MPO": "mpo",
        }[fmt]
        content_type = Image.MIME[fmt]
    return data, width, height, extension, content_type


def _verify_bytes(storage, name, data):
    with storage.open(name, "rb") as stream:
        existing = stream.read(len(data) + 1)
    if existing != data:
        raise ValueError("destination_bytes_mismatch")


def _validated_video(filename, expected_sha256, roots):
    path = Path(filename).resolve(strict=True)
    if not any(path.is_relative_to(root) for root in roots) or not path.is_file():
        raise ValueError("video_outside_source_roots")
    with path.open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if not data or len(data) > MAX_BYTES:
        raise ValueError("invalid_video_size")
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError("source_hash_mismatch")
    validate_mp4(data)
    return data, None, None, "mp4", "video/mp4"


def validate_entry(person, entry):
    expected = entry.get("expected_sha256")
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("expected_hash_required")
    source_url = entry.get("source_url", "")
    try:
        source = urlsplit(source_url or "")
        valid_source = not source_url or (
            source.scheme in {"http", "https"}
            and bool(source.hostname)
            and not source.username
            and not source.password
        )
    except ValueError:
        valid_source = False
    if not isinstance(source_url, str) or not valid_source:
        raise ValueError("invalid_source_url")
    if not isinstance(entry.get("credit", ""), str):
        raise TypeError("invalid_credit")
    if str(person.pk) != entry.get("candidate_person_id"):
        raise ValueError("person_mismatch")
    identity = entry.get("identity_resolution") or {}
    if (
        identity.get("state") != "verified"
        or identity.get("person_id") != str(person.pk)
        or not isinstance(identity.get("evidence"), list)
        or not identity["evidence"]
        or any(
            not isinstance(item, str) or not item.strip()
            for item in identity["evidence"]
        )
    ):
        raise ValueError("verified_identity_evidence_required")
    accreditation = entry.get("recorded_accreditation")
    if accreditation is not None and (
        not isinstance(accreditation, dict)
        or set(accreditation) - {"asset_id", "original_creator", "basis", "evidence"}
        or any(
            value is not None and not isinstance(value, str)
            for value in accreditation.values()
        )
    ):
        raise ValueError("invalid_recorded_accreditation")


def ingest_image(*, person, entry, source_roots, storage, observed_at, preview=False):
    """Store one image and pending attribution without overwriting objects."""
    return _ingest_asset(
        person=person,
        entry=entry,
        source_roots=source_roots,
        storage=storage,
        observed_at=observed_at,
        kind="image",
        preview=preview,
    )


def ingest_video(*, person, entry, source_roots, storage, observed_at, preview=False):
    """Store an original MP4 and its pending source attribution."""
    return _ingest_asset(
        person=person,
        entry=entry,
        source_roots=source_roots,
        storage=storage,
        observed_at=observed_at,
        kind="video",
        preview=preview,
    )


def _ingest_asset(*, person, entry, source_roots, storage, observed_at, kind, preview):
    roots = [Path(root).resolve(strict=True) for root in source_roots]
    if not roots:
        raise ValueError("source_roots_required")
    validate_entry(person, entry)
    expected = entry["expected_sha256"]
    source_url = entry.get("source_url", "")
    identity = entry["identity_resolution"]
    validate_media = _validated_image if kind == "image" else _validated_video
    data, width, height, extension, content_type = validate_media(
        entry["file"], expected, roots
    )
    evidence = {
        "schema": f"g2-cast-{kind}/v1",
        "source_person_key": entry["person_key"],
        "source_role": entry.get("role"),
        "source_sha256": expected,
        "source_evidence": entry.get("source_evidence"),
        "source_verified_as_recorded": entry.get("source_verified"),
        "source_verification": entry.get("source_verification"),
        "identity_resolution": identity,
        "grade_as_recorded": entry.get("grade"),
        "reuse_as_recorded": entry.get("reuse_status", "unknown"),
        "credit": entry.get("credit", ""),
        "credit_as_recorded": entry.get("credit_as_recorded"),
        "credit_origin": entry.get("credit_origin"),
        "license": entry.get("license"),
        "parent_sha256": entry.get("parent_sha256"),
        "crop_pixels_xyxy": entry.get("crop_pixels_xyxy"),
        "source_seconds": entry.get("source_seconds"),
        "local_seconds": entry.get("local_seconds"),
        "transformation": entry.get("transformation"),
    }
    if kind == "video":
        evidence["video_inspection"] = entry.get("video_inspection")
    if entry.get("recorded_accreditation"):
        evidence["recorded_accreditation"] = entry["recorded_accreditation"]
    if entry.get("source_child_sha256"):
        evidence["source_child_sha256"] = entry["source_child_sha256"]
    values = {
        "source_url": source_url,
        "original_url": entry.get("original_url") or "",
        "source_kind": "saved_g2_cast",
        "discovery_provider": "g2_cast",
        "kind": kind,
        "evidence": evidence,
    }
    fingerprint = digest(values)
    name = f"sha256/{expected[:2]}/{expected}.{extension}"
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [int(expected[:15], 16)])
        obj = StaffMediaObject.objects.filter(pk=expected).first()
        if obj:
            name = obj.storage_name
            if (
                obj.byte_size != len(data)
                or obj.media_type != content_type
                or obj.width != width
                or obj.height != height
            ):
                raise ValueError("existing_object_metadata_mismatch")
        existing_rows = list(
            PersonMedia.objects.filter(
                person=person, media_id=expected, source_url=source_url
            )
        )
        reusable = next(
            (
                row
                for row in existing_rows
                if row.availability == "available" and row.evidence == evidence
            ),
            None,
        )
        if existing_rows and reusable is None:
            raise ValueError("existing_attribution_requires_reconciliation")
        if storage.exists(name):
            _verify_bytes(storage, name, data)
        elif preview:
            if obj is not None:
                raise ValueError("existing_object_bytes_missing")
        elif isinstance(storage, PrivateR2Storage):
            storage.save_if_absent(name, data, content_type=content_type)
            _verify_bytes(storage, name, data)
        elif isinstance(storage, FileSystemStorage) and not storage._allow_overwrite:
            content = ContentFile(data)
            content.content_type = content_type
            if storage.save(name, content) != name:
                raise ValueError("destination_renamed_object")
            _verify_bytes(storage, name, data)
        else:
            raise ValueError("destination_does_not_support_safe_copy")
        if preview:
            return reusable, reusable is None
        if obj is None:
            obj = StaffMediaObject.objects.create(
                sha256=expected,
                storage_name=name,
                media_type=content_type,
                byte_size=len(data),
                width=width,
                height=height,
            )
        # Do not discard new lineage or duplicate an existing attribution with
        # different evidence. Hold it for reconciliation without changing it.
        if reusable is not None:
            return reusable, False
        row, created = PersonMedia.objects.get_or_create(
            person=person,
            fingerprint=fingerprint,
            defaults={
                **values,
                "media": obj,
                "availability": "available",
                "observed_at": observed_at,
            },
        )
        if not created and (row.media_id != obj.pk or row.source_url != source_url):
            raise ValueError("attribution_fingerprint_collision")
        return row, created
