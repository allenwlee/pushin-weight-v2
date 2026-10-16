"""Remove only physical instruction copies after the ORM-free bridge rollout.

Keep the job-backed lifecycle and the old scope SQL-NULL rejection. The
preceding ORM-free application can keep serving this schema; restoring an
older ORM revision would require a separate compatibility release.
"""

from typing import ClassVar

from django.db import migrations

RUN_GUARD = """
CREATE OR REPLACE FUNCTION collection_run_job_instructions() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE instructions record;
BEGIN
    -- Immutable instructions need no job-row lock during a run update.
    SELECT purpose, contract_id, definition->'scope' AS scope
      INTO instructions FROM collection_jobs WHERE id = NEW.job_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'collection run requires an existing job'
            USING ERRCODE = '23503';
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
    -- The former physical JSONB copy rejected SQL NULL. JSON null is a
    -- present value and remains allowed, with no additional JSON shape rule.
    IF instructions.scope IS NULL THEN
        RAISE EXCEPTION 'collection job scope must be present'
            USING ERRCODE = '23502';
    END IF;
    RETURN NEW;
END $$;
"""

DROP_COPIES = """
ALTER TABLE collection_runs
    DROP COLUMN source_id,
    DROP COLUMN purpose,
    DROP COLUMN contract_id,
    DROP COLUMN scope;
"""


class Migration(migrations.Migration):
    atomic = True
    dependencies: ClassVar[list] = [("core", "0089_job_owned_run_instructions")]
    operations: ClassVar[list] = [
        migrations.RunSQL("SET LOCAL lock_timeout = '5s'"),
        migrations.RunSQL(RUN_GUARD + DROP_COPIES),
    ]
