from __future__ import annotations

import json
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Count, Min, Q
from django.utils import timezone

from core.models import EnrichmentBudgetWindow, PostEnrichmentState
from monitor.enrichment_queue import stage_due_q


class Command(BaseCommand):
    help = "Report scheduled enrichment arrivals, completions, debt and retry causes."

    def handle(self, *args, **options):
        now = timezone.now()
        states = PostEnrichmentState.objects.filter(source_collection_job__isnull=True)
        pending = states.filter(
            Q(translation_status="pending") | Q(classification_status="pending")
        )
        due = pending.filter(
            stage_due_q("translation", now) | stage_due_q("classification", now)
        )
        completed = states.filter(
            translation_status="succeeded", classification_status="succeeded"
        )
        receipt = {
            "observed_at": now.isoformat(),
            "pending_posts": pending.count(),
            "due_posts": due.count(),
            "future_retry_posts": pending.exclude(pk__in=due.values("pk")).count(),
            "leased_posts": pending.filter(claim_expires_at__gt=now).count(),
            "oldest_pending_created_at": pending.aggregate(value=Min("created_at"))[
                "value"
            ],
            "arrivals_last_hour": states.filter(
                created_at__gte=now - timedelta(hours=1)
            ).count(),
            "completed_last_hour": completed.filter(
                updated_at__gte=now - timedelta(hours=1)
            ).count(),
            "older_than_30_minutes_incomplete": states.filter(
                created_at__lt=now - timedelta(minutes=30)
            )
            .exclude(pk__in=completed.values("pk"))
            .count(),
            "by_brand": list(
                pending.values("post__brands__brand_id")
                .annotate(posts=Count("pk", distinct=True))
                .order_by("post__brands__brand_id")
            ),
            "stage_errors": {
                stage: list(
                    states.exclude(**{f"{stage}_error_code": ""})
                    .values(f"{stage}_status", f"{stage}_error_code")
                    .annotate(posts=Count("pk"))
                    .order_by("-posts")
                )
                for stage in ("translation", "classification")
            },
            "budgets": list(
                EnrichmentBudgetWindow.objects.filter(ends_at__gt=now).values(
                    "id",
                    "scope",
                    "ends_at",
                    "request_limit",
                    "reserved_requests",
                    "usd_limit",
                    "reserved_usd",
                    "config_fingerprint",
                )
            ),
        }
        self.stdout.write(json.dumps(receipt, sort_keys=True, default=str))
