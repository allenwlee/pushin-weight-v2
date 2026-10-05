"""Copy existing staff files without changing their database references."""

import hashlib
import json
import re
from pathlib import Path, PurePosixPath

from botocore.exceptions import BotoCoreError, ClientError
from django.core.exceptions import SuspiciousFileOperation
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage

from core.media_storage import PrivateR2Storage
from core.models import StaffMediaObject
from core.staff_assets.media import MAX_BYTES, local_bytes, media_storage


def _check_metadata(row):
    name = row["storage_name"]
    path = PurePosixPath(name)
    if not name or path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError("invalid_object_name")
    if not re.fullmatch(r"[a-f0-9]{64}", row["sha256"]):
        raise ValueError("invalid_expected_hash")
    if not 0 < row["byte_size"] <= MAX_BYTES:
        raise ValueError("invalid_expected_size")


def _check_bytes(data, row):
    if len(data) != row["byte_size"]:
        raise ValueError("byte_size_mismatch")
    if hashlib.sha256(data).hexdigest() != row["sha256"]:
        raise ValueError("sha256_mismatch")


def _verify_stored(storage, row):
    if storage.size(row["storage_name"]) != row["byte_size"]:
        raise ValueError("byte_size_mismatch")
    with storage.open(row["storage_name"], "rb") as stream:
        _check_bytes(stream.read(row["byte_size"] + 1), row)


def transfer_staff_media(
    *, source_root=None, storage=None, apply=False, verify_only=False
):
    """Preview by default; apply is resumable, verify-only needs no local files.

    Database rows and source files are read-only in every mode. A differing
    destination is an error, never an overwrite request.
    """
    if apply and verify_only:
        raise ValueError("apply and verify_only are mutually exclusive")
    storage = media_storage() if storage is None else storage
    root = None
    if not verify_only:
        if source_root is None:
            raise ValueError("source_root is required for preview or copy")
        root = Path(source_root).resolve(strict=True)
        if not root.is_dir():
            raise ValueError("source_root must be a directory")
        if (
            isinstance(storage, FileSystemStorage)
            and root == Path(storage.location).resolve()
        ):
            raise ValueError("source and destination are the same directory")
    rows = list(
        StaffMediaObject.objects.order_by("sha256").values(
            "sha256", "storage_name", "byte_size", "media_type"
        )
    )
    report = {
        "schema": "staff-media-transfer/v1",
        "mode": "verify" if verify_only else "copy" if apply else "preview",
        "objects": len(rows),
        "inventory_sha256": hashlib.sha256(
            json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "planned": 0,
        "copied": 0,
        "verified": 0,
        "verified_bytes": 0,
        "errors": [],
    }
    for row in rows:
        try:
            _check_metadata(row)
            if storage.exists(row["storage_name"]):
                _verify_stored(storage, row)
            elif verify_only:
                raise ValueError("destination_missing")
            else:
                data = local_bytes(root, row["storage_name"])
                _check_bytes(data, row)
                report["planned"] += 1
                if not apply:
                    continue
                if isinstance(storage, PrivateR2Storage):
                    created = storage.save_if_absent(
                        row["storage_name"], data, content_type=row["media_type"]
                    )
                elif (
                    isinstance(storage, FileSystemStorage)
                    and not storage._allow_overwrite
                ):
                    content = ContentFile(data)
                    content.content_type = row["media_type"]
                    saved = storage.save(row["storage_name"], content)
                    if saved != row["storage_name"]:
                        raise ValueError("destination_renamed_object")
                    created = True
                else:
                    raise ValueError("destination_does_not_support_safe_copy")
                report["copied"] += int(created)
                _verify_stored(storage, row)
            report["verified"] += 1
            report["verified_bytes"] += row["byte_size"]
        except (
            OSError,
            ValueError,
            SuspiciousFileOperation,
            BotoCoreError,
            ClientError,
        ) as exc:
            # Provider exception strings can contain operational details. Only
            # our controlled validation errors and exception classes enter receipts.
            report["errors"].append(
                {
                    "sha256": row["sha256"],
                    "storage_name": row["storage_name"],
                    "error": str(exc)
                    if type(exc) is ValueError
                    else type(exc).__name__,
                }
            )
    return report
