"""Provider-free maintenance of the registered dashboard materializations."""

import json

from django.core.management.base import BaseCommand, CommandError

from core.materializations import refresh_materialization, sqlstate


def registered_definitions():
    from monitor.each_chart_facts import EACH_FACTS
    from monitor.home_count_summary import HOME_COUNTS
    from monitor.home_sentiment_counts import HOME_CLASSIFICATION

    return HOME_COUNTS, EACH_FACTS, HOME_CLASSIFICATION


class Command(BaseCommand):
    help = "Refresh saved homepage counts and Each post facts independently."

    def format_results(self, results):
        return results

    def handle(self, *args, **options):
        from monitor.home_sentiment_counts import HOME_CLASSIFICATION

        results = {}
        failures = []
        for definition in registered_definitions():
            try:
                results[definition.dataset_key] = refresh_materialization(definition)
                if (definition.dataset_key == HOME_CLASSIFICATION.dataset_key
                        and results[definition.dataset_key]['status'] == 'unavailable'):
                    # Rolling deploys and rollback can remove newer projections.
                    from monitor.home_sentiment_counts import HOME_SENTIMENT, HOME_SENTIMENT_V1

                    for fallback in (HOME_SENTIMENT, HOME_SENTIMENT_V1):
                        result = refresh_materialization(fallback)
                        if result['status'] != 'unavailable':
                            results[definition.dataset_key] = {
                                **result, 'fallback_dataset': fallback.dataset_key,
                            }
                            break
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
