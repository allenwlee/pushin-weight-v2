"""Separate evidenced citizenship from ambiguous legacy nationality wording."""

import hashlib
import json
import uuid

import django.db.models.deletion
from django.db import migrations, models
from django.utils import timezone

# Django migration declarations are class-level values.
# ruff: noqa: RUF012


def retain_reported_nationality(apps, schema_editor):
    people = apps.get_model("core", "Person")
    texts = apps.get_model("core", "PersonText")
    alias = schema_editor.connection.alias
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("LOCK TABLE people IN SHARE ROW EXCLUSIVE MODE")
        cursor.execute("SELECT count(*) FROM people WHERE nationality IS NOT NULL AND nationality<>''")
        expected = cursor.fetchone()[0]
    retained = 0
    observed = timezone.now()
    for person in people.objects.using(alias).exclude(nationality__isnull=True).exclude(
        nationality=""
    ).iterator(chunk_size=500):
        source_text = person.nationality
        version_hash = hashlib.sha256(
            json.dumps(["und", source_text], sort_keys=True,
                       ensure_ascii=False, default=str).encode()
        ).hexdigest()
        row, _ = texts.objects.using(alias).get_or_create(
            person_id=person.pk,
            affiliation_id=None,
            kind="reported_nationality",
            source_reference="legacy:people.nationality",
            version_hash=version_hash,
            defaults={
                "origin": "unknown",
                "review_status": "pending",
                "language": "und",
                "text": source_text,
                "observed_at": observed,
            },
        )
        if row.text != source_text:
            raise RuntimeError("Legacy nationality evidence conflicts with retained text")
        retained += 1
    if retained != expected:
        raise RuntimeError("Legacy nationality wording was not fully retained")


GUARDS = """
CREATE FUNCTION pw_rg4_citizenship_link_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE owner_id uuid; evidence_person_id uuid;
BEGIN
  IF TG_TABLE_NAME='person_citizenships' THEN
    IF NEW.person_id IS DISTINCT FROM OLD.person_id
       OR NEW.country_code IS DISTINCT FROM OLD.country_code THEN
      RAISE EXCEPTION 'Citizenship owner and country are immutable' USING ERRCODE='23514';
    END IF;
  ELSIF TG_TABLE_NAME='people_texts' THEN
    IF NEW.person_id IS DISTINCT FROM OLD.person_id
       AND EXISTS (SELECT 1 FROM person_citizenship_evidence
                   WHERE person_text_id=OLD.id) THEN
      RAISE EXCEPTION 'Cited person text owner is immutable' USING ERRCODE='23514';
    END IF;
  ELSE
    IF TG_OP='UPDATE' AND (
        NEW.citizenship_id IS DISTINCT FROM OLD.citizenship_id
        OR NEW.person_text_id IS DISTINCT FROM OLD.person_text_id) THEN
      RAISE EXCEPTION 'Citizenship evidence link is immutable' USING ERRCODE='23514';
    END IF;
    SELECT person_id INTO owner_id FROM person_citizenships
      WHERE id=NEW.citizenship_id;
    SELECT person_id INTO evidence_person_id FROM people_texts
      WHERE id=NEW.person_text_id;
    IF owner_id IS NULL OR evidence_person_id IS NULL
       OR owner_id IS DISTINCT FROM evidence_person_id THEN
      RAISE EXCEPTION 'Citizenship evidence must belong to the same person'
        USING ERRCODE='23514';
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER pw_rg4_citizenship_owner BEFORE UPDATE OF person_id,country_code
  ON person_citizenships FOR EACH ROW EXECUTE FUNCTION pw_rg4_citizenship_link_guard();
CREATE TRIGGER pw_rg4_citizenship_text_owner BEFORE UPDATE OF person_id
  ON people_texts FOR EACH ROW EXECUTE FUNCTION pw_rg4_citizenship_link_guard();
CREATE TRIGGER pw_rg4_citizenship_evidence_owner BEFORE INSERT OR UPDATE
  ON person_citizenship_evidence FOR EACH ROW
  EXECUTE FUNCTION pw_rg4_citizenship_link_guard();

CREATE FUNCTION pw_rg4_citizenship_supported() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE citizenship_key uuid;
BEGIN
  IF TG_TABLE_NAME='person_citizenships' THEN
    citizenship_key := NEW.id;
  ELSE
    citizenship_key := OLD.citizenship_id;
  END IF;
  IF EXISTS (SELECT 1 FROM person_citizenships WHERE id=citizenship_key)
     AND NOT EXISTS (SELECT 1 FROM person_citizenship_evidence
                     WHERE citizenship_id=citizenship_key) THEN
    RAISE EXCEPTION 'Citizenship needs a source evidence link' USING ERRCODE='23514';
  END IF;
  RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER pw_rg4_citizenship_supported
  AFTER INSERT ON person_citizenships DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION pw_rg4_citizenship_supported();
CREATE CONSTRAINT TRIGGER pw_rg4_citizenship_evidence_retained
  AFTER DELETE ON person_citizenship_evidence DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION pw_rg4_citizenship_supported();
"""

UNGUARDS = """
DROP TRIGGER pw_rg4_citizenship_evidence_retained ON person_citizenship_evidence;
DROP TRIGGER pw_rg4_citizenship_supported ON person_citizenships;
DROP FUNCTION pw_rg4_citizenship_supported();
DROP TRIGGER pw_rg4_citizenship_evidence_owner ON person_citizenship_evidence;
DROP TRIGGER pw_rg4_citizenship_text_owner ON people_texts;
DROP TRIGGER pw_rg4_citizenship_owner ON person_citizenships;
DROP FUNCTION pw_rg4_citizenship_link_guard();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0142_rg4_scoped_claim_references")]

    operations = [
        migrations.RunSQL(
            "SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='30s'",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.CreateModel(
            name="PersonCitizenship",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False,
                                        primary_key=True, serialize=False)),
                ("is_primary", models.BooleanField(default=False)),
                ("country", models.ForeignKey(
                    db_column="country_code", on_delete=django.db.models.deletion.PROTECT,
                    related_name="person_citizenships", to="core.country",
                )),
                ("person", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="citizenships", to="core.person",
                )),
            ],
            options={"db_table": "person_citizenships"},
        ),
        migrations.CreateModel(
            name="PersonCitizenshipEvidence",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                          serialize=False, verbose_name="ID")),
                ("citizenship", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="evidence", to="core.personcitizenship",
                )),
                ("person_text", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="citizenship_evidence", to="core.persontext",
                )),
            ],
            options={"db_table": "person_citizenship_evidence"},
        ),
        migrations.AddConstraint(
            model_name="personcitizenship",
            constraint=models.UniqueConstraint(
                fields=("person", "country"), name="uq_person_citizenship_country"
            ),
        ),
        migrations.AddConstraint(
            model_name="personcitizenship",
            constraint=models.UniqueConstraint(
                condition=models.Q(is_primary=True), fields=("person",),
                name="uq_person_primary_citizenship",
            ),
        ),
        migrations.AddConstraint(
            model_name="personcitizenshipevidence",
            constraint=models.UniqueConstraint(
                fields=("citizenship", "person_text"),
                name="uq_person_citizenship_evidence",
            ),
        ),
        migrations.RunPython(retain_reported_nationality, migrations.RunPython.noop),
        migrations.RunSQL(GUARDS, reverse_sql=UNGUARDS),
        migrations.SeparateDatabaseAndState(state_operations=[
            migrations.RemoveField(model_name="person", name="nationality"),
        ]),
    ]
