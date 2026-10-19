"""Correct reported timing from retained evidence; dry-run unless --apply."""

import json
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.models import Max

from core.benchmark_metric_timing_repair import repair_batch, repair_lock
from core.models import MetricValue


class Command(BaseCommand):
    help = "Bounded timing correction from retained evidence, with before-images."

    def add_arguments(self, parser):
        parser.add_argument("--database-name", required=True)
        parser.add_argument("--cutoff-value-id", type=int)
        parser.add_argument("--after-value-id", type=int, default=0)
        parser.add_argument("--batch-size", type=int, default=250)
        parser.add_argument("--max-batches", type=int, default=1)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--rollback", action="store_true")
        parser.add_argument("--backup-id")

    def handle(self, **options):
        if not (
            1 <= options["batch_size"] <= 1000
            and 1 <= options["max_batches"] <= 10000
            and options["after_value_id"] >= 0
        ):
            raise CommandError("invalid correction bounds")
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            database = cursor.fetchone()[0]
        if database != options["database_name"]:
            raise CommandError("database identity mismatch")
        if options["apply"] and not options["backup_id"]:
            raise CommandError("--apply requires the verified --backup-id")
        cutoff = options["cutoff_value_id"]
        if cutoff is None:
            cutoff = MetricValue.objects.aggregate(last=Max("id"))["last"] or 0
        if cutoff < options["after_value_id"]:
            raise CommandError("cutoff precedes cursor")
        result = {
            "database": database,
            "cutoff_value_id": cutoff,
            "after_value_id": options["after_value_id"],
            "apply": options["apply"],
            "rollback": options["rollback"],
            "backup_id": options["backup_id"],
            "scanned_values": 0,
            "changed_values": 0,
            "metadata_updates": 0,
            "conflicts": 0,
            "deferred_values": 0,
            "batches": 0,
            "exhausted": False,
        }
        reasons = Counter()
        with repair_lock():
            for _ in range(options["max_batches"]):
                batch = repair_batch(
                    cutoff=cutoff,
                    after=result["after_value_id"],
                    batch_size=options["batch_size"],
                    apply=options["apply"],
                    rollback=options["rollback"],
                )
                result["after_value_id"] = batch["after_value_id"]
                for key in (
                    "scanned_values",
                    "changed_values",
                    "metadata_updates",
                    "conflicts",
                    "deferred_values",
                ):
                    result[key] += batch[key]
                reasons.update(batch["reasons"])
                result["batches"] += 1
                self.stdout.write(
                    "G3_TIMING_BATCH " + json.dumps(batch, sort_keys=True)
                )
                if batch["scanned_values"] < options["batch_size"]:
                    result["exhausted"] = True
                    break
        result["reasons"] = dict(reasons)
        self.stdout.write("G3_TIMING_COMPLETE " + json.dumps(result, sort_keys=True))
