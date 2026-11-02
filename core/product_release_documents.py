"""Import retained public documents; no network, model calls or ownership guesses.

Capture bytes belong to the existing archive. URL and capture time belong to
the collection run/observation. Importing a capture is not an HTTP request.
"""

import hashlib
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit

from django.db import transaction
from django.utils import timezone

from core import models
from core.collection_capture import archive_document, checked_endpoint
from core.collection_jobs import register_job
from core.measurement_taxonomy import digest, require

PROJECTION = "release-document-v1"
MAX_BYTES = 2_000_000
MEDIA_TYPES = {"text/html", "text/plain", "text/markdown"}


class _VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = []
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "template", "noscript"}:
            self.hidden.append(tag)

    def handle_endtag(self, tag):
        if self.hidden and tag == self.hidden[-1]:
            self.hidden.pop()

    def handle_data(self, text):
        if not self.hidden:
            self.parts.append(text)


def document_text(body, media_type):
    require(
        isinstance(body, bytes) and 0 < len(body) <= MAX_BYTES,
        "bounded document bytes required",
    )
    require(media_type in MEDIA_TYPES, "unsupported document media type")
    text = body.decode("utf-8-sig")
    if media_type == "text/html":
        parser = _VisibleText()
        parser.feed(text)
        text = " ".join(parser.parts)
    text = " ".join(text.split())
    require(text, "document has no usable text")
    return text


def validate_capture(
    *,
    body,
    url,
    observed_at,
    sha256,
    media_type,
    source_id,
    subject_kind,
    native_identifier=None,
    publisher_account_id=None,
):
    checked_endpoint(url)
    require(not urlsplit(url).fragment, "capture URL must not contain a fragment")
    require(
        isinstance(observed_at, datetime)
        and observed_at.tzinfo is not None
        and observed_at <= timezone.now(),
        "capture time must be aware and not future",
    )
    document_text(body, media_type)
    require(hashlib.sha256(body).hexdigest() == sha256, "document checksum mismatch")
    require(
        source_id in {"publisher_web", "hf", "github"}, "unsupported document source"
    )
    require(
        subject_kind in {"model", "repository"},
        "document must describe a model or repository",
    )
    native_identifier = native_identifier or url
    require(
        isinstance(native_identifier, str)
        and 0 < len(native_identifier) <= 256
        and native_identifier.strip() == native_identifier,
        "bounded native identity required",
    )
    if source_id == "publisher_web":
        require(
            publisher_account_id is None,
            "website ownership is reviewed separately; do not invent an account",
        )
    else:
        host = "huggingface.co" if source_id == "hf" else "github.com"
        require(urlsplit(url).hostname == host, "document host/source mismatch")
        require(
            "/".join(urlsplit(url).path.strip("/").split("/")[:2]).casefold()
            == native_identifier.casefold(),
            "repository identity absent from document URL",
        )
        if publisher_account_id:
            account = models.Account.objects.get(pk=publisher_account_id)
            require(account.data_source_id == source_id, "publisher source mismatch")
            owner = native_identifier.split("/", 1)[0]
            expected = (
                account.normalized_identifier if source_id == "hf" else account.handle
            )
            require(
                expected and owner.casefold() == expected.casefold(),
                "publisher namespace mismatch",
            )
    return native_identifier


@transaction.atomic
def import_document(**capture):
    native = validate_capture(**capture)
    body = capture["body"]
    identity = {
        name: capture[name]
        for name in ("url", "sha256", "media_type", "source_id", "subject_kind")
    }
    identity.update(
        observed_at=capture["observed_at"].isoformat(),
        native_identifier=native,
        publisher_account_id=str(capture["publisher_account_id"])
        if capture.get("publisher_account_id")
        else None,
    )
    key = digest([PROJECTION, identity])
    if capture["source_id"] == "publisher_web":
        source, _ = models.DataSource.objects.get_or_create(
            pk="publisher_web",
            defaults={
                "name": "Publisher release documents",
                "source_type": "model_adoption",
                "enabled": False,
            },
        )
    else:
        source = models.DataSource.objects.get(pk=capture["source_id"])
    job = register_job(
        job_key="release-document:" + key,
        source=source,
        purpose="content",
        operation="release_document_import",
        mode="manual",
        definition={"version": 2, "options": {}},
        settings={
            "owner_kind": "source",
            "schedule_kind": "manual",
            "schedule_driver": "manual",
            "max_requests": 1,
            "max_bytes": MAX_BYTES,
            "max_seconds": 60,
            "max_items": 1,
        },
        targets=[
            {
                "target_key": key,
                "native_identifier": native,
                "target_kind": capture["subject_kind"],
                "target_role": "document",
                "resolution_state": "unresolved",
                "gap_reason": "source_identity_only",
            }
        ],
    )
    archive = archive_document(
        body,
        encoding="decoded-body-v1",
        media_type=capture["media_type"],
        capture_kind="release_document",
    )
    require(
        archive.media_type == capture["media_type"],
        "captured format conflicts with existing archive",
    )
    now = timezone.now()
    run, _ = models.CollectionRun.objects.get_or_create(
        ingestion_key=key,
        defaults={
            "job": job,
            "status": "success",
            "execution_state": "completed",
            "coverage_state": "complete",
            "started_at": now,
            "completed_at": now,
            "observed_at": capture["observed_at"],
            "direct_ingestion": True,
            "source_url": capture["url"],
            "request_count": 0,
            "physical_bytes_received": 0,
            "selected_count": 1,
            "success_count": 1,
            "payload_sha256": archive.content_sha256,
            "payload_archive": archive,
        },
    )
    require(
        run.job_id == job.pk
        and run.payload_archive_id == archive.pk
        and run.source_url == capture["url"],
        "document import identity conflict",
    )
    observation, _ = models.CollectionObservation.objects.get_or_create(
        run=run,
        observation_key=key,
        defaults={
            "source_identifier": native,
            "source_subject_kind": capture["subject_kind"],
            "observation_kind": "release_document",
            "projection_kind": PROJECTION,
            "observed_at": capture["observed_at"],
            "original_retrieved_at": capture["observed_at"],
            "payload_sha256": archive.content_sha256,
        },
    )
    models.CollectionResourceSnapshot.objects.get_or_create(
        observation=observation,
        defaults={
            "resource_kind": "release_document",
            "native_identifier": native,
            "content_hash": archive.content_sha256,
            "hash_algorithm": "sha256",
            "publisher_account_id": capture.get("publisher_account_id"),
        },
    )
    observation_documents(observation)
    return observation


def observation_documents(observation):
    run = observation.run
    archive = run.payload_archive
    require(
        observation.projection_kind == PROJECTION
        and run.job.operation == "release_document_import"
        and observation.status == "ok"
        and run.status == "success"
        and archive is not None,
        "document observation is unavailable",
    )
    body = bytes(archive.body)
    require(
        hashlib.sha256(body).hexdigest()
        == archive.content_sha256
        == observation.payload_sha256
        == run.payload_sha256
        == observation.resource_snapshot.content_hash,
        "document evidence checksum mismatch",
    )
    require(
        observation.source_identifier
        == observation.resource_snapshot.native_identifier,
        "document evidence identity mismatch",
    )
    return (
        {
            "body": document_text(body, archive.media_type),
            "web_url": checked_endpoint(run.source_url),
        },
        {},
        {},
    )
