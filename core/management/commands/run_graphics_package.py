"""Start a Graphics package for an already selected and stored story."""

import json

from django.core.management.base import BaseCommand, CommandError

from monitor.editorial import graphics_entry


class Command(BaseCommand):
    help = 'Run Graphics for one existing selected story and its saved source packet.'

    def add_arguments(self, parser):
        parser.add_argument('--content-id', type=int, required=True)
        parser.add_argument('--run-id', type=int, required=True)
        parser.add_argument('--locale', default='en', choices=['en', 'zh-cn', 'ja'])
        parser.add_argument('--per-story-usd')
        parser.add_argument('--daily-usd')

    def handle(self, *args, **options):
        try:
            result = graphics_entry.run_selected_story(
                content_id=options['content_id'], run_id=options['run_id'],
                locale=options['locale'], per_story_usd=options['per_story_usd'],
                daily_usd=options['daily_usd'],
            )
            self.stdout.write(json.dumps(result, sort_keys=True))
        except (TypeError, ValueError, RuntimeError) as exc:
            raise CommandError(str(exc)) from exc
