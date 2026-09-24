"""Preview, import, resume, or refresh the public HF model Product catalog."""

from __future__ import annotations

import json
import math
import uuid

import httpx
from django.core.management.base import BaseCommand, CommandError

from core.hf_catalog import check_scope, execute_catalog, resolve_scope
from core.hf_metadata_client import HFMetadataClient
from core.models import Brand, BrandCompany, HFModelCatalogRun, HFOrg


class Command(BaseCommand):
    help = "Collect public HF models and rich metadata; preview by default"

    def add_arguments(self, parser):
        parser.add_argument("--all-tracked", action="store_true")
        parser.add_argument("--brand")
        parser.add_argument("--confirmed-namespace")
        parser.add_argument("--resume", help="Resume a saved run UUID")
        parser.add_argument(
            "--refresh",
            action="store_true",
            help="Start a fresh observation of the selected scope",
        )
        parser.add_argument("--max-requests", type=int, default=1000)
        parser.add_argument("--max-seconds", type=float, default=900)
        parser.add_argument("--max-response-bytes", type=int, default=16 * 1024 * 1024)
        parser.add_argument("--max-models", type=int)
        parser.add_argument(
            "--cursor", default="", help="Retired: use --resume for durable checkpoints"
        )
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Permit bounded public metadata requests and database writes",
        )

    def handle(self, *args, **options):
        if not math.isfinite(options["max_seconds"]):
            raise CommandError("--max-seconds must be finite")
        if any(
            options[key] <= 0
            for key in ("max_requests", "max_seconds", "max_response_bytes")
        ):
            raise CommandError(
                "request, time, and response-size budgets must be positive"
            )
        if options["max_models"] is not None and options["max_models"] <= 0:
            raise CommandError("--max-models must be positive")
        if options["cursor"]:
            raise CommandError(
                "--cursor cannot prove full coverage; use --resume RUN_ID"
            )
        explicit = bool(options["brand"] or options["confirmed_namespace"])
        if sum((options["all_tracked"], explicit, bool(options["resume"]))) != 1:
            raise CommandError(
                "select --all-tracked, --brand with --confirmed-namespace, or --resume"
            )
        if options["resume"] and options["refresh"]:
            raise CommandError("--resume and --refresh are mutually exclusive")
        run_id = None
        try:
            if options["resume"]:
                run_id = uuid.UUID(options["resume"])
                run = HFModelCatalogRun.objects.get(pk=run_id)
                manifest = run.scope
                check_scope(manifest)
            elif options["all_tracked"]:
                manifest = resolve_scope()
            else:
                if not options["brand"] or not options["confirmed_namespace"]:
                    raise ValueError(
                        "both --brand and --confirmed-namespace are required"
                    )
                brand = Brand.objects.get(pk=options["brand"], is_sentinel=False)
                org = HFOrg.objects.get(
                    pk=options["confirmed_namespace"], confirmed=True
                )
                if not BrandCompany.objects.filter(
                    brand=brand, company_id=org.company_id
                ).exists():
                    raise ValueError(
                        "Brand does not own the confirmed HF namespace; no request was sent"
                    )
                manifest = resolve_scope(
                    brands=[brand.pk], companies=[], namespace=org.pk
                )
        except (
            ValueError,
            Brand.DoesNotExist,
            HFOrg.DoesNotExist,
            HFModelCatalogRun.DoesNotExist,
        ) as exc:
            raise CommandError(str(exc)) from exc
        preview = {
            "mode": "commit" if options["commit"] else "preview",
            "scope": manifest,
            "run_id": str(run_id) if run_id else None,
            "max_requests": options["max_requests"],
            "max_seconds": options["max_seconds"],
            "max_models": options["max_models"],
            "max_response_bytes": options["max_response_bytes"],
        }
        if not options["commit"]:
            self.stdout.write(json.dumps(preview, sort_keys=True))
            return
        try:
            with httpx.Client(
                timeout=30, follow_redirects=False, trust_env=False
            ) as client:
                hf = HFMetadataClient(
                    client,
                    max_requests=options["max_requests"],
                    max_seconds=options["max_seconds"],
                    max_bytes=options["max_response_bytes"],
                )
                result = execute_catalog(
                    hf=hf,
                    scope=None if run_id else manifest,
                    run_id=run_id,
                    max_models=options["max_models"],
                )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps({**preview, **result}, sort_keys=True))
        if not result["complete"]:
            raise CommandError(
                f"HF catalog incomplete; inspect coverage and resume {result['run_id']}",
                returncode=2,
            )
