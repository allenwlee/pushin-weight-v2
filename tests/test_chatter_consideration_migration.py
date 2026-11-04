"""Exercise the additive migration on the locked permanent test database."""

from uuid import uuid4

import pytest
from django.apps import apps as runtime_apps
from django.db import connection, migrations
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]
BASE = ("core", "0219_release_mapping_reconcile_index")
EXTENSION = ("core", "0220_chatter_consideration_ownership")
TARGET = ("core", "0224_chatter_source_snapshot_owner")


def test_populated_legacy_citations_survive_chatter_extension_without_new_tables():
    # Never discard another test/session's new-contract records to stage this cohort.
    executor = MigrationExecutor(connection)
    assert not runtime_apps.get_model("core", "OriginalContentSource").objects.filter(snapshot_run__isnull=False).exists(), "Shared cohort contains source-owner references"
    operations = list(executor.loader.get_migration(*EXTENSION).operations)
    for operation in operations:
        if isinstance(operation, migrations.SeparateDatabaseAndState):
            operations.extend(operation.state_operations)
        elif isinstance(operation, migrations.AddField):
            model = runtime_apps.get_model("core", operation.model_name)
            assert not model.objects.exclude(
                **{operation.name: model._meta.get_field(operation.name).get_default()}
            ).exists(), f"new-contract data must be preserved: {operation.model_name}.{operation.name}"
    executor.migrate([BASE])
    try:
        old = executor.loader.project_state([BASE]).apps
        tables = set(connection.introspection.table_names())
        run = old.get_model("core", "OriginalContentRun").objects.create(
            source_cycle_id=str(uuid4()), workflow_key="editorial-dispatch",
            scope_key=str(uuid4()), facts_as_of=timezone.now(),
            packet_schema_version=1, snapshot={},
        )
        content = old.get_model("core", "OriginalContent").objects.create(
            run=run, workflow_key="social-brief", output_key=str(uuid4()),
            brand_key_snapshot="", status="prepared", attempted_at=timezone.now(),
        )
        text = old.get_model("core", "OriginalContentText").objects.create(
            narrative=content, locale="en", headline="Saved headline",
            secondary="Saved supporting line", public_id=uuid4(),
        )
        post = old.get_model("core", "Post").objects.create(tweet_id="991001", text="Saved source.")
        source = old.get_model("core", "OriginalContentSource").objects.create(
            text=text, post=post, position=0, url_snapshot="https://x.com/i/status/991001",
            source_hash="a" * 64, hash_basis="writing_packet",
        )
        executor = MigrationExecutor(connection)
        executor.migrate([TARGET])
        current = executor.loader.project_state([TARGET]).apps
        saved = current.get_model("core", "OriginalContentSource").objects.get(pk=source.pk)
        assert (saved.text_id, saved.post_id, saved.source_hash) == (text.pk, post.pk, "a" * 64)
        assert saved.content_id is None and saved.dossier_source_id is None
        assert saved.usage == "citation"
        copy = current.get_model("core", "OriginalContentText").objects.get(pk=text.pk)
        assert copy.public_id == text.public_id and copy.headline == "Saved headline"
        assert set(connection.introspection.table_names()) == tables
        # Old workers can finish writes after the additive migration, before code rollout.
        late = old.get_model("core", "OriginalContent").objects.create(
            run=run, workflow_key="social-brief", output_key=str(uuid4()),
            brand_key_snapshot="", status="prepared", attempted_at=timezone.now(),
        )
        assert current.get_model("core", "OriginalContent").objects.get(pk=late.pk).consideration_reason == ""
        with connection.cursor() as cursor:
            cursor.execute("SELECT bool_and(convalidated) FROM pg_constraint WHERE conname LIKE 'fk_chatter_%%'")
            assert cursor.fetchone()[0] is True
    finally:
        MigrationExecutor(connection).migrate([TARGET])
