"""Materialize previously saved title audits without rewriting their intake."""
import json

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import StaffIntake
from core.person_text import record_text
from core.staff_assets.manifest import saved_title_entries


class Command(BaseCommand):
    help = "Preview/apply normalized titles from saved DeepSeek source audits"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    @transaction.atomic
    def handle(self, **options):
        from core.staff_assets.queue import _lock
        _lock()
        results = []
        for intake in StaffIntake.objects.filter(person__isnull=False).select_related("person").order_by("pk"):
            dossier = intake.payload.get("source_dossier", {})
            if not dossier.get("deepseek"):
                continue
            entries = saved_title_entries(dossier.get("presentation", {}).get("fields", {}))
            if not entries:
                continue
            roles = intake.person.brand_affiliations.filter(brand_id="deepseek")
            original_roles = [r for r in intake.payload.get("affiliations", []) if r.get("brand_id") == "deepseek"]
            if len(original_roles) == 1:
                original = original_roles[0]
                roles = roles.filter(title_raw=original.get("title_raw"), status=original.get("status", "unknown"))
            if roles.count() != 1:
                results.append({"intake": intake.pk, "status": "needs_review", "reason": "Ambiguous source affiliation"})
                continue
            role = roles.get()
            results.append({"intake": intake.pk, "affiliation": role.pk, "titles": len(entries)})
            if options["apply"]:
                recorded = {}
                for entry in entries:
                    key = entry.pop("key")
                    parent = entry.pop("derived_from_key", None)
                    recorded[key] = record_text(intake.person, affiliation=role, kind="title",
                        observed_at=intake.observed_at, derived_from=recorded.get(parent), **entry)
        self.stdout.write(json.dumps({"applied": options["apply"], "records": results}))
