"""Inspect existing native inventory instructions; execute explicitly."""

import json
import os

from django.core.management.base import BaseCommand, CommandError

from core.collection_capture import run_report_document
from core.collection_jobs import validate_job
from core.model_inventory import execute_model_inventory
from core.models import CollectionJob


class Command(BaseCommand):
    help = "Inspect a model-inventory job; --execute captures one bounded native catalog chunk."

    def add_arguments(self, parser):
        parser.add_argument("--job", required=True)
        parser.add_argument("--execute", action="store_true")

    def handle(self, *args, **options):
        try:
            job = CollectionJob.objects.get(pk=options["job"])
            validate_job(job)
            if not options["execute"]:
                self.stdout.write(
                    json.dumps({"job_id": str(job.pk), "state": job.state, "writes": 0})
                )
                return
            run = execute_model_inventory(
                job.pk, key=os.environ.get("BENCHMARK_OPENROUTER_API_KEY")
            )
            self.stdout.write(
                json.dumps(
                    {"run_id": str(run.pk), "status": run.status, "report": run_report_document(run)}
                )
            )
        except (ValueError, CollectionJob.DoesNotExist) as exc:
            raise CommandError(
                "inventory job is missing, inactive, claimed or unqualified"
            ) from exc
