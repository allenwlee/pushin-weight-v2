from __future__ import annotations

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]

BEFORE = [("core", "0049_rare_type_domain_records")]
AFTER = [("core", "0051_profile_movement_token_evidence")]


def test_populated_profile_snapshot_survives_movement_schema_upgrade():
    executor = MigrationExecutor(connection)
    try:
        executor.migrate(BEFORE)
        old_apps = executor.loader.project_state(BEFORE).apps
        Account = old_apps.get_model("core", "Account")
        Snapshot = old_apps.get_model("core", "AccountProfileSnapshot")
        account = Account.objects.create(author_id="migration-profile")
        now = timezone.now()
        snapshot = Snapshot.objects.create(
            account=account,
            profile_hash="a" * 64,
            first_observed_at=now,
            last_observed_at=now,
            first_source_kind="post",
            present_fields=["description"],
            profile_data={"description": "OpenAI researcher"},
            description="OpenAI researcher",
        )

        executor = MigrationExecutor(connection)
        executor.migrate(AFTER)
        apps = executor.loader.project_state(AFTER).apps
        migrated = apps.get_model("core", "AccountProfileSnapshot").objects.get(
            pk=snapshot.pk
        )
        assert migrated.description == "OpenAI researcher"
        Movement = apps.get_model("core", "ProfileMovementCandidate")
        assert not Movement.objects.exists()
    finally:
        MigrationExecutor(connection).migrate(
            MigrationExecutor(connection).loader.graph.leaf_nodes()
        )
