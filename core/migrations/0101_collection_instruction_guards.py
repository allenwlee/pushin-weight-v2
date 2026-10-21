"""Seal typed job settings/membership and validate the narrowed instruction JSON.

The option grammar is frozen at this migration boundary. Future grammar changes
need a versioned migration and the matching runtime validator.
"""

from typing import ClassVar

from django.db import migrations

OPTION_TYPES = {
    "model_inventory": {
        "ingest_metadata": "boolean",
        "watch_inventory": "boolean",
        "inventory_version": "string",
        "recheck_days": "number",
        "projection_policy": "string",
    },
    "model_history": {
        "cutoff": "string",
        "global_start_at": "string",
        "cap_per_brand": "number",
        "qualification_policy": "string",
        "window_policy": "string",
        "arena_config": "string",
        "arena_publication_mode": "string",
    },
    "github_catalog": {"github_role": "string"},
    "hf_catalog": {"rules_version": "string"},
    "collect_metrics": {},
    "match_crosswalk": {
        "ruleset": "string",
        "preview_sha256": "string",
        "reviewed_by": "string",
        "review_basis": "string",
        "cutoff": "string",
    },
    "x_cycle": {"adapter": "string", "credential_purpose": "string"},
    "x_backfill": {
        "adapter": "string",
        "credential_purpose": "string",
        "config_digest": "string",
        "policy_sha256": "string",
        "maximum_api_requests": "number",
        "maximum_model_requests": "number",
        "model_requests_per_run": "number",
        "deadline": "string",
    },
}


def grammar():
    import json

    return json.dumps(OPTION_TYPES, separators=(",", ":")).replace("'", "''")


GUARDS = """
CREATE FUNCTION collection_typed_instruction_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE grammar jsonb := 'GRAMMAR'::jsonb; rules jsonb; option record;
BEGIN
    IF TG_OP='UPDATE' AND OLD.instructions_sealed_at IS NOT NULL
       AND (to_jsonb(NEW)-ARRAY['state','next_due_at','next_retry_at','active_run_id','last_attempt_id','last_attempt_attempt_id','last_success_id','updated_at','authority_enabled'])
       IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['state','next_due_at','next_retry_at','active_run_id','last_attempt_id','last_attempt_attempt_id','last_success_id','updated_at','authority_enabled']) THEN
        RAISE EXCEPTION 'collection relational instructions are sealed' USING ERRCODE='23514';
    END IF;
    IF NEW.definition->'version'='2'::jsonb AND NEW.instruction_version<>2 THEN
        RAISE EXCEPTION 'instruction representation version mismatch' USING ERRCODE='23514';
    END IF;
    IF NEW.instruction_version=2 THEN
        IF NEW.definition->>'version' IS DISTINCT FROM '2'
           OR jsonb_typeof(NEW.definition->'options') IS DISTINCT FROM 'object'
           OR (NEW.definition-ARRAY['version','options']) <> '{}'::jsonb THEN
            RAISE EXCEPTION 'strict instruction version 2 required' USING ERRCODE='23514';
        END IF;
        rules := grammar->NEW.operation;
        IF rules IS NULL THEN
            RAISE EXCEPTION 'unsupported instruction operation' USING ERRCODE='23514';
        END IF;
        FOR option IN SELECT key,value FROM jsonb_each(NEW.definition->'options') LOOP
            IF rules->>option.key IS DISTINCT FROM jsonb_typeof(option.value) THEN
                RAISE EXCEPTION 'unknown or mistyped instruction option' USING ERRCODE='23514';
            END IF;
            IF jsonb_typeof(option.value)='number' AND (
                (option.value::text)::numeric <= 0 OR (option.value::text)::numeric > 1000000
                OR (option.value::text)::numeric <> trunc((option.value::text)::numeric)
            ) THEN
                RAISE EXCEPTION 'instruction option out of range' USING ERRCODE='23514';
            END IF;
            IF jsonb_typeof(option.value)='string' AND (
                length(option.value#>>'{}')=0 OR length(option.value#>>'{}')>1024
                OR (option.value#>>'{}') ~ '[[:cntrl:]]'
            ) THEN
                RAISE EXCEPTION 'invalid instruction option string' USING ERRCODE='23514';
            END IF;
        END LOOP;
        IF NEW.owner_kind NOT IN ('account','source')
           OR (NEW.owner_kind='account') IS DISTINCT FROM (NEW.owner_account_id IS NOT NULL)
           OR NEW.max_requests IS NULL OR NEW.max_requests NOT BETWEEN 1 AND 10000
           OR NEW.max_bytes IS NULL OR NEW.max_bytes NOT BETWEEN 1 AND 33554432
           OR NEW.max_seconds IS NULL OR NEW.max_seconds NOT BETWEEN 1 AND 3600
           OR NEW.max_items IS NULL OR NEW.max_items NOT BETWEEN 1 AND 100000 THEN
            RAISE EXCEPTION 'typed ownership and finite budgets required' USING ERRCODE='23514';
        END IF;
        IF NEW.source_id IN ('hf','github','x') AND NEW.owner_account_id IS NOT NULL
            AND NOT EXISTS (SELECT 1 FROM accounts a WHERE a.account_key=NEW.owner_account_id AND a.data_source_id=NEW.source_id) THEN
            RAISE EXCEPTION 'native collector owner source mismatch' USING ERRCODE='23514';
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER collection_typed_instruction_guard BEFORE INSERT OR UPDATE ON collection_jobs
FOR EACH ROW EXECUTE FUNCTION collection_typed_instruction_guard();

CREATE OR REPLACE FUNCTION collection_run_job_instructions() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE instructions record;
BEGIN
    SELECT purpose,contract_id,instruction_version,definition->'scope' AS scope INTO instructions
        FROM collection_jobs WHERE id=NEW.job_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'collection run requires an existing job' USING ERRCODE='23503';
    END IF;
    IF NOT (
        (instructions.purpose='metric' AND instructions.contract_id IS NOT NULL AND NEW.lease_expires_at IS NOT NULL
         AND ((NEW.status='running' AND NEW.completed_at IS NULL) OR (NEW.status IN ('success','partial','failed','aborted') AND NEW.completed_at IS NOT NULL)))
        OR (instructions.purpose='catalog' AND instructions.contract_id IS NULL
         AND ((NEW.status IN ('pending','running','partial','interrupted') AND NEW.completed_at IS NULL) OR (NEW.status IN ('success','failed','aborted') AND NEW.completed_at IS NOT NULL)))
        OR (instructions.purpose='content' AND instructions.contract_id IS NULL
         AND ((NEW.status='running' AND NEW.completed_at IS NULL) OR (NEW.status IN ('success','partial','failed','aborted') AND NEW.completed_at IS NOT NULL)))
    ) THEN
        RAISE EXCEPTION 'collection run lifecycle mismatch' USING ERRCODE='23514';
    END IF;
    IF instructions.instruction_version=1 AND instructions.scope IS NULL THEN
        RAISE EXCEPTION 'collection job scope must be present' USING ERRCODE='23502';
    END IF;
    RETURN NEW;
END $$;

CREATE FUNCTION collection_target_seal_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE target_job_id uuid;
BEGIN
    IF TG_OP<>'INSERT' THEN
        target_job_id := OLD.job_id;
        PERFORM 1 FROM collection_jobs WHERE id=target_job_id FOR UPDATE;
        IF EXISTS(SELECT 1 FROM collection_jobs WHERE id=target_job_id AND instructions_sealed_at IS NOT NULL) THEN
            RAISE EXCEPTION 'collection target membership is sealed' USING ERRCODE='23514';
        END IF;
    END IF;
    IF TG_OP<>'DELETE' THEN
        PERFORM 1 FROM collection_jobs WHERE id=NEW.job_id FOR UPDATE;
        IF EXISTS(SELECT 1 FROM collection_jobs WHERE id=NEW.job_id AND instructions_sealed_at IS NOT NULL) THEN
            RAISE EXCEPTION 'collection target membership is sealed' USING ERRCODE='23514';
        END IF;
        IF NEW.mapping_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM source_subject_mappings m WHERE m.id=NEW.mapping_id AND m.subject_id=NEW.subject_id
        ) THEN
            RAISE EXCEPTION 'job target mapping subject mismatch' USING ERRCODE='23514';
        END IF;
        RETURN NEW;
    END IF;
    RETURN OLD;
END $$;
CREATE TRIGGER collection_target_seal_guard BEFORE INSERT OR UPDATE OR DELETE
ON collection_job_targets FOR EACH ROW EXECUTE FUNCTION collection_target_seal_guard();

CREATE FUNCTION collection_campaign_seal_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'collection campaign instructions are immutable' USING ERRCODE='23514';
END $$;
CREATE TRIGGER collection_campaign_seal_guard BEFORE UPDATE OR DELETE ON collection_campaigns
FOR EACH ROW EXECUTE FUNCTION collection_campaign_seal_guard();
""".replace("GRAMMAR", grammar())

REVERSE = """
DROP TRIGGER collection_campaign_seal_guard ON collection_campaigns;
DROP FUNCTION collection_campaign_seal_guard();
DROP TRIGGER collection_target_seal_guard ON collection_job_targets;
DROP FUNCTION collection_target_seal_guard();
DROP TRIGGER collection_typed_instruction_guard ON collection_jobs;
DROP FUNCTION collection_typed_instruction_guard();
"""


from importlib import import_module

REVERSE += import_module(
    "core.migrations.0090_remove_run_instruction_columns"
).RUN_GUARD


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [("core", "0100_collection_capture_guards")]
    operations: ClassVar[list] = [
        migrations.RunSQL("SET LOCAL lock_timeout = '5s'", migrations.RunSQL.noop),
        migrations.RunSQL(GUARDS, REVERSE),
    ]
