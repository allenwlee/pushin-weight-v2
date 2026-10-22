"""Record explicitly supported citizenship without interpreting nationality prose."""

from django.db import transaction

from core.models import (
    Country,
    Person,
    PersonCitizenship,
    PersonCitizenshipEvidence,
    PersonText,
)


@transaction.atomic
def record_citizenship(
    person_id, *, country_code: str, person_text_id: int,
    is_primary: bool | None = None,
) -> PersonCitizenship:
    person = Person.objects.select_for_update().get(pk=person_id)
    if person.merged_into_id is not None:
        raise ValueError("Record citizenship on the canonical person")
    country = Country.objects.get(pk=country_code)
    source = PersonText.objects.get(pk=person_text_id)
    if source.person_id != person.pk or source.origin != "source":
        raise ValueError("Citizenship needs source evidence from the same person")
    existing = PersonCitizenship.objects.filter(
        person=person, country=country
    ).first()
    if existing is not None:
        if is_primary is not None and existing.is_primary != is_primary:
            raise ValueError("Change the primary citizenship in a reviewed correction")
        PersonCitizenshipEvidence.objects.get_or_create(
            citizenship=existing, person_text=source
        )
        return existing
    if is_primary is None:
        is_primary = not PersonCitizenship.objects.filter(person=person).exists()
    row = PersonCitizenship.objects.create(
        person=person, country=country, is_primary=is_primary
    )
    PersonCitizenshipEvidence.objects.create(citizenship=row, person_text=source)
    return row
