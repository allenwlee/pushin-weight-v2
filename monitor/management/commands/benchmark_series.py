import json

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError

from core.benchmark_metric_series import build_comparison
from core.models import MetricCollectionContract


class Command(BaseCommand):
    help = "Read a frozen benchmark comparison as JSON; no provider calls or writes."

    def add_arguments(self, parser):
        parser.add_argument("--contract", required=True)
        parser.add_argument("--preset", required=True)
        parser.add_argument("--start-date")
        parser.add_argument("--end-date")

    def handle(self, *args, **options):
        try:
            contract = MetricCollectionContract.objects.get(pk=options["contract"])
            result = build_comparison(
                contract, options["preset"], options["start_date"], options["end_date"]
            )
        except (ObjectDoesNotExist, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, indent=2, allow_nan=False))
