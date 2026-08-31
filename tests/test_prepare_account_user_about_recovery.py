from __future__ import annotations

import json
from contextlib import nullcontext
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext

from core.models import Account
from monitor.management.commands.backfill_account_based_in import (
    _parse_recovery_receipt,
)

pytestmark = [
    pytest.mark.requires_postgres,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]


def test_recovery_snapshot_defaults_to_zero_write_dry_run():
    Account.objects.create(author_id="1", handle="one")
    stdout = StringIO()

    with patch(
        "monitor.management.commands.prepare_account_user_about_recovery._production_run_lock",
        side_effect=AssertionError("dry run acquired the production lock"),
    ):
        call_command("prepare_account_user_about_recovery", stdout=stdout)

    report = json.loads(stdout.getvalue())
    assert report == {
        "account_count": 1,
        "mode": "dry_run",
        "target": "production",
        "writes": 0,
    }


def test_recovery_snapshot_copies_and_restore_proves_real_account_rows():
    Account.objects.create(author_id="1", handle="one", country_code="US")
    Account.objects.create(author_id="2", handle="two", country_code="CN")
    stdout = StringIO()
    relation = None

    try:
        with (
            patch(
                "monitor.management.commands.prepare_account_user_about_recovery._is_authorized_executor",
                return_value=True,
            ),
            patch(
                "monitor.management.commands.prepare_account_user_about_recovery._required_migrations_applied",
                return_value=True,
            ),
            patch(
                "monitor.management.commands.prepare_account_user_about_recovery._production_run_lock",
                side_effect=nullcontext,
            ),
            CaptureQueriesContext(connection) as queries,
        ):
            call_command(
                "prepare_account_user_about_recovery",
                apply=True,
                confirm_database="pushinweight_shadow",
                stdout=stdout,
            )

        command_sql = [query["sql"] for query in queries.captured_queries]
        isolation_index = next(
            index
            for index, statement in enumerate(command_sql)
            if "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ" in statement
        )
        count_index = next(
            index
            for index, statement in enumerate(command_sql)
            if 'SELECT statement_timestamp(), count(*) FROM "accounts"' in statement
        )
        assert isolation_index < count_index

        report = json.loads(stdout.getvalue())
        relation = report["snapshot_relation"]
        receipt = _parse_recovery_receipt(report["recovery_receipt"])
        assert report["mode"] == "production_snapshot_apply"
        assert report["account_count"] == 2
        assert report["restore_proved"] is True
        assert receipt.snapshot_account_count == 2
        assert receipt.row_digest == report["row_digest"]
        assert receipt.receipt_sha256 == report["receipt_sha256"]

        schema_name, table_name = relation.split(".", 1)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = %s AND table_name = %s",
                [schema_name, table_name],
            )
            assert cursor.fetchone()[0] == 1
    finally:
        if relation:
            schema_name, table_name = relation.split(".", 1)
            with connection.cursor() as cursor:
                cursor.execute(f'DROP TABLE IF EXISTS "{schema_name}"."{table_name}"')
