"""Copy reviewed history import result-run links in bounded batches."""

from django.core.management.base import BaseCommand, CommandError

from core.collection_storage_migration import project_archive_import_links_batch


class Command(BaseCommand):
    help = "Project or verify historical archive-import result-run links"

    def add_arguments(self, parser):
        parser.add_argument("--after-id", type=int, default=0)
        parser.add_argument("--batch-size", type=int, default=200)
        parser.add_argument("--max-batches", type=int, default=1)
        parser.add_argument("--verify-only", action="store_true")

    def handle(self, *args, **options):
        if options["max_batches"] < 1:
            raise CommandError("max-batches must be positive")
        last_id = options["after_id"]
        scanned = updated = 0
        exhausted = False
        for _ in range(options["max_batches"]):
            try:
                result = project_archive_import_links_batch(
                    after_id=last_id, batch_size=options["batch_size"],
                    verify_only=options["verify_only"],
                )
            except ValueError as exc:
                raise CommandError(str(exc)) from exc
            last_id = result.last_id
            scanned += result.scanned
            updated += result.updated
            if result.scanned == 0:
                exhausted = True
                break
        self.stdout.write(
            f"archive_import_scanned={scanned} links_updated={updated} "
            f"next_after_id={last_id} exhausted={str(exhausted).lower()}"
        )
