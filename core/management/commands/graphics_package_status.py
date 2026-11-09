"""Inspect a Graphics package without triggering work or provider calls."""

import json

from django.core.management.base import BaseCommand, CommandError

from core.models import OriginalContent, OriginalContentRun
from monitor.editorial.graphics_status import graphics_status


class Command(BaseCommand):
    help = 'Show a Graphics run and its revision-bound editorial review.'

    def add_arguments(self, parser):
        parser.add_argument('--run-id', type=int, required=True)

    def handle(self, *args, **options):
        try:
            result = graphics_status(options['run_id'])
        except (OriginalContentRun.DoesNotExist, OriginalContent.DoesNotExist) as exc:
            raise CommandError('Graphics package not found') from exc
        self.stdout.write(json.dumps(result, sort_keys=True))
