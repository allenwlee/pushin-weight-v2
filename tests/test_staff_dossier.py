import io
import uuid
from pathlib import Path

import pytest
from django.core.management import call_command
from django.utils import timezone

from core.models import (
    Person,
    PersonMedia,
    PersonName,
    StaffCollectionWork,
    StaffProviderRequest,
)
from core.person_names import record_name
from core.staff_assets.dossier import dossier_records, export_dossier
from core.staff_assets.intake import ingest_record
from core.staff_assets.manifest import from_deepseek_dossier
from core.staff_assets.queue import enqueue
from core.staff_assets.worker import run_once
from tests.test_staff_library import record

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_export_has_sources_roles_and_no_invented_photo_or_join_date(
    settings, tmp_path
):
    settings.STORAGES = {
        **settings.STORAGES,
        "staff_media": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": str(tmp_path)},
        },
    }
    data = record()
    data["names"][0]["full_name"] = '<script>alert("unsafe")</script>'
    ingest_record(data)
    result = export_dossier(brand_id="deepseek", output=tmp_path / "export")
    html = Path(result["output"]).read_text()
    assert result["people"] == 1 and result["portrait_gaps"] == 1
    assert "&lt;script&gt;" in html
    assert "研究员" in html and "北京" in html
    assert "Name source" in html and "No completed Chinese-web search recorded" in html
    assert "Source-verified portrait needed" in html


def test_adapter_keeps_profile_location_separate_and_excludes_contributors():
    owner = {
        "id": "fixture-staff",
        "name": "Test Worker",
        "location": "Beijing",
        "joined": None,
        "bio": "An English summary of a Chinese page",
        "bio_source": "https://example.com",
        "deepseek": {
            "observed_at": "2026-10-01T00:00:00Z",
            "source": "https://example.com",
            "source_language": "zh-Hans",
            "title_original": "研究员",
            "staff_eligibility": {
                "included": True,
                "view": "current",
                "reason": "Employment wording",
                "source": "https://example.com",
            },
        },
        "presentation": {
            "fields": {
                "romanized_name": {
                    "value": "Test Worker",
                    "status": "Owner-supplied profile",
                    "source": "https://example.com",
                }
            }
        },
    }
    excluded = {
        **owner,
        "id": "contributor",
        "deepseek": {**owner["deepseek"], "staff_eligibility": {"included": False}},
    }
    result = from_deepseek_dossier({"people": [owner, excluded]})["people"]
    assert "location" not in result[0]["affiliations"][0]
    assert "start_date" not in result[0]["affiliations"][0]
    assert result[0]["names"][0]["origin"] == "owner"
    assert result[0]["texts"] == []  # a summary is not original Chinese text
    assert result[1]["eligibility"] == "unestablished" and result[1]["names"] == []


def test_later_account_observation_preserves_dossier():
    data = record()
    data["affiliations"][0]["titles"] = [{"language": "zh-Hans", "text": "研究员",
                                          "source_reference": "https://example.com/bio"}]
    intake, _ = ingest_record(
        record(
            affiliations=data["affiliations"],
            texts=[{"kind": "location", "language": "en", "text": "Beijing", "source_reference": "https://example.com/profile"}],
            source_dossier={
                "location": "Beijing",
                "presentation": {
                    "fields": {
                        "job_title_zh": {
                            "value": "研究员",
                            "source": "https://example.com/bio",
                        }
                    },
                    "chinese_web": {
                        "attempts": [
                            {"query": "测试人 DeepSeek", "provider": "SerpApi"}
                        ]
                    },
                },
            }
        )
    )
    ingest_record(
        record(
            source_key="account-only:later",
            person_id=str(intake.person_id),
            eligibility="db_staff",
            names=[],
            affiliations=[],
        )
    )
    result = dossier_records(brand_id="deepseek")[0]
    assert result["titles"][0]["value"] == "研究员"
    assert result["titles"][0]["source"] == "https://example.com/bio"
    assert result["profile_location"] == "Beijing"
    assert result["searches"][0]["query"] == "测试人 DeepSeek"


def test_review_command_previews_then_selects_and_retains_history():
    person = Person.objects.create(display_name="Test")
    name = record_name(
        person,
        full_name="Test",
        language="en",
        source_kind="owner",
        source_reference="owner:session",
        source_text="Test",
        collection_method="manual",
    )
    options = {
        "status": "confirmed",
        "select": "english",
        "reviewer": "Allen",
        "reason": "Named profile",
        "stdout": io.StringIO(),
    }
    call_command("review_staff_collection", "name", str(name.pk), **options)
    name.refresh_from_db()
    assert name.review_status == "pending"
    call_command("review_staff_collection", "name", str(name.pk), apply=True, **options)
    person.refresh_from_db()
    assert person.english_name_id == name.pk
    call_command(
        "review_staff_collection",
        "name",
        str(name.pk),
        status="rejected",
        reviewer="Allen",
        reason="Wrong record",
        apply=True,
        stdout=io.StringIO(),
    )
    person.refresh_from_db()
    assert person.english_name_id is None
    assert len(PersonName.objects.get(pk=name.pk).review_history) == 2


def test_worker_network_activation_requires_explicit_configuration(settings):
    from django.core.management.base import CommandError

    settings.STAFF_COLLECTION_NETWORK_ENABLED = False
    with pytest.raises(CommandError, match="NETWORK_ENABLED"):
        call_command("run_staff_collection_worker", once=True, enable_network=True)
    assert not StaffProviderRequest.objects.exists()


def test_search_summary_comes_from_provider_requests():
    intake, _ = ingest_record(
        record(
            source_dossier={
                "presentation": {
                    "chinese_web": {"summary": "No completed search recorded."}
                }
            }
        )
    )
    person = intake.person
    assert (
        dossier_records(brand_id="deepseek")[0]["search_summary"]
        == "No completed search recorded."
    )
    for state, response, fingerprint in (
        ("complete", {"organic_results": [{}, {}]}, "a" * 64),
        ("needs_review", {}, "b" * 64),
        ("reserved", {}, "c" * 64),
    ):
        StaffProviderRequest.objects.create(
            person=person,
            provider="serpapi",
            fingerprint=fingerprint,
            run_id=uuid.uuid4(),
            parameters={"q": "测试人 DeepSeek"},
            state=state,
            response=response,
        )
    summary = dossier_records(brand_id="deepseek")[0]["search_summary"]
    assert summary == (
        "serpapi search completed (2 results); "
        "serpapi search needs review; "
        "serpapi search completion unconfirmed."
    )
    assert "No completed search recorded." not in summary


def test_export_preserves_uncertainty_after_interrupted_provider_request(
    settings, tmp_path
):
    settings.STORAGES = {
        **settings.STORAGES,
        "staff_media": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": str(tmp_path / "media")},
        },
    }

    class Interrupted(BaseException):
        pass

    class Provider:
        name = "serpapi"
        calls = 0

        def search(self, parameters):
            self.calls += 1
            raise Interrupted("Process stopped after sending the request")

    ingest_record(record(baidu_eligible=True, baidu_query="测试人 DeepSeek"))
    provider = Provider()
    with pytest.raises(Interrupted):
        run_once(
            run_id=uuid.uuid4(),
            provider=provider,
            allow_network=True,
            per_person=1,
            per_run=1,
            per_day=1,
        )
    assert provider.calls == 1
    assert StaffProviderRequest.objects.get().state == "reserved"
    call_command(
        "export_staff_dossier",
        brand="deepseek",
        output=str(tmp_path),
        stdout=io.StringIO(),
    )
    html = (tmp_path / "index.html").read_text()
    assert "serpapi search completion unconfirmed." in html
    assert "serpapi search not run." not in html
    assert "reserved" in html


def test_requeue_retries_unavailable_media_without_stored_bytes():
    person = Person.objects.create(display_name="Test")
    work = enqueue(person.pk, {"version": "requeue-media"})
    StaffCollectionWork.objects.filter(pk=work.pk).update(state="needs_evidence")
    missing = PersonMedia.objects.create(
        person=person,
        fingerprint="missing-bytes",
        source_url="https://example.com/bio",
        original_url="https://example.com/photo.png",
        source_kind="company_bio",
        availability="unavailable",
        observed_at=timezone.now(),
    )
    call_command(
        "review_staff_collection",
        "work",
        str(work.pk),
        reviewer="Allen",
        reason="Storage restored",
        apply=True,
        stdout=io.StringIO(),
    )
    missing.refresh_from_db()
    work.refresh_from_db()
    assert work.state == "queued"
    assert missing.availability == "unfetched"


def test_requeue_preserves_work_and_operator_reason():
    person = Person.objects.create(display_name="Test")
    work = enqueue(person.pk, {})
    StaffCollectionWork.objects.filter(pk=work.pk).update(state="needs_evidence")
    call_command(
        "review_staff_collection",
        "work",
        str(work.pk),
        reviewer="Allen",
        reason="New source provided",
        apply=True,
        stdout=io.StringIO(),
    )
    work.refresh_from_db()
    assert work.state == "queued"
    assert work.result["requeue_reviews"][-1]["reason"] == "New source provided"
