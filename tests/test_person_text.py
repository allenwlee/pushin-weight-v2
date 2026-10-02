import pytest
from django.db import IntegrityError, transaction

from core.models import PersonText, StaffIntake
from core.person_text import record_text
from core.staff_assets.dossier import dossier_records, export_dossier
from core.staff_assets.intake import ingest_record
from tests.test_person_affiliations import replace, role
from tests.test_staff_library import record

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_two_jobs_keep_separate_titles_and_translation_sources(tmp_path, settings):
    settings.STORAGES = {**settings.STORAGES, "staff_media": {
        "BACKEND": "django.core.files.storage.FileSystemStorage", "OPTIONS": {"location": str(tmp_path)}}}
    intake, _ = ingest_record(record(source_dossier={"presentation": {"fields": {
        "job_title_zh": {"value": "过时标题", "source": "https://old.example"}}}}))
    first = intake.person.brand_affiliations.get()
    second = role(intake.person, title="工程主管")
    original = record_text(intake.person, affiliation=second, kind="title", language="zh-Hans",
                           text="工程主管", source_reference="https://new.example/bio",
                           review_status="confirmed", review_note="Official bio")
    record_text(intake.person, affiliation=second, kind="title", language="en", text="Engineering lead",
                source_reference="https://new.example/bio", origin="translation", derived_from=original,
                review_status="confirmed", review_note="Reviewed translation")
    first_title = record_text(intake.person, affiliation=first, kind="title", language="zh-Hans",
                              text="研究员", source_reference="https://example.com/person")
    assert first_title.affiliation_id != original.affiliation_id
    result = dossier_records(brand_id="deepseek")[0]
    assert {row["value"] for row in result["titles"]} >= {"研究员", "工程主管", "Engineering lead"}
    assert "过时标题" not in {row["value"] for row in result["titles"]}
    html = (tmp_path / "export" / "index.html")
    export_dossier(brand_id="deepseek", output=html.parent)
    assert "translation" in html.read_text() and "https://new.example/bio" in html.read_text()


def test_new_job_conclusion_overrides_old_intake_presentation():
    intake, _ = ingest_record(record(source_dossier={"presentation": {"fields": {
        "job_title_zh": {"value": "旧研究员", "source": "https://example.com"}}}}))
    old = intake.person.brand_affiliations.get()
    new = role(intake.person, title="研究主管")
    record_text(intake.person, affiliation=new, kind="title", language="zh-Hans", text="研究主管",
                source_reference="https://new.example")
    replace(old, new)
    titles = dossier_records(brand_id="deepseek")[0]["titles"]
    assert any(row["value"] == "研究主管" for row in titles)
    assert not any(row["value"] == "旧研究员" for row in titles)


def test_original_prose_and_intake_version_cannot_be_rewritten():
    intake, _ = ingest_record(record())
    original = record_text(intake.person, kind="biography", language="zh-Hans", text="原文",
                           source_reference="https://example.com")
    with pytest.raises(IntegrityError), transaction.atomic():
        PersonText.objects.filter(pk=original.pk).update(text="替换原文")
    with pytest.raises(IntegrityError), transaction.atomic():
        StaffIntake.objects.filter(pk=intake.pk).update(payload={"erased": True})


def test_title_requires_its_own_person_affiliation():
    intake, _ = ingest_record(record())
    other, _ = ingest_record(record(source_key="other"))
    with pytest.raises(ValueError, match="same person"):
        record_text(intake.person, affiliation=other.person.brand_affiliations.get(), kind="title",
                    language="zh-Hans", text="研究员", source_reference="https://example.com")


def test_name_selection_mirrors_legacy_columns_and_demotion_clears_them():
    from core.person_names import review_name
    intake, _ = ingest_record(record())
    person = intake.person
    person.refresh_from_db()
    assert person.display_name == person.display_name_zh_cn == "测试人"
    review_name(person.primary_name, "rejected", "Allen", "Wrong identity")
    person.refresh_from_db()
    assert person.display_name == "Unreviewed person" and person.display_name_zh_cn is None
    assert person.names.get().full_name == "测试人"


def test_database_checks_both_sides_of_affiliation_text_ownership():
    intake, _ = ingest_record(record())
    other, _ = ingest_record(record(source_key="other"))
    affiliation = intake.person.brand_affiliations.get()
    original = record_text(intake.person, affiliation=affiliation, kind="title", language="zh-Hans",
                           text="研究员", source_reference="https://example.com")
    with pytest.raises(IntegrityError), transaction.atomic():
        PersonText.objects.filter(pk=original.pk).update(person=other.person)
    with pytest.raises(IntegrityError), transaction.atomic():
        type(affiliation).objects.filter(pk=affiliation.pk).update(person=other.person)
