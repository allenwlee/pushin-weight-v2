"""Provider-free maintenance of the registered dashboard materializations."""

import json

from django.core.management.base import BaseCommand, CommandError

from core.materializations import refresh_materialization


def registered_definitions():
    from monitor.each_chart_facts import EACH_FACTS
    from monitor.home_count_summary import HOME_COUNTS

    return HOME_COUNTS, EACH_FACTS


class Command(BaseCommand):
    help = "Refresh saved homepage counts and Each post facts independently."

    def handle(self, *args, **options):
        results = {}
        failures = []
        for definition in registered_definitions():
            try:
                results[definition.dataset_key] = refresh_materialization(definition)
            except Exception as error:  # noqa: BLE001 -- report failure, then attempt the next dataset.
                failures.append(definition.dataset_key)
                results[definition.dataset_key] = {
                    "status": "unavailable", "error": type(error).__name__,
                }
        self.stdout.write(json.dumps(results, sort_keys=True))
        if failures:
            raise CommandError("Materialization refresh failed for: " + ", ".join(failures))
