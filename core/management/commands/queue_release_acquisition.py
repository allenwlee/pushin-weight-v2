"""Recover a bounded page of unqueued product-release acquisition leads."""

import json

from django.core.management.base import BaseCommand, CommandError

from core.product_release_acquisition import queue_saved_release_claims


class Command(BaseCommand):
    help = "Queue saved release names and repository leads; dry-run unless --persist."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--cursor", help="JSON next_cursor returned by the previous page")
        parser.add_argument("--persist", action="store_true")

    def handle(self, *args, **options):
        try:
            cursor = json.loads(options["cursor"]) if options["cursor"] else None
            result = queue_saved_release_claims(
                limit=options["limit"], after=cursor, persist=options["persist"]
            )
        except (TypeError, ValueError) as error:
            raise CommandError(str(error)) from error
        result.update(mode="persist" if options["persist"] else "dry_run", provider_calls=0)
        self.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True))
