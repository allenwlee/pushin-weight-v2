import json

from django.core.management.base import BaseCommand, CommandError

from core.person_affiliations import replace_claim


class Command(BaseCommand):
    help = "Preview or apply a reviewed replacement of one employment claim"

    def add_arguments(self, parser):
        parser.add_argument("old", type=int)
        parser.add_argument("replacement", type=int)
        parser.add_argument("--reviewer", required=True)
        parser.add_argument("--reason", required=True)
        parser.add_argument("--apply", action="store_true")

    def handle(self, **options):
        try:
            result = replace_claim(options["old"], options["replacement"],
                                   reviewer=options["reviewer"], reason=options["reason"],
                                   apply=options["apply"])
        except (KeyError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, ensure_ascii=False))
