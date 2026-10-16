import json

from django.core.management.base import BaseCommand, CommandError

from core.collection_reports import campaign_status, job_status, resource_statistics
from core.models import CollectionJob, MetricCollectionContract


class Command(BaseCommand):
    help = (
        "Read collection status, provenance and coverage; makes no provider requests."
    )

    def add_arguments(self, parser):
        selection = parser.add_mutually_exclusive_group(required=True)
        selection.add_argument("--job")
        selection.add_argument("--cohort")
        selection.add_argument("--contract")
        parser.add_argument("--source")
        parser.add_argument("--identifier")
        parser.add_argument("--limit", type=int, default=1000)

    def handle(self, *args, **options):
        try:
            if options["contract"]:
                if not options["source"] or not options["identifier"]:
                    raise ValueError("source and native identifier required")
                report = resource_statistics(
                    contract_id=options["contract"],
                    source=options["source"],
                    identifier=options["identifier"],
                    limit=options["limit"],
                )
            else:
                report = (
                    job_status(options["job"])
                    if options["job"]
                    else campaign_status(options["cohort"])
                )
            self.stdout.write(json.dumps(report))
        except (
            ValueError,
            CollectionJob.DoesNotExist,
            MetricCollectionContract.DoesNotExist,
        ) as exc:
            raise CommandError("unknown collection report identity") from exc
