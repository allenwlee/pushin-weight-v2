"""Frozen RG3 migration data and finite old-image compatibility bridges."""

import hashlib
import uuid

from core.job_vocabulary_v1 import ALIASES, assignment_values, canonical_code

DIMENSIONS = (
    ("job_function", "JobFunction", "JobFunctionAssignment"),
    ("seniority", "SeniorityLevel", "JobSeniorityAssignment"),
    ("employment_type", "EmploymentType", "JobEmploymentTypeAssignment"),
    ("workplace_type", "WorkplaceType", "JobWorkplaceTypeAssignment"),
    (
        "organization_ai_relationship",
        "OrganizationAIRelationshipType",
        "JobOrganizationAIRelationshipAssignment",
    ),
    (
        "role_ai_relationship",
        "RoleAIRelationshipType",
        "JobRoleAIRelationshipAssignment",
    ),
)
NORMALIZER_ID = uuid.uuid5(uuid.NAMESPACE_URL, "pushinweight:job-vocabulary:v1")
# Registry and source hashes are frozen below when constructing migration0132.
CURRENCY_CODES = (
        "ADP",
        "AED",
        "AFA",
        "AFN",
        "ALK",
        "ALL",
        "AMD",
        "ANG",
        "AOA",
        "AOK",
        "AON",
        "AOR",
        "ARA",
        "ARP",
        "ARS",
        "ARY",
        "ATS",
        "AUD",
        "AWG",
        "AYM",
        "AZM",
        "AZN",
        "BAD",
        "BAM",
        "BBD",
        "BDT",
        "BEC",
        "BEF",
        "BEL",
        "BGJ",
        "BGK",
        "BGL",
        "BGN",
        "BHD",
        "BIF",
        "BMD",
        "BND",
        "BOB",
        "BOP",
        "BOV",
        "BRB",
        "BRC",
        "BRE",
        "BRL",
        "BRN",
        "BRR",
        "BSD",
        "BTN",
        "BUK",
        "BWP",
        "BYB",
        "BYN",
        "BYR",
        "BZD",
        "CAD",
        "CDF",
        "CHC",
        "CHE",
        "CHF",
        "CHW",
        "CLF",
        "CLP",
        "CNY",
        "COP",
        "COU",
        "CRC",
        "CSD",
        "CSJ",
        "CSK",
        "CUC",
        "CUP",
        "CVE",
        "CYP",
        "CZK",
        "DDM",
        "DEM",
        "DJF",
        "DKK",
        "DOP",
        "DZD",
        "ECS",
        "ECV",
        "EEK",
        "EGP",
        "ERN",
        "ESA",
        "ESB",
        "ESP",
        "ETB",
        "EUR",
        "FIM",
        "FJD",
        "FKP",
        "FRF",
        "GBP",
        "GEK",
        "GEL",
        "GHC",
        "GHP",
        "GHS",
        "GIP",
        "GMD",
        "GNE",
        "GNF",
        "GNS",
        "GQE",
        "GRD",
        "GTQ",
        "GWE",
        "GWP",
        "GYD",
        "HKD",
        "HNL",
        "HRD",
        "HRK",
        "HTG",
        "HUF",
        "IDR",
        "IEP",
        "ILP",
        "ILR",
        "ILS",
        "INR",
        "IQD",
        "IRR",
        "ISJ",
        "ISK",
        "ITL",
        "JMD",
        "JOD",
        "JPY",
        "KES",
        "KGS",
        "KHR",
        "KMF",
        "KPW",
        "KRW",
        "KWD",
        "KYD",
        "KZT",
        "LAJ",
        "LAK",
        "LBP",
        "LKR",
        "LRD",
        "LSL",
        "LSM",
        "LTL",
        "LTT",
        "LUC",
        "LUF",
        "LUL",
        "LVL",
        "LVR",
        "LYD",
        "MAD",
        "MDL",
        "MGA",
        "MGF",
        "MKD",
        "MLF",
        "MMK",
        "MNT",
        "MOP",
        "MRO",
        "MRU",
        "MTL",
        "MTP",
        "MUR",
        "MVQ",
        "MVR",
        "MWK",
        "MXN",
        "MXP",
        "MXV",
        "MYR",
        "MZE",
        "MZM",
        "MZN",
        "NAD",
        "NGN",
        "NIC",
        "NIO",
        "NLG",
        "NOK",
        "NPR",
        "NZD",
        "OMR",
        "PAB",
        "PEH",
        "PEI",
        "PEN",
        "PES",
        "PGK",
        "PHP",
        "PKR",
        "PLN",
        "PLZ",
        "PTE",
        "PYG",
        "QAR",
        "RHD",
        "ROK",
        "ROL",
        "RON",
        "RSD",
        "RUB",
        "RUR",
        "RWF",
        "SAR",
        "SBD",
        "SCR",
        "SDD",
        "SDG",
        "SDP",
        "SEK",
        "SGD",
        "SHP",
        "SIT",
        "SKK",
        "SLE",
        "SLL",
        "SOS",
        "SRD",
        "SRG",
        "SSP",
        "STD",
        "STN",
        "SUR",
        "SVC",
        "SYP",
        "SZL",
        "THB",
        "TJR",
        "TJS",
        "TMM",
        "TMT",
        "TND",
        "TOP",
        "TPE",
        "TRL",
        "TRY",
        "TTD",
        "TWD",
        "TZS",
        "UAH",
        "UAK",
        "UGS",
        "UGW",
        "UGX",
        "USD",
        "USN",
        "USS",
        "UYI",
        "UYN",
        "UYP",
        "UYU",
        "UYW",
        "UZS",
        "VEB",
        "VED",
        "VEF",
        "VES",
        "VNC",
        "VND",
        "VUV",
        "WST",
        "XAD",
        "XAF",
        "XAG",
        "XAU",
        "XBA",
        "XBB",
        "XBC",
        "XBD",
        "XCD",
        "XCG",
        "XDR",
        "XEU",
        "XFO",
        "XFU",
        "XOF",
        "XPD",
        "XPF",
        "XPT",
        "XRE",
        "XSU",
        "XTS",
        "XUA",
        "XXX",
        "YDD",
        "YER",
        "YUD",
        "YUM",
        "YUN",
        "ZAL",
        "ZAR",
        "ZMK",
        "ZMW",
        "ZRN",
        "ZRZ",
        "ZWC",
        "ZWD",
        "ZWG",
        "ZWL",
        "ZWN",
        "ZWR",
    )
NORMALIZER_SOURCE_SHA256 = (
    "066612181d9027b903ea1f3edc85e87b27c3bd517a1baa977bd7793a3e89a914"
)


def retained_records_fingerprint(connection):
    """Compare every listing/source value outside the explicitly replaced fields."""
    excluded = {
        "job_listings": [dimension for dimension, _, _ in DIMENSIONS]
        + [
            "salary_currency",
            "salary_period",
            "salary_currency_id",
            "salary_period_id",
        ],
        "job_listing_evidence": [],
        "companies": ["hq_country", "hq_country_id"],
    }
    result = {}
    with connection.cursor() as cursor:
        for table, columns in excluded.items():
            identity = "nickname" if table == "companies" else "id"
            cursor.execute(
                f"SELECT count(*), md5(COALESCE(string_agg((to_jsonb(t)-%s::text[])::text, '' ORDER BY {identity}),'')) FROM {table} t",
                [columns],
            )
            result[table] = cursor.fetchone()
    return result


def seed_and_map(apps, schema_editor):
    database = schema_editor.connection.alias
    retained_before = retained_records_fingerprint(schema_editor.connection)
    currency = apps.get_model("core", "Currency")
    currency.objects.using(database).bulk_create(
        [currency(code=code) for code in CURRENCY_CODES]
    )
    definition = apps.get_model("core", "DefinitionVersion")
    definition.objects.using(database).create(
        id=NORMALIZER_ID,
        definition_domain="normalizer",
        definition_key="job_vocabulary",
        reported_version_token="v1",
        identity_sha256=hashlib.sha256(b"pushinweight:job-vocabulary:v1").hexdigest(),
        content_sha256=NORMALIZER_SOURCE_SHA256,
        source_git_commit="20de98dbec531d6f34c791bad170a2349fa24818",
        source_path="core/job_vocabulary_v1.py",
        provenance_state="source_pinned",
    )
    for dimension, catalogue_name in (
        *((dimension, catalogue_name) for dimension, catalogue_name, _ in DIMENSIONS),
        ("salary_period", "SalaryPeriod"),
    ):
        model = apps.get_model("core", catalogue_name)
        model.objects.using(database).bulk_create(
            [model(code=code) for code in ALIASES[dimension]]
        )

    company = apps.get_model("core", "Company")
    country_codes = set(
        apps.get_model("core", "Country")
        .objects.using(database)
        .values_list("pk", flat=True)
    )
    for row in (
        company.objects.using(database)
        .exclude(hq_country__isnull=True)
        .iterator(chunk_size=500)
    ):
        if row.hq_country == "":
            continue
        if row.hq_country not in country_codes:
            raise RuntimeError(f"RG3 HQ has no registered country: {row.hq_country!r}")
        company.objects.using(database).filter(pk=row.pk).update(
            hq_country_reference_id=row.hq_country
        )

    listing = apps.get_model("core", "JobListing")
    period_ids = dict(
        apps.get_model("core", "SalaryPeriod")
        .objects.using(database)
        .values_list("code", "pk")
    )
    currency_codes = set(CURRENCY_CODES)
    targets = {}
    for dimension, catalogue_name, assignment_name in DIMENSIONS:
        catalogue = apps.get_model("core", catalogue_name)
        targets[dimension] = (
            apps.get_model("core", assignment_name),
            dict(catalogue.objects.using(database).values_list("code", "pk")),
        )
    pending = {dimension: [] for dimension, _, _ in DIMENSIONS}
    for row in listing.objects.using(database).iterator(chunk_size=500):
        reported_currency = (row.salary_currency or "").strip().upper()
        listing.objects.using(database).filter(pk=row.pk).update(
            salary_currency_reference_id=reported_currency
            if reported_currency in currency_codes
            else None,
            salary_period_reference_id=period_ids.get(
                canonical_code("salary_period", row.salary_period)
            ),
        )
        for dimension, (model, categories) in targets.items():
            for value in assignment_values(dimension, getattr(row, dimension)):
                category_id = categories.get(value.category_code)
                pending[dimension].append(
                    model(
                        job_listing_id=row.pk,
                        category_id=category_id,
                        reported_value=value.reported_value,
                        source_value_sha256=value.source_value_sha256,
                        normalizer_version_id=NORMALIZER_ID,
                        resolution_state="resolved"
                        if category_id is not None
                        else "unresolved",
                    )
                )
            if len(pending[dimension]) >= 500:
                model.objects.using(database).bulk_create(
                    pending[dimension], batch_size=500
                )
                pending[dimension].clear()
    for dimension, (model, _) in targets.items():
        model.objects.using(database).bulk_create(pending[dimension], batch_size=500)
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
    if retained_records_fingerprint(schema_editor.connection) != retained_before:
        raise RuntimeError(
            "RG3 changed listing, company or source values outside the selected fields"
        )


SCALAR_BRIDGE_SQL = """
CREATE FUNCTION pw_rg3_salary_bridge() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (TG_OP='INSERT' AND NEW.salary_currency IS NOT NULL)
     OR (TG_OP='UPDATE' AND NEW.salary_currency IS DISTINCT FROM OLD.salary_currency) THEN
    SELECT code INTO NEW.salary_currency_id FROM currencies WHERE code=upper(btrim(NEW.salary_currency));
  ELSIF TG_OP='INSERT' OR NEW.salary_currency_id IS DISTINCT FROM OLD.salary_currency_id THEN
    NEW.salary_currency := NEW.salary_currency_id;
  END IF;
  IF (TG_OP='INSERT' AND NEW.salary_period IS NOT NULL)
     OR (TG_OP='UPDATE' AND NEW.salary_period IS DISTINCT FROM OLD.salary_period) THEN
    SELECT id INTO NEW.salary_period_id FROM salary_periods
      WHERE code=pw_rg3_period_code(NEW.salary_period);
  ELSIF TG_OP='INSERT' OR NEW.salary_period_id IS DISTINCT FROM OLD.salary_period_id THEN
    SELECT code INTO NEW.salary_period FROM salary_periods WHERE id=NEW.salary_period_id;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER pw_rg3_salary_bridge BEFORE INSERT OR UPDATE ON job_listings
FOR EACH ROW EXECUTE FUNCTION pw_rg3_salary_bridge();

CREATE FUNCTION pw_rg3_hq_bridge() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (TG_OP='INSERT' AND NEW.hq_country IS NOT NULL)
     OR (TG_OP='UPDATE' AND NEW.hq_country IS DISTINCT FROM OLD.hq_country) THEN
    NEW.hq_country_id := NULLIF(NEW.hq_country, '');
  ELSIF TG_OP='INSERT' OR NEW.hq_country_id IS DISTINCT FROM OLD.hq_country_id THEN
    NEW.hq_country := NEW.hq_country_id;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER pw_rg3_hq_bridge BEFORE INSERT OR UPDATE ON companies
FOR EACH ROW EXECUTE FUNCTION pw_rg3_hq_bridge();
"""


GUARD_SQL = """
CREATE FUNCTION pw_rg3_catalogue_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.code IS DISTINCT FROM OLD.code THEN
    RAISE EXCEPTION 'RG3 catalogue codes are immutable' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
CREATE FUNCTION pw_rg3_assignment_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.normalizer_version_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM definition_versions WHERE id=NEW.normalizer_version_id
    AND definition_domain='normalizer'
  ) THEN
    RAISE EXCEPTION 'Job classification method must be a normalizer' USING ERRCODE='23514';
  END IF;
  IF NEW.reported_value IS NOT NULL AND NEW.source_value_sha256 IS DISTINCT FROM
     encode(sha256(convert_to(NEW.reported_value,'UTF8')), 'hex') THEN
    RAISE EXCEPTION 'Job classification source hash does not match its wording' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
"""


def install_guards_and_bridges(apps, schema_editor):
    quote = schema_editor.quote_name
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout='5s'")
        cursor.execute(GUARD_SQL)
        for name in (
            "Currency",
            "SalaryPeriod",
            *(catalogue for _, catalogue, _ in DIMENSIONS),
        ):
            table = apps.get_model("core", name)._meta.db_table
            cursor.execute(
                f"CREATE TRIGGER pw_rg3_catalogue_identity BEFORE UPDATE ON {quote(table)} "
                "FOR EACH ROW EXECUTE FUNCTION pw_rg3_catalogue_identity()"
            )
        # ISO registry membership is enforced for bulk/direct inserts as well.
        cursor.execute(
            "ALTER TABLE currencies ADD CONSTRAINT ck_currency_registry CHECK (code = ANY(%s))",
            [list(CURRENCY_CODES)],
        )
        for _, _, assignment_name in DIMENSIONS:
            table = apps.get_model("core", assignment_name)._meta.db_table
            cursor.execute(
                f"ALTER TABLE {quote(table)} ADD CONSTRAINT {quote('fk_' + table + '_evidence_owner')} "
                "FOREIGN KEY (evidence_id, job_listing_id) REFERENCES job_listing_evidence(id,listing_id) DEFERRABLE INITIALLY IMMEDIATE"
            )
            cursor.execute(
                f"CREATE TRIGGER pw_rg3_assignment_guard BEFORE INSERT OR UPDATE ON {quote(table)} "
                "FOR EACH ROW EXECUTE FUNCTION pw_rg3_assignment_guard()"
            )
        cases = []
        for code, aliases in ALIASES["salary_period"].items():
            for alias in {code, *aliases}:
                cases.append(
                    "WHEN " + "'" + alias.replace("'", "''") + "' THEN '" + code + "'"
                )
        cursor.execute(
            "CREATE FUNCTION pw_rg3_period_code(text) RETURNS text LANGUAGE sql IMMUTABLE AS $$ "
            "SELECT CASE lower(btrim($1)) " + " ".join(cases) + " ELSE NULL END $$"
        )
        cursor.execute(SCALAR_BRIDGE_SQL)

        # Old binaries have no normalizer identity. Preserve their exact value
        # as unresolved; current writers use the registered v1 normalizer.
        statements = []
        for dimension, _, assignment_name in DIMENSIONS:
            table = apps.get_model("core", assignment_name)._meta.db_table
            statements.append(f"""
            IF TG_OP='INSERT' OR NEW.{quote(dimension)} IS DISTINCT FROM OLD.{quote(dimension)} THEN
              DELETE FROM {quote(table)} WHERE job_listing_id=NEW.id;
              IF NEW.{quote(dimension)} IS NOT NULL AND btrim(NEW.{quote(dimension)})<>'' THEN
                INSERT INTO {quote(table)} (job_listing_id,reported_value,source_value_sha256,resolution_state)
                VALUES(NEW.id,NEW.{quote(dimension)},encode(sha256(convert_to(NEW.{quote(dimension)},'UTF8')),'hex'),'unresolved');
              END IF;
            END IF;
            """)
        cursor.execute(
            "CREATE FUNCTION pw_rg3_dimensions_from_legacy() RETURNS trigger LANGUAGE plpgsql AS $$ "
            "BEGIN IF pg_trigger_depth()>1 THEN RETURN NEW; END IF; "
            + "\n".join(statements)
            + " RETURN NEW; END $$"
        )
        cursor.execute(
            "CREATE TRIGGER pw_rg3_dimensions_from_legacy AFTER INSERT OR UPDATE ON job_listings "
            "FOR EACH ROW EXECUTE FUNCTION pw_rg3_dimensions_from_legacy()"
        )
        cursor.execute("""
          CREATE FUNCTION pw_rg3_dimension_to_legacy() RETURNS trigger LANGUAGE plpgsql AS $$
          DECLARE owner_id bigint; owners bigint[]; rendered text;
          BEGIN
            IF pg_trigger_depth()>1 THEN RETURN NULL; END IF;
            IF TG_OP='INSERT' THEN owners:=ARRAY[NEW.job_listing_id];
            ELSIF TG_OP='DELETE' THEN owners:=ARRAY[OLD.job_listing_id];
            ELSE owners:=ARRAY[OLD.job_listing_id,NEW.job_listing_id]; END IF;
            FOR owner_id IN SELECT DISTINCT unnest(owners) LOOP
              EXECUTE format('SELECT string_agg(COALESCE(a.reported_value,c.code), %L ORDER BY a.id) FROM %I a LEFT JOIN %I c ON c.id=a.category_id WHERE a.job_listing_id=$1', ' · ', TG_TABLE_NAME, TG_ARGV[1]) INTO rendered USING owner_id;
              EXECUTE format('UPDATE job_listings SET %I=$1 WHERE id=$2', TG_ARGV[0]) USING rendered,owner_id;
            END LOOP;
            RETURN NULL;
          END $$;
        """)
        for dimension, catalogue_name, assignment_name in DIMENSIONS:
            table = apps.get_model("core", assignment_name)._meta.db_table
            catalogue = apps.get_model("core", catalogue_name)._meta.db_table
            cursor.execute(
                f"CREATE TRIGGER pw_rg3_dimension_to_legacy AFTER INSERT OR UPDATE OR DELETE ON {quote(table)} "
                "FOR EACH ROW EXECUTE FUNCTION pw_rg3_dimension_to_legacy(%s,%s)",
                [dimension, catalogue],
            )
