"""Restore the two owner-selected scalars without rewriting source rows.

The old FK columns and their bridges stay physical until the RG4 drain/drop.
This forward migration never rewrites the already-applied 0135–0146 history.
"""

from django.db import migrations, models

# Django migration declarations are class-level values.
# ruff: noqa: RUF012


def verify_original_values(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "LOCK TABLE people_names, model_release_details IN SHARE ROW EXCLUSIVE MODE"
        )
        for table, scalar, reference, catalogue in (
            ("people_names", "name_type", "name_type_id", "person_name_types"),
            ("model_release_details", "disclosure_state", "disclosure_state_id", "release_disclosure_states"),
        ):
            cursor.execute(
                f"SELECT count(*) FROM {table} r LEFT JOIN {catalogue} c "
                f"ON c.id=r.{reference} WHERE r.{scalar} IS NULL "
                f"OR c.id IS NULL OR r.{scalar} IS DISTINCT FROM c.code"
            )
            if cursor.fetchone()[0]:
                raise RuntimeError(f"Conflicting {table}.{scalar}; preserve and reconcile evidence")


NAME_IDENTITY = """
CREATE FUNCTION pw_person_name_type_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.name_type IS DISTINCT FROM OLD.name_type THEN
    RAISE EXCEPTION 'Create a new name representation to change its kind' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER pw_person_name_type_immutable BEFORE UPDATE ON people_names
FOR EACH ROW EXECUTE FUNCTION pw_person_name_type_immutable();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0146_rg4_career_site_source_type")]

    operations = [
        migrations.RunSQL(
            "SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='30s'",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunPython(verify_original_values, migrations.RunPython.noop),
        migrations.SeparateDatabaseAndState(state_operations=[
            migrations.RemoveField(
                model_name="modelreleasedetail", name="release_disclosure_reference",
            ),
            migrations.RemoveField(model_name="personname", name="name_type_reference"),
            migrations.AddField(
                model_name="modelreleasedetail", name="disclosure_state",
                field=models.CharField(
                    choices=[(v, v) for v in ("unknown", "unannounced", "announced")],
                    default="unknown", max_length=16,
                ),
            ),
            migrations.AddField(
                model_name="personname", name="name_type",
                field=models.CharField(
                    choices=[(v, v) for v in ("professional", "romanized")],
                    default="professional", max_length=32,
                ),
            ),
        ]),
        migrations.AddConstraint(
            model_name="modelreleasedetail",
            constraint=models.CheckConstraint(
                condition=models.Q(disclosure_state__in=["unknown", "unannounced", "announced"]),
                name="ck_ed_release_disclosure",
            ),
        ),
        migrations.AddConstraint(
            model_name="personname",
            constraint=models.CheckConstraint(
                condition=models.Q(name_type__in=["professional", "romanized"]),
                name="ck_person_name_type",
            ),
        ),
        migrations.RunSQL(NAME_IDENTITY, reverse_sql="""
            DROP TRIGGER pw_person_name_type_immutable ON people_names;
            DROP FUNCTION pw_person_name_type_immutable();
        """),
    ]
