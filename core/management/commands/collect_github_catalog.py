"""Inspect by default; execute only an explicitly activated, bounded DB job."""

import json
import os

from django.core.management.base import BaseCommand, CommandError

from core.collection_jobs import validate_job
from core.github_catalog import execute_github_catalog
from core.models import CollectionJob


class Command(BaseCommand):
    help = "Inspect a GitHub collection job; --execute runs one bounded invocation."

    def add_arguments(self, parser):
        parser.add_argument("--job", required=True)
        parser.add_argument("--execute", action="store_true")

    def handle(self, *args, **options):
        try:
            job = CollectionJob.objects.get(pk=options["job"])
            validate_job(job)
            if job.operation != "github_catalog":
                raise ValueError("GitHub catalog job required")
            if not options["execute"]:
                self.stdout.write(
                    json.dumps(
                        {
                            "job_id": str(job.pk),
                            "state": job.state,
                            "definition_sha256": job.definition_sha256,
                            "budgets": job.definition["budgets"],
                            "writes": 0,
                        }
                    )
                )
                return
            run = execute_github_catalog(
                job.pk, key=os.environ.get("PUSHINWEIGHT_GITHUB_API_TOKEN")
            )
            self.stdout.write(
                json.dumps(
                    {"run_id": str(run.pk), "status": run.status, "report": run.report}
                )
            )
        except (ValueError, CollectionJob.DoesNotExist) as exc:
            raise CommandError(
                "GitHub job is missing, unqualified, paused or already claimed"
            ) from exc
