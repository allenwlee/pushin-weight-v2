"""Read-only operator status for shared trend-narrative state."""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import TrendNarrative
from monitor.trend_narrative_projection import trend_narrative_state
from x_monitor.config import load_config


class Command(BaseCommand):
    help = "Show provider-free trend narrative freshness and attempt state."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options) -> None:
        config = load_config(Path("config.yaml")).headline_narrative
        now = timezone.now()
        windows = []
        for window_days in (1, 7, 30, 365):
            current = (
                TrendNarrative.objects.filter(
                    window_days=window_days,
                    is_current=True,
                )
                .prefetch_related("subjects")
                .first()
            )
            latest = (
                TrendNarrative.objects.filter(window_days=window_days)
                .order_by("-created_at", "-pk")
                .first()
            )
            state, checked_at = trend_narrative_state(
                current,
                window_days=window_days,
                config=config,
                now=now,
            )
            windows.append(
                {
                    "window_days": window_days,
                    "state": state,
                    "current_source_cycle_id": (
                        current.source_cycle_id if current else None
                    ),
                    "semantic_fingerprint": (
                        current.semantic_fingerprint if current else None
                    ),
                    "facts_as_of": _iso(current.facts_as_of if current else None),
                    "generated_at": _iso(current.generated_at if current else None),
                    "checked_at": _iso(checked_at),
                    "latest_checked_source_cycle_id": (
                        current.latest_checked_source_cycle_id if current else None
                    ),
                    "latest_status": latest.status if latest else None,
                    "output_schema_version": (
                        current.output_schema_version if current else None
                    ),
                    "selected_candidate_ids": (
                        current.selected_candidate_ids if current else []
                    ),
                    "subjects": _safe_subjects(current),
                    "call_slot_consumed": (
                        latest.call_slot_consumed if latest else False
                    ),
                    "transport_started": bool(latest and latest.transport_started_at),
                    "transport_completed": bool(
                        latest and latest.transport_completed_at
                    ),
                    "claim_owner": latest.claim_owner if latest else "",
                    "claim_fence": latest.claim_fence if latest else 0,
                    "claim_expires_at": _iso(
                        latest.claim_expires_at if latest else None
                    ),
                    "generated_at_latest": _iso(
                        latest.generated_at if latest else None
                    ),
                    "published_at_latest": _iso(
                        latest.published_at if latest else None
                    ),
                    "next_attempt_at": _iso(latest.next_attempt_at if latest else None),
                    "consecutive_failures": (
                        latest.consecutive_failures if latest else 0
                    ),
                    "error_code": latest.error_code if latest else "",
                    "provider": latest.provider if latest else config.provider,
                    "provider_host": (latest.provider_host if latest else "configured"),
                    "model": (
                        latest.resolved_llm_model_name if latest else config.model
                    ),
                    "prompt_version": (
                        latest.prompt_version if latest else config.prompt_version
                    ),
                    "publication_epoch": (
                        latest.publication_epoch if latest else config.publication_epoch
                    ),
                    "input_tokens": latest.input_tokens if latest else 0,
                    "output_tokens": latest.output_tokens if latest else 0,
                    "latency_ms": latest.latency_ms if latest else None,
                    "output_hash": latest.output_hash if latest else "",
                }
            )
        payload = {
            "control_revision": config.control_revision,
            "activation_state": config.activation_state,
            "serving_enabled": config.serving_enabled,
            "enqueue_enabled": config.enqueue_enabled,
            "provider_calls_enabled": config.provider_calls_enabled,
            "serving_active": config.serving_active,
            "enqueue_active": config.enqueue_active,
            "provider_calls_active": config.provider_calls_active,
            "windows": windows,
        }
        if options["as_json"]:
            self.stdout.write(json.dumps(payload, indent=2))
            return
        self.stdout.write(
            "headline controls "
            f"revision={config.control_revision} "
            f"activation={config.activation_state} "
            "requested["
            f"serving={config.serving_enabled} "
            f"enqueue={config.enqueue_enabled} "
            f"provider={config.provider_calls_enabled}] "
            "active["
            f"serving={config.serving_active} "
            f"enqueue={config.enqueue_active} "
            f"provider={config.provider_calls_active}]"
        )
        for row in windows:
            self.stdout.write(
                f"{row['window_days']}d {row['state']} "
                f"status={row['latest_status'] or '-'} "
                f"schema={row['output_schema_version'] or '-'} "
                f"subjects={len(row['subjects'])} "
                f"source={row['current_source_cycle_id'] or '-'} "
                f"checked={row['checked_at'] or '-'} "
                f"slot={int(row['call_slot_consumed'])} "
                f"transport={int(row['transport_started'])}/{int(row['transport_completed'])} "
                f"claim={row['claim_owner'] or '-'}:{row['claim_fence']} "
                f"failures={row['consecutive_failures']} "
                f"error={row['error_code'] or '-'}"
            )


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _safe_subjects(narrative: TrendNarrative | None) -> list[dict[str, object]]:
    """Expose identity/support diagnostics without private evidence IDs."""
    if narrative is None:
        return []
    return [
        {
            "position": subject.position,
            "support_type": subject.support_type,
            "entity_type": subject.entity_type,
            "identity_type": subject.identity_type,
            "key": subject.canonical_key_snapshot or None,
        }
        for subject in narrative.subjects.all()
    ]
