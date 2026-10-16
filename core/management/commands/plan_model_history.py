"""Inspect observed inventory; freeze only on explicit --freeze."""

import json

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.model_history_cohort import build_cohort, cohort_report, freeze_model_history


class Command(BaseCommand):
    help = (
        "Inspect a 21-brand newest-model cohort; --freeze persists paused source jobs."
    )

    def add_arguments(self, parser):
        parser.add_argument("--brands", required=True)
        parser.add_argument("--cutoff")
        parser.add_argument("--freeze", action="store_true")
        parser.add_argument(
            "--qualification-policy", choices=["hf-public-model-registry-v1"]
        )
        parser.add_argument("--job-key-prefix", default="model-history")
        parser.add_argument("--requests", type=int, default=40)
        parser.add_argument("--seconds", type=int, default=180)
        parser.add_argument("--bytes", type=int, default=4 * 1024 * 1024)
        parser.add_argument("--items", type=int, default=10000)

    def handle(self, *args, **options):
        try:
            arguments = {
                "brand_ids": options["brands"].split(","),
                "cutoff": options["cutoff"] or timezone.now(),
                "qualification_policy": options["qualification_policy"],
            }
            if options["freeze"]:
                jobs = freeze_model_history(
                    **arguments,
                    job_key_prefix=options["job_key_prefix"],
                    budgets={
                        k: options[k] for k in ("requests", "seconds", "bytes", "items")
                    },
                )
                report = cohort_report(jobs)
            else:
                report = {**build_cohort(**arguments), "writes": 0}
            self.stdout.write(json.dumps(report, ensure_ascii=False))
        except (ValueError, TypeError) as exc:
            raise CommandError(
                "invalid cohort scope, dates, instruction identity or budgets"
            ) from exc
