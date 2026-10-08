import json

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError

from core.benchmark_metric_operations import collection_health
from core.models import MetricCollectionContract


class Command(BaseCommand):
    help = "Report benchmark retrieval, publication and coverage health without writes."

    def add_arguments(self, parser):
        parser.add_argument("--contract", required=True)

    def handle(self, *args, **options):
        try:
            contract = MetricCollectionContract.objects.get(pk=options["contract"])
        except (ObjectDoesNotExist, ValueError) as exc:
            raise CommandError("Unknown collection contract") from exc
        self.stdout.write(json.dumps(collection_health(contract), indent=2))
