"""Sync production's Call A list members and X brand-account roles into xbackfiller."""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from monitor.backfill_list_roles import SyncRefused, sync


class Command(BaseCommand):
    help = (
        "Copy production's main-list members and X account roles from a saved "
        "read-only export into the dedicated backfill database. Dry run unless --execute."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--export",
            type=Path,
            required=True,
            help="saved output of scripts/backfill_list_roles_production.sql (read-only production export)",
        )
        parser.add_argument(
            "--execute",
            action="store_true",
            help="commit the writes when every proof passes; without it every write is rolled back",
        )

    def handle(self, *args, **options) -> None:
        try:
            report = sync(options["export"], execute=bool(options["execute"]))
        except SyncRefused as exc:
            raise CommandError(f"refused: {exc}") from exc
        self.stdout.write(json.dumps(report, ensure_ascii=False, sort_keys=True))
        if report["status"] == "proof_failed":
            raise CommandError("a proof failed; every write was rolled back and nothing was changed")
