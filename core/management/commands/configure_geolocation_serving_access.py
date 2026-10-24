"""Apply reviewed canonical-only grants using a separate owner connection."""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from core.geolocation_access import apply_serving_grants


class Command(BaseCommand):
    help = "Configure an existing dedicated serving login; no credentials are created or printed"

    def add_arguments(self, parser):
        parser.add_argument("--role", required=True)

    def handle(self, *args, **options):
        try:
            with transaction.atomic():
                report = apply_serving_grants(connection, options["role"])
        except ValueError as error:
            raise CommandError(str(error)) from error
        self.stdout.write(f"Configured canonical access for {report['role']}; checked {report['relations_checked']} relations")
