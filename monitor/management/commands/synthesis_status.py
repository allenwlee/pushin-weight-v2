from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db.models import Count, Sum
from django.utils import timezone

from core.models import (
    PostSynthesisArtifact,
    PostSynthesisDailyBudget,
    PostSynthesisDemand,
)
from x_monitor.config import load_config


class Command(BaseCommand):
    help = "Show provider-free synthesis controls, backlog, and usage."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options) -> None:
        config = load_config(Path("config.yaml")).synthesis
        now = timezone.now()
        states = {
            row["state"]: row["count"]
            for row in PostSynthesisDemand.objects.values("state").annotate(
                count=Count("pk")
            )
        }
        oldest = (
            PostSynthesisDemand.objects.filter(
                state__in=["pending", "processing"]
            )
            .order_by("first_requested_at")
            .values_list("first_requested_at", flat=True)
            .first()
        )
        usage = PostSynthesisArtifact.objects.filter(
            completed_at__gte=now - timedelta(days=1)
        ).aggregate(input_tokens=Sum("input_tokens"), output_tokens=Sum("output_tokens"))
        budget = PostSynthesisDailyBudget.objects.filter(
            usage_date=now.date(),
            control_revision=config.control_revision,
            provider=config.provider,
            model=config.model,
        ).first()
        payload = {
            "control_revision": config.control_revision,
            "activation_state": config.activation_state,
            "provider_calls_enabled": config.provider_calls_enabled,
            "provider_calls_active": config.provider_calls_active,
            "demand_states": {
                state: states.get(state, 0)
                for state in PostSynthesisDemand.State.values
            },
            "queue_age_seconds": (
                max(0, int((now - oldest).total_seconds())) if oldest else None
            ),
            "artifacts": PostSynthesisArtifact.objects.count(),
            "current_artifacts": PostSynthesisArtifact.objects.filter(
                is_current=True
            ).count(),
            "tokens_24h": {
                "input": usage["input_tokens"] or 0,
                "output": usage["output_tokens"] or 0,
            },
            "daily_budget": {
                "request_cap": config.daily_request_cap,
                "reserved_requests": budget.reserved_requests if budget else 0,
                "input_token_cap": config.daily_input_token_cap,
                "reserved_input_tokens": (
                    budget.reserved_input_tokens if budget else 0
                ),
                "observed_input_tokens": (
                    budget.observed_input_tokens if budget else 0
                ),
                "output_token_cap": config.daily_output_token_cap,
                "reserved_output_tokens": (
                    budget.reserved_output_tokens if budget else 0
                ),
                "observed_output_tokens": (
                    budget.observed_output_tokens if budget else 0
                ),
                "pricing_version": config.pricing_version,
                "maximum_cost_usd": str(config.daily_cost_cap_usd),
            },
        }
        if options["as_json"]:
            self.stdout.write(json.dumps(payload, sort_keys=True))
            return
        self.stdout.write(
            f"synthesis active={int(config.provider_calls_active)} "
            f"pending={states.get('pending', 0)} "
            f"processing={states.get('processing', 0)} "
            f"failed={states.get('failed', 0)}"
        )
