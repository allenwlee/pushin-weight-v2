"""Preserve legacy spellings without inventing source verification."""

import hashlib
import json

from django.db import migrations
from django.utils import timezone


def backfill(apps, schema_editor):
    Person = apps.get_model("core", "Person")
    Name = apps.get_model("core", "PersonName")
    Evidence = apps.get_model("core", "PersonNameEvidence")
    alias = schema_editor.connection.alias
    for person in Person.objects.using(alias).iterator(chunk_size=500):
        for field, lang in (
            ("display_name", "und"),
            ("display_name_en", "en"),
            ("display_name_zh_cn", "zh-Hans"),
            ("display_name_ja", "ja"),
        ):
            value = getattr(person, field)
            if not value or not value.strip():
                continue
            fingerprint = hashlib.sha256(
                json.dumps([field, value], ensure_ascii=False).encode()
            ).hexdigest()
            name, _ = Name.objects.using(alias).get_or_create(
                person_id=person.pk,
                fingerprint=fingerprint,
                defaults=dict(full_name=value, language=lang, origin="legacy"),
            )
            Evidence.objects.using(alias).get_or_create(
                name_id=name.pk,
                evidence_hash=fingerprint,
                defaults=dict(
                    source_kind="legacy_unknown",
                    source_reference=f"people:{person.pk}:{field}",
                    source_text=value,
                    supports_fields=["full_name"],
                    observed_at=timezone.now(),
                    collection_method="migration",
                    review_reason="Original source unknown; retained without verification",
                ),
            )


FORWARD = """
CREATE FUNCTION g1_check_person_name_selection() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE chosen record;
BEGIN
  IF NEW.primary_name_id IS NOT NULL THEN
    SELECT * INTO chosen FROM people_names WHERE id = NEW.primary_name_id FOR SHARE;
    IF chosen.person_id IS DISTINCT FROM NEW.id OR chosen.review_status IS DISTINCT FROM 'confirmed' THEN
      RAISE EXCEPTION 'Primary name must be confirmed and belong to this person' USING ERRCODE = '23514';
    END IF;
  END IF;
  IF NEW.english_name_id IS NOT NULL THEN
    SELECT * INTO chosen FROM people_names WHERE id = NEW.english_name_id FOR SHARE;
    IF chosen.person_id IS DISTINCT FROM NEW.id OR chosen.review_status IS DISTINCT FROM 'confirmed'
       OR chosen.language NOT IN ('en', 'en-Latn') THEN
      RAISE EXCEPTION 'English name must be confirmed, English, and belong to this person' USING ERRCODE = '23514';
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER g1_person_name_selection BEFORE INSERT OR UPDATE OF primary_name_id, english_name_id
ON people FOR EACH ROW EXECUTE FUNCTION g1_check_person_name_selection();

CREATE FUNCTION g1_check_person_name() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent_person uuid;
BEGIN
  IF TG_OP = 'UPDATE' AND (NEW.person_id IS DISTINCT FROM OLD.person_id
      OR NEW.full_name IS DISTINCT FROM OLD.full_name OR NEW.language IS DISTINCT FROM OLD.language
      OR NEW.origin IS DISTINCT FROM OLD.origin OR NEW.derived_from_id IS DISTINCT FROM OLD.derived_from_id) THEN
    RAISE EXCEPTION 'Create a new name representation to preserve the original' USING ERRCODE = '23514';
  END IF;
  IF NEW.derived_from_id IS NOT NULL THEN
    SELECT person_id INTO parent_person FROM people_names WHERE id = NEW.derived_from_id FOR SHARE;
    IF parent_person IS DISTINCT FROM NEW.person_id THEN
      RAISE EXCEPTION 'Derived name must belong to the same person' USING ERRCODE = '23514';
    END IF;
  END IF;
  IF NEW.review_status <> 'confirmed' AND EXISTS (
    SELECT 1 FROM people WHERE primary_name_id = NEW.id OR english_name_id = NEW.id
  ) THEN
    RAISE EXCEPTION 'Clear display selections before changing name review' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER g1_person_name_guard BEFORE INSERT OR UPDATE ON people_names
FOR EACH ROW EXECUTE FUNCTION g1_check_person_name();
"""
REVERSE = """
DROP TRIGGER IF EXISTS g1_person_name_guard ON people_names;
DROP FUNCTION IF EXISTS g1_check_person_name();
DROP TRIGGER IF EXISTS g1_person_name_selection ON people;
DROP FUNCTION IF EXISTS g1_check_person_name_selection();
"""


def guards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(FORWARD)


def remove_guards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(REVERSE)


class Migration(migrations.Migration):
    dependencies = [("core", "0059_person_names_and_sex")]
    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
        migrations.RunPython(guards, remove_guards),
    ]
