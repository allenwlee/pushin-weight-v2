"""Operator-controlled import of legacy timing correction histories."""

from django.core.management.base import BaseCommand, CommandError

from core.collection_timing_import import import_legacy_timing_batch


class Command(BaseCommand):
    help = "Copy historical timing before/after images into typed correction rows"

    def add_arguments(self, parser):
        parser.add_argument("--after-id", type=int, default=0)
        parser.add_argument("--batch-size", type=int, default=100)
        parser.add_argument("--max-batches", type=int, default=1)

    def handle(self, *args, **options):
        if options["max_batches"] < 1:
            raise CommandError("max-batches must be positive")
        last_id = options["after_id"]
        scanned = selected = inserted = 0
        for _ in range(options["max_batches"]):
            result = import_legacy_timing_batch(
                after_id=last_id, batch_size=options["batch_size"]
            )
            last_id = result.last_observation_id
            scanned += result.scanned_observations
            selected += result.selected_corrections
            inserted += result.inserted_corrections
            if not result.scanned_observations:
                break
        self.stdout.write(
            f"scanned_observations={scanned} selected_corrections={selected} "
            f"inserted_corrections={inserted} next_after_id={last_id}"
        )
