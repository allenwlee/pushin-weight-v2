"""Poll or inspect the public provider announcement source."""
import json

from django.core.management.base import BaseCommand, CommandError

from monitor.provider_announcements import poll, poll_status


class Command(BaseCommand):
    help = "Collect public TwitterAPI.io Telegram announcements."

    def add_arguments(self, parser):
        parser.add_argument("--interval-minutes", type=int, default=15)
        parser.add_argument("--status", action="store_true", help="Read the saved poll health.")

    def handle(self, **options):
        minutes = options["interval_minutes"]
        if not 1 <= minutes <= 1440:
            raise CommandError("Interval must be between 1 and 1440 minutes.")
        result = (poll_status if options["status"] else poll)(minutes * 60)
        self.stdout.write(json.dumps(result, ensure_ascii=False))
        if result["status"] == "unavailable":
            raise CommandError("Provider announcement monitoring unavailable.")
