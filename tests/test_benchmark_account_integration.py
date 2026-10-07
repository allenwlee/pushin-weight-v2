"""Populated account cutover covers both independent migration orders."""

import importlib
import json
import uuid

import pytest
from django.db import connection

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


@pytest.mark.parametrize("original_type", ["text", "uuid"])
def test_company_links_preserve_identity_evidence_and_native_writers(original_type):
    migration = importlib.import_module(
        "core.migrations.0074_official_company_generic_accounts"
    )
    schema = "benchmark_company_link_fixture"
    account_key = uuid.uuid4()
    original = "native-991" if original_type == "text" else str(account_key)
    with connection.cursor() as cursor:
        cursor.execute(f"CREATE SCHEMA {schema}")
        cursor.execute(f"SET LOCAL search_path TO {schema}, public")
        try:
            cursor.execute(
                "CREATE TABLE accounts (account_key uuid PRIMARY KEY, author_id text UNIQUE, data_source_id text)"
            )
            cursor.execute(
                "INSERT INTO accounts VALUES (%s,'native-991','x')", [account_key]
            )
            cursor.execute(
                "CREATE TABLE official_company_scans (key text PRIMARY KEY, cursor text)"
            )
            cursor.execute(
                "INSERT INTO official_company_scans VALUES ('account-observations',%s)",
                [json.dumps({"at": "2026-10-07T12:00:00+00:00", "pk": "native-991"})],
            )
            cursor.execute(
                f"CREATE TABLE official_company_account_states (id bigint PRIMARY KEY, "
                f"account_id {original_type} NOT NULL UNIQUE, evidence jsonb NOT NULL)"
            )
            cursor.execute(
                f"CREATE TABLE official_company_list_intents (id bigint PRIMARY KEY, "
                f"account_id {original_type} NOT NULL, list_id bigint NOT NULL, status text, "
                "CONSTRAINT uq_official_co_list_intent UNIQUE(list_id,account_id))"
            )
            cursor.execute(
                "INSERT INTO official_company_account_states VALUES (17,%s,'{\"keep\":true}')",
                [original],
            )
            cursor.execute(
                "INSERT INTO official_company_list_intents VALUES (23,%s,42,'confirmed')",
                [original],
            )
            with connection.schema_editor(atomic=False) as editor:
                migration.forward(None, editor)
            cursor.execute(
                "SELECT id,account_id,account_key,evidence FROM official_company_account_states"
            )
            row = cursor.fetchone()
            assert row[:3] == (17, "native-991", account_key)
            assert json.loads(row[3]) == {"keep": True}
            cursor.execute(
                "SELECT id,account_id,account_key,status FROM official_company_list_intents"
            )
            assert cursor.fetchone() == (23, "native-991", account_key, "confirmed")
            cursor.execute(
                "INSERT INTO official_company_list_intents (id,account_id,list_id,status) VALUES (24,'native-991',43,'pending')"
            )
            cursor.execute(
                "SELECT account_key FROM official_company_list_intents WHERE id=24"
            )
            assert cursor.fetchone()[0] == account_key
            cursor.execute(
                "INSERT INTO official_company_list_intents (id,account_key,list_id,status) VALUES (25,%s,44,'pending')",
                [account_key],
            )
            cursor.execute(
                "SELECT account_id FROM official_company_list_intents WHERE id=25"
            )
            assert cursor.fetchone()[0] == "native-991"
            cursor.execute("SELECT cursor FROM official_company_scans")
            checkpoint = json.loads(cursor.fetchone()[0])
            assert checkpoint["pk"] == str(account_key)
            assert checkpoint["legacy_native_pk"] == "native-991"
        finally:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            cursor.execute("SET LOCAL search_path TO public")
            cursor.execute(f"DROP SCHEMA {schema} CASCADE")
