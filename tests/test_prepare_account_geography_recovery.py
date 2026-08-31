from __future__ import annotations

import json
from contextlib import nullcontext
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test.utils import CaptureQueriesContext

from core.models import Account
from monitor.account_geography_recovery import (
    parse_geography_recovery_receipt,
    verify_geography_recovery_snapshot,
)

pytestmark = [
    pytest.mark.requires_postgres,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]


def test_geography_snapshot_defaults_to_zero_write_dry_run():
    Account.objects.create(author_id="1", handle="one")
    stdout = StringIO()

    with patch(
        "monitor.management.commands.prepare_account_geography_recovery._geography_run_lock",
        side_effect=AssertionError("dry run acquired the geography lock"),
    ):
        call_command("prepare_account_geography_recovery", stdout=stdout)

    assert json.loads(stdout.getvalue()) == {
        "account_count": 1,
        "columns": [
            "author_id",
            "account_based_in",
            "country_code",
            "based_in_region_key",
            "account_based_in_fetched_at",
            "first_seen_at",
        ],
        "mode": "dry_run",
        "target": "production",
        "writes": 0,
    }


def test_geography_snapshot_is_narrow_and_restore_proved():
    Account.objects.create(
        author_id="1",
        handle="one",
        account_based_in="United States",
        country_code="US",
    )
    Account.objects.create(author_id="2", handle="two")
    stdout = StringIO()
    relation = None

    try:
        with (
            patch(
                "monitor.management.commands.prepare_account_geography_recovery._is_authorized_executor",
                return_value=True,
            ),
            patch(
                "monitor.management.commands.prepare_account_geography_recovery._required_migrations_applied",
                return_value=True,
            ),
            patch(
                "monitor.management.commands.prepare_account_geography_recovery._geography_run_lock",
                side_effect=nullcontext,
            ),
            CaptureQueriesContext(connection) as queries,
        ):
            call_command(
                "prepare_account_geography_recovery",
                apply=True,
                confirm_database="pushinweight_shadow",
                stdout=stdout,
            )

        report = json.loads(stdout.getvalue())
        relation = report["snapshot_relation"]
        receipt = parse_geography_recovery_receipt(report["recovery_receipt"])
        assert report["mode"] == "production_geography_snapshot_apply"
        assert report["account_count"] == 2
        assert report["restore_proved"] is True
        assert receipt.snapshot_account_count == 2
        assert receipt.row_digest == report["row_digest"]

        create_sql = next(
            query["sql"]
            for query in queries.captured_queries
            if "CREATE TABLE" in query["sql"]
            and "account_geography_backup" in query["sql"]
        )
        assert "SELECT *" not in create_sql
        for column in receipt.columns:
            assert column in create_sql

        Account.objects.filter(pk="1").update(account_based_in="Europe")
        with pytest.raises(CommandError, match="does not match recovery snapshot"):
            verify_geography_recovery_snapshot(receipt)
    finally:
        if relation:
            schema_name, table_name = relation.split(".", 1)
            with connection.cursor() as cursor:
                cursor.execute(f'DROP TABLE IF EXISTS "{schema_name}"."{table_name}"')
