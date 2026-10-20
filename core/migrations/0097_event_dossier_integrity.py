"""Protect completed dossiers even when a caller bypasses the service/ORM.

Reviews are assembled before their current pointer is published, within one
transaction. Deferred checks require a complete, selected revision at commit.
Once selected (or superseded), neither its rows nor its claim membership can
change. All locks are on dossier rows; shared collection tables are untouched.
"""

from django.db import migrations

# Django migration classes intentionally expose mutable dependency/operation lists.
# ruff: noqa: RUF012

FORWARD = r"""
CREATE FUNCTION ed_frozen_v1() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Dossier evidence and completed review history are immutable'
        USING ERRCODE = '23514';
END $$;

CREATE FUNCTION ed_source_v1() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE captured_post text;
BEGIN
    PERFORM 1 FROM event_dossiers WHERE id = NEW.event_dossier_id FOR UPDATE;
    IF NEW.collection_observation_id IS NOT NULL THEN
        SELECT post_id INTO captured_post FROM collection_observations
            WHERE id = NEW.collection_observation_id;
        IF captured_post IS NOT NULL THEN
            IF NEW.post_id IS NOT NULL THEN
                RAISE EXCEPTION 'Supply only one dossier source' USING ERRCODE = '23514';
            END IF;
            NEW.post_id := captured_post;
            NEW.collection_observation_id := NULL;
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER ed_source_canonical BEFORE INSERT ON event_dossier_sources
    FOR EACH ROW EXECUTE FUNCTION ed_source_v1();

CREATE FUNCTION ed_child_v1() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE owner_id uuid; current_id uuid;
BEGIN
    SELECT event_dossier_id INTO owner_id FROM event_dossier_reviews WHERE id = NEW.review_id;
    IF owner_id IS NULL THEN
        RAISE EXCEPTION 'Create the review before assembling its detail/claims' USING ERRCODE = '23514';
    END IF;
    SELECT current_review_id INTO current_id FROM event_dossiers WHERE id = owner_id FOR UPDATE;
    IF current_id = NEW.review_id OR EXISTS (
        SELECT 1 FROM event_dossier_reviews WHERE supersedes_id = NEW.review_id
    ) THEN
        RAISE EXCEPTION 'Cannot add inputs to a completed dossier review' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;

CREATE FUNCTION ed_validate_review_v1(review_key uuid) RETURNS void LANGUAGE plpgsql AS $$
DECLARE r event_dossier_reviews%ROWTYPE; kind text; previous event_dossier_reviews%ROWTYPE;
BEGIN
    IF review_key IS NULL THEN RETURN; END IF;
    SELECT * INTO r FROM event_dossier_reviews WHERE id = review_key;
    IF NOT FOUND THEN RETURN; END IF; -- ordinary FK validates missing rows
    SELECT event_kind INTO kind FROM event_dossiers WHERE id = r.event_dossier_id;
    IF r.supersedes_id IS NOT NULL THEN
        SELECT * INTO previous FROM event_dossier_reviews WHERE id = r.supersedes_id;
        IF previous.id IS NULL OR previous.event_dossier_id <> r.event_dossier_id
           OR previous.revision + 1 <> r.revision
           OR previous.evidence_cutoff_at > r.evidence_cutoff_at THEN
            RAISE EXCEPTION 'Invalid dossier review predecessor/cutoff' USING ERRCODE = '23514';
        END IF;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM event_dossier_review_claims WHERE review_id = r.id)
       OR EXISTS (
           SELECT 1 FROM event_dossier_review_claims rc
           JOIN event_dossier_claims c ON c.id = rc.claim_id
           JOIN event_dossier_sources s ON s.id = c.event_dossier_source_id
           WHERE rc.review_id = r.id AND (
               s.event_dossier_id <> r.event_dossier_id
               OR c.recorded_at > r.evidence_cutoff_at OR s.linked_at > r.evidence_cutoff_at
           )
       ) THEN
        RAISE EXCEPTION 'Review requires same-dossier claims known by its cutoff' USING ERRCODE = '23514';
    END IF;
    IF (kind = 'model_release' AND (
            NOT EXISTS (SELECT 1 FROM model_release_details WHERE review_id = r.id)
            OR EXISTS (SELECT 1 FROM personnel_change_details WHERE review_id = r.id)))
       OR (kind = 'personnel_change' AND (
            NOT EXISTS (SELECT 1 FROM personnel_change_details WHERE review_id = r.id)
            OR EXISTS (SELECT 1 FROM model_release_details WHERE review_id = r.id))) THEN
        RAISE EXCEPTION 'Review needs exactly its matching typed detail' USING ERRCODE = '23514';
    END IF;
    IF EXISTS (
        SELECT 1 FROM personnel_change_details d
        LEFT JOIN people_brand_affiliations a ON a.id = d.from_affiliation_id
        LEFT JOIN people_brand_affiliations b ON b.id = d.to_affiliation_id
        WHERE d.review_id = r.id AND (
            (a.id IS NOT NULL AND a.person_id IS DISTINCT FROM d.person_id)
            OR (b.id IS NOT NULL AND b.person_id IS DISTINCT FROM d.person_id)
        )
    ) THEN
        RAISE EXCEPTION 'Personnel roles must belong to the same person' USING ERRCODE = '23514';
    END IF;
END $$;

CREATE FUNCTION ed_complete_v1() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE owner_id uuid; selected uuid; latest uuid;
BEGIN
    IF TG_TABLE_NAME = 'event_dossiers' THEN owner_id := NEW.id;
    ELSE owner_id := NEW.event_dossier_id;
    END IF;
    SELECT current_review_id INTO selected FROM event_dossiers WHERE id = owner_id FOR UPDATE;
    SELECT id INTO latest FROM event_dossier_reviews WHERE event_dossier_id = owner_id
        ORDER BY revision DESC LIMIT 1;
    IF selected IS DISTINCT FROM latest THEN
        RAISE EXCEPTION 'Current dossier review must select its latest own revision' USING ERRCODE = '23514';
    END IF;
    PERFORM ed_validate_review_v1(selected);
    IF TG_TABLE_NAME = 'event_dossier_reviews' THEN
        PERFORM ed_validate_review_v1(NEW.id);
    END IF;
    RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER ed_dossier_complete AFTER INSERT OR UPDATE ON event_dossiers
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ed_complete_v1();
CREATE CONSTRAINT TRIGGER ed_review_complete AFTER INSERT ON event_dossier_reviews
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ed_complete_v1();

CREATE FUNCTION ed_identity_v1() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE target event_dossier_reviews%ROWTYPE; previous_revision integer;
BEGIN
    IF (NEW.id, NEW.event_kind, NEW.identity_key, NEW.first_seen_at, NEW.created_at)
        IS DISTINCT FROM (OLD.id, OLD.event_kind, OLD.identity_key, OLD.first_seen_at, OLD.created_at)
        OR NEW.last_seen_at < OLD.last_seen_at THEN
        RAISE EXCEPTION 'Dossier identity/discovery history cannot be rewritten' USING ERRCODE = '23514';
    END IF;
    IF NEW.current_review_id IS DISTINCT FROM OLD.current_review_id THEN
        IF NEW.current_review_id IS NULL THEN
            RAISE EXCEPTION 'A selected dossier review cannot be cleared' USING ERRCODE = '23514';
        END IF;
        SELECT * INTO target FROM event_dossier_reviews WHERE id = NEW.current_review_id;
        IF NOT FOUND OR target.event_dossier_id <> OLD.id THEN
            RAISE EXCEPTION 'Current review must belong to its dossier' USING ERRCODE = '23514';
        END IF;
        IF OLD.current_review_id IS NULL THEN
            IF target.revision <> 1 OR target.supersedes_id IS NOT NULL THEN
                RAISE EXCEPTION 'First selected review must begin the dossier history' USING ERRCODE = '23514';
            END IF;
        ELSE
            SELECT revision INTO previous_revision FROM event_dossier_reviews WHERE id = OLD.current_review_id;
            IF target.supersedes_id IS DISTINCT FROM OLD.current_review_id
               OR target.revision <> previous_revision + 1 THEN
                RAISE EXCEPTION 'Current review must be the valid next revision' USING ERRCODE = '23514';
            END IF;
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER ed_identity_frozen BEFORE UPDATE ON event_dossiers
    FOR EACH ROW EXECUTE FUNCTION ed_identity_v1();
"""

FROZEN = (
    "event_dossier_sources",
    "event_dossier_claims",
    "event_dossier_reviews",
    "event_dossier_review_claims",
    "model_release_details",
    "personnel_change_details",
)
CHILDREN = (
    "event_dossier_review_claims",
    "model_release_details",
    "personnel_change_details",
)

for table in FROZEN:
    FORWARD += f"CREATE TRIGGER ed_frozen BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION ed_frozen_v1();\n"
for table in CHILDREN:
    FORWARD += f"CREATE TRIGGER ed_child BEFORE INSERT ON {table} FOR EACH ROW EXECUTE FUNCTION ed_child_v1();\n"

REVERSE = "\n".join(f"DROP TRIGGER ed_frozen ON {table};" for table in FROZEN)
REVERSE += "\n" + "\n".join(f"DROP TRIGGER ed_child ON {table};" for table in CHILDREN)
REVERSE += """
DROP TRIGGER ed_identity_frozen ON event_dossiers;
DROP TRIGGER ed_review_complete ON event_dossier_reviews;
DROP TRIGGER ed_dossier_complete ON event_dossiers;
DROP TRIGGER ed_source_canonical ON event_dossier_sources;
DROP FUNCTION ed_identity_v1();
DROP FUNCTION ed_complete_v1();
DROP FUNCTION ed_validate_review_v1(uuid);
DROP FUNCTION ed_child_v1();
DROP FUNCTION ed_source_v1();
DROP FUNCTION ed_frozen_v1();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0096_event_dossier_foundation")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
