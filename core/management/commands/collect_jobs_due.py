"""Read persisted scheduling decisions; no dispatch without --execute."""

import json

import httpx
from django.core.management.base import BaseCommand, CommandError

from core.collection_budgets import invocation_budget
from core.collection_scheduling import dispatch_due


class Command(BaseCommand):
    help = "Inspect shared due jobs; --execute uses one finite invocation budget."

    def add_arguments(self, parser):
        parser.add_argument("--execute", action="store_true")
        parser.add_argument("--job", default=None)
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--max-requests", type=int, default=20)
        parser.add_argument("--max-seconds", type=int, default=120)
        parser.add_argument("--max-bytes", type=int, default=8388608)

    def handle(self, *args, **options):
        try:
            if options["execute"]:
                with httpx.Client(trust_env=False) as client:
                    budget = invocation_budget(
                        client,
                        requests=options["max_requests"],
                        seconds=options["max_seconds"],
                        max_bytes=options["max_bytes"],
                    )
                    rows = dispatch_due(
                        execute=True,
                        budget=budget,
                        job_id=options["job"],
                        limit=options["limit"],
                    )
            else:
                rows = dispatch_due(job_id=options["job"], limit=options["limit"])
            self.stdout.write(json.dumps(rows))
        except ValueError as exc:
            raise CommandError(
                "invalid shared collection instruction or budget"
            ) from exc
