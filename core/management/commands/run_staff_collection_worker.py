import json
import os
import time
import uuid

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

from core.staff_assets.arrivals import catch_up
from core.staff_assets.providers import SerpApiBaidu
from core.staff_assets.worker import run_once


class Command(BaseCommand):
    help = "Poll the independent staff queue. Network access is disabled by default."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--enable-network", action="store_true")
        parser.add_argument("--provider", choices=["serpapi_baidu"])
        parser.add_argument("--per-person", type=int, default=0)
        parser.add_argument("--per-run", type=int, default=0)
        parser.add_argument("--per-day", type=int, default=0)
        parser.add_argument("--run-id", type=uuid.UUID)
        parser.add_argument("--max-seconds", type=int, default=3600)
        parser.add_argument("--list-id", type=int)
        parser.add_argument("--poll-seconds", type=int, default=15)

    def handle(self, *args, **options):
        network = options["enable_network"]
        if not 1 <= options["poll_seconds"] <= 60 or options["max_seconds"] < 1:
            raise CommandError(
                "Positive runtime and a poll interval of 1–60 seconds are required"
            )
        if network and not settings.STAFF_COLLECTION_NETWORK_ENABLED:
            raise CommandError(
                "STAFF_COLLECTION_NETWORK_ENABLED must explicitly enable collection"
            )
        if network and not settings.STAFF_MEDIA_DURABLE:
            raise CommandError(
                "Network worker requires configured durable shared staff media storage"
            )
        if options["provider"] and (
            not network
            or min(options["per_person"], options["per_run"], options["per_day"]) < 1
        ):
            raise CommandError(
                "Paid provider requires network enabled and explicit positive request caps"
            )
        provider = None
        if options["provider"]:
            key = os.environ.get("SERP_API_KEY") or os.environ.get("SERPAPI_API_KEY")
            if not key:
                raise CommandError("SerpApi credential is absent")
            provider = SerpApiBaidu(api_key=key)
        run_id = options["run_id"] or uuid.uuid4()
        deadline = time.monotonic() + options["max_seconds"]
        next_scan = 0
        while time.monotonic() < deadline:
            close_old_connections()
            if options["list_id"] and time.monotonic() >= next_scan:
                catch_up(list_id=options["list_id"])
                next_scan = time.monotonic() + 300
            result = run_once(
                run_id=run_id,
                provider=provider,
                allow_network=network,
                per_person=options["per_person"],
                per_run=options["per_run"],
                per_day=options["per_day"],
            )
            self.stdout.write(json.dumps({"run_id": str(run_id), **result}))
            if options["once"]:
                break
            time.sleep(options["poll_seconds"])
