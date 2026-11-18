"""Freeze, inspect and explicitly process one official-company queue snapshot."""

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.official_company_queue_pass import (
    acknowledge_failure,
    freeze_queue,
    read_manifest,
    report,
    run_batch,
)


class Command(BaseCommand):
    help = "Work on one frozen official-company evaluation queue."

    def add_arguments(self, parser):
        parser.add_argument(
            "action", choices=("freeze", "report", "run", "acknowledge")
        )
        parser.add_argument("--manifest", required=True)
        parser.add_argument("--total-limit-usd")
        parser.add_argument("--limit", type=int, default=1)
        parser.add_argument("--seconds", type=int, default=60)
        parser.add_argument("--config", default="config.yaml")
        parser.add_argument("--attempt-id", type=int)
        parser.add_argument("--reason")

    def handle(self, *args, **opts):
        action = opts["action"]
        try:
            if action == "freeze":
                if opts["total_limit_usd"] is None:
                    raise ValueError("freeze requires --total-limit-usd")
                manifest = freeze_queue(
                    path=opts["manifest"], total_limit=Decimal(opts["total_limit_usd"])
                )
                result = {
                    "run_id": manifest["run_id"],
                    "cutoff": manifest["cutoff"],
                    "count": manifest["count"],
                    "sha256": manifest["sha256"],
                }
            else:
                if opts["total_limit_usd"] is not None:
                    raise ValueError("the saved run limit cannot be changed")
                manifest = read_manifest(opts["manifest"])
                if action == "report":
                    result = report(manifest)
                elif action == "acknowledge":
                    result = acknowledge_failure(
                        manifest,
                        attempt_id=opts["attempt_id"],
                        reason=opts["reason"],
                        acknowledgement_path=opts["manifest"]
                        + ".verification.json.acknowledged.json",
                    )
                else:
                    from core.official_company_discovery import build_discovery_call
                    from x_monitor.config import load_config

                    cfg = load_config(Path(opts["config"])).official_company
                    if not cfg.enabled:
                        raise ValueError("official-company evaluator is disabled")
                    result = run_batch(
                        manifest,
                        cfg=cfg,
                        call=build_discovery_call(cfg),
                        limit=opts["limit"],
                        seconds=opts["seconds"],
                        receipt_path=opts["manifest"] + ".verification.json",
                    )
        except (ValueError, InvalidOperation, OSError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result))
