"""Preview and requeue an exact incident cohort without rewriting its posts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from django.db import connections, transaction
from django.db.models import Q
from django.utils import timezone

from core.models import PostEnrichmentState
from monitor.enrichment_queue import STAGES

VERSION = "enrichment-recovery/v1"
FIELDS = ["post_id", "created_at"] + [
    f"{stage}_{field}"
    for stage in STAGES
    for field in ("status", "attempts", "error_code")
]


def manifest_digest(manifest: dict) -> str:
    payload = {key: value for key, value in manifest.items() if key != "sha256"}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_manifest(
    *, since: datetime, until: datetime, reset_post_ids=(), reset_reason=""
) -> dict:
    if timezone.is_naive(since) or timezone.is_naive(until) or since >= until:
        raise ValueError("recovery_window_invalid")
    reset_ids = set(reset_post_ids)
    if reset_ids and len(reset_reason.strip()) < 12:
        raise ValueError("recovery_reset_requires_reason")
    rows = PostEnrichmentState.objects.filter(
        source_collection_job__isnull=True,
        created_at__gte=since,
        created_at__lt=until,
    ).filter(
        Q(translation_status__in=["pending", "failed"])
        | Q(classification_status__in=["pending", "failed"])
    )
    entries = []
    for row in rows.order_by("created_at", "post_id").values(*FIELDS):
        row["post_id"] = str(row["post_id"])
        row["created_at"] = row["created_at"].isoformat()
        row["reset_reason"] = (
            reset_reason.strip() if row["post_id"] in reset_ids else ""
        )
        entries.append(row)
    if reset_ids - {entry["post_id"] for entry in entries}:
        raise ValueError("recovery_reset_id_outside_cohort")
    manifest = {
        "version": VERSION,
        "database": connections["default"].settings_dict["NAME"],
        "since": since.isoformat(),
        "until": until.isoformat(),
        "entries": entries,
    }
    manifest["sha256"] = manifest_digest(manifest)
    return manifest


def validate_manifest(manifest):
    if (
        not isinstance(manifest, dict)
        or manifest.get("version") != VERSION
        or manifest.get("sha256") != manifest_digest(manifest)
    ):
        raise ValueError("recovery_manifest_digest_invalid")
    if manifest.get("database") != connections["default"].settings_dict["NAME"]:
        raise ValueError("recovery_database_mismatch")
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise TypeError("recovery_entries_invalid")
    ids = [entry.get("post_id") for entry in entries if isinstance(entry, dict)]
    if (
        len(ids) != len(entries)
        or len(ids) != len(set(ids))
        or any(not isinstance(value, str) or not value for value in ids)
    ):
        raise ValueError("recovery_ids_invalid")
    since, until = (
        datetime.fromisoformat(manifest["since"]),
        datetime.fromisoformat(manifest["until"]),
    )
    if timezone.is_naive(since) or timezone.is_naive(until) or since >= until:
        raise ValueError("recovery_window_invalid")
    for entry in entries:
        if set(entry) != {*FIELDS, "reset_reason"} or not isinstance(
            entry["reset_reason"], str
        ):
            raise ValueError("recovery_entry_invalid")
        created = datetime.fromisoformat(entry["created_at"])
        if timezone.is_naive(created) or not since <= created < until:
            raise ValueError("recovery_entry_outside_window")
        for stage in STAGES:
            if (
                entry[f"{stage}_status"] not in {"pending", "succeeded", "failed"}
                or type(entry[f"{stage}_attempts"]) is not int
                or entry[f"{stage}_attempts"] < 0
                or not isinstance(entry[f"{stage}_error_code"], str)
            ):
                raise ValueError("recovery_entry_invalid")
    return entries


def _recovery_decision(state, entry, *, now, max_attempts):
    if state is None:
        return "missing", {}, {}
    if state.source_collection_job_id is not None:
        return "source_owner_changed", {}, {}
    if state.claim_expires_at and state.claim_expires_at > now:
        return "active_lease", {}, {}
    if state.created_at.isoformat() != entry["created_at"]:
        return "queue_identity_changed", {}, {}
    changes, before = {}, {}
    for stage in STAGES:
        status = getattr(state, f"{stage}_status")
        attempts = getattr(state, f"{stage}_attempts")
        error = getattr(state, f"{stage}_error_code")
        if status != "failed":
            continue
        if (status, attempts, error) != tuple(
            entry[f"{stage}_{field}"] for field in ("status", "attempts", "error_code")
        ):
            continue
        if (error != "age_exhausted" or attempts >= max_attempts) and not entry[
            "reset_reason"
        ]:
            continue
        before[stage] = {"attempts": attempts, "error_code": error}
        changes.update(
            {
                f"{stage}_status": "pending",
                f"{stage}_next_attempt_at": now,
                f"{stage}_error_code": "incident_requeued",
            }
        )
        if attempts >= max_attempts:
            changes[f"{stage}_attempts"] = 0
    return (
        (None if changes else "already_pending_complete_or_not_approved"),
        changes,
        before,
    )


def apply_manifest(manifest, *, limit=100, max_attempts=8):
    entries = validate_manifest(manifest)
    if not 1 <= limit <= 1000:
        raise ValueError("recovery_apply_limit_invalid")
    now = timezone.now()
    receipt = {
        "manifest_sha256": manifest["sha256"],
        "applied_at": now.isoformat(),
        "requeued": [],
        "skipped": {},
        "remaining": 0,
    }
    # Inspect the frozen cohort once, then lock only the bounded write set.
    # Repeated apply must not issue one transaction for every already-done row.
    snapshots = {
        str(state.pk): state
        for state in PostEnrichmentState.objects.filter(
            pk__in=[entry["post_id"] for entry in entries],
        ).only(*FIELDS, "source_collection_job_id", "claim_expires_at")
    }
    for entry in entries:
        reason, _, _ = _recovery_decision(
            snapshots.get(entry["post_id"]), entry, now=now, max_attempts=max_attempts
        )
        if reason:
            receipt["skipped"][entry["post_id"]] = reason
            continue
        if len(receipt["requeued"]) >= limit:
            receipt["remaining"] += 1
            continue
        with transaction.atomic():
            state = (
                PostEnrichmentState.objects.select_for_update()
                .filter(pk=entry["post_id"])
                .first()
            )
            reason, changes, before = _recovery_decision(
                state, entry, now=timezone.now(), max_attempts=max_attempts
            )
            if reason:
                receipt["skipped"][entry["post_id"]] = reason
                continue
            changes.update(
                claim_owner="", claim_run_id="", claimed_at=None, claim_expires_at=None
            )
            for field, value in changes.items():
                setattr(state, field, value)
            state.save(update_fields=[*changes, "updated_at"])
            receipt["requeued"].append(
                {
                    "post_id": state.pk,
                    "before": before,
                    "reset_reason": entry["reset_reason"],
                }
            )
    return receipt
