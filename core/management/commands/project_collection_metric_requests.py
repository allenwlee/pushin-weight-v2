"""Bounded copy of legacy metric request dates and cursors."""

from django.core.management.base import BaseCommand, CommandError

from core.collection_storage_migration import project_metric_request_coordinates_batch


class Command(BaseCommand):
    help = "Project or verify metric request options on collection scope fields"

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=200)
        parser.add_argument("--max-batches", type=int, default=25)
        parser.add_argument("--verify-only", action="store_true")

    def handle(self, *args, **options):
        maximum = options["max_batches"]
        if maximum < 1:
            raise CommandError("max-batches must be positive")
        cursor = None
        scanned = updated = 0
        for _ in range(maximum):
            try:
                result = project_metric_request_coordinates_batch(
                    after_id=cursor,
                    batch_size=options["batch_size"],
                    verify_only=options["verify_only"],
                )
            except ValueError as exc:
                raise CommandError(str(exc)) from exc
            if result.scanned == 0:
                self.stdout.write(
                    f"metric request coordinate scan complete: scanned={scanned} "
                    f"updated={updated}"
                )
                return
            scanned += result.scanned
            updated += result.updated
            cursor = result.last_id
        raise CommandError(
            f"metric request coordinate scan incomplete after {maximum} batches; "
            f"scanned={scanned} updated={updated}; rerun from the beginning"
        )
