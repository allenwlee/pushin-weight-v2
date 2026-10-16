"""Jobs own instructions; retain physical copies for the serving 0088 reader.

The later physical-drop release must first replace the compatibility trigger.
This migration is forward-only: reversing state would require a separate,
explicit compatibility release.
"""

from importlib import import_module
from typing import ClassVar

import django.db.models.deletion
from django.db import migrations, models


def normalize_all_runs(apps, schema_editor):
    import_module(
        "core.migrations.0088_archive_run_instructions"
    ).archive_run_instructions(apps, schema_editor)
    Run = apps.get_model("core", "CollectionRun")
    if (
        Run.objects.using(schema_editor.connection.alias)
        .filter(job__isnull=True)
        .exists()
    ):
        raise ValueError("collection runs still lack jobs")


JOB_GUARD = """
CREATE FUNCTION collection_job_immutable_instructions() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF ROW(NEW.id, NEW.source_id, NEW.purpose, NEW.contract_id, NEW.operation,
           NEW.mode, NEW.job_key, NEW.definition, NEW.definition_sha256)
       IS DISTINCT FROM
       ROW(OLD.id, OLD.source_id, OLD.purpose, OLD.contract_id, OLD.operation,
           OLD.mode, OLD.job_key, OLD.definition, OLD.definition_sha256) THEN
        RAISE EXCEPTION 'collection job instructions are immutable'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER collection_job_immutable_instructions
BEFORE UPDATE ON collection_jobs FOR EACH ROW
EXECUTE FUNCTION collection_job_immutable_instructions();
"""

RUN_GUARD = """
CREATE FUNCTION collection_run_job_instructions() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE instructions record;
BEGIN
    -- No row lock: instructions cannot change, including before first use.
    -- Shared writers hold job then run; acquiring a job lock here would invert
    -- that order for a previous-revision UPDATE of an already-locked run.
    SELECT source_id, purpose, contract_id, definition->'scope' AS scope
      INTO instructions FROM collection_jobs WHERE id = NEW.job_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'collection run requires an existing job'
            USING ERRCODE = '23503';
    END IF;
    IF TG_OP = 'UPDATE' AND (
        (NEW.source_id IS DISTINCT FROM OLD.source_id
            AND NEW.source_id IS DISTINCT FROM instructions.source_id)
        OR (NEW.purpose IS DISTINCT FROM OLD.purpose
            AND NEW.purpose IS DISTINCT FROM instructions.purpose)
        OR (NEW.contract_id IS DISTINCT FROM OLD.contract_id
            AND NEW.contract_id IS DISTINCT FROM instructions.contract_id)
        OR (NEW.scope IS DISTINCT FROM OLD.scope
            AND NEW.scope IS DISTINCT FROM instructions.scope)
    ) THEN
        RAISE EXCEPTION 'collection run instruction copy mismatch'
            USING ERRCODE = '23514';
    END IF;
    IF (
        (instructions.purpose = 'metric' AND instructions.contract_id IS NOT NULL
            AND NEW.lease_expires_at IS NOT NULL AND (
                (NEW.status = 'running' AND NEW.completed_at IS NULL)
                OR (NEW.status IN ('success', 'partial', 'failed', 'aborted')
                    AND NEW.completed_at IS NOT NULL)))
        OR (instructions.purpose = 'catalog' AND instructions.contract_id IS NULL AND (
                (NEW.status IN ('pending', 'running', 'partial', 'interrupted')
                    AND NEW.completed_at IS NULL)
                OR (NEW.status IN ('success', 'failed', 'aborted')
                    AND NEW.completed_at IS NOT NULL)))
        OR (instructions.purpose = 'content' AND instructions.contract_id IS NULL AND (
                (NEW.status = 'running' AND NEW.completed_at IS NULL)
                OR (NEW.status IN ('success', 'partial', 'failed', 'aborted')
                    AND NEW.completed_at IS NOT NULL)))
    ) IS NOT TRUE THEN
        RAISE EXCEPTION 'collection run lifecycle mismatch'
            USING ERRCODE = '23514';
    END IF;
    NEW.source_id := instructions.source_id;
    NEW.purpose := instructions.purpose;
    NEW.contract_id := instructions.contract_id;
    NEW.scope := instructions.scope;
    RETURN NEW;
END $$;
CREATE TRIGGER collection_run_job_instructions
BEFORE INSERT OR UPDATE ON collection_runs FOR EACH ROW
EXECUTE FUNCTION collection_run_job_instructions();
"""

VIEWS = """
CREATE OR REPLACE VIEW metric_collection_runs AS
SELECT r.id, r.batch_id, r.ingestion_key, r.status, r.started_at,
       r.lease_expires_at, r.observed_at, r.completed_at, r.source_as_of,
       r.source_url, r.request_params, r.source_metadata, r.request_count,
       r.selected_count, r.success_count, r.payload_sha256, r.raw_payload,
       r.error_code,
       (SELECT j.contract_id FROM collection_jobs j WHERE j.id = r.job_id) AS contract_id,
       (SELECT j.source_id FROM collection_jobs j WHERE j.id = r.job_id) AS source_id,
       (SELECT j.purpose FROM collection_jobs j WHERE j.id = r.job_id) AS purpose,
       (SELECT j.definition->'scope' FROM collection_jobs j WHERE j.id = r.job_id) AS scope,
       r.invocations, r.report, r.updated_at
  FROM collection_runs r
 WHERE (SELECT j.purpose FROM collection_jobs j WHERE j.id = r.job_id) = 'metric'
 WITH LOCAL CHECK OPTION;
CREATE OR REPLACE VIEW metric_observations AS
SELECT o.* FROM collection_observations o
 WHERE o.run_id IN (
     SELECT r.id FROM collection_runs r
     WHERE (SELECT j.purpose FROM collection_jobs j WHERE j.id = r.job_id) = 'metric'
 ) WITH LOCAL CHECK OPTION;
"""


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [("core", "0088_archive_run_instructions")]
    operations: ClassVar[list] = [
        migrations.RunSQL("SET LOCAL lock_timeout = '5s'"),
        migrations.RunPython(normalize_all_runs),
        # Catch-up updates deferred job FKs; drain their events before ALTER.
        migrations.RunSQL("SET CONSTRAINTS ALL IMMEDIATE"),
        migrations.RemoveIndex("collectionrun", "idx_metric_run_outcome"),
        migrations.RemoveConstraint("collectionrun", "ck_collection_run_lifecycle"),
        migrations.RunSQL(JOB_GUARD + RUN_GUARD + VIEWS),
        migrations.AlterField(
            "collectionrun",
            "job",
            models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="runs",
                to="core.collectionjob",
            ),
        ),
        migrations.AddIndex(
            "collectionrun",
            models.Index(
                fields=["job", "status", "completed_at"], name="idx_metric_run_outcome"
            ),
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField("collectionrun", "source"),
                migrations.RemoveField("collectionrun", "purpose"),
                migrations.RemoveField("collectionrun", "contract"),
                migrations.RemoveField("collectionrun", "scope"),
            ]
        ),
    ]
