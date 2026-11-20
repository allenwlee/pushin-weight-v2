"""Initialize the configured Pulse control document explicitly."""
import json

from django.core.management.base import BaseCommand, CommandError

from monitor.pulse_control import (
    PulseControlConflict,
    PulseControlUnavailable,
    initialize,
)


class Command(BaseCommand):
    help = 'Initialize Pulse control once; an existing document is never replaced.'

    def add_arguments(self, parser):
        parser.add_argument('--state', choices=('running', 'stopped'), required=True)
        parser.add_argument('--actor', required=True)
        parser.add_argument('--reason', required=True)

    def handle(self, *args, **options):
        try:
            result = initialize(state=options['state'], actor=options['actor'], reason=options['reason'])
        except (PulseControlConflict, PulseControlUnavailable, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps({'status': result['status'], 'desired_revision': result['desired_revision']}))
