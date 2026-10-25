"""Prepare reviewed reference data before migrating an older refresh candidate."""

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


class Command(BaseCommand):
    help = "Prepare approved unit references in a non-serving refresh candidate."

    def handle(self, *args, **options):
        executor = MigrationExecutor(connection)
        cutover = ("core", "0124_metric_unit_writer_cutover")
        if cutover in executor.loader.applied_migrations:
            return
        target = ("core", "0123_shared_definition_and_service_identities")
        if any(backwards for _, backwards in executor.migration_plan([target])):
            raise CommandError("Reference preparation cannot reverse migrations")
        call_command(
            "migrate", *target, interactive=False, verbosity=options["verbosity"]
        )
        # Only the hash-pinned, reviewed catalogue is seeded. Unknown units
        # still fail 0124; no value is inferred from untrusted source wording.
        call_command(
            "seed_shared_vocabulary",
            catalogue=["measurement_units"],
            verbosity=options["verbosity"],
        )
