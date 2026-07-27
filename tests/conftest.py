"""Shared pytest fixtures and markers.

Notably: `requires_postgres`, plus a session-end warning when it fired.

The core models declare `db_collation="case_insensitive"` (a Postgres ICU
collation) so Django cannot build a SQLite test database at all -- every
`django_db` test in this repo errors on the shipped `.env`
(`DATABASE_URL=sqlite:///data/django_dev.db`).

Skipping those tests silently is the dangerous part.  The harvest regression
nets exist because ~half of daily collection was lost with no error; a net
that quietly does not run reproduces exactly that class of false confidence.
So the skip is centralized here and announced in the terminal summary.

To run the full suite:

    createdb xmon_test          # once
    DATABASE_URL=postgres://$(whoami)@localhost:5432/xmon_test pytest
"""

from __future__ import annotations

import os

import pytest


def _database_url() -> str:
    return os.environ.get("DATABASE_URL", "")


def postgres_available() -> bool:
    """True when DATABASE_URL points at PostgreSQL.

    An unset DATABASE_URL is treated as NOT available: settings.py defaults to
    Postgres, but the repo's committed .env overrides it with SQLite, so the
    conservative reading of "unset" is "probably the SQLite dev default".
    """
    url = _database_url()
    return url.startswith(("postgres://", "postgresql://"))


requires_postgres = pytest.mark.skipif(
    not postgres_available(),
    reason=(
        "needs PostgreSQL: core models use a Postgres ICU collation, so Django "
        "cannot build a SQLite test database. Re-run with "
        "DATABASE_URL=postgres://... to execute these tests."
    ),
)

_SKIP_REASON = (
    "needs PostgreSQL: core models use a Postgres ICU collation, so Django "
    "cannot build a SQLite test database. Re-run with "
    "DATABASE_URL=postgres://... to execute these tests."
)

_SKIPPED_FOR_POSTGRES: list[str] = []


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "requires_postgres: test needs a real PostgreSQL DATABASE_URL "
        "(core models use a Postgres ICU collation).",
    )


def pytest_collection_modifyitems(config, items):
    """Skip requires_postgres tests unless DATABASE_URL is PostgreSQL.

    Also records how many were skipped so the terminal summary can shout about
    it -- a silently-skipped regression net is how false confidence starts.
    """
    if postgres_available():
        return
    skip = pytest.mark.skip(reason=_SKIP_REASON)
    for item in items:
        if "requires_postgres" in item.keywords:
            item.add_marker(skip)
            _SKIPPED_FOR_POSTGRES.append(item.nodeid)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Make a Postgres-only skip impossible to miss.

    A silent skip is how a regression net rots: the suite stays green while the
    checks that would catch a regression never execute.
    """
    n = len(_SKIPPED_FOR_POSTGRES)
    if not n:
        return
    terminalreporter.write_sep("=", "PostgreSQL-only tests were SKIPPED", yellow=True)
    terminalreporter.write_line(
        f"{n} test(s) did not run because DATABASE_URL is not PostgreSQL "
        f"(currently: {_database_url() or '<unset>'})."
    )
    terminalreporter.write_line(
        "These include the harvest cursor + surface regression nets. They "
        "protect against a silent ~50% collection loss, so a green run WITHOUT "
        "them is not a full verification."
    )
    terminalreporter.write_line(
        "Run them with:  DATABASE_URL=postgres://$(whoami)@localhost:5432/"
        "<db> pytest"
    )
