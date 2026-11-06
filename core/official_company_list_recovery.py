"""Exact-target, read-before-release recovery for an interrupted list delivery."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import timedelta
from pathlib import Path

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.models import OfficialCompanyListIntent, OfficialCompanyOwnerCredential
from core.official_company_credentials import (
    CREDENTIAL_KEY,
    RECOVERY_VALIDATION_PENDING,
    OwnerTokenStore,
    clear_credential_stop,
    credential_diagnostics,
    credential_error_diagnostics,
    credential_stop_fields,
)
from core.official_company_lists import (
    _BILLING_ERROR,
    XListError,
    _complete,
    build_owner_list_client,
    list_cooldown,
    safe_error_code,
)
from core.official_company_lock import official_company_writer_lock


def read_recovery_json(path, *, error="recovery_snapshot_invalid", sha256=None):
    """Bounded local input; no contents or operating-system exceptions escape."""
    try:
        with Path(path).open("rb") as source:
            raw = source.read(65537)
        if len(raw) > 65536 or (sha256 is not None and hashlib.sha256(raw).hexdigest() != sha256):
            raise ValueError
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise TypeError
        return value
    except (OSError, TypeError, ValueError):
        raise XListError(error) from None


def _stamp(value):
    return value.isoformat() if value else None


def _rows(intent_id, *, lock=False):
    credentials = OfficialCompanyOwnerCredential.objects.defer("encrypted_tokens")
    intents = OfficialCompanyListIntent.objects.select_related("state", "account")
    if lock:
        credentials = credentials.select_for_update()
        intents = intents.select_for_update()
    credential = credentials.filter(pk=CREDENTIAL_KEY).first()
    intent = intents.filter(pk=intent_id).first()
    if credential is None:
        raise XListError("owner_credential_not_provisioned")
    if intent is None:
        raise XListError("recovery_target_missing").with_credential(credential)
    return credential, intent


def _target_snapshot(intent):
    return {
        "intent_id": intent.pk, "list_id": str(intent.list_id),
        "intent_status": intent.status, "intent_error": safe_error_code(intent.last_error),
        "intent_updated_at": _stamp(intent.updated_at), "evidence_hash": intent.evidence_hash,
        "account_id": str(intent.account_id), "native_account_id": intent.native_account_id,
        "current_native_account_id": intent.account.author_id,
        "state_id": intent.state_id, "state_account_id": str(intent.state.account_id),
        "state_native_account_id": intent.state.native_account_id,
        "state_status": intent.state.status, "state_evidence_hash": intent.state.evidence_hash,
        "state_updated_at": _stamp(intent.state.updated_at), "attempts": intent.attempts,
        "claim_token": intent.claim_token, "claim_expires_at": _stamp(intent.claim_expires_at),
        "next_attempt_at": _stamp(intent.next_attempt_at),
        "add_requested_at": _stamp(intent.add_requested_at),
        "add_acknowledged_at": _stamp(intent.add_acknowledged_at),
    }


def _snapshot(credential, intent):
    return {
        "version": 1, "credential_key": credential.key,
        "credential_updated_at": _stamp(credential.updated_at),
        "credential_status": credential.status,
        **credential_diagnostics(credential), **_target_snapshot(intent),
    }


def _claim_token(credential, intent):
    binding = f"{credential.key}:{_stamp(credential.blocked_at)}:{intent.pk}"
    return "recovery:" + hashlib.sha256(binding.encode()).hexdigest()[:55]


def _known_hold(credential):
    return (
        credential.status == "blocked" and credential.blocked_origin == "operator"
        and credential.blocked_reason == RECOVERY_VALIDATION_PENDING and credential.blocked_at is not None
    )


def _validate_receipt(credential, *, acknowledged, path, sha256):
    if not acknowledged or not path or not sha256:
        raise XListError("recovery_operator_receipt_required")
    receipt = read_recovery_json(path, error="recovery_operator_receipt_invalid", sha256=sha256)
    try:
        attempted = parse_datetime(receipt.get("attempted_at", ""))
        confirmed = parse_datetime(receipt.get("confirmed_at", ""))
        valid = (
            receipt.get("status") == "confirmed"
            and receipt.get("automated_credential_hold_preserved") is True
            and receipt.get("independently_confirmed") is True
            and type(receipt.get("refresh_attempts")) is int and receipt["refresh_attempts"] == 1
            and type(receipt.get("refresh_http_status")) is int and receipt["refresh_http_status"] == 200
            and type(receipt.get("credential_revision_after")) is int
            and receipt["credential_revision_after"] == credential.revision
            and type(receipt.get("credential_revision_before")) is int
            and receipt["credential_revision_before"] == credential.revision - 1
            and attempted is not None and confirmed is not None
            and timezone.is_aware(attempted) and timezone.is_aware(confirmed)
            and attempted <= credential.updated_at <= confirmed
        )
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise XListError("recovery_operator_receipt_invalid")


def _validate_target(intent):
    if (
        intent.status != "blocked_auth" or intent.state.status != "registered"
        or not intent.evidence_hash or intent.evidence_hash != intent.state.evidence_hash
        or intent.account_id != intent.state.account_id
        or not str(intent.account.author_id or "").isdecimal()
        or intent.native_account_id != intent.account.author_id
        or intent.state.native_account_id != intent.account.author_id
    ):
        raise XListError("recovery_target_state")
    if intent.attempts >= 5:
        raise XListError("recovery_attempt_limit")


def _validate(credential, intent, *, cfg, list_id, expected, apply, receipt):
    if not cfg.enabled or not cfg.list_sync_enabled:
        raise XListError("recovery_disabled")
    if (
        str(list_id) != str(intent.list_id) or str(list_id) != str(cfg.list_id)
        or CREDENTIAL_KEY != f"x-owner-{cfg.owner_id}-list-{list_id}"
    ):
        raise XListError("recovery_list_mismatch")
    if expected is None and apply:
        raise XListError("recovery_snapshot_required")
    if expected is not None and expected != _snapshot(credential, intent):
        raise XListError("recovery_snapshot_mismatch")
    _validate_target(intent)
    if _known_hold(credential):
        if intent.claim_token != _claim_token(credential, intent) or intent.claim_expires_at is not None:
            raise XListError("recovery_active_claim")
        return
    if intent.claim_token or intent.claim_expires_at is not None:
        raise XListError("recovery_active_claim")
    if intent.last_error != _BILLING_ERROR:
        raise XListError("recovery_not_billing")
    if credential.status == "ready":
        # Replacing credentials does not requeue the dated billing failure.
        return
    if credential.status != "blocked":
        raise XListError("recovery_credential_state")
    if credential.blocked_reason == _BILLING_ERROR and credential.blocked_origin == "provider":
        return
    if credential.blocked_origin in {"", "legacy_unknown"} and credential.blocked_reason in {"", "unknown"}:
        _validate_receipt(credential, **receipt)
        return
    raise XListError("recovery_credential_state")


def _record_failure(intent_id, target, error, *, revision, hold_at):
    with transaction.atomic():
        credential, intent = _rows(intent_id, lock=True)
        if (
            error.auth and error.error_origin != "local_credential_gate"
            and credential.revision == revision and _known_hold(credential)
            and credential.blocked_at == hold_at
        ):
            origin = "provider" if error.error_origin == "provider" else "local_configuration"
            for name, value in credential_stop_fields(reason=str(error), origin=origin).items():
                setattr(credential, name, value)
            credential.save(update_fields=["blocked_reason", "blocked_origin", "blocked_at", "updated_at"])
        if _target_snapshot(intent) != target:
            return  # Preserve a concurrent suppression, evidence change or operator edit.
        retry_at = timezone.now() + timedelta(hours=24) if error.billing else (
            error.retry_at or timezone.now() + timedelta(minutes=15)
        )
        pause = list_cooldown(intent.list_id)
        intent.next_attempt_at = max(
            value for value in (retry_at, intent.next_attempt_at, pause["next_attempt_at"] if pause else None) if value
        )
        # Report this fresh error in the command result, but retain the reason
        # governing a longer provider pause across another recovery attempt.
        intent.last_error = (
            pause["last_error"] if pause and pause["next_attempt_at"] >= retry_at else str(error)
        )
        intent.save(update_fields=["last_error", "next_attempt_at", "updated_at"])


def recover_list_billing(
    *, cfg, intent_id, list_id, apply=False, expected_snapshot=None,
    acknowledge_operator_hold=False, operator_hold_receipt=None,
    operator_hold_receipt_sha256=None, deadline=None,
):
    """Preview without secrets; apply performs GET validation under the dedicated lock."""
    receipt = {
        "acknowledged": acknowledge_operator_hold, "path": operator_hold_receipt,
        "sha256": operator_hold_receipt_sha256,
    }
    client = store = None
    target = None
    try:
        credential, intent = _rows(intent_id)
        result = {
            "status": "preview", "eligible": False, "provider_request_made": False,
            "credential": credential_diagnostics(credential),
            "snapshot": _snapshot(credential, intent),
            "planned_effects": {
                "present": "confirmed", "complete_absence": "verify_needed",
                "add_requests": 0, "preserve_attempts_and_add_history": True,
            },
            "queue_recorded_at": _stamp(intent.updated_at),
            "error_origin": "local_queue_gate" if credential.status == "ready" else "local_credential_gate",
        }
        _validate(
            credential, intent, cfg=cfg, list_id=list_id, expected=expected_snapshot,
            apply=apply, receipt=receipt,
        )
        if not apply:
            result["eligible"] = True
            return result
        with official_company_writer_lock(
            execution_mode="manual", entrypoint="recover-list-billing", run_id=f"list-recovery-{intent_id}",
        ) as lease:
            if not lease.acquired:
                return {**result, "status": "discovery_busy"}
            try:
                with transaction.atomic():
                    credential, intent = _rows(intent_id, lock=True)
                    _validate(
                        credential, intent, cfg=cfg, list_id=list_id, expected=expected_snapshot,
                        apply=True, receipt=receipt,
                    )
                    cooldown = intent.next_attempt_at
                    if not _known_hold(credential):
                        credential.status = "blocked"
                        for name, value in credential_stop_fields(reason=RECOVERY_VALIDATION_PENDING, origin="operator").items():
                            setattr(credential, name, value)
                        credential.save(update_fields=["status", "blocked_reason", "blocked_origin", "blocked_at", "updated_at"])
                        intent.claim_token = _claim_token(credential, intent)
                        intent.save(update_fields=["claim_token", "updated_at"])
                    target = _target_snapshot(intent)
                    hold_revision, hold_at = credential.revision, credential.blocked_at
                # No database transaction/row lock remains open across provider HTTP.
                store = OwnerTokenStore.from_env()
                with store.recovery_hold(revision=hold_revision, blocked_at=hold_at):
                    client = build_owner_list_client(cfg, token_store=store)
                    client.limit_deadline(deadline or time.monotonic() + 45)
                    client.preflight()
                    members, complete = client.members()
                    if not complete:
                        raise XListError("recovery_incomplete_membership")
                    with transaction.atomic():
                        credential, intent = _rows(intent_id, lock=True)
                        if not store.matches_recovery_hold(credential):
                            raise XListError("recovery_hold_changed")
                        if _target_snapshot(intent) != target:
                            raise XListError("recovery_target_changed")
                        _validate_target(intent)
                        status = "confirmed" if intent.native_account_id in members else "verify_needed"
                        pause = list_cooldown(intent.list_id)
                        due = max(value for value in (
                            timezone.now(), cooldown, pause["next_attempt_at"] if pause else None,
                        ) if value)
                        credential.status = "ready"
                        clear_credential_stop(credential)
                        credential.save(update_fields=["status", "blocked_reason", "blocked_origin", "blocked_at", "updated_at"])
                        if not _complete(
                            intent, status, error=pause["last_error"] if pause else "",
                            retry_at=due if pause or status == "verify_needed" else None,
                            preserve_attempts=True,
                        ):
                            raise XListError("recovery_target_changed")
                    return {
                        "status": status, "intent_id": intent_id, "list_id": str(list_id),
                        "provider_request_made": client.provider_request_made,
                        **credential_diagnostics(credential),
                        "retry_at": _stamp(due) if pause or status == "verify_needed" else None,
                    }
            except Exception as exc:  # noqa: BLE001 - retain the hold under the writer lock
                error = exc if isinstance(exc, XListError) else XListError("unexpected_error")
                error.provider_request_made |= bool(client and client.provider_request_made) or bool(store and store.provider_request_made)
                if target is not None:
                    _record_failure(
                        intent_id, target, error,
                        revision=store.revision if store and store.revision is not None else hold_revision,
                        hold_at=hold_at,
                    )
                if store is not None:
                    store.annotate_error(error)
                raise error from None
    except Exception as exc:  # noqa: BLE001 - provider errors must never leak credentials
        error = exc if isinstance(exc, XListError) else XListError("unexpected_error")
        error.provider_request_made |= bool(client and client.provider_request_made) or bool(store and store.provider_request_made)
        return {
            "status": "blocked" if apply else "preview", "eligible": False,
            **credential_error_diagnostics(error),
            **({"snapshot": result["snapshot"]} if "result" in locals() else {}),
        }
