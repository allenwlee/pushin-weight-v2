"""Only original source text may support a typed citizenship."""

from django.db import migrations

# Django migration declarations are class-level values.
# ruff: noqa: RUF012


GUARD = """
CREATE FUNCTION pw_rg4_citizenship_source_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_TABLE_NAME='people_texts' THEN
    IF NEW.origin<>'source' AND EXISTS (
        SELECT 1 FROM person_citizenship_evidence
        WHERE person_text_id=OLD.id) THEN
      RAISE EXCEPTION 'Cited citizenship evidence must remain original source text'
        USING ERRCODE='23514';
    END IF;
  ELSIF NOT EXISTS (
      SELECT 1 FROM people_texts
      WHERE id=NEW.person_text_id AND origin='source') THEN
    RAISE EXCEPTION 'Citizenship needs original source text'
      USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER pw_rg4_citizenship_source_evidence
  BEFORE INSERT OR UPDATE ON person_citizenship_evidence
  FOR EACH ROW EXECUTE FUNCTION pw_rg4_citizenship_source_guard();
CREATE TRIGGER pw_rg4_citizenship_source_text
  BEFORE UPDATE OF origin ON people_texts
  FOR EACH ROW EXECUTE FUNCTION pw_rg4_citizenship_source_guard();
"""

UNGUARD = """
DROP TRIGGER pw_rg4_citizenship_source_text ON people_texts;
DROP TRIGGER pw_rg4_citizenship_source_evidence ON person_citizenship_evidence;
DROP FUNCTION pw_rg4_citizenship_source_guard();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0144_rg4_nationality_old_writer_bridge")]
    operations = [
        migrations.RunSQL(GUARD, reverse_sql=UNGUARD),
    ]
