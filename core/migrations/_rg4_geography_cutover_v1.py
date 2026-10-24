"""Frozen rolling-release bridges and final legacy-writer reconciliation.

Run before the first canonical-only application image. Old images may finish
while the bridges are present; deletion requires a final drain and job sweep.
"""

import hashlib
import json
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from ._rg4_geography_mapping_v1 import INPUT_HASHES, capture, resolve


def inputs():
    body = (Path(__file__).resolve().parents[2] / "data/geonames/resolution-inputs.json").read_bytes()
    if hashlib.sha256(body).hexdigest() != INPUT_HASHES["resolution-inputs.json"]:
        raise ValueError("Frozen geographic input changed")
    return json.loads(body)


BRIDGES = """
CREATE OR REPLACE FUNCTION pw_geo_legacy_reference() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE old_value text; raw_value text; target bigint;
BEGIN
  old_value := to_jsonb(NEW)->>TG_ARGV[0];
  IF TG_OP='UPDATE' AND old_value IS NOT DISTINCT FROM (to_jsonb(OLD)->>TG_ARGV[0])
      AND (TG_TABLE_NAME<>'accounts' OR (to_jsonb(NEW)->>'based_in_region_key') IS NOT DISTINCT FROM (to_jsonb(OLD)->>'based_in_region_key')) THEN
    RETURN NEW;
  END IF;
  IF TG_OP='INSERT' AND old_value IS NULL AND
      (TG_TABLE_NAME<>'accounts' OR to_jsonb(NEW)->>'based_in_region_key' IS NULL) THEN
    RETURN NEW;
  END IF;
  IF TG_TABLE_NAME='accounts' THEN
    SELECT reported_based_in INTO raw_value FROM x_account_details WHERE account_key=NEW.account_key;
    IF NULLIF(btrim(raw_value),'') IS NOT NULL THEN
      target := pw_geo_source_id(raw_value,'based_in');
    ELSE
      target := COALESCE(pw_geo_legacy_id(old_value,'country'),
        pw_geo_legacy_id(NEW.based_in_region_key,'region'));
    END IF;
  ELSIF TG_TABLE_NAME='account_based_in_mappings' THEN
    target := pw_geo_source_id(NEW.value,'based_in');
  ELSE
    target := pw_geo_legacy_id(old_value,'country');
  END IF;
  NEW := jsonb_populate_record(NEW,jsonb_build_object(TG_ARGV[1],target));
  RETURN NEW;
END $$;
CREATE TRIGGER pw_geo_legacy_reference BEFORE INSERT OR UPDATE OF country_code,based_in_region_key ON accounts
FOR EACH ROW EXECUTE FUNCTION pw_geo_legacy_reference('country_code','based_in_location_id');
CREATE TRIGGER pw_geo_legacy_reference BEFORE INSERT OR UPDATE OF hq_country_id ON companies
FOR EACH ROW EXECUTE FUNCTION pw_geo_legacy_reference('hq_country_id','hq_geolocation_id');
CREATE TRIGGER pw_geo_legacy_reference BEFORE INSERT OR UPDATE OF country_code ON person_citizenships
FOR EACH ROW EXECUTE FUNCTION pw_geo_legacy_reference('country_code','geolocation_id');
CREATE TRIGGER pw_geo_legacy_reference BEFORE INSERT OR UPDATE OF country_code,region_key ON account_based_in_mappings
FOR EACH ROW EXECUTE FUNCTION pw_geo_legacy_reference('country_code','geolocation_id');
"""


IMMUTABLE_CITIZENSHIP = """
CREATE OR REPLACE FUNCTION pw_citizenship_geolocation_owner() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.person_id IS DISTINCT FROM OLD.person_id OR
     (OLD.geolocation_id IS NOT NULL AND NEW.geolocation_id IS DISTINCT FROM OLD.geolocation_id) THEN
    RAISE EXCEPTION 'Citizenship owner and place are immutable' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS pw_citizenship_geolocation_owner ON person_citizenships;
CREATE TRIGGER pw_citizenship_geolocation_owner BEFORE UPDATE OF person_id,geolocation_id ON person_citizenships
FOR EACH ROW EXECUTE FUNCTION pw_citizenship_geolocation_owner();
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
    WHERE conrelid='person_citizenships'::regclass AND conname='uq_person_citizenship_geolocation') THEN
    ALTER TABLE person_citizenships ADD CONSTRAINT uq_person_citizenship_geolocation
      UNIQUE (person_id,geolocation_id);
  END IF;
END $$;
"""


def install(apps, schema_editor):
    source = inputs()
    literal = "'" + json.dumps({"country": source["country_codes"], "region": source["legacy_region_geonames_ids"]}).replace("'", "''") + "'"
    schema_editor.execute("SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='30s'")
    schema_editor.execute(f"""CREATE OR REPLACE FUNCTION pw_geo_legacy_id(value text, context text) RETURNS bigint
        LANGUAGE sql STABLE AS $body$
        SELECT id FROM geolocations WHERE geonames_id=({literal}::jsonb->context->>value)::bigint
        $body$""")
    for table in ("accounts", "companies", "person_citizenships", "account_based_in_mappings"):
        schema_editor.execute(f'DROP TRIGGER IF EXISTS pw_geo_legacy_reference ON "{table}"')
    schema_editor.execute(BRIDGES)
    schema_editor.execute("ALTER TABLE person_citizenships ALTER COLUMN country_code DROP NOT NULL")
    schema_editor.execute("ALTER TABLE account_based_in_mappings DROP CONSTRAINT IF EXISTS ck_account_based_in_mapping_one_target")


def reconcile_owners(apps, schema_editor):
    """Refresh derivations made before the bridge was installed, before serving cutover."""
    conn = schema_editor.connection
    expressions = (
        ("companies", "nickname", "hq_geolocation_id", "pw_geo_legacy_id(owner.hq_country_id,'country')", "owner.hq_country_id IS NOT NULL"),
        ("person_citizenships", "id", "geolocation_id", "pw_geo_legacy_id(owner.country_code,'country')", "owner.country_code IS NOT NULL"),
        ("account_based_in_mappings", "value", "geolocation_id", "pw_geo_source_id(owner.value,'based_in')", "true"),
        ("accounts", "account_key", "based_in_location_id", """CASE
          WHEN EXISTS(SELECT 1 FROM x_account_details x WHERE x.account_key=owner.account_key AND NULLIF(btrim(x.reported_based_in),'') IS NOT NULL)
          THEN pw_geo_source_id((SELECT reported_based_in FROM x_account_details x WHERE x.account_key=owner.account_key),'based_in')
          ELSE COALESCE(pw_geo_legacy_id(owner.country_code,'country'),pw_geo_legacy_id(owner.based_in_region_key,'region')) END""",
          "owner.country_code IS NOT NULL OR owner.based_in_region_key IS NOT NULL OR EXISTS(SELECT 1 FROM x_account_details x WHERE x.account_key=owner.account_key AND x.reported_based_in IS NOT NULL)"),
    )
    for table, pk, field, expression, predicate in expressions:
        while True:
            with transaction.atomic(using=conn.alias), conn.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='30s'")
                cursor.execute(f"""WITH selected AS (
                    SELECT owner.{pk}, {expression} AS target FROM {table} owner
                    WHERE ({predicate}) AND owner.{field} IS DISTINCT FROM ({expression})
                    ORDER BY owner.{pk} LIMIT 1000 FOR UPDATE
                ) UPDATE {table} owner SET {field}=selected.target FROM selected WHERE owner.{pk}=selected.{pk}""")
                if cursor.rowcount == 0:
                    break
    # Preserve unsupported typed claims before their reference columns disappear.
    # Existing source archives own this historical evidence; no new storage owner.
    with conn.cursor() as cursor:
        for table, columns, missing in (
            ("companies", "nickname,hq_country_id", "hq_country_id IS NOT NULL AND hq_geolocation_id IS NULL"),
            ("person_citizenships", "id,country_code", "country_code IS NOT NULL AND geolocation_id IS NULL"),
            ("accounts", "account_key,country_code,based_in_region_key", "based_in_location_id IS NULL AND (country_code IS NOT NULL OR based_in_region_key IS NOT NULL)"),
        ):
            cursor.execute(f"SELECT {columns} FROM {table} WHERE {missing} ORDER BY 1")
            names = [column.name for column in cursor.description]
            while rows := cursor.fetchmany(1000):
                capture(apps, {"table": table, "unresolved_legacy_references": [dict(zip(names, [str(value) if value is not None else None for value in row])) for row in rows]})


def reconcile_jobs(apps, schema_editor):
    """Map the last old-image writes, retaining exact input and unknown source time."""
    conn = schema_editor.connection
    source = inputs()
    ids = dict(apps.get_model("core", "Geolocation").objects.values_list("geonames_id", "pk"))
    while True:
        with transaction.atomic(using=conn.alias), conn.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='30s'")
            cursor.execute("SELECT id,locations,locations_raw FROM job_listings WHERE geolocation_source_archive_id IS NULL ORDER BY id LIMIT 100 FOR UPDATE")
            rows = cursor.fetchall()
            if not rows:
                return
            for listing, locations, wording in rows:
                locations = json.loads(locations) if isinstance(locations, str) else locations
                if not isinstance(locations, list):
                    raise TypeError("Legacy job locations must be an array")
                archive = capture(apps, {"locations": locations, "reported_value": wording})
                now = timezone.now()
                cursor.execute("UPDATE job_listing_locations SET superseded_at=%s WHERE listing_id=%s AND superseded_at IS NULL", [now, listing])
                cursor.execute("UPDATE job_listings SET geolocation_source_archive_id=%s WHERE id=%s", [archive.pk, listing])
                for ordinal, value in enumerate(locations or ([wording] if wording and wording.strip() else [])):
                    cursor.execute("""INSERT INTO job_listing_locations
                      (listing_id,source_archive_id,ordinal,recorded_at,geolocation_id,reported_value)
                      VALUES (%s,%s,%s,%s,%s,%s)""",
                      [listing,archive.pk,ordinal,now,resolve(source,ids,value),value if isinstance(value,str) else None])
