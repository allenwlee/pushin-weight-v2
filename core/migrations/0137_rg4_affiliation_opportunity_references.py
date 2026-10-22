"""Reference shared business kinds without changing source identities or evidence."""

import django.db.models.deletion
from django.db import migrations, models

# Django migration declarations are class-level values.
# ruff: noqa: RUF012


DOMAINS = (
    ("people_brand_affiliations", "affiliation_type", "affiliation_types"),
    ("opportunities", "opportunity_type", "opportunity_types"),
)


def map_business_kinds(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        for table, old, catalogue in DOMAINS:
            new = old + "_id"
            cursor.execute(f"LOCK TABLE {table} IN SHARE ROW EXCLUSIVE MODE")
            cursor.execute(
                f"SELECT count(*), md5(string_agg((to_jsonb(r)-'{new}')::text, "
                f"E'\\n' ORDER BY id)) FROM {table} r"
            )
            before = cursor.fetchone()
            cursor.execute(
                f"UPDATE {table} r SET {new}=c.id FROM {catalogue} c "
                f"WHERE c.code=r.{old} AND r.{new} IS NULL"
            )
            cursor.execute(
                f"SELECT count(*) FROM {table} r LEFT JOIN {catalogue} c "
                f"ON c.id=r.{new} WHERE c.code IS DISTINCT FROM r.{old}"
            )
            if cursor.fetchone()[0]:
                raise RuntimeError(f"Unmapped {table}.{old}; preserve source evidence")
            cursor.execute(
                f"SELECT count(*), md5(string_agg((to_jsonb(r)-'{new}')::text, "
                f"E'\\n' ORDER BY id)) FROM {table} r"
            )
            if cursor.fetchone() != before:
                raise RuntimeError(f"{table} source rows changed during kind mapping")
        # Existing rows create deferred FK trigger events when the new IDs are
        # populated. PostgreSQL refuses the following ALTER TABLE while those
        # events remain queued in this transaction.
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")


def bridge_sql(table, old, catalogue):
    new = old + "_id"
    function = "pw_rg4_" + old + "_bridge"
    return f"""
CREATE FUNCTION {function}() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE resolved_code text; resolved_id bigint;
BEGIN
  IF TG_OP='UPDATE' AND NEW.{old} IS DISTINCT FROM OLD.{old}
      AND NEW.{new} IS NOT DISTINCT FROM OLD.{new} THEN
    SELECT id INTO resolved_id FROM {catalogue} WHERE code=NEW.{old};
    IF resolved_id IS NULL THEN
      RAISE EXCEPTION 'Unregistered {old}' USING ERRCODE='23514';
    END IF;
    NEW.{new} := resolved_id;
  ELSIF NEW.{new} IS NULL THEN
    SELECT id INTO resolved_id FROM {catalogue} WHERE code=NEW.{old};
    IF resolved_id IS NULL THEN
      RAISE EXCEPTION 'Unregistered {old}' USING ERRCODE='23514';
    END IF;
    NEW.{new} := resolved_id;
  ELSE
    SELECT code INTO resolved_code FROM {catalogue} WHERE id=NEW.{new};
    IF resolved_code IS NULL THEN
      RAISE EXCEPTION 'Unregistered {old} identity' USING ERRCODE='23514';
    END IF;
    IF (TG_OP='INSERT' AND NEW.{old} IS NOT NULL AND NEW.{old}<>resolved_code)
       OR (TG_OP='UPDATE' AND NEW.{old} IS DISTINCT FROM OLD.{old}
           AND NEW.{old}<>resolved_code) THEN
      RAISE EXCEPTION 'Conflicting {old} representations' USING ERRCODE='23514';
    END IF;
    NEW.{old} := resolved_code;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER {function} BEFORE INSERT OR UPDATE OF {old},{new}
ON {table} FOR EACH ROW EXECUTE FUNCTION {function}();
"""


def unbridge_sql(table, old, catalogue):
    function = "pw_rg4_" + old + "_bridge"
    return f"DROP TRIGGER {function} ON {table}; DROP FUNCTION {function}();"


class Migration(migrations.Migration):
    dependencies = [("core", "0136_rg4_person_name_kind_cutover")]

    operations = [
        migrations.RunSQL(
            "SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='30s'",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AddField(
            model_name="personbrandaffiliation",
            name="affiliation_type_reference",
            field=models.ForeignKey(
                db_column="affiliation_type_id", null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="affiliations", to="core.affiliationtype",
            ),
        ),
        migrations.AddField(
            model_name="opportunity",
            name="opportunity_type_reference",
            field=models.ForeignKey(
                db_column="opportunity_type_id", null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="opportunities", to="core.opportunitytype",
            ),
        ),
        migrations.RunPython(map_business_kinds, migrations.RunPython.noop),
        *[
            migrations.RunSQL(
                bridge_sql(table, old, catalogue),
                reverse_sql=unbridge_sql(table, old, catalogue),
            )
            for table, old, catalogue in DOMAINS
        ],
        migrations.AlterField(
            model_name="personbrandaffiliation",
            name="affiliation_type_reference",
            field=models.ForeignKey(
                db_column="affiliation_type_id",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="affiliations", to="core.affiliationtype",
            ),
        ),
        migrations.AlterField(
            model_name="opportunity",
            name="opportunity_type_reference",
            field=models.ForeignKey(
                db_column="opportunity_type_id",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="opportunities", to="core.opportunitytype",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="personbrandaffiliation", name="ck_pba_affiliation_type"
        ),
        migrations.RemoveConstraint(
            model_name="opportunity", name="ck_opportunities_type"
        ),
        migrations.RemoveIndex(
            model_name="personbrandaffiliation", name="idx_pba_brand_type_status"
        ),
        migrations.RemoveIndex(
            model_name="personbrandaffiliation", name="idx_pba_person_type"
        ),
        migrations.AddIndex(
            model_name="personbrandaffiliation",
            index=models.Index(
                fields=["brand", "affiliation_type_reference", "status"],
                name="idx_pba_brand_type_status",
            ),
        ),
        migrations.AddIndex(
            model_name="personbrandaffiliation",
            index=models.Index(
                fields=["person", "affiliation_type_reference"],
                name="idx_pba_person_type",
            ),
        ),
        # Keep the old columns physical until the final RG4 deletion candidate.
        migrations.SeparateDatabaseAndState(state_operations=[
            migrations.RemoveField(
                model_name="personbrandaffiliation", name="affiliation_type"
            ),
            migrations.RemoveField(model_name="opportunity", name="opportunity_type"),
        ]),
    ]
