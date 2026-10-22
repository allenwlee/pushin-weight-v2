"""Citizenship needs explicit Country identity and same-person source evidence."""

import pytest
from django.db import IntegrityError, transaction

from core.intelligence_readers import person_intelligence
from core.models import PersonCitizenship, PersonCitizenshipEvidence, PersonText
from core.person_citizenship import record_citizenship
from core.person_text import record_text
from tests.person_factory import person_with_name

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_evidenced_dual_citizenship_and_ambiguous_nationality_remain_distinct(
    company_country_catalogue,
):
    person = person_with_name("Person", nationality="possibly Japanese")
    assert person_intelligence(person.pk)["person"]["citizenships"] == []
    assert person_intelligence(person.pk)["person"]["nationality"] == (
        "possibly Japanese"
    )
    legacy_text = PersonText.objects.get(
        person=person, kind="reported_nationality"
    )
    with pytest.raises(ValueError, match="source evidence"):
        record_citizenship(
            person.pk, country_code="GB", person_text_id=legacy_text.pk
        )
    source = record_text(
        person, kind="reported_nationality", language="en",
        text="Holds Japanese and US citizenship",
        source_reference="https://example.test/verified-bio",
    )
    japan = record_citizenship(
        person.pk, country_code="JP", person_text_id=source.pk
    )
    usa = record_citizenship(
        person.pk, country_code="US", person_text_id=source.pk
    )
    assert japan.is_primary and not usa.is_primary
    assert record_citizenship(
        person.pk, country_code="US", person_text_id=source.pk
    ).pk == usa.pk
    assert person_intelligence(person.pk)["person"]["citizenships"] == [
        {"country_code": "JP", "is_primary": True},
        {"country_code": "US", "is_primary": False},
    ]
    assert person_intelligence(person.pk)["person"]["nationality"] == (
        "possibly Japanese"
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        PersonCitizenship.objects.create(
            person=person, country_id="GB", is_primary=True
        )
    other = person_with_name("Other person")
    other_source = record_text(
        other, kind="reported_nationality", language="en",
        text="British", source_reference="https://example.test/other",
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        PersonCitizenshipEvidence.objects.create(
            citizenship=japan, person_text=other_source
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        PersonCitizenshipEvidence.objects.filter(
            citizenship=usa, person_text=source
        ).delete()
    with pytest.raises(IntegrityError), transaction.atomic():
        PersonText.objects.filter(pk=source.pk).update(origin="unknown")
    with pytest.raises(IntegrityError), transaction.atomic():
        unsupported = PersonCitizenship.objects.create(
            person=person, country_id="GB"
        )
        PersonCitizenshipEvidence.objects.create(
            citizenship=unsupported, person_text=legacy_text
        )


def test_citizenship_cannot_exist_without_evidence(company_country_catalogue):
    person = person_with_name("Unsupported")
    with pytest.raises(IntegrityError), transaction.atomic():
        PersonCitizenship.objects.create(
            person=person, country_id="JP", is_primary=True
        )
