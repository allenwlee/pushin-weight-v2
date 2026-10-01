"""Names are sourced representations, never an identity matching key."""

import pytest
from django.db import IntegrityError, transaction

from core.models import Person, PersonName
from core.person_names import record_name, review_name, select_names

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def name(person, full_name="李元", **kwargs):
    return record_name(
        person,
        full_name=full_name,
        language="zh-Hans",
        source_kind="owner",
        source_reference="owner:2026-10-01",
        source_text=full_name,
        collection_method="manual",
        **kwargs,
    )


def test_homonyms_do_not_merge_and_components_require_evidence():
    a = Person.objects.create(display_name="Ryan Lee")
    b = Person.objects.create(display_name="Another Li")
    first = name(a)
    assert name(b).person_id != first.person_id
    assert first.given_name is None and first.family_name is None
    with pytest.raises(ValueError, match="supports_fields"):
        name(a, given_name="元")
    assert name(a).pk == first.pk
    assert first.evidence.count() == 1


def test_selection_requires_review_and_preserves_derived_origin():
    person = Person.objects.create(display_name="Ryan Lee")
    original = name(person)
    with pytest.raises(ValueError, match="confirmed"):
        select_names(person, primary=original)
    review_name(original, "confirmed", "Allen", "Owner supplied Chinese name")
    english = record_name(
        person,
        full_name="Li Yuan",
        language="en",
        name_type="romanized",
        origin="generated",
        derived_from=original,
        source_kind="conversion",
        source_reference="pinyin:manual",
        source_text="李元",
        collection_method="manual",
    )
    review_name(english, "confirmed", "Allen", "Corroborated on public speaker bio")
    select_names(person, primary=original, english=english)
    english.refresh_from_db()
    assert english.origin == "generated"
    assert english.derived_from_id == original.pk
    assert english.review_history[-1]["reason"].startswith("Corroborated")
    review_name(english, "rejected", "Allen", "Incorrect reading")
    person.refresh_from_db()
    assert person.english_name_id is None


def test_database_rejects_cross_person_selection_and_derivation():
    a = Person.objects.create(display_name="A")
    b = Person.objects.create(display_name="B")
    original = name(a)
    review_name(original, "confirmed", "Allen", "Owner observation")
    with pytest.raises(IntegrityError), transaction.atomic():
        Person.objects.filter(pk=b.pk).update(primary_name=original)
    with pytest.raises(IntegrityError), transaction.atomic():
        PersonName.objects.create(
            person=b,
            full_name="Li Yuan",
            language="en",
            fingerprint="x" * 64,
            derived_from=original,
        )


def test_additional_evidence_does_not_rewrite_original():
    person = Person.objects.create(display_name="Ryan Lee")
    original = name(person)
    record_name(
        person,
        full_name="李元",
        language="zh-Hans",
        source_kind="speaker_bio",
        source_reference="https://example.com/speaker",
        source_text="李元 MiniMax",
        collection_method="web",
    )
    assert original.evidence.count() == 2
