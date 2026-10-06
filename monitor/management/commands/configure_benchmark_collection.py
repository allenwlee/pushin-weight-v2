"""Explicit registry, HF account and immutable measurement-contract setup."""

import json
from pathlib import Path

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError

from core.benchmark_metric_identity import (
    configure_collection,
    configure_hf_account,
    prepare_collection,
    register_definitions,
)
from core.measurement_taxonomy import digest


class Command(BaseCommand):
    help = "Validate a reviewed metric contract; --apply writes it, without enabling collection."

    def add_arguments(self, parser):
        parser.add_argument("manifest", nargs="?")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--register-definitions", action="store_true")
        parser.add_argument("--hf-account")
        parser.add_argument("--reviewed-by")
        parser.add_argument("--evidence-url")

    def handle(self, *args, **options):
        try:
            if options["register_definitions"]:
                if not options["apply"]:
                    raise ValueError("registry setup requires --apply")
                result = {
                    "registered_definitions": register_definitions(),
                    "polling_enabled": False,
                }
            elif options["hf_account"]:
                if not options["apply"]:
                    raise ValueError("account setup requires --apply")
                if not options["reviewed_by"] or not options["evidence_url"]:
                    raise ValueError("reviewer and evidence required")
                account = configure_hf_account(
                    options["hf_account"],
                    reviewed_by=options["reviewed_by"],
                    evidence_url=options["evidence_url"],
                )
                result = {"account_key": str(account.pk)}
            else:
                if not options["manifest"]:
                    raise ValueError("manifest required")
                path = Path(options["manifest"])
                if path.stat().st_size > 4 * 1024 * 1024:
                    raise ValueError("manifest too large")
                spec = json.loads(path.read_text())
                _, mappings, frozen = prepare_collection(spec)
                result = {
                    "contract_hash": digest(frozen),
                    "mappings": len(mappings),
                    "applied": False,
                }
                if options["apply"]:
                    result.update(id=str(configure_collection(spec).pk), applied=True)
            self.stdout.write(json.dumps(result))
        except (ValueError, KeyError, OSError, ObjectDoesNotExist) as exc:
            raise CommandError(str(exc)) from exc
