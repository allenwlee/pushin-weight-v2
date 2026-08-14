from __future__ import annotations

import os

import django

_MIGRATION_LOCK_ID = 8_675_309


def main() -> int:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
    django.setup()

    from django.conf import settings
    from django.core.management import execute_from_command_line
    from django.db import connection

    from project.staging import should_run_build_migrations

    marker_status = None
    if settings.OLLIJA_STAGING_MODE:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT to_regclass(%s)",
                ["public.ollija_environment_marker"],
            )
            if cursor.fetchone()[0] is not None:
                cursor.execute(
                    "SELECT status FROM public.ollija_environment_marker "
                    "WHERE singleton = TRUE"
                )
                row = cursor.fetchone()
                marker_status = str(row[0]) if row else None

    if not should_run_build_migrations(
        staging_enabled=settings.OLLIJA_STAGING_MODE,
        marker_status=marker_status,
    ):
        print(
            "Skipped migrations until the Ollija staging database is active",
            flush=True,
        )
        return 0

    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock(%s)", [_MIGRATION_LOCK_ID])
    print(f"Acquired migration advisory lock {_MIGRATION_LOCK_ID}", flush=True)
    try:
        execute_from_command_line(["manage.py", "migrate", "--noinput"])
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [_MIGRATION_LOCK_ID])
        print("Released migration advisory lock", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
