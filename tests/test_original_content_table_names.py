"""Real PostgreSQL names and old-process compatibility during physical renames."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.db import (
    IntegrityError,
    OperationalError,
    ProgrammingError,
    connection,
    connections,
    transaction,
)
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from core import models
from scripts.render_migrate import run_migrations

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]

TABLES = {
    "OriginalContent": ("brand_trend_narratives", "original_content"),
    "OriginalContentText": ("brand_trend_narrative_texts", "original_content_texts"),
    "OriginalContentRun": ("trend_narrative_runs", "original_content_runs"),
    "OriginalContentCall": ("trend_narrative_provider_calls", "original_content_calls"),
    "OriginalContentSelection": (
        "trend_narrative_visible_runs",
        "original_content_selections",
    ),
    "ContentPicture": ("editorial_pictures", "content_pictures"),
}
BEFORE = ("core", "0078_original_content_workflow_shape")
AFTER = ("core", "0079_original_content_physical_names")


def migrate(target):
    executor = MigrationExecutor(connection)
    executor.migrate([target])
    return executor.loader.project_state([target]).apps


def seed(apps):
    now = timezone.now()

    def get(name):
        return apps.get_model("core", name)

    run = get("OriginalContentRun").objects.create(
        source_cycle_id="rename-fixture",
        window_days=7,
        facts_as_of=now,
        packet_schema_version=1,
        snapshot={"evidence": ["rename-source"]},
    )
    call = get("OriginalContentCall").objects.create(
        run=run,
        stage="editor",
        request_identity="rename-request",
        request_hash="a" * 64,
        reserved_at=now,
        budget_scope="editorial",
        budget_day=now.date(),
        reserved_usd=Decimal("0.125000"),
    )
    content = get("OriginalContent").objects.create(
        run=run,
        brand_key_snapshot="fixture",
        status="approved",
        attempted_at=now,
        verified_at=now,
        headline_en="Saved headline",
        secondary_en="Saved byline",
        headline_zh_cn="中文标题",
        secondary_zh_cn="中文署名",
    )
    text = get("OriginalContentText").objects.create(
        narrative=content,
        locale="en",
        headline="Saved headline",
        secondary="Saved byline",
        body="Saved article",
        public_id=uuid4(),
        producing_call=call,
    )
    post = get("Post").objects.create(tweet_id="rename-source", text="Source")
    source = get("OriginalContentSource").objects.create(
        text=text,
        post=post,
        position=1,
        url_snapshot="https://x.com/i/status/123456789",
        source_hash="b" * 64,
        hash_basis="writing_packet",
    )
    selection = get("OriginalContentSelection").objects.create(
        scope_key="featured-chatter-en",
        text=text,
        facts_as_of=now,
        activated_at=now,
    )
    picture = get("ContentPicture").objects.create(
        text=text,
        run=run,
        content_kind="chatter",
        content_id=str(text.public_id),
        revision_hash="c" * 64,
        mode="off",
        state="missing",
    )
    return SimpleNamespace(
        run=run,
        call=call,
        content=content,
        text=text,
        source=source,
        selection=selection,
        picture=picture,
    )


def snapshot(names):
    """Compare actual rows and database object identities, including incoming FKs."""
    result = {}
    with connection.cursor() as cursor:
        for name in names:
            cursor.execute("SELECT %s::regclass::oid", [name])
            oid = cursor.fetchone()[0]
            cursor.execute(f'SELECT row_to_json(t)::text FROM "{name}" t ORDER BY id')
            rows = cursor.fetchall()
            cursor.execute(
                "SELECT oid, conname, contype, conrelid, confrelid, conkey, confkey "
                "FROM pg_constraint WHERE conrelid=%s OR confrelid=%s ORDER BY oid",
                [oid, oid],
            )
            constraints = cursor.fetchall()
            cursor.execute(
                "SELECT indexrelid, indkey FROM pg_index WHERE indrelid=%s ORDER BY indexrelid",
                [oid],
            )
            indexes = cursor.fetchall()
            cursor.execute("SELECT pg_get_serial_sequence(%s, 'id')", [name])
            sequence = cursor.fetchone()[0]
            sequence_state = None
            if sequence:
                cursor.execute(f"SELECT last_value, is_called FROM {sequence}")
                sequence_state = cursor.fetchone()
            result[name] = (oid, rows, constraints, indexes, sequence, sequence_state)
    return result


def test_runtime_orm_names_match_canonical_base_tables_and_compatible_views():
    for name, (old, canonical) in TABLES.items():
        assert getattr(models, name)._meta.db_table == canonical
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT relname, relkind FROM pg_class "
                "WHERE oid IN (to_regclass(%s), to_regclass(%s))",
                [old, canonical],
            )
            assert dict(cursor.fetchall()) == {old: "v", canonical: "r"}


def test_populated_forward_and_reverse_preserve_rows_keys_indexes_and_sequences():
    try:
        old_apps = migrate(BEFORE)
        graph = seed(old_apps)
        old_names = [pair[0] for pair in TABLES.values()] + ["original_content_sources"]
        before = snapshot(old_names)
        migrate(AFTER)
        after = snapshot(
            [pair[1] for pair in TABLES.values()] + ["original_content_sources"]
        )
        for old, new in TABLES.values():
            assert after[new] == before[old]
        assert after["original_content_sources"] == before["original_content_sources"]
        assert (
            models.OriginalContentText.objects.get(pk=graph.text.pk).public_id
            == graph.text.public_id
        )
        migrate(BEFORE)
        assert snapshot(old_names) == before
        with connection.cursor() as cursor:
            for _, new in TABLES.values():
                cursor.execute("SELECT to_regclass(%s)", [new])
                assert cursor.fetchone()[0] is None
    finally:
        migrate(AFTER)


def test_old_and_new_orms_write_same_rows_with_defaults_conflicts_locks_and_protection():
    old_apps = MigrationExecutor(connection).loader.project_state([BEFORE]).apps
    graph = seed(old_apps)
    # Every old-name model inserts through a view; current readers see its real IDs.
    for name, attr in (
        ("OriginalContentRun", "run"),
        ("OriginalContentCall", "call"),
        ("OriginalContent", "content"),
        ("OriginalContentText", "text"),
        ("OriginalContentSelection", "selection"),
        ("ContentPicture", "picture"),
    ):
        assert getattr(models, name).objects.filter(pk=getattr(graph, attr).pk).exists()
    old_run = old_apps.get_model("core", "OriginalContentRun")
    old_call = old_apps.get_model("core", "OriginalContentCall")
    old_text = old_apps.get_model("core", "OriginalContentText")
    defaults = {
        "window_days": 7,
        "facts_as_of": timezone.now(),
        "packet_schema_version": 1,
        "snapshot": {},
    }
    run, created = old_run.objects.get_or_create(
        source_cycle_id="another-run", defaults=defaults
    )
    assert created and run.pk
    run2, created = models.OriginalContentRun.objects.get_or_create(
        source_cycle_id="another-run", defaults=defaults
    )
    assert not created and run2.pk == run.pk
    inserted = old_run.objects.bulk_create(
        [old_run(source_cycle_id="bulk-run", **defaults)]
    )
    assert (
        inserted[0].pk
        and models.OriginalContentRun.objects.filter(pk=inserted[0].pk).exists()
    )
    old_call.objects.bulk_create(
        [
            old_call(
                run_id=graph.run.pk,
                stage="editor",
                request_identity="rename-request",
                request_hash="a" * 64,
                reserved_at=graph.call.reserved_at,
                budget_day=graph.call.budget_day,
                budget_scope="editorial",
                reserved_usd="0.250000",
            )
        ],
        update_conflicts=True,
        update_fields=["reserved_usd"],
        unique_fields=["request_identity"],
    )
    assert models.OriginalContentCall.objects.get(
        pk=graph.call.pk
    ).reserved_usd == Decimal("0.250000")
    with transaction.atomic():
        old_text.objects.select_for_update(of=("self",)).get(pk=graph.text.pk)
        models.OriginalContentText.objects.filter(pk=graph.text.pk).update(
            body="New process write"
        )
    saved, created = old_text.objects.update_or_create(
        pk=graph.text.pk, defaults={"secondary": "Updated byline"}
    )
    assert not created and saved.body == "New process write"
    assert (
        models.OriginalContentText.objects.get(pk=graph.text.pk).secondary
        == "Updated byline"
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        old_text.objects.create(
            narrative_id=graph.content.pk,
            locale="en",
            headline="Duplicate",
            secondary="Duplicate",
        )
    with pytest.raises(ProtectedError):
        old_call.objects.get(pk=graph.call.pk).delete()
    with pytest.raises(ProtectedError):
        old_run.objects.get(pk=graph.run.pk).delete()
    old_run.objects.get(pk=inserted[0].pk).delete()
    assert not models.OriginalContentRun.objects.filter(pk=inserted[0].pk).exists()
    assert (
        models.OriginalContentSource.objects.get(pk=graph.source.pk).url_snapshot
        == graph.source.url_snapshot
    )


def test_lock_timeout_rolls_back_all_prior_renames():
    blocker = connection.copy()
    try:
        migrate(BEFORE)
        blocker.set_autocommit(False)
        with blocker.cursor() as cursor:
            cursor.execute(
                "LOCK TABLE brand_trend_narrative_texts IN ACCESS SHARE MODE"
            )
        with pytest.raises(OperationalError, match="lock timeout"):
            migrate(AFTER)
        with connection.cursor() as cursor:
            for old, new in TABLES.values():
                cursor.execute("SELECT to_regclass(%s), to_regclass(%s)", [old, new])
                assert cursor.fetchone() == (old, None)
            cursor.execute(
                "SELECT count(*) FROM django_migrations WHERE app=%s AND name=%s", AFTER
            )
            assert cursor.fetchone()[0] == 0
    finally:
        blocker.rollback()
        blocker.close()
        migrate(AFTER)


def test_unexpected_target_is_not_replaced_and_all_renames_roll_back():
    try:
        migrate(BEFORE)
        with connection.cursor() as cursor:
            cursor.execute("CREATE VIEW original_content_texts AS SELECT 42 AS marker")
        with pytest.raises(ProgrammingError, match="already exists"):
            migrate(AFTER)
        with connection.cursor() as cursor:
            cursor.execute("SELECT marker FROM original_content_texts")
            assert cursor.fetchone()[0] == 42
            for old, _ in TABLES.values():
                cursor.execute(
                    "SELECT relkind FROM pg_class WHERE oid=to_regclass(%s)", [old]
                )
                assert cursor.fetchone()[0] == "r"
            cursor.execute("DROP VIEW original_content_texts")
    finally:
        migrate(AFTER)


def test_two_build_migration_runners_serialize_the_same_rename():
    try:
        migrate(BEFORE)
        barrier = Barrier(2)

        def build():
            db = connections["default"]
            try:
                barrier.wait(timeout=10)
                run_migrations(
                    connection=db,
                    execute_migrate=lambda: MigrationExecutor(db).migrate([AFTER]),
                )
            finally:
                db.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(build) for _ in range(2)]
            for future in futures:
                future.result(timeout=30)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM django_migrations WHERE app=%s AND name=%s", AFTER
            )
            assert cursor.fetchone()[0] == 1
        test_runtime_orm_names_match_canonical_base_tables_and_compatible_views()
    finally:
        migrate(AFTER)
