"""Remove RG3 compatibility columns after all affected old processes finish.

Release 0132/0133 separately. Recovery after this migration uses replacement-only
application code or a forward repair; the old columns are not reconstructed.
"""

# Django migration operation lists are class-level declarations.
# ruff: noqa: RUF012
from django.db import migrations

from core.job_vocabulary_v1 import EXPLICIT_PLURALS

DIMENSIONS = (
    ("job_function", "job_function_assignments", "job_functions"),
    ("seniority", "job_seniority_assignments", "seniority_levels"),
    ("employment_type", "job_employment_type_assignments", "employment_types"),
    ("workplace_type", "job_workplace_type_assignments", "workplace_types"),
    (
        "organization_ai_relationship",
        "job_organization_ai_relationship_assignments",
        "organization_ai_relationship_types",
    ),
    (
        "role_ai_relationship",
        "job_role_ai_relationship_assignments",
        "role_ai_relationship_types",
    ),
)


def remove_compatibility(apps, schema_editor):
    """Keep every listing, source record, assignment and replacement reference."""
    quote = schema_editor.quote_name
    retired = {
        "companies": ["hq_country"],
        "job_listings": [dimension for dimension, _, _ in DIMENSIONS]
        + ["salary_currency", "salary_period"],
        "job_listing_evidence": [],
        **{table: [] for _, table, _ in DIMENSIONS},
    }
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout='5s'")
        cursor.execute("SET LOCAL statement_timeout='30s'")
        # The check and drop must see one stable set of source and owner rows.
        # Short bounded locks prevent a writer from changing an already checked
        # legacy value before deletion. A busy database aborts this transaction.
        cursor.execute(
            "LOCK TABLE "
            + ", ".join(quote(table) for table in retired)
            + " IN ACCESS EXCLUSIVE MODE"
        )

        def retained_fingerprints():
            fingerprints = {}
            for table, columns in retired.items():
                identity = "nickname" if table == "companies" else "id"
                cursor.execute(
                    "SELECT count(*), md5(COALESCE(string_agg("
                    "(to_jsonb(t)-%s::text[])::text, '' ORDER BY "
                    + quote(identity)
                    + "),'')) FROM "
                    + quote(table)
                    + " t",
                    [columns],
                )
                fingerprints[table] = cursor.fetchone()
            return fingerprints

        before = retained_fingerprints()
        checks = {
            "company headquarters": """
                SELECT count(*) FROM companies
                WHERE NULLIF(hq_country, '') IS DISTINCT FROM hq_country_id
            """,
        }
        for field, resolved in (
            (
                "salary_currency",
                "j.salary_currency_id=upper(btrim(j.salary_currency))",
            ),
            (
                "salary_period",
                (
                    "EXISTS (SELECT 1 FROM salary_periods p "
                    "WHERE p.id=j.salary_period_id "
                    "AND p.code=pw_rg3_period_code(j.salary_period))"
                ),
            ),
        ):
            checks[field] = f"""
                SELECT count(*) FROM job_listings j
                WHERE NULLIF(btrim(j.{quote(field)}), '') IS NOT NULL
                  AND NOT COALESCE(({resolved}), false)
                  AND NOT COALESCE(btrim(j.raw_payload->>'{field}')=btrim(j.{quote(field)}), false)
                  AND NOT EXISTS (
                    SELECT 1 FROM job_listing_evidence e WHERE e.listing_id=j.id
                    AND (btrim(e.raw_evidence->'record'->>'{field}')=btrim(j.{quote(field)})
                      OR btrim(e.raw_evidence->>'{field}')=btrim(j.{quote(field)}))
                  )
            """
        for meaning, sql in checks.items():
            cursor.execute(sql)
            missing = cursor.fetchone()[0]
            if missing:
                raise RuntimeError(
                    f"RG3 deletion refused: {missing} unpreserved {meaning} values"
                )
        for field, table, catalogue in DIMENSIONS:
            cursor.execute(f"""
                SELECT j.id,j.{quote(field)} FROM job_listings j
                WHERE NULLIF(btrim(j.{quote(field)}), '') IS NOT NULL
                  AND NOT EXISTS (SELECT 1 FROM {quote(table)} a
                    WHERE a.job_listing_id=j.id AND a.reported_value=j.{quote(field)})
                  AND j.{quote(field)} IS DISTINCT FROM (
                    SELECT string_agg(COALESCE(a.reported_value,c.code), ' · ' ORDER BY a.id)
                    FROM {quote(table)} a LEFT JOIN {quote(catalogue)} c ON c.id=a.category_id
                    WHERE a.job_listing_id=j.id
                  )
            """)
            candidates = cursor.fetchall()
            for listing_id, reported in candidates:
                # The frozen v1 mapping splits only these explicitly reviewed
                # plural phrases. Every part must survive; do not infer a split
                # from arbitrary source prose or accept only one of the parts.
                parts = EXPLICIT_PLURALS.get(field, {}).get(reported.strip().casefold())
                cursor.execute(
                    "SELECT reported_value FROM "
                    + quote(table)
                    + " WHERE job_listing_id=%s",
                    [listing_id],
                )
                retained = {row[0] for row in cursor.fetchall()}
                if not parts or not set(parts).issubset(retained):
                    raise RuntimeError(
                        f"RG3 deletion refused: unpreserved {field} value on listing {listing_id}"
                    )

        for _, table, _ in DIMENSIONS:
            cursor.execute("DROP TRIGGER pw_rg3_dimension_to_legacy ON " + quote(table))
        cursor.execute("DROP TRIGGER pw_rg3_dimensions_from_legacy ON job_listings")
        cursor.execute("DROP TRIGGER pw_rg3_salary_bridge ON job_listings")
        cursor.execute("DROP TRIGGER pw_rg3_hq_bridge ON companies")
        cursor.execute("DROP FUNCTION pw_rg3_dimension_to_legacy()")
        cursor.execute("DROP FUNCTION pw_rg3_dimensions_from_legacy()")
        cursor.execute("DROP FUNCTION pw_rg3_salary_bridge()")
        cursor.execute("DROP FUNCTION pw_rg3_hq_bridge()")
        cursor.execute("DROP FUNCTION pw_rg3_period_code(text)")
        for table in ("job_listings", "companies"):
            cursor.execute(
                "ALTER TABLE "
                + quote(table)
                + " "
                + ", ".join("DROP COLUMN " + quote(column) for column in retired[table])
            )
        if retained_fingerprints() != before:
            raise RuntimeError(
                "RG3 deletion changed retained listing/source/assignment data"
            )


class Migration(migrations.Migration):
    dependencies = [("core", "0133_rg3_cutover_job_and_hq_fields")]
    operations = [migrations.RunPython(remove_compatibility, reverse_code=None)]
