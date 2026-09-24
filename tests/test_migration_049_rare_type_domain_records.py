from __future__ import annotations

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]

BEFORE = [("core", "0048_rare_type_candidate_tokens")]
AFTER = [("core", "0049_rare_type_domain_records")]


def test_populated_brand_owned_event_survives_candidate_owner_migration():
    executor = MigrationExecutor(connection)
    try:
        executor.migrate(BEFORE)
        old_apps = executor.loader.project_state(BEFORE).apps
        Brand = old_apps.get_model("core", "Brand")
        Event = old_apps.get_model("core", "Event")
        brand = Brand.objects.create(nickname="migration-brand")
        now = timezone.now()
        event = Event.objects.create(
            brand=brand,
            source_url="https://example.com/event",
            title="Existing event",
            organizer_name="Existing org",
            first_seen_at=now,
            last_seen_at=now,
            event_identity="e" * 64,
        )

        executor = MigrationExecutor(connection)
        executor.migrate(AFTER)
        apps = executor.loader.project_state(AFTER).apps
        migrated = apps.get_model("core", "Event").objects.get(pk=event.pk)
        assert migrated.brand_id == "migration-brand"
        assert migrated.brand_discovery_candidate_id is None
        assert set(
            apps.get_model("core", "Brand")
            .objects.filter(pk__in=["openai", "anthropic", "spacexai", "gemini"])
            .values_list("nickname", flat=True)
        ) == {"openai", "anthropic", "spacexai", "gemini"}
    finally:
        MigrationExecutor(connection).migrate(
            MigrationExecutor(connection).loader.graph.leaf_nodes()
        )
