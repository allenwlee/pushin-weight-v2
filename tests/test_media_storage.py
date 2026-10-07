"""Private R2 configuration and non-destructive staff-media migration."""

import hashlib
import io
import json
from urllib.parse import parse_qs, urlsplit

import pytest
from botocore.exceptions import ClientError
from botocore.stub import Stubber
from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.core.management import call_command
from django.core.management.base import CommandError


@pytest.fixture
def r2_settings(settings):
    settings.R2_ACCOUNT_ID = "a" * 32
    settings.R2_ACCESS_KEY_ID = "test-access-key"
    settings.R2_SECRET_ACCESS_KEY = "test-secret-key"
    return settings


def test_r2_uses_explicit_credentials_and_private_signed_urls(r2_settings):
    from core.media_storage import PrivateR2Storage

    storage = PrivateR2Storage(bucket_name="test-media", location="staff")
    parts = urlsplit(storage.url("sha256/example.jpg"))
    query = parse_qs(parts.query)
    assert parts.scheme == "https"
    assert parts.hostname == "a" * 32 + ".r2.cloudflarestorage.com"
    assert parts.path == "/test-media/staff/sha256/example.jpg"
    assert query["X-Amz-Expires"] == ["300"]
    assert query["X-Amz-Credential"][0].startswith("test-access-key/")
    assert query["X-Amz-Signature"]
    assert query["response-cache-control"] == ["private, no-store"]
    assert storage.default_acl is None
    assert storage.file_overwrite is True


def test_r2_never_falls_back_to_an_aws_credential(r2_settings):
    from core.media_storage import PrivateR2Storage

    r2_settings.R2_ACCESS_KEY_ID = ""
    r2_settings.AWS_ACCESS_KEY_ID = "unrelated-project"
    with pytest.raises(ImproperlyConfigured, match="R2_ACCESS_KEY_ID"):
        PrivateR2Storage(bucket_name="test-media")


@pytest.mark.parametrize(
    "overrides",
    [
        {"querystring_auth": False},
        {"custom_domain": "public.example.com"},
        {"default_acl": "public-read"},
        {"object_parameters": {"ACL": "public-read"}},
        {"endpoint_url": "https://unrelated.example.com"},
        {"querystring_expire": 3600},
        {"verify": False},
    ],
)
def test_r2_rejects_configuration_that_weakens_private_delivery(r2_settings, overrides):
    from core.media_storage import PrivateR2Storage

    with pytest.raises(ImproperlyConfigured):
        PrivateR2Storage(bucket_name="test-media", **overrides)


def test_r2_does_not_allow_callers_to_extend_url_lifetime(r2_settings):
    from core.media_storage import PrivateR2Storage

    storage = PrivateR2Storage(bucket_name="test-media")
    with pytest.raises(ValueError, match="300"):
        storage.url("example.jpg", expire=301)


@pytest.mark.parametrize(
    "overrides",
    [
        {"access_key": ""},
        {"secret_key": ""},
        {"access_key": "unrelated-project"},
        {"security_token": "unrelated-token"},
    ],
)
def test_r2_rejects_overrides_of_its_explicit_credentials(r2_settings, overrides):
    from core.media_storage import PrivateR2Storage

    with pytest.raises(ImproperlyConfigured):
        PrivateR2Storage(bucket_name="test-media", **overrides)


def test_r2_conditional_copy_cannot_replace_an_existing_object(r2_settings):
    from core.media_storage import PrivateR2Storage

    storage = PrivateR2Storage(bucket_name="test-media", location="staff")
    params = {
        "Bucket": "test-media",
        "Key": "staff/sha256/existing.jpg",
        "Body": b"verified image",
        "ContentLength": 14,
        "ContentType": "image/jpeg",
        "CacheControl": "private, no-store",
        "IfNoneMatch": "*",
    }
    with Stubber(storage.connection.meta.client) as api:
        api.add_response("put_object", {}, params)
        api.add_client_error(
            "put_object",
            "PreconditionFailed",
            http_status_code=412,
            expected_params=params,
        )
        api.add_client_error(
            "put_object",
            "AccessDenied",
            http_status_code=403,
            expected_params=params,
        )
        assert (
            storage.save_if_absent(
                "sha256/existing.jpg", b"verified image", content_type="image/jpeg"
            )
            is True
        )
        assert (
            storage.save_if_absent(
                "sha256/existing.jpg", b"verified image", content_type="image/jpeg"
            )
            is False
        )
        with pytest.raises(ClientError):
            storage.save_if_absent(
                "sha256/existing.jpg", b"verified image", content_type="image/jpeg"
            )
        api.assert_no_pending_responses()


@pytest.fixture
def media_files(tmp_path, settings):
    source = tmp_path / "source"
    source.mkdir()
    target = FileSystemStorage(location=tmp_path / "target")
    settings.STORAGES = {
        **settings.STORAGES,
        "staff_media": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": target.location},
        },
    }
    return source, target


def make_object(source, data=b"existing verified media"):
    from core.models import StaffMediaObject

    sha = hashlib.sha256(data).hexdigest()
    name = f"sha256/{sha[:2]}/{sha}.jpg"
    path = source / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    row = StaffMediaObject.objects.create(
        sha256=sha,
        storage_name=name,
        byte_size=len(data),
        media_type="image/jpeg",
        width=24,
        height=32,
    )
    return row, data


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_migration_preview_copy_replay_and_verification_preserve_database(media_files):
    from core.models import StaffMediaObject
    from core.staff_assets.transfer import transfer_staff_media

    source, target = media_files
    row, data = make_object(source)
    original = list(StaffMediaObject.objects.values())
    preview = transfer_staff_media(source_root=source, storage=target)
    assert preview["planned"] == 1 and not target.exists(row.storage_name)
    applied = transfer_staff_media(source_root=source, storage=target, apply=True)
    assert applied["copied"] == applied["verified"] == 1
    assert applied["verified_bytes"] == len(data)
    repeated = transfer_staff_media(source_root=source, storage=target, apply=True)
    assert repeated["copied"] == 0 and repeated["verified"] == 1
    verified = transfer_staff_media(storage=target, verify_only=True)
    assert verified["verified"] == 1 and not verified["errors"]
    assert verified["inventory_sha256"] == applied["inventory_sha256"]
    assert list(StaffMediaObject.objects.values()) == original
    assert (source / row.storage_name).read_bytes() == data


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_migration_refuses_to_replace_a_different_existing_object(media_files):
    from core.staff_assets.transfer import transfer_staff_media

    source, target = media_files
    row, _ = make_object(source)
    target.save(row.storage_name, ContentFile(b"different object"))
    result = transfer_staff_media(source_root=source, storage=target, apply=True)
    assert result["copied"] == 0 and result["errors"]
    with target.open(row.storage_name) as stream:
        assert stream.read() == b"different object"


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_migration_refuses_corrupt_or_missing_source_without_writing(media_files):
    from core.staff_assets.transfer import transfer_staff_media

    source, target = media_files
    row, _ = make_object(source)
    (source / row.storage_name).write_bytes(b"corrupt source")
    result = transfer_staff_media(source_root=source, storage=target, apply=True)
    assert result["errors"] and not target.exists(row.storage_name)
    (source / row.storage_name).unlink()
    result = transfer_staff_media(source_root=source, storage=target, apply=True)
    assert result["errors"] and not target.exists(row.storage_name)


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_verification_detects_missing_files_and_command_exits_nonzero(media_files):
    source, _ = media_files
    make_object(source)
    output = io.StringIO()
    with pytest.raises(CommandError, match="verification"):
        call_command("migrate_staff_media", verify_only=True, stdout=output)
    result = json.loads(output.getvalue())
    assert result["errors"] and result["verified"] == 0


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_migration_rejects_paths_outside_the_source_and_self_copy(media_files):
    from core.staff_assets.transfer import transfer_staff_media

    source, target = media_files
    row, _ = make_object(source)
    row.storage_name = "../outside.jpg"
    row.save(update_fields=["storage_name"])
    result = transfer_staff_media(source_root=source, storage=target, apply=True)
    assert result["errors"] and result["copied"] == 0
    with pytest.raises(ValueError, match="same"):
        transfer_staff_media(
            source_root=source, storage=FileSystemStorage(location=source)
        )


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_migration_resumes_after_partial_storage_failure(media_files, monkeypatch):
    from core.staff_assets.transfer import transfer_staff_media

    source, target = media_files
    make_object(source, b"first object")
    second, _ = make_object(source, b"second object")
    save = target.save

    def unavailable(name, content, **kwargs):
        if name == second.storage_name:
            raise OSError("temporary destination failure")
        return save(name, content, **kwargs)

    monkeypatch.setattr(target, "save", unavailable)
    first = transfer_staff_media(source_root=source, storage=target, apply=True)
    assert first["copied"] == 1 and len(first["errors"]) == 1
    monkeypatch.setattr(target, "save", save)
    resumed = transfer_staff_media(source_root=source, storage=target, apply=True)
    assert resumed["copied"] == 1 and resumed["verified"] == 2
    assert not resumed["errors"]


@pytest.mark.requires_postgres
@pytest.mark.django_db
@pytest.mark.parametrize("same_bytes", [True, False])
def test_migration_verifies_a_concurrent_r2_winner(
    media_files, r2_settings, monkeypatch, same_bytes
):
    from core.media_storage import PrivateR2Storage
    from core.staff_assets.transfer import transfer_staff_media

    source, files = media_files
    row, data = make_object(source)
    winner = data if same_bytes else b"a different concurrent object"
    files.save(row.storage_name, ContentFile(winner))
    storage = PrivateR2Storage(bucket_name="test-media", location="staff")
    # The destination appears after HEAD reported a missing object. Its bytes
    # remain independently readable after the conditional PUT loses the race.
    monkeypatch.setattr(storage, "exists", lambda name: False)
    monkeypatch.setattr(storage, "size", files.size)
    monkeypatch.setattr(storage, "open", files.open)
    with Stubber(storage.connection.meta.client) as api:
        api.add_client_error(
            "put_object",
            "PreconditionFailed",
            http_status_code=412,
            expected_params={
                "Bucket": "test-media",
                "Key": f"staff/{row.storage_name}",
                "Body": data,
                "ContentLength": len(data),
                "ContentType": row.media_type,
                "CacheControl": "private, no-store",
                "IfNoneMatch": "*",
            },
        )
        result = transfer_staff_media(source_root=source, storage=storage, apply=True)
        api.assert_no_pending_responses()
    assert result["copied"] == 0
    assert result["verified"] == int(same_bytes)
    assert bool(result["errors"]) is not same_bytes
    with files.open(row.storage_name) as stream:
        assert stream.read() == winner


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_migration_rejects_overwriting_filesystem_configuration(media_files):
    from core.staff_assets.transfer import transfer_staff_media

    source, target = media_files
    row, _ = make_object(source)
    unsafe = FileSystemStorage(location=target.location, allow_overwrite=True)
    result = transfer_staff_media(source_root=source, storage=unsafe, apply=True)
    assert result["errors"][0]["error"] == "destination_does_not_support_safe_copy"
    assert not unsafe.exists(row.storage_name)


def test_cross_service_probe_validates_bytes_and_preserves_the_proof(
    media_files, monkeypatch
):
    _, target = media_files
    writer = io.StringIO()
    monkeypatch.setenv("RENDER_SERVICE_ID", "test-web")
    call_command(
        "check_media_storage", storage="staff_media", write=True, stdout=writer
    )
    receipt = json.loads(writer.getvalue())
    reader = io.StringIO()
    monkeypatch.setenv("RENDER_SERVICE_ID", "test-worker")
    call_command(
        "check_media_storage",
        storage="staff_media",
        probe_id=receipt["probe_id"],
        expected_sha256=receipt["sha256"],
        stdout=reader,
    )
    verified = json.loads(reader.getvalue())
    assert verified["writer_service"] == "test-web"
    assert verified["reader_service"] == "test-worker"
    assert verified["verified"] and target.exists(receipt["key"])
    with pytest.raises(CommandError, match="verification"):
        call_command(
            "check_media_storage",
            storage="staff_media",
            probe_id=receipt["probe_id"],
            expected_sha256="0" * 64,
        )
