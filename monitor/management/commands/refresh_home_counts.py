"""Provider-free maintenance of the shared homepage count materialization."""

import json

from django.core.management.base import BaseCommand

from monitor.home_count_summary import refresh_home_counts


class Command(BaseCommand):
    help = "Refresh closed-day homepage counts when their UTC day or history changes."

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(refresh_home_counts(), sort_keys=True))
