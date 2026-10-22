"""Small database fixtures for a person with an unreviewed default spelling."""

from core.models import Person
from core.person_names import record_legacy_display_name
from core.person_text import record_text


def person_with_name(name: str, **fields) -> Person:
    reported_nationality = fields.pop("nationality", None)
    person = Person.objects.create(**fields)
    record_legacy_display_name(person, name)
    if reported_nationality:
        record_text(
            person, kind="reported_nationality", language="und",
            text=reported_nationality, source_reference="test:reported-nationality",
            origin="unknown",
        )
    return person
