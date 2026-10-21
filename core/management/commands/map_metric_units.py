"""Audit canonical measurement-unit references after cutover."""

import json

from django.core.management.base import BaseCommand
from django.db import connections

from core.metric_units import map_metric_units


class Command(BaseCommand):
    help = "Audit required metric and time-window unit references."

    def add_arguments(self, parser):
        parser.add_argument("--database", default="default", choices=tuple(connections))

    def handle(self, *args, **options):
        result = map_metric_units(database=options["database"])
        if options["verbosity"]:
            self.stdout.write(json.dumps(result, sort_keys=True))
