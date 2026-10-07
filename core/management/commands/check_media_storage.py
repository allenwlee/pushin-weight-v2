"""Write/read a small proof object from independently deployed services."""

import hashlib
import json
import os
import re
from uuid import UUID, uuid4

from botocore.exceptions import BotoCoreError, ClientError
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = "Write or verify a small media probe; print no credentials or download URLs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--storage", choices=["staff_media", "editorial_media"], required=True
        )
        parser.add_argument("--write", action="store_true")
        parser.add_argument("--probe-id")
        parser.add_argument("--expected-sha256")

    def handle(self, *args, **options):
        try:
            probe_id = (
                str(UUID(options["probe_id"])) if options["probe_id"] else str(uuid4())
            )
        except ValueError as exc:
            raise CommandError("probe-id must be a UUID") from exc
        expected = options["expected_sha256"]
        if not options["write"] and (
            not options["probe_id"]
            or not expected
            or not re.fullmatch(r"[a-f0-9]{64}", expected)
        ):
            raise CommandError(
                "Read verification requires probe-id and expected-sha256"
            )
        storage = storages[options["storage"]]
        key = f"_storage-probes/{probe_id}.json"
        try:
            if options["write"]:
                if storage.exists(key):
                    raise CommandError("Probe already exists; use a fresh probe-id")
                payload = {
                    "schema": "media-storage-probe/v1",
                    "probe_id": probe_id,
                    "writer_service": os.environ.get("RENDER_SERVICE_ID", "local"),
                    "writer_commit": os.environ.get("RENDER_GIT_COMMIT", ""),
                    "created_at": timezone.now().isoformat(),
                }
                data = json.dumps(payload, sort_keys=True).encode()
                expected = hashlib.sha256(data).hexdigest()
                if storage.save(key, ContentFile(data)) != key:
                    raise CommandError("Storage renamed the probe")
            with storage.open(key, "rb") as stream:
                data = stream.read(65537)
            if len(data) > 65536 or hashlib.sha256(data).hexdigest() != expected:
                raise CommandError("Probe verification failed")
            payload = json.loads(data)
            if (
                payload.get("schema") != "media-storage-probe/v1"
                or payload.get("probe_id") != probe_id
            ):
                raise CommandError("Probe identity does not match")
        except (OSError, ValueError, BotoCoreError, ClientError) as exc:
            raise CommandError(f"Media probe failed: {type(exc).__name__}") from exc
        self.stdout.write(
            json.dumps(
                {
                    "schema": "media-storage-probe-receipt/v1",
                    "storage": options["storage"],
                    "backend": f"{type(storage).__module__}.{type(storage).__name__}",
                    "probe_id": probe_id,
                    "key": key,
                    "sha256": expected,
                    "bytes": len(data),
                    "writer_service": payload["writer_service"],
                    "writer_commit": payload["writer_commit"],
                    "reader_service": os.environ.get("RENDER_SERVICE_ID", "local"),
                    "reader_commit": os.environ.get("RENDER_GIT_COMMIT", ""),
                    "verified": True,
                },
                sort_keys=True,
            )
        )
