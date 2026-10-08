"""Inspect readiness; record only an already-observed compatible cutover."""

import json
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from monitor.original_content_cutover import (
    readiness,
    record_cutover,
    retirement_status,
)


class Command(BaseCommand):
    help = "Report OriginalContent storage readiness and compatibility"

    def add_arguments(self, parser):
        parser.add_argument("--retirement-report", action="store_true")
        parser.add_argument("--record-cutover", action="store_true")
        parser.add_argument("--consumer-receipts")

    def handle(self, *args, **options):
        if options["retirement_report"]:
            self.stdout.write(json.dumps(retirement_status()))
            return
        try:
            if options["record_cutover"]:
                if not options["consumer_receipts"]:
                    raise ValueError("observed consumer receipts are required")
                receipts = json.loads(Path(options["consumer_receipts"]).read_text())
                report = record_cutover(
                    receipts, os.environ.get("RENDER_GIT_COMMIT", "")
                )
            else:
                report = readiness()
                report["revision"] = os.environ.get(
                    "RENDER_GIT_COMMIT", "local-unverified"
                )
        except (ValueError, OSError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(report, sort_keys=True))
        if report.get("ready") is False:
            raise CommandError("OriginalContent storage reconciliation is incomplete")
