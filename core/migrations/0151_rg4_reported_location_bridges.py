"""Name necessary source wording explicitly and protect canonical resolution.

Old columns stay synchronized only through the rolling-image cutover. The final
RG4 deletion migration removes them and these compatibility triggers.
"""

import hashlib
import json
from pathlib import Path

from django.db import migrations, models, transaction

from ._rg4_geography_mapping_v1 import INPUT_HASHES

# ruff: noqa: RUF012

from ._rg4_geography_write_performance_v1 import OWNERS, reported_triggers

BRIDGE = """
CREATE OR REPLACE FUNCTION pw_geo_based_in_reference() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (TG_OP='INSERT' AND NEW.reported_based_in IS NOT NULL)
     OR (TG_OP='UPDATE' AND NEW.reported_based_in IS DISTINCT FROM OLD.account_based_in) THEN
    UPDATE accounts SET based_in_location_id=pw_geo_source_id(NEW.reported_based_in,'based_in')
    WHERE account_key=NEW.account_key;
  END IF;
  RETURN NEW;
END $$;
"""


def install(apps, schema_editor):
    body = (Path(__file__).resolve().parents[2] / "data/geonames/resolution-inputs.json").read_bytes()
    if hashlib.sha256(body).hexdigest() != INPUT_HASHES["resolution-inputs.json"]:
        raise ValueError("Frozen RG4 geographic input changed")
    inputs = json.loads(body)
    schema_editor.execute("SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='30s'")
    inputs["freeform"].update({"korea":1835841,"congo":203312})
    inputs["based_in"].update({"korea":1835841,"congo":203312})
    # These are trusted versioned literals in function definitions, not new JSON
    # columns. All relationships returned by the boundary use our local PK.
    literal = "'" + json.dumps({key:inputs[key] for key in ("freeform","based_in")},ensure_ascii=False).replace("'","''") + "'"
    schema_editor.execute(f"""
        CREATE OR REPLACE FUNCTION pw_geo_source_id(source_value text,source_context text) RETURNS bigint
        LANGUAGE sql STABLE AS $body$
          SELECT id FROM geolocations WHERE geonames_id=({literal}::jsonb -> source_context ->>
            lower(btrim(normalize(COALESCE(source_value,''),NFKC))))::bigint
        $body$
    """)
    schema_editor.execute(BRIDGE)
    quote = schema_editor.quote_name
    for table, _pk, old, new, field, context in OWNERS:
        schema_editor.execute(f"ALTER TABLE {quote(table)} ADD COLUMN IF NOT EXISTS {quote(new)} text")
    reported_triggers(schema_editor)
    schema_editor.execute("DROP TRIGGER IF EXISTS pw_geo_based_in_reference ON x_account_details")
    schema_editor.execute("CREATE TRIGGER pw_geo_based_in_reference AFTER INSERT OR UPDATE ON x_account_details FOR EACH ROW EXECUTE FUNCTION pw_geo_based_in_reference()")


def copy_source(apps, schema_editor):
    quote = schema_editor.quote_name
    for table, pk, old, new, field, context in OWNERS:
        last_key = None
        while True:
            with transaction.atomic(using=schema_editor.connection.alias), schema_editor.connection.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='30s'")
                after = f"AND {quote(pk)} > %s" if last_key is not None else ""
                cursor.execute(f"""WITH selected AS (
                    SELECT {quote(pk)} FROM {quote(table)} WHERE {quote(new)} IS NULL AND {quote(old)} IS NOT NULL
                    {after} ORDER BY {quote(pk)} LIMIT 100 FOR UPDATE
                ), changed AS (UPDATE {quote(table)} owner SET {quote(new)}=owner.{quote(old)}
                FROM selected WHERE owner.{quote(pk)}=selected.{quote(pk)}
                RETURNING owner.{quote(pk)}) SELECT {quote(pk)} FROM changed ORDER BY {quote(pk)} DESC LIMIT 1""",
                [last_key] if last_key is not None else [])
                last = cursor.fetchone()
                if last is None:
                    break
                last_key = last[0]
        # The old image could have changed a source after 0150 mapped it but
        # before these bridges existed. Copying identical old/new wording is
        # deliberately not a source-change event, so reconcile that gap here.
        if not field:
            continue
        last_key = None
        while True:
            with transaction.atomic(using=schema_editor.connection.alias), schema_editor.connection.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='30s'")
                after = f"AND {quote(pk)} > %s" if last_key is not None else ""
                cursor.execute(f"""WITH selected AS (
                    SELECT {quote(pk)},pw_geo_source_id({quote(new)},%s) AS target
                    FROM {quote(table)} WHERE {quote(field)} IS DISTINCT FROM pw_geo_source_id({quote(new)},%s)
                    {after} ORDER BY {quote(pk)} LIMIT 100 FOR UPDATE
                ), changed AS (UPDATE {quote(table)} owner SET {quote(field)}=selected.target
                FROM selected WHERE owner.{quote(pk)}=selected.{quote(pk)}
                RETURNING owner.{quote(pk)}) SELECT {quote(pk)} FROM changed ORDER BY {quote(pk)} DESC LIMIT 1""",
                [context, context, *([last_key] if last_key is not None else [])])
                last = cursor.fetchone()
                if last is None:
                    break
                last_key = last[0]
        print(f"RG4 {table}: reported source copy and reconciliation complete", flush=True)


def uninstall(apps, schema_editor):
    schema_editor.execute("DROP TRIGGER pw_geo_based_in_reference ON x_account_details; DROP FUNCTION pw_geo_based_in_reference()")
    for table, _pk, _old, new, _field, _context in OWNERS:
        schema_editor.execute(f'DROP TRIGGER pw_geo_reported_bridge ON "{table}"; ALTER TABLE "{table}" DROP COLUMN "{new}"')
    schema_editor.execute("DROP FUNCTION pw_geo_reported_bridge(); DROP FUNCTION pw_geo_source_id(text,text)")


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("core", "0150_rg4_geolocation_mapping")]
    operations = [
        migrations.RunPython(install, reverse_code=uninstall, atomic=True),
        migrations.RunPython(copy_source, reverse_code=migrations.RunPython.noop, atomic=False),
        migrations.AlterField("accountlocationevidence", "reported_profile_location", models.TextField(null=True)),
        migrations.AlterField("accountbasedinevidence", "reported_based_in", models.TextField(null=True)),
        migrations.AlterField("postlocationevidence", "reported_author_location", models.TextField(null=True)),
        migrations.AlterField("profilelocationevidence", "reported_location", models.TextField(null=True)),
        migrations.AlterField("affiliationlocationevidence", "reported_location", models.TextField(null=True)),
    ]
