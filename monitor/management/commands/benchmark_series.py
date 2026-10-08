import json

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError

from core.benchmark_attribution import enforce_use
from core.benchmark_metric_series import build_comparison
from core.models import MetricCollectionContract


class Command(BaseCommand):
    help = "Read a frozen benchmark comparison as JSON; no provider calls or writes."

    def add_arguments(self, parser):
        parser.add_argument("--contract", required=True)
        parser.add_argument("--preset", required=True)
        parser.add_argument(
            "--isolated-review",
            action="store_true",
            help="Internal review output only; not public redistribution",
        )
        parser.add_argument("--start-date")
        parser.add_argument("--end-date")

    def handle(self, *args, **options):
        try:
            contract = MetricCollectionContract.objects.get(pk=options["contract"])
            result = build_comparison(
                contract, options["preset"], options["start_date"], options["end_date"]
            )
            enforce_use(
                contract,
                result,
                "isolated_review" if options["isolated_review"] else "numeric_export",
                isolated_review=options["isolated_review"],
            )
        except (ObjectDoesNotExist, ValueError, PermissionError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, indent=2, allow_nan=False))
