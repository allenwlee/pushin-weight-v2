"""Keep affiliation validation usable with column-limited serving grants."""

from typing import ClassVar

from django.db import migrations

FORWARD_SQL = """
        CREATE OR REPLACE FUNCTION g1_check_affiliation_replacement() RETURNS trigger AS $$
        DECLARE current_row record; replacement record;
        BEGIN
          SELECT id, person_id, brand_id, brand_discovery_candidate_id, superseded_by_id, superseded_at, superseded_by_reviewer, supersession_reason INTO current_row FROM people_brand_affiliations WHERE id = NEW.id;
          IF current_row.superseded_by_id IS NOT NULL THEN
            SELECT person_id, brand_id, brand_discovery_candidate_id INTO replacement FROM people_brand_affiliations WHERE id = current_row.superseded_by_id;
            IF current_row.person_id IS DISTINCT FROM replacement.person_id
              OR current_row.brand_id IS DISTINCT FROM replacement.brand_id
              OR current_row.brand_discovery_candidate_id IS DISTINCT FROM replacement.brand_discovery_candidate_id
              OR current_row.superseded_at IS NULL
              OR btrim(current_row.superseded_by_reviewer) = ''
              OR btrim(current_row.supersession_reason) = '' THEN
              RAISE EXCEPTION 'Replacement needs same person, organization and review' USING ERRCODE = '23514';
            END IF;
            IF EXISTS (
              WITH RECURSIVE chain(id, next_id) AS (
                SELECT id, superseded_by_id FROM people_brand_affiliations WHERE id = current_row.superseded_by_id
                UNION
                SELECT p.id, p.superseded_by_id FROM people_brand_affiliations p JOIN chain c ON p.id = c.next_id
              ) SELECT 1 FROM chain WHERE id = current_row.id
            ) THEN
              RAISE EXCEPTION 'Replacement cycle' USING ERRCODE = '23514';
            END IF;
          END IF;
          IF EXISTS (SELECT 1 FROM people_brand_affiliations p
            WHERE p.superseded_by_id = NEW.id AND (
              p.person_id IS DISTINCT FROM current_row.person_id
              OR p.brand_id IS DISTINCT FROM current_row.brand_id
              OR p.brand_discovery_candidate_id IS DISTINCT FROM current_row.brand_discovery_candidate_id)) THEN
            RAISE EXCEPTION 'Replacement dependencies must move together' USING ERRCODE = '23514';
          END IF;
          RETURN NULL;
        END; $$ LANGUAGE plpgsql;
"""

REVERSE_SQL = """
        CREATE OR REPLACE FUNCTION g1_check_affiliation_replacement() RETURNS trigger AS $$
        DECLARE current_row record; replacement record;
        BEGIN
          SELECT * INTO current_row FROM people_brand_affiliations WHERE id = NEW.id;
          IF current_row.superseded_by_id IS NOT NULL THEN
            SELECT * INTO replacement FROM people_brand_affiliations WHERE id = current_row.superseded_by_id;
            IF current_row.person_id IS DISTINCT FROM replacement.person_id
              OR current_row.brand_id IS DISTINCT FROM replacement.brand_id
              OR current_row.brand_discovery_candidate_id IS DISTINCT FROM replacement.brand_discovery_candidate_id
              OR current_row.superseded_at IS NULL
              OR btrim(current_row.superseded_by_reviewer) = ''
              OR btrim(current_row.supersession_reason) = '' THEN
              RAISE EXCEPTION 'Replacement needs same person, organization and review' USING ERRCODE = '23514';
            END IF;
            IF EXISTS (
              WITH RECURSIVE chain(id, next_id) AS (
                SELECT id, superseded_by_id FROM people_brand_affiliations WHERE id = current_row.superseded_by_id
                UNION
                SELECT p.id, p.superseded_by_id FROM people_brand_affiliations p JOIN chain c ON p.id = c.next_id
              ) SELECT 1 FROM chain WHERE id = current_row.id
            ) THEN
              RAISE EXCEPTION 'Replacement cycle' USING ERRCODE = '23514';
            END IF;
          END IF;
          IF EXISTS (SELECT 1 FROM people_brand_affiliations p
            WHERE p.superseded_by_id = NEW.id AND (
              p.person_id IS DISTINCT FROM current_row.person_id
              OR p.brand_id IS DISTINCT FROM current_row.brand_id
              OR p.brand_discovery_candidate_id IS DISTINCT FROM current_row.brand_discovery_candidate_id)) THEN
            RAISE EXCEPTION 'Replacement dependencies must move together' USING ERRCODE = '23514';
          END IF;
          RETURN NULL;
        END; $$ LANGUAGE plpgsql;
"""


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [("core", "0219_release_mapping_reconcile_index")]
    operations: ClassVar[list] = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
