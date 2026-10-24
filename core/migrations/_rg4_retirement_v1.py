"""Frozen RG4 preservation checks and final, replacement-only database guards."""

import hashlib
import json
import re
from importlib import import_module

from django.db import transaction

from ._rg4_geography_cutover_v1 import reconcile_jobs
from ._rg4_geography_write_performance_v1 import (
    OWNERS,
    source_bridge_sql,
    trigger_matches,
)

DROP_COLUMNS = {
    "account_based_in_mappings": ("country_code", "region_key"),
    "account_profile_snapshots": ("location",),
    "accounts": ("based_in_region_key", "country_code", "location"),
    "companies": ("hq_country_id",),
    "event_dossier_claims": ("claim_kind", "event_timezone"),
    "event_dossiers": ("event_kind",),
    "job_listings": ("locations", "locations_raw"),
    "model_release_details": ("availability_state", "disclosure_state_id", "release_channel"),
    "model_releases": ("release_channel",),
    "opportunities": ("opportunity_type",),
    "people": ("nationality",),
    "people_brand_affiliations": ("affiliation_type", "location"),
    "people_names": ("name_type_id",),
    "person_citizenships": ("country_code",),
    "personnel_change_details": ("change_kind",),
    "posts": ("author_location",),
    "x_account_details": ("account_based_in",),
}
DROP_TABLES = (
    "country_codes_region", "country_labels", "region_labels", "countries", "regions",
    "person_name_types", "release_disclosure_states",
)
SCALAR_PAIRS = (
    ("people_names", "name_type", "name_type_id", "person_name_types"),
    ("people_brand_affiliations", "affiliation_type", "affiliation_type_id", "affiliation_types"),
    ("opportunities", "opportunity_type", "opportunity_type_id", "opportunity_types"),
    ("event_dossiers", "event_kind", "event_kind_id", "event_kinds"),
    ("event_dossier_claims", "claim_kind", "claim_kind_id", "event_claim_kinds"),
    ("model_releases", "release_channel", "release_maturity_id", "release_maturities"),
    ("model_release_details", "release_channel", "release_maturity_id", "release_maturities"),
    ("model_release_details", "availability_state", "availability_state_id", "release_availability_states"),
    ("model_release_details", "disclosure_state", "disclosure_state_id", "release_disclosure_states"),
    ("personnel_change_details", "change_kind", "change_kind_id", "personnel_change_types"),
)
BRIDGES = (
    ("people_names", "pw_rg4_name_kind_bridge"),
    ("people_names", "pw_rg4_name_kind_identity"),
    ("people_brand_affiliations", "pw_rg4_affiliation_type_bridge"),
    ("opportunities", "pw_rg4_opportunity_type_bridge"),
    ("event_dossiers", "pw_rg4_dossier_kind_bridge"),
    ("event_dossier_claims", "pw_rg4_claim_kind_bridge"),
    ("event_dossier_claims", "pw_rg4_claim_timezone_bridge"),
    ("model_releases", "pw_rg4_release_channel_bridge"),
    ("model_release_details", "pw_rg4_detail_release_channel_bridge"),
    ("model_release_details", "pw_rg4_detail_availability_state_bridge"),
    ("model_release_details", "pw_rg4_detail_disclosure_state_bridge"),
    ("personnel_change_details", "pw_rg4_personnel_kind_bridge"),
    ("people", "pw_rg4_nationality_evidence_bridge"),
    ("job_listings", "pw_job_location_legacy_invalidation"),
    *((table, "pw_geo_reported_bridge") for table, *_ in OWNERS),
    *((table, "pw_geo_legacy_reference") for table in (
        "accounts", "companies", "person_citizenships", "account_based_in_mappings",
    )),
)


def check_source_bridges(connection):
    """Preservation reads may precede DDL only while the exact bridges stay active."""
    for table, _pk, old, new, field, context in OWNERS:
        if not trigger_matches(connection, table, "pw_geo_reported_bridge", "pw_geo_reported_bridge",
                23, columns=(old, new), arguments=(old, new, field, context)):
            raise RuntimeError(f"RG4 deletion requires the enabled source bridge on {table}")
    with connection.cursor() as cursor:
        cursor.execute("SELECT prosrc FROM pg_proc WHERE oid='pw_geo_reported_bridge()'::regprocedure")
        if cursor.fetchone()[0].strip() != source_bridge_sql().split("$$", 2)[1].strip():
            raise RuntimeError("RG4 source bridge function differs from its verified definition")


def check_legacy_catalogue(cursor):
    """Require the exact saved translation/policy snapshot, not just a row count."""
    def records(query):
        cursor.execute(query)
        names = [column.name for column in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]

    countries = records("SELECT * FROM countries ORDER BY code")
    regions = records("SELECT * FROM regions ORDER BY key")
    labels = []
    for table, column, owner in (
        ("country_labels", "country_code", "country_id"),
        ("region_labels", "region_key", "region_id"),
    ):
        labels.extend({"owner": owner, **row} for row in records(
            f"SELECT {column} AS {owner},locale_id AS locale_reference_id,label FROM {table} ORDER BY {column},locale_id"
        ))
    if not countries and not regions and not labels:
        return  # An empty test/installation catalogue has no source wording.
    original = {
        "meaning": "Existing country display policy and translated wording; old membership is retired, not recreated.",
        "countries": countries, "regions": regions, "labels": labels,
    }
    body = json.dumps(original, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    cursor.execute("SELECT body,byte_count FROM collection_evidence_archives WHERE content_sha256=%s",
                   [hashlib.sha256(body).hexdigest()])
    saved = cursor.fetchone()
    if saved is None or bytes(saved[0]) != body or saved[1] != len(body):
        raise RuntimeError("RG4 legacy geography wording/policy snapshot needs reconciliation")


def check_job_archives(cursor):
    cursor.execute("""SELECT j.id,j.locations,j.locations_raw,a.content_sha256,a.byte_count,a.body
        FROM job_listings j LEFT JOIN collection_evidence_archives a ON a.id=j.geolocation_source_archive_id
        ORDER BY j.id""")
    # Only the small job source records are materialized; never whole Post rows.
    for listing, locations, wording, digest, size, saved in cursor.fetchall():
        locations = json.loads(locations) if isinstance(locations, str) else locations
        if saved is None:
            raise RuntimeError(f"RG4 job {listing} lacks its selected source archive")
        body = bytes(saved)
        if len(body) != size or hashlib.sha256(body).hexdigest() != digest:
            raise RuntimeError(f"RG4 job {listing} source archive is corrupt")
        original = {"locations": locations, "reported_value": wording}
        if json.loads(body) == original or (locations == [] and wording is None):
            continue
        original_body = json.dumps(original, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        cursor.execute("""SELECT a.body,a.byte_count FROM job_listing_locations o
            JOIN collection_evidence_archives a ON a.id=o.source_archive_id
            WHERE o.listing_id=%s AND a.content_sha256=%s LIMIT 1""",
            [listing, hashlib.sha256(original_body).hexdigest()])
        prior = cursor.fetchone()
        if prior is None or bytes(prior[0]) != original_body or prior[1] != len(original_body):
            raise RuntimeError(f"RG4 job {listing} original location evidence is missing")
    cursor.execute("""SELECT count(*) FROM job_listing_locations o JOIN job_listings j ON j.id=o.listing_id
        WHERE o.superseded_at IS NULL AND o.source_archive_id IS DISTINCT FROM j.geolocation_source_archive_id""")
    if cursor.fetchone()[0]:
        raise RuntimeError("RG4 current job locations disagree with their source selection")


def prepare_retirement(apps, schema_editor):
    """Commit the final old-job source capture, then read without exclusive locks."""
    reconcile_jobs(apps, schema_editor)
    connection = schema_editor.connection
    with transaction.atomic(using=connection.alias), connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='90s'")
        check_source_bridges(connection)
        for table, _pk, old, new, _field, _context in OWNERS:
            cursor.execute(f'SELECT count(*) FROM "{table}" WHERE "{old}" IS DISTINCT FROM "{new}"')
            if cursor.fetchone()[0]:
                raise RuntimeError(f"RG4 unpreserved source wording in {table}")
        for table, scalar, reference, catalogue in SCALAR_PAIRS:
            cursor.execute(f"""SELECT count(*) FROM {table} owner LEFT JOIN {catalogue} target
                ON target.id=owner.{reference} WHERE target.code IS DISTINCT FROM owner.{scalar}""")
            if cursor.fetchone()[0]:
                raise RuntimeError(f"RG4 conflicting catalogue representations in {table}.{scalar}")
        cursor.execute("SELECT count(*) FROM event_dossier_claims WHERE event_timezone IS DISTINCT FROM event_timezone_id")
        if cursor.fetchone()[0]:
            raise RuntimeError("RG4 conflicting dossier claim timezones")
        cursor.execute("""SELECT count(*) FROM people p WHERE p.nationality IS NOT NULL AND p.nationality<>''
            AND NOT EXISTS (SELECT 1 FROM people_texts t WHERE t.person_id=p.id AND t.affiliation_id IS NULL
              AND t.kind='reported_nationality' AND t.source_reference='legacy:people.nationality'
              AND t.text=p.nationality)""")
        if cursor.fetchone()[0]:
            raise RuntimeError("RG4 unpreserved nationality wording")
        check_legacy_catalogue(cursor)
        check_job_archives(cursor)


def final_source_guards_sql():
    cases = []
    triggers = []
    for table, _pk, _old, source, reference, context in OWNERS:
        if not reference:
            continue  # Based-in updates its account through the separate AFTER guard.
        cases.append(f"""WHEN '{table}' THEN
          IF (TG_OP='INSERT' AND NEW.{source} IS NOT NULL)
             OR (TG_OP='UPDATE' AND NEW.{source} IS DISTINCT FROM OLD.{source}) THEN
            NEW.{reference}:=pw_geo_source_id(NEW.{source},'{context}');
          END IF;""")
        triggers.append(f"""CREATE TRIGGER pw_geo_reported_source BEFORE INSERT OR UPDATE OF {source}
            ON {table} FOR EACH ROW EXECUTE FUNCTION pw_geo_reported_source();""")
    return """
CREATE FUNCTION pw_geo_reported_source() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  CASE TG_TABLE_NAME """ + "\n".join(cases) + """
    ELSE RAISE EXCEPTION 'unsupported geography source owner';
  END CASE;
  RETURN NEW;
END $$;
""" + "\n".join(triggers) + """
CREATE OR REPLACE FUNCTION pw_geo_based_in_reference() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (TG_OP='INSERT' AND NEW.reported_based_in IS NOT NULL)
     OR (TG_OP='UPDATE' AND NEW.reported_based_in IS DISTINCT FROM OLD.reported_based_in) THEN
    UPDATE accounts SET based_in_location_id=pw_geo_source_id(NEW.reported_based_in,'based_in')
    WHERE account_key=NEW.account_key;
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER pw_geo_based_in_reference ON x_account_details;
CREATE TRIGGER pw_geo_based_in_reference AFTER INSERT OR UPDATE OF reported_based_in ON x_account_details
FOR EACH ROW EXECUTE FUNCTION pw_geo_based_in_reference();
"""


CITIZENSHIP_LINK = """
CREATE OR REPLACE FUNCTION pw_rg4_citizenship_link_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE owner_id uuid; evidence_person_id uuid;
BEGIN
  IF TG_TABLE_NAME='people_texts' THEN
    IF NEW.person_id IS DISTINCT FROM OLD.person_id
       AND EXISTS (SELECT 1 FROM person_citizenship_evidence WHERE person_text_id=OLD.id) THEN
      RAISE EXCEPTION 'Cited person text owner is immutable' USING ERRCODE='23514';
    END IF;
  ELSE
    IF TG_OP='UPDATE' AND (NEW.citizenship_id IS DISTINCT FROM OLD.citizenship_id
        OR NEW.person_text_id IS DISTINCT FROM OLD.person_text_id) THEN
      RAISE EXCEPTION 'Citizenship evidence link is immutable' USING ERRCODE='23514';
    END IF;
    SELECT person_id INTO owner_id FROM person_citizenships WHERE id=NEW.citizenship_id;
    SELECT person_id INTO evidence_person_id FROM people_texts WHERE id=NEW.person_text_id;
    IF owner_id IS NULL OR evidence_person_id IS NULL OR owner_id IS DISTINCT FROM evidence_person_id THEN
      RAISE EXCEPTION 'Citizenship evidence must belong to the same person' USING ERRCODE='23514';
    END IF;
  END IF;
  RETURN NEW;
END $$;
"""


def dossier_functions_sql():
    """Keep the frozen review/history rules; replace only the retired identity read."""
    original = import_module("core.migrations.0097_event_dossier_integrity").FORWARD
    result = []
    for name in ("ed_validate_review_v1", "ed_identity_v1"):
        match = re.search(r"CREATE FUNCTION " + name + r"\(.*?END \$\$;", original, re.DOTALL)
        if match is None:
            raise RuntimeError("Missing frozen dossier function")
        statement = match.group(0).replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
        if name == "ed_validate_review_v1":
            old = "SELECT event_kind INTO kind FROM event_dossiers WHERE id = r.event_dossier_id;"
            if statement.count(old) != 1:
                raise RuntimeError("Unexpected frozen dossier-kind reader")
            statement = statement.replace(old, """SELECT k.code INTO kind FROM event_dossiers d
                JOIN event_kinds k ON k.id=d.event_kind_id WHERE d.id=r.event_dossier_id;""")
        else:
            statement = statement.replace("NEW.event_kind,", "NEW.event_kind_id,").replace("OLD.event_kind,", "OLD.event_kind_id,")
        result.append(statement)
    return "\n".join(result)


def remove_storage(apps, schema_editor):
    """Short, all-or-nothing DDL after preservation and observed process drain."""
    quote = schema_editor.quote_name
    connection = schema_editor.connection
    schema_editor.execute("SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='30s'")
    # Ingestion order first; all locks are bounded and released on any failure.
    order = ("accounts", "x_account_details", "posts", "account_profile_snapshots")
    tables = [*order, *(table for table in DROP_COLUMNS if table not in order), *DROP_TABLES]
    schema_editor.execute("LOCK TABLE " + ",".join(quote(table) for table in tables) + " IN ACCESS EXCLUSIVE MODE")
    check_source_bridges(connection)
    for table, name in BRIDGES:
        schema_editor.execute(f"DROP TRIGGER {quote(name)} ON {quote(table)}")
    schema_editor.execute("DROP TRIGGER pw_rg4_citizenship_owner ON person_citizenships")
    for name in sorted({name for _table, name in BRIDGES}):
        schema_editor.execute(f"DROP FUNCTION {quote(name)}()")
    schema_editor.execute("DROP FUNCTION pw_geo_legacy_id(text,text)")
    schema_editor.execute(CITIZENSHIP_LINK)
    schema_editor.execute(dossier_functions_sql(), params=None)
    schema_editor.execute(final_source_guards_sql())
    for table, columns in DROP_COLUMNS.items():
        schema_editor.execute(f"ALTER TABLE {quote(table)} " + ",".join(f"DROP COLUMN {quote(column)}" for column in columns))
    for table in DROP_TABLES:
        schema_editor.execute(f"DROP TABLE {quote(table)}")
