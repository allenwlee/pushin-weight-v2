"""Read reviewed person references from the configured production storage."""

import hashlib
import re
from dataclasses import dataclass

from botocore.exceptions import BotoCoreError, ClientError
from django.core.exceptions import ValidationError
from django.core.files.storage import storages

from core.models import Person, PersonMedia
from core.staff_assets.media import MAX_BYTES


@dataclass(frozen=True)
class Reference:
    person_media_id: int
    sha256: str
    kind: str
    media_type: str
    data: bytes
    source_url: str
    credit: str
    parent_sha256: str | None
    source_seconds: float | None
    local_seconds: float | None
    reuse_status: str
    source_verified: bool
    individual_portrait: bool
    suitability: str
    evidence: dict
    owner_confirmed: bool | None
    review_history: list


@dataclass(frozen=True)
class ReferenceGap:
    person_media_id: int | None
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ReferencePack:
    person_id: str
    references: tuple[Reference, ...]
    gaps: tuple[ReferenceGap, ...]


def _media_kind(row):
    """Use the stored file type when the attribution kind describes its use."""
    media_type = row.media.media_type if row.media_id else ""
    if media_type.startswith("image/"):
        return "image"
    if media_type.startswith("video/"):
        return "video"
    if row.kind in {"image", "video"}:
        return row.kind
    if row.kind in {"portrait", "avatar"}:
        return "image"
    return None


def read_graphics_references(
    person_id, *, permitted_reuse, max_images=3, include_video=False, storage=None
):
    """Return original bytes, recorded evidence and gaps for one existing person.

    A caller supplies its reuse policy; review states are reported as recorded,
    rather than silently becoming additional eligibility requirements.
    """
    if (
        not isinstance(max_images, int)
        or isinstance(max_images, bool)
        or not 1 <= max_images <= 10
    ):
        raise ValueError("max_images must be between 1 and 10")
    permitted_reuse = frozenset(permitted_reuse)
    if not permitted_reuse <= {"unknown", "permitted", "restricted"}:
        raise ValueError("invalid reuse policy")
    try:
        person = Person.objects.filter(pk=person_id).first()
    except (ValidationError, ValueError, TypeError) as exc:
        raise ValueError("invalid person id") from exc
    if person is None:
        return ReferencePack(
            str(person_id), (), (ReferenceGap(None, ("person_not_found",)),)
        )
    if person.merged_into_id:
        return ReferencePack(
            str(person.pk), (), (ReferenceGap(None, ("person_was_merged",)),)
        )
    storage = storage if storage is not None else storages["staff_media"]
    rows = list(
        PersonMedia.objects.filter(person=person).select_related("media").order_by("id")
    )
    role_rank = {
        "identity-still": 0,
        "prepared-identity-crop": 0,
        "identity": 0,
        "existing-reference": 1,
        "source-frame": 2,
    }

    def role_order(row):
        evidence = row.evidence if isinstance(row.evidence, dict) else {}
        role = evidence.get("source_role")
        return role_rank.get(role, 3) if isinstance(role, str) else 3

    rows.sort(
        key=lambda row: (
            _media_kind(row) != "image",
            role_order(row),
            row.pk,
        )
    )
    refs, gaps, hashes = [], [], set()
    images = videos = 0
    for row in rows:
        kind = _media_kind(row)
        if kind not in {"image", "video"} or (kind == "video" and not include_video):
            continue
        if kind == "image" and images >= max_images or kind == "video" and videos >= 1:
            continue
        evidence = row.evidence if isinstance(row.evidence, dict) else {}
        history = row.review_history if isinstance(row.review_history, list) else []
        owner_confirmed = (
            True
            if any(
                isinstance(event, dict)
                and event.get("event") == "owner_confirmed_media"
                and event.get("person_id") == str(person.pk)
                and event.get("sha256") == row.media_id
                and bool(event.get("source_reference"))
                for event in history
            )
            else None
        )
        credit = evidence.get("credit")
        reasons = []
        if not row.media_id or row.availability != "available":
            reasons.append("bytes_not_available")
        if row.reuse_status not in permitted_reuse:
            reasons.append("reuse_not_permitted_by_caller")
        if reasons:
            gaps.append(ReferenceGap(row.pk, tuple(reasons)))
            continue
        obj = row.media
        if (
            not re.fullmatch(r"[0-9a-f]{64}", obj.sha256)
            or not 0 < obj.byte_size <= MAX_BYTES
        ):
            gaps.append(ReferenceGap(row.pk, ("invalid_object_metadata",)))
            continue
        if obj.sha256 in hashes:
            continue
        if (
            kind == "image"
            and obj.media_type
            not in {"image/jpeg", "image/png", "image/webp", "image/gif"}
            or kind == "video"
            and obj.media_type != "video/mp4"
        ):
            gaps.append(ReferenceGap(row.pk, ("unsupported_media_type",)))
            continue
        try:
            with storage.open(obj.storage_name, "rb") as stream:
                data = stream.read(MAX_BYTES + 1)
        except (OSError, BotoCoreError, ClientError, ValueError):
            gaps.append(ReferenceGap(row.pk, ("storage_unreadable",)))
            continue
        if len(data) != obj.byte_size or hashlib.sha256(data).hexdigest() != obj.sha256:
            gaps.append(ReferenceGap(row.pk, ("stored_bytes_mismatch",)))
            continue
        refs.append(
            Reference(
                row.pk,
                obj.sha256,
                kind,
                obj.media_type,
                data,
                row.source_url,
                credit if isinstance(credit, str) else "",
                evidence.get("parent_sha256"),
                evidence.get("source_seconds"),
                evidence.get("local_seconds"),
                row.reuse_status,
                row.source_verified,
                row.individual_portrait,
                row.suitability,
                evidence,
                owner_confirmed,
                history,
            )
        )
        hashes.add(obj.sha256)
        images += kind == "image"
        videos += kind == "video"
    if not images:
        gaps.append(ReferenceGap(None, ("no_usable_still",)))
    return ReferencePack(str(person.pk), tuple(refs), tuple(gaps))
