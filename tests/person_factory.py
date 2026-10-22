"""Small database fixtures for a person with an unreviewed default spelling."""

from core.models import Person
from core.person_names import record_legacy_display_name


def person_with_name(name: str, **fields) -> Person:
    person = Person.objects.create(**fields)
    record_legacy_display_name(person, name)
    return person
