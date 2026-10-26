from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from monitor.enrichment_recovery import apply_manifest, build_manifest


class Command(BaseCommand):
    help = "Preview an immutable incident manifest, or requeue its exact failed stages."

    def add_arguments(self, parser):
        parser.add_argument("--since", default="2026-10-20T15:00:00+00:00")
        parser.add_argument("--until")
        parser.add_argument("--manifest", type=Path, required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--receipt", type=Path)
        parser.add_argument("--reset-post-id", action="append", default=[])
        parser.add_argument("--reset-reason", default="")

    def handle(self, *args, **options):
        try:
            if options["apply"]:
                if not options["receipt"] or options["receipt"].exists():
                    raise CommandError("apply requires a new --receipt path")
                manifest = json.loads(options["manifest"].read_text())
                # A missing directory or failed receipt write must not
                # leave a committed, unrecorded recovery batch.
                with options["receipt"].open("x") as output, transaction.atomic():
                    result = apply_manifest(manifest, limit=options["limit"])
                    json.dump(result, output, sort_keys=True, indent=2)
                    output.flush()
                    os.fsync(output.fileno())
                self.stdout.write(
                    json.dumps(
                        {
                            "requeued": len(result["requeued"]),
                            "remaining": result["remaining"],
                            "manifest_sha256": manifest["sha256"],
                        }
                    )
                )
            else:
                manifest = build_manifest(
                    since=datetime.fromisoformat(options["since"]),
                    until=datetime.fromisoformat(options["until"])
                    if options["until"]
                    else timezone.now(),
                    reset_post_ids=options["reset_post_id"],
                    reset_reason=options["reset_reason"],
                )
                with options["manifest"].open("x") as output:
                    json.dump(manifest, output, sort_keys=True, indent=2)
                self.stdout.write(
                    json.dumps(
                        {
                            "preview": True,
                            "posts": len(manifest["entries"]),
                            "sha256": manifest["sha256"],
                        }
                    )
                )
        except (ValueError, TypeError, OSError) as exc:
            raise CommandError(str(exc)) from exc
