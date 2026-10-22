"""Reference the guarded personnel-change vocabulary in reviewed details."""

import django.db.models.deletion
from django.db import migrations, models

# Django migration declarations are class-level values.
# ruff: noqa: RUF012


def map_personnel_change_kinds(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("LOCK TABLE personnel_change_details IN SHARE ROW EXCLUSIVE MODE")
        # Only the new FK may be written; original completed-review fields are
        # fingerprinted and the frozen trigger is restored before commit.
        cursor.execute("ALTER TABLE personnel_change_details DISABLE TRIGGER ed_frozen")
        fingerprint = """
            SELECT count(*), md5(string_agg((to_jsonb(d)-'change_kind_id')::text,
                E'\\n' ORDER BY review_id)) FROM personnel_change_details d
        """
        cursor.execute(fingerprint)
        before = cursor.fetchone()
        cursor.execute("""
            UPDATE personnel_change_details d SET change_kind_id=k.id
            FROM personnel_change_types k
            WHERE k.code=d.change_kind AND d.change_kind_id IS NULL
        """)
        cursor.execute("""
            SELECT count(*) FROM personnel_change_details d
            LEFT JOIN personnel_change_types k ON k.id=d.change_kind_id
            WHERE k.code IS DISTINCT FROM d.change_kind
        """)
        if cursor.fetchone()[0]:
            raise RuntimeError("Unmapped personnel change kind; preserve source review")
        cursor.execute(fingerprint)
        if cursor.fetchone() != before:
            raise RuntimeError("Personnel review evidence changed during kind mapping")
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        cursor.execute("ALTER TABLE personnel_change_details ENABLE TRIGGER ed_frozen")


BRIDGE = """
CREATE FUNCTION pw_rg4_personnel_kind_bridge() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE resolved_code text; resolved_id bigint;
BEGIN
  IF TG_OP='UPDATE' AND NEW.change_kind IS DISTINCT FROM OLD.change_kind
      AND NEW.change_kind_id IS NOT DISTINCT FROM OLD.change_kind_id THEN
    SELECT id INTO resolved_id FROM personnel_change_types WHERE code=NEW.change_kind;
    IF resolved_id IS NULL THEN
      RAISE EXCEPTION 'Unregistered personnel change kind' USING ERRCODE='23514';
    END IF;
    NEW.change_kind_id := resolved_id;
  ELSIF NEW.change_kind_id IS NULL THEN
    SELECT id INTO resolved_id FROM personnel_change_types WHERE code=NEW.change_kind;
    IF resolved_id IS NULL THEN
      RAISE EXCEPTION 'Unregistered personnel change kind' USING ERRCODE='23514';
    END IF;
    NEW.change_kind_id := resolved_id;
  ELSE
    SELECT code INTO resolved_code FROM personnel_change_types WHERE id=NEW.change_kind_id;
    IF resolved_code IS NULL THEN
      RAISE EXCEPTION 'Unregistered personnel change identity' USING ERRCODE='23514';
    END IF;
    IF (TG_OP='INSERT' AND NEW.change_kind IS NOT NULL
        AND NEW.change_kind<>resolved_code)
       OR (TG_OP='UPDATE' AND NEW.change_kind IS DISTINCT FROM OLD.change_kind
           AND NEW.change_kind<>resolved_code) THEN
      RAISE EXCEPTION 'Conflicting personnel change representations' USING ERRCODE='23514';
    END IF;
    NEW.change_kind := resolved_code;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER pw_rg4_personnel_kind_bridge BEFORE INSERT OR UPDATE OF change_kind,change_kind_id
ON personnel_change_details FOR EACH ROW EXECUTE FUNCTION pw_rg4_personnel_kind_bridge();
"""

UNBRIDGE = """
DROP TRIGGER pw_rg4_personnel_kind_bridge ON personnel_change_details;
DROP FUNCTION pw_rg4_personnel_kind_bridge();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0139_rg4_release_meaning_references")]

    operations = [
        migrations.RunSQL(
            "SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='30s'",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AddField(
            model_name="personnelchangedetail", name="change_type_reference",
            field=models.ForeignKey(
                db_column="change_kind_id", null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="reviewed_changes", to="core.personnelchangetype",
            ),
        ),
        migrations.RunPython(map_personnel_change_kinds, migrations.RunPython.noop),
        migrations.RunSQL(BRIDGE, reverse_sql=UNBRIDGE),
        migrations.AlterField(
            model_name="personnelchangedetail", name="change_type_reference",
            field=models.ForeignKey(
                db_column="change_kind_id",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="reviewed_changes", to="core.personnelchangetype",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="personnelchangedetail", name="ck_ed_person_change"
        ),
        migrations.SeparateDatabaseAndState(state_operations=[
            migrations.RemoveField(model_name="personnelchangedetail", name="change_kind"),
        ]),
    ]
