"""Bounded RG6 projection of published benchmark provenance scalars."""

from django.core.management.base import BaseCommand, CommandError

from core.collection_storage_migration import (
    project_benchmark_provenance_batch,
    project_run_ingestion_mode,
    provenance_mismatch_counts,
)


class Command(BaseCommand):
    help = "Copy JSON provenance flags into typed benchmark columns without provider calls"

    def add_arguments(self, parser):
        parser.add_argument("--after-id", type=int, default=0)
        parser.add_argument("--batch-size", type=int, default=500)
        parser.add_argument("--max-batches", type=int, default=1)
        parser.add_argument("--verify-only", action="store_true")

    def handle(self, *args, **options):
        if options["verify_only"]:
            runs, observations = provenance_mismatch_counts()
            self.stdout.write(
                f"run_mismatches={runs} observation_mismatches={observations}"
            )
            if runs or observations:
                raise CommandError("benchmark provenance copy incomplete")
            return
        if options["max_batches"] < 1:
            raise CommandError("max-batches must be positive")
        run_updates = project_run_ingestion_mode()
        last_id = options["after_id"]
        scanned = updated = 0
        for _ in range(options["max_batches"]):
            result = project_benchmark_provenance_batch(
                after_id=last_id, batch_size=options["batch_size"]
            )
            last_id = result.last_id
            scanned += result.scanned
            updated += result.updated
            if not result.scanned:
                break
        self.stdout.write(
            f"run_updates={run_updates} observation_scanned={scanned} "
            f"observation_updated={updated} next_after_id={last_id}"
        )
