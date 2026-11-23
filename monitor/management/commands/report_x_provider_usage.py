"""Report physical X provider attempts from the existing collection ledger."""
import json
from datetime import timedelta
from urllib.parse import urlsplit

from django.core.management.base import BaseCommand, CommandError
from django.db.models import (
    Avg,
    BigIntegerField,
    Count,
    DurationField,
    ExpressionWrapper,
    F,
    Q,
    Sum,
)
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.models import CollectionRequest


class Command(BaseCommand):
    help = "Summarize saved X request attempts by provider, endpoint and collection run."

    def add_arguments(self, parser):
        parser.add_argument("--since", required=True, help="ISO timestamp with UTC offset")
        parser.add_argument("--until", required=True, help="Exclusive ISO timestamp with UTC offset")

    def handle(self, **options):
        try:
            start, end = (parse_datetime(options[key]) for key in ("since", "until"))
        except ValueError as exc:
            raise CommandError("Invalid ISO timestamp.") from exc
        if (not start or not end or timezone.is_naive(start) or timezone.is_naive(end)
                or not timedelta(0) < end - start <= timedelta(days=7)):
            raise CommandError("Supply offset-aware timestamps covering at most seven days.")
        rows = CollectionRequest.objects.filter(
            attempt__run__job__source_id="x",
            receipt_kind="physical",
            started_at__gte=start,
            started_at__lt=end,
        ).values(
            "attempt__run_id", "scope_run__scope_key", "scope_run__coverage_state",
            "scope_run__requested_start_at", "scope_run__requested_end_at",
            "provider_source_id", "credential_purpose", "endpoint_url",
        ).annotate(
            sends=Count("pk", filter=~Q(transport_outcome__in=["pending", "unknown"])),
            unconfirmed=Count("pk", filter=Q(transport_outcome__in=["pending", "unknown"])),
            successful_http=Count("pk", filter=Q(http_status__gte=200, http_status__lt=300)),
            rate_limited=Count("pk", filter=Q(http_status=429)),
            unavailable=Count("pk", filter=Q(http_status=503)),
            timed_out=Count("pk", filter=Q(transport_outcome="timeout") | Q(error_code__in=[
                "Timeout", "ReadTimeout", "ConnectTimeout", "TimeoutError",
            ])),
            returned=Sum(Coalesce("returned_count", "raw_count", output_field=BigIntegerField())),
            returned_count_unknown=Count("pk", filter=Q(raw_count__isnull=True, returned_count__isnull=True)),
            mean_response_time=Avg(ExpressionWrapper(
                F("received_at") - F("started_at"), output_field=DurationField(),
            )),
        ).order_by("attempt__run_id", "scope_run__scope_key", "provider_source_id")
        for row in rows.iterator():
            row["provider_source_id"] = row["provider_source_id"] or "unknown"
            endpoint = urlsplit(row.pop("endpoint_url") or "")
            row["endpoint"] = endpoint.path
            self.stdout.write(json.dumps(row, default=str, sort_keys=True))
