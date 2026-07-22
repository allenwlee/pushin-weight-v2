#!/usr/bin/env python
"""Django management utility with SQLite collation for local dev."""
import os
import sys


def _register_sqlite_collation() -> None:
    """Register case_insensitive collation before Django touches the DB."""
    import sqlite3

    def _ci_compare(a, b):
        a_l = (a or "").lower()
        b_l = (b or "").lower()
        if a_l < b_l:
            return -1
        if a_l > b_l:
            return 1
        return 0

    orig = sqlite3.connect

    def patched(*args, **kwargs):
        conn = orig(*args, **kwargs)
        conn.create_collation("case_insensitive", _ci_compare)
        return conn

    sqlite3.connect = patched
    import sqlite3.dbapi2 as dbapi2
    dbapi2.connect = patched


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
    _register_sqlite_collation()
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
