"""Keep claim scope independent while typing timezone and release access channel."""

import django.db.models.deletion
from django.db import migrations, models

# Django migration declarations are class-level values.
# ruff: noqa: RUF012


def map_claim_timezones(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("LOCK TABLE event_dossier_claims IN SHARE ROW EXCLUSIVE MODE")
        cursor.execute("ALTER TABLE event_dossier_claims DISABLE TRIGGER ed_frozen")
        fingerprint = """
            SELECT count(*), md5(string_agg((to_jsonb(c)-'event_timezone_id'
                -'access_channel_id')::text, E'\\n' ORDER BY id))
            FROM event_dossier_claims c
        """
        cursor.execute(fingerprint)
        before = cursor.fetchone()
        cursor.execute("""
            UPDATE event_dossier_claims c SET event_timezone_id=z.code
            FROM time_zones z
            WHERE z.code=c.event_timezone AND c.event_timezone_id IS NULL
        """)
        cursor.execute("""
            SELECT count(*) FROM event_dossier_claims c
            WHERE c.event_timezone IS NOT NULL
              AND c.event_timezone_id IS DISTINCT FROM c.event_timezone
        """)
        if cursor.fetchone()[0]:
            raise RuntimeError("Unmapped dossier claim timezone; preserve source evidence")
        cursor.execute(fingerprint)
        if cursor.fetchone() != before:
            raise RuntimeError("Dossier claim evidence changed during timezone mapping")
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        cursor.execute("ALTER TABLE event_dossier_claims ENABLE TRIGGER ed_frozen")


BRIDGE = """
CREATE FUNCTION pw_rg4_claim_timezone_bridge() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.event_timezone_id IS NULL THEN
    IF NEW.event_timezone IS NOT NULL THEN
      IF NOT EXISTS (SELECT 1 FROM time_zones WHERE code=NEW.event_timezone) THEN
        RAISE EXCEPTION 'Unregistered claim timezone' USING ERRCODE='23514';
      END IF;
      NEW.event_timezone_id := NEW.event_timezone;
    END IF;
  ELSE
    IF NOT EXISTS (SELECT 1 FROM time_zones WHERE code=NEW.event_timezone_id) THEN
      RAISE EXCEPTION 'Unregistered claim timezone identity' USING ERRCODE='23514';
    END IF;
    IF NEW.event_timezone IS NOT NULL
        AND NEW.event_timezone IS DISTINCT FROM NEW.event_timezone_id THEN
      RAISE EXCEPTION 'Conflicting claim timezone representations' USING ERRCODE='23514';
    END IF;
    NEW.event_timezone := NEW.event_timezone_id;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER pw_rg4_claim_timezone_bridge BEFORE INSERT OR UPDATE OF event_timezone,event_timezone_id
ON event_dossier_claims FOR EACH ROW EXECUTE FUNCTION pw_rg4_claim_timezone_bridge();
"""

UNBRIDGE = """
DROP TRIGGER pw_rg4_claim_timezone_bridge ON event_dossier_claims;
DROP FUNCTION pw_rg4_claim_timezone_bridge();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0141_rg4_dossier_claim_kind_reference")]

    operations = [
        migrations.RunSQL(
            "SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='30s'",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AddField(
            model_name="eventdossierclaim", name="event_timezone_reference",
            field=models.ForeignKey(
                db_column="event_timezone_id", null=True, blank=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="dossier_claims", to="core.timezone",
            ),
        ),
        migrations.AddField(
            model_name="eventdossierclaim", name="release_access_channel_reference",
            field=models.ForeignKey(
                db_column="access_channel_id", null=True, blank=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="dossier_claims", to="core.releaseaccesschannel",
            ),
        ),
        migrations.RunPython(map_claim_timezones, migrations.RunPython.noop),
        migrations.RunSQL(BRIDGE, reverse_sql=UNBRIDGE),
        migrations.SeparateDatabaseAndState(state_operations=[
            migrations.RemoveField(model_name="eventdossierclaim", name="event_timezone"),
        ]),
    ]
