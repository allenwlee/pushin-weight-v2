import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_existing_person_and_links_survive_name_migration():
    before = [("core", "0058_postenrichmentstate_translation_diagnostics")]
    after = [("core", "0060_person_name_provenance_and_guards")]
    try:
        executor = MigrationExecutor(connection)
        executor.migrate(before)
        apps = executor.loader.project_state(before).apps
        person = apps.get_model("core", "Person").objects.create(
            display_name="劉洺堉",
            display_name_en="Ming-Yu Liu",
            display_name_zh_cn="刘洺堉",
            display_name_ja="劉洺堉",
            sexs="male",
        )
        account = apps.get_model("core", "Account").objects.create(
            author_id="migration-person"
        )
        apps.get_model("core", "PersonAccount").objects.create(
            person=person,
            account=account,
            first_observed_at=timezone.now(),
            last_observed_at=timezone.now(),
        )
        executor = MigrationExecutor(connection)
        executor.migrate(after)
        apps = executor.loader.project_state(after).apps
        migrated = apps.get_model("core", "Person").objects.get(pk=person.pk)
        assert migrated.sex == "male"
        assert migrated.display_name == "劉洺堉"
        assert migrated.account_links.get().account_id == account.pk
        assert migrated.names.count() == 4
        assert set(migrated.names.values_list("origin", flat=True)) == {"legacy"}
        assert migrated.primary_name_id is None
        assert (
            apps.get_model("core", "PersonNameEvidence")
            .objects.filter(name__person=migrated, source_kind="legacy_unknown")
            .count()
            == 4
        )
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
