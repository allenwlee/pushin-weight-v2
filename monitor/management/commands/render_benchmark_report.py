from pathlib import Path

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError

from core.benchmark_attribution import enforce_use
from core.benchmark_metric_report import report_from_comparison
from core.benchmark_metric_series import build_comparison
from core.models import MetricCollectionContract
from scripts.benchmark_download_collector.report import render_report


class Command(BaseCommand):
    help = "Save the shared database series as an offline four-panel HTML report."

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
        parser.add_argument("--output", required=True)

    def handle(self, *args, **options):
        try:
            contract = MetricCollectionContract.objects.get(pk=options["contract"])
            comparison = build_comparison(
                contract, options["preset"], options["start_date"], options["end_date"]
            )
            enforce_use(
                contract,
                comparison,
                "isolated_review" if options["isolated_review"] else "numeric_export",
                isolated_review=options["isolated_review"],
            )
            render_report(report_from_comparison(comparison), Path(options["output"]))
        except (ObjectDoesNotExist, ValueError, OSError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(str(options["output"]))
