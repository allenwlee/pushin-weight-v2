"""Reference the controlled claim-kind catalogue without changing claim hashes."""

import django.db.models.deletion
from django.db import migrations, models

# Django migration declarations are class-level values.
# ruff: noqa: RUF012


def seed_established_claim_kind(apps, schema_editor):
    kind = apps.get_model("core", "EventClaimKind")
    kind.objects.using(schema_editor.connection.alias).get_or_create(
        code="repository_created"
    )


def map_claim_kinds(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("LOCK TABLE event_dossier_claims IN SHARE ROW EXCLUSIVE MODE")
        cursor.execute("ALTER TABLE event_dossier_claims DISABLE TRIGGER ed_frozen")
        fingerprint = """
            SELECT count(*), md5(string_agg((to_jsonb(c)-'claim_kind_id')::text,
                E'\\n' ORDER BY id)) FROM event_dossier_claims c
        """
        cursor.execute(fingerprint)
        before = cursor.fetchone()
        cursor.execute("""
            UPDATE event_dossier_claims c SET claim_kind_id=k.id
            FROM event_claim_kinds k
            WHERE k.code=c.claim_kind AND c.claim_kind_id IS NULL
        """)
        cursor.execute("""
            SELECT count(*) FROM event_dossier_claims c
            LEFT JOIN event_claim_kinds k ON k.id=c.claim_kind_id
            WHERE k.code IS DISTINCT FROM c.claim_kind
        """)
        if cursor.fetchone()[0]:
            raise RuntimeError("Unmapped dossier claim kind; preserve original claim")
        cursor.execute(fingerprint)
        if cursor.fetchone() != before:
            raise RuntimeError("Dossier claim evidence changed during kind mapping")
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        cursor.execute("ALTER TABLE event_dossier_claims ENABLE TRIGGER ed_frozen")


BRIDGE = """
CREATE FUNCTION pw_rg4_claim_kind_bridge() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE resolved_code text; resolved_id bigint;
BEGIN
  IF TG_OP='UPDATE' AND NEW.claim_kind IS DISTINCT FROM OLD.claim_kind
      AND NEW.claim_kind_id IS NOT DISTINCT FROM OLD.claim_kind_id THEN
    SELECT id INTO resolved_id FROM event_claim_kinds WHERE code=NEW.claim_kind;
    IF resolved_id IS NULL THEN
      RAISE EXCEPTION 'Unregistered claim kind' USING ERRCODE='23514';
    END IF;
    NEW.claim_kind_id := resolved_id;
  ELSIF NEW.claim_kind_id IS NULL THEN
    SELECT id INTO resolved_id FROM event_claim_kinds WHERE code=NEW.claim_kind;
    IF resolved_id IS NULL THEN
      RAISE EXCEPTION 'Unregistered claim kind' USING ERRCODE='23514';
    END IF;
    NEW.claim_kind_id := resolved_id;
  ELSE
    SELECT code INTO resolved_code FROM event_claim_kinds WHERE id=NEW.claim_kind_id;
    IF resolved_code IS NULL THEN
      RAISE EXCEPTION 'Unregistered claim kind identity' USING ERRCODE='23514';
    END IF;
    IF (TG_OP='INSERT' AND NEW.claim_kind IS NOT NULL
        AND NEW.claim_kind<>resolved_code)
       OR (TG_OP='UPDATE' AND NEW.claim_kind IS DISTINCT FROM OLD.claim_kind
           AND NEW.claim_kind<>resolved_code) THEN
      RAISE EXCEPTION 'Conflicting claim-kind representations' USING ERRCODE='23514';
    END IF;
    NEW.claim_kind := resolved_code;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER pw_rg4_claim_kind_bridge BEFORE INSERT OR UPDATE OF claim_kind,claim_kind_id
ON event_dossier_claims FOR EACH ROW EXECUTE FUNCTION pw_rg4_claim_kind_bridge();
"""

UNBRIDGE = """
DROP TRIGGER pw_rg4_claim_kind_bridge ON event_dossier_claims;
DROP FUNCTION pw_rg4_claim_kind_bridge();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0140_rg4_personnel_change_kind_reference")]

    operations = [
        migrations.RunSQL(
            "SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='30s'",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunPython(seed_established_claim_kind, migrations.RunPython.noop),
        migrations.AddField(
            model_name="eventdossierclaim", name="claim_kind_reference",
            field=models.ForeignKey(
                db_column="claim_kind_id", null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="dossier_claims", to="core.eventclaimkind",
            ),
        ),
        migrations.RunPython(map_claim_kinds, migrations.RunPython.noop),
        migrations.RunSQL(BRIDGE, reverse_sql=UNBRIDGE),
        migrations.AlterField(
            model_name="eventdossierclaim", name="claim_kind_reference",
            field=models.ForeignKey(
                db_column="claim_kind_id",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="dossier_claims", to="core.eventclaimkind",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="eventdossierclaim", name="ck_ed_claim_text"
        ),
        migrations.AddConstraint(
            model_name="eventdossierclaim",
            constraint=models.CheckConstraint(
                condition=~models.Q(scope_key="")
                & ~models.Q(extraction_version="")
                & ~models.Q(assertion_text="")
                & ~models.Q(source_excerpt=""),
                name="ck_ed_claim_text",
            ),
        ),
        migrations.SeparateDatabaseAndState(state_operations=[
            migrations.RemoveField(model_name="eventdossierclaim", name="claim_kind"),
        ]),
    ]
