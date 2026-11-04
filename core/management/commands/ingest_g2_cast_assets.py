"""Ingest a frozen, identity-resolved cast-asset batch with durable receipts."""

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

from django.core.files.storage import storages
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from core.models import (
    AccountProfileSnapshot,
    Person,
    PersonAccount,
    PersonBrandAffiliation,
    PersonBrandAffiliationEvidence,
    PersonMedia,
    PersonName,
    PersonNameEvidence,
)
from core.staff_assets.g2_cast_ingest import (
    _validated_image,
    _validated_video,
    ingest_image,
    ingest_video,
    validate_entry,
)
from core.staff_assets.media import MAX_BYTES


class Command(BaseCommand):
    help = "Preview or import a frozen G2 image/video batch; existing review states are preserved."

    def add_arguments(self, parser):
        parser.add_argument("--manifest", required=True)
        parser.add_argument("--source-root", action="append", default=[])
        parser.add_argument("--from-existing-storage", action="store_true")
        parser.add_argument("--expected-database", required=True)
        parser.add_argument("--expected-bucket", required=True)
        parser.add_argument("--receipt", required=True)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        try:
            raw = Path(options["manifest"]).read_bytes()
            batch = json.loads(raw)
            if batch.get("schema") != "g2-cast-import-batch/v1" or not batch.get(
                "entries"
            ):
                raise ValueError("invalid_or_empty_batch")
            if (
                connection.settings_dict["NAME"] != options["expected_database"]
                or batch.get("target_database") != options["expected_database"]
            ):
                raise ValueError("database_target_mismatch")
            storage = storages["staff_media"]
            if (
                getattr(storage, "bucket_name", None) != options["expected_bucket"]
                or batch.get("target_bucket") != options["expected_bucket"]
            ):
                raise ValueError("bucket_target_mismatch")
            if getattr(storage, "location", "") != batch.get("target_namespace"):
                raise ValueError("storage_namespace_mismatch")
            observed_at = datetime.fromisoformat(batch["inventory_observed_at"])
            if observed_at.utcoffset() is None:
                raise ValueError("observation_time_requires_timezone")
            with (
                Path(options["receipt"]).open("x", encoding="utf-8") as receipt,
                tempfile.TemporaryDirectory(prefix="g2-cast-import-") as temp,
            ):

                def emit(item):
                    receipt.write(json.dumps(item, sort_keys=True) + "\n")
                    receipt.flush()
                    os.fsync(receipt.fileno())

                emit(
                    {
                        "event": "started",
                        "mode": "apply" if options["apply"] else "preview",
                        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
                        "database": options["expected_database"],
                        "bucket": options["expected_bucket"],
                        "count": len(batch["entries"]),
                    }
                )
                ready = []
                seen_attributions = set()
                for index, original in enumerate(batch["entries"]):
                    entry = dict(original)
                    person = Person.objects.get(
                        pk=entry["candidate_person_id"], merged_into__isnull=True
                    )
                    proof = entry.get("identity_resolution") or {}
                    if (
                        proof.get("state") != "verified"
                        or proof.get("person_id") != str(person.pk)
                        or not proof.get("evidence")
                    ):
                        raise ValueError("identity_evidence_missing")
                    if proof.get(
                        "method", "confirmed_name"
                    ) != "confirmed_name" and not re.fullmatch(
                        r"[0-9a-f]{64}", proof.get("source_pack_sha256") or ""
                    ):
                        raise ValueError("source_pack_hash_missing")
                    if proof.get("method", "confirmed_name") == "confirmed_name":
                        if not PersonName.objects.filter(
                            person=person,
                            full_name=proof.get("confirmed_name"),
                            review_status="confirmed",
                        ).exists():
                            raise ValueError("confirmed_identity_name_changed")
                        candidates = PersonMedia.objects.filter(
                            person=person, media_id=entry.get("expected_sha256")
                        ).only("review_history")
                        if not any(
                            isinstance(event, dict)
                            and event.get("event") == "owner_confirmed_media"
                            and event.get("person_id") == str(person.pk)
                            and event.get("sha256") == entry.get("expected_sha256")
                            and bool(event.get("source_reference"))
                            for row in candidates
                            for event in (
                                row.review_history
                                if isinstance(row.review_history, list)
                                else []
                            )
                        ):
                            raise ValueError("confirmed_name_does_not_verify_media")
                    elif proof.get("method") == "owner_selected_cast":
                        if (
                            not proof.get("source_pack_sha256")
                            or (
                                proof.get("owner_confirmation_reference")
                                and proof.get("owner_confirmed_sha256")
                                != entry.get("expected_sha256")
                            )
                            or not PersonNameEvidence.objects.filter(
                                name__person=person,
                                name__full_name=proof.get("owner_selected_name"),
                                source_kind="owner_supplied",
                                collection_method="explicit_owner_cast_selection",
                                source_reference=proof.get("owner_source_reference"),
                            )
                            .exclude(name__review_status="rejected")
                            .exists()
                        ):
                            raise ValueError("owner_cast_identity_evidence_changed")
                    elif proof.get("method") == "owner_confirmed_media":
                        if (
                            not PersonNameEvidence.objects.filter(
                                name__person=person,
                                name__full_name=proof.get("recorded_name"),
                                source_kind="owner_supplied",
                                collection_method="explicit_owner_media_confirmation",
                                source_reference=proof.get("owner_source_reference"),
                            )
                            .exclude(name__review_status="rejected")
                            .exists()
                        ):
                            raise ValueError("owner_media_identity_evidence_changed")
                    elif proof.get("method") == "matched_source_evidence":
                        if (
                            not proof.get("source_pack_sha256")
                            or not PersonNameEvidence.objects.filter(
                                name__person=person,
                                name__full_name=proof.get("source_name"),
                                source_reference=proof.get("matched_source_reference"),
                                source_kind="named_third_party",
                            )
                            .exclude(name__review_status="rejected")
                            .exists()
                        ):
                            raise ValueError("matched_identity_source_changed")
                    elif proof.get("method") == "corroborated_name_context":
                        name = proof.get("source_name") or ""
                        fragment = proof.get("source_context") or ""
                        term = proof.get("source_context_term") or ""
                        if (
                            not proof.get("source_pack_sha256")
                            or not name
                            or name not in fragment
                            or not term
                            or not PersonNameEvidence.objects.filter(
                                name__person=person,
                                name__full_name=name,
                                source_reference=proof.get("matched_source_reference"),
                                source_kind="employment_extraction",
                                source_text__contains=fragment,
                            )
                            .filter(source_text__contains=term)
                            .exclude(name__review_status="rejected")
                            .exists()
                        ):
                            raise ValueError("corroborating_identity_source_changed")
                    elif proof.get("method") == "corroborated_affiliation_source":
                        name = proof.get("source_name") or ""
                        fragment = proof.get("source_context") or ""
                        term = proof.get("source_context_term") or ""
                        if (
                            not proof.get("source_pack_sha256")
                            or not name
                            or name not in fragment
                            or not term
                            or not PersonName.objects.filter(
                                person=person, full_name=name
                            )
                            .exclude(review_status="rejected")
                            .exists()
                            or not PersonBrandAffiliationEvidence.objects.filter(
                                affiliation__person=person,
                                source_post_id=proof.get("source_post_id"),
                                source_post__text__contains=fragment,
                            )
                            .filter(source_post__text__contains=term)
                            .exclude(review_status="rejected")
                            .exists()
                        ):
                            raise ValueError("corroborating_affiliation_source_changed")
                    elif proof.get("method") == "confirmed_name_and_affiliation":
                        if (
                            not PersonNameEvidence.objects.filter(
                                name__person=person,
                                name__full_name=proof.get("confirmed_name"),
                                name__review_status="confirmed",
                                source_reference=proof.get("matched_source_reference"),
                            ).exists()
                            or not PersonBrandAffiliation.objects.filter(
                                person=person,
                                observed_organization_name=proof.get("organization"),
                            )
                            .exclude(review_status="rejected")
                            .exists()
                        ):
                            raise ValueError("confirmed_name_affiliation_changed")
                    elif proof.get("method") == "corroborated_profile_source":
                        snapshot_id = proof.get("source_profile_snapshot_id")
                        account_id = proof.get("candidate_account_id")
                        name = proof.get("source_name")
                        term = proof.get("source_context_term")
                        if (
                            not name
                            or not term
                            or not snapshot_id
                            or not account_id
                            or not AccountProfileSnapshot.objects.filter(
                                pk=snapshot_id, account_id=account_id, display_name=name
                            ).exists()
                            or not PersonAccount.objects.filter(
                                person=person, account_id=account_id
                            )
                            .exclude(resolution_status="rejected")
                            .exists()
                            or not PersonNameEvidence.objects.filter(
                                name__person=person,
                                name__full_name=name,
                                source_kind="employment_extraction",
                                source_reference=f"profile-snapshot:{snapshot_id}",
                                source_text__contains=term,
                            )
                            .exclude(name__review_status="rejected")
                            .exists()
                        ):
                            raise ValueError("corroborating_profile_source_changed")
                    elif proof.get("method") in {
                        "owner_reviewed_candidate",
                        "owner_reviewed_parent",
                    }:
                        if (
                            not re.fullmatch(
                                r"[0-9a-f]{64}",
                                proof.get("owner_decision_sha256") or "",
                            )
                            or not re.fullmatch(
                                r"[0-9a-f]{64}",
                                proof.get("review_artifact_sha256") or "",
                            )
                            or not re.fullmatch(
                                r"[0-9a-f]{64}",
                                proof.get("reviewed_asset_sha256") or "",
                            )
                            or (
                                proof.get("method") == "owner_reviewed_candidate"
                                and proof.get("reviewed_asset_sha256")
                                != entry.get("expected_sha256")
                            )
                            or (
                                proof.get("method") == "owner_reviewed_parent"
                                and proof.get("source_parent_sha256")
                                != entry.get("expected_sha256")
                            )
                            or (
                                proof.get("method") == "owner_reviewed_parent"
                                and not PersonMedia.objects.filter(
                                    person=person,
                                    media_id=proof.get("reviewed_asset_sha256"),
                                    evidence__parent_sha256=entry.get(
                                        "expected_sha256"
                                    ),
                                    evidence__identity_resolution__owner_decision_sha256=proof.get(
                                        "owner_decision_sha256"
                                    ),
                                ).exists()
                            )
                            or not PersonName.objects.filter(
                                person=person, full_name=proof.get("candidate_name")
                            )
                            .exclude(review_status="rejected")
                            .exists()
                            or not PersonAccount.objects.filter(
                                person=person,
                                account_id=proof.get("candidate_account_id"),
                            )
                            .exclude(resolution_status="rejected")
                            .exists()
                        ):
                            raise ValueError("owner_reviewed_candidate_changed")
                    else:
                        raise ValueError("unsupported_identity_method")
                    child_sha = entry.get("source_child_sha256")
                    if child_sha and (
                        not re.fullmatch(r"[0-9a-f]{64}", child_sha)
                        or not PersonMedia.objects.filter(
                            person=person,
                            media_id=child_sha,
                            evidence__parent_sha256=entry.get("expected_sha256"),
                        ).exists()
                    ):
                        raise ValueError("parent_lineage_not_established")
                    validate_entry(person, entry)
                    attribution_key = (
                        str(person.pk),
                        entry["expected_sha256"],
                        entry.get("source_url", ""),
                    )
                    if attribution_key in seen_attributions:
                        raise ValueError("duplicate_batch_attribution")
                    seen_attributions.add(attribution_key)
                    kind = entry.get("media_kind", "image")
                    if kind not in {"image", "video"}:
                        raise ValueError("unsupported_media_kind")
                    roots = options["source_root"]
                    if options["from_existing_storage"]:
                        name = entry["storage_name"]
                        if not name.startswith("sha256/") or ".." in name.split("/"):
                            raise ValueError("invalid_storage_name")
                        with storage.open(name, "rb") as stream:
                            data = stream.read(MAX_BYTES + 1)
                        source = Path(temp) / str(index)
                        source.write_bytes(data)
                        entry["file"] = str(source)
                        roots = [temp]
                    if not roots:
                        raise ValueError("source_root_required")
                    validator = (
                        _validated_image if kind == "image" else _validated_video
                    )
                    _, _, _, extension, _ = validator(
                        entry["file"],
                        entry["expected_sha256"],
                        [Path(root).resolve(strict=True) for root in roots],
                    )
                    if (
                        options["from_existing_storage"]
                        and name
                        != f"sha256/{entry['expected_sha256'][:2]}/{entry['expected_sha256']}.{extension}"
                    ):
                        raise ValueError("storage_name_hash_mismatch")
                    writer = ingest_image if kind == "image" else ingest_video
                    writer(
                        person=person,
                        entry=entry,
                        source_roots=roots,
                        storage=storage,
                        observed_at=observed_at,
                        preview=True,
                    )
                    ready.append((person, entry, roots))
                    emit(
                        {
                            "event": "preflight",
                            "index": index,
                            "sha256": entry["expected_sha256"],
                            "state": "ready",
                        }
                    )
                created = reused = 0
                if options["apply"]:
                    for index, (person, entry, roots) in enumerate(ready):
                        try:
                            writer = (
                                ingest_image
                                if entry.get("media_kind", "image") == "image"
                                else ingest_video
                            )
                            row, added = writer(
                                person=person,
                                entry=entry,
                                source_roots=roots,
                                storage=storage,
                                observed_at=observed_at,
                            )
                        except Exception as exc:
                            emit(
                                {
                                    "event": "item",
                                    "index": index,
                                    "sha256": entry["expected_sha256"],
                                    "state": "error",
                                    "error": type(exc).__name__,
                                }
                            )
                            raise
                        created += int(added)
                        reused += int(not added)
                        emit(
                            {
                                "event": "item",
                                "index": index,
                                "sha256": entry["expected_sha256"],
                                "person_media_id": row.pk,
                                "state": "created" if added else "reused",
                                "review_state": row.suitability,
                                "reuse_status": row.reuse_status,
                            }
                        )
                emit(
                    {
                        "event": "complete",
                        "created": created,
                        "reused": reused,
                        "preflight": len(ready),
                    }
                )
        except Exception as exc:
            detail = f": {exc}" if isinstance(exc, ValueError) else ""
            raise CommandError(
                f"cast asset batch failed: {type(exc).__name__}{detail}"
            ) from exc
        self.stdout.write(
            json.dumps(
                {
                    "mode": "apply" if options["apply"] else "preview",
                    "preflight": len(ready),
                    "created": created,
                    "reused": reused,
                    "receipt": options["receipt"],
                },
                sort_keys=True,
            )
        )
