"""Map release maturity, availability and disclosure to their shared owners."""

import django.db.models.deletion
from django.db import migrations, models

# Django migration declarations are class-level values.
# ruff: noqa: RUF012


DOMAINS = (
    ("model_releases", "release_channel", "release_maturity_id", "release_maturities", "other"),
    ("model_release_details", "release_channel", "release_maturity_id", "release_maturities", "unknown"),
    ("model_release_details", "availability_state", "availability_state_id", "release_availability_states", "unknown"),
    ("model_release_details", "disclosure_state", "disclosure_state_id", "release_disclosure_states", "unknown"),
)


def map_release_meanings(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        # Completed dossier details are immutable. The only permitted change
        # here is filling the four newly added FK columns, while the original
        # columns are checked byte-for-byte and the table is locked. PostgreSQL
        # rolls this trigger toggle back with the migration if any check fails.
        cursor.execute("ALTER TABLE model_release_details DISABLE TRIGGER ed_frozen")
        for table, old, new, catalogue, _default in DOMAINS:
            cursor.execute(f"LOCK TABLE {table} IN SHARE ROW EXCLUSIVE MODE")
            ordering_key = "review_id" if table == "model_release_details" else "id"
            fingerprint = (
                f"SELECT count(*), md5(string_agg((to_jsonb(r)-'{new}')::text, "
                f"E'\\n' ORDER BY {ordering_key})) FROM {table} r"
            )
            cursor.execute(fingerprint)
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
                raise RuntimeError(f"Unmapped {table}.{old}; preserve source meaning")
            cursor.execute(fingerprint)
            if cursor.fetchone() != before:
                raise RuntimeError(f"{table} source rows changed during release mapping")
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        cursor.execute("ALTER TABLE model_release_details ENABLE TRIGGER ed_frozen")


def bridge_sql(table, old, new, catalogue, old_default):
    function = "pw_rg4_" + ("detail_" if table == "model_release_details" else "") + old + "_bridge"
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
    IF (TG_OP='INSERT' AND NEW.{old} IS NOT NULL
        AND NEW.{old}<>resolved_code AND NEW.{old}<>'{old_default}')
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


def unbridge_sql(table, old):
    function = "pw_rg4_" + ("detail_" if table == "model_release_details" else "") + old + "_bridge"
    return f"DROP TRIGGER {function} ON {table}; DROP FUNCTION {function}();"


class Migration(migrations.Migration):
    dependencies = [("core", "0138_rg4_event_kind_reference")]

    operations = [
        migrations.RunSQL(
            "SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='30s'",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AddField(
            model_name="modelrelease", name="release_maturity_reference",
            field=models.ForeignKey(
                db_column="release_maturity_id", null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="extracted_releases", to="core.releasematurity",
            ),
        ),
        migrations.AddField(
            model_name="modelreleasedetail", name="release_maturity_reference",
            field=models.ForeignKey(
                db_column="release_maturity_id", null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="reviewed_releases", to="core.releasematurity",
            ),
        ),
        migrations.AddField(
            model_name="modelreleasedetail", name="release_availability_reference",
            field=models.ForeignKey(
                db_column="availability_state_id", null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="reviewed_releases", to="core.releaseavailabilitystate",
            ),
        ),
        migrations.AddField(
            model_name="modelreleasedetail", name="release_disclosure_reference",
            field=models.ForeignKey(
                db_column="disclosure_state_id", null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="reviewed_releases", to="core.releasedisclosurestate",
            ),
        ),
        migrations.RunPython(map_release_meanings, migrations.RunPython.noop),
        *[
            migrations.RunSQL(
                bridge_sql(table, old, new, catalogue, default),
                reverse_sql=unbridge_sql(table, old),
            )
            for table, old, new, catalogue, default in DOMAINS
        ],
        migrations.AlterField(
            model_name="modelrelease", name="release_maturity_reference",
            field=models.ForeignKey(
                db_column="release_maturity_id",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="extracted_releases", to="core.releasematurity",
            ),
        ),
        migrations.AlterField(
            model_name="modelreleasedetail", name="release_maturity_reference",
            field=models.ForeignKey(
                db_column="release_maturity_id",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="reviewed_releases", to="core.releasematurity",
            ),
        ),
        migrations.AlterField(
            model_name="modelreleasedetail", name="release_availability_reference",
            field=models.ForeignKey(
                db_column="availability_state_id",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="reviewed_releases", to="core.releaseavailabilitystate",
            ),
        ),
        migrations.AlterField(
            model_name="modelreleasedetail", name="release_disclosure_reference",
            field=models.ForeignKey(
                db_column="disclosure_state_id",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="reviewed_releases", to="core.releasedisclosurestate",
            ),
        ),
        migrations.RemoveConstraint(model_name="modelreleasedetail", name="ck_ed_release_channel"),
        migrations.RemoveConstraint(model_name="modelreleasedetail", name="ck_ed_release_availability"),
        migrations.RemoveConstraint(model_name="modelreleasedetail", name="ck_ed_release_disclosure"),
        migrations.SeparateDatabaseAndState(state_operations=[
            migrations.RemoveField(model_name="modelrelease", name="release_channel"),
            migrations.RemoveField(model_name="modelreleasedetail", name="release_channel"),
            migrations.RemoveField(model_name="modelreleasedetail", name="availability_state"),
            migrations.RemoveField(model_name="modelreleasedetail", name="disclosure_state"),
        ]),
    ]
