"""Project saved completed X backfill results before retiring run.report."""

from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from core.models import CollectionRun
from monitor.backfill_collection import adopt_completed_backfill_result


class Command(BaseCommand):
    help = "Project or verify exact completed X backfill result evidence"

    def add_arguments(self, parser):
        parser.add_argument("--after-id", default=None)
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--verify-only", action="store_true")

    def handle(self, *args, **options):
        if not 1 <= options["limit"] <= 1000:
            raise CommandError("limit must be between 1 and 1000")
        retained = {field.name for field in CollectionRun._meta.fields}
        if "report" not in retained:
            raise CommandError("historical result projection must run before report deletion")
        query = CollectionRun.objects.filter(
            job__source_id="x", job__purpose="content",
            job__operation="x_backfill", status="success",
        ).order_by("pk")
        if options["after_id"]:
            try:
                after_id = UUID(options["after_id"])
            except ValueError as exc:
                raise CommandError("after-id must be a UUID") from exc
            query = query.filter(pk__gt=after_id)
        run_ids = list(query.values_list("pk", flat=True)[: options["limit"]])
        copied = verified = 0
        unresolved = []
        for run_id in run_ids:
            try:
                result = adopt_completed_backfill_result(
                    run_id, verify_only=options["verify_only"],
                )
            except ValueError as exc:
                unresolved.append((str(run_id), str(exc)))
                continue
            copied += int(result["copied"])
            verified += int(not result["copied"])
        for run_id, reason in unresolved:
            self.stdout.write(f"unresolved_run={run_id} reason={reason}")
        self.stdout.write(
            f"scanned={len(run_ids)} copied={copied} verified={verified} "
            f"unresolved={len(unresolved)} "
            f"next_after_id={run_ids[-1] if run_ids else options['after_id'] or ''} "
            f"exhausted={str(len(run_ids) < options['limit']).lower()}"
        )
