"""Preview or run one bounded, resumable known-org HF model catalog import."""

from __future__ import annotations

import json

import httpx
from django.core.management.base import BaseCommand, CommandError

from core.models import Brand, BrandCompany, HFOrg
from core.product_verification import import_known_org_catalog


class Command(BaseCommand):
    help = "Import one confirmed Hugging Face organization's model catalog"

    def add_arguments(self, parser):
        parser.add_argument("--brand", required=True)
        parser.add_argument("--confirmed-namespace", required=True)
        parser.add_argument("--max-requests", required=True, type=int)
        parser.add_argument("--max-models", required=True, type=int)
        parser.add_argument("--cursor", default="")
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Permit bounded public metadata requests and database writes",
        )

    def handle(self, *args, **options):
        max_requests = options["max_requests"]
        max_models = options["max_models"]
        if not 1 <= max_requests <= 100:
            raise CommandError("--max-requests must be between 1 and 100")
        if not 1 <= max_models <= 10_000:
            raise CommandError("--max-models must be between 1 and 10000")
        try:
            brand = Brand.objects.get(
                pk=options["brand"],
                is_sentinel=False,
            )
        except Brand.DoesNotExist as exc:
            raise CommandError("unknown Brand") from exc
        try:
            hf_org = HFOrg.objects.get(
                namespace=options["confirmed_namespace"],
                confirmed=True,
            )
        except HFOrg.DoesNotExist as exc:
            raise CommandError("unknown or unconfirmed HF namespace") from exc
        if not BrandCompany.objects.filter(
            brand=brand,
            company_id=hf_org.company_id,
        ).exists():
            raise CommandError(
                "Brand does not own the confirmed HF namespace; no request was sent"
            )

        preview = {
            "mode": "commit" if options["commit"] else "preview",
            "brand": brand.pk,
            "confirmed_namespace": hf_org.pk,
            "max_requests": max_requests,
            "max_models": max_models,
            "cursor": options["cursor"] or None,
        }
        if not options["commit"]:
            self.stdout.write(json.dumps(preview, sort_keys=True))
            return

        with httpx.Client(timeout=2.0, follow_redirects=False) as client:
            result = import_known_org_catalog(
                brand=brand,
                hf_org=hf_org,
                client=client,
                max_requests=max_requests,
                max_models=max_models,
                cursor=options["cursor"] or None,
            )
        self.stdout.write(
            json.dumps(
                {
                    **preview,
                    "imported": result.imported,
                    "updated": result.updated,
                    "requests": result.requests,
                    "complete": result.complete,
                    "stop_reason": result.stop_reason,
                    "next_cursor": result.next_cursor,
                },
                sort_keys=True,
            )
        )
