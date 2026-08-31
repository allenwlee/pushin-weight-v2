from __future__ import annotations

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = [
    pytest.mark.requires_postgres,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

BEFORE = [("core", "0025_account_verification_override_year")]
CURRENT = [("core", "0027_account_country_foreign_key")]


def _apps_at(targets):
    executor = MigrationExecutor(connection)
    executor.migrate(targets)
    return executor.loader.project_state(targets).apps


def test_geography_migrations_preserve_existing_country_column_and_seed_taxonomy():
    try:
        old_apps = _apps_at(BEFORE)
        OldAccount = old_apps.get_model("core", "Account")
        OldAccount.objects.create(
            author_id="migration-country",
            handle="migration-country",
            country_code="US",
        )
        OldAccount.objects.create(
            author_id="migration-null",
            handle="migration-null",
            country_code=None,
        )

        current_apps = _apps_at(CURRENT)
        Account = current_apps.get_model("core", "Account")
        Country = current_apps.get_model("core", "Country")
        CountryLabel = current_apps.get_model("core", "CountryLabel")
        CountryRegion = current_apps.get_model("core", "CountryRegion")
        Region = current_apps.get_model("core", "Region")
        RegionLabel = current_apps.get_model("core", "RegionLabel")

        assert Account.objects.get(pk="migration-country").country_id == "US"
        assert Account.objects.get(pk="migration-null").country_id is None
        assert Country.objects.count() == 249
        assert CountryLabel.objects.count() == 498
        assert CountryRegion.objects.count() == 249
        assert Region.objects.filter(key="europe").exists()
        assert RegionLabel.objects.filter(region_id="europe", lang="zh-cn").exists()

        old_apps = _apps_at(BEFORE)
        OldAccount = old_apps.get_model("core", "Account")
        assert OldAccount.objects.get(pk="migration-country").country_code == "US"
        assert OldAccount.objects.get(pk="migration-null").country_code is None
    finally:
        _apps_at(CURRENT)


def test_country_foreign_key_preflight_rejects_unknown_existing_code():
    try:
        old_apps = _apps_at(BEFORE)
        OldAccount = old_apps.get_model("core", "Account")
        OldAccount.objects.create(
            author_id="migration-unsupported",
            handle="migration-unsupported",
            country_code="ZZ",
        )

        with pytest.raises(RuntimeError, match="unsupported country codes.*ZZ"):
            _apps_at(CURRENT)

        state_0026 = [("core", "0026_account_geography_taxonomy")]
        apps_0026 = MigrationExecutor(connection).loader.project_state(state_0026).apps
        apps_0026.get_model("core", "Account").objects.filter(
            pk="migration-unsupported"
        ).delete()
    finally:
        _apps_at(CURRENT)
