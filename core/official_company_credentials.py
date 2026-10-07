"""Encrypted OAuth token rotation; the dedicated key stays outside PostgreSQL."""

from __future__ import annotations

import json
import os
import time

import requests
from cryptography.fernet import Fernet, InvalidToken
from django.db import transaction

from core.models import OfficialCompanyOwnerCredential
from core.official_company_lists import XListError

CREDENTIAL_KEY = "x-owner-17456158-list-2067062923525275922"
REQUIRED_SCOPES = {
    "tweet.read",
    "users.read",
    "list.read",
    "list.write",
    "offline.access",
}


class OwnerTokenStore:
    def __init__(self, *, key, client_id, client_secret):
        if not key or not client_id or not client_secret:
            raise XListError("missing_owner_client_configuration", auth=True)
        try:
            self._cipher = Fernet(key)
        except (ValueError, TypeError) as exc:
            raise XListError("invalid_credential_key", auth=True) from exc
        self._client_id = client_id
        self._client_secret = client_secret

    @classmethod
    def from_env(cls):
        return cls(
            key=os.environ.get("PUSHINWEIGHT_X_LIST_ENCRYPTION_KEY"),
            client_id=os.environ.get("PUSHINWEIGHT_X_LIST_CLIENT_ID"),
            client_secret=os.environ.get("PUSHINWEIGHT_X_LIST_CLIENT_SECRET"),
        )

    def _decode(self, row):
        try:
            value = json.loads(self._cipher.decrypt(bytes(row.encrypted_tokens)))
        except (InvalidToken, ValueError, TypeError) as exc:
            raise XListError("credential_decryption", auth=True) from exc
        if value.get("client_id") != self._client_id:
            raise XListError("credential_client_mismatch", auth=True)
        return value

    def _encode(self, value):
        return self._cipher.encrypt(json.dumps(value).encode())

    def provision(self, *, access_token, refresh_token, replace=False):
        if not access_token or not refresh_token:
            raise XListError("missing_owner_tokens", auth=True)
        value = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "client_id": self._client_id,
            "expires_at": None,
            "scopes": [],
        }
        with transaction.atomic():
            row, created = (
                OfficialCompanyOwnerCredential.objects.select_for_update().get_or_create(
                    key=CREDENTIAL_KEY,
                    defaults={"encrypted_tokens": self._encode(value)},
                )
            )
            if not created:
                if not replace:
                    raise XListError("credential_already_provisioned", auth=True)
                row.encrypted_tokens = self._encode(value)
                row.status = "ready"
                row.revision += 1
                row.save()

    def load(self):
        try:
            row = OfficialCompanyOwnerCredential.objects.get(pk=CREDENTIAL_KEY)
        except OfficialCompanyOwnerCredential.DoesNotExist as exc:
            raise XListError("owner_credential_not_provisioned", auth=True) from exc
        if row.status != "ready":
            raise XListError("credential_blocked", auth=True)
        return self._decode(row)

    def access_token(self):
        value = self.load()
        if value.get("expires_at") and value["expires_at"] <= time.time() + 300:
            return self.refresh()
        return value["access_token"]

    def block(self):
        OfficialCompanyOwnerCredential.objects.filter(
            pk=CREDENTIAL_KEY, status="ready"
        ).update(status="blocked")

    def refresh(self, *, request=requests.request):
        # Persist the in-flight marker before HTTP. A process crash / uncertain
        # response cannot silently reuse a possibly rotated single-use token.
        with transaction.atomic():
            row = OfficialCompanyOwnerCredential.objects.select_for_update().get(
                pk=CREDENTIAL_KEY
            )
            if row.status != "ready":
                raise XListError("credential_blocked", auth=True)
            value = self._decode(row)
            revision = row.revision
            row.status = "refreshing"
            row.save(update_fields=["status", "updated_at"])
        try:
            response = request(
                "POST",
                "https://api.x.com/2/oauth2/token",
                auth=(self._client_id, self._client_secret),
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": value["refresh_token"],
                },
                timeout=10,
                allow_redirects=False,
            )
            if response.status_code != 200:
                raise XListError("refresh_http_" + str(response.status_code), auth=True)
            payload = response.json()
            if not all(
                isinstance(payload.get(k), str) and payload[k]
                for k in ["access_token", "refresh_token"]
            ):
                raise ValueError("missing rotated tokens")
            expires = payload.get("expires_in")
            if (
                not isinstance(expires, int)
                or isinstance(expires, bool)
                or expires <= 0
            ):
                raise ValueError("invalid expiry")
            scopes = set(payload.get("scope", "").split())
            if not REQUIRED_SCOPES <= scopes:
                raise ValueError("missing scopes")
            value.update(
                access_token=payload["access_token"],
                refresh_token=payload["refresh_token"],
                expires_at=time.time() + expires,
                scopes=sorted(scopes),
            )
            with transaction.atomic():
                row = OfficialCompanyOwnerCredential.objects.select_for_update().get(
                    pk=CREDENTIAL_KEY
                )
                if row.revision != revision or row.status != "refreshing":
                    raise XListError("credential_revision_changed", auth=True)
                row.encrypted_tokens = self._encode(value)
                row.revision += 1
                row.status = "ready"
                row.save()
            return value["access_token"]
        except Exception as exc:
            OfficialCompanyOwnerCredential.objects.filter(
                pk=CREDENTIAL_KEY, revision=revision, status="refreshing"
            ).update(status="blocked")
            raise XListError("refresh_failed", auth=True) from exc
