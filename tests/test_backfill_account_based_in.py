from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO
from unittest.mock import AsyncMock, patch

import pytest
from django.core.management import call_command
from django.test import override_settings

from core.models import Account
from monitor.management.commands.backfill_account_based_in import _select_accounts
from monitor.twitterapi.user_about import (
    FetchBatchResult,
    FetchOutcome,
    UserAboutObservation,
)

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def _success(author_id: str, country: str = "US") -> FetchOutcome:
    observed_at = datetime(2026, 8, 29, tzinfo=UTC)
    return FetchOutcome(
        author_id=author_id,
        observation=UserAboutObservation(
            author_id=author_id,
            candidates={
                "account_based_in": "United States",
                "country_code": country,
                "account_based_in_fetched_at": observed_at,
            },
            present_fields={
                "account_based_in",
                "country_code",
                "account_based_in_fetched_at",
            },
        ),
        reason="success",
        status_code=200,
        latency_ms=10,
    )


def _batch(outcomes):
    return FetchBatchResult(
        outcomes=outcomes,
        attempts=len(outcomes),
        retries=0,
        projected_credits=18 * len(outcomes),
        latencies_ms=[10 for _ in outcomes],
        wall_seconds=1.0,
        stop_reason=None,
    )


def test_default_dry_run_selects_without_http_or_writes():
    for index in range(3):
        Account.objects.create(author_id=str(index), handle=f"user{index}")
    stdout = StringIO()

    with patch(
        "monitor.management.commands.backfill_account_based_in.fetch_user_about_batch",
        side_effect=AssertionError("dry-run performed HTTP"),
    ):
        call_command(
            "backfill_account_based_in",
            limit=3,
            seed="test-seed",
            stdout=stdout,
        )

    assert (
        Account.objects.filter(account_based_in_fetched_at__isnull=False).count() == 0
    )
    assert '"mode": "dry_run"' in stdout.getvalue()


@override_settings(OLLIJA_STAGING_MODE=True)
def test_apply_writes_only_matching_selected_accounts(tmp_path, monkeypatch):
    monkeypatch.setenv("TWITTERAPI_IO_API_KEY", "managed-secret")
    accounts = [
        Account.objects.create(author_id=str(index), handle=f"user{index}")
        for index in range(2)
    ]
    result = _batch([_success(account.author_id) for account in accounts])
    json_path = tmp_path / "2026-08-29-230000-pilot.json"
    markdown_path = tmp_path / "2026-08-29-230000-pilot.md"

    with patch(
        "monitor.management.commands.backfill_account_based_in.fetch_user_about_batch",
        new=AsyncMock(return_value=result),
    ) as fetch:
        call_command(
            "backfill_account_based_in",
            apply=True,
            limit=2,
            max_attempts=2,
            max_credits=36,
            max_wall_seconds=60,
            max_qps=5,
            provider_qps=6,
            seed="test-seed",
            json_report=str(json_path),
            markdown_report=str(markdown_path),
            stdout=StringIO(),
        )

    assert Account.objects.filter(country_code="US").count() == 2
    assert fetch.await_args.kwargs["api_key"] == "managed-secret"
    report = json_path.read_text()
    assert "managed-secret" not in report
    assert "user0" not in report
    assert '"accepted": 2' in report
    assert markdown_path.exists()


@override_settings(OLLIJA_STAGING_MODE=False)
def test_apply_refuses_outside_staging(monkeypatch, tmp_path):
    monkeypatch.setenv("TWITTERAPI_IO_API_KEY", "managed-secret")
    Account.objects.create(author_id="1", handle="user1")

    with pytest.raises(Exception, match="staging"):
        call_command(
            "backfill_account_based_in",
            apply=True,
            limit=1,
            provider_qps=3,
            json_report=str(tmp_path / "report.json"),
            markdown_report=str(tmp_path / "report.md"),
        )


@override_settings(OLLIJA_STAGING_MODE=True)
def test_apply_refuses_budget_above_pilot_caps(monkeypatch, tmp_path):
    monkeypatch.setenv("TWITTERAPI_IO_API_KEY", "managed-secret")
    with pytest.raises(Exception, match="pilot cap"):
        call_command(
            "backfill_account_based_in",
            apply=True,
            limit=101,
            provider_qps=3,
            json_report=str(tmp_path / "report.json"),
            markdown_report=str(tmp_path / "report.md"),
        )


@override_settings(OLLIJA_STAGING_MODE=True)
def test_success_empty_checkpoint_is_skipped_on_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("TWITTERAPI_IO_API_KEY", "managed-secret")
    account = Account.objects.create(author_id="1", handle="user1")
    observed_at = datetime(2026, 8, 29, tzinfo=UTC)
    result = _batch(
        [
            FetchOutcome(
                author_id=account.author_id,
                observation=UserAboutObservation(
                    author_id=account.author_id,
                    candidates={"account_based_in_fetched_at": observed_at},
                    present_fields={"account_based_in_fetched_at"},
                ),
                reason="success",
                status_code=200,
                latency_ms=10,
            )
        ]
    )

    with patch(
        "monitor.management.commands.backfill_account_based_in.fetch_user_about_batch",
        new=AsyncMock(return_value=result),
    ):
        call_command(
            "backfill_account_based_in",
            apply=True,
            limit=1,
            max_attempts=1,
            max_credits=18,
            max_wall_seconds=60,
            max_qps=5,
            provider_qps=6,
            seed="test-seed",
            json_report=str(tmp_path / "pilot.json"),
            markdown_report=str(tmp_path / "pilot.md"),
            stdout=StringIO(),
        )

    account.refresh_from_db()
    assert account.account_based_in_fetched_at == observed_at
    assert _select_accounts(limit=1, seed="test-seed", refresh=False) == []
