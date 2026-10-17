"""Preview stored product identities, then explicitly apply reviewed choices."""

import json

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.management.base import BaseCommand, CommandError

from core import collection_matching as matching


class Command(BaseCommand):
    help = "Preview conservative product crosswalks without writes or provider calls."

    def add_arguments(self, parser):
        parser.add_argument("--brand", action="append", default=[])
        parser.add_argument("--source", action="append", choices=matching.SOURCES)
        parser.add_argument(
            "--cutoff", help="UTC evidence cutoff from the reviewed preview"
        )
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--input-sha256")
        parser.add_argument("--review-candidate", action="append", default=[])
        parser.add_argument("--reviewed-by")
        parser.add_argument("--review-basis")
        parser.add_argument("--resume", help="Resume a persisted matching job UUID")
        parser.add_argument("--format", choices=["json", "markdown"], default="json")

    def handle(self, *args, **options):
        try:
            if options["resume"]:
                if (
                    not options["apply"]
                    or options["brand"]
                    or options["input_sha256"]
                    or options["review_candidate"]
                ):
                    raise ValueError(
                        "resume requires --apply and uses database instructions only"
                    )
                result = matching.apply_matches(resume_job_id=options["resume"])
            else:
                if options["apply"] and not all(
                    options[k]
                    for k in ("cutoff", "input_sha256", "reviewed_by", "review_basis")
                ):
                    raise ValueError(
                        "apply requires cutoff, preview fingerprint, reviewer and review basis"
                    )
                result = matching.preview_matches(
                    brand_ids=options["brand"],
                    sources=options["source"] or matching.SOURCES,
                    cutoff=options["cutoff"],
                )
                if options["apply"]:
                    result = matching.apply_matches(
                        preview=result,
                        input_sha256=options["input_sha256"],
                        reviewed_by=options["reviewed_by"],
                        review_basis=options["review_basis"],
                        reviewed_candidate_ids=options["review_candidate"],
                    )
            self.stdout.write(
                json.dumps(result, indent=2)
                if options["format"] == "json"
                else matching.markdown_report(result)
            )
        except (ValueError, KeyError) as exc:
            raise CommandError(str(exc)) from exc
        except (ObjectDoesNotExist, ValidationError) as exc:
            raise CommandError(
                "invalid saved matching identity or unavailable evidence"
            ) from exc
