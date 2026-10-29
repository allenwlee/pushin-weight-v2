"""Validate/apply a source-checked study; emit persisted results and a report."""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.product_release_report import render_report
from core.product_release_study import apply_study, validate_assessment


class Command(BaseCommand):
    help = "Apply a reviewed release study (validation only unless --persist)"

    def add_arguments(self, parser):
        parser.add_argument("packet")
        parser.add_argument("--persist", action="store_true")
        parser.add_argument("--discussion", action="store_true")
        parser.add_argument("--output")
        parser.add_argument("--report")

    def handle(self, *args, **options):
        try:
            path = Path(options["packet"])
            if path.stat().st_size > 4000000:
                raise ValueError("Study packet exceeds 4 MB")
            packet = validate_assessment(json.loads(path.read_text()))
            if not options["persist"]:
                self.stdout.write(
                    json.dumps(
                        {"validated_cases": len(packet["cases"]), "persisted": False}
                    )
                )
                return
            result = apply_study(packet, discussion=options["discussion"])
            if options["output"]:
                Path(options["output"]).write_text(
                    json.dumps(result, default=str, indent=2)
                )
            if options["report"]:
                Path(options["report"]).write_text(
                    render_report(
                        result["releases"],
                        notes="Source-checked study. Current stored classifications; coverage is incomplete. Two-hour curves and 15-minute windows near the anchor are reusable. Date-only anchors use an explicit UTC-midnight study convention.",
                    )
                )
            self.stdout.write(
                json.dumps(
                    {
                        "persisted": True,
                        "cases": len(result["cases"]),
                        "input_hash": result["input_hash"],
                    }
                )
            )
        except (ValueError, OSError, KeyError, TypeError) as exc:
            raise CommandError(str(exc)) from exc
