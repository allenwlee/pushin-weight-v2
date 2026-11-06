"""Encrypted OAuth token rotation; the dedicated key stays outside PostgreSQL."""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager

import requests
from cryptography.fernet import Fernet, InvalidToken
from django.db import transaction
from django.utils import timezone

from core.models import OfficialCompanyOwnerCredential
from core.official_company_lists import XListError, safe_error_code

CREDENTIAL_KEY = "x-owner-17456158-list-2067062923525275922"
BLOCK_ORIGINS = frozenset({"provider", "refresh", "local_configuration", "operator", "legacy_unknown"})
REQUIRED_SCOPES = {"tweet.read", "users.read", "list.read", "list.write", "offline.access"}


def credential_diagnostics(row=None):
    """Read active stop facts without loading configuration or encrypted tokens."""
    if row is None:
        row = OfficialCompanyOwnerCredential.objects.only(
            "status", "revision", "blocked_reason", "blocked_origin", "blocked_at",
        ).filter(pk=CREDENTIAL_KEY).first()
    result = {
        "credential_revision": row.revision if row else None,
        "credential_status": row.status if row else None,
        "blocked_reason": "", "blocked_origin": "", "blocked_at": None,
    }
    if row is not None and row.status != "ready":
        known = row.blocked_origin in BLOCK_ORIGINS and row.blocked_origin != "legacy_unknown"
        reason = safe_error_code(row.blocked_reason) if known else "unknown"
        result.update(
            blocked_reason=reason,
            blocked_origin=row.blocked_origin if known else "legacy_unknown",
            blocked_at=row.blocked_at.isoformat() if known and reason != "unknown" and row.blocked_at else None,
        )
    return result


def credential_error_diagnostics(error):
    """Keep the attempted revision; distinguish any newer credential's state."""
    current = credential_diagnostics()
    attempted = error.diagnostics()
    if error.credential_revision in {None, current["credential_revision"]}:
        attempted.update(current)
    return {**attempted, "credential": current}


def credential_stop_fields(*, reason, origin, at=None):
    """One validation boundary for row saves and compare-and-update writers."""
    if origin not in BLOCK_ORIGINS or safe_error_code(reason) != reason:
        raise ValueError("Invalid credential stop code or origin")
    return {
        "blocked_reason": reason, "blocked_origin": origin,
        "blocked_at": None if origin == "legacy_unknown" else (at or timezone.now()),
    }


def clear_credential_stop(row):
    row.blocked_reason = ""
    row.blocked_origin = ""
    row.blocked_at = None


class OwnerTokenStore:
    def __init__(self, *, key, client_id, client_secret):
        if not key or not client_id or not client_secret:
            raise XListError("missing_owner_client_configuration", auth=True)
        try:
            self._cipher = Fernet(key)
        except (ValueError, TypeError):
            raise XListError("invalid_credential_key", auth=True) from None
        self._client_id = client_id
        self._client_secret = client_secret
        self.revision = None
        self.provider_request_made = False
        self.redactions = {client_secret}
        self._recovery_revision = None
        self._recovery_blocked_at = None
        self.refresh_attempts = 0

    @classmethod
    def from_env(cls):
        return cls(
            key=os.environ.get("PUSHINWEIGHT_X_LIST_ENCRYPTION_KEY"),
            client_id=os.environ.get("PUSHINWEIGHT_X_LIST_CLIENT_ID"),
            client_secret=os.environ.get("PUSHINWEIGHT_X_LIST_CLIENT_SECRET"),
        )

    def begin_invocation(self):
        self.provider_request_made = False
        self.revision = None
        self.refresh_attempts = 0

    @property
    def recovery_active(self):
        return self._recovery_revision is not None

    @contextmanager
    def recovery_hold(self, *, revision, blocked_at):
        """Permit only this guarded, durable hold; never make it generally ready."""
        if self.recovery_active or blocked_at is None:
            raise XListError("recovery_hold_changed", auth=True, error_origin="local_credential_gate")
        self._recovery_revision = revision
        self._recovery_blocked_at = blocked_at
        self.refresh_attempts = 0
        try:
            yield self
        finally:
            self._recovery_revision = None
            self._recovery_blocked_at = None

    def matches_recovery_hold(self, row):
        return (
            self.recovery_active and row.revision == self._recovery_revision
            and row.status == "blocked" and row.blocked_origin == "operator"
            and row.blocked_reason == "recovery_validation_pending"
            and row.blocked_at == self._recovery_blocked_at
        )

    def _row(self, *, for_update=False):
        query = OfficialCompanyOwnerCredential.objects
        if for_update:
            query = query.select_for_update()
        try:
            row = query.get(pk=CREDENTIAL_KEY)
        except OfficialCompanyOwnerCredential.DoesNotExist:
            raise XListError("owner_credential_not_provisioned", auth=True) from None
        self.revision = row.revision
        return row

    def _require_ready(self, row):
        if self.recovery_active:
            if not self.matches_recovery_hold(row):
                raise XListError(
                    "recovery_hold_changed", auth=True, error_origin="local_credential_gate",
                    provider_request_made=self.provider_request_made,
                ).with_credential(row)
            return
        if row.status != "ready":
            raise XListError(
                "credential_blocked", auth=True, error_origin="local_credential_gate",
                provider_request_made=self.provider_request_made,
            ).with_credential(row)

    def _decode(self, row):
        try:
            value = json.loads(self._cipher.decrypt(bytes(row.encrypted_tokens)))
            if not isinstance(value, dict) or not all(
                isinstance(value.get(key), str) and value[key]
                for key in ("access_token", "refresh_token", "client_id")
            ):
                raise ValueError("Invalid token record")
        except (InvalidToken, ValueError, TypeError):
            raise XListError("credential_decryption", auth=True).with_credential(row) from None
        if value["client_id"] != self._client_id:
            raise XListError("credential_client_mismatch", auth=True).with_credential(row)
        self.redactions.update((value["access_token"], value["refresh_token"]))
        return value

    def _encode(self, value):
        return self._cipher.encrypt(json.dumps(value).encode())

    def provision(self, *, access_token, refresh_token, replace=False):
        if not access_token or not refresh_token:
            raise XListError("missing_owner_tokens", auth=True)
        value = {
            "access_token": access_token, "refresh_token": refresh_token,
            "client_id": self._client_id, "expires_at": None, "scopes": [],
        }
        with transaction.atomic():
            row, created = OfficialCompanyOwnerCredential.objects.select_for_update().get_or_create(
                key=CREDENTIAL_KEY, defaults={"encrypted_tokens": self._encode(value)},
            )
            if not created:
                if not replace:
                    raise XListError("credential_already_provisioned", auth=True).with_credential(row)
                row.encrypted_tokens = self._encode(value)
                row.status = "ready"
                row.revision += 1
                clear_credential_stop(row)
                row.save()
            self.revision = row.revision

    def load(self):
        row = self._row()
        self._require_ready(row)
        return self._decode(row)

    def access_token(self):
        value = self.load()
        if value.get("expires_at") and value["expires_at"] <= time.time() + 300:
            return self.refresh()
        return value["access_token"]

    def annotate_error(self, error):
        # A late response retains its attempted revision, and cannot borrow a
        # newer token pair's stop facts. This read never decrypts the payload.
        row = OfficialCompanyOwnerCredential.objects.only(
            "status", "revision", "blocked_reason", "blocked_origin", "blocked_at",
        ).filter(pk=CREDENTIAL_KEY, revision=self.revision).first()
        if row is not None:
            error.with_credential(row)
        elif self.revision is not None:
            error.credential_revision = self.revision
        error.provider_request_made |= self.provider_request_made
        return error

    def block(self, *, reason, origin):
        if any(secret and secret in reason for secret in self.redactions):
            reason = "http_403:unspecified" if reason.startswith("http_403:") else "unknown"
        fields = credential_stop_fields(reason=reason, origin=origin)
        if self.revision is None:
            return False
        query = OfficialCompanyOwnerCredential.objects.filter(pk=CREDENTIAL_KEY, revision=self.revision)
        if self.recovery_active:
            query = query.filter(
                revision=self._recovery_revision, status="blocked", blocked_origin="operator",
                blocked_reason="recovery_validation_pending", blocked_at=self._recovery_blocked_at,
            )
        else:
            query = query.filter(status="ready")
        return bool(query.update(status="blocked", updated_at=timezone.now(), **fields))

    def refresh(self, *, request=requests.request):
        if self.recovery_active and self.refresh_attempts >= 1:
            raise XListError(
                "recovery_refresh_limit", auth=True, error_origin="local_credential_gate",
                provider_request_made=self.provider_request_made,
            )
        # Persist before HTTP: a crash cannot silently reuse a rotated token.
        with transaction.atomic():
            row = self._row(for_update=True)
            self._require_ready(row)
            value = self._decode(row)
            revision = row.revision
            row.status = "refreshing"
            for name, field_value in credential_stop_fields(reason="refresh_in_progress", origin="refresh").items():
                setattr(row, name, field_value)
            row.save(update_fields=["status", "blocked_reason", "blocked_origin", "blocked_at", "updated_at"])
        self.refresh_attempts += 1
        failure_reason = "refresh_transport_uncertain"
        error_origin = "provider"
        try:
            self.provider_request_made = True
            response = request(
                "POST", "https://api.x.com/2/oauth2/token",
                auth=(self._client_id, self._client_secret),
                data={"grant_type": "refresh_token", "refresh_token": value["refresh_token"]},
                timeout=10, allow_redirects=False,
            )
            if response.status_code != 200:
                failure_reason = "refresh_http_" + str(response.status_code)
                raise ValueError("Refresh rejected")
            failure_reason = "refresh_response_uncertain"
            payload = response.json()
            if not isinstance(payload, dict) or not all(
                isinstance(payload.get(key), str) and payload[key]
                for key in ("access_token", "refresh_token", "scope")
            ):
                raise ValueError("Invalid rotated tokens")
            expires = payload.get("expires_in")
            if type(expires) is not int or expires <= 0:
                raise ValueError("Invalid expiry")
            scopes = set(payload["scope"].split())
            if not REQUIRED_SCOPES <= scopes:
                raise ValueError("Missing scopes")
            value.update(
                access_token=payload["access_token"], refresh_token=payload["refresh_token"],
                expires_at=time.time() + expires, scopes=sorted(scopes),
            )
            self.redactions.update((value["access_token"], value["refresh_token"]))
            failure_reason = "refresh_save_uncertain"
            error_origin = "local_configuration"
            with transaction.atomic():
                row = OfficialCompanyOwnerCredential.objects.select_for_update().get(pk=CREDENTIAL_KEY)
                if row.revision != revision or row.status != "refreshing":
                    raise XListError("credential_revision_changed", auth=True)
                row.encrypted_tokens = self._encode(value)
                row.revision += 1
                if self.recovery_active:
                    row.status = "blocked"
                    for name, field_value in credential_stop_fields(
                        reason="recovery_validation_pending", origin="operator", at=self._recovery_blocked_at,
                    ).items():
                        setattr(row, name, field_value)
                else:
                    row.status = "ready"
                    clear_credential_stop(row)
                row.save()
                self.revision = row.revision
                if self.recovery_active:
                    self._recovery_revision = row.revision
            return value["access_token"]
        except Exception as exc:  # noqa: BLE001 - never expose provider bodies or token-bearing exceptions
            OfficialCompanyOwnerCredential.objects.filter(
                pk=CREDENTIAL_KEY, revision=revision, status="refreshing",
            ).update(
                status="blocked", updated_at=timezone.now(),
                **credential_stop_fields(reason=safe_error_code(failure_reason), origin="refresh"),
            )
            error = XListError(
                "credential_revision_changed" if isinstance(exc, XListError) else "refresh_failed",
                auth=True, error_origin=error_origin, provider_request_made=self.provider_request_made,
            )
            raise self.annotate_error(error) from None
