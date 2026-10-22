"""Historical-to-reference upgrades preserve source meaning and retry identity."""

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
BASE = ("core", "0135_rg4_business_catalogues_expand")
NAME_CUTOVER = ("core", "0136_rg4_person_name_kind_cutover")


@pytest.mark.parametrize("migration_rehearsal_schema", [BASE], indirect=True)
def test_person_name_cutover_preserves_fingerprints_and_both_writer_generations(
    migration_rehearsal_schema,
):
    old = MigrationExecutor(connection).loader.project_state([BASE]).apps
    old.get_model("core", "Language").objects.get_or_create(code="und")
    old.get_model("core", "Locale").objects.get_or_create(
        code="und",
        defaults={"language_id": "und"},
    )
    person = old.get_model("core", "Person").objects.create()
    old_names = old.get_model("core", "PersonName")
    original = old_names.objects.create(
        person=person,
        full_name="Name from source",
        locale_id="und",
        name_type="professional",
        fingerprint="a" * 64,
    )
    unsupported = old_names.objects.create(
        person=person,
        full_name="Another source spelling",
        locale_id="und",
        name_type="not_registered",
        fingerprint="b" * 64,
    )
    before = list(old_names.objects.order_by("id").values())
    with pytest.raises(RuntimeError, match="Unmapped person name kinds"):
        MigrationExecutor(connection).migrate([NAME_CUTOVER])
    assert list(old_names.objects.order_by("id").values()) == before
    assert NAME_CUTOVER not in MigrationExecutor(connection).loader.applied_migrations

    # Remove only this deliberate failure fixture before rehearsing known input.
    unsupported.delete()
    before = old_names.objects.get(pk=original.pk)
    MigrationExecutor(connection).migrate([NAME_CUTOVER])
    current = MigrationExecutor(connection).loader.project_state([NAME_CUTOVER]).apps
    names = current.get_model("core", "PersonName")
    migrated = names.objects.get(pk=original.pk)
    assert migrated.name_type_reference.code == "professional"
    assert migrated.fingerprint == before.fingerprint
    assert migrated.full_name == before.full_name
    assert migrated.created_at == before.created_at
    assert migrated.updated_at == before.updated_at

    # A still-running preceding image supplies only the retired scalar.
    legacy = old_names.objects.create(
        person=person,
        full_name="Romanized spelling",
        locale_id="und",
        name_type="romanized",
        fingerprint="c" * 64,
    )
    assert names.objects.get(pk=legacy.pk).name_type_reference.code == "romanized"

    # The new production caller supplies only the FK; its hash keeps the exact
    # pre-cutover string serialization, so a retry returns the same name.
    from core.models import Person
    from core.person_names import digest, record_name

    live_person = Person.objects.get(pk=person.pk)
    kwargs = {
        "full_name": "New writer spelling",
        "language": "und",
        "name_type": "professional",
        "source_kind": "owner",
        "source_reference": "test:name-kind",
        "source_text": "New writer spelling",
        "collection_method": "manual",
    }
    created = record_name(live_person, **kwargs)
    assert record_name(live_person, **kwargs).pk == created.pk
    assert created.fingerprint == digest(
        {
            "full_name": kwargs["full_name"],
            "language": "und",
            "name_type": "professional",
            "origin": "source",
            "derived_from_id": None,
        }
    )
    with connection.cursor() as cursor:
        cursor.execute("SELECT name_type FROM people_names WHERE id=%s", [created.pk])
        assert cursor.fetchone() == ("professional",)
    with pytest.raises(IntegrityError), transaction.atomic():
        old_names.objects.filter(pk=original.pk).update(name_type="romanized")
    assert names.objects.get(pk=original.pk).fingerprint == "a" * 64
