from __future__ import annotations

import pytest
from django.core.exceptions import ImproperlyConfigured

from project.staging import (
    should_run_build_migrations,
    validate_staging_environment,
)


def test_new_staging_database_stays_empty_until_ollija_bootstraps_it() -> None:
    assert not should_run_build_migrations(
        staging_enabled=True,
        marker_status=None,
    )
    assert not should_run_build_migrations(
        staging_enabled=True,
        marker_status="building",
    )
    assert should_run_build_migrations(
        staging_enabled=True,
        marker_status="active",
    )
    assert should_run_build_migrations(
        staging_enabled=False,
        marker_status=None,
    )


def test_staging_boot_requires_its_own_auth_and_owner_values() -> None:
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


def test_production_does_not_require_staging_values() -> None:
    validate_staging_environment(
        enabled=False,
        django_secret_key="dev-only-change-in-production-xmonitor-v2",
        google_client_id="",
        google_client_secret="",
        allowed_emails=(),
    )


def test_complete_staging_auth_contract_passes() -> None:
    validate_staging_environment(
        enabled=True,
        django_secret_key="staging-only-long-random-value",
        google_client_id="staging-client.apps.googleusercontent.com",
        google_client_secret="staging-client-secret",
        allowed_emails=("owner@example.com",),
    )
