import json

from django.core.management.base import BaseCommand

from core.staff_assets.dossier import export_dossier


class Command(BaseCommand):
    help = (
        "Export a private, printable HTML dossier and stored images from the database."
    )

    def add_arguments(self, parser):
        parser.add_argument("--brand", required=True)
        parser.add_argument("--output", required=True)

    def handle(self, *args, **options):
        self.stdout.write(
            json.dumps(
                export_dossier(brand_id=options["brand"], output=options["output"])
            )
        )
