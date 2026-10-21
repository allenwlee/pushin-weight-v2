"""Stop new application code writing legacy timezone strings.

The old physical columns stay temporarily for old application instances during
the rolling deploy. New code uses the references only; old code may still write
the strings and have the trigger resolve them to the reference.
"""

from typing import ClassVar

from django.db import migrations

FORWARD_SQL = """
ALTER TABLE metrics DROP CONSTRAINT ck_metric_source_timezone_ref;
ALTER TABLE events DROP CONSTRAINT ck_events_source_timezone_ref;
ALTER TABLE opportunities DROP CONSTRAINT ck_opportunities_source_timezone_ref;
ALTER TABLE metrics ALTER COLUMN source_timezone DROP NOT NULL;

CREATE OR REPLACE FUNCTION sync_metric_source_timezone() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE resolved_code varchar(64); legacy_changed boolean; reference_changed boolean;
BEGIN
    SELECT code INTO resolved_code FROM time_zones WHERE code=NEW.source_timezone;
    IF TG_OP='INSERT' THEN
        IF NEW.source_timezone_id IS NULL THEN
            NEW.source_timezone_id := resolved_code;
        ELSIF resolved_code IS NOT NULL
              AND resolved_code IS DISTINCT FROM NEW.source_timezone_id
              AND NEW.source_timezone IS DISTINCT FROM 'unknown' THEN
            RAISE EXCEPTION 'metric timezone reference differs from reported timezone'
                USING ERRCODE='23514';
        END IF;
        RETURN NEW;
    END IF;
    legacy_changed := NEW.source_timezone IS DISTINCT FROM OLD.source_timezone;
    reference_changed := NEW.source_timezone_id IS DISTINCT FROM OLD.source_timezone_id;
    IF legacy_changed AND NOT reference_changed THEN
        NEW.source_timezone_id := resolved_code;
    ELSIF legacy_changed AND reference_changed
          AND resolved_code IS NOT NULL
          AND resolved_code IS DISTINCT FROM NEW.source_timezone_id
          AND NEW.source_timezone IS DISTINCT FROM 'unknown' THEN
        RAISE EXCEPTION 'metric timezone reference differs from reported timezone'
            USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION sync_intelligence_source_timezone() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE resolved_code varchar(64); legacy_changed boolean; reference_changed boolean;
BEGIN
    SELECT code INTO resolved_code FROM time_zones WHERE code=NEW.source_timezone;
    IF TG_OP='INSERT' THEN
        IF NEW.source_timezone_id IS NULL THEN
            NEW.source_timezone_id := resolved_code;
        ELSIF resolved_code IS NOT NULL
              AND resolved_code IS DISTINCT FROM NEW.source_timezone_id
              AND NEW.source_timezone IS DISTINCT FROM 'unknown' THEN
            RAISE EXCEPTION 'source timezone reference differs from reported timezone'
                USING ERRCODE='23514';
        END IF;
        RETURN NEW;
    END IF;
    legacy_changed := NEW.source_timezone IS DISTINCT FROM OLD.source_timezone;
    reference_changed := NEW.source_timezone_id IS DISTINCT FROM OLD.source_timezone_id;
    IF legacy_changed AND NOT reference_changed THEN
        NEW.source_timezone_id := resolved_code;
    ELSIF legacy_changed AND reference_changed
          AND resolved_code IS NOT NULL
          AND resolved_code IS DISTINCT FROM NEW.source_timezone_id
          AND NEW.source_timezone IS DISTINCT FROM 'unknown' THEN
        RAISE EXCEPTION 'source timezone reference differs from reported timezone'
            USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
"""


REVERSE_SQL = """
UPDATE metrics
SET source_timezone=COALESCE(source_timezone_id, 'unknown');
UPDATE events
SET source_timezone=COALESCE(source_timezone_id, raw_payload->>'source_timezone');
UPDATE opportunities
SET source_timezone=COALESCE(source_timezone_id, raw_payload->>'source_timezone');
ALTER TABLE metrics ALTER COLUMN source_timezone SET NOT NULL;

ALTER TABLE metrics ADD CONSTRAINT ck_metric_source_timezone_ref
    CHECK (source_timezone_id IS NULL OR source_timezone_id=source_timezone);
ALTER TABLE events ADD CONSTRAINT ck_events_source_timezone_ref
    CHECK (source_timezone_id IS NULL OR (source_timezone IS NOT NULL AND source_timezone_id=source_timezone));
ALTER TABLE opportunities ADD CONSTRAINT ck_opportunities_source_timezone_ref
    CHECK (source_timezone_id IS NULL OR (source_timezone IS NOT NULL AND source_timezone_id=source_timezone));

CREATE OR REPLACE FUNCTION sync_metric_source_timezone() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE resolved_code varchar(64);
BEGIN
    SELECT code INTO resolved_code FROM time_zones WHERE code=NEW.source_timezone;
    IF TG_OP='UPDATE' AND NEW.source_timezone IS DISTINCT FROM OLD.source_timezone
       AND NEW.source_timezone_id IS NOT DISTINCT FROM OLD.source_timezone_id THEN
        NEW.source_timezone_id := resolved_code;
    ELSIF NEW.source_timezone_id IS NULL THEN
        NEW.source_timezone_id := resolved_code;
    ELSIF NEW.source_timezone_id IS DISTINCT FROM resolved_code THEN
        RAISE EXCEPTION 'metric timezone reference differs from reported timezone'
            USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION sync_intelligence_source_timezone() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE resolved_code varchar(64);
BEGIN
    SELECT code INTO resolved_code FROM time_zones WHERE code=NEW.source_timezone;
    IF TG_OP='UPDATE' AND NEW.source_timezone IS DISTINCT FROM OLD.source_timezone
       AND NEW.source_timezone_id IS NOT DISTINCT FROM OLD.source_timezone_id THEN
        NEW.source_timezone_id := resolved_code;
    ELSIF NEW.source_timezone_id IS NULL THEN
        NEW.source_timezone_id := resolved_code;
    ELSIF NEW.source_timezone_id IS DISTINCT FROM resolved_code THEN
        RAISE EXCEPTION 'source timezone reference differs from reported timezone'
            USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
"""


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [
        ("core", "0120_merge_homepage_shared_vocabulary"),
    ]

    operations: ClassVar[list] = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    "SET LOCAL lock_timeout='5s'", migrations.RunSQL.noop
                ),
                migrations.RunSQL(FORWARD_SQL, REVERSE_SQL),
            ],
            state_operations=[
                migrations.RemoveConstraint(
                    model_name="event", name="ck_events_source_timezone_ref"
                ),
                migrations.RemoveConstraint(
                    model_name="opportunity",
                    name="ck_opportunities_source_timezone_ref",
                ),
                migrations.RemoveConstraint(
                    model_name="sourcemetric", name="ck_metric_source_timezone_ref"
                ),
                migrations.RemoveField(model_name="event", name="source_timezone"),
                migrations.RemoveField(
                    model_name="opportunity", name="source_timezone"
                ),
                migrations.RemoveField(
                    model_name="sourcemetric", name="source_timezone"
                ),
            ],
        ),
    ]
