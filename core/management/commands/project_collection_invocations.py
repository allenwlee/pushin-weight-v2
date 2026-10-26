"""Recover typed attempts from shared-collector run invocation receipts."""

from django.core.management.base import BaseCommand, CommandError

from core.collection_storage_migration import project_run_invocations_batch


class Command(BaseCommand):
    help = "Copy or verify ordered run invocations, including archived catalog receipts"

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=200)
        parser.add_argument("--max-batches", type=int, default=25)
        parser.add_argument("--verify-only", action="store_true")

    def handle(self, *args, **options):
        maximum = options["max_batches"]
        if maximum < 1:
            raise CommandError("max-batches must be positive")
        after_id = None
        scanned = inserted = updated = 0
        for _ in range(maximum):
            try:
                batch = project_run_invocations_batch(
                    after_id=after_id,
                    batch_size=options["batch_size"],
                    verify_only=options["verify_only"],
                )
            except ValueError as exc:
                raise CommandError(str(exc)) from exc
            if not batch.scanned:
                self.stdout.write(
                    f"shared invocation copy complete: scanned={scanned} "
                    f"inserted={inserted} updated={updated}"
                )
                return
            scanned += batch.scanned
            inserted += batch.inserted
            updated += batch.updated
            after_id = batch.last_id
        raise CommandError(
            f"invocation scan incomplete after {maximum} batches; "
            f"scanned={scanned} inserted={inserted} updated={updated}; rerun from the beginning"
        )
