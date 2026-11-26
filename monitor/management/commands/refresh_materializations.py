"""Provider-free maintenance of the registered dashboard materializations."""

import json

from django.core.management.base import BaseCommand, CommandError

from core.materializations import refresh_materialization, sqlstate


def registered_definitions():
    from monitor.each_chart_facts import EACH_FACTS
    from monitor.home_count_summary import HOME_COUNTS
    from monitor.home_sentiment_counts import HOME_SENTIMENT

    return HOME_COUNTS, EACH_FACTS, HOME_SENTIMENT


class Command(BaseCommand):
    help = "Refresh saved homepage counts and Each post facts independently."

    def format_results(self, results):
        return results

    def handle(self, *args, **options):
        results = {}
        failures = []
        for definition in registered_definitions():
            try:
                results[definition.dataset_key] = refresh_materialization(definition)
                if (definition.dataset_key == 'home.post_sentiment_facts.v2'
                        and results[definition.dataset_key]['status'] == 'unavailable'):
                    # A rollback may remove v2 before all new workers stop.
                    from monitor.home_sentiment_counts import HOME_SENTIMENT_V1

                    results[definition.dataset_key] = {
                        **refresh_materialization(HOME_SENTIMENT_V1),
                        'fallback_dataset': HOME_SENTIMENT_V1.dataset_key,
                    }
            except Exception as error:  # noqa: BLE001 -- report failure, then attempt the next dataset.
                failures.append(definition.dataset_key)
                results[definition.dataset_key] = {
                    "status": "unavailable", "error": type(error).__name__,
                }
                if code := sqlstate(error):
                    results[definition.dataset_key]["sqlstate"] = code
        self.stdout.write(json.dumps(self.format_results(results), sort_keys=True))
        if failures:
            raise CommandError("Materialization refresh failed for: " + ", ".join(failures))
