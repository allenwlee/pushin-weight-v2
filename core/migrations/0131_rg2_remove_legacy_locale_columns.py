"""Delete retired columns only after the 0130 application has replaced old consumers.

Release 0130 independently first. After this migration, recovery uses compatible
code or a forward repair; old fixed-language columns are not reconstructed.
"""

from django.db import migrations


def verify_retained_evidence(apps, schema_editor):
    """Refuse deletion if immutable wording or name identity was not retained."""
    checks = {
        "person-name locale": """
            SELECT count(*) FROM people_names
            WHERE locale_id IS NULL
               OR (language IS NOT NULL AND language IS DISTINCT FROM locale_id)
        """,
        "person display spelling": """
            SELECT count(*) FROM people p
            CROSS JOIN LATERAL (VALUES
                (p.display_name, 'und'), (p.display_name_en, 'en'),
                (p.display_name_zh_cn, 'zh-Hans'), (p.display_name_ja, 'ja')
            ) old(value, locale)
            WHERE old.value IS NOT NULL AND old.value <> ''
              AND old.value <> 'Unreviewed person'
              AND NOT EXISTS (SELECT 1 FROM people_names n
                  WHERE n.person_id=p.id AND n.full_name=old.value
                    AND n.locale_id=old.locale)
        """,
        "saved content snapshot": """
            SELECT count(*) FROM original_content c
            CROSS JOIN LATERAL (VALUES
                (c.brand_name_en_snapshot, 'en'),
                (c.brand_name_zh_cn_snapshot, 'zh-Hans')
            ) old(value, locale)
            WHERE old.value IS NOT NULL AND old.value <> ''
              AND NOT EXISTS (SELECT 1 FROM original_content_subject_labels l
                  WHERE l.content_id=c.id AND l.locale_id=old.locale
                    AND l.label_snapshot=old.value)
        """,
        "narrative subject snapshot": """
            SELECT count(*) FROM trend_narrative_subjects s
            CROSS JOIN LATERAL (VALUES
                (s.name_en_snapshot, 'en'), (s.name_zh_cn_snapshot, 'zh-Hans')
            ) old(value, locale)
            WHERE old.value IS NOT NULL AND old.value <> ''
              AND NOT EXISTS (SELECT 1 FROM trend_narrative_subject_labels l
                  WHERE l.subject_id=s.id AND l.locale_id=old.locale
                    AND l.label_snapshot=old.value)
        """,
    }
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SET LOCAL statement_timeout='30s'")
        for label, query in checks.items():
            cursor.execute(query)
            missing = cursor.fetchone()[0]
            if missing:
                raise RuntimeError(f"RG2 deletion refused: {missing} unmatched {label} values")


def preserve_original_content_view(apps, schema_editor):
    """Keep the existing read alias while its snapshot values move to owner rows."""
    quote = schema_editor.quote_name
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout='5s'")
        cursor.execute("SET LOCAL statement_timeout='30s'")
        cursor.execute(
            "SELECT attname FROM pg_attribute "
            "WHERE attrelid='brand_trend_narratives'::regclass "
            "AND attnum>0 AND NOT attisdropped ORDER BY attnum"
        )
        columns = [row[0] for row in cursor.fetchall()]
        replacements = {
            "brand_name_en_snapshot": "en",
            "brand_name_zh_cn_snapshot": "zh-Hans",
        }
        selections = []
        for column in columns:
            if column in replacements:
                locale = replacements[column]
                selections.append(
                    "COALESCE((SELECT label_snapshot FROM original_content_subject_labels "
                    f"WHERE content_id=c.id AND locale_id='{locale}'), '') AS {quote(column)}"
                )
            else:
                selections.append(f"c.{quote(column)}")
        cursor.execute(
            "CREATE OR REPLACE VIEW brand_trend_narratives AS SELECT "
            + ", ".join(selections)
            + " FROM original_content c"
        )


DROP_COMPATIBILITY_SQL = """
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
DROP TRIGGER IF EXISTS pw_person_name_locale_from_legacy ON people_names;
DROP FUNCTION IF EXISTS pw_person_name_locale_from_legacy();
DROP TRIGGER IF EXISTS pw_sync_company_labels_from_legacy ON companies;
DROP FUNCTION IF EXISTS pw_sync_company_labels_from_legacy();
DROP FUNCTION IF EXISTS pw_legacy_company_label(varchar,varchar,text);
DROP TRIGGER IF EXISTS pw_sync_person_names_from_legacy ON people;
DROP FUNCTION IF EXISTS pw_sync_person_names_from_legacy();
DROP FUNCTION IF EXISTS pw_legacy_person_selection(uuid,varchar,bigint);
DROP FUNCTION IF EXISTS pw_legacy_person_name(uuid,text,varchar,varchar);
DROP TRIGGER IF EXISTS pw_sync_account_profile_text_from_legacy ON accounts;
DROP FUNCTION IF EXISTS pw_sync_account_profile_text_from_legacy();
DROP TRIGGER IF EXISTS pw_copy_original_content_subject_labels ON original_content;
DROP FUNCTION IF EXISTS pw_copy_original_content_subject_labels();
DROP TRIGGER IF EXISTS pw_copy_trend_subject_labels ON trend_narrative_subjects;
DROP FUNCTION IF EXISTS pw_copy_trend_subject_labels();

CREATE OR REPLACE FUNCTION g1_check_person_name() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent_person uuid;
BEGIN
  IF TG_OP = 'UPDATE' AND (NEW.person_id IS DISTINCT FROM OLD.person_id
      OR NEW.full_name IS DISTINCT FROM OLD.full_name
      OR NEW.locale_id IS DISTINCT FROM OLD.locale_id
      OR NEW.origin IS DISTINCT FROM OLD.origin
      OR NEW.derived_from_id IS DISTINCT FROM OLD.derived_from_id) THEN
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

ALTER TABLE accounts DROP COLUMN bio_en, DROP COLUMN bio_zh_cn;
ALTER TABLE companies DROP COLUMN display_name, DROP COLUMN display_name_en,
    DROP COLUMN display_name_zh_cn;
ALTER TABLE original_content DROP COLUMN brand_name_en_snapshot,
    DROP COLUMN brand_name_zh_cn_snapshot;
ALTER TABLE people DROP COLUMN display_name, DROP COLUMN display_name_en,
    DROP COLUMN display_name_ja, DROP COLUMN display_name_zh_cn;
ALTER TABLE people_names DROP COLUMN language;
ALTER TABLE trend_narrative_subjects DROP COLUMN name_en_snapshot,
    DROP COLUMN name_zh_cn_snapshot;
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0130_rg2_person_name_locale_required")]

    operations = [
        migrations.RunPython(verify_retained_evidence, reverse_code=None),
        migrations.RunPython(preserve_original_content_view, reverse_code=None),
        migrations.RunSQL(DROP_COMPATIBILITY_SQL, reverse_sql=None),
    ]
