from __future__ import annotations

from types import SimpleNamespace
from typing import Self
from unittest.mock import patch

import pytest
from django.core.exceptions import ImproperlyConfigured

from project.middleware import StagingOwnerOnlyMiddleware
from project.staging import validate_staging_environment
from scripts import render_migrate

Operation = tuple[str, tuple[int, ...]] | str


class _Cursor:
    def __init__(self, operations: list[Operation]) -> None:
        self.operations = operations

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, statement: str, parameters: list[int]) -> None:
        self.operations.append((statement, tuple(parameters)))


class _Connection:
    def __init__(self, operations: list[Operation]) -> None:
        self.operations = operations

    def cursor(self) -> _Cursor:
        return _Cursor(self.operations)


def test_build_migrations_always_run_under_the_advisory_lock() -> None:
    operations: list[Operation] = []
    connection = _Connection(operations)

    render_migrate.run_migrations(
        connection=connection,
        execute_migrate=lambda: operations.append("migrate"),
    )

    assert operations == [
        ("SELECT pg_advisory_lock(%s)", (8_675_309,)),
        "migrate",
        ("SELECT pg_advisory_unlock(%s)", (8_675_309,)),
    ]


def test_failed_build_migration_releases_the_advisory_lock() -> None:
    operations: list[Operation] = []
    connection = _Connection(operations)

    def fail_migration() -> None:
        operations.append("migrate")
        raise RuntimeError("migration failed")

    with pytest.raises(RuntimeError, match="migration failed"):
        render_migrate.run_migrations(
            connection=connection,
            execute_migrate=fail_migration,
        )

    assert operations == [
        ("SELECT pg_advisory_lock(%s)", (8_675_309,)),
        "migrate",
        ("SELECT pg_advisory_unlock(%s)", (8_675_309,)),
    ]


def test_staging_boot_fails_closed_for_missing_credentials_or_owner_allowlist() -> None:
    with pytest.raises(ImproperlyConfigured) as caught:
        validate_staging_environment(
            enabled=True,
            django_secret_key="dev-only-change-in-production-xmonitor-v2",
            google_client_id="",
            google_client_secret="",
            allowed_emails=(),
        )

    message = str(caught.value)
    assert "DJANGO_SECRET_KEY" in message
    assert "GOOGLE_CLIENT_ID" in message
    assert "GOOGLE_CLIENT_SECRET" in message
    assert "OLLIJA_STAGING_ALLOWED_EMAILS" in message


def test_staging_boot_fails_closed_for_an_empty_owner_allowlist_alone() -> None:
    with pytest.raises(ImproperlyConfigured, match="OLLIJA_STAGING_ALLOWED_EMAILS"):
        validate_staging_environment(
            enabled=True,
            django_secret_key="staging-only-long-random-value",
            google_client_id="staging-client.apps.googleusercontent.com",
            google_client_secret="staging-client-secret",
            allowed_emails=(),
        )


def test_production_does_not_require_staging_values() -> None:
    validate_staging_environment(
        enabled=False,
        django_secret_key="dev-only-change-in-production-xmonitor-v2",
        google_client_id="",
        google_client_secret="",
        allowed_emails=(),
    )


def test_staging_owner_middleware_rejects_unauthenticated_and_nonallowlisted_requests() -> None:
    settings = SimpleNamespace(
        OLLIJA_STAGING_MODE=True,
        OLLIJA_STAGING_ALLOWED_EMAILS=frozenset({"owner@example.com"}),
        LOGIN_URL="/accounts/login/",
    )
    middleware = StagingOwnerOnlyMiddleware(lambda _request: "protected")
    anonymous = SimpleNamespace(is_authenticated=False, email="")
    outsider = SimpleNamespace(is_authenticated=True, email="outsider@example.com")
    owner = SimpleNamespace(is_authenticated=True, email="owner@example.com")

    with (
        patch("project.middleware.settings", settings),
        patch("project.middleware.redirect", lambda url: ("redirect", url)),
        patch(
            "project.middleware.HttpResponseForbidden",
            lambda _message: "forbidden",
        ),
    ):
        assert middleware(SimpleNamespace(path="/", user=anonymous)) == (
            "redirect",
            "/accounts/login/",
        )
        assert middleware(SimpleNamespace(path="/", user=outsider)) == "forbidden"
        assert middleware(SimpleNamespace(path="/", user=owner)) == "protected"
