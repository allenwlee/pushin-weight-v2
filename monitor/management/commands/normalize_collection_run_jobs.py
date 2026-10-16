"""Catch old-revision writes after the compatible rollout, without providers."""

from importlib import import_module

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Link jobless runs to inactive archival jobs; reject instruction mismatches."

    def add_arguments(self, parser):
        parser.add_argument("--purpose", choices=["metric", "catalog", "content"])

    def handle(self, *args, **options):
        migration = import_module("core.migrations.0088_archive_run_instructions")
        with connection.schema_editor(atomic=False) as editor:
            migration.archive_run_instructions(
                apps,
                editor,
                purposes=[options["purpose"]] if options["purpose"] else None,
            )
        self.stdout.write(
            "Collection run instructions checked and jobless runs archived."
        )
