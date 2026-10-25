"""Copy scope/rare-hit membership from saved receipts without provider calls."""

from django.core.management.base import BaseCommand, CommandError

from core.collection_storage_migration import (
    project_scope_rare_hits_batch,
    scope_rare_hit_mismatch_counts,
)


class Command(BaseCommand):
    help = "Copy historical X scope and rare-type hit memberships"

    def add_arguments(self, parser):
        parser.add_argument("--after-id", type=int, default=0)
        parser.add_argument("--batch-size", type=int, default=200)
        parser.add_argument("--max-batches", type=int, default=1)
        parser.add_argument("--verify-only", action="store_true")

    def handle(self, *args, **options):
        if options["verify_only"]:
            missing, extra = scope_rare_hit_mismatch_counts()
            self.stdout.write(f"missing_pairs={missing} extra_pairs={extra}")
            if missing or extra:
                raise CommandError("rare hit membership copy incomplete")
            return
        if options["max_batches"] < 1:
            raise CommandError("max-batches must be positive")
        last_id = options["after_id"]
        scanned = inserted = 0
        exhausted = False
        for _ in range(options["max_batches"]):
            result = project_scope_rare_hits_batch(
                after_id=last_id, batch_size=options["batch_size"]
            )
            last_id = result.last_id
            scanned += result.scanned
            inserted += result.inserted
            if not result.scanned:
                exhausted = True
                break
        self.stdout.write(
            f"scope_scanned={scanned} links_inserted={inserted} "
            f"next_after_id={last_id} exhausted={str(exhausted).lower()}"
        )
