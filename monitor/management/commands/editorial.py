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
            "action", choices=["preview", "status", "replay", "run", "picture", "poll", "chatter"]
        )
        parser.add_argument("--cutoff", help="Aware ISO-8601 cutoff; defaults to now")
        parser.add_argument("--assessment", type=int)
        parser.add_argument(
            "--kind", choices=["atomic", "current_headline", "chatter", "pulse"]
        )
        parser.add_argument("--content-id")
        parser.add_argument("--picture-id")
        parser.add_argument("--execute", action="store_true")
        parser.add_argument("--chatter-run", type=int, help="Resume saved Chatter stages without resending ambiguous calls")
        parser.add_argument("--chatter-trial-scope", help="Reconciled existing validation budget identity")
        parser.add_argument("--chatter-trial-limit-usd", type=float)
        parser.add_argument("--chatter-trial-carry-usd", type=float, help="Reconciled charges/reservations already consumed")

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
                from core.models import OriginalContentRun
                from monitor.editorial.chatter_accounting import chatter_call_report

                chatter = OriginalContentRun.objects.filter(workflow_key="chatter-discovery")
                if options["chatter_run"]:
                    chatter = chatter.filter(pk=options["chatter_run"])
                    if not chatter.exists():
                        raise ValueError("Chatter run does not exist")
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
                    "chatter": [chatter_call_report(run.pk) for run in chatter.order_by("-pk")[:5]],
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
                if action == "chatter":
                    trial_values = [options[key] for key in ("chatter_trial_scope", "chatter_trial_limit_usd", "chatter_trial_carry_usd")]
                    if any(value is not None for value in trial_values):
                        if any(value is None for value in trial_values):
                            raise CommandError("Supply scope, limit and reconciled carry together")
                        from monitor.editorial.config import EditorialConfig

                        data = cfg.model_dump(mode="json")
                        data["chatter"]["trial"] = dict(zip(("scope", "limit_usd", "carry_usd"), trial_values))
                        cfg = EditorialConfig.model_validate(data)
                    if cfg.chatter.trial is None:
                        raise CommandError("The private Chatter tester requires a finite trial profile")
                    if cfg.chatter.discovery_lane == "personalized-trends-v1" and not options["chatter_run"]:
                        from monitor.editorial.dispatch import dispatch_chatter_due_slot

                        result = dispatch_chatter_due_slot("operator-chatter:" + cutoff.isoformat(), cutoff, cfg=cfg, purpose="on-demand")
                        self.stdout.write(json.dumps(result, default=str, ensure_ascii=False))
                        return
                    from core.models import OriginalContentRun
                    from monitor.editorial.chatter_chain import (
                        resume_chatter_discovery,
                        review_chatter,
                        run_chatter,
                        select_chatter,
                        write_chatter,
                    )
                    pending = []
                    def queue(stage, *arguments):
                        pending.append((stage, arguments))
                    if options["chatter_run"]:
                        from monitor.editorial.chatter_trends import (
                            TRENDS_SCOPE,
                            validate_slot_authority,
                        )

                        run = OriginalContentRun.objects.get(pk=options["chatter_run"], workflow_key="chatter-discovery")
                        if run.scope_key == TRENDS_SCOPE:
                            validate_slot_authority(run, cfg=cfg, purpose="on-demand")
                        if run.discovery_state == "complete":
                            result = {"status": "resuming", "run_id": run.pk}
                            queue("select", run.pk)
                        else:
                            result = resume_chatter_discovery(run.pk, cfg=cfg, enqueue=queue)
                    else:
                        result = run_chatter({"schema_version": 1, "source_cycle_id": "operator-chatter",
                            "cycle_started_at": timezone.now().isoformat(), "cutoff": cutoff.isoformat(),
                            "dry_run": False, "credential_purpose": "on-demand"}, cfg=cfg, enqueue=queue)
                    stages = []
                    while pending:
                        stage, arguments = pending.pop(0)
                        if stage == "select":
                            stages.append(select_chatter(*arguments, cfg=cfg, enqueue=queue))
                        elif stage == "write":
                            stages.append(write_chatter(*arguments, cfg=cfg, enqueue=queue))
                        elif stage == "review":
                            stages.append(review_chatter(*arguments, cfg=cfg))
                    result["stages"] = stages
                elif action == "poll":
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
