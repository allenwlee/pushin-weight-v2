"""Reconcile the curated Twitter list into canonical account membership."""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from monitor.list_membership import reconciliation_due, run_due_reconciliation
from monitor.run_lock import harvest_writer_lock
from x_monitor.apify import TwitterApiClient
from x_monitor.config import load_config
from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose


class Command(BaseCommand):
    help = "Reconcile Twitter list members without changing the Call A query."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--list-id", type=int, default=None)
        parser.add_argument("--force", action="store_true")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options) -> None:
        cfg = load_config(Path("config.yaml"))
        list_id = options["list_id"] or cfg.x_monitor_list_id
        if list_id is None:
            raise CommandError("Twitter list ID is not configured")
        due = reconciliation_due(
            list_id=int(list_id),
            interval_hours=cfg.harvest.list_membership.reconcile_interval_hours,
        )
        if options["dry_run"]:
            self.stdout.write(
                f"Twitter list {list_id}: reconciliation "
                f"{'due' if due else 'not due'} (dry run)"
            )
            return

        with harvest_writer_lock(
            execution_mode="list_membership",
            entrypoint="management.sync_twitter_list_members",
        ) as lease:
            if not lease.acquired:
                self.stderr.write("List reconciliation skipped: harvest lock is held.")
                return
            result = run_due_reconciliation(
                api=TwitterApiClient.from_env(
                    TwitterApiCredentialPurpose.ON_DEMAND
                ),
                cfg=cfg,
                list_id=int(list_id),
                deadline=cfg.harvest.start_deadline(),
                run_id="manual-list-sync",
                force=bool(options["force"]),
            )
        self.stdout.write(
            f"Twitter list {list_id}: status={result.status} "
            f"activated={result.activated} deactivated={result.deactivated}"
        )
