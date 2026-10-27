"""Replay saved prototype release reports into canonical EventDossiers."""

import json

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from core.product_release_dossiers import pending_release_ids, transfer_pending

PARITY_SQL = """
SELECT
  (SELECT count(*) FROM model_releases) AS releases,
  (SELECT count(*) FROM model_release_evidence) AS evidence,
  (SELECT count(*) FROM product_verification_proposals
   WHERE source_release_id IS NOT NULL) AS proposals,
  (SELECT count(*) FROM model_releases r
   LEFT JOIN event_dossiers d ON d.id=r.rg7_dossier_id
   LEFT JOIN event_kinds k ON k.id=d.event_kind_id
   WHERE d.id IS NULL OR k.code NOT IN ('model_release','product_release')
      OR d.first_seen_at<>r.first_seen_at OR d.last_seen_at<r.last_seen_at) AS bad_releases,
  (SELECT count(*) FROM model_release_evidence e
   JOIN model_releases r ON r.id=e.release_id
   LEFT JOIN event_dossier_claims c ON c.id=e.rg7_claim_id
   LEFT JOIN event_dossier_sources s ON s.id=c.event_dossier_source_id
   LEFT JOIN collection_evidence_archives a ON a.id=c.source_archive_id
   LEFT JOIN event_claim_kinds k ON k.id=c.claim_kind_id
   LEFT JOIN LATERAL (
     SELECT convert_from(a.body,'UTF8')::jsonb AS packet
   ) packet ON a.id IS NOT NULL
   WHERE c.id IS NULL OR s.event_dossier_id<>r.rg7_dossier_id
      OR s.post_id<>e.source_post_id OR k.code<>'release_report'
      OR c.reported_brand_id IS DISTINCT FROM r.brand_id
      OR c.reported_brand_discovery_candidate_id IS DISTINCT FROM r.brand_discovery_candidate_id
      OR c.release_maturity_id IS DISTINCT FROM r.release_maturity_id
      OR c.extraction_version<>e.extraction_version
      OR c.recorded_at<>e.created_at
      OR c.source_locator IS DISTINCT FROM e.source_url
      OR a.capture_kind<>'product_release_legacy'
      OR packet.packet->>'schema'<>'product-release-legacy-v1'
      OR packet.packet#>>'{release,release_identity}'<>r.release_identity
      OR packet.packet#>>'{release,brand_id}' IS DISTINCT FROM r.brand_id
      OR packet.packet#>>'{release,brand_discovery_candidate_id}'
         IS DISTINCT FROM r.brand_discovery_candidate_id::text
      OR packet.packet#>>'{evidence,evidence_hash}'<>e.evidence_hash
      OR packet.packet#>>'{evidence,source_post_id}'<>e.source_post_id
      OR packet.packet#>'{evidence,observed_claim}'<>e.observed_claim
      OR (packet.packet#>>'{evidence,observed_at}')::timestamptz<>e.observed_at
      OR (packet.packet#>>'{evidence,created_at}')::timestamptz<>e.created_at
      OR a.content_sha256<>encode(sha256(a.body),'hex')) AS bad_evidence,
  (SELECT count(*) FROM product_verification_proposals p
   JOIN model_releases r ON r.id=p.source_release_id
   WHERE p.source_dossier_id IS DISTINCT FROM r.rg7_dossier_id) AS bad_proposals
"""


def parity_counts():
    with connection.cursor() as cursor:
        cursor.execute(PARITY_SQL)
        return dict(
            zip([column[0] for column in cursor.description], cursor.fetchone())
        )


class Command(BaseCommand):
    help = "Copy saved release reports and check legacy-to-dossier parity"

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=50)
        parser.add_argument("--check-only", action="store_true")

    def handle(self, *args, **options):
        if options["batch_size"] < 1 or options["batch_size"] > 500:
            raise CommandError("batch size must be 1..500")
        result = (
            {}
            if options["check_only"]
            else transfer_pending(batch_size=options["batch_size"])
        )
        counts = parity_counts()
        pending = len(pending_release_ids(limit=1))
        self.stdout.write(
            json.dumps({"transfer": result, "parity": counts, "pending": pending})
        )
        if pending or any(
            counts[key] for key in ("bad_releases", "bad_evidence", "bad_proposals")
        ):
            raise CommandError("Product-release dossier parity is incomplete")
