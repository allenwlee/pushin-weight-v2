from pathlib import Path
from uuid import uuid4

import pytest
from django.db import connection, transaction
from django.utils import timezone

from core.models import (
    Person,
    PersonIdentityCorrection,
    PersonMedia,
    PersonTextTranslation,
    StaffCollectionWork,
    StaffIntake,
    StaffMediaObject,
    StaffProviderRequest,
)
from core.person_names import record_name, review_name, select_names
from core.person_text import record_text
from scripts.staging_refresh.database import scrub_candidate_data
from scripts.staging_refresh.policy import load_policy


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_scrub_keeps_selected_names_and_prose_without_replaying_staff_work():
    policy = load_policy(
        Path(__file__).resolve().parents[2] / "config/staging_refresh.yaml"
    )
    person = Person.objects.create(display_name="Yuchen Zhao")
    name = record_name(
        person,
        full_name="Yuchen Zhao",
        language="en",
        source_kind="personal_site",
        source_reference="https://example.org/team/yuchen",
        source_text="Yuchen Zhao",
        collection_method="fixture",
    )
    review_name(name, "confirmed", "test reviewer", "Named professional biography")
    select_names(person, primary=name, english=name)
    original = record_text(
        person,
        kind="biography",
        language="zh-Hans",
        text="人工智能研究员",
        source_reference="https://example.org/team/yuchen",
    )
    translation = PersonTextTranslation.objects.create(
        original=original,
        language="en",
        text="AI researcher",
        provider="fixture",
        model="fixture",
        prompt_version="fixture-v1",
    )
    PersonIdentityCorrection.objects.create(
        source=person,
        target=person,
        kind="confirm_account",
        reviewer="test reviewer",
        reason="Private review note",
        request_key="staging-staff-scrub",
    )
    StaffIntake.objects.create(
        source_key="pending:fixture",
        fingerprint="a" * 64,
        eligibility="needs_review",
        payload={"private_observation": True},
        observed_at=timezone.now(),
    )
    work = StaffCollectionWork.objects.create(person=person, fingerprint="b" * 64)
    StaffProviderRequest.objects.create(
        person=person,
        work=work,
        provider="fixture",
        fingerprint="c" * 64,
        run_id=uuid4(),
    )
    media = StaffMediaObject.objects.create(
        sha256="d" * 64,
        storage_name="production-only/image.jpg",
        media_type="image/jpeg",
        byte_size=100,
    )
    PersonMedia.objects.create(
        person=person,
        media=media,
        fingerprint="e" * 64,
        source_url="https://example.org/team/yuchen",
        source_kind="personal_site",
        observed_at=timezone.now(),
        availability="available",
    )

    with transaction.atomic(), connection.cursor() as cursor:
        scrub_candidate_data(cursor, policy)

    person.refresh_from_db()
    original.refresh_from_db()
    translation.refresh_from_db()
    assert person.primary_name_id == person.english_name_id == name.pk
    assert name.evidence.get().source_text == "Yuchen Zhao"
    assert original.text == "人工智能研究员"
    assert translation.text == "AI researcher"
    for model in (
        PersonIdentityCorrection,
        PersonMedia,
        StaffCollectionWork,
        StaffIntake,
        StaffMediaObject,
        StaffProviderRequest,
    ):
        assert not model.objects.exists(), model._meta.db_table
