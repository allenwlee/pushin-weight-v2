"""Operator-controlled, provider-free RG6 collection evidence copy."""

from django.core.management.base import BaseCommand, CommandError

from core.collection_storage_migration import (
    LEGACY_FIELDS,
    archive_legacy_batch,
    stale_legacy_archive_count,
)


class Command(BaseCommand):
    help = "Archive old collection JSON in bounded, restartable database batches"

    def add_arguments(self, parser):
        parser.add_argument("table", choices=tuple(LEGACY_FIELDS))
        parser.add_argument("--batch-size", type=int, default=100)
        parser.add_argument("--max-batches", type=int, default=1)
        parser.add_argument("--verify-only", action="store_true")
        parser.add_argument("--repair-stale", action="store_true")

    def handle(self, *args, **options):
        table = options["table"]
        if options["verify_only"]:
            stale = stale_legacy_archive_count(table)
            self.stdout.write(f"{table}: {stale} missing or stale archive pointers")
            if stale:
                raise CommandError("collection archive reconciliation incomplete")
            return
        maximum = options["max_batches"]
        if maximum < 1:
            raise CommandError("max-batches must be positive")
        total = 0
        more = True
        for _ in range(maximum):
            result = archive_legacy_batch(
                table,
                batch_size=options["batch_size"],
                repair_stale=options["repair_stale"],
            )
            total += result.archived
            more = result.more_unarchived
            if not result.selected:
                break
        self.stdout.write(f"{table}: archived {total} rows; more_unarchived={more}")
