"""Retired country/region operation; shared places use source-backed migrations."""

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Retired: country/region columns are replaced by shared geolocation IDs"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--target")
        parser.add_argument("--confirm-database")
        parser.add_argument("--recovery-receipt")
        parser.add_argument("--chunk-size", type=int)
        parser.add_argument("--json-report")
        parser.add_argument("--markdown-report")

    def handle(self, **options):
        raise CommandError(
            "Retired country/region operation. Use the current geolocation migrations "
            "for cutover and import_geolocations for explicit provider refresh. "
            "Existing source evidence is preserved; unresolved references remain NULL."
        )
