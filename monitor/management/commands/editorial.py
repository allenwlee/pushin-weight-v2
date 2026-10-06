"""Inspect/replay saved editorial decisions; provider work requires --execute."""

import json
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.models import EditorialAssessment, EditorialBudget
from monitor.editorial.config import load_editorial_config
from monitor.editorial.contracts import Decisions
from monitor.editorial.evidence import build_packet
from monitor.editorial.selection import aged_priority


class Command(BaseCommand):
    help = "Preview evidence, inspect spend, replay saved decisions, or explicitly run the editorial engine."

    def add_arguments(self, parser):
        parser.add_argument(
            "action", choices=["preview", "status", "replay", "run", "picture", "poll"]
        )
        parser.add_argument("--cutoff", help="Aware ISO-8601 cutoff; defaults to now")
        parser.add_argument("--assessment", type=int)
        parser.add_argument(
            "--kind", choices=["atomic", "current_headline", "chatter", "pulse"]
        )
        parser.add_argument("--content-id")
        parser.add_argument("--picture-id")
        parser.add_argument("--execute", action="store_true")

    def handle(self, *args, **options):
        cfg = load_editorial_config()
        try:
            cutoff = (
                datetime.fromisoformat(options["cutoff"])
                if options["cutoff"]
                else timezone.now()
            )
            if cutoff.utcoffset() is None:
                raise ValueError("cutoff requires timezone")
            action = options["action"]
            if action == "preview":
                result = build_packet(cutoff, cfg)
            elif action == "status":
                result = {
                    "generation_enabled": cfg.enabled,
                    "public_enabled": cfg.public_enabled,
                    "pictures": cfg.pictures,
                    "budgets": list(
                        EditorialBudget.objects.order_by("-day").values()[:7]
                    ),
                    "assessments": list(
                        EditorialAssessment.objects.order_by("-cutoff").values(
                            "id", "scope", "cutoff", "state", "outcome"
                        )[:20]
                    ),
                }
            elif action == "replay":
                row = EditorialAssessment.objects.get(pk=options["assessment"])
                decisions = Decisions.model_validate(row.decisions)
                result = {
                    "assessment": row.pk,
                    "cutoff": row.cutoff,
                    "coverage": row.packet.get("coverage", {}),
                    "events": [
                        {
                            "key": e.key,
                            "chatter": e.chatter,
                            "pulse": e.pulse,
                            "reason": e.reason,
                            "priority": aged_priority(
                                e.importance, e.occurred_at, cutoff, cfg
                            ),
                        }
                        for e in decisions.events
                    ],
                }
            else:
                if not options["execute"]:
                    raise CommandError(
                        "--execute is required for provider-capable work"
                    )
                if action == "poll":
                    if not options["picture_id"]:
                        raise CommandError("--picture-id is required")
                    from monitor.editorial.dispatch import dispatch_poll
                    from monitor.editorial.media import poll_derivative

                    polled = poll_derivative(options["picture_id"], cfg)
                    if polled.reschedule:
                        dispatch_poll(polled.picture.pk)
                    result = {
                        "state": polled.picture.state,
                        "picture_id": str(polled.picture.pk),
                    }
                elif action == "picture":
                    if not options["kind"] or not options["content_id"]:
                        raise CommandError("--kind and --content-id are required")
                    from monitor.editorial.bindings import picture_for_content

                    result = picture_for_content(options["kind"], options["content_id"])
                else:
                    from monitor.editorial.service import run_editorial

                    result = run_editorial(
                        {
                            "schema_version": 1,
                            "completed_at": cutoff.isoformat(),
                            "source_cycle_id": "operator",
                            "outcome": "completed",
                            "dry_run": False,
                        }
                    )
        except (ValueError, EditorialAssessment.DoesNotExist) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, default=str, ensure_ascii=False, indent=2))
