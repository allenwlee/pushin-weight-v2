"""Export revised daily reports with their actual hourly retrieval evidence."""

import json

from django.core.management.base import BaseCommand, CommandError

from core.benchmark_attribution import enforce_use
from core.benchmark_metric_store import aware_instant
from core.benchmark_opencode import retained_checks
from core.measurement_taxonomy import require
from core.models import MetricCollectionContract, MetricObservation
from scripts.benchmark_download_collector.identity import days


class Command(BaseCommand):
    help = "Read OpenCode daily-total snapshots, including provisional current days; not hourly usage."

    def add_arguments(self, parser):
        parser.add_argument("--contract", required=True)
        parser.add_argument("--start-date", required=True)
        parser.add_argument("--end-date", required=True)
        parser.add_argument("--cutoff")
        parser.add_argument("--limit", type=int, default=1000)
        parser.add_argument("--isolated-review", action="store_true")

    def handle(self, *args, **opts):
        try:
            contract = MetricCollectionContract.objects.get(pk=opts["contract"])
            window = set(days(opts["start_date"], opts["end_date"]))
            require(1 <= opts["limit"] <= 10000, "snapshot export budget")
            enforce_use(
                contract,
                {"lines": [{"source": "opencode"}], "attributions": []},
                "isolated_review" if opts["isolated_review"] else "numeric_export",
                isolated_review=opts["isolated_review"],
            )
            checks = retained_checks(
                contract,
                cutoff=aware_instant(opts["cutoff"]) if opts["cutoff"] else None,
            )
            references = [
                (run, check, label, pk)
                for run, check in checks
                for label, pk in check["row_references"].items()
                if label in window
            ]
            require(
                len(references) <= opts["limit"],
                "snapshot export exceeds limit; narrow date range",
            )
            observations = {
                o.pk: o
                for o in MetricObservation.objects.filter(
                    pk__in={r[3] for r in references},
                    run__contract=contract,
                    run__source_id="opencode",
                ).prefetch_related("values__source_metric")
            }
            rows = []
            for run, check, label, pk in references:
                observation = observations[pk]
                rows.append(
                    {
                        "source_identifier": check["source_identifier"],
                        "date": label,
                        "endpoint_updated_at": check["updated_at"],
                        "retrieval_completed_at": run.completed_at.isoformat(),
                        "check_run_id": str(run.pk),
                        "observation_id": pk,
                        "first_observed_at": observation.observed_at.isoformat(),
                        "period_status": observation.source_metadata["period_status"],
                        "revision_anomaly": check.get("revision_anomaly"),
                        "traffic_scope": "opencode_go_and_free",
                        "values": [
                            {
                                "metric": v.source_metric.metric_key,
                                "value": str(v.integer_value),
                                "approximate": v.source_metric.metric_key
                                in {"unique_users", "sessions"},
                                "value_id": v.pk,
                                "window_start_at": v.window_start_at.isoformat()
                                if v.window_start_at
                                else None,
                                "window_end_at": v.window_end_at.isoformat()
                                if v.window_end_at
                                else None,
                                "temporal_status": v.temporal_status,
                            }
                            for v in observation.values.all()
                        ],
                    }
                )
            self.stdout.write(
                json.dumps(
                    {
                        "schema_version": 1,
                        "semantics": "Revised reported UTC-day totals; differences are not exact hourly usage.",
                        "rows": rows,
                    },
                    allow_nan=False,
                )
            )
        except (ValueError, KeyError, MetricCollectionContract.DoesNotExist) as exc:
            raise CommandError(str(exc)) from exc
