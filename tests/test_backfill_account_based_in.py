from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO
from unittest.mock import AsyncMock, patch

import pytest
from django.core.management import call_command
from django.test import override_settings

from core.models import Account
from monitor.management.commands.backfill_account_based_in import (
    _is_authorized_staging_executor,
    _select_accounts,
)
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


def _unavailable(author_id: str) -> FetchOutcome:
    observed_at = datetime(2026, 8, 30, tzinfo=UTC)
    return FetchOutcome(
        author_id=author_id,
        observation=UserAboutObservation(
            author_id=author_id,
            candidates={
                "unavailable": True,
                "unavailable_reason": "Account unavailable",
                "account_based_in_fetched_at": observed_at,
            },
            present_fields={
                "unavailable",
                "unavailable_reason",
                "account_based_in_fetched_at",
            },
        ),
        reason="success",
        status_code=200,
        latency_ms=10,
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


@override_settings(OLLIJA_STAGING_MODE=True)
def test_unavailable_result_checkpoints_selected_handle_without_leaking_reason(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("TWITTERAPI_IO_API_KEY", "managed-secret")
    account = Account.objects.create(author_id="42", handle="selected_handle")

    with patch(
        "monitor.management.commands.backfill_account_based_in.fetch_user_about_batch",
        new=AsyncMock(return_value=_batch([_unavailable(account.author_id)])),
    ):
        call_command(
            "backfill_account_based_in",
            apply=True,
            limit=1,
            max_attempts=1,
            max_credits=18,
            max_wall_seconds=60,
            max_qps=1,
            provider_qps=1,
            seed="test-seed",
            json_report=str(tmp_path / "unavailable.json"),
            markdown_report=str(tmp_path / "unavailable.md"),
            stdout=StringIO(),
        )

    account.refresh_from_db()
    report = (tmp_path / "unavailable.json").read_text()
    assert account.unavailable is True
    assert account.unavailable_reason == "Account unavailable"
    assert account.account_based_in_fetched_at is not None
    assert '"success_empty": 1' in report
    assert "Account unavailable" not in report


@override_settings(OLLIJA_STAGING_MODE=True)
def test_schema_drift_reaches_report_without_response_values_or_account_identity(
    tmp_path,
    monkeypatch,
):
    import json
    from unittest.mock import MagicMock

    monkeypatch.setenv("TWITTERAPI_IO_API_KEY", "managed-secret")
    account = Account.objects.create(author_id="424242", handle="selected_handle")
    response = MagicMock()
    response.status = 200
    response.headers = {}
    response.text = AsyncMock(
        return_value=json.dumps(
            {
                "status": "success",
                "data": {
                    "id": account.author_id,
                    "userName": account.handle,
                    "unknownLeaf": "private-response-value",
                },
            }
        )
    )
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.get = MagicMock(return_value=response)
    monkeypatch.setattr("aiohttp.ClientSession", lambda **kwargs: session)
    json_path = tmp_path / "schema-drift.json"
    markdown_path = tmp_path / "schema-drift.md"

    call_command(
        "backfill_account_based_in",
        apply=True,
        limit=1,
        max_attempts=1,
        max_credits=18,
        max_wall_seconds=60,
        max_qps=1,
        provider_qps=1,
        seed="test-seed",
        json_report=str(json_path),
        markdown_report=str(markdown_path),
        stdout=StringIO(),
    )

    report = json_path.read_text()
    account.refresh_from_db()
    assert '"stop_reason": "schema_drift"' in report
    assert "$.data.unknownLeaf:string" in report
    assert "private-response-value" not in report
    assert "managed-secret" not in report
    assert account.author_id not in report
    assert account.handle not in report
    assert account.account_based_in_fetched_at is None


@override_settings(OLLIJA_STAGING_MODE=True)
def test_live_user_about_shape_reaches_typed_account_fields(tmp_path, monkeypatch):
    import json
    from unittest.mock import MagicMock

    monkeypatch.setenv("TWITTERAPI_IO_API_KEY", "managed-secret")
    account = Account.objects.create(author_id="424242", handle="selected_handle")
    response = MagicMock()
    response.status = 200
    response.headers = {}
    response.text = AsyncMock(
        return_value=json.dumps(
            {
                "status": "success",
                "msg": "ok",
                "data": {
                    "id": account.author_id,
                    "name": "Selected Account",
                    "userName": account.handle,
                    "createdAt": "Wed Jul 22 03:40:35 +0000 2020",
                    "isVerified": True,
                    "isBlueVerified": False,
                    "protected": False,
                    "profilePicture": "https://cdn.example/avatar.png",
                    "verification_info": {
                        "id": "verification-42",
                        "is_identity_verified": True,
                        "reason": {"verified_since_msec": "1784691635000"},
                    },
                    "affiliates_highlighted_label": {},
                    "about_profile": {
                        "account_based_in": "United States",
                        "location_accurate": True,
                        "created_country_accurate": False,
                        "learn_more_url": "https://help.example/about",
                        "source": "ip",
                        "username_changes": {
                            "count": "2",
                            "last_changed_at_msec": "1784691635000",
                        },
                    },
                    "identity_profile_labels_highlighted_label": {},
                },
            }
        )
    )
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.get = MagicMock(return_value=response)
    monkeypatch.setattr("aiohttp.ClientSession", lambda **kwargs: session)
    json_path = tmp_path / "live-shape.json"
    markdown_path = tmp_path / "live-shape.md"

    call_command(
        "backfill_account_based_in",
        apply=True,
        limit=1,
        max_attempts=1,
        max_credits=18,
        max_wall_seconds=60,
        max_qps=1,
        provider_qps=1,
        seed="test-seed",
        json_report=str(json_path),
        markdown_report=str(markdown_path),
        stdout=StringIO(),
    )

    account.refresh_from_db()
    report = json_path.read_text()
    assert account.verified is True
    assert account.profile_picture.endswith("avatar.png")
    assert account.created_country_accurate is False
    assert account.username_changes_last_changed_at_msec == 1_784_691_635_000
    assert account.verification_info_id == "verification-42"
    assert account.verification_info_is_identity_verified is True
    assert account.verification_info_reason_verified_since_msec == 1_784_691_635_000
    assert account.country_code == "US"
    assert account.account_based_in_fetched_at is not None
    assert '"accepted": 1' in report
    assert '"schema_diagnostics": []' in report
    assert account.author_id not in report
    assert account.handle not in report


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


@override_settings(OLLIJA_STAGING_MODE=False)
@pytest.mark.parametrize(
    ("deployment_environment", "database_name", "expected"),
    [
        ("staging", "pushinweight_staging", True),
        ("staging", "pushinweight_shadow", False),
        ("production", "pushinweight_staging", False),
    ],
)
def test_staging_harvester_guard_requires_environment_and_database_identity(
    monkeypatch,
    deployment_environment,
    database_name,
    expected,
):
    from unittest.mock import MagicMock

    monkeypatch.setenv(
        "X_MONITOR_DEPLOYMENT_ENVIRONMENT",
        deployment_environment,
    )
    cursor = MagicMock()
    cursor.fetchone.return_value = (database_name,)
    context = MagicMock()
    context.__enter__.return_value = cursor
    context.__exit__.return_value = None

    with patch(
        "monitor.management.commands.backfill_account_based_in.connection.cursor",
        return_value=context,
    ):
        assert _is_authorized_staging_executor() is expected


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
