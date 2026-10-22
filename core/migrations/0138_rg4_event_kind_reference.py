"""Move atomic dossier kinds to the shared guarded business vocabulary."""

import django.db.models.deletion
from django.db import migrations, models

# Django migrations use class-level declarations.
# ruff: noqa: RUF012


def map_dossier_kinds(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("LOCK TABLE event_dossiers IN SHARE ROW EXCLUSIVE MODE")
        fingerprint = """
            SELECT count(*), md5(string_agg((to_jsonb(d)-'event_kind_id')::text,
                E'\\n' ORDER BY id)) FROM event_dossiers d
        """
        cursor.execute(fingerprint)
        before = cursor.fetchone()
        cursor.execute("""
            UPDATE event_dossiers d SET event_kind_id=k.id FROM event_kinds k
            WHERE k.code=d.event_kind AND d.event_kind_id IS NULL
        """)
        cursor.execute("""
            SELECT count(*) FROM event_dossiers d LEFT JOIN event_kinds k
            ON k.id=d.event_kind_id WHERE k.code IS DISTINCT FROM d.event_kind
        """)
        if cursor.fetchone()[0]:
            raise RuntimeError("Unmapped dossier event kinds; preserve atomic identity")
        cursor.execute(fingerprint)
        if cursor.fetchone() != before:
            raise RuntimeError("Dossier identities or evidence changed during kind mapping")
        # Flush deferred FK checks before the later ALTER TABLE in this migration.
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")


BRIDGE = """
CREATE FUNCTION pw_rg4_dossier_kind_bridge() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE resolved_code text; resolved_id bigint;
BEGIN
  IF TG_OP='UPDATE' AND NEW.event_kind IS DISTINCT FROM OLD.event_kind
      AND NEW.event_kind_id IS NOT DISTINCT FROM OLD.event_kind_id THEN
    SELECT id INTO resolved_id FROM event_kinds WHERE code=NEW.event_kind;
    IF resolved_id IS NULL THEN
      RAISE EXCEPTION 'Unregistered event kind' USING ERRCODE='23514';
    END IF;
    NEW.event_kind_id := resolved_id;
  ELSIF NEW.event_kind_id IS NULL THEN
    SELECT id INTO resolved_id FROM event_kinds WHERE code=NEW.event_kind;
    IF resolved_id IS NULL THEN
      RAISE EXCEPTION 'Unregistered event kind' USING ERRCODE='23514';
    END IF;
    NEW.event_kind_id := resolved_id;
  ELSE
    SELECT code INTO resolved_code FROM event_kinds WHERE id=NEW.event_kind_id;
    IF resolved_code IS NULL THEN
      RAISE EXCEPTION 'Unregistered event kind identity' USING ERRCODE='23514';
    END IF;
    IF (TG_OP='INSERT' AND NEW.event_kind IS NOT NULL
        AND NEW.event_kind<>resolved_code)
       OR (TG_OP='UPDATE' AND NEW.event_kind IS DISTINCT FROM OLD.event_kind
           AND NEW.event_kind<>resolved_code) THEN
      RAISE EXCEPTION 'Conflicting event kind representations' USING ERRCODE='23514';
    END IF;
    NEW.event_kind := resolved_code;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER pw_rg4_dossier_kind_bridge BEFORE INSERT OR UPDATE OF event_kind,event_kind_id
ON event_dossiers FOR EACH ROW EXECUTE FUNCTION pw_rg4_dossier_kind_bridge();

CREATE FUNCTION pw_rg4_dossier_kind_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.event_kind_id IS DISTINCT FROM OLD.event_kind_id THEN
    RAISE EXCEPTION 'Dossier event kind is immutable' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER pw_rg4_dossier_kind_identity BEFORE UPDATE ON event_dossiers
FOR EACH ROW EXECUTE FUNCTION pw_rg4_dossier_kind_identity();
"""

UNBRIDGE = """
DROP TRIGGER pw_rg4_dossier_kind_identity ON event_dossiers;
DROP FUNCTION pw_rg4_dossier_kind_identity();
DROP TRIGGER pw_rg4_dossier_kind_bridge ON event_dossiers;
DROP FUNCTION pw_rg4_dossier_kind_bridge();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0137_rg4_affiliation_opportunity_references")]

    operations = [
        migrations.RunSQL(
            "SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='30s'",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AddField(
            model_name="eventdossier",
            name="event_kind_reference",
            field=models.ForeignKey(
                db_column="event_kind_id", null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="dossiers", to="core.eventkind",
            ),
        ),
        migrations.RunPython(map_dossier_kinds, migrations.RunPython.noop),
        migrations.RunSQL(BRIDGE, reverse_sql=UNBRIDGE),
        migrations.AlterField(
            model_name="eventdossier",
            name="event_kind_reference",
            field=models.ForeignKey(
                db_column="event_kind_id",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="dossiers", to="core.eventkind",
            ),
        ),
        migrations.RemoveConstraint(model_name="eventdossier", name="ck_ed_kind"),
        # Remove from new ORM state only. The old application image still sees
        # its scalar until the final RG4 physical-deletion candidate.
        migrations.SeparateDatabaseAndState(state_operations=[
            migrations.RemoveField(model_name="eventdossier", name="event_kind"),
        ]),
    ]
