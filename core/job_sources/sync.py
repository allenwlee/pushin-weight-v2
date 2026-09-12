from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.db import transaction
from django.utils import timezone

from core.models import Brand, JobListing, JobListingEvidence, JobSourceSyncRun

from .registry import get_source
from .types import SourceJob, SourceSnapshot


@dataclass(frozen=True, slots=True)
class SyncResult:
    run_id: int
    created_count: int = 0
    updated_count: int = 0
    unchanged_count: int = 0
    reopened_count: int = 0
    closed_count: int = 0


def _digest(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _listing_identity(source_key: str, source_listing_id: str) -> str:
    return _digest(["direct_job", source_key, source_listing_id])


def _content_hash(job: SourceJob, *, allowed_hosts: frozenset[str]) -> str:
    payload = asdict(job) | {"raw_payload": None}
    payload["canonical_url"] = _official_url(
        job.canonical_url, allowed_hosts=allowed_hosts
    )
    payload["application_url"] = _official_url(
        job.application_url or job.canonical_url, allowed_hosts=allowed_hosts
    )
    return _digest(payload)


def _official_url(value: str | None, *, allowed_hosts: frozenset[str]) -> str | None:
    if not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
        raise ValueError("job destination is not an approved official host")
    query = urlencode(
        [
            (key, item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith("utm_")
            and key.lower() not in {"spm", "track", "tracking", "share_id", "shareid"}
        ]
    )
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, query, parsed.fragment)
    )


def _source_owned_fields(job: SourceJob, *, source, brand, observed_at):
    canonical_url = _official_url(job.canonical_url, allowed_hosts=source.allowed_hosts)
    application_url = _official_url(
        job.application_url or job.canonical_url,
        allowed_hosts=source.allowed_hosts,
    )
    return {
        "brand": brand,
        "brand_discovery_candidate": None,
        "hiring_organization": source.display_name,
        "source_key": source.key,
        "source_name": source.display_name,
        "source_listing_id": job.source_listing_id,
        "canonical_url": canonical_url,
        "application_url": application_url,
        "application_route_kind": "direct_url",
        "application_resolution_status": "official_source",
        "title": job.title,
        "description_html": job.description_html,
        "description_text": job.description_text,
        "department": job.department,
        "team": job.team,
        "job_function": job.job_function,
        "seniority": job.seniority,
        "employment_type": job.employment_type,
        "workplace_type": job.workplace_type,
        "locations_raw": " · ".join(job.locations) or None,
        "locations": list(job.locations),
        "posted_at": job.posted_at,
        "updated_source_at": job.updated_at,
        "last_seen_at": observed_at,
        "closed_at": None,
        "status": "open",
        "consecutive_missing_snapshots": 0,
        "last_complete_source_sync_at": observed_at,
        "content_hash": _content_hash(job, allowed_hosts=source.allowed_hosts),
        "extraction_version": "official-site-v1",
        "extraction_confidence": 1.0,
        "raw_payload": job.raw_payload,
        "source_language": "zh-CN",
    }


def validate_snapshot(snapshot: SourceSnapshot) -> None:
    source = get_source(snapshot.source_key)
    if (
        snapshot.complete
        and snapshot.declared_total is not None
        and snapshot.declared_total != len(snapshot.jobs)
    ):
        raise ValueError(
            f"{source.key} declared {snapshot.declared_total} jobs but returned "
            f"{len(snapshot.jobs)}"
        )
    ids = [job.source_listing_id for job in snapshot.jobs]
    if any(not value for value in ids) or len(ids) != len(set(ids)):
        raise ValueError(
            f"{source.key} snapshot contains missing or duplicate listing IDs"
        )
    for job in snapshot.jobs:
        _content_hash(job, allowed_hosts=source.allowed_hosts)


@transaction.atomic
def _persist_snapshot(
    snapshot: SourceSnapshot,
    *,
    run: JobSourceSyncRun,
    no_close: bool,
) -> SyncResult:
    source = get_source(snapshot.source_key)
    validate_snapshot(snapshot)
    brand = Brand.objects.get(nickname=source.brand_nickname)
    counts = {
        "created_count": 0,
        "updated_count": 0,
        "unchanged_count": 0,
        "reopened_count": 0,
        "closed_count": 0,
    }
    seen_identities: list[str] = []

    # Partial snapshots are diagnostic evidence only. They cannot author or
    # reconcile listing state because absence is unknowable.
    if not snapshot.complete:
        run.status = "partial"
        run.finished_at = timezone.now()
        run.snapshot_complete = False
        run.declared_total = snapshot.declared_total
        run.observed_total = len(snapshot.jobs)
        run.metadata = snapshot.metadata
        run.save()
        return SyncResult(run_id=run.pk)

    for job in snapshot.jobs:
        identity = _listing_identity(source.key, job.source_listing_id)
        seen_identities.append(identity)
        fields = _source_owned_fields(
            job, source=source, brand=brand, observed_at=snapshot.observed_at
        )
        listing = JobListing.objects.filter(listing_identity=identity).first()
        if listing is None:
            listing = JobListing.objects.create(
                listing_identity=identity,
                first_seen_at=snapshot.observed_at,
                **fields,
            )
            counts["created_count"] += 1
        else:
            was_closed = listing.status == "closed"
            changed = listing.content_hash != fields["content_hash"]
            for name, value in fields.items():
                setattr(listing, name, value)
            listing.save()
            if was_closed:
                counts["reopened_count"] += 1
            elif changed:
                counts["updated_count"] += 1
            else:
                counts["unchanged_count"] += 1
        evidence_hash = _digest(["official-site", source.key, job.source_listing_id])
        evidence, created = JobListingEvidence.objects.get_or_create(
            listing=listing,
            evidence_hash=evidence_hash,
            defaults={
                "source_url": listing.canonical_url,
                "source_relationship": "official",
                "evidence_text": job.description_text or job.title,
                "linked_urls": [
                    value
                    for value in [listing.canonical_url, listing.application_url]
                    if value
                ],
                "observed_at": snapshot.observed_at,
                "extraction_method": "structured_text",
                "extraction_identity": "official-site-v1",
                "confidence": 1.0,
                "raw_evidence": job.raw_payload,
            },
        )
        if not created:
            evidence.source_url = listing.canonical_url
            evidence.evidence_text = job.description_text or job.title
            evidence.linked_urls = [
                value
                for value in [listing.canonical_url, listing.application_url]
                if value
            ]
            evidence.observed_at = snapshot.observed_at
            evidence.raw_evidence = job.raw_payload
            evidence.save(
                update_fields=[
                    "source_url",
                    "evidence_text",
                    "linked_urls",
                    "observed_at",
                    "raw_evidence",
                ]
            )

    if not no_close:
        missing = JobListing.objects.filter(source_key=source.key).exclude(
            listing_identity__in=seen_identities
        )
        for listing in missing.select_for_update():
            listing.consecutive_missing_snapshots = min(
                listing.consecutive_missing_snapshots + 1, 2
            )
            listing.last_complete_source_sync_at = snapshot.observed_at
            update_fields = [
                "consecutive_missing_snapshots",
                "last_complete_source_sync_at",
                "updated_at",
            ]
            if listing.status == "open" and listing.consecutive_missing_snapshots >= 2:
                listing.status = "closed"
                listing.closed_at = snapshot.observed_at
                update_fields.extend(["status", "closed_at"])
                counts["closed_count"] += 1
            listing.save(update_fields=update_fields)

    run.status = "succeeded"
    run.finished_at = timezone.now()
    run.snapshot_complete = True
    run.declared_total = snapshot.declared_total
    run.observed_total = len(snapshot.jobs)
    run.metadata = snapshot.metadata
    for name, value in counts.items():
        setattr(run, name, value)
    run.save()
    return SyncResult(run_id=run.pk, **counts)


def sync_snapshot(
    snapshot: SourceSnapshot,
    *,
    no_close: bool = False,
    run: JobSourceSyncRun | None = None,
) -> SyncResult:
    run = run or JobSourceSyncRun.objects.create(source_key=snapshot.source_key)
    try:
        return _persist_snapshot(snapshot, run=run, no_close=no_close)
    except Exception as exc:
        run.status = "failed"
        run.finished_at = timezone.now()
        run.error_summary = str(exc)[:4000]
        run.save(update_fields=["status", "finished_at", "error_summary"])
        raise
