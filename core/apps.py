from __future__ import annotations

from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self) -> None:
        from django.db import connection

        if connection.vendor == "sqlite":
            # Register a Python-based case_insensitive collation for
            # SQLite (Postgres has native CITEXT / case_insensitive
            # collation; SQLite needs a Python fallback for local dev).
            conn = connection.connection
            if conn is not None:
                conn.create_collation(
                    "case_insensitive",
                    _sqlite_case_insensitive_compare,
                )


def _sqlite_case_insensitive_compare(a: str | None, b: str | None) -> int:
    """SQLite collation: case-insensitive ordering for local dev."""
    a_lower = (a or "").lower()
    b_lower = (b or "").lower()
    if a_lower < b_lower:
        return -1
    if a_lower > b_lower:
        return 1
    return 0
