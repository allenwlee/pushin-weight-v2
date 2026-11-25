"""Keep source-attributed events on the shared evidence and review history."""

from importlib import import_module
from typing import ClassVar

from django.db import migrations

# A review can be assembled in several inserts. Validate the final projection
# in the existing deferred validator, along with claim ownership and chronology.
REVIEW_GUARD = """
CREATE OR REPLACE FUNCTION ed_validate_review_v1(review_key uuid)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE r event_dossier_reviews%ROWTYPE; kind text; previous event_dossier_reviews%ROWTYPE;
BEGIN
    IF review_key IS NULL THEN RETURN; END IF;
    SELECT * INTO r FROM event_dossier_reviews WHERE id = review_key;
    IF NOT FOUND THEN RETURN; END IF;
    SELECT k.code INTO kind FROM event_dossiers d
        JOIN event_kinds k ON k.id = d.event_kind_id WHERE d.id = r.event_dossier_id;
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
    IF kind NOT IN ('product_release', 'personnel_change', 'human_interest')
       OR (kind = 'product_release') IS DISTINCT FROM
            EXISTS (SELECT 1 FROM product_release_details WHERE review_id = r.id)
       OR (kind = 'personnel_change') IS DISTINCT FROM
            EXISTS (SELECT 1 FROM personnel_change_details WHERE review_id = r.id) THEN
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
"""


def install_review_guard(apps, schema_editor):
    schema_editor.execute(REVIEW_GUARD, params=None)


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [("core", "0239_provider_announcement_instruction")]
    operations: ClassVar[list] = [
        migrations.RunSQL("SET LOCAL lock_timeout = '5s'", migrations.RunSQL.noop),
        migrations.RunPython(
            install_review_guard,
            import_module("core.migrations.0203_rg7_product_release_cutover").replace_guard,
        ),
        migrations.RunSQL(
            """
            INSERT INTO event_kinds (code) VALUES ('human_interest') ON CONFLICT (code) DO NOTHING;
            INSERT INTO event_claim_kinds (code) VALUES ('attributed_statement') ON CONFLICT (code) DO NOTHING;
            """,
            # Existing FK references prevent rolling back vocabularies in use.
            """
            DELETE FROM event_claim_kinds WHERE code = 'attributed_statement';
            DELETE FROM event_kinds WHERE code = 'human_interest';
            """,
        ),
    ]
