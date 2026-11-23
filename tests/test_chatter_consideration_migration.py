"""Exercise the additive migration in an isolated historical schema."""

from uuid import uuid4

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]
BASE = ("core", "0219_release_mapping_reconcile_index")
TARGET = ("core", "0224_chatter_source_snapshot_owner")


@pytest.mark.parametrize("migration_rehearsal_schema", [BASE], indirect=True)
def test_populated_legacy_citations_survive_chatter_extension_without_new_tables(
    migration_rehearsal_schema,
):
    executor = MigrationExecutor(connection)
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
        cursor.execute(
            "SELECT conname, convalidated FROM pg_constraint "
            "WHERE connamespace = %s::regnamespace AND conname LIKE 'fk_chatter_%%'",
            [migration_rehearsal_schema],
        )
        assert dict(cursor.fetchall()) == {
            "fk_chatter_collectionrun_content_run": True,
            "fk_chatter_collectionscoperun_content_call": True,
            "fk_chatter_collectionscoperun_search_query": True,
            "fk_chatter_source_snapshot": True,
        }
