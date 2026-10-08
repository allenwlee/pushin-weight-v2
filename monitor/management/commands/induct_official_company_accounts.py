"""Owner-authorized cohort settlement shares the existing guarded registration path."""

import json
import time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.official_company_induction import induce_accounts, validate_manifest
from core.official_company_lock import official_company_writer_lock
from monitor.run_lock import harvest_writer_lock
from x_monitor.config import load_config


class Command(BaseCommand):
    help = "Settle an explicitly approved bounded cohort and enqueue Call A list additions."

    def add_arguments(self, parser):
        parser.add_argument("manifest")
        parser.add_argument("--expected-count", required=True, type=int)
        parser.add_argument("--seconds", type=int, default=90)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--config", default="config.yaml")

    def handle(self, *args, **options):
        path = Path(options["manifest"])
        if path.stat().st_size > 2 * 1024 * 1024 or not 5 <= options["seconds"] <= 120:
            raise CommandError("manifest exceeds 2MiB or seconds outside5..120")
        manifest = json.loads(path.read_text())
        try:
            policy = validate_manifest(
                manifest, expected_count=options["expected_count"]
            )
        except (TypeError, ValueError, KeyError) as exc:
            raise CommandError(str(exc)) from None
        if options["dry_run"]:
            self.stdout.write(
                json.dumps(
                    {
                        "policy": policy,
                        "requested": len(manifest["accounts"]),
                        "writes": False,
                    }
                )
            )
            return
        cfg = load_config(Path(options["config"])).official_company
        if not cfg.enabled:
            raise CommandError("official company extraction is disabled")
        context = {
            "execution_mode": "manual",
            "entrypoint": "owner-cohort-induction",
            "run_id": policy,
        }
        with harvest_writer_lock(**context) as harvest:
            if not harvest.acquired:
                self.stdout.write(json.dumps({"status": "writer_busy"}))
                return
            with official_company_writer_lock(**context) as discovery:
                if not discovery.acquired:
                    self.stdout.write(json.dumps({"status": "discovery_busy"}))
                    return
                result = induce_accounts(
                    manifest,
                    cfg=cfg,
                    expected_count=options["expected_count"],
                    deadline=time.monotonic() + options["seconds"],
                )
        self.stdout.write(json.dumps(result))
