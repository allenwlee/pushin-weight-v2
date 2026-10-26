"""Adopt frozen historical campaign reservations before retiring run reports."""

import json

from django.core.management.base import BaseCommand

from core.data_source_backfill import project_legacy_campaigns


class Command(BaseCommand):
    help = "Copy historical campaign reservation baselines into typed campaign rows"

    def add_arguments(self, parser):
        parser.add_argument("--verify-only", action="store_true")

    def handle(self, *args, **options):
        result = project_legacy_campaigns(verify_only=options["verify_only"])
        self.stdout.write(json.dumps({"verify_only": options["verify_only"], **result}))
