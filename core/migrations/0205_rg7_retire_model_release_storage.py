"""Retire prototype release storage after the live dossier parity gate."""

from django.db import migrations

# Django migration declarations are class-level values.
# ruff: noqa: RUF012

GUARD = r"""
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM model_releases r
    LEFT JOIN event_dossiers d ON d.id=r.rg7_dossier_id
    LEFT JOIN event_kinds k ON k.id=d.event_kind_id
    WHERE r.review_status<>'pending' OR d.id IS NULL
       OR k.code<>'product_release'
       OR d.first_seen_at<>r.first_seen_at OR d.last_seen_at<r.last_seen_at
  ) THEN
    RAISE EXCEPTION 'RG7 retirement blocked: unmapped release or review';
  END IF;
  IF EXISTS (
    SELECT 1 FROM model_release_evidence e
    JOIN model_releases r ON r.id=e.release_id
    LEFT JOIN event_dossier_claims c ON c.id=e.rg7_claim_id
    LEFT JOIN event_dossier_sources s ON s.id=c.event_dossier_source_id
    LEFT JOIN collection_evidence_archives a ON a.id=c.source_archive_id
    LEFT JOIN event_claim_kinds k ON k.id=c.claim_kind_id
    LEFT JOIN LATERAL (
      SELECT convert_from(a.body,'UTF8')::jsonb AS packet
    ) p ON a.id IS NOT NULL
    WHERE c.id IS NULL OR s.event_dossier_id<>r.rg7_dossier_id
       OR s.post_id<>e.source_post_id OR k.code<>'release_report'
       OR c.reported_brand_id IS DISTINCT FROM r.brand_id
       OR c.reported_brand_discovery_candidate_id
          IS DISTINCT FROM r.brand_discovery_candidate_id
       OR c.release_maturity_id IS DISTINCT FROM r.release_maturity_id
       OR c.extraction_version<>e.extraction_version
       OR c.recorded_at<>e.created_at
       OR c.source_locator IS DISTINCT FROM e.source_url
       OR a.capture_kind<>'product_release_legacy'
       OR p.packet->>'schema'<>'product-release-legacy-v1'
       OR p.packet#>>'{release,release_identity}'<>r.release_identity
       OR p.packet#>>'{evidence,evidence_hash}'<>e.evidence_hash
       OR p.packet#>'{evidence,observed_claim}'<>e.observed_claim
       OR a.content_sha256<>encode(sha256(a.body),'hex')
  ) THEN
    RAISE EXCEPTION 'RG7 retirement blocked: evidence parity mismatch';
  END IF;
  IF EXISTS (
    SELECT 1 FROM product_verification_proposals p
    JOIN model_releases r ON r.id=p.source_release_id
    WHERE p.source_dossier_id IS DISTINCT FROM r.rg7_dossier_id
  ) THEN
    RAISE EXCEPTION 'RG7 retirement blocked: proposal parity mismatch';
  END IF;
  IF EXISTS (
    SELECT 1 FROM event_dossier_claims c
    JOIN collection_evidence_archives a ON a.id=c.source_archive_id
    WHERE a.capture_kind='product_release_legacy'
      AND NOT EXISTS (
        SELECT 1 FROM model_release_evidence e WHERE e.rg7_claim_id=c.id
      )
  ) THEN
    RAISE EXCEPTION 'RG7 retirement blocked: obsolete legacy claim';
  END IF;
END $$;
"""

DROP_TRACKING = r"""
DROP TRIGGER pw_rg7_proposal_invalidation ON product_verification_proposals;
DROP FUNCTION pw_rg7_proposal_invalidation();
DROP TRIGGER pw_rg7_evidence_invalidation ON model_release_evidence;
DROP FUNCTION pw_rg7_evidence_invalidation();
DROP TRIGGER pw_rg7_release_invalidation ON model_releases;
DROP FUNCTION pw_rg7_release_invalidation();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0204_rg7_reported_release_owner_names")]

    operations = [
        migrations.RunSQL(GUARD),
        migrations.RunSQL(DROP_TRACKING),
        migrations.RemoveField(
            model_name="productverificationproposal", name="source_release"
        ),
        migrations.DeleteModel(name="ModelReleaseEvidence"),
        migrations.DeleteModel(name="ModelRelease"),
    ]
