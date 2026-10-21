"""Protect immutable source evidence and cross-table collection membership."""

from typing import ClassVar

from django.db import migrations

GUARDS = """
CREATE FUNCTION collection_archive_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'collection evidence archive is immutable' USING ERRCODE='23514';
    END IF;
    IF NEW.byte_count <> octet_length(NEW.body)
       OR NEW.content_sha256 <> encode(sha256(NEW.body), 'hex') THEN
        RAISE EXCEPTION 'collection evidence checksum mismatch' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER collection_archive_guard BEFORE INSERT OR UPDATE OR DELETE
ON collection_evidence_archives FOR EACH ROW EXECUTE FUNCTION collection_archive_guard();

CREATE FUNCTION collection_request_membership() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE attempt_run uuid; scope_run uuid;
BEGIN
    SELECT run_id INTO attempt_run FROM collection_attempts WHERE id=NEW.attempt_id;
    SELECT run_id INTO scope_run FROM collection_scope_runs WHERE id=NEW.scope_run_id;
    IF attempt_run IS NULL OR scope_run IS NULL OR attempt_run <> scope_run THEN
        RAISE EXCEPTION 'request attempt and scope require the same run' USING ERRCODE='23514';
    END IF;
    IF TG_OP='UPDATE' AND ROW(NEW.attempt_id,NEW.scope_run_id,NEW.ordinal)
        IS DISTINCT FROM ROW(OLD.attempt_id,OLD.scope_run_id,OLD.ordinal) THEN
        RAISE EXCEPTION 'request execution identity is immutable' USING ERRCODE='23514';
    END IF;
    IF NEW.endpoint_url ~* '(://[^/]*@|[?&](api_key|apikey|access_token|token|password|secret|key|authorization)=)' THEN
        RAISE EXCEPTION 'credential-bearing endpoint is prohibited' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER collection_request_membership BEFORE INSERT OR UPDATE ON collection_requests
FOR EACH ROW EXECUTE FUNCTION collection_request_membership();

CREATE FUNCTION collection_input_membership() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE output_run uuid; request_run uuid;
BEGIN
    IF NEW.input_request_id IS NOT NULL THEN
        SELECT run_id INTO output_run FROM collection_observations WHERE id=NEW.observation_id;
        SELECT a.run_id INTO request_run FROM collection_requests q
            JOIN collection_attempts a ON a.id=q.attempt_id WHERE q.id=NEW.input_request_id;
        IF output_run IS NULL OR request_run IS NULL OR output_run <> request_run THEN
            RAISE EXCEPTION 'request input and observation require the same run' USING ERRCODE='23514';
        END IF;
    ELSE
        -- Serialize edge changes so concurrent opposite edges cannot both pass.
        PERFORM pg_advisory_xact_lock(1194544221);
        IF EXISTS (
            WITH RECURSIVE ancestors(id) AS (
                SELECT NEW.input_observation_id
                UNION
                SELECT i.input_observation_id FROM collection_observation_inputs i
                JOIN ancestors a ON i.observation_id=a.id
                WHERE i.input_observation_id IS NOT NULL
            ) SELECT 1 FROM ancestors WHERE id=NEW.observation_id
        ) THEN
            RAISE EXCEPTION 'cyclic observation input is prohibited' USING ERRCODE='23514';
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER collection_input_membership BEFORE INSERT OR UPDATE ON collection_observation_inputs
FOR EACH ROW EXECUTE FUNCTION collection_input_membership();

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

REVERSE = """
DROP TRIGGER collection_correction_guard ON collection_corrections;
DROP FUNCTION collection_correction_guard();
DROP TRIGGER collection_input_membership ON collection_observation_inputs;
DROP FUNCTION collection_input_membership();
DROP TRIGGER collection_request_membership ON collection_requests;
DROP FUNCTION collection_request_membership();
DROP TRIGGER collection_archive_guard ON collection_evidence_archives;
DROP FUNCTION collection_archive_guard();
"""


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [("core", "0099_collection_typed_owners")]
    operations: ClassVar[list] = [
        migrations.RunSQL("SET LOCAL lock_timeout = '5s'", migrations.RunSQL.noop),
        migrations.RunSQL(GUARDS, REVERSE),
    ]
