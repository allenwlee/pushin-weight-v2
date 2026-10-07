"""Bounded, owner-authorized X list writes, separate from observed membership."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta

import requests
from django.db import transaction
from django.db.models import F, Q, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from core.models import OfficialCompanyListIntent
from core.official_company_accounts import x_account_identifier


class XListError(RuntimeError):
    def __init__(self, code, *, auth=False, unknown=False):
        super().__init__(code)
        self.auth = auth
        self.unknown = unknown


@dataclass
class XOwnerListClient:
    access_token: str = field(repr=False)
    list_id: str
    owner_id: str
    request: Callable = field(default=requests.request, repr=False)
    timeout: float = 10
    # X permits 5000 members per list, returned in pages of at most 100.
    # The elapsed-time deadline also bounds reads when the provider is slow.
    max_pages: int = 50
    deadline: float = field(default_factory=lambda: time.monotonic() + 40)
    refresh: Callable | None = field(default=None, repr=False)
    _ready: bool = field(default=False, init=False)
    _refreshed: bool = field(default=False, init=False)

    def _call(self, method, path, **kwargs):
        remaining = self.deadline - time.monotonic()
        if remaining < 1:
            raise XListError("deadline")
        try:
            response = self.request(
                method,
                "https://api.x.com/2" + path,
                headers={"Authorization": "Bearer " + self.access_token},
                timeout=min(self.timeout, remaining),
                allow_redirects=False,
                **kwargs,
            )
        except requests.RequestException as exc:
            raise XListError("transport", unknown=method == "POST") from exc
        if response.status_code == 401 and self.refresh and not self._refreshed:
            self._refreshed = True
            self.access_token = self.refresh()
            return self._call(method, path, **kwargs)
        if response.status_code in {401, 403}:
            raise XListError("owner_auth_denied", auth=True)
        if response.status_code >= 300:
            raise XListError(
                "http_" + str(response.status_code),
                unknown=method == "POST" and response.status_code >= 500,
            )
        try:
            payload = response.json()
            if not isinstance(payload, dict) or payload.get("errors"):
                raise ValueError("invalid payload")
            return payload
        except (ValueError, TypeError) as exc:
            raise XListError("invalid_response", unknown=method == "POST") from exc

    def preflight(self):
        if not self.access_token:
            raise XListError("missing_owner_token", auth=True)
        user = self._call("GET", "/users/me").get("data", {})
        if user.get("id") != self.owner_id:
            raise XListError("owner_mismatch", auth=True)
        target = self._call(
            "GET", "/lists/" + self.list_id, params={"list.fields": "owner_id,private"}
        ).get("data", {})
        if target.get("owner_id") != self.owner_id or target.get("private") is not True:
            raise XListError("owner_mismatch", auth=True)
        self._ready = True

    def members(self):
        if not self._ready:
            raise XListError("preflight_required", auth=True)
        result = set()
        token = None
        seen = set()
        for _ in range(self.max_pages):
            params = {"max_results": 100}
            if token:
                params["pagination_token"] = token
            payload = self._call("GET", f"/lists/{self.list_id}/members", params=params)
            rows = payload.get("data", [])
            if not isinstance(rows, list) or any(
                not isinstance(r, dict) or not str(r.get("id", "")).isdecimal()
                for r in rows
            ):
                raise XListError("invalid_members")
            result.update(str(row["id"]) for row in rows)
            token = payload.get("meta", {}).get("next_token")
            if not token:
                return result, True
            if token in seen:
                return result, False
            seen.add(token)
        return result, False

    def add(self, identifier):
        if not self._ready:
            raise XListError("preflight_required", auth=True)
        if not str(identifier).isdecimal():
            raise ValueError("X native identifier required")
        payload = self._call(
            "POST", f"/lists/{self.list_id}/members", json={"user_id": str(identifier)}
        )
        if payload.get("data", {}).get("is_member") is not True:
            raise XListError("unconfirmed_add", unknown=True)


def _claim(intent_id):
    with transaction.atomic():
        intent = (
            OfficialCompanyListIntent.objects.select_for_update()
            .select_related("state", "account")
            .get(pk=intent_id)
        )
        now = timezone.now()
        if intent.status not in {
            "pending",
            "retry_due",
            "verify_needed",
            "claimed",
        } or (intent.next_attempt_at and intent.next_attempt_at > now):
            return None
        if (
            intent.status == "claimed"
            and intent.claim_expires_at
            and intent.claim_expires_at > now
        ):
            return None
        if (
            intent.state.status != "registered"
            or intent.state.evidence_hash != intent.evidence_hash
        ):
            return None
        if intent.attempts >= 5:
            intent.status = "review_needed"
            intent.last_error = "attempt_limit"
            intent.save()
            return None
        intent.status = "claimed"
        intent.claim_token = uuid.uuid4().hex
        intent.claim_expires_at = now + timedelta(seconds=90)
        intent.attempts += 1
        intent.save()
        return intent


def _complete(claim, status, error=""):
    from monitor.list_membership import _upsert_membership

    with transaction.atomic():
        intent = (
            OfficialCompanyListIntent.objects.select_for_update()
            .select_related("state")
            .get(pk=claim.pk)
        )
        if (
            intent.claim_token != claim.claim_token
            or intent.evidence_hash != claim.evidence_hash
            or intent.state.evidence_hash != claim.evidence_hash
        ):
            return False
        now = timezone.now()
        intent.status = status
        intent.last_error = error
        intent.claim_token = ""
        intent.claim_expires_at = None
        intent.next_attempt_at = (
            now + timedelta(minutes=15)
            if status in {"retry_due", "verify_needed"}
            else None
        )
        if status == "confirmed":
            intent.confirmed_at = now
            _upsert_membership(
                list_id=intent.list_id,
                account=intent.account,
                observed_at=now,
                source="official_owner_api",
                source_run_id=claim.claim_token,
                complete=False,
            )
        intent.save()
        return True


def sync_intents(*, cfg, client, deadline=None):
    result = {"claimed": 0, "confirmed": 0, "writes": 0, "status": "disabled"}
    if not cfg.list_sync_enabled or cfg.max_list_writes == 0:
        return result
    if deadline and time.monotonic() + 2 >= deadline:
        result["status"] = "deferred_deadline"
        return result
    if deadline and hasattr(client, "limit_deadline"):
        client.limit_deadline(deadline)
    # Claims, reads and writes are bounded independently of queue size. An expired
    # claim is always read back before a new POST, including a crash after POST.
    now = timezone.now()
    removed_ids = list(
        OfficialCompanyListIntent.objects.filter(
            status="confirmed",
            list_id=int(cfg.list_id),
            account__twitter_list_memberships__list_id=int(cfg.list_id),
            account__twitter_list_memberships__active=False,
            account__twitter_list_memberships__last_complete_reconciliation_at__gt=F(
                "confirmed_at"
            ),
        ).values_list("pk", flat=True)[:100]
    )
    OfficialCompanyListIntent.objects.filter(
        pk__in=removed_ids, status="confirmed"
    ).update(status="review_needed", last_error="observed_member_removal")
    ids = list(
        OfficialCompanyListIntent.objects.filter(
            list_id=int(cfg.list_id),
            status__in=["pending", "retry_due", "verify_needed", "claimed"],
            state__status="registered",
            state__evidence_hash=F("evidence_hash"),
        )
        .filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
        .filter(
            ~Q(status="claimed")
            | Q(claim_expires_at__isnull=True)
            | Q(claim_expires_at__lte=now)
        )
        .order_by("created_at", "pk")
        .values_list("pk", flat=True)[: cfg.max_list_writes]
    )
    claims = [claim for pk in ids if (claim := _claim(pk)) is not None]
    if not claims:
        result["status"] = "idle"
        return result
    result["claimed"] = len(claims)
    try:
        client.preflight()
        members, complete = client.members()
    except Exception as exc:  # noqa: BLE001 - preserve durable claims without logging credentials
        auth = isinstance(exc, XListError) and exc.auth
        for claim in claims:
            _complete(
                claim,
                "blocked_auth" if auth else "verify_needed",
                str(exc) if isinstance(exc, XListError) else type(exc).__name__,
            )
        result["status"] = "blocked_auth" if auth else "deferred"
        return result
    for claim in claims:
        try:
            identifier = x_account_identifier(claim.account)
            if identifier in members:
                result["confirmed"] += int(_complete(claim, "confirmed"))
                continue
            if not complete or (deadline and time.monotonic() + 10 > deadline):
                _complete(claim, "verify_needed", "incomplete_membership_read")
                continue
            # Recheck after network reads; contradictory evidence or suppression
            # arriving while preflight ran must prevent this outbound write.
            requested = OfficialCompanyListIntent.objects.filter(
                pk=claim.pk,
                claim_token=claim.claim_token,
                state__status="registered",
                state__evidence_hash=claim.evidence_hash,
                evidence_hash=claim.evidence_hash,
            ).update(
                add_requested_at=Coalesce("add_requested_at", Value(timezone.now()))
            )
            if not requested:
                continue
            result["writes"] += 1
            client.add(identifier)
            # A completed provider add is history even when new evidence has
            # superseded this claim during network IO. Completion stays fenced.
            OfficialCompanyListIntent.objects.filter(pk=claim.pk).update(
                add_acknowledged_at=Coalesce(
                    "add_acknowledged_at", Value(timezone.now())
                )
            )
            result["confirmed"] += int(_complete(claim, "confirmed"))
        except Exception as exc:  # noqa: BLE001
            auth = isinstance(exc, XListError) and exc.auth
            terminal = isinstance(exc, XListError) and str(exc) in {
                "http_400",
                "http_404",
            }
            _complete(
                claim,
                "blocked_auth"
                if auth
                else ("review_needed" if terminal else "verify_needed"),
                str(exc) if isinstance(exc, XListError) else type(exc).__name__,
            )
    result["status"] = "complete" if result["confirmed"] == len(claims) else "deferred"
    return result


def build_owner_list_client(cfg):
    from core.official_company_credentials import OwnerTokenStore

    # Lazy credential access: sync claims no work => no secret reads or renewal.
    class StoredClient:
        _client = None
        _deadline = None
        _store = None

        def limit_deadline(self, deadline):
            self._deadline = deadline

        def preflight(self):
            store = OwnerTokenStore.from_env()
            self._store = store
            self._client = XOwnerListClient(
                access_token=store.access_token(),
                list_id=cfg.list_id,
                owner_id=cfg.owner_id,
                refresh=store.refresh,
            )
            if self._deadline is not None:
                self._client.deadline = self._deadline
            try:
                return self._client.preflight()
            except XListError as exc:
                if exc.auth:
                    store.block()
                raise

        def members(self):
            return self._client.members()

        def add(self, identifier):
            try:
                return self._client.add(identifier)
            except XListError as exc:
                if exc.auth:
                    self._store.block()
                raise

    return StoredClient()
