from __future__ import annotations

import os
import sys
from collections.abc import Callable, Mapping
from typing import Any

import django

if __package__:
    from .database_lock import DatabaseLockError, acquire_cluster_lock
else:
    from database_lock import DatabaseLockError, acquire_cluster_lock

_MIGRATION_LOCK_ID = 8_675_309


def run_migrations(*, connection, execute_migrate) -> None:
    """Run every build migration while holding the shared PostgreSQL lock."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock(%s)", [_MIGRATION_LOCK_ID])
    print(f"Acquired migration advisory lock {_MIGRATION_LOCK_ID}", flush=True)
    try:
        execute_migrate()
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [_MIGRATION_LOCK_ID])
        print("Released migration advisory lock", flush=True)


def main(
    *,
    environ: Mapping[str, str] | None = None,
    connect: Callable[..., Any] | None = None,
    app_connection: Any | None = None,
    execute_migrate: Callable[[], None] | None = None,
    setup_django: Callable[[], None] = django.setup,
) -> int:
    values = os.environ if environ is None else environ
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
    setup_django()

    from django.core.management import execute_from_command_line
    from django.db import connection

    database_url = values.get("DATABASE_URL")
    if not database_url:
        print("Migration cluster lock unavailable; set DATABASE_URL and retry.", file=sys.stderr)
        return 75
    migration_connection = app_connection or connection
    migration_command = execute_migrate or (
        lambda: execute_from_command_line(["manage.py", "migrate", "--noinput"])
    )
    lock_options: dict[str, object] = {}
    if connect is not None:
        lock_options["connect"] = connect
    try:
        with acquire_cluster_lock(database_url, wait_seconds=900, **lock_options):
            run_migrations(
                connection=migration_connection,
                execute_migrate=migration_command,
            )
    except DatabaseLockError as exc:
        print(f"Migration cluster lock failed ({exc}); retry the deploy.", file=sys.stderr)
        return 75
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
