"""Keep0092 dispatch writes coherent through the additive deployment window.

The existing metadata keys are temporary compatibility projections. Typed jobs
own new dispatch, while an older image can still register/select a v1 job.
Unknown legacy requests or attempts are never invented by this bridge.
"""

from importlib import import_module
from typing import ClassVar

from django.db import migrations, models

FORWARD = r"""
CREATE FUNCTION collection_previous_dispatch_bridge() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE roles jsonb; metrics jsonb; limits jsonb; coordinate text; identifier text;
        candidate collection_jobs%ROWTYPE; previous collection_jobs%ROWTYPE;
BEGIN
    roles := COALESCE(NEW.metadata->'collection_role_authorities', '{}'::jsonb);
    metrics := COALESCE(NEW.metadata->'collection_job_authorities', '{}'::jsonb);
    IF jsonb_typeof(roles) <> 'object' OR jsonb_typeof(metrics) <> 'object' THEN
        RAISE EXCEPTION 'invalid previous collection authority map' USING ERRCODE='23514';
    END IF;

    FOR coordinate,identifier IN SELECT e.key,e.value FROM jsonb_each_text(roles) e
        WHERE e.value IS DISTINCT FROM OLD.metadata->'collection_role_authorities'->>e.key
    LOOP
        SELECT * INTO candidate FROM collection_jobs
        WHERE id=identifier::uuid AND source_id=NEW.id AND purpose='catalog' AND mode='recurring'
        FOR UPDATE NOWAIT;
        IF NOT FOUND OR candidate.instruction_version <> 1 OR candidate.owner_account_id IS NOT NULL
            OR candidate.definition#>>'{scope,routine_role}' IS DISTINCT FROM coordinate THEN
            RAISE EXCEPTION 'invalid previous collection role identity' USING ERRCODE='23514';
        END IF;
        IF candidate.state <> 'cancelled' THEN
            SELECT * INTO previous FROM collection_jobs
            WHERE source_id=NEW.id AND purpose='catalog' AND owner_account_id IS NULL
              AND routine_role=coordinate AND authority_enabled AND id<>candidate.id
            FOR UPDATE NOWAIT;
            IF FOUND THEN
                IF previous.state <> 'cancelled' THEN
                    RAISE EXCEPTION 'another job owns collection role dispatch' USING ERRCODE='23514';
                END IF;
                UPDATE collection_jobs SET authority_enabled=false WHERE id=previous.id;
            END IF;
        END IF;
        UPDATE collection_jobs SET routine_role=coordinate,
            authority_enabled=(candidate.state <> 'cancelled') WHERE id=candidate.id;
    END LOOP;
    FOR coordinate,identifier IN
        SELECT e.key,e.value FROM jsonb_each_text(
            COALESCE(OLD.metadata->'collection_role_authorities','{}'::jsonb)) e
        WHERE NOT roles ? e.key
    LOOP
        PERFORM 1 FROM collection_jobs WHERE id=identifier::uuid AND source_id=NEW.id
            AND instruction_version=1 AND purpose='catalog' AND owner_account_id IS NULL
            FOR UPDATE NOWAIT;
        UPDATE collection_jobs SET authority_enabled=false
        WHERE id=identifier::uuid AND source_id=NEW.id AND instruction_version=1
            AND purpose='catalog' AND owner_account_id IS NULL;
    END LOOP;

    FOR coordinate,identifier IN SELECT e.key,e.value FROM jsonb_each_text(metrics) e
        WHERE e.value IS DISTINCT FROM OLD.metadata->'collection_job_authorities'->>e.key
    LOOP
        SELECT * INTO candidate FROM collection_jobs
        WHERE id=identifier::uuid AND source_id=NEW.id AND purpose='metric'
            AND mode='recurring' AND contract_id=coordinate::uuid FOR UPDATE NOWAIT;
        IF NOT FOUND OR candidate.instruction_version <> 1 THEN
            RAISE EXCEPTION 'invalid previous collection metric identity' USING ERRCODE='23514';
        END IF;
        IF EXISTS (SELECT 1 FROM collection_jobs WHERE source_id=NEW.id
            AND purpose='metric' AND contract_id=candidate.contract_id
            AND authority_enabled AND id<>candidate.id) THEN
            RAISE EXCEPTION 'another job owns metric dispatch' USING ERRCODE='23514';
        END IF;
        UPDATE collection_jobs SET authority_enabled=true WHERE id=candidate.id;
    END LOOP;
    FOR coordinate,identifier IN
        SELECT e.key,e.value FROM jsonb_each_text(
            COALESCE(OLD.metadata->'collection_job_authorities','{}'::jsonb)) e
        WHERE NOT metrics ? e.key
    LOOP
        PERFORM 1 FROM collection_jobs WHERE id=identifier::uuid AND source_id=NEW.id
            AND instruction_version=1 AND purpose='metric' FOR UPDATE NOWAIT;
        UPDATE collection_jobs SET authority_enabled=false WHERE id=identifier::uuid
            AND source_id=NEW.id AND instruction_version=1 AND purpose='metric';
    END LOOP;

    IF NEW.metadata->'collection_role_dispatch_budget' IS DISTINCT FROM
       OLD.metadata->'collection_role_dispatch_budget' THEN
        IF NOT NEW.metadata ? 'collection_role_dispatch_budget' THEN
            NEW.dispatch_max_requests := 100;
            NEW.dispatch_max_bytes := 8388608;
            NEW.dispatch_max_seconds := 300;
        ELSE
            limits := NEW.metadata->'collection_role_dispatch_budget';
            IF jsonb_typeof(limits) <> 'object'
                OR NOT limits ?& ARRAY['requests','bytes','seconds']
                OR limits - ARRAY['requests','bytes','seconds'] <> '{}'::jsonb THEN
                RAISE EXCEPTION 'invalid previous source dispatch budget' USING ERRCODE='23514';
            END IF;
            FOR coordinate,identifier IN SELECT e.key,e.value FROM jsonb_each_text(limits) e
            LOOP
                IF identifier IS NULL OR identifier !~ '^[0-9]+$'
                    OR jsonb_typeof(limits->coordinate) <> 'number' THEN
                    RAISE EXCEPTION 'invalid previous source dispatch limit' USING ERRCODE='23514';
                END IF;
            END LOOP;
            NEW.dispatch_max_requests := (limits->>'requests')::integer;
            NEW.dispatch_max_bytes := (limits->>'bytes')::bigint;
            NEW.dispatch_max_seconds := (limits->>'seconds')::integer;
        END IF;
    ELSIF ROW(NEW.dispatch_max_requests,NEW.dispatch_max_bytes,NEW.dispatch_max_seconds)
        IS DISTINCT FROM ROW(OLD.dispatch_max_requests,OLD.dispatch_max_bytes,OLD.dispatch_max_seconds) THEN
        NEW.metadata := jsonb_set(NEW.metadata,'{collection_role_dispatch_budget}',
            jsonb_build_object('requests',NEW.dispatch_max_requests,
                'bytes',NEW.dispatch_max_bytes,'seconds',NEW.dispatch_max_seconds));
    END IF;
    IF NOT (NEW.dispatch_max_requests BETWEEN 1 AND 10000
        AND NEW.dispatch_max_bytes BETWEEN 1 AND 33554432
        AND NEW.dispatch_max_seconds BETWEEN 1 AND 3600) THEN
        RAISE EXCEPTION 'source dispatch limits exceed existing policy' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER collection_previous_dispatch_bridge BEFORE UPDATE ON data_sources
FOR EACH ROW EXECUTE FUNCTION collection_previous_dispatch_bridge();
"""

REVERSE = """
DROP TRIGGER collection_previous_dispatch_bridge ON data_sources;
DROP FUNCTION collection_previous_dispatch_bridge();
"""


def reconcile_previous_writes(apps, schema_editor):
    # Installing the trigger first closes the copy/window race. Each source lock
    # fences legacy authority writers while its latest map is copied.
    Source = apps.get_model("core", "DataSource")
    alias = schema_editor.connection.alias
    list(Source.objects.using(alias).select_for_update().order_by("pk"))
    import_module("core.migrations.0106_collection_schedule_data").forward(
        apps, schema_editor
    )


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [("core", "0112_collection_publication_options")]
    operations: ClassVar[list] = [
        migrations.RunSQL("SET LOCAL lock_timeout = '5s'", migrations.RunSQL.noop),
        migrations.RunSQL(FORWARD, REVERSE),
        migrations.RunPython(reconcile_previous_writes, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="datasource",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    dispatch_max_requests__gte=1, dispatch_max_requests__lte=10000,
                    dispatch_max_bytes__gte=1, dispatch_max_bytes__lte=33554432,
                    dispatch_max_seconds__gte=1, dispatch_max_seconds__lte=3600,
                ),
                name="ck_source_dispatch_limits",
            ),
        ),
    ]
