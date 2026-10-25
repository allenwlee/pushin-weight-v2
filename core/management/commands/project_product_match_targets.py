"""Copy frozen historical product match targets without provider calls."""

from django.core.management.base import BaseCommand, CommandError

from core.collection_storage_migration import (
    product_match_target_mismatch_counts,
    project_product_match_targets_batch,
)


class Command(BaseCommand):
    help = "Pin historical product-match scopes to existing typed subjects"

    def add_arguments(self, parser):
        parser.add_argument("--after-id", type=int, default=0)
        parser.add_argument("--batch-size", type=int, default=200)
        parser.add_argument("--max-batches", type=int, default=1)
        parser.add_argument("--verify-only", action="store_true")

    def handle(self, *args, **options):
        if options["verify_only"]:
            invalid, mismatch = product_match_target_mismatch_counts()
            self.stdout.write(f"invalid_ownership={invalid} target_mismatches={mismatch}")
            if invalid or mismatch:
                raise CommandError("product target copy incomplete")
            return
        if options["max_batches"] < 1:
            raise CommandError("max-batches must be positive")
        last_id = options["after_id"]
        scanned = updated = 0
        exhausted = False
        for _ in range(options["max_batches"]):
            result = project_product_match_targets_batch(
                after_id=last_id, batch_size=options["batch_size"]
            )
            last_id = result.last_id
            scanned += result.scanned
            updated += result.updated
            if not result.scanned:
                exhausted = True
                break
        self.stdout.write(
            f"scope_scanned={scanned} target_updated={updated} "
            f"next_after_id={last_id} exhausted={str(exhausted).lower()}"
        )
