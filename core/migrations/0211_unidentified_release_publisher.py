"""Retain a source-backed release report when its publisher is unknown."""

from importlib import import_module
from typing import ClassVar

from django.db import migrations

OLD = import_module("core.migrations.0204_rg7_reported_release_owner_names")

FORWARD = """
CREATE OR REPLACE FUNCTION pw_rg7_release_claim_owner() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE kind_code text;
BEGIN
  SELECT code INTO kind_code FROM event_claim_kinds WHERE id=NEW.claim_kind_id;
  IF kind_code='release_report' AND (
       (NEW.reported_brand_id IS NOT NULL AND NEW.reported_brand_discovery_candidate_id IS NOT NULL)
       OR NEW.source_archive_id IS NULL OR NEW.release_maturity_id IS NULL
  ) THEN
    RAISE EXCEPTION 'Release report needs at most one typed owner, archive and maturity'
      USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
"""

REVERSE_GUARD = """
DO $$ BEGIN
  IF EXISTS (
    SELECT 1 FROM event_dossier_claims c
    JOIN event_claim_kinds k ON k.id=c.claim_kind_id
    WHERE k.code='release_report' AND c.reported_brand_id IS NULL
      AND c.reported_brand_discovery_candidate_id IS NULL
  ) THEN
    RAISE EXCEPTION 'Cannot restore owner requirement while unidentified release claims exist';
  END IF;
END $$;
"""


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [("core", "0210_release_acquisition_operation")]
    operations: ClassVar[list] = [
        migrations.RunSQL("SET LOCAL lock_timeout = '5s'", migrations.RunSQL.noop),
        migrations.RunSQL(
            FORWARD,
            REVERSE_GUARD + OLD.owner_guard("reported_brand_id", "reported_brand_discovery_candidate_id"),
        ),
    ]
