"""Run a finite manual page of due product-release acquisition jobs."""

import json

import httpx
from django.core.management.base import BaseCommand, CommandError

from core.product_release_acquisition import drain_due_hf_acquisitions


class Command(BaseCommand):
    help = "Preview due release acquisition jobs; contact providers only with --execute."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=10)
        parser.add_argument("--job", dest="job_ids", action="append", help="Select a specific job UUID; repeatable")
        parser.add_argument("--execute", action="store_true")

    def handle(self, *args, **options):
        try:
            with httpx.Client(follow_redirects=False, trust_env=False) as client:
                result = drain_due_hf_acquisitions(
                    client=client, limit=options["limit"], execute=options["execute"],
                    job_ids=options["job_ids"],
                )
        except ValueError as error:
            raise CommandError(str(error)) from error
        result["mode"] = "execute" if options["execute"] else "dry_run"
        self.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True))
