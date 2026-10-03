import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import (
    PersonMedia,
    PersonName,
    StaffCollectionWork,
    StaffProviderRequest,
)
from core.person_names import digest, review_name, select_names
from core.staff_assets.media import review_media


class Command(BaseCommand):
    help = "Record a sourced name/media review or deliberately requeue held work."

    def add_arguments(self, parser):
        parser.add_argument("kind", choices=["name", "media", "work", "request-retry"])
        parser.add_argument("id", type=int)
        parser.add_argument("--reviewer", required=True)
        parser.add_argument("--reason", required=True)
        parser.add_argument(
            "--status", choices=["pending", "confirmed", "rejected"], default="pending"
        )
        parser.add_argument("--select", choices=["primary", "english"])
        parser.add_argument("--source-verified", action="store_true")
        parser.add_argument("--individual-portrait", action="store_true")
        parser.add_argument(
            "--suitability",
            choices=["pending", "approved", "rejected"],
            default="pending",
        )
        parser.add_argument(
            "--reuse", choices=["unknown", "permitted", "restricted"], default="unknown"
        )
        parser.add_argument("--apply", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        if not options["reviewer"].strip() or not options["reason"].strip():
            raise CommandError("A reviewer and evidence-based reason are required")
        if not options["apply"]:
            self.stdout.write(
                json.dumps(
                    {
                        "apply": False,
                        "kind": options["kind"],
                        "id": options["id"],
                        "reason": options["reason"],
                    }
                )
            )
            return
        kind, pk = options["kind"], options["id"]
        if kind == "name":
            row = PersonName.objects.get(pk=pk)
            review_name(row, options["status"], options["reviewer"], options["reason"])
            if options["select"]:
                person = row.person
                selections = {
                    "primary": person.primary_name,
                    "english": person.english_name,
                }
                selections[options["select"]] = row
                select_names(person, **selections)
        elif kind == "media":
            review_media(
                PersonMedia.objects.get(pk=pk),
                reviewer=options["reviewer"],
                reason=options["reason"],
                source_verified=options["source_verified"],
                individual_portrait=options["individual_portrait"],
                suitability=options["suitability"],
                reuse_status=options["reuse"],
            )
        else:
            review = {
                "reviewer": options["reviewer"],
                "reason": options["reason"],
                "at": timezone.now().isoformat(),
            }
            if kind == "request-retry":
                request = StaffProviderRequest.objects.select_for_update().get(pk=pk)
                if (
                    request.state == "complete"
                    or "retry_authorization" in request.response
                ):
                    raise CommandError(
                        "A completed or previously retired request cannot be retried here"
                    )
                # Retain the original reservation and its cost, but release the query
                # identity only after an explicit operator decision permitting a charge.
                request.response = {
                    **request.response,
                    "retry_authorization": review,
                    "original_fingerprint": request.fingerprint,
                }
                request.fingerprint = digest(
                    [request.fingerprint, request.pk, "operator-retired"]
                )
                request.state = "needs_review"
                request.save()
                if request.work_id is None:
                    raise CommandError("The original work no longer exists")
                pk = request.work_id
            work = StaffCollectionWork.objects.select_for_update().get(pk=pk)
            if work.state == "running":
                raise CommandError("Cannot requeue work with an active lease")
            work.result = {
                **work.result,
                "requeue_reviews": [*work.result.get("requeue_reviews", []), review],
            }
            work.state, work.error_category = "queued", ""
            work.next_attempt_at = timezone.now()
            work.save()
            PersonMedia.objects.filter(
                person_id=work.person_id,
                availability="unavailable",
                media__isnull=True,
            ).update(availability="unfetched")
        self.stdout.write(
            json.dumps({"applied": True, "kind": kind, "id": options["id"]})
        )
