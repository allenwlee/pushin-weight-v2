"""Copy and verify run-wide Arena publication dates without provider calls."""

from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from core.collection_storage_migration import project_arena_publication_batch


class Command(BaseCommand):
    help = "Preserve Arena publication dates as aggregate collection observations"

    def add_arguments(self, parser):
        parser.add_argument("--after-id", type=UUID)
        parser.add_argument("--batch-size", type=int, default=10)
        parser.add_argument("--max-batches", type=int, default=1)
        parser.add_argument("--verify-only", action="store_true")

    def handle(self, *args, **options):
        if options["max_batches"] < 1:
            raise CommandError("max-batches must be positive")
        last_id = options["after_id"]
        scanned = inserted = 0
        exhausted = False
        for _ in range(options["max_batches"]):
            result = project_arena_publication_batch(
                after_id=last_id,
                batch_size=options["batch_size"],
                verify_only=options["verify_only"],
            )
            last_id = result.last_id
            scanned += result.scanned
            inserted += result.inserted
            if not result.scanned:
                exhausted = True
                break
        self.stdout.write(
            f"mode={'verify' if options['verify_only'] else 'copy'} "
            f"runs_scanned={scanned} markers_inserted={inserted} "
            f"next_after_id={last_id} exhausted={str(exhausted).lower()}"
        )
