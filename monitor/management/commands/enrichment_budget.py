from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.models import EnrichmentBudgetWindow
from monitor.enrichment_budget import config_fingerprint
from x_monitor.config import load_config


class Command(BaseCommand):
    help = "Preview or explicitly create a fixed enrichment spending allowance."

    def add_arguments(self, parser):
        parser.add_argument("--scope", choices=["pilot", "scheduled"], required=True)
        parser.add_argument("--hours", type=int, required=True)
        parser.add_argument("--requests", type=int, required=True)
        parser.add_argument("--usd-limit", type=Decimal, required=True)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        if (
            not 1 <= options["hours"] <= 168
            or options["requests"] <= 0
            or not options["usd_limit"].is_finite()
            or options["usd_limit"] <= 0
        ):
            raise CommandError(
                "positive limits and a window of 1–168 hours are required"
            )
        if options["scope"] == "pilot" and options["requests"] > 1200:
            raise CommandError("pilot is capped at 1200 requests")
        now = timezone.now()
        window = EnrichmentBudgetWindow(
            scope=options["scope"],
            starts_at=now,
            ends_at=now + timedelta(hours=options["hours"]),
            request_limit=options["requests"],
            usd_limit=options["usd_limit"],
            config_fingerprint=config_fingerprint(load_config(Path("config.yaml"))),
        )
        window.full_clean()
        if options["apply"]:
            window.save(force_insert=True)
        self.stdout.write(
            json.dumps(
                {
                    "applied": options["apply"],
                    "window_id": str(window.pk),
                    "scope": window.scope,
                    "starts_at": now.isoformat(),
                    "ends_at": window.ends_at.isoformat(),
                    "requests": window.request_limit,
                    "usd_limit": str(window.usd_limit),
                    "config_fingerprint": window.config_fingerprint,
                },
                sort_keys=True,
            )
        )
