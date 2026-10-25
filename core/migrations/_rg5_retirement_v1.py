"""Frozen RG5 physical retirement, run only after all old images have drained."""

import importlib

from django.db import transaction

from ._rg5_reference_mapping_v1 import bridge_name


def domains():
    products = importlib.import_module("core.migrations.0163_rg5_product_references")
    accounts = importlib.import_module(
        "core.migrations.0164_rg5_account_classification_references"
    )
    zones = importlib.import_module(
        "core.migrations.0162_rg5_measurement_timezone_references"
    )
    result = [dict(domain) for domain in products.DOMAINS]
    result += [
        {"table": table, "old": old, "new": old + "_id", "catalogue": catalogue}
        for table, old, catalogue, _ in accounts.DOMAINS
    ]
    result += [
        {
            "table": table,
            "old": "identifier_scope",
            "new": "identifier_scope_id",
            "catalogue": "source_identifier_namespaces",
        }
        for table in ("source_subject_mappings", "collection_job_targets")
    ]
    for item in result:
        item["bridge"] = bridge_name(item["table"], item["old"])
    result += [
        {
            "table": table,
            "old": old,
            "new": new,
            "catalogue": "time_zones",
            "bridge": f"pw_rg5_{old}_bridge",
        }
        for table, old, new in zones.DOMAINS
    ]
    assert len(result) == 24
    return result


def prepare_retirement(apps, schema_editor):
    """Read parity before the short exclusive-lock transaction; bridges stay on."""
    with (
        transaction.atomic(using=schema_editor.connection.alias),
        schema_editor.connection.cursor() as cursor,
    ):
        cursor.execute("SET LOCAL statement_timeout='60s'; SET LOCAL lock_timeout='2s'")
        for item in domains():
            table, old, new, catalogue = (
                item[key] for key in ("table", "old", "new", "catalogue")
            )
            expected = f"o.{old}"
            if catalogue == "time_zones":
                expected = f"NULLIF(o.{old},'unknown')"
                actual = f"o.{new}"
                join = ""
            else:
                actual = "c.code"
                join = f"LEFT JOIN {catalogue} c ON c.id=o.{new}"
                if item.get("gating"):
                    expected = f"CASE o.{old} WHEN 'False' THEN 'public' WHEN 'True' THEN 'gated' ELSE o.{old} END"
                elif catalogue in {
                    "software_libraries",
                    "model_tasks",
                    "provider_label_types",
                    "provider_label_display_types",
                    "provider_link_types",
                }:
                    expected = f"NULLIF(o.{old},'')"
            cursor.execute(
                f"SELECT EXISTS(SELECT 1 FROM {table} o {join} "
                f"WHERE {actual} IS DISTINCT FROM ({expected}))"
            )
            if cursor.fetchone()[0]:
                raise RuntimeError(f"Cannot retire mismatched reference: {table}.{old}")


def remove_storage(apps, schema_editor):
    """Drop exactly the superseded columns and their temporary bridge functions."""
    selected = domains()
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout='2s'; SET LOCAL statement_timeout='30s'")
        tables = sorted({item["table"] for item in selected})
        cursor.execute("LOCK TABLE " + ",".join(tables) + " IN ACCESS EXCLUSIVE MODE")
        for item in selected:
            table, old, new, bridge = (
                item[key] for key in ("table", "old", "new", "bridge")
            )
            cursor.execute(
                "SELECT t.tgenabled='O' AND EXISTS(SELECT 1 FROM pg_constraint c "
                "JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attname=%s "
                "WHERE c.conrelid=t.tgrelid AND c.contype='f' AND c.convalidated "
                "AND c.conkey=ARRAY[a.attnum]) FROM pg_trigger t "
                "WHERE t.tgrelid=%s::regclass AND t.tgname=%s",
                [new, table, bridge],
            )
            if cursor.fetchone() != (True,):
                raise RuntimeError(f"Unready reference retirement: {table}.{old}")
        source_tables = {
            "products",
            "collection_resource_snapshots",
            "account_profile_snapshots",
            "posts",
            "x_account_details",
            "source_subject_mappings",
            "collection_job_targets",
        }
        for table in sorted(source_tables):
            cursor.execute(
                "SELECT tgenabled='O' FROM pg_trigger WHERE tgrelid=%s::regclass AND tgname=%s",
                [table, "pw_rg5_source_" + table],
            )
            if cursor.fetchone() != (True,):
                raise RuntimeError(f"Missing permanent source guard: {table}")
        for item in selected:
            cursor.execute(f"DROP TRIGGER {item['bridge']} ON {item['table']}")
            cursor.execute(f"DROP FUNCTION {item['bridge']}()")
        for table in tables:
            drops = [
                f"DROP COLUMN {item['old']}"
                for item in selected
                if item["table"] == table
            ]
            # No CASCADE: an unreviewed dependent view must stop retirement.
            cursor.execute(f"ALTER TABLE {table} " + ",".join(drops))
