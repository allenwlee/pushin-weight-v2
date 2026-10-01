import json

from django.core.management.base import BaseCommand, CommandError

from core.staff_assets.manifest import import_manifest, load_manifest


class Command(BaseCommand):
    help = "Preview or apply sourced staff-intake/v1 records; no network calls."

    def add_arguments(self, parser):
        parser.add_argument("manifest")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--asset-root")

    def handle(self, *args, **options):
        try:
            result = import_manifest(
                load_manifest(options["manifest"]),
                apply=options["apply"],
                asset_root=options["asset_root"],
            )
        except (ValueError, KeyError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, ensure_ascii=False))
