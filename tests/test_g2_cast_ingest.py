import hashlib
import io
import json
import struct
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.core.files.storage import FileSystemStorage
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import close_old_connections, connection
from django.utils import timezone
from PIL import Image

from core.models import (
    Account,
    AccountProfileSnapshot,
    AffiliationType,
    Brand,
    Language,
    Locale,
    Person,
    PersonAccount,
    PersonBrandAffiliation,
    PersonBrandAffiliationEvidence,
    PersonMedia,
    PersonName,
    PersonNameEvidence,
    Post,
    StaffMediaObject,
)
from core.staff_assets.g2_cast_ingest import ingest_image, ingest_video


@pytest.fixture
def image_entry(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    path = source / "image.png"
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(buffer, "PNG")
    data = buffer.getvalue()
    path.write_bytes(data)
    person = Person.objects.create()
    entry = {
        "file": str(path),
        "expected_sha256": hashlib.sha256(data).hexdigest(),
        "person_key": "example",
        "candidate_person_id": str(person.pk),
        "identity_resolution": {
            "state": "verified",
            "person_id": str(person.pk),
            "evidence": ["fixture source"],
        },
        "source_url": "https://example.org/source",
        "credit": "Example creator",
        "role": "identity-still",
    }
    return source, data, person, entry


@pytest.mark.django_db(transaction=True)
def test_real_import_is_idempotent_and_keeps_sources_separate(tmp_path, image_entry):
    source, data, person, entry = image_entry
    storage = FileSystemStorage(location=tmp_path / "target")
    row, created = ingest_image(
        person=person,
        entry=entry,
        source_roots=[source],
        storage=storage,
        observed_at=timezone.now(),
    )
    assert created and row.availability == "available"
    assert row.evidence["identity_resolution"]["state"] == "unverified_claim"
    assert row.evidence["identity_resolution"]["state_as_recorded"] == "verified"
    assert not row.source_verified and not row.individual_portrait
    assert row.suitability == "pending" and row.reuse_status == "unknown"
    with storage.open(row.media.storage_name, "rb") as stream:
        assert stream.read() == data
    again, created = ingest_image(
        person=person,
        entry=entry,
        source_roots=[source],
        storage=storage,
        observed_at=timezone.now(),
    )
    assert not created and again.pk == row.pk
    legacy_evidence = dict(row.evidence)
    legacy_evidence["identity_resolution"] = dict(entry["identity_resolution"])
    PersonMedia.objects.filter(pk=row.pk).update(evidence=legacy_evidence)
    legacy, created = ingest_image(
        person=person,
        entry=entry,
        source_roots=[source],
        storage=storage,
        observed_at=timezone.now(),
    )
    assert not created and legacy.pk == row.pk and legacy.evidence == legacy_evidence
    other = {**entry, "source_url": "https://example.org/other"}
    second, created = ingest_image(
        person=person,
        entry=other,
        source_roots=[source],
        storage=storage,
        observed_at=timezone.now(),
    )
    assert created and second.media_id == row.media_id
    assert StaffMediaObject.objects.count() == 1
    assert PersonMedia.objects.count() == 2

    same_source_new_credit = {**entry, "credit": "Another credited creator"}
    with pytest.raises(
        ValueError, match="existing_attribution_requires_reconciliation"
    ):
        ingest_image(
            person=person,
            entry=same_source_new_credit,
            source_roots=[source],
            storage=storage,
            observed_at=timezone.now(),
        )
    assert PersonMedia.objects.count() == 2


@pytest.mark.django_db(transaction=True)
def test_mismatch_refuses_to_overwrite_or_create_rows(tmp_path, image_entry):
    source, _, person, entry = image_entry
    root = tmp_path / "target"
    storage = FileSystemStorage(location=root)
    name = f"sha256/{entry['expected_sha256'][:2]}/{entry['expected_sha256']}.png"
    destination = root / name
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"different")
    with pytest.raises(ValueError, match="destination_bytes_mismatch"):
        ingest_image(
            person=person,
            entry=entry,
            source_roots=[source],
            storage=storage,
            observed_at=timezone.now(),
        )
    assert destination.read_bytes() == b"different"
    assert StaffMediaObject.objects.count() == PersonMedia.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_preview_checks_existing_bytes_and_does_not_write(tmp_path, image_entry):
    source, _, person, entry = image_entry
    root = tmp_path / "target"
    storage = FileSystemStorage(location=root)
    row, would_create = ingest_image(
        person=person,
        entry=entry,
        source_roots=[source],
        storage=storage,
        observed_at=timezone.now(),
        preview=True,
    )
    assert row is None and would_create
    assert StaffMediaObject.objects.count() == PersonMedia.objects.count() == 0
    name = f"sha256/{entry['expected_sha256'][:2]}/{entry['expected_sha256']}.png"
    destination = root / name
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"different")
    with pytest.raises(ValueError, match="destination_bytes_mismatch"):
        ingest_image(
            person=person,
            entry=entry,
            source_roots=[source],
            storage=storage,
            observed_at=timezone.now(),
            preview=True,
        )


@pytest.mark.django_db(transaction=True)
def test_unverified_identity_never_writes(tmp_path, image_entry):
    source, _, person, entry = image_entry
    entry.pop("identity_resolution")
    with pytest.raises(ValueError, match="verified_identity_evidence_required"):
        ingest_image(
            person=person,
            entry=entry,
            source_roots=[source],
            storage=FileSystemStorage(location=tmp_path / "target"),
            observed_at=timezone.now(),
        )
    assert StaffMediaObject.objects.count() == PersonMedia.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_unknown_source_and_credit_are_preserved_not_rejected(tmp_path, image_entry):
    source, _, person, entry = image_entry
    entry.pop("source_url")
    entry.pop("credit")
    row, created = ingest_image(
        person=person,
        entry=entry,
        source_roots=[source],
        storage=FileSystemStorage(location=tmp_path / "target"),
        observed_at=timezone.now(),
    )
    assert created and row.source_url == "" and row.evidence["credit"] == ""


@pytest.mark.django_db(transaction=True)
def test_malformed_source_accreditation_is_rejected(tmp_path, image_entry):
    source, _, person, entry = image_entry
    entry["recorded_accreditation"] = {"creator": "unexpected key"}
    with pytest.raises(ValueError, match="invalid_recorded_accreditation"):
        ingest_image(
            person=person,
            entry=entry,
            source_roots=[source],
            storage=FileSystemStorage(location=tmp_path / "target"),
            observed_at=timezone.now(),
        )
    assert StaffMediaObject.objects.count() == PersonMedia.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_mpo_preserves_original_frames_and_rejects_excessive_frame_count(
    tmp_path, image_entry
):
    source, _, person, entry = image_entry
    path = source / "original.mpo"
    output = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(
        output,
        format="MPO",
        save_all=True,
        append_images=[Image.new("RGB", (4, 4), "blue")],
    )
    data = output.getvalue()
    path.write_bytes(data)
    entry.update(
        file=str(path),
        expected_sha256=hashlib.sha256(data).hexdigest(),
        role="original-source-reference",
    )
    storage = FileSystemStorage(location=tmp_path / "target")
    row, created = ingest_image(
        person=person,
        entry=entry,
        source_roots=[source],
        storage=storage,
        observed_at=timezone.now(),
    )
    assert (
        created
        and row.media.media_type == "image/mpo"
        and row.media.storage_name.endswith(".mpo")
    )
    with storage.open(row.media.storage_name, "rb") as stream:
        assert stream.read() == data
    with Image.open(io.BytesIO(data)) as image:
        assert image.n_frames == 2
    output = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(
        output,
        format="MPO",
        save_all=True,
        append_images=[Image.new("RGB", (4, 4), "blue") for _ in range(10)],
    )
    path.write_bytes(output.getvalue())
    entry["expected_sha256"] = hashlib.sha256(output.getvalue()).hexdigest()
    with pytest.raises(ValueError, match="too_many_mpo_frames"):
        ingest_image(
            person=person,
            entry=entry,
            source_roots=[source],
            storage=storage,
            observed_at=timezone.now(),
        )
    assert PersonMedia.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_confirmed_name_alone_does_not_confirm_media(
    tmp_path, image_entry, monkeypatch
):
    from core.management.commands import ingest_g2_cast_assets

    source, _, person, entry = image_entry
    Language.objects.get_or_create(code="en")
    locale, _ = Locale.objects.get_or_create(code="en", defaults={"language_id": "en"})
    PersonName.objects.create(
        person=person,
        locale=locale,
        full_name="Example",
        review_status="confirmed",
        fingerprint="a" * 64,
    )
    entry["identity_resolution"]["confirmed_name"] = "Example"
    storage = FileSystemStorage(location=tmp_path / "target")
    storage.bucket_name = "test-bucket"
    monkeypatch.setattr(ingest_g2_cast_assets, "storages", {"staff_media": storage})
    batch = {
        "schema": "g2-cast-import-batch/v1",
        "target_database": connection.settings_dict["NAME"],
        "target_bucket": "test-bucket",
        "target_namespace": storage.location,
        "inventory_observed_at": timezone.now().isoformat(),
        "entries": [entry],
    }
    manifest = tmp_path / "batch.json"
    manifest.write_text(json.dumps(batch))
    with pytest.raises(CommandError, match="confirmed_name_does_not_verify_media"):
        call_command(
            "ingest_g2_cast_assets",
            manifest=str(manifest),
            source_root=[str(source)],
            expected_database=connection.settings_dict["NAME"],
            expected_bucket="test-bucket",
            receipt=str(tmp_path / "receipt.jsonl"),
            apply=True,
        )
    assert not PersonMedia.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_batch_preflights_every_entry_before_writing(
    tmp_path, image_entry, monkeypatch
):
    from core.management.commands import ingest_g2_cast_assets

    source, _, person, entry = image_entry
    Language.objects.get_or_create(code="en")
    locale, _ = Locale.objects.get_or_create(code="en", defaults={"language_id": "en"})
    name = PersonName.objects.create(
        person=person,
        locale=locale,
        full_name="Example",
        review_status="confirmed",
        fingerprint="a" * 64,
    )
    PersonNameEvidence.objects.create(
        name=name,
        source_kind="owner_supplied",
        source_reference="owner:cast",
        collection_method="explicit_owner_cast_selection",
        observed_at=timezone.now(),
        evidence_hash="b" * 64,
    )
    entry["identity_resolution"].update(
        method="owner_selected_cast",
        owner_selected_name="Example",
        owner_source_reference="owner:cast",
        source_pack_sha256="c" * 64,
    )
    storage = FileSystemStorage(location=tmp_path / "target")
    storage.bucket_name = "test-bucket"
    storage.location = str(tmp_path / "target")
    monkeypatch.setattr(ingest_g2_cast_assets, "storages", {"staff_media": storage})
    batch = {
        "schema": "g2-cast-import-batch/v1",
        "target_database": connection.settings_dict["NAME"],
        "target_bucket": "test-bucket",
        "target_namespace": storage.location,
        "inventory_observed_at": timezone.now().isoformat(),
        "entries": [entry, {**entry, "source_url": "not-a-url"}],
    }
    manifest = tmp_path / "batch.json"
    manifest.write_text(json.dumps(batch))
    arguments = {
        "manifest": str(manifest),
        "source_root": [str(source)],
        "expected_database": connection.settings_dict["NAME"],
        "expected_bucket": "test-bucket",
        "receipt": str(tmp_path / "receipt.jsonl"),
        "apply": True,
    }
    with pytest.raises(CommandError, match="invalid_source_url"):
        call_command("ingest_g2_cast_assets", **arguments)
    assert PersonMedia.objects.count() == StaffMediaObject.objects.count() == 0
    batch["entries"] = [entry, {**entry}]
    manifest.write_text(json.dumps(batch))
    arguments["receipt"] = str(tmp_path / "duplicate.jsonl")
    with pytest.raises(CommandError, match="duplicate_batch_attribution"):
        call_command("ingest_g2_cast_assets", **arguments)
    assert PersonMedia.objects.count() == StaffMediaObject.objects.count() == 0
    batch["entries"] = [entry]
    manifest.write_text(json.dumps(batch))
    arguments["receipt"] = str(tmp_path / "success.jsonl")
    call_command("ingest_g2_cast_assets", **arguments)
    assert PersonMedia.objects.count() == StaffMediaObject.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_interrupted_database_write_can_be_retried_and_shared_by_another_person(
    tmp_path, image_entry, monkeypatch
):
    source, data, person, entry = image_entry
    storage = FileSystemStorage(location=tmp_path / "target")
    original_create = StaffMediaObject.objects.create

    def fail_after_storage(**kwargs):
        raise RuntimeError("simulated database interruption")

    monkeypatch.setattr(StaffMediaObject.objects, "create", fail_after_storage)
    with pytest.raises(RuntimeError, match="simulated database interruption"):
        ingest_image(
            person=person,
            entry=entry,
            source_roots=[source],
            storage=storage,
            observed_at=timezone.now(),
        )
    assert StaffMediaObject.objects.count() == PersonMedia.objects.count() == 0
    name = f"sha256/{entry['expected_sha256'][:2]}/{entry['expected_sha256']}.png"
    with storage.open(name, "rb") as stream:
        assert stream.read() == data
    monkeypatch.setattr(StaffMediaObject.objects, "create", original_create)
    ingest_image(
        person=person,
        entry=entry,
        source_roots=[source],
        storage=storage,
        observed_at=timezone.now(),
    )
    other = Person.objects.create()
    other_entry = {
        **entry,
        "candidate_person_id": str(other.pk),
        "identity_resolution": {
            "state": "verified",
            "person_id": str(other.pk),
            "evidence": ["separate evidence"],
        },
    }
    ingest_image(
        person=other,
        entry=other_entry,
        source_roots=[source],
        storage=storage,
        observed_at=timezone.now(),
    )
    assert StaffMediaObject.objects.count() == 1
    assert PersonMedia.objects.count() == 2


@pytest.mark.django_db(transaction=True)
def test_video_is_preserved_and_invalid_container_is_rejected(tmp_path, image_entry):
    source, _, person, entry = image_entry

    def box(kind, payload):
        return struct.pack(">I4s", len(payload) + 8, kind) + payload

    data = box(b"ftyp", b"isom") + box(b"moov", b"metadata") + box(b"mdat", b"video")
    path = source / "clip.mp4"
    path.write_bytes(data)
    entry.update(
        file=str(path),
        expected_sha256=hashlib.sha256(data).hexdigest(),
        role="real-source-clip",
    )
    storage = FileSystemStorage(location=tmp_path / "target")
    row, created = ingest_video(
        person=person,
        entry=entry,
        source_roots=[source],
        storage=storage,
        observed_at=timezone.now(),
    )
    assert created and row.kind == "video" and row.media.media_type == "video/mp4"
    assert row.suitability == "pending" and row.reuse_status == "unknown"
    with storage.open(row.media.storage_name, "rb") as stream:
        assert stream.read() == data
    row_again, created = ingest_video(
        person=person,
        entry=entry,
        source_roots=[source],
        storage=storage,
        observed_at=timezone.now(),
    )
    assert not created and row_again.pk == row.pk
    bad = b"not an mp4"
    path.write_bytes(bad)
    entry["expected_sha256"] = hashlib.sha256(bad).hexdigest()
    with pytest.raises(ValueError, match="invalid MP4"):
        ingest_video(
            person=person,
            entry=entry,
            source_roots=[source],
            storage=storage,
            observed_at=timezone.now(),
        )
    assert PersonMedia.objects.count() == StaffMediaObject.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_batch_ingests_video_from_existing_storage(tmp_path, image_entry, monkeypatch):
    from core.management.commands import ingest_g2_cast_assets

    _, _, person, entry = image_entry
    Language.objects.get_or_create(code="en")
    locale, _ = Locale.objects.get_or_create(code="en", defaults={"language_id": "en"})
    name = PersonName.objects.create(
        person=person,
        locale=locale,
        full_name="Example",
        review_status="confirmed",
        fingerprint="a" * 64,
    )
    PersonNameEvidence.objects.create(
        name=name,
        source_kind="owner_supplied",
        source_reference="owner:cast",
        collection_method="explicit_owner_cast_selection",
        observed_at=timezone.now(),
        evidence_hash="b" * 64,
    )
    entry["identity_resolution"].update(
        method="owner_selected_cast",
        owner_selected_name="Example",
        owner_source_reference="owner:cast",
        source_pack_sha256="c" * 64,
    )
    data = b"".join(
        struct.pack(">I4s", 12, name) + b"data" for name in (b"ftyp", b"moov", b"mdat")
    )
    sha = hashlib.sha256(data).hexdigest()
    name = f"sha256/{sha[:2]}/{sha}.mp4"
    storage = FileSystemStorage(location=tmp_path / "target")
    storage.bucket_name = "test-bucket"
    from django.core.files.base import ContentFile

    storage.save(name, ContentFile(data))
    monkeypatch.setattr(ingest_g2_cast_assets, "storages", {"staff_media": storage})
    entry.update(media_kind="video", storage_name=name, expected_sha256=sha)
    batch = {
        "schema": "g2-cast-import-batch/v1",
        "target_database": connection.settings_dict["NAME"],
        "target_bucket": "test-bucket",
        "target_namespace": storage.location,
        "inventory_observed_at": timezone.now().isoformat(),
        "entries": [entry],
    }
    manifest = tmp_path / "batch.json"
    manifest.write_text(json.dumps(batch))
    call_command(
        "ingest_g2_cast_assets",
        manifest=str(manifest),
        from_existing_storage=True,
        expected_database=connection.settings_dict["NAME"],
        expected_bucket="test-bucket",
        receipt=str(tmp_path / "receipt.jsonl"),
        apply=True,
    )
    row = PersonMedia.objects.get()
    assert row.kind == "video" and row.media.storage_name == name
    assert row.media.byte_size == len(data)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("method", ["owner_selected_cast", "owner_confirmed_media"])
def test_owner_selected_cast_requires_the_same_recorded_source(
    tmp_path, image_entry, monkeypatch, method
):
    from core.management.commands import ingest_g2_cast_assets

    source, _, person, entry = image_entry
    Language.objects.get_or_create(code="en")
    locale, _ = Locale.objects.get_or_create(code="en", defaults={"language_id": "en"})
    name = PersonName.objects.create(
        person=person,
        locale=locale,
        full_name="Example",
        review_status="pending",
        fingerprint="a" * 64,
    )
    PersonNameEvidence.objects.create(
        name=name,
        source_kind="owner_supplied",
        source_reference="owner:cast",
        collection_method=(
            "explicit_owner_cast_selection"
            if method == "owner_selected_cast"
            else "explicit_owner_media_confirmation"
        ),
        observed_at=timezone.now(),
        evidence_hash="b" * 64,
    )
    entry["identity_resolution"].update(
        method=method,
        owner_selected_name="Example",
        recorded_name="Example",
        owner_source_reference="owner:wrong",
        source_pack_sha256="c" * 64,
    )
    storage = FileSystemStorage(location=tmp_path / "target")
    storage.bucket_name = "test-bucket"
    monkeypatch.setattr(ingest_g2_cast_assets, "storages", {"staff_media": storage})
    batch = {
        "schema": "g2-cast-import-batch/v1",
        "target_database": connection.settings_dict["NAME"],
        "target_bucket": "test-bucket",
        "target_namespace": storage.location,
        "inventory_observed_at": timezone.now().isoformat(),
        "entries": [entry],
    }
    manifest = tmp_path / "batch.json"
    manifest.write_text(json.dumps(batch))
    args = {
        "manifest": str(manifest),
        "source_root": [str(source)],
        "expected_database": connection.settings_dict["NAME"],
        "expected_bucket": "test-bucket",
        "receipt": str(tmp_path / "bad.jsonl"),
        "apply": True,
    }
    with pytest.raises(
        CommandError, match="owner_(cast|media)_identity_evidence_changed"
    ):
        call_command("ingest_g2_cast_assets", **args)
    assert PersonMedia.objects.count() == 0
    entry["identity_resolution"]["owner_source_reference"] = "owner:cast"
    manifest.write_text(json.dumps(batch))
    args["receipt"] = str(tmp_path / "good.jsonl")
    call_command("ingest_g2_cast_assets", **args)
    name.refresh_from_db()
    assert name.review_status == "pending" and PersonMedia.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_matched_source_requires_existing_name_evidence(
    tmp_path, image_entry, monkeypatch
):
    from core.management.commands import ingest_g2_cast_assets

    source, _, person, entry = image_entry
    Language.objects.get_or_create(code="en")
    locale, _ = Locale.objects.get_or_create(code="en", defaults={"language_id": "en"})
    name = PersonName.objects.create(
        person=person,
        locale=locale,
        full_name="Example",
        review_status="pending",
        fingerprint="a" * 64,
    )
    PersonNameEvidence.objects.create(
        name=name,
        source_kind="named_third_party",
        source_reference="https://example.org/person",
        collection_method="saved_source",
        observed_at=timezone.now(),
        evidence_hash="b" * 64,
    )
    entry["identity_resolution"].update(
        method="matched_source_evidence",
        source_name="Example",
        matched_source_reference="https://example.org/other",
        source_pack_sha256="c" * 64,
    )
    storage = FileSystemStorage(location=tmp_path / "target")
    storage.bucket_name = "test-bucket"
    monkeypatch.setattr(ingest_g2_cast_assets, "storages", {"staff_media": storage})
    batch = {
        "schema": "g2-cast-import-batch/v1",
        "target_database": connection.settings_dict["NAME"],
        "target_bucket": "test-bucket",
        "target_namespace": storage.location,
        "inventory_observed_at": timezone.now().isoformat(),
        "entries": [entry],
    }
    manifest = tmp_path / "batch.json"
    manifest.write_text(json.dumps(batch))
    args = {
        "manifest": str(manifest),
        "source_root": [str(source)],
        "expected_database": connection.settings_dict["NAME"],
        "expected_bucket": "test-bucket",
        "receipt": str(tmp_path / "bad.jsonl"),
        "apply": True,
    }
    with pytest.raises(CommandError, match="matched_identity_source_changed"):
        call_command("ingest_g2_cast_assets", **args)
    assert PersonMedia.objects.count() == 0
    entry["identity_resolution"]["matched_source_reference"] = (
        "https://example.org/person"
    )
    manifest.write_text(json.dumps(batch))
    args["receipt"] = str(tmp_path / "good.jsonl")
    call_command("ingest_g2_cast_assets", **args)
    name.refresh_from_db()
    assert name.review_status == "pending" and PersonMedia.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_corroboration_checks_name_and_organization_in_source(
    tmp_path, image_entry, monkeypatch
):
    from core.management.commands import ingest_g2_cast_assets

    source, _, person, entry = image_entry
    Language.objects.get_or_create(code="en")
    locale, _ = Locale.objects.get_or_create(code="en", defaults={"language_id": "en"})
    name = PersonName.objects.create(
        person=person,
        locale=locale,
        full_name="Example",
        review_status="pending",
        fingerprint="a" * 64,
    )
    PersonNameEvidence.objects.create(
        name=name,
        source_kind="employment_extraction",
        source_reference="https://example.org/person",
        source_text="Example founded Acme",
        collection_method="saved_source",
        observed_at=timezone.now(),
        evidence_hash="b" * 64,
    )
    entry["identity_resolution"].update(
        method="corroborated_name_context",
        source_name="Example",
        matched_source_reference="https://example.org/person",
        source_context="Example founded",
        source_context_term="OtherCo",
        source_pack_sha256="c" * 64,
    )
    storage = FileSystemStorage(location=tmp_path / "target")
    storage.bucket_name = "test-bucket"
    monkeypatch.setattr(ingest_g2_cast_assets, "storages", {"staff_media": storage})
    batch = {
        "schema": "g2-cast-import-batch/v1",
        "target_database": connection.settings_dict["NAME"],
        "target_bucket": "test-bucket",
        "target_namespace": storage.location,
        "inventory_observed_at": timezone.now().isoformat(),
        "entries": [entry],
    }
    manifest = tmp_path / "batch.json"
    manifest.write_text(json.dumps(batch))
    args = {
        "manifest": str(manifest),
        "source_root": [str(source)],
        "expected_database": connection.settings_dict["NAME"],
        "expected_bucket": "test-bucket",
        "receipt": str(tmp_path / "bad.jsonl"),
        "apply": True,
    }
    with pytest.raises(CommandError, match="corroborating_identity_source_changed"):
        call_command("ingest_g2_cast_assets", **args)
    assert PersonMedia.objects.count() == 0
    entry["identity_resolution"]["source_context_term"] = "Acme"
    manifest.write_text(json.dumps(batch))
    args["receipt"] = str(tmp_path / "good.jsonl")
    call_command("ingest_g2_cast_assets", **args)
    name.refresh_from_db()
    assert name.review_status == "pending" and PersonMedia.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_imports_share_one_object_and_attribution(tmp_path, image_entry):
    source, _, person, entry = image_entry
    barrier = threading.Barrier(2)

    def run():
        close_old_connections()
        try:
            target = Person.objects.get(pk=person.pk)
            barrier.wait(timeout=10)
            row, created = ingest_image(
                person=target,
                entry=entry,
                source_roots=[source],
                storage=FileSystemStorage(location=tmp_path / "target"),
                observed_at=timezone.now(),
            )
            return row.pk, created
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: run(), range(2)))
    assert results[0][0] == results[1][0]
    assert sorted(created for _, created in results) == [False, True]
    assert PersonMedia.objects.count() == StaffMediaObject.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_affiliation_corroboration_checks_target_and_source(
    tmp_path, image_entry, monkeypatch
):
    from core.management.commands import ingest_g2_cast_assets

    source, _, person, entry = image_entry
    Language.objects.get_or_create(code="en")
    locale, _ = Locale.objects.get_or_create(code="en", defaults={"language_id": "en"})
    PersonName.objects.create(
        person=person,
        locale=locale,
        full_name="Example",
        review_status="pending",
        fingerprint="a" * 64,
    )
    kind, _ = AffiliationType.objects.get_or_create(code="employment")
    brand = Brand.objects.create(nickname="acme-test", display_name="Acme")
    affiliation = PersonBrandAffiliation.objects.create(
        person=person,
        brand=brand,
        affiliation_type_reference=kind,
        observed_organization_name="Acme",
        claim_identity="b" * 64,
    )
    post = Post.objects.create(tweet_id="123456789", text="Example joined Acme")
    PersonBrandAffiliationEvidence.objects.create(
        affiliation=affiliation,
        source_post=post,
        observed_at=timezone.now(),
        extraction_method="structured_text",
        evidence_hash="c" * 64,
    )
    entry["identity_resolution"].update(
        method="corroborated_affiliation_source",
        source_name="Example",
        source_post_id="123456789",
        source_context="Example joined",
        source_context_term="OtherCo",
        source_pack_sha256="d" * 64,
    )
    storage = FileSystemStorage(location=tmp_path / "target")
    storage.bucket_name = "test-bucket"
    monkeypatch.setattr(ingest_g2_cast_assets, "storages", {"staff_media": storage})
    batch = {
        "schema": "g2-cast-import-batch/v1",
        "target_database": connection.settings_dict["NAME"],
        "target_bucket": "test-bucket",
        "target_namespace": storage.location,
        "inventory_observed_at": timezone.now().isoformat(),
        "entries": [entry],
    }
    manifest = tmp_path / "batch.json"
    manifest.write_text(json.dumps(batch))
    args = {
        "manifest": str(manifest),
        "source_root": [str(source)],
        "expected_database": connection.settings_dict["NAME"],
        "expected_bucket": "test-bucket",
        "receipt": str(tmp_path / "bad.jsonl"),
        "apply": True,
    }
    with pytest.raises(CommandError, match="corroborating_affiliation_source_changed"):
        call_command("ingest_g2_cast_assets", **args)
    assert PersonMedia.objects.count() == 0
    entry["identity_resolution"]["source_context_term"] = "Acme"
    manifest.write_text(json.dumps(batch))
    args["receipt"] = str(tmp_path / "good.jsonl")
    call_command("ingest_g2_cast_assets", **args)
    assert PersonMedia.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_confirmed_name_match_also_requires_same_person_affiliation(
    tmp_path, image_entry, monkeypatch
):
    from core.management.commands import ingest_g2_cast_assets

    source, _, person, entry = image_entry
    Language.objects.get_or_create(code="en")
    locale, _ = Locale.objects.get_or_create(code="en", defaults={"language_id": "en"})
    name = PersonName.objects.create(
        person=person,
        locale=locale,
        full_name="Example",
        review_status="confirmed",
        fingerprint="a" * 64,
    )
    PersonNameEvidence.objects.create(
        name=name,
        source_kind="saved_dossier",
        source_reference="https://example.org/person",
        collection_method="saved_source",
        observed_at=timezone.now(),
        evidence_hash="c" * 64,
    )
    kind, _ = AffiliationType.objects.get_or_create(code="employment")
    brand = Brand.objects.create(nickname="acme-test", display_name="Acme")
    PersonBrandAffiliation.objects.create(
        person=person,
        brand=brand,
        affiliation_type_reference=kind,
        observed_organization_name="Acme",
        claim_identity="b" * 64,
    )
    entry["identity_resolution"].update(
        method="confirmed_name_and_affiliation",
        confirmed_name="Example",
        matched_source_reference="https://example.org/person",
        organization="OtherCo",
        source_pack_sha256="d" * 64,
    )
    storage = FileSystemStorage(location=tmp_path / "target")
    storage.bucket_name = "test-bucket"
    monkeypatch.setattr(ingest_g2_cast_assets, "storages", {"staff_media": storage})
    batch = {
        "schema": "g2-cast-import-batch/v1",
        "target_database": connection.settings_dict["NAME"],
        "target_bucket": "test-bucket",
        "target_namespace": storage.location,
        "inventory_observed_at": timezone.now().isoformat(),
        "entries": [entry],
    }
    manifest = tmp_path / "batch.json"
    manifest.write_text(json.dumps(batch))
    args = {
        "manifest": str(manifest),
        "source_root": [str(source)],
        "expected_database": connection.settings_dict["NAME"],
        "expected_bucket": "test-bucket",
        "receipt": str(tmp_path / "bad.jsonl"),
        "apply": True,
    }
    with pytest.raises(CommandError, match="confirmed_name_affiliation_changed"):
        call_command("ingest_g2_cast_assets", **args)
    assert PersonMedia.objects.count() == 0
    entry["identity_resolution"]["organization"] = "Acme"
    manifest.write_text(json.dumps(batch))
    args["receipt"] = str(tmp_path / "good.jsonl")
    call_command("ingest_g2_cast_assets", **args)
    assert PersonMedia.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_owner_review_is_bound_to_exact_person_account_and_asset(
    tmp_path, image_entry, monkeypatch
):
    from core.management.commands import ingest_g2_cast_assets

    source, _, person, entry = image_entry
    Language.objects.get_or_create(code="en")
    locale, _ = Locale.objects.get_or_create(code="en", defaults={"language_id": "en"})
    PersonName.objects.create(
        person=person,
        locale=locale,
        full_name="Example",
        review_status="pending",
        fingerprint="a" * 64,
    )
    account = Account.objects.create(author_id="7654321", handle="reviewed_example")
    link = PersonAccount.objects.create(
        person=person,
        account=account,
        resolution_status="pending",
        first_observed_at=timezone.now(),
        last_observed_at=timezone.now(),
    )
    parent_file = source / "parent.png"
    parent_buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "blue").save(parent_buffer, "PNG")
    parent_data = parent_buffer.getvalue()
    parent_file.write_bytes(parent_data)
    parent_sha = hashlib.sha256(parent_data).hexdigest()
    entry["parent_sha256"] = parent_sha
    entry["identity_resolution"].update(
        method="owner_reviewed_candidate",
        candidate_name="Example",
        candidate_account_id=str(account.pk),
        source_pack_sha256="b" * 64,
        owner_decision_sha256="c" * 64,
        review_artifact_sha256="d" * 64,
        reviewed_asset_sha256="e" * 64,
    )
    storage = FileSystemStorage(location=tmp_path / "target")
    storage.bucket_name = "test-bucket"
    monkeypatch.setattr(ingest_g2_cast_assets, "storages", {"staff_media": storage})
    batch = {
        "schema": "g2-cast-import-batch/v1",
        "target_database": connection.settings_dict["NAME"],
        "target_bucket": "test-bucket",
        "target_namespace": storage.location,
        "inventory_observed_at": timezone.now().isoformat(),
        "entries": [entry],
    }
    manifest = tmp_path / "batch.json"
    manifest.write_text(json.dumps(batch))
    args = {
        "manifest": str(manifest),
        "source_root": [str(source)],
        "expected_database": connection.settings_dict["NAME"],
        "expected_bucket": "test-bucket",
        "receipt": str(tmp_path / "bad.jsonl"),
        "apply": True,
    }
    with pytest.raises(CommandError, match="owner_reviewed_candidate_changed"):
        call_command("ingest_g2_cast_assets", **args)
    assert PersonMedia.objects.count() == 0
    entry["identity_resolution"]["reviewed_asset_sha256"] = entry["expected_sha256"]
    manifest.write_text(json.dumps(batch))
    args["receipt"] = str(tmp_path / "good.jsonl")
    call_command("ingest_g2_cast_assets", **args)
    link.refresh_from_db()
    assert link.resolution_status == "pending"
    assert PersonMedia.objects.count() == 1
    child_sha = entry["expected_sha256"]
    parent = {
        **entry,
        "file": str(parent_file),
        "expected_sha256": parent_sha,
        "parent_sha256": None,
        "source_child_sha256": child_sha,
        "identity_resolution": {
            **entry["identity_resolution"],
            "method": "owner_reviewed_parent",
            "source_parent_sha256": "f" * 64,
        },
    }
    batch["entries"] = [parent]
    manifest.write_text(json.dumps(batch))
    args["receipt"] = str(tmp_path / "bad-parent.jsonl")
    with pytest.raises(CommandError, match="owner_reviewed_candidate_changed"):
        call_command("ingest_g2_cast_assets", **args)
    assert PersonMedia.objects.count() == 1
    parent["identity_resolution"]["source_parent_sha256"] = parent_sha
    parent["source_child_sha256"] = "f" * 64
    manifest.write_text(json.dumps(batch))
    args["receipt"] = str(tmp_path / "wrong-child.jsonl")
    with pytest.raises(CommandError, match="parent_lineage_not_established"):
        call_command("ingest_g2_cast_assets", **args)
    parent["source_child_sha256"] = child_sha
    manifest.write_text(json.dumps(batch))
    args["receipt"] = str(tmp_path / "good-parent.jsonl")
    call_command("ingest_g2_cast_assets", **args)
    assert (
        PersonMedia.objects.get(media_id=parent_sha).evidence["source_child_sha256"]
        == child_sha
    )


@pytest.mark.django_db(transaction=True)
def test_profile_corroboration_requires_named_snapshot_and_matching_person(
    tmp_path, image_entry, monkeypatch
):
    from core.management.commands import ingest_g2_cast_assets

    source, _, person, entry = image_entry
    Language.objects.get_or_create(code="en")
    locale, _ = Locale.objects.get_or_create(code="en", defaults={"language_id": "en"})
    name = PersonName.objects.create(
        person=person,
        locale=locale,
        full_name="Example",
        review_status="pending",
        fingerprint="a" * 64,
    )
    account = Account.objects.create(author_id="7654321", handle="profile_example")
    link = PersonAccount.objects.create(
        person=person,
        account=account,
        resolution_status="pending",
        first_observed_at=timezone.now(),
        last_observed_at=timezone.now(),
    )
    snapshot = AccountProfileSnapshot.objects.create(
        account=account,
        profile_hash="b" * 64,
        first_observed_at=timezone.now(),
        last_observed_at=timezone.now(),
        first_source_kind="post",
        display_name="Example",
    )
    PersonNameEvidence.objects.create(
        name=name,
        source_kind="employment_extraction",
        source_reference=f"profile-snapshot:{snapshot.pk}",
        source_text="Researcher at Acme",
        collection_method="fixture",
        observed_at=timezone.now(),
        evidence_hash="c" * 64,
    )
    entry["identity_resolution"].update(
        method="corroborated_profile_source",
        source_profile_snapshot_id=snapshot.pk,
        candidate_account_id=str(account.pk),
        source_name="Example",
        source_context_term="OtherCo",
        source_pack_sha256="d" * 64,
    )
    storage = FileSystemStorage(location=tmp_path / "target")
    storage.bucket_name = "test-bucket"
    monkeypatch.setattr(ingest_g2_cast_assets, "storages", {"staff_media": storage})
    batch = {
        "schema": "g2-cast-import-batch/v1",
        "target_database": connection.settings_dict["NAME"],
        "target_bucket": "test-bucket",
        "target_namespace": storage.location,
        "inventory_observed_at": timezone.now().isoformat(),
        "entries": [entry],
    }
    manifest = tmp_path / "batch.json"
    manifest.write_text(json.dumps(batch))
    args = {
        "manifest": str(manifest),
        "source_root": [str(source)],
        "expected_database": connection.settings_dict["NAME"],
        "expected_bucket": "test-bucket",
        "receipt": str(tmp_path / "bad.jsonl"),
        "apply": True,
    }
    with pytest.raises(CommandError, match="corroborating_profile_source_changed"):
        call_command("ingest_g2_cast_assets", **args)
    assert PersonMedia.objects.count() == 0
    entry["identity_resolution"]["source_context_term"] = "Acme"
    manifest.write_text(json.dumps(batch))
    args["receipt"] = str(tmp_path / "good.jsonl")
    call_command("ingest_g2_cast_assets", **args)
    link.refresh_from_db()
    assert link.resolution_status == "pending" and PersonMedia.objects.count() == 1
