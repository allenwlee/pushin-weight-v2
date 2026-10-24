"""Rehearse shared-place creation without advancing the shared public schema."""

import pytest
from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
BASE = ("core", "0147_rg4_restore_selected_scalar_fields")
TARGET = ("core", "0148_rg4_geolocation_owners")


@pytest.mark.parametrize("migration_rehearsal_schema", [BASE], indirect=True)
def test_new_geography_owners_import_beside_preserved_legacy_data(migration_rehearsal_schema):
    from core.geolocations import import_geonames_documents, load_pinned_geonames

    old = MigrationExecutor(connection).loader.project_state([BASE]).apps
    Country = old.get_model("core", "Country")
    before = list(Country.objects.order_by("pk").values())
    assert before
    MigrationExecutor(connection).migrate([TARGET])
    current = MigrationExecutor(connection).loader.project_state([TARGET]).apps
    assert current.get_model("core", "Geolocation").objects.count() == 0
    documents, metadata, roots = load_pinned_geonames(settings.BASE_DIR / "data" / "geonames")
    identities = import_geonames_documents(documents, country_metadata=metadata, selected_ids=roots)
    assert identities[203312] and identities[1835841]
    assert list(Country.objects.order_by("pk").values()) == before
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM geolocations WHERE geonames_id=ANY(%s)", [[203312, 1835841]])
        assert cursor.fetchone() == (2,)
        cursor.execute("SELECT confkey FROM pg_constraint WHERE conrelid='geolocation_alternate_names'::regclass AND confrelid='geolocations'::regclass")
        assert cursor.fetchall() == [([1],)]
