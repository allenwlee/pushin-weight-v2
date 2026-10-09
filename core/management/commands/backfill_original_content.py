"""Report by default; bounded, replay-safe application requires --apply."""
import json

from django.core.management.base import BaseCommand, CommandError

from monitor.original_content_backfill import backfill_original_content


class Command(BaseCommand):
    help = "Inspect/import OriginalContent history without provider requests"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--batch-size", type=int, default=200)
        parser.add_argument("--after-assessment", type=int, default=0)
        parser.add_argument("--limit", type=int)

    def handle(self, *args, **options):
        try:
            report = backfill_original_content(apply=options["apply"], batch_size=options["batch_size"],
                after_assessment=options["after_assessment"], limit=options["limit"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(report, sort_keys=True))
        if not report["ready"]:
            raise CommandError("OriginalContent reconciliation has unresolved discrepancies")
