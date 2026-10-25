"""Exercise the real deletion migration's transaction and retry boundaries."""

import psycopg
import pytest
from django.db import OperationalError, connection
from django.db.migrations.executor import MigrationExecutor

from core.migrations._rg5_retirement_v1 import domains

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]
BASE = ("core", "0167_benchmark_serving_provenance")
TARGET = ("core", "0168_rg5_remove_superseded_storage")


def columns():
    with connection.cursor() as cursor:
        cursor.execute("""SELECT c.relname,a.attname FROM pg_class c
            JOIN pg_attribute a ON a.attrelid=c.oid
            WHERE c.relnamespace=current_schema()::regnamespace AND c.relkind='r'
              AND a.attnum>0 AND NOT a.attisdropped""")
        return set(cursor.fetchall())


def assert_retired(before):
    selected = domains()
    assert columns() == before - {(d["table"], d["old"]) for d in selected}
    with connection.cursor() as cursor:
        for domain in selected:
            cursor.execute("SELECT to_regprocedure(%s)", [domain["bridge"] + "()"])
            assert cursor.fetchone() == (None,)
        cursor.execute("""SELECT count(*) FROM pg_trigger t JOIN pg_class c
            ON c.oid=t.tgrelid WHERE c.relnamespace=current_schema()::regnamespace
            AND t.tgname LIKE 'pw_rg5_source_%%' AND t.tgenabled='O'""")
        assert cursor.fetchone() == (7,)


@pytest.mark.parametrize("migration_rehearsal_schema", [BASE], indirect=True)
def test_live_writer_lock_rolls_back_entire_drop_and_can_resume(migration_rehearsal_schema):
    before = columns()
    with connection.cursor() as cursor:
        cursor.execute("SHOW search_path")
        path = cursor.fetchone()[0]
        cursor.execute("SHOW lock_timeout")
        timeout = cursor.fetchone()[0]
    with psycopg.connect(**connection.get_connection_params()) as writer:
        writer.execute("SELECT set_config('search_path', %s, false)", [path])
        writer.execute("LOCK TABLE posts IN ROW EXCLUSIVE MODE")
        with pytest.raises(OperationalError) as caught:
            MigrationExecutor(connection).migrate([TARGET])
        assert caught.value.__cause__.sqlstate == "55P03"
        assert columns() == before
        assert not MigrationExecutor(connection).recorder.migration_qs.filter(
            app=TARGET[0], name=TARGET[1],
        ).exists()
        writer.rollback()
    with connection.cursor() as cursor:
        cursor.execute("SHOW lock_timeout")
        assert cursor.fetchone()[0] == timeout
    MigrationExecutor(connection).migrate([TARGET])
    assert_retired(before)


@pytest.mark.parametrize("migration_rehearsal_schema", [BASE], indirect=True)
@pytest.mark.parametrize("permanent", [False, True])
def test_missing_bridge_or_source_guard_refuses_drop(migration_rehearsal_schema, permanent):
    before = columns()
    bridge = next(d["bridge"] for d in domains() if d["table"] == "posts")
    trigger = "pw_rg5_source_posts" if permanent else bridge
    with connection.cursor() as cursor:
        cursor.execute(f"ALTER TABLE posts DISABLE TRIGGER {trigger}")
    with pytest.raises(RuntimeError, match="Missing permanent source guard|Unready reference retirement"):
        MigrationExecutor(connection).migrate([TARGET])
    assert columns() == before
    with connection.cursor() as cursor:
        cursor.execute(f"ALTER TABLE posts ENABLE TRIGGER {trigger}")
    MigrationExecutor(connection).migrate([TARGET])
    assert_retired(before)


def test_current_schema_contains_only_replacement_columns():
    physical = columns()
    selected = domains()
    assert all((d["table"], d["old"]) not in physical for d in selected)
    assert all((d["table"], d["new"]) in physical for d in selected)
