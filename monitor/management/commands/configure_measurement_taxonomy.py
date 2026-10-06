import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.measurement_taxonomy import configure_taxonomy, digest, prepare_taxonomy


class Command(BaseCommand):
    help = (
        "Validate a reviewed taxonomy manifest; --apply persists an immutable version."
    )

    def add_arguments(self, parser):
        parser.add_argument("manifest")
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        try:
            spec = json.loads(Path(options["manifest"]).read_text())
            snapshot = prepare_taxonomy(spec)
            result = {
                "version_hash": digest(snapshot),
                "subjects": len(snapshot["subjects"]),
                "applied": False,
            }
            if options["apply"]:
                result.update(id=str(configure_taxonomy(spec).pk), applied=True)
            self.stdout.write(json.dumps(result))
        except (ValueError, KeyError) as exc:
            raise CommandError(str(exc)) from exc
