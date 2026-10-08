import json
from pathlib import Path

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError

from core.measurement_taxonomy import configure_taxonomy, digest, prepare_taxonomy


class Command(BaseCommand):
    help = (
        "Validate a reviewed taxonomy snapshot; --apply persists an immutable version."
    )

    def add_arguments(self, parser):
        parser.add_argument("manifest")
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        try:
            path = Path(options["manifest"])
            if path.stat().st_size > 4 * 1024 * 1024:
                raise ValueError("taxonomy manifest exceeds 4MiB")
            spec = json.loads(path.read_text())
            snapshot = prepare_taxonomy(spec)
            result = {
                "applied": False,
                "version_hash": digest(snapshot),
                "subjects": len(snapshot["subjects"]),
            }
            if options["apply"]:
                result.update(applied=True, id=str(configure_taxonomy(spec).pk))
        except (ValueError, KeyError, OSError, ObjectDoesNotExist) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result))
