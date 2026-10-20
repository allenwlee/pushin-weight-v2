"""Each F0 migration is additive and preserves existing metric definitions."""

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


@pytest.mark.usefixtures("isolated_migration_database")
def test_catalogue_boundaries_preserve_existing_writer_and_allow_seed_replay():
    from core.benchmark_metric_identity import register_definitions
    from core.models import SourceMetric

    base = ("core", "0092_measurement_window_index")
    MigrationExecutor(connection).migrate([base])
    register_definitions()
    before = list(SourceMetric.objects.order_by("pk").values())
    before_tables = set(connection.introspection.table_names())
    assert (
        before
        and not {"languages", "locales", "time_zones", "measurement_units"}
        & before_tables
    )

    MigrationExecutor(connection).migrate([("core", "0093_shared_time_zones")])
    call_command("seed_shared_vocabulary", catalogue=["time_zones"], verbosity=0)
    assert set(connection.introspection.table_names()) - before_tables == {"time_zones"}
    MigrationExecutor(connection).migrate([("core", "0094_shared_languages_locales")])
    call_command(
        "seed_shared_vocabulary", catalogue=["locales", "languages"], verbosity=0
    )
    assert set(connection.introspection.table_names()) - before_tables == {
        "time_zones",
        "languages",
        "locales",
    }
    MigrationExecutor(connection).migrate([("core", "0095_shared_measurement_units")])
    call_command("seed_shared_vocabulary", catalogue=["measurement_units"], verbosity=0)
    call_command("seed_shared_vocabulary", verbosity=0)
    assert set(connection.introspection.table_names()) - before_tables == {
        "time_zones",
        "languages",
        "locales",
        "measurement_units",
    }
    assert list(SourceMetric.objects.order_by("pk").values()) == before
    register_definitions()  # Existing writer still accepts its original unit/timezone strings.
    assert list(SourceMetric.objects.order_by("pk").values()) == before
