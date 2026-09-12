from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from core.job_sources.registry import SOURCES
from core.job_sources.runner import SourceRunResult, run_source


class Command(BaseCommand):
    help = "Pull public job listings from official AI-lab recruiting sites."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            action="append",
            choices=sorted(SOURCES),
            help="Sync one named source; repeat for multiple sources. Defaults to all.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Fetch and validate without database writes or leases.",
        )
        parser.add_argument(
            "--no-close",
            action="store_true",
            help="Upsert observed jobs without advancing missing-job closure state.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            dest="as_json",
            help="Emit one machine-readable summary.",
        )

    def handle(self, *args, **options):
        selected = options["source"] or list(SOURCES)
        results = []
        for key in selected:
            try:
                result = run_source(
                    SOURCES[key],
                    dry_run=options["dry_run"],
                    no_close=options["no_close"],
                )
            except Exception as exc:  # noqa: BLE001 - preserve later source attempts
                result = SourceRunResult(key, "failed", error=str(exc)[:4000])
            results.append(result)
        wire = [
            {
                "source": result.source_key,
                "status": result.status,
                "observed_total": result.observed_total,
                "error": result.error,
                "sync": (
                    {
                        name: getattr(result.sync, name)
                        for name in (
                            "run_id",
                            "created_count",
                            "updated_count",
                            "unchanged_count",
                            "reopened_count",
                            "closed_count",
                        )
                    }
                    if result.sync
                    else None
                ),
            }
            for result in results
        ]
        if options["as_json"]:
            self.stdout.write(json.dumps(wire, ensure_ascii=False))
        else:
            for item in wire:
                line = (
                    f"{item['source']}: {item['status']} "
                    f"({item['observed_total']} observed)"
                )
                if item["error"]:
                    line += f" — {item['error']}"
                self.stdout.write(line)
        failed = [item for item in wire if item["status"] == "failed"]
        if failed:
            raise CommandError(f"{len(failed)} job source(s) failed")
