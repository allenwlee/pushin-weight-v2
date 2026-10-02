"""Preview, then explicitly apply a reviewed identity correction."""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder

from core.person_identity_corrections import correct_identity


class Command(BaseCommand):
    help = "Preview or apply a reviewed account confirmation, merge, or selective split"

    def add_arguments(self, parser):
        parser.add_argument("kind", choices=["confirm_account", "merge", "split"])
        parser.add_argument("--source", required=True)
        parser.add_argument("--target", required=True)
        parser.add_argument("--reviewer", required=True)
        parser.add_argument("--reason", required=True)
        parser.add_argument("--request-key", required=True)
        parser.add_argument("--account-id")
        parser.add_argument(
            "--selection",
            type=Path,
            help="JSON file containing selected row IDs for a split",
        )
        parser.add_argument("--apply", action="store_true")

    def handle(self, **options):
        try:
            selection = (
                json.loads(options["selection"].read_text())
                if options["selection"]
                else None
            )
            result = correct_identity(
                kind=options["kind"],
                source_id=options["source"],
                target_id=options["target"],
                reviewer=options["reviewer"],
                reason=options["reason"],
                request_key=options["request_key"],
                account_id=options["account_id"],
                selection=selection,
                apply=options["apply"],
            )
        except (ValueError, OSError) as exc:
            raise CommandError(str(exc)) from exc
        if not isinstance(result, dict):
            result = {
                "applied": True,
                "correction_id": result.pk,
                "changes": result.changes,
            }
        self.stdout.write(
            json.dumps(result, cls=DjangoJSONEncoder, ensure_ascii=False, indent=2)
        )
