import io
import json
import socket
import uuid
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone
from PIL import Image, UnidentifiedImageError

from core.models import (
    Account,
    Brand,
    BrandAccount,
    Person,
    PersonBrandAffiliation,
    PersonMedia,
    PersonName,
    Role,
    StaffCollectionWork,
    StaffIntake,
    StaffMediaObject,
    StaffProviderRequest,
    TwitterListMembership,
)
from core.person_text import record_text, translate_text
from core.staff_assets.arrivals import catch_up
from core.staff_assets.intake import ingest_record
from core.staff_assets.manifest import import_manifest
from core.staff_assets.media import (
    local_bytes,
    media_storage,
    public_addresses,
    record_media,
    store_image,
)
from core.staff_assets.population import staff_population
from core.staff_assets.queue import claim, enqueue, finish
from core.staff_assets.worker import run_once

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def staff_storage(settings, tmp_path):
    settings.STORAGES = {
        **settings.STORAGES,
        "staff_media": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": str(tmp_path / "stored")},
        },
    }
    return tmp_path


def record(**changes):
    Brand.objects.get_or_create(
        nickname="deepseek", defaults={"display_name": "DeepSeek"}
    )
    return {
        "source_key": "official:example:001",
        "display_name": "Test Person",
        "eligibility": "staff",
        "observed_at": "2026-10-01T00:00:00Z",
        "names": [
            {
                "full_name": "测试人",
                "language": "zh-Hans",
                "source_kind": "personal_website",
                "source_reference": "https://example.com/person",
                "source_text": "测试人",
                "collection_method": "manual",
                "selection": "primary",
                "review": {
                    "status": "confirmed",
                    "reviewer": "fixture",
                    "reason": "Bilingual personal bio",
                },
            }
        ],
        "affiliations": [
            {
                "brand_id": "deepseek",
                "status": "current",
                "title_raw": "研究员",
                "location": "北京",
                "source_url": "https://example.com/person",
                "evidence_text": "目前在 DeepSeek 北京工作",
            }
        ],
        **changes,
    }


def png_bytes():
    data = io.BytesIO()
    Image.new("RGB", (24, 32), "navy").save(data, format="PNG")
    return data.getvalue()


def test_accountless_repeat_import_preserves_original_and_role_location(staff_storage):
    row = record()
    manifest = {"schema": "staff-intake/v1", "people": [row]}
    preview = import_manifest(manifest)
    assert preview["counts"] == {"create": 1}
    assert not Person.objects.exists() and not StaffIntake.objects.exists()
    import_manifest(manifest, apply=True)
    counts = (
        Person.objects.count(),
        PersonName.objects.count(),
        PersonBrandAffiliation.objects.count(),
        StaffCollectionWork.objects.count(),
    )
    import_manifest(manifest, apply=True)
    assert counts == (1, 1, 1, 1)
    assert counts == (
        Person.objects.count(),
        PersonName.objects.count(),
        PersonBrandAffiliation.objects.count(),
        StaffCollectionWork.objects.count(),
    )
    person = Person.objects.get()
    assert person.primary_name.full_name == "测试人"
    assert not person.account_links.exists()
    assert person.brand_affiliations.get().location == "北京"


def test_contributor_is_accounted_for_without_person_or_work():
    intake, _ = ingest_record(record(eligibility="unestablished", affiliations=[]))
    assert intake.person_id is None and not StaffCollectionWork.objects.exists()
    assert not Person.objects.exists()


def test_transaction_rollback_does_not_enqueue():
    row = record()
    with pytest.raises(RuntimeError), transaction.atomic():
        ingest_record(row)
        assert not StaffCollectionWork.objects.exists()
        raise RuntimeError("roll back")
    assert not StaffCollectionWork.objects.exists() and not Person.objects.exists()


def test_population_union_and_bulk_write_catchup():
    brand, _ = Brand.objects.get_or_create(
        nickname="deepseek", defaults={"display_name": "DeepSeek"}
    )
    staff, _ = Role.objects.get_or_create(key="staff")
    official, _ = Role.objects.get_or_create(key="official")
    accounts = [
        Account.objects.create(author_id=f"union-{n}", display_name=f"Member {n}")
        for n in range(4)
    ]
    # Bulk writes deliberately bypass arrival signals.
    BrandAccount.objects.bulk_create(
        [
            BrandAccount(brand=brand, account=accounts[0], role=staff),
            BrandAccount(brand=brand, account=accounts[1], role=staff),
            BrandAccount(brand=brand, account=accounts[2], role=official),
        ]
    )
    TwitterListMembership.objects.bulk_create(
        [
            TwitterListMembership(list_id=12, account=accounts[n], source="fixture")
            for n in (0, 2, 3)
        ]
    )
    population = staff_population(list_id=12)
    assert {entry["account_id"] for entry in population["accounts"]} == {
        "union-0",
        "union-1",
        "union-3",
    }
    assert population["excluded_official_accounts"] == ["union-2"]
    assert population["overlap_accounts"] == 1
    catch_up(list_id=12)
    assert Person.objects.count() == 3
    work_count = StaffCollectionWork.objects.count()
    catch_up(list_id=12)
    assert StaffCollectionWork.objects.count() == work_count == 3


def test_manual_role_writer_queues_only_after_commit():
    brand, _ = Brand.objects.get_or_create(
        nickname="deepseek", defaults={"display_name": "DeepSeek"}
    )
    staff, _ = Role.objects.get_or_create(key="staff")
    account = Account.objects.create(
        author_id="manual-added", display_name="Manual Person"
    )
    with transaction.atomic():
        BrandAccount.objects.create(brand=brand, account=account, role=staff)
        assert not StaffCollectionWork.objects.exists()
    assert StaffCollectionWork.objects.count() == 1


def test_media_dedup_keeps_attributions_and_avatar_is_not_a_portrait(staff_storage):
    root = staff_storage
    (root / "portrait.png").write_bytes(png_bytes())
    person = Person.objects.create(display_name="Image subject")
    for source in ("https://example.com/a", "https://example.com/b"):
        record_media(
            person,
            {
                "path": "portrait.png",
                "source_url": source,
                "source_kind": "x_account",
                "kind": "avatar",
            },
            asset_root=root,
        )
    assert StaffMediaObject.objects.count() == 1
    assert PersonMedia.objects.count() == 2
    assert not PersonMedia.objects.filter(source_verified=True).exists()
    with pytest.raises(UnidentifiedImageError):
        store_image(b"<html>not an image</html>")


def test_path_escape_and_private_network_are_rejected(staff_storage, monkeypatch):
    root = staff_storage / "assets"
    root.mkdir()
    private = staff_storage / "outside.png"
    private.write_bytes(png_bytes())
    (root / "link.png").symlink_to(private)
    for path in ("../outside.png", "link.png", str(private)):
        with pytest.raises(ValueError, match="escapes"):
            local_bytes(root, path)
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))
        ],
    )
    with pytest.raises(ValueError, match="Non-public"):
        public_addresses("https://example.com/a.png")


def test_store_image_restores_missing_bytes(staff_storage):
    data = png_bytes()
    obj = store_image(data)
    media_storage().delete(obj.storage_name)
    restored = store_image(data)
    assert restored.pk == obj.pk
    with media_storage().open(restored.storage_name, "rb") as stored:
        assert stored.read() == data
    assert StaffMediaObject.objects.count() == 1


def test_reimport_restores_missing_bytes(staff_storage):
    (staff_storage / "portrait.png").write_bytes(png_bytes())
    person = Person.objects.create(display_name="Subject")
    entry = {
        "path": "portrait.png",
        "source_url": "https://example.com/bio",
        "source_kind": "company_bio",
        "kind": "image",
    }
    row = record_media(person, entry, asset_root=staff_storage)
    media_storage().delete(row.media.storage_name)
    restored = record_media(person, entry, asset_root=staff_storage)
    assert restored.pk == row.pk
    assert restored.availability == "available"
    with media_storage().open(restored.media.storage_name, "rb") as stored:
        assert stored.read() == png_bytes()
    assert StaffMediaObject.objects.count() == 1
    assert PersonMedia.objects.count() == 1


def test_lease_contention_expiry_and_stale_results():
    person = Person.objects.create(display_name="Leased")
    enqueue(person.pk, {"version": 1})
    work = claim()
    assert claim() is None
    StaffCollectionWork.objects.filter(pk=work.pk).update(
        lease_expires_at=timezone.now() - timedelta(seconds=1)
    )
    replacement = claim()
    assert replacement.pk == work.pk and replacement.lease_token != work.lease_token
    assert not finish(work, state="complete")
    assert finish(replacement, state="needs_evidence")


class Provider:
    name = "fixture"

    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    def search(self, parameters):
        self.calls += 1
        if self.fail:
            raise TimeoutError("secret must not reach logs")
        return {
            "organic_results": [
                {
                    "link": "https://example.com/person",
                    "title": "Researcher",
                    "thumbnail": "https://example.com/photo.png",
                }
            ],
            "search_parameters": {"api_key": "private"},
        }


def test_paid_journal_dedup_budget_and_no_implicit_china_route(staff_storage):
    person = Person.objects.create(display_name="Staff")
    provider = Provider()
    run_id = uuid.uuid4()
    enqueue(person.pk, {"baidu_eligible": True, "baidu_query": "测试人 DeepSeek"})
    run_once(
        run_id=run_id,
        provider=provider,
        allow_network=True,
        per_person=2,
        per_run=1,
        per_day=1,
        fetcher=lambda url: png_bytes(),
    )
    assert provider.calls == 1
    request = StaffProviderRequest.objects.get()
    assert request.state == "complete" and "private" not in json.dumps(request.response)
    enqueue(
        person.pk,
        {"baidu_eligible": True, "baidu_query": "测试人 DeepSeek", "revision": 2},
    )
    run_once(
        run_id=run_id,
        provider=provider,
        allow_network=True,
        per_person=2,
        per_run=1,
        per_day=1,
    )
    assert provider.calls == 1
    enqueue(person.pk, {"baidu_eligible": True, "baidu_query": "different query"})
    assert (
        run_once(
            run_id=run_id,
            provider=provider,
            allow_network=True,
            per_person=2,
            per_run=1,
            per_day=1,
        )["error"]
        == "budget_exhausted"
    )
    other = Person.objects.create(display_name="中文名字")
    enqueue(other.pk, {"baidu_query": "中文名字"})
    run_once(
        run_id=run_id,
        provider=provider,
        allow_network=True,
        per_person=2,
        per_run=1,
        per_day=1,
    )
    assert provider.calls == 1


def _unfetched_media(person, url):
    return PersonMedia.objects.create(
        person=person,
        fingerprint=url,
        source_url="https://example.com/bio",
        original_url=url,
        source_kind="company_bio",
        kind="image",
        availability="unfetched",
        observed_at=timezone.now(),
    )


def test_transient_download_stays_unfetched_and_retries_until_three_attempts():
    person = Person.objects.create(display_name="Retry")
    enqueue(person.pk, {"version": "download"})
    row = _unfetched_media(person, "https://example.com/photo.png")

    def fail(url):
        raise OSError("timed out")

    first = run_once(run_id=uuid.uuid4(), allow_network=True, fetcher=fail)
    row.refresh_from_db()
    work = StaffCollectionWork.objects.get(person=person)
    assert first["state"] == "retry_due"
    assert row.availability == "unfetched" and row.media_id is None
    assert work.attempts == 1
    StaffCollectionWork.objects.filter(pk=work.pk).update(
        attempts=2, state="retry_due", next_attempt_at=timezone.now()
    )
    second = run_once(run_id=uuid.uuid4(), allow_network=True, fetcher=fail)
    row.refresh_from_db()
    work.refresh_from_db()
    assert second["state"] == "needs_review"
    assert work.attempts == 3
    assert row.availability == "unfetched" and row.media_id is None


def test_unsupported_image_and_decompression_bomb_stay_unavailable():
    person = Person.objects.create(display_name="Bad image")
    enqueue(person.pk, {"version": "bad-image"})
    unsupported = _unfetched_media(person, "https://example.com/not-image")
    bomb = _unfetched_media(person, "https://example.com/bomb")

    def fetch(url):
        if url.endswith("/bomb"):
            raise Image.DecompressionBombError("too many pixels")
        data = io.BytesIO()
        Image.new("RGB", (8, 8), "red").save(data, format="BMP")
        return data.getvalue()

    result = run_once(run_id=uuid.uuid4(), allow_network=True, fetcher=fetch)
    unsupported.refresh_from_db()
    bomb.refresh_from_db()
    assert unsupported.availability == "unavailable"
    assert bomb.availability == "unavailable"
    assert result["state"] == "needs_evidence"
    assert result["unavailable"] == 2


def test_interrupted_paid_request_is_not_automatically_retried():
    person = Person.objects.create(display_name="Staff")
    provider = Provider(fail=True)
    enqueue(person.pk, {"baidu_eligible": True, "baidu_query": "Staff DeepSeek"})
    options = {
        "run_id": uuid.uuid4(),
        "provider": provider,
        "allow_network": True,
        "per_person": 3,
        "per_run": 3,
        "per_day": 3,
    }
    assert run_once(**options)["state"] == "needs_review"
    enqueue(
        person.pk,
        {"baidu_eligible": True, "baidu_query": "Staff DeepSeek", "new_evidence": True},
    )
    assert run_once(**options)["state"] == "needs_review"
    assert provider.calls == 1


def test_original_prose_and_translation_versions_survive_failure():
    person = Person.objects.create(display_name="Writer")
    first = record_text(
        person,
        kind="biography",
        language="zh-Hans",
        text="研究员",
        source_reference="https://example.com",
    )
    calls = []

    def translator(**kwargs):
        calls.append(kwargs)
        return "Researcher"

    options = {
        "language": "en",
        "provider": "fixture",
        "model": "fixture",
        "prompt_version": "1",
        "translator": translator,
    }
    translated = translate_text(first, **options)
    assert translate_text(first, **options).pk == translated.pk and len(calls) == 1
    second = record_text(
        person,
        kind="biography",
        language="zh-Hans",
        text="高级研究员",
        source_reference="https://example.com",
    )
    with pytest.raises(ValueError):
        translate_text(second, **{**options, "translator": lambda **kwargs: ""})
    assert (
        person.texts.count() == 2
        and first.translations.count() == 1
        and second.translations.count() == 0
    )


def test_preview_command_does_not_mutate(staff_storage):
    path = staff_storage / "manifest.json"
    path.write_text(json.dumps({"schema": "staff-intake/v1", "people": [record()]}))
    output = io.StringIO()
    call_command("import_staff_manifest", str(path), stdout=output)
    assert not Person.objects.exists()
    assert json.loads(output.getvalue())["applied"] is False
