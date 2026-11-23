"""Rehearse provenance changes without altering the public schema."""

import threading
import time

import psycopg
import pytest
from django.db import IntegrityError, OperationalError, connection, transaction
from django.db.migrations.executor import MigrationExecutor

from core.models import OriginalContent
from tests.test_original_content_consideration import consideration

BASE = ("core", "0228_merge_staging_chatter_translation")
TARGET = ("core", "0229_chatter_personalized_trend_appearance")
pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.requires_postgres,
    pytest.mark.parametrize("migration_rehearsal_schema", [BASE], indirect=True),
]


def public_schema_state():
    """Include physical objects and recorder rows, independently of search_path."""
    statements = (
        (
            "SELECT c.oid, c.relname, c.relkind, c.relfilenode FROM pg_class c "
            "WHERE c.relnamespace = 'public'::regnamespace ORDER BY c.oid"
        ),
        (
            "SELECT table_name, column_name, data_type, is_nullable, column_default "
            "FROM information_schema.columns WHERE table_schema = 'public' "
            "ORDER BY table_name, ordinal_position"
        ),
        (
            "SELECT oid, conname, convalidated, pg_get_constraintdef(oid) "
            "FROM pg_constraint WHERE connamespace = 'public'::regnamespace ORDER BY oid"
        ),
        (
            "SELECT i.indexrelid, i.indisvalid, i.indisready, pg_get_indexdef(i.indexrelid) "
            "FROM pg_index i JOIN pg_class c ON c.oid = i.indrelid "
            "WHERE c.relnamespace = 'public'::regnamespace ORDER BY i.indexrelid"
        ),
        (
            "SELECT t.oid, t.tgenabled, pg_get_triggerdef(t.oid) FROM pg_trigger t "
            "JOIN pg_class c ON c.oid = t.tgrelid "
            "WHERE c.relnamespace = 'public'::regnamespace ORDER BY t.oid"
        ),
        "SELECT app, name, applied FROM public.django_migrations ORDER BY app, name",
    )
    with connection.cursor() as cursor:
        state = []
        for statement in statements:
            cursor.execute(statement)
            state.append(cursor.fetchall())
        return state


@pytest.fixture(autouse=True)
def public_schema_unchanged(transactional_db):
    before = public_schema_state()
    yield
    # Runs after rehearsal cleanup, including migration failure/cancellation.
    assert public_schema_state() == before


def layout():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT table_name, column_name, data_type, is_nullable "
            "FROM information_schema.columns WHERE table_schema = current_schema() "
            "ORDER BY table_name, ordinal_position"
        )
        return cursor.fetchall()


def appearance_constraint():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT conname, convalidated, pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid = 'original_content'::regclass "
            "AND conname LIKE 'ck_oc_appearance_kind%' ORDER BY conname"
        )
        (constraint,) = cursor.fetchall()
        assert constraint[:2] == ("ck_oc_appearance_kind", True)
        return constraint[2]


def test_personalized_trend_migration_preserves_legacy_records_and_schema(
    migration_rehearsal_schema,
):
    assert connection.settings_dict["NAME"].startswith("test_")
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_schema()")
        assert cursor.fetchone()[0] == migration_rehearsal_schema
        assert migration_rehearsal_schema.startswith("migration_rehearsal_")
    executor = MigrationExecutor(connection)
    assert executor.loader.get_migration(*TARGET).dependencies == [BASE]
    rows = [consideration(appearance_kind=kind) for kind in (
        "semantic_shortlist", "memory_only", "keyword_only", "release", None,
    )]
    ids = [row.pk for row in rows]
    saved = list(OriginalContent.objects.filter(pk__in=ids).order_by("pk").values())
    before_layout = layout()
    MigrationExecutor(connection).migrate([TARGET])
    assert layout() == before_layout
    assert list(OriginalContent.objects.filter(pk__in=ids).order_by("pk").values()) == saved
    assert "personalized_trend" in appearance_constraint()
    personalized = consideration(appearance_kind="personalized_trend")
    with pytest.raises(IntegrityError), transaction.atomic():
        OriginalContent.objects.filter(pk=personalized.pk).update(appearance_kind="personalized_trends")

    # Refuse a lossy reversal, retaining the current validated guard and data.
    with pytest.raises(IntegrityError):
        MigrationExecutor(connection).migrate([BASE])
    assert "personalized_trend" in appearance_constraint()
    personalized.refresh_from_db()
    assert personalized.appearance_kind == "personalized_trend"
    personalized.delete()

    MigrationExecutor(connection).migrate([BASE])
    assert "personalized_trend" not in appearance_constraint()
    with pytest.raises(IntegrityError), transaction.atomic():
        OriginalContent.objects.filter(pk=rows[0].pk).update(appearance_kind="personalized_trend")
    assert list(OriginalContent.objects.filter(pk__in=ids).order_by("pk").values()) == saved
    assert layout() == before_layout


def peer_connection():
    peer = psycopg.connect(**connection.get_connection_params(), autocommit=True)
    with connection.cursor() as cursor:
        cursor.execute("SHOW search_path")
        peer.execute("SELECT set_config('search_path', %s, false)", [cursor.fetchone()[0]])
    return peer


def is_validation(sql):
    return 'VALIDATE CONSTRAINT "ck_oc_appearance_kind_next"' in sql


def assert_wider_guard_and_writes(row):
    assert "personalized_trend" in appearance_constraint()
    assert TARGET in MigrationExecutor(connection).loader.applied_migrations
    assert OriginalContent.objects.filter(pk=row.pk).update(
        appearance_kind="personalized_trend"
    ) == 1


def test_reverse_interrupt_preserves_wider_guard(migration_rehearsal_schema):
    MigrationExecutor(connection).migrate([TARGET])
    row = consideration()

    def interrupt(execute, sql, params, many, context):
        if is_validation(sql):
            raise KeyboardInterrupt("reverse interrupted before validation")
        return execute(sql, params, many, context)

    with connection.execute_wrapper(interrupt), pytest.raises(KeyboardInterrupt):
        MigrationExecutor(connection).migrate([BASE])
    assert_wider_guard_and_writes(row)


def test_reverse_refuses_active_writer_without_waiting(migration_rehearsal_schema):
    MigrationExecutor(connection).migrate([TARGET])
    row = consideration()
    with peer_connection() as peer, peer.transaction():
        peer.execute(
            "UPDATE original_content SET consideration_reason = %s WHERE id = %s",
            ["Writer remains active", row.pk],
        )
        started = time.monotonic()
        with pytest.raises(OperationalError) as caught:
            MigrationExecutor(connection).migrate([BASE])
        assert caught.value.__cause__.sqlstate == "55P03"
        assert time.monotonic() - started < 2
    assert_wider_guard_and_writes(row)


def test_reverse_database_cancel_exposes_only_wider_guard(migration_rehearsal_schema):
    MigrationExecutor(connection).migrate([TARGET])
    row = consideration()
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_backend_pid()")
        migration_pid = cursor.fetchone()[0]
        cursor.execute("SHOW lock_timeout")
        original_lock_timeout = cursor.fetchone()[0]
        cursor.execute("SHOW statement_timeout")
        original_statement_timeout = cursor.fetchone()[0]

    validating = threading.Event()
    observed_guards = []
    failures = []
    with peer_connection() as peer:
        def cancel_validation():
            try:
                assert validating.wait(10), "migration did not reach validation"
                deadline = time.monotonic() + 4
                while time.monotonic() < deadline:
                    state = peer.execute(
                        "SELECT wait_event FROM pg_stat_activity WHERE pid = %s",
                        [migration_pid],
                    ).fetchone()
                    if state == ("PgSleep",):
                        observed_guards.extend(peer.execute(
                            "SELECT conname, convalidated FROM pg_constraint "
                            "WHERE conrelid = 'original_content'::regclass "
                            "AND conname LIKE 'ck_oc_appearance_kind%' ORDER BY conname"
                        ).fetchall())
                        assert peer.execute(
                            "SELECT pg_cancel_backend(%s)", [migration_pid]
                        ).fetchone() == (True,)
                        return
                    time.sleep(0.01)
                raise AssertionError("migration did not enter cancellable database query")
            except (AssertionError, psycopg.Error) as exc:
                failures.append(exc)

        def pause_after_validation(execute, sql, params, many, context):
            result = execute(sql, params, many, context)
            if is_validation(sql):
                validating.set()
                # Cancel a real server query after validation and before swap.
                execute("SELECT pg_sleep(30)", None, False, context)
            return result

        canceller = threading.Thread(target=cancel_validation, daemon=True)
        canceller.start()
        try:
            with (
                connection.execute_wrapper(pause_after_validation),
                pytest.raises(OperationalError) as caught,
            ):
                MigrationExecutor(connection).migrate([BASE])
            assert caught.value.__cause__.sqlstate == "57014"
        finally:
            validating.set()
            canceller.join(10)
        assert not canceller.is_alive()
        assert not failures
    assert observed_guards == [("ck_oc_appearance_kind", True)]
    assert_wider_guard_and_writes(row)
    with connection.cursor() as cursor:
        cursor.execute("SHOW lock_timeout")
        assert cursor.fetchone()[0] == original_lock_timeout
        cursor.execute("SHOW statement_timeout")
        assert cursor.fetchone()[0] == original_statement_timeout


def test_forward_validation_allows_active_writer(migration_rehearsal_schema):
    row = consideration()
    with peer_connection() as peer:
        def validate_with_writer(execute, sql, params, many, context):
            if is_validation(sql):
                with peer.transaction():
                    peer.execute(
                        "UPDATE original_content SET consideration_reason = %s WHERE id = %s",
                        ["Writer overlaps online validation", row.pk],
                    )
                    return execute(sql, params, many, context)
            return execute(sql, params, many, context)

        with connection.execute_wrapper(validate_with_writer):
            MigrationExecutor(connection).migrate([TARGET])
    assert "personalized_trend" in appearance_constraint()
    row.refresh_from_db()
    assert row.consideration_reason == "Writer overlaps online validation"
