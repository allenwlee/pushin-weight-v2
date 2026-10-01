import json

from django.core.management.base import BaseCommand

from core.staff_assets.arrivals import catch_up
from core.staff_assets.population import staff_population


class Command(BaseCommand):
    help = "Freeze stored Call A + database staff population; optionally register work."

    def add_arguments(self, parser):
        parser.add_argument("--list-id", type=int, required=True)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        operation = catch_up if options["apply"] else staff_population
        self.stdout.write(
            json.dumps(operation(list_id=options["list_id"]), ensure_ascii=False)
        )
