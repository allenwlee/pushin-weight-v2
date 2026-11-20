"""Add current category identities and reject new legacy assignments."""

from typing import ClassVar

from django.db import migrations, models

CODES = ("model-llm", "model-other", "agent", "harness", "other")


def seed_categories(apps, schema_editor):
    category = apps.get_model("core", "ProductType")
    for code in CODES:
        category.objects.using(schema_editor.connection.alias).get_or_create(code=code)


GUARDS = """
CREATE FUNCTION pw_pulse_category_catalog_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='INSERT' AND NEW.code NOT IN ('model-llm','model-other','agent','harness','other') THEN
    RAISE EXCEPTION 'Invalid current product category definition' USING ERRCODE='23514';
  END IF;
  IF NEW.code IN ('model-llm','model-other','agent','harness','other')
     AND NEW.parent_id IS NOT NULL THEN
    RAISE EXCEPTION 'Current product categories must be flat' USING ERRCODE='23514';
  END IF;
  IF TG_OP='UPDATE' AND OLD.code NOT IN ('model-llm','model-other','agent','harness','other')
     AND NEW.parent_id IS DISTINCT FROM OLD.parent_id THEN
    RAISE EXCEPTION 'Legacy product category is read only' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER pw_pulse_category_catalog_guard BEFORE INSERT OR UPDATE ON product_types
FOR EACH ROW EXECUTE FUNCTION pw_pulse_category_catalog_guard();
CREATE FUNCTION pw_pulse_category_catalog_final() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.code IN ('model-llm','model-other','agent','harness','other')
     AND NEW.parent_id IS NOT NULL THEN
    RAISE EXCEPTION 'Current product categories must be flat' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER pw_pulse_category_catalog_final AFTER INSERT OR UPDATE ON product_types
FOR EACH ROW EXECUTE FUNCTION pw_pulse_category_catalog_final();
CREATE FUNCTION pw_pulse_product_type_write() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.product_type_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM product_types WHERE id=NEW.product_type_id
      AND code IN ('model-llm','model-other','agent','harness','other')
  ) THEN
    RAISE EXCEPTION 'Invalid current product category' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER pw_pulse_product_type_write BEFORE INSERT OR UPDATE OF product_type_id ON products
FOR EACH ROW EXECUTE FUNCTION pw_pulse_product_type_write();
CREATE FUNCTION pw_pulse_product_type_final() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (TG_OP='INSERT' OR NEW.product_type_id IS DISTINCT FROM OLD.product_type_id) AND NEW.product_type_id IS NOT NULL
    AND NOT EXISTS (SELECT 1 FROM product_types WHERE id=NEW.product_type_id
      AND code IN ('model-llm','model-other','agent','harness','other')) THEN
    RAISE EXCEPTION 'Invalid final product category' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER pw_pulse_product_type_final AFTER INSERT OR UPDATE ON products
FOR EACH ROW EXECUTE FUNCTION pw_pulse_product_type_final();
CREATE FUNCTION pw_pulse_rare_category_write() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.category NOT IN ('model-llm','model-other','agent','harness','other') THEN
    RAISE EXCEPTION 'Invalid current product category' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER pw_pulse_rare_category_write BEFORE INSERT OR UPDATE OF category ON rare_type_category_assignments
FOR EACH ROW EXECUTE FUNCTION pw_pulse_rare_category_write();
CREATE FUNCTION pw_pulse_rare_category_final() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (TG_OP='INSERT' OR NEW.category IS DISTINCT FROM OLD.category) AND NEW.category NOT IN
     ('model-llm','model-other','agent','harness','other') THEN
    RAISE EXCEPTION 'Invalid final product category' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER pw_pulse_rare_category_final AFTER INSERT OR UPDATE ON rare_type_category_assignments
FOR EACH ROW EXECUTE FUNCTION pw_pulse_rare_category_final();
"""

REVERSE = """
DROP TRIGGER pw_pulse_category_catalog_guard ON product_types;
DROP TRIGGER pw_pulse_category_catalog_final ON product_types;
DROP FUNCTION pw_pulse_category_catalog_guard();
DROP FUNCTION pw_pulse_category_catalog_final();
DROP TRIGGER pw_pulse_product_type_write ON products;
DROP TRIGGER pw_pulse_product_type_final ON products;
DROP TRIGGER pw_pulse_rare_category_write ON rare_type_category_assignments;
DROP TRIGGER pw_pulse_rare_category_final ON rare_type_category_assignments;
DROP FUNCTION pw_pulse_product_type_write();
DROP FUNCTION pw_pulse_product_type_final();
DROP FUNCTION pw_pulse_rare_category_write();
DROP FUNCTION pw_pulse_rare_category_final();
"""


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [("core", "0226_chart_native_lookup_index")]
    operations: ClassVar[list] = [
        migrations.RunSQL("SET LOCAL lock_timeout = '5s'", migrations.RunSQL.noop),
        migrations.AlterField(
            model_name="raretypecategoryassignment",
            name="category",
            field=models.CharField(
                max_length=32,
                choices=[
                    ("model-llm", "LLM model"),
                    ("model-other", "Other AI model"),
                    ("agent", "Agent"),
                    ("harness", "Harness"),
                    ("other", "Other"),
                ],
            ),
        ),
        migrations.RunPython(seed_categories, migrations.RunPython.noop),
        migrations.RunSQL(GUARDS, REVERSE),
    ]
