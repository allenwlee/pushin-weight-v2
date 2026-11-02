"""Import one retained source capture. No network request is made."""

import json
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.product_release_documents import MAX_BYTES, import_document, validate_capture


class Command(BaseCommand):
    help = "Validate/import one retained release document (no writes unless --persist)"

    def add_arguments(self, parser):
        parser.add_argument("capture")
        for name in (
            "url",
            "observed-at",
            "sha256",
            "media-type",
            "source",
            "subject-kind",
        ):
            parser.add_argument("--" + name, required=True)
        parser.add_argument("--native-identifier")
        parser.add_argument("--publisher-account-id")
        parser.add_argument("--persist", action="store_true")

    def handle(self, *args, **options):
        try:
            path = Path(options["capture"])
            if path.stat().st_size > MAX_BYTES:
                raise ValueError("Document exceeds 2 MB")
            values = {
                name: options[name]
                for name in (
                    "url",
                    "sha256",
                    "media_type",
                    "subject_kind",
                    "native_identifier",
                    "publisher_account_id",
                )
            }
            values.update(
                body=path.read_bytes(),
                source_id=options["source"],
                observed_at=datetime.fromisoformat(options["observed_at"]),
            )
            validate_capture(**values)
            observation = import_document(**values) if options["persist"] else None
            self.stdout.write(
                json.dumps(
                    {
                        "persisted": bool(observation),
                        "observation_id": observation.pk if observation else None,
                    }
                )
            )
        except (ValueError, OSError, TypeError) as exc:
            raise CommandError(str(exc)) from exc
