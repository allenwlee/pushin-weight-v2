"""Name reported release owners explicitly on source claims."""

from django.db import migrations, models

# Django migration declarations are class-level values.
# ruff: noqa: RUF012


def owner_guard(brand, candidate):
    return f"""
CREATE OR REPLACE FUNCTION pw_rg7_release_claim_owner() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE kind_code text;
BEGIN
  SELECT code INTO kind_code FROM event_claim_kinds WHERE id=NEW.claim_kind_id;
  IF kind_code='release_report' AND (
       (NEW.{brand} IS NULL)=(NEW.{candidate} IS NULL)
       OR NEW.source_archive_id IS NULL OR NEW.release_maturity_id IS NULL
  ) THEN
    RAISE EXCEPTION 'Release report needs exactly one typed owner, archive and maturity'
      USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0203_rg7_product_release_cutover")]

    operations = [
        migrations.RemoveConstraint(
            model_name="eventdossierclaim", name="ck_ed_claim_one_owner"
        ),
        migrations.RenameField(
            model_name="eventdossierclaim", old_name="brand", new_name="reported_brand"
        ),
        migrations.RenameField(
            model_name="eventdossierclaim",
            old_name="brand_discovery_candidate",
            new_name="reported_brand_discovery_candidate",
        ),
        migrations.AddConstraint(
            model_name="eventdossierclaim",
            constraint=models.CheckConstraint(
                condition=models.Q(reported_brand__isnull=True)
                | models.Q(reported_brand_discovery_candidate__isnull=True),
                name="ck_ed_claim_one_owner",
            ),
        ),
        migrations.RunSQL(
            owner_guard("reported_brand_id", "reported_brand_discovery_candidate_id"),
            owner_guard("brand_id", "brand_discovery_candidate_id"),
        ),
    ]
