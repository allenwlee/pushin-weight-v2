import json
from pathlib import Path

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError

from core.benchmark_metric_history import import_history


class Command(BaseCommand):
    help = "Validate bounded historical source evidence; --apply writes shared numeric history."

    def add_arguments(self, parser):
        parser.add_argument("manifest")
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        try:
            path = Path(options["manifest"])
            if path.stat().st_size > 32 * 1024 * 1024:
                raise ValueError("history manifest exceeds 32MiB")
            manifest = json.loads(path.read_text())
            result = import_history(manifest, apply=options["apply"])
            if options["apply"]:
                result = {
                    "applied": True,
                    "run_id": str(result.pk),
                    "status": result.status,
                    "observations": result.observations.count(),
                }
            self.stdout.write(json.dumps(result))
            if result.get("status") in {"failed", "aborted"}:
                raise CommandError(
                    "historical import contains no usable selected measurements"
                )
        except (ValueError, KeyError, OSError, ObjectDoesNotExist) as exc:
            raise CommandError(str(exc)) from exc
