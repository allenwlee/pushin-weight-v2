"""Admit reviewed repository relations from a bounded operator-supplied recording."""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.collection_identity import review_github_mapping
from core.models import MeasurementSubject


class Command(BaseCommand):
    help = "Inspect a reviewed GitHub crosswalk import; use --apply to persist existing-subject links."

    def add_arguments(self, parser):
        parser.add_argument("recording")
        parser.add_argument("--reviewed-by", required=True)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        try:
            path = Path(options["recording"])
            if path.stat().st_size > 2 * 1024 * 1024:
                raise ValueError("crosswalk import byte budget exceeded")
            rows = json.loads(path.read_text())
            if not isinstance(rows, list) or len(rows) > 10000:
                raise ValueError("bounded crosswalk list required")
            if not options["apply"]:
                self.stdout.write(
                    json.dumps(
                        {"operation": "inspect", "candidates": len(rows), "writes": 0}
                    )
                )
                return
            with transaction.atomic():
                identities = []
                for row in rows:
                    subject = MeasurementSubject.objects.get(pk=row["subject_id"])
                    mapping = review_github_mapping(
                        subject=subject,
                        repo=row["repo"],
                        role=row["role"],
                        version_selector=row.get("version_selector"),
                        evidence_url=row["evidence_url"],
                        reviewed_by=options["reviewed_by"],
                    )
                    identities.append(str(mapping.pk))
            self.stdout.write(
                json.dumps({"operation": "admit", "mapping_ids": identities})
            )
        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            MeasurementSubject.DoesNotExist,
        ) as exc:
            raise CommandError("invalid or unqualified crosswalk import") from exc
