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

OWNERS = (
    ("accounts", "account_key", "location", "reported_profile_location", "profile_location_id", "freeform"),
    ("x_account_details", "account_key", "account_based_in", "reported_based_in", "", "based_in"),
    ("posts", "tweet_id", "author_location", "reported_author_location", "author_geolocation_id", "freeform"),
    ("account_profile_snapshots", "id", "location", "reported_location", "geolocation_id", "freeform"),
    ("people_brand_affiliations", "id", "location", "reported_location", "geolocation_id", "freeform"),
)

BRIDGE = """
CREATE FUNCTION pw_geo_reported_bridge() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE before_value text; before_new text; old_value text; new_value text;
        chosen text; resolved bigint; source_changed boolean;
BEGIN
  old_value := to_jsonb(NEW)->>TG_ARGV[0];
  new_value := to_jsonb(NEW)->>TG_ARGV[1];
  IF TG_OP='INSERT' THEN
    IF old_value IS NOT NULL AND new_value IS NOT NULL AND old_value IS DISTINCT FROM new_value THEN
      RAISE EXCEPTION 'conflicting location source representations' USING ERRCODE='23514';
    END IF;
    chosen := COALESCE(new_value,old_value);
    source_changed := chosen IS NOT NULL;
  ELSE
    before_value := to_jsonb(OLD)->>TG_ARGV[0];
    before_new := to_jsonb(OLD)->>TG_ARGV[1];
    IF old_value IS DISTINCT FROM before_value AND new_value IS DISTINCT FROM before_new
       AND old_value IS DISTINCT FROM new_value THEN
      RAISE EXCEPTION 'conflicting location source representations' USING ERRCODE='23514';
    END IF;
    IF new_value IS DISTINCT FROM before_new THEN chosen:=new_value;
    ELSIF old_value IS DISTINCT FROM before_value THEN chosen:=old_value;
    ELSE chosen:=COALESCE(new_value,old_value); END IF;
    source_changed := chosen IS DISTINCT FROM before_value;
  END IF;
  NEW := jsonb_populate_record(NEW,jsonb_build_object(TG_ARGV[0],chosen,TG_ARGV[1],chosen));
  IF source_changed AND TG_ARGV[2]<>'' THEN
    resolved := pw_geo_source_id(chosen,TG_ARGV[3]);
    NEW := jsonb_populate_record(NEW,jsonb_build_object(TG_ARGV[2],resolved));
  END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION pw_geo_based_in_reference() RETURNS trigger LANGUAGE plpgsql AS $$
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
        CREATE FUNCTION pw_geo_source_id(source_value text,source_context text) RETURNS bigint
        LANGUAGE sql STABLE AS $body$
          SELECT id FROM geolocations WHERE geonames_id=({literal}::jsonb -> source_context ->>
            lower(btrim(normalize(COALESCE(source_value,''),NFKC))))::bigint
        $body$
    """)
    schema_editor.execute(BRIDGE)
    quote = schema_editor.quote_name
    for table, _pk, old, new, field, context in OWNERS:
        schema_editor.execute(f"ALTER TABLE {quote(table)} ADD COLUMN {quote(new)} text")
        args = ",".join("'" + part + "'" for part in (old, new, field, context))
        schema_editor.execute(f"CREATE TRIGGER pw_geo_reported_bridge BEFORE INSERT OR UPDATE ON {quote(table)} FOR EACH ROW EXECUTE FUNCTION pw_geo_reported_bridge({args})")
    schema_editor.execute("CREATE TRIGGER pw_geo_based_in_reference AFTER INSERT OR UPDATE ON x_account_details FOR EACH ROW EXECUTE FUNCTION pw_geo_based_in_reference()")


def copy_source(apps, schema_editor):
    quote = schema_editor.quote_name
    for table, pk, old, new, _field, _context in OWNERS:
        while True:
            with transaction.atomic(using=schema_editor.connection.alias), schema_editor.connection.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='30s'")
                cursor.execute(f"""WITH selected AS (
                    SELECT {quote(pk)} FROM {quote(table)} WHERE {quote(new)} IS NULL AND {quote(old)} IS NOT NULL
                    ORDER BY {quote(pk)} LIMIT 1000 FOR UPDATE
                ) UPDATE {quote(table)} owner SET {quote(new)}=owner.{quote(old)}
                FROM selected WHERE owner.{quote(pk)}=selected.{quote(pk)}""")
                if cursor.rowcount == 0:
                    break


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
