"""Import explicit places from pinned evidence, with opt-in bounded source refresh."""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.geolocations import (
    fetch_geonames_documents,
    import_geonames_documents,
    load_pinned_geonames,
)


class Command(BaseCommand):
    help = "Import selected GeoNames documents and required ancestors from a verified local bundle"

    def add_arguments(self, parser):
        parser.add_argument("--source-directory", type=Path, default=settings.BASE_DIR / "data" / "geonames")
        parser.add_argument("--geonames-id", action="append", type=int, help="Select explicit place roots")
        parser.add_argument("--fetch", action="store_true", help="Fetch the explicit IDs and missing ancestors before importing")
        parser.add_argument("--max-places", type=int, default=100, help="Bound optional network expansion")

    def handle(self, *args, **options):
        try:
            documents, metadata, roots = load_pinned_geonames(options["source_directory"])
            if options["fetch"]:
                if not options["geonames_id"]:
                    raise ValueError("--fetch requires explicit --geonames-id values")
                documents = fetch_geonames_documents(options["geonames_id"], max_places=options["max_places"])
            result = import_geonames_documents(
                documents, country_metadata=metadata,
                selected_ids=options["geonames_id"] or roots,
            )
        except (OSError, ValueError, KeyError) as error:
            raise CommandError(str(error)) from error
        self.stdout.write(self.style.SUCCESS(f"Imported/refreshed {len(result)} shared places"))
