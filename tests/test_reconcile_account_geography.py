from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from core.models import Account, AccountBasedInMapping

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def _seed_accounts() -> None:
    observed_at = datetime(2026, 8, 31, tzinfo=UTC)
    Account.objects.create(
        author_id="country-account",
        handle="country-secret-handle",
        account_based_in="United States",
        account_based_in_fetched_at=observed_at,
    )
    Account.objects.create(
        author_id="region-account",
        handle="region-secret-handle",
        account_based_in="Europe",
        country_code="US",
        account_based_in_fetched_at=observed_at,
    )
    Account.objects.create(
        author_id="unresolved-account",
        handle="unresolved-secret-handle",
        account_based_in="Korea",
        based_in_region_key="europe",
        account_based_in_fetched_at=observed_at,
    )


def test_reconciliation_defaults_to_zero_write_dry_run():
    _seed_accounts()
    stdout = StringIO()

    with patch.object(
        Account,
        "apply_observation",
        side_effect=AssertionError("dry run entered the write gateway"),
    ):
        call_command("reconcile_account_geography", stdout=stdout)

    report = json.loads(stdout.getvalue())
    assert report["mode"] == "dry_run"
    assert report["classification"] == {
        "country": 1,
        "region": 1,
        "unresolved": 1,
    }
    assert report["would_change"] == 3
    assert report["http_calls"] == 0
    assert report["provider_credits"] == 0
    assert report["writes"] == 0


@override_settings(OLLIJA_STAGING_MODE=True)
def test_staging_apply_is_idempotent_and_uses_no_provider_io(tmp_path):
    _seed_accounts()
    first_json = tmp_path / "first.json"
    first_markdown = tmp_path / "first.md"
    dry_stdout = StringIO()
    call_command("reconcile_account_geography", stdout=dry_stdout)
    dry_report = json.loads(dry_stdout.getvalue())

    with patch(
        "requests.sessions.Session.request",
        side_effect=AssertionError("reconciliation attempted provider I/O"),
    ):
        call_command(
            "reconcile_account_geography",
            apply=True,
            target="staging",
            confirm_database="pushinweight_staging",
            json_report=str(first_json),
            markdown_report=str(first_markdown),
            stdout=StringIO(),
        )

    country = Account.objects.get(pk="country-account")
    region = Account.objects.get(pk="region-account")
    unresolved = Account.objects.get(pk="unresolved-account")
    assert (country.country_code, country.based_in_region_key) == ("US", None)
    assert (region.country_code, region.based_in_region_key) == (None, "europe")
    assert (unresolved.country_code, unresolved.based_in_region_key) == (None, None)

    report = json.loads(first_json.read_text())
    assert report["classification"] == dry_report["classification"]
    assert report["changed"] == 3
    assert report["rejected"] == 0
    assert report["http_calls"] == 0
    assert first_markdown.exists()
    serialized = first_json.read_text()
    assert "country-secret-handle" not in serialized
    assert "country-account" not in serialized

    second_json = tmp_path / "second.json"
    call_command(
        "reconcile_account_geography",
        apply=True,
        target="staging",
        confirm_database="pushinweight_staging",
        json_report=str(second_json),
        markdown_report=str(tmp_path / "second.md"),
        stdout=StringIO(),
    )
    assert json.loads(second_json.read_text())["changed"] == 0


def test_unreviewed_raw_value_fails_before_any_write():
    account = Account.objects.create(
        author_id="unknown",
        account_based_in="Asia Pacific",
        country_code="US",
        account_based_in_fetched_at=datetime(2026, 8, 31, tzinfo=UTC),
    )

    with pytest.raises(CommandError, match="unreviewed account_based_in values"):
        call_command("reconcile_account_geography", stdout=StringIO())

    account.refresh_from_db()
    assert account.country_code == "US"


def test_taxonomy_seed_drift_fails_preflight():
    AccountBasedInMapping.objects.filter(pk="United States").delete()
    Account.objects.create(
        author_id="seed-drift",
        account_based_in="United States",
        account_based_in_fetched_at=datetime(2026, 8, 31, tzinfo=UTC),
    )

    with pytest.raises(CommandError, match="taxonomy seed does not match"):
        call_command("reconcile_account_geography", stdout=StringIO())


@override_settings(OLLIJA_STAGING_MODE=True)
def test_apply_refuses_when_nonblocking_geography_lock_is_held(tmp_path):
    _seed_accounts()

    with (
        patch(
            "monitor.management.commands.reconcile_account_geography._geography_run_lock",
            side_effect=CommandError(
                "another account geography reconciliation is running"
            ),
        ),
        pytest.raises(CommandError, match="another account geography reconciliation"),
    ):
        call_command(
            "reconcile_account_geography",
            apply=True,
            target="staging",
            confirm_database="pushinweight_staging",
            json_report=str(tmp_path / "locked.json"),
            markdown_report=str(tmp_path / "locked.md"),
            stdout=StringIO(),
        )


@override_settings(OLLIJA_STAGING_MODE=False)
def test_production_apply_requires_fresh_geography_receipt(monkeypatch, tmp_path):
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "production")
    _seed_accounts()

    with (
        patch(
            "monitor.management.commands.reconcile_account_geography._current_database_name",
            return_value="pushinweight_shadow",
        ),
        patch(
            "monitor.management.commands.reconcile_account_geography._required_migrations_applied",
            return_value=True,
        ),
        patch.object(
            Account,
            "apply_observation",
            side_effect=AssertionError("missing receipt reached writes"),
        ),
        pytest.raises(
            CommandError, match="production apply requires a geography recovery receipt"
        ),
    ):
        call_command(
            "reconcile_account_geography",
            apply=True,
            target="production",
            confirm_database="pushinweight_shadow",
            json_report=str(tmp_path / "production.json"),
            markdown_report=str(tmp_path / "production.md"),
            stdout=StringIO(),
        )


@override_settings(OLLIJA_STAGING_MODE=False)
def test_production_apply_requires_exact_frozen_census(monkeypatch, tmp_path):
    from monitor.account_geography_recovery import _build_geography_receipt

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "production")
    _seed_accounts()
    _payload, token = _build_geography_receipt(
        created_at=datetime.now(tz=UTC),
        snapshot_relation="account_geography_backup.accounts_geo_20260831t210000z",
        snapshot_account_count=3,
        snapshot_row_digest="a" * 64,
        restore_account_count=3,
        restore_row_digest="a" * 64,
    )

    with (
        patch(
            "monitor.management.commands.reconcile_account_geography._current_database_name",
            return_value="pushinweight_shadow",
        ),
        patch(
            "monitor.management.commands.reconcile_account_geography._required_migrations_applied",
            return_value=True,
        ),
        patch(
            "monitor.management.commands.reconcile_account_geography.verify_geography_recovery_snapshot",
            return_value=Account.objects.all(),
        ),
        patch.object(
            Account,
            "apply_observation",
            side_effect=AssertionError("census mismatch reached writes"),
        ),
        pytest.raises(CommandError, match="does not match frozen input"),
    ):
        call_command(
            "reconcile_account_geography",
            apply=True,
            target="production",
            confirm_database="pushinweight_shadow",
            recovery_receipt=token,
            json_report=str(tmp_path / "production.json"),
            markdown_report=str(tmp_path / "production.md"),
            stdout=StringIO(),
        )


def test_geography_receipt_rejects_stale_timestamp():
    from monitor.account_geography_recovery import (
        _build_geography_receipt,
        parse_geography_recovery_receipt,
    )

    _payload, token = _build_geography_receipt(
        created_at=datetime.now(tz=UTC) - timedelta(days=2),
        snapshot_relation="account_geography_backup.accounts_geo_20260831t210000z",
        snapshot_account_count=3,
        snapshot_row_digest="a" * 64,
        restore_account_count=3,
        restore_row_digest="a" * 64,
    )

    with pytest.raises(CommandError, match="geography recovery receipt is stale"):
        parse_geography_recovery_receipt(token)
