"""Explicit operator approval of a bounded native-X cohort; no model inference."""

from __future__ import annotations

import time
import uuid

from django.db import transaction
from django.utils import timezone

from core.models import Account, OfficialCompanyAccountState, OfficialCompanyAttempt
from core.official_company_accounts import (
    digest,
    register_account,
    x_account_identifier,
)
from core.official_company_offerings import validate_screen


def validate_manifest(manifest, *, expected_count):
    if not isinstance(manifest, dict) or set(manifest) != {
        "approval_reference",
        "accounts",
    }:
        raise ValueError("invalid induction manifest")
    reference = manifest["approval_reference"]
    if not isinstance(reference, str) or not 8 <= len(reference) <= 200:
        raise ValueError("explicit owner approval reference required")
    rows = manifest["accounts"]
    if (
        not isinstance(rows, list)
        or not 1 <= expected_count <= 500
        or len(rows) != expected_count
    ):
        raise ValueError("induction cohort count mismatch")
    identifiers = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "native_x_id",
            "organization_name",
            "evidence",
            "screen",
        }:
            raise ValueError("invalid induction account")
        identifier = row["native_x_id"]
        if (
            not isinstance(identifier, str)
            or not identifier.isdecimal()
            or identifier in identifiers
        ):
            raise ValueError("invalid or duplicate native X identifier")
        identifiers.add(identifier)
        name = row["organization_name"]
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise ValueError("bounded organization name required")
        if (
            not isinstance(row["evidence"], dict)
            or row["evidence"].get("provider") != "x"
            or row["evidence"].get("external_identifier") != identifier
        ):
            raise ValueError("offering evidence account mismatch")
        validate_screen(row["screen"], row["evidence"])
    return "owner-cohort:" + digest(manifest)


def induce_accounts(manifest, *, cfg, expected_count, deadline=None):
    policy = validate_manifest(manifest, expected_count=expected_count)
    if not cfg.registration_enabled:
        raise ValueError("official company registration is disabled")
    results = []
    for row in manifest["accounts"]:
        if deadline and time.monotonic() + 2 > deadline:
            break
        identifier = row["native_x_id"]
        with transaction.atomic():
            account = (
                Account.objects.select_for_update()
                .filter(
                    data_source_id="x",
                    author_id=identifier,
                )
                .first()
            )
            if account is None:
                results.append({"native_x_id": identifier, "status": "missing_account"})
                continue
            x_account_identifier(account)
            state = (
                OfficialCompanyAccountState.objects.select_for_update()
                .filter(account=account)
                .first()
            )
            if state is None or state.status == "suppressed":
                results.append(
                    {"native_x_id": identifier, "status": "missing_or_suppressed"}
                )
                continue
            if (
                state.status == "claimed"
                and state.claim_expires_at
                and state.claim_expires_at > timezone.now()
            ):
                results.append({"native_x_id": identifier, "status": "claim_busy"})
                continue
            existing = state.attempt_records.filter(
                policy_version=policy, status="owner_attested"
            ).exists()
            if not existing:
                source = {
                    "id": policy,
                    "text": "Explicit owner approval of this fixed account for Call A collection: "
                    + manifest["approval_reference"],
                    "observed_at": timezone.now().isoformat(),
                }
                evidence = {
                    **state.evidence,
                    "sources": [*state.evidence.get("sources", []), source],
                }
                decision = {
                    **state.decision,
                    "outcome": "accepted",
                    "organization_name": row["organization_name"],
                    "owner_approval": {
                        "reference": manifest["approval_reference"],
                        "manifest_digest": policy,
                    },
                    "internal_offering_screen": {
                        "screen": row["screen"],
                        "evidence": row["evidence"],
                    },
                }
                state.evidence = evidence
                state.decision = decision
                state.model = "owner-attestation"
                state.policy_version = policy
                state.status = (
                    "accepted" if state.status != "registered" else "registered"
                )
                state.claim_token = ""
                state.claim_expires_at = None
                state.next_attempt_at = None
                state.last_error = ""
                state.save()
                OfficialCompanyAttempt.objects.create(
                    state=state,
                    evidence_hash=state.evidence_hash,
                    evidence=evidence,
                    claim_token=uuid.uuid4().hex,
                    model=state.model,
                    policy_version=policy,
                    status="owner_attested",
                    decision=decision,
                    reserved_usd=0,
                    actual_usd=0,
                    completed_at=timezone.now(),
                )
            elif state.status not in {"accepted", "registered"}:
                results.append(
                    {
                        "native_x_id": identifier,
                        "status": "review_needed",
                        "error": state.last_error,
                    }
                )
                continue
        intent = register_account(state.pk, cfg=cfg)
        state.refresh_from_db()
        results.append(
            {
                "native_x_id": identifier,
                "status": state.status,
                "intent_id": intent,
                "error": state.last_error,
            }
        )
    return {
        "policy": policy,
        "requested": len(manifest["accounts"]),
        "processed": len(results),
        "accounts": results,
    }
