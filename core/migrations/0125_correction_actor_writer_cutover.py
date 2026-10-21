import django.db.models.deletion
from django.db import migrations, models


def backfill_registered_actors(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            UPDATE collection_corrections c
            SET actor_id=a.id
            FROM actors a
            WHERE c.actor_id IS NULL
              AND c.actor_identifier=a.actor_kind || ':' || a.actor_key
        """)
        cursor.execute("SELECT count(*) FROM collection_corrections WHERE actor_id IS NULL")
        if cursor.fetchone()[0]:
            raise RuntimeError(
                "Correction actor labels without an exact registered Actor match "
                "block actor cutover; preserve and resolve them first"
            )


ACTOR_BRIDGE = """
CREATE OR REPLACE FUNCTION sync_correction_actor_label() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE legacy_changed boolean; reference_changed boolean;
BEGIN
    IF TG_OP='INSERT' THEN
        IF NEW.actor_id IS NULL THEN
            SELECT id INTO NEW.actor_id FROM actors
            WHERE actor_kind || ':' || actor_key = NEW.actor_identifier;
        ELSIF NEW.actor_identifier IS NOT NULL
          AND NEW.actor_identifier IS DISTINCT FROM (
              SELECT actor_kind || ':' || actor_key FROM actors WHERE id=NEW.actor_id
          ) THEN
            RAISE EXCEPTION 'correction actor reference differs from reported actor'
                USING ERRCODE='23514';
        END IF;
    ELSE
        legacy_changed := NEW.actor_identifier IS DISTINCT FROM OLD.actor_identifier;
        reference_changed := NEW.actor_id IS DISTINCT FROM OLD.actor_id;
        IF legacy_changed AND NOT reference_changed THEN
            SELECT id INTO NEW.actor_id FROM actors
            WHERE actor_kind || ':' || actor_key = NEW.actor_identifier;
        ELSIF legacy_changed AND reference_changed THEN
            IF NEW.actor_identifier IS DISTINCT FROM (
                SELECT actor_kind || ':' || actor_key FROM actors WHERE id=NEW.actor_id
            ) THEN
                RAISE EXCEPTION 'correction actor reference differs from reported actor'
                    USING ERRCODE='23514';
            END IF;
        END IF;
    END IF;
    IF NEW.actor_id IS NOT NULL THEN
        SELECT actor_kind || ':' || actor_key INTO NEW.actor_identifier
        FROM actors WHERE id=NEW.actor_id;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER sync_correction_actor_label
BEFORE INSERT OR UPDATE ON collection_corrections
FOR EACH ROW EXECUTE FUNCTION sync_correction_actor_label();
"""

REVERSE_ACTOR_BRIDGE = """
DROP TRIGGER sync_correction_actor_label ON collection_corrections;
DROP FUNCTION sync_correction_actor_label();
"""

RESTORE_CORRECTION_GUARD = """
CREATE FUNCTION collection_correction_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE owner_observation bigint;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'collection correction is immutable' USING ERRCODE='23514';
    END IF;
    IF NEW.metric_value_id IS NOT NULL THEN
        SELECT observation_id INTO owner_observation FROM metric_values WHERE id=NEW.metric_value_id;
        IF owner_observation IS NULL OR owner_observation <> NEW.observation_id THEN
            RAISE EXCEPTION 'correction must reference its measurement observation' USING ERRCODE='23514';
        END IF;
    END IF;
    IF NEW.predecessor_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM collection_corrections c WHERE c.id=NEW.predecessor_id
        AND c.observation_id=NEW.observation_id
        AND c.metric_value_id IS NOT DISTINCT FROM NEW.metric_value_id
        AND c.correction_kind=NEW.correction_kind
    ) THEN
        RAISE EXCEPTION 'correction predecessor has another owner' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER collection_correction_guard BEFORE INSERT OR UPDATE OR DELETE
ON collection_corrections FOR EACH ROW EXECUTE FUNCTION collection_correction_guard();
"""

DROP_CORRECTION_GUARD = """
DROP TRIGGER collection_correction_guard ON collection_corrections;
DROP FUNCTION collection_correction_guard();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0124_metric_unit_writer_cutover")]

    state_operations = [
        migrations.RemoveField(
            model_name="collectioncorrection", name="actor_identifier"
        ),
        migrations.AlterField(
            model_name="collectioncorrection",
            name="actor",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, to="core.actor"
            ),
        ),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=state_operations,
            database_operations=[
                migrations.RunSQL("SET LOCAL lock_timeout='5s'", migrations.RunSQL.noop),
                migrations.RunSQL(DROP_CORRECTION_GUARD, RESTORE_CORRECTION_GUARD),
                migrations.RunPython(backfill_registered_actors, migrations.RunPython.noop),
                migrations.RunSQL(RESTORE_CORRECTION_GUARD, DROP_CORRECTION_GUARD),
                migrations.RunSQL(ACTOR_BRIDGE, REVERSE_ACTOR_BRIDGE),
            ],
        )
    ]
