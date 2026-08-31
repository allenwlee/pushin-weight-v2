from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from io import StringIO
from unittest.mock import AsyncMock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from core.models import Account
from monitor.management.commands.backfill_account_based_in import (
    _is_authorized_staging_executor,
    _select_accounts,
    _selection_distribution,
)
from monitor.twitterapi.user_about import (
    FetchBatchResult,
    FetchOutcome,
    UserAboutObservation,
)
from x_monitor.twitterapi_credentials import (
    TWITTERAPI_IO_ON_DEMAND_API_KEY_ENV,
    TWITTERAPI_IO_SCHEDULED_API_KEY_ENV,
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


def _production_recovery_receipt(
    *,
    account_count: int,
    created_at: datetime | None = None,
) -> str:
    payload = {
        "schema_version": 1,
        "database": "pushinweight_shadow",
        "created_at": (created_at or datetime.now(UTC)).isoformat(),
        "snapshot_account_count": account_count,
        "snapshot_row_digest": "a" * 64,
        "restore_account_count": account_count,
        "restore_row_digest": "a" * 64,
        "storage": "render-postgres-encrypted-at-rest",
        "snapshot_relation": "account_user_about_backup.accounts_20260831t120000z",
        "restore_proof": "temporary-relation-count-and-digest-match",
    }
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    payload["receipt_sha256"] = hashlib.sha256(canonical).hexdigest()
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(encoded).decode().rstrip("=")


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


def _schema_drift(author_id: str) -> FetchOutcome:
    return FetchOutcome(
        author_id=author_id,
        observation=None,
        reason="schema_drift",
        status_code=200,
        latency_ms=10,
        schema_diagnostic=(
            "parser_error:response.data.example must be an integer",
            "$.data.example:number",
        ),
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


def test_diversity_stratified_selection_balances_age_size_and_location_proxy():
    ages = [
        datetime(2012, 1, 1, tzinfo=UTC),
        datetime(2017, 1, 1, tzinfo=UTC),
        datetime(2022, 1, 1, tzinfo=UTC),
    ]
    sizes = [100, 10_000, 1_000_000, None]
    locations = ["United States", "France", "日本", "Brazil", None]
    index = 0
    for age in ages:
        for followers_count in sizes:
            for location in locations:
                for _ in range(2):
                    index += 1
                    Account.objects.create(
                        author_id=str(index),
                        handle=f"user{index}",
                        created_at=age,
                        followers_count=followers_count,
                        location=location,
                    )

    selections = _select_accounts(
        limit=100,
        seed="diversity-test",
        refresh=False,
        strategy="diversity_stratified",
    )

    assert len(selections) == 100
    assert _selection_distribution(selections) == {
        "account_age": {
            "middle_2015_2019": 33,
            "new_2020_plus": 33,
            "old_pre_2015": 34,
        },
        "audience_size": {
            "large_100k_plus": 25,
            "medium_1k_100k": 25,
            "small_lt_1k": 25,
            "unknown": 25,
        },
        "profile_location_proxy": {
            "eu": 20,
            "jp": 20,
            "other": 20,
            "unknown": 20,
            "us": 20,
        },
    }


@override_settings(OLLIJA_STAGING_MODE=True)
def test_apply_does_not_fall_back_to_scheduled_or_legacy_key(tmp_path, monkeypatch):
    monkeypatch.delenv(TWITTERAPI_IO_ON_DEMAND_API_KEY_ENV, raising=False)
    monkeypatch.setenv(TWITTERAPI_IO_SCHEDULED_API_KEY_ENV, "scheduled-secret")
    monkeypatch.setenv("TWITTERAPI_IO_API_KEY", "legacy-secret")
    Account.objects.create(author_id="1", handle="user1")

    with pytest.raises(CommandError, match=TWITTERAPI_IO_ON_DEMAND_API_KEY_ENV):
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
            json_report=str(tmp_path / "pilot.json"),
            markdown_report=str(tmp_path / "pilot.md"),
            stdout=StringIO(),
        )


@override_settings(OLLIJA_STAGING_MODE=True)
def test_apply_writes_only_matching_selected_accounts(tmp_path, monkeypatch):
    monkeypatch.setenv(TWITTERAPI_IO_ON_DEMAND_API_KEY_ENV, "on-demand-secret")
    monkeypatch.setenv(TWITTERAPI_IO_SCHEDULED_API_KEY_ENV, "scheduled-secret")
    monkeypatch.setenv("TWITTERAPI_IO_API_KEY", "legacy-secret")
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
    assert fetch.await_args.kwargs["api_key"] == "on-demand-secret"
    report = json_path.read_text()
    assert "on-demand-secret" not in report
    assert "scheduled-secret" not in report
    assert "legacy-secret" not in report
    assert "user0" not in report
    assert '"accepted": 2' in report
    assert markdown_path.exists()


@override_settings(OLLIJA_STAGING_MODE=True)
def test_unavailable_result_checkpoints_selected_handle_without_leaking_reason(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(TWITTERAPI_IO_ON_DEMAND_API_KEY_ENV, "managed-secret")
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

    monkeypatch.setenv(TWITTERAPI_IO_ON_DEMAND_API_KEY_ENV, "managed-secret")
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
    assert '"stop_reason": null' in report
    assert '"quarantined_accounts": 1' in report
    assert '"remaining_retryable": 0' in report
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

    monkeypatch.setenv(TWITTERAPI_IO_ON_DEMAND_API_KEY_ENV, "managed-secret")
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
                        "reason": {
                            "verified_since_msec": "1784691635000",
                            "override_verified_year": 2012,
                        },
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
    assert account.verification_info_reason_override_verified_year == 2012
    assert account.country_code == "US"
    assert account.account_based_in_fetched_at is not None
    assert '"accepted": 1' in report
    assert '"schema_diagnostics": []' in report
    assert account.author_id not in report
    assert account.handle not in report


@override_settings(OLLIJA_STAGING_MODE=False)
def test_apply_refuses_outside_staging(monkeypatch, tmp_path):
    monkeypatch.setenv(TWITTERAPI_IO_ON_DEMAND_API_KEY_ENV, "managed-secret")
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
def test_production_apply_checks_environment_before_credential_access(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "staging")
    Account.objects.create(author_id="1", handle="user1")

    with (
        patch(
            "monitor.management.commands.backfill_account_based_in.require_twitterapi_api_key",
            side_effect=AssertionError("credential loaded before production guard"),
        ),
        pytest.raises(CommandError, match="production"),
    ):
        call_command(
            "backfill_account_based_in",
            apply=True,
            target="production",
            limit=1,
            max_attempts=1,
            max_credits=18,
            max_wall_seconds=60,
            max_qps=1,
            provider_qps=1,
            concurrency=1,
            chunk_size=1,
            recovery_receipt=_production_recovery_receipt(account_count=1),
            json_report=str(tmp_path / "report.json"),
            markdown_report=str(tmp_path / "report.md"),
            stdout=StringIO(),
        )


@override_settings(OLLIJA_STAGING_MODE=False)
def test_production_apply_requires_recovery_receipt_before_credential(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "production")
    Account.objects.create(author_id="1", handle="user1")

    with (
        patch(
            "monitor.management.commands.backfill_account_based_in._current_database_name",
            return_value="pushinweight_shadow",
        ),
        patch(
            "monitor.management.commands.backfill_account_based_in.require_twitterapi_api_key",
            side_effect=AssertionError("credential loaded before recovery guard"),
        ),
        pytest.raises(CommandError, match="recovery receipt"),
    ):
        call_command(
            "backfill_account_based_in",
            apply=True,
            target="production",
            limit=1,
            max_attempts=1,
            max_credits=18,
            max_wall_seconds=60,
            max_qps=1,
            provider_qps=1,
            concurrency=1,
            chunk_size=1,
            json_report=str(tmp_path / "report.json"),
            markdown_report=str(tmp_path / "report.md"),
            stdout=StringIO(),
        )


@override_settings(OLLIJA_STAGING_MODE=False)
def test_production_apply_rejects_stale_recovery_receipt_before_credential(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "production")
    Account.objects.create(author_id="1", handle="user1")
    stale = _production_recovery_receipt(
        account_count=1,
        created_at=datetime.now(UTC) - timedelta(hours=25),
    )

    with (
        patch(
            "monitor.management.commands.backfill_account_based_in._current_database_name",
            return_value="pushinweight_shadow",
        ),
        patch(
            "monitor.management.commands.backfill_account_based_in._required_migrations_applied",
            return_value=True,
        ),
        patch(
            "monitor.management.commands.backfill_account_based_in.require_twitterapi_api_key",
            side_effect=AssertionError("credential loaded before recovery guard"),
        ),
        pytest.raises(CommandError, match="stale"),
    ):
        call_command(
            "backfill_account_based_in",
            apply=True,
            target="production",
            limit=1,
            max_attempts=1,
            max_credits=18,
            max_wall_seconds=60,
            max_qps=1,
            provider_qps=1,
            concurrency=1,
            chunk_size=1,
            recovery_receipt=stale,
            json_report=str(tmp_path / "report.json"),
            markdown_report=str(tmp_path / "report.md"),
            stdout=StringIO(),
        )


@override_settings(OLLIJA_STAGING_MODE=False)
def test_production_apply_loses_advisory_lock_before_credential_access(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "production")
    Account.objects.create(author_id="1", handle="user1")

    with (
        patch(
            "monitor.management.commands.backfill_account_based_in._current_database_name",
            return_value="pushinweight_shadow",
        ),
        patch(
            "monitor.management.commands.backfill_account_based_in._required_migrations_applied",
            return_value=True,
        ),
        patch(
            "monitor.management.commands.backfill_account_based_in._verify_recovery_snapshot"
        ),
        patch(
            "monitor.management.commands.backfill_account_based_in._production_run_lock",
            side_effect=CommandError(
                "another production User About backfill is running"
            ),
        ),
        patch(
            "monitor.management.commands.backfill_account_based_in.require_twitterapi_api_key",
            side_effect=AssertionError("credential loaded after losing run lock"),
        ),
        pytest.raises(CommandError, match="another production"),
    ):
        call_command(
            "backfill_account_based_in",
            apply=True,
            target="production",
            limit=1,
            max_attempts=1,
            max_credits=18,
            max_wall_seconds=60,
            max_qps=1,
            provider_qps=1,
            concurrency=1,
            chunk_size=1,
            recovery_receipt=_production_recovery_receipt(account_count=1),
            json_report=str(tmp_path / "report.json"),
            markdown_report=str(tmp_path / "report.md"),
            stdout=StringIO(),
        )


@override_settings(OLLIJA_STAGING_MODE=False)
def test_production_apply_excludes_nonnumeric_account_ids_before_provider_call(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "production")
    monkeypatch.setenv(TWITTERAPI_IO_ON_DEMAND_API_KEY_ENV, "managed-secret")
    numeric = Account.objects.create(author_id="42", handle="numeric_user")
    placeholders = [
        Account.objects.create(author_id="handle:legacy", handle="legacy_user"),
        Account.objects.create(author_id="synthetic:seed", handle="seed_user"),
    ]
    fetch = AsyncMock(return_value=_batch([_success(numeric.author_id)]))

    with (
        patch(
            "monitor.management.commands.backfill_account_based_in._current_database_name",
            return_value="pushinweight_shadow",
        ),
        patch(
            "monitor.management.commands.backfill_account_based_in._required_migrations_applied",
            return_value=True,
        ),
        patch(
            "monitor.management.commands.backfill_account_based_in._verify_recovery_snapshot"
        ),
        patch(
            "monitor.management.commands.backfill_account_based_in._production_run_lock"
        ),
        patch(
            "monitor.management.commands.backfill_account_based_in.fetch_user_about_batch",
            new=fetch,
        ),
    ):
        call_command(
            "backfill_account_based_in",
            apply=True,
            target="production",
            limit=3,
            max_attempts=3,
            max_credits=54,
            max_wall_seconds=60,
            max_qps=1,
            provider_qps=1,
            concurrency=1,
            chunk_size=1,
            recovery_receipt=_production_recovery_receipt(account_count=3),
            json_report=str(tmp_path / "report.json"),
            markdown_report=str(tmp_path / "report.md"),
            stdout=StringIO(),
        )

    fetch.assert_awaited_once()
    selections = fetch.await_args.args[0]
    assert [selection.author_id for selection in selections] == [numeric.author_id]
    assert all(
        account.account_based_in_fetched_at is None
        for account in Account.objects.filter(
            author_id__in=[placeholder.author_id for placeholder in placeholders]
        )
    )


@override_settings(OLLIJA_STAGING_MODE=False)
def test_production_chunk_checkpoint_survives_crash_and_restart(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "production")
    monkeypatch.setenv(TWITTERAPI_IO_ON_DEMAND_API_KEY_ENV, "managed-secret")
    for index in range(3):
        Account.objects.create(author_id=str(index), handle=f"user{index}")
    recovery_receipt = _production_recovery_receipt(account_count=3)
    fetched_ids: list[list[str]] = []

    async def crash_after_first_chunk(selections, **_kwargs):
        fetched_ids.append([selection.author_id for selection in selections])
        if len(fetched_ids) == 1:
            return _batch([_success(selections[0].author_id)])
        raise RuntimeError("simulated process crash")

    common = {
        "apply": True,
        "target": "production",
        "limit": 3,
        "max_attempts": 3,
        "max_credits": 54,
        "max_wall_seconds": 60,
        "max_qps": 1,
        "provider_qps": 1,
        "concurrency": 1,
        "chunk_size": 1,
        "recovery_receipt": recovery_receipt,
        "json_report": str(tmp_path / "report.json"),
        "markdown_report": str(tmp_path / "report.md"),
        "stdout": StringIO(),
    }
    with (
        patch(
            "monitor.management.commands.backfill_account_based_in._current_database_name",
            return_value="pushinweight_shadow",
        ),
        patch(
            "monitor.management.commands.backfill_account_based_in._required_migrations_applied",
            return_value=True,
        ),
        patch(
            "monitor.management.commands.backfill_account_based_in._verify_recovery_snapshot"
        ),
        patch(
            "monitor.management.commands.backfill_account_based_in._production_run_lock"
        ),
        patch(
            "monitor.management.commands.backfill_account_based_in.fetch_user_about_batch",
            side_effect=crash_after_first_chunk,
        ),
        pytest.raises(RuntimeError, match="simulated process crash"),
    ):
        call_command("backfill_account_based_in", **common)

    completed_id = fetched_ids[0][0]
    assert Account.objects.get(author_id=completed_id).account_based_in_fetched_at
    remaining_ids: list[str] = []

    async def finish_remaining(selections, **_kwargs):
        remaining_ids.extend(selection.author_id for selection in selections)
        return _batch([_success(selection.author_id) for selection in selections])

    with (
        patch(
            "monitor.management.commands.backfill_account_based_in._current_database_name",
            return_value="pushinweight_shadow",
        ),
        patch(
            "monitor.management.commands.backfill_account_based_in._required_migrations_applied",
            return_value=True,
        ),
        patch(
            "monitor.management.commands.backfill_account_based_in._verify_recovery_snapshot"
        ),
        patch(
            "monitor.management.commands.backfill_account_based_in._production_run_lock"
        ),
        patch(
            "monitor.management.commands.backfill_account_based_in.fetch_user_about_batch",
            side_effect=finish_remaining,
        ),
    ):
        call_command("backfill_account_based_in", **{**common, "limit": 3})

    assert completed_id not in remaining_ids
    assert (
        Account.objects.filter(account_based_in_fetched_at__isnull=False).count() == 3
    )
    report = (tmp_path / "report.json").read_text()
    assert "managed-secret" not in report
    assert recovery_receipt not in report
    assert all(f"user{index}" not in report for index in range(3))
    assert '"remaining_eligible": 0' in report


@override_settings(OLLIJA_STAGING_MODE=False)
def test_production_apply_requires_current_snapshot_relation_before_credential(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "production")
    Account.objects.create(author_id="1", handle="user1")

    with (
        patch(
            "monitor.management.commands.backfill_account_based_in._current_database_name",
            return_value="pushinweight_shadow",
        ),
        patch(
            "monitor.management.commands.backfill_account_based_in._required_migrations_applied",
            return_value=True,
        ),
        patch(
            "monitor.management.commands.backfill_account_based_in.require_twitterapi_api_key",
            side_effect=AssertionError("credential loaded before snapshot guard"),
        ),
        pytest.raises(CommandError, match="snapshot relation is unavailable"),
    ):
        call_command(
            "backfill_account_based_in",
            apply=True,
            target="production",
            limit=1,
            max_attempts=1,
            max_credits=18,
            max_wall_seconds=60,
            max_qps=1,
            provider_qps=1,
            concurrency=1,
            chunk_size=1,
            recovery_receipt=_production_recovery_receipt(account_count=1),
            json_report=str(tmp_path / "report.json"),
            markdown_report=str(tmp_path / "report.md"),
            stdout=StringIO(),
        )


@override_settings(OLLIJA_STAGING_MODE=False)
def test_production_require_complete_fails_after_writing_resume_report(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "production")
    monkeypatch.setenv(TWITTERAPI_IO_ON_DEMAND_API_KEY_ENV, "managed-secret")
    for index in range(2):
        Account.objects.create(author_id=str(index), handle=f"user{index}")
    json_path = tmp_path / "incomplete.json"

    async def fetch_selected(selections, **_kwargs):
        return _batch([_success(selections[0].author_id)])

    with (
        patch(
            "monitor.management.commands.backfill_account_based_in._current_database_name",
            return_value="pushinweight_shadow",
        ),
        patch(
            "monitor.management.commands.backfill_account_based_in._required_migrations_applied",
            return_value=True,
        ),
        patch(
            "monitor.management.commands.backfill_account_based_in._verify_recovery_snapshot"
        ),
        patch(
            "monitor.management.commands.backfill_account_based_in._production_run_lock"
        ),
        patch(
            "monitor.management.commands.backfill_account_based_in.fetch_user_about_batch",
            side_effect=fetch_selected,
        ),
        pytest.raises(CommandError, match="1 retryable Accounts remain"),
    ):
        call_command(
            "backfill_account_based_in",
            apply=True,
            target="production",
            require_complete=True,
            limit=1,
            max_attempts=1,
            max_credits=18,
            max_wall_seconds=60,
            max_qps=1,
            provider_qps=1,
            concurrency=1,
            chunk_size=1,
            recovery_receipt=_production_recovery_receipt(account_count=2),
            json_report=str(json_path),
            markdown_report=str(tmp_path / "incomplete.md"),
            stdout=StringIO(),
        )

    assert json.loads(json_path.read_text())["outcome"]["remaining_eligible"] == 1


@override_settings(OLLIJA_STAGING_MODE=False)
def test_production_require_complete_quarantines_account_drift_and_continues(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "production")
    monkeypatch.setenv(TWITTERAPI_IO_ON_DEMAND_API_KEY_ENV, "managed-secret")
    for index in range(2):
        Account.objects.create(author_id=str(index), handle=f"user{index}")
    json_path = tmp_path / "quarantined.json"
    quarantined_ids: list[str] = []
    accepted_ids: list[str] = []

    async def fetch_selected(selections, **_kwargs):
        quarantined_ids.append(selections[0].author_id)
        accepted_ids.append(selections[1].author_id)
        return _batch(
            [
                _schema_drift(selections[0].author_id),
                _success(selections[1].author_id),
            ]
        )

    with (
        patch(
            "monitor.management.commands.backfill_account_based_in._current_database_name",
            return_value="pushinweight_shadow",
        ),
        patch(
            "monitor.management.commands.backfill_account_based_in._required_migrations_applied",
            return_value=True,
        ),
        patch(
            "monitor.management.commands.backfill_account_based_in._verify_recovery_snapshot"
        ),
        patch(
            "monitor.management.commands.backfill_account_based_in._production_run_lock"
        ),
        patch(
            "monitor.management.commands.backfill_account_based_in.fetch_user_about_batch",
            side_effect=fetch_selected,
        ),
    ):
        call_command(
            "backfill_account_based_in",
            apply=True,
            target="production",
            require_complete=True,
            limit=2,
            max_attempts=2,
            max_credits=36,
            max_wall_seconds=60,
            max_qps=1,
            provider_qps=1,
            concurrency=1,
            chunk_size=2,
            recovery_receipt=_production_recovery_receipt(account_count=2),
            json_report=str(json_path),
            markdown_report=str(tmp_path / "quarantined.md"),
            stdout=StringIO(),
        )

    report = json.loads(json_path.read_text())
    assert Account.objects.get(
        author_id=quarantined_ids[0]
    ).account_based_in_fetched_at is None
    assert Account.objects.get(
        author_id=accepted_ids[0]
    ).account_based_in_fetched_at is not None
    assert report["outcome"]["quarantined_accounts"] == 1
    assert report["outcome"]["quarantined_reasons"] == {"schema_drift": 1}
    assert report["outcome"]["remaining_eligible"] == 1
    assert report["outcome"]["remaining_retryable"] == 0
    assert report["outcome"]["stop_reason"] is None


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
    monkeypatch.setenv(TWITTERAPI_IO_ON_DEMAND_API_KEY_ENV, "managed-secret")
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
    monkeypatch.setenv(TWITTERAPI_IO_ON_DEMAND_API_KEY_ENV, "managed-secret")
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
