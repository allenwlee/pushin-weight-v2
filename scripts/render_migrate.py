from __future__ import annotations

import os

import django

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


def main() -> int:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
    django.setup()

    from django.core.management import execute_from_command_line
    from django.db import connection

    run_migrations(
        connection=connection,
        execute_migrate=lambda: execute_from_command_line(
            ["manage.py", "migrate", "--noinput"]
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
