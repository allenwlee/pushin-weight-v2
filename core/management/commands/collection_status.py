import json

from django.core.management.base import BaseCommand, CommandError

from core.collection_reports import campaign_status, job_status
from core.models import CollectionJob


class Command(BaseCommand):
    help = (
        "Read collection status, provenance and coverage; makes no provider requests."
    )

    def add_arguments(self, parser):
        selection = parser.add_mutually_exclusive_group(required=True)
        selection.add_argument("--job")
        selection.add_argument("--cohort")

    def handle(self, *args, **options):
        try:
            report = (
                job_status(options["job"])
                if options["job"]
                else campaign_status(options["cohort"])
            )
            self.stdout.write(json.dumps(report))
        except (ValueError, CollectionJob.DoesNotExist) as exc:
            raise CommandError("unknown collection report identity") from exc
