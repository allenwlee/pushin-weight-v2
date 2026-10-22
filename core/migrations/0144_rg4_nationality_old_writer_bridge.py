"""Retain any old-image nationality wording during the RG4 drain window."""

from django.db import migrations

# Django migration declarations are class-level values.
# ruff: noqa: RUF012


BRIDGE = """
CREATE FUNCTION pw_rg4_nationality_evidence_bridge() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE changed boolean;
BEGIN
  IF TG_OP='UPDATE' THEN
    IF OLD.nationality IS NOT NULL AND OLD.nationality<>''
       AND (NEW.nationality IS NULL OR NEW.nationality='') THEN
      RAISE EXCEPTION 'Clear legacy nationality only after a reviewed evidence correction'
        USING ERRCODE='23514';
    END IF;
    changed := NEW.nationality IS DISTINCT FROM OLD.nationality;
  ELSE
    changed := true;
  END IF;
  IF NEW.nationality IS NOT NULL AND NEW.nationality<>''
     AND changed THEN
    INSERT INTO people_texts (
      person_id, affiliation_id, origin, derived_from_id, review_status,
      review_note, kind, language, text, source_reference, version_hash,
      observed_at, created_at
    )
    SELECT NEW.id, NULL, 'unknown', NULL, 'pending', '',
      'reported_nationality', 'und', NEW.nationality,
      'legacy:people.nationality',
      encode(sha256(convert_to('legacy:people.nationality:' || NEW.nationality,
                               'UTF8')), 'hex'),
      statement_timestamp(), statement_timestamp()
    WHERE NOT EXISTS (
      SELECT 1 FROM people_texts
      WHERE person_id=NEW.id AND affiliation_id IS NULL
        AND kind='reported_nationality'
        AND source_reference='legacy:people.nationality'
        AND text=NEW.nationality
    )
    ON CONFLICT ON CONSTRAINT uq_person_text_version DO NOTHING;
  END IF;
  RETURN NULL;
END $$;
CREATE TRIGGER pw_rg4_nationality_evidence_bridge
  AFTER INSERT OR UPDATE OF nationality ON people
  FOR EACH ROW EXECUTE FUNCTION pw_rg4_nationality_evidence_bridge();
"""

UNBRIDGE = """
DROP TRIGGER pw_rg4_nationality_evidence_bridge ON people;
DROP FUNCTION pw_rg4_nationality_evidence_bridge();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0143_rg4_person_citizenship_evidence")]
    operations = [
        migrations.RunSQL(
            "SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='30s'",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(BRIDGE, reverse_sql=UNBRIDGE),
    ]
