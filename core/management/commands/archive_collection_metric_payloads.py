"""Bounded archive copy for legacy metric run payloads."""

from django.core.management.base import BaseCommand, CommandError

from core.collection_storage_migration import archive_metric_payload_batch


class Command(BaseCommand):
    help = "Archive or verify legacy metric run payloads"

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=50)
        parser.add_argument("--max-batches", type=int, default=100)
        parser.add_argument("--verify-only", action="store_true")

    def handle(self, *args, **options):
        maximum = options["max_batches"]
        if maximum < 1:
            raise CommandError("max-batches must be positive")
        cursor = None
        scanned = archived = 0
        for _ in range(maximum):
            try:
                result = archive_metric_payload_batch(
                    after_id=cursor,
                    batch_size=options["batch_size"],
                    verify_only=options["verify_only"],
                )
            except ValueError as exc:
                raise CommandError(str(exc)) from exc
            if result.scanned == 0:
                self.stdout.write(
                    f"metric payload archive scan complete: scanned={scanned} "
                    f"archived={archived}"
                )
                return
            scanned += result.scanned
            archived += result.archived
            cursor = result.last_id
        raise CommandError(
            f"metric payload archive scan incomplete after {maximum} batches; "
            f"scanned={scanned} archived={archived}; rerun from the beginning"
        )
