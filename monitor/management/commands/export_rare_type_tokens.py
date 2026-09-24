from __future__ import annotations

import yaml
from django.core.management.base import BaseCommand

from core.models import BrandDiscoveryCandidate

EXPORT_VERSION = 1


def build_export_document() -> dict:
    candidates = BrandDiscoveryCandidate.objects.prefetch_related(
        "exact_tokens__evidence"
    ).order_by("candidate_identity", "id")
    rows = []
    for candidate in candidates:
        tokens = sorted(
            candidate.exact_tokens.all(),
            key=lambda token: (token.kind, token.form, token.pk),
        )
        evidence = [item for token in tokens for item in token.evidence.all()]
        rare_types = sorted({item.rare_type for item in evidence})
        ordered_evidence = sorted(
            evidence,
            key=lambda item: (item.observed_at, item.source_post_id, item.pk),
        )
        rows.append(
            {
                "id": candidate.candidate_identity,
                "status": candidate.verification_status,
                "rare_types_seen": rare_types,
                "tokens": [
                    {"form": token.form, "kind": token.kind, "script": token.script}
                    for token in tokens
                ],
                "first_post_id": (
                    ordered_evidence[0].source_post_id if ordered_evidence else None
                ),
                "last_post_id": (
                    ordered_evidence[-1].source_post_id if ordered_evidence else None
                ),
            }
        )
    return {"version": EXPORT_VERSION, "candidates": rows}


class Command(BaseCommand):
    help = "Export exact unresolved rare-type organization tokens as YAML."

    def handle(self, *args, **options):
        self.stdout.write(
            yaml.safe_dump(
                build_export_document(),
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
            ),
            ending="",
        )
