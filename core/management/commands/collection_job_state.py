"""Explicit activation/cancellation; state changes never make provider requests."""

import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.collection_jobs import set_job_state, validate_job
from core.collection_scheduling import take_metric_authority
from core.models import CollectionJob


class Command(BaseCommand):
    help = "Inspect a state change; --apply persists it. Metric takeover is separate."

    def add_arguments(self, parser):
        parser.add_argument("--job", required=True)
        parser.add_argument(
            "--state", required=True, choices=["ready", "paused", "cancelled"]
        )
        parser.add_argument("--take-metric-authority", action="store_true")
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        try:
            job = CollectionJob.objects.get(pk=options["job"])
            validate_job(job)
            if options["apply"]:
                with transaction.atomic():
                    if options["take_metric_authority"]:
                        take_metric_authority(job.pk)
                    job = set_job_state(job.pk, options["state"])
            self.stdout.write(
                json.dumps(
                    {
                        "job_id": str(job.pk),
                        "state": job.state,
                        "requested_state": options["state"],
                        "applied": options["apply"],
                    }
                )
            )
        except (ValueError, CollectionJob.DoesNotExist) as exc:
            raise CommandError("invalid collection job state transition") from exc
