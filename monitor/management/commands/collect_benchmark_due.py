"""Scheduler entry point, inert unless environment and reviewed sources enable it."""

import json
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.models import DataSource, MetricCollectionContract, MetricCollectionRun


class Command(BaseCommand):
    help = (
        "Inspect due collections; --apply also requires explicit collection activation."
    )

    def add_arguments(self, parser):
        parser.add_argument("--contract", required=True)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        if options["apply"] and not settings.BENCHMARK_COLLECTION_ENABLED:
            raise CommandError("Benchmark collection is disabled in this environment")
        try:
            contract = MetricCollectionContract.objects.get(pk=options["contract"])
        except (MetricCollectionContract.DoesNotExist, ValueError) as exc:
            raise CommandError("Unknown collection contract") from exc
        now = timezone.now()
        output = []
        for source, config in contract.source_configuration.items():
            enabled = (
                config.get("scheduling_enabled", False)
                and DataSource.objects.get(pk=source).enabled
            )
            latest = (
                MetricCollectionRun.objects.filter(contract=contract, source_id=source)
                .order_by("-started_at")
                .first()
            )
            interval = config.get("poll_seconds", 86400)
            due = enabled and (
                latest is None or (now - latest.started_at).total_seconds() >= interval
            )
            row = {"source": source, "enabled": enabled, "due": due, "applied": False}
            if due and options["apply"]:
                end = now.date() - timedelta(
                    days=config.get("completed_day_lag", 1)
                    if source == "openrouter"
                    else 0
                )
                start = (
                    end - timedelta(days=config.get("recheck_days", 7) - 1)
                    if source == "openrouter"
                    else end
                )
                bucket = int(now.timestamp()) // interval
                batch = uuid.uuid5(
                    uuid.NAMESPACE_URL, f"pw-benchmark:{contract.pk}:{source}:{bucket}"
                )
                call_command(
                    "collect_benchmark_metrics",
                    contract=str(contract.pk),
                    source=source,
                    start_date=start.isoformat(),
                    end_date=end.isoformat(),
                    batch_id=str(batch),
                    max_requests=config.get("max_requests", 20),
                    max_seconds=config.get("max_seconds", 120),
                    max_bytes=config.get("max_bytes", 8388608),
                    apply=True,
                    stdout=self.stdout,
                )
                row["applied"] = True
            output.append(row)
        self.stdout.write(json.dumps(output))
