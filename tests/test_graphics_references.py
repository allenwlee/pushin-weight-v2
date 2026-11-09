import hashlib
import io
import struct

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.utils import timezone
from PIL import Image

from core.models import Person, PersonMedia, StaffMediaObject
from core.staff_assets.graphics_references import read_graphics_references


def saved_reference(
    tmp_path, person, storage, *, color="red", source="one", kind="image"
):
    root = tmp_path / "source"
    root.mkdir(exist_ok=True)
    if kind == "image":
        buf = io.BytesIO()
        Image.new("RGB", (4, 4), color).save(buf, "PNG")
        data = buf.getvalue()
        path = root / f"{source}.png"
    else:
        data = b"".join(
            struct.pack(">I4s", 12, name) + b"data"
            for name in (b"ftyp", b"moov", b"mdat")
        )
        path = root / f"{source}.mp4"
    path.write_bytes(data)
    checksum = hashlib.sha256(data).hexdigest()
    name = f"fixtures/{checksum}"
    if not storage.exists(name):
        storage.save(name, ContentFile(data))
    obj, _ = StaffMediaObject.objects.get_or_create(
        sha256=checksum,
        defaults={"storage_name": name, "media_type": "image/png" if kind == "image" else "video/mp4",
                  "byte_size": len(data), "width": 4 if kind == "image" else None,
                  "height": 4 if kind == "image" else None},
    )
    row = PersonMedia.objects.create(
        person=person, media=obj, fingerprint=hashlib.sha256(source.encode()).hexdigest(),
        source_url=f"https://example.org/{source}", source_kind="saved_g2_cast", kind=kind,
        availability="available", observed_at=timezone.now(),
        evidence={"source_role": "identity-still", "credit": f"Credit {source}",
                  "parent_sha256": "f" * 64, "identity_resolution": {
                      "state": "unverified_claim", "state_as_recorded": "verified",
                      "person_id": str(person.pk), "evidence": ["fixture"]}},
    )
    return row, data


def approve(row):
    PersonMedia.objects.filter(pk=row.pk).update(
        source_verified=True,
        individual_portrait=True,
        suitability="approved",
        reuse_status="permitted",
        verification_reason="Reviewed fixture",
    )


@pytest.mark.django_db(transaction=True)
def test_owner_confirmed_reference_is_usable_without_inventing_rights(tmp_path):
    person = Person.objects.create()
    storage = FileSystemStorage(location=tmp_path / "storage")
    row, data = saved_reference(tmp_path, person, storage, source="owner-confirmed")
    evidence = dict(row.evidence)
    evidence["identity_resolution"] = {
        "state": "verified",
        "method": "owner_confirmed_media",
        "person_id": str(person.pk),
        "evidence": ["Owner confirmed this reference for this person."],
    }
    PersonMedia.objects.filter(pk=row.pk).update(evidence=evidence)

    pack = read_graphics_references(
        person.pk, permitted_reuse={"unknown", "permitted"}, storage=storage
    )

    assert [ref.data for ref in pack.references] == [data]
    assert pack.references[0].reuse_status == "unknown"
    assert (
        pack.references[0].evidence["identity_resolution"]["method"]
        == "owner_confirmed_media"
    )
    row.refresh_from_db()
    assert row.reuse_status == "unknown"


@pytest.mark.django_db(transaction=True)
def test_cast_selection_needs_confirmation_bound_to_exact_file(tmp_path):
    person = Person.objects.create()
    storage = FileSystemStorage(location=tmp_path / "storage")
    row, data = saved_reference(tmp_path, person, storage)
    identity = {
        "state": "verified",
        "method": "owner_selected_cast",
        "person_id": str(person.pk),
        "evidence": ["Owner selected cast"],
        "owner_confirmation_reference": "owner:four-person-confirmation",
        "owner_confirmed_sha256": "0" * 64,
    }
    evidence = {**row.evidence, "identity_resolution": identity}
    PersonMedia.objects.filter(pk=row.pk).update(evidence=evidence)
    pack = read_graphics_references(
        person.pk, permitted_reuse={"unknown"}, storage=storage
    )
    assert len(pack.references) == 1 and not pack.references[0].owner_confirmed
    identity["owner_confirmed_sha256"] = row.media_id
    PersonMedia.objects.filter(pk=row.pk).update(
        evidence={**evidence, "identity_resolution": identity}
    )
    pack = read_graphics_references(
        person.pk, permitted_reuse={"unknown"}, storage=storage
    )
    assert [ref.data for ref in pack.references] == [data]
    assert not pack.references[0].owner_confirmed


@pytest.mark.django_db(transaction=True)
def test_existing_reference_accepts_owner_confirmation_in_review_history(tmp_path):
    person = Person.objects.create()
    storage = FileSystemStorage(location=tmp_path / "storage")
    row, data = saved_reference(tmp_path, person, storage)
    history = [
        {
            "event": "owner_confirmed_media",
            "person_id": str(person.pk),
            "sha256": row.media_id,
            "source_reference": "owner:confirmed",
        }
    ]
    PersonMedia.objects.filter(pk=row.pk).update(review_history=history)
    pack = read_graphics_references(
        person.pk, permitted_reuse={"unknown"}, storage=storage
    )
    assert [ref.data for ref in pack.references] == [data]


@pytest.mark.django_db(transaction=True)
def test_production_contract_passes_real_bytes_credits_and_lineage_to_caller(tmp_path):
    person = Person.objects.create()
    storage = FileSystemStorage(location=tmp_path / "storage")
    first, red = saved_reference(tmp_path, person, storage, color="red", source="first")
    second, blue = saved_reference(
        tmp_path, person, storage, color="blue", source="second"
    )
    clip, video = saved_reference(
        tmp_path, person, storage, source="clip", kind="video"
    )
    for row in (first, second, clip):
        approve(row)
    pack = read_graphics_references(
        person.pk, permitted_reuse={"permitted"}, include_video=True, storage=storage
    )
    received = [
        (ref.kind, ref.data, ref.credit, ref.parent_sha256) for ref in pack.references
    ]
    assert received == [
        ("image", red, "Credit first", "f" * 64),
        ("image", blue, "Credit second", "f" * 64),
        ("video", video, "Credit clip", "f" * 64),
    ]
    assert not pack.gaps
    fake_generation_transport = lambda payload: [
        (item.data, item.credit) for item in payload
    ]
    assert fake_generation_transport(pack.references) == [
        (red, "Credit first"),
        (blue, "Credit second"),
        (video, "Credit clip"),
    ]


@pytest.mark.django_db(transaction=True)
def test_pending_wrong_hash_and_missing_credit_are_explicit_gaps(tmp_path):
    person = Person.objects.create()
    storage = FileSystemStorage(location=tmp_path / "storage")
    pending, _ = saved_reference(tmp_path, person, storage, source="pending")
    corrupt, _ = saved_reference(
        tmp_path, person, storage, color="blue", source="corrupt"
    )
    missing_credit, _ = saved_reference(
        tmp_path, person, storage, color="green", source="no-credit"
    )
    approve(corrupt)
    approve(missing_credit)
    PersonMedia.objects.filter(pk=missing_credit.pk).update(evidence={})
    with storage.open(corrupt.media.storage_name, "wb") as stream:
        stream.write(b"wrong bytes")
    pack = read_graphics_references(
        person.pk, permitted_reuse={"permitted"}, storage=storage
    )
    reasons = {gap.person_media_id: gap.reasons for gap in pack.gaps}
    assert [ref.person_media_id for ref in pack.references] == [missing_credit.pk]
    assert "reuse_not_permitted_by_caller" in reasons[pending.pk]
    assert reasons[corrupt.pk] == ("stored_bytes_mismatch",)


@pytest.mark.django_db(transaction=True)
def test_partial_pack_deduplicates_bytes_and_respects_reuse_policy(tmp_path):
    person = Person.objects.create()
    storage = FileSystemStorage(location=tmp_path / "storage")
    first, data = saved_reference(tmp_path, person, storage, source="first")
    duplicate, _ = saved_reference(tmp_path, person, storage, source="second")
    approve(first)
    approve(duplicate)
    PersonMedia.objects.filter(pk=first.pk).update(reuse_status="unknown")
    pack = read_graphics_references(
        person.pk, permitted_reuse={"permitted"}, storage=storage
    )
    assert [(r.data, r.credit) for r in pack.references] == [(data, "Credit second")]
    assert any(
        g.person_media_id == first.pk and "reuse_not_permitted_by_caller" in g.reasons
        for g in pack.gaps
    )
    allowed = read_graphics_references(
        person.pk, permitted_reuse={"permitted", "unknown"}, storage=storage
    )
    assert len(allowed.references) == 1
    assert allowed.references[0].credit == "Credit first"


@pytest.mark.django_db(transaction=True)
def test_unknown_and_merged_people_do_not_return_someone_elses_files():
    import uuid

    missing = read_graphics_references(uuid.uuid4(), permitted_reuse={"permitted"})
    assert missing.gaps[0].reasons == ("person_not_found",)
    target = Person.objects.create()
    merged = Person.objects.create(merged_into=target)
    result = read_graphics_references(merged.pk, permitted_reuse={"permitted"})
    assert result.gaps[0].reasons == ("person_was_merged",)


@pytest.mark.django_db(transaction=True)
def test_unexpected_evidence_shape_does_not_hide_other_valid_references(tmp_path):
    person = Person.objects.create()
    storage = FileSystemStorage(location=tmp_path / "storage")
    malformed, _ = saved_reference(tmp_path, person, storage, source="malformed")
    valid, _ = saved_reference(tmp_path, person, storage, color="blue", source="valid")
    approve(malformed)
    approve(valid)
    PersonMedia.objects.filter(pk=malformed.pk).update(evidence=["unexpected"])

    pack = read_graphics_references(
        person.pk, permitted_reuse={"permitted"}, storage=storage
    )

    assert {ref.person_media_id for ref in pack.references} == {malformed.pk, valid.pk}
    assert (
        next(
            ref for ref in pack.references if ref.person_media_id == malformed.pk
        ).credit
        == ""
    )


@pytest.mark.django_db(transaction=True)
def test_unexpected_nested_role_does_not_hide_other_references(tmp_path):
    person = Person.objects.create()
    storage = FileSystemStorage(location=tmp_path / "storage")
    malformed, _ = saved_reference(tmp_path, person, storage, source="malformed")
    valid, _ = saved_reference(tmp_path, person, storage, color="blue", source="valid")
    PersonMedia.objects.filter(pk=malformed.pk).update(evidence={"source_role": []})
    pack = read_graphics_references(
        person.pk, permitted_reuse={"unknown"}, storage=storage
    )
    assert {r.person_media_id for r in pack.references} == {malformed.pk, valid.pk}


@pytest.mark.django_db(transaction=True)
def test_storage_endpoint_failure_is_reported_as_gap(tmp_path):
    from botocore.exceptions import EndpointConnectionError

    person = Person.objects.create()
    storage = FileSystemStorage(location=tmp_path / "storage")
    row, _ = saved_reference(tmp_path, person, storage)

    class UnavailableStorage:
        def open(self, name, mode):
            raise EndpointConnectionError(endpoint_url="https://example.org")

    pack = read_graphics_references(
        person.pk, permitted_reuse={"unknown"}, storage=UnavailableStorage()
    )
    assert any(
        g.person_media_id == row.pk and "storage_unreadable" in g.reasons
        for g in pack.gaps
    )


@pytest.mark.django_db(transaction=True)
def test_existing_portrait_kind_is_read_and_unreviewed_avatar_is_a_gap(tmp_path):
    person = Person.objects.create()
    storage = FileSystemStorage(location=tmp_path / "storage")
    portrait, data = saved_reference(tmp_path, person, storage, source="portrait")
    avatar, _ = saved_reference(
        tmp_path, person, storage, color="blue", source="avatar"
    )
    approve(portrait)
    PersonMedia.objects.filter(pk=portrait.pk).update(kind="portrait")
    PersonMedia.objects.filter(pk=avatar.pk).update(kind="avatar")

    pack = read_graphics_references(
        person.pk, permitted_reuse={"permitted"}, storage=storage
    )

    assert [(ref.kind, ref.data) for ref in pack.references] == [("image", data)]
    assert any(
        gap.person_media_id == avatar.pk
        and "reuse_not_permitted_by_caller" in gap.reasons
        for gap in pack.gaps
    )
