"""Catch old-revision writes after the compatible rollout, without providers."""

from importlib import import_module

from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


class Command(BaseCommand):
    help = "Link jobless runs to inactive archival jobs; reject instruction mismatches."

    def add_arguments(self, parser):
        parser.add_argument("--purpose", choices=["metric", "catalog", "content"])

    def handle(self, *args, **options):
        executor = MigrationExecutor(connection)
        normalized = ("core", "0089_job_owned_run_instructions")
        if normalized in executor.loader.applied_migrations:
            # Do not feed current ORM-free models to the historical archiver.
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT count(*) FROM collection_runs r "
                    "LEFT JOIN collection_jobs j ON j.id = r.job_id "
                    "WHERE r.job_id IS NULL OR j.id IS NULL"
                )
                if cursor.fetchone()[0]:
                    raise ValueError("collection runs have missing or orphaned jobs")
        else:
            historical = executor.loader.project_state(
                [("core", "0088_archive_run_instructions")]
            ).apps
            migration = import_module("core.migrations.0088_archive_run_instructions")
            with connection.schema_editor(atomic=False) as editor:
                migration.archive_run_instructions(
                    historical,
                    editor,
                    purposes=[options["purpose"]] if options["purpose"] else None,
                )
        self.stdout.write(
            "Collection run instructions checked and jobless runs archived."
        )
