"""Bounded, owner-authorized X list writes, separate from observed membership."""

from __future__ import annotations

import re
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

_BILLING_ERROR = "http_403:spend-cap-reached"


# Only machine codes produced by this adapter can enter logs or saved stops.
_LOCAL_ERROR_CODES = frozenset({
    "unknown", "unexpected_error", "deadline", "transport", "owner_auth_denied",
    "invalid_response", "missing_owner_token", "owner_mismatch", "preflight_required",
    "invalid_members", "unconfirmed_add", "missing_owner_client_configuration",
    "invalid_credential_key", "credential_decryption", "credential_client_mismatch",
    "missing_owner_tokens", "credential_already_provisioned", "owner_credential_not_provisioned",
    "credential_blocked", "credential_revision_changed", "refresh_failed",
    "refresh_in_progress", "refresh_transport_uncertain", "refresh_response_uncertain",
    "refresh_save_uncertain", "recovery_validation_pending",
})
LIST_DIAGNOSTIC_FIELDS = (
    "error", "error_origin", "error_observed_at", "provider_request_made",
    "blocked_reason", "blocked_origin", "blocked_at", "credential_revision",
    "retry_at", "queue_recorded_at",
)


def safe_error_code(value):
    if isinstance(value, str) and (
        value in _LOCAL_ERROR_CODES
        or re.fullmatch(r"(?:refresh_)?http_[1-5][0-9]{2}", value)
        or re.fullmatch(r"http_403:[a-z][a-z0-9_-]{0,47}", value)
    ):
        return value
    return "unknown"


class XListError(RuntimeError):
    def __init__(
        self, code, *, auth=False, unknown=False, retry_at=None,
        write_refused=False, billing=False, error_origin="local_configuration",
        provider_request_made=False, credential_revision=None,
    ):
        super().__init__(safe_error_code(code))
        self.auth = auth
        self.unknown = unknown
        self.retry_at = retry_at
        self.write_refused = write_refused
        self.billing = billing
        self.error_origin = error_origin
        self.provider_request_made = provider_request_made
        self.credential_revision = credential_revision
        self.blocked_reason = None
        self.blocked_origin = None
        self.blocked_at = None
        self.error_observed_at = timezone.now() if error_origin == "provider" else None

    def diagnostics(self):
        result = {
            "error": str(self), "error_origin": self.error_origin,
            "provider_request_made": self.provider_request_made,
        }
        for key in ("credential_revision", "blocked_reason", "blocked_origin"):
            value = getattr(self, key)
            if value is not None:
                result[key] = value
        if self.blocked_reason is not None:
            result["blocked_at"] = self.blocked_at.isoformat() if self.blocked_at else None
        for key in ("retry_at", "error_observed_at"):
            value = getattr(self, key)
            if value is not None:
                result[key] = value.isoformat()
        return result

    def with_credential(self, row):
        from core.official_company_credentials import credential_diagnostics

        values = credential_diagnostics(row)
        self.credential_revision = values["credential_revision"]
        self.blocked_reason = values["blocked_reason"]
        self.blocked_origin = values["blocked_origin"]
        self.blocked_at = row.blocked_at if values["blocked_at"] else None
        return self


def _forbidden_reason(response, access_token, *, redactions=()):
    """Keep a machine-readable reason, never a raw body, detail or echoed token."""
    try:
        payload = response.json()
    except (ValueError, TypeError):
        return "unspecified"
    if not isinstance(payload, dict):
        return "unspecified"
    candidates = []
    problem_type = payload.get("type")
    if isinstance(problem_type, str):
        for prefix in ("https://api.x.com/2/problems/", "https://api.twitter.com/2/problems/"):
            if problem_type.startswith(prefix):
                candidates.append(problem_type.removeprefix(prefix))
    candidates.append(payload.get("reason"))
    for candidate in candidates:
        if (
            isinstance(candidate, str)
            and re.fullmatch(r"[a-z][a-z0-9_-]{0,47}", candidate)
            and not any(secret and secret in candidate for secret in (access_token, *redactions))
        ):
            return candidate
    errors = payload.get("errors")
    if isinstance(errors, list) and errors and isinstance(errors[0], dict):
        code = errors[0].get("code")
        if type(code) is int and 0 <= code <= 99999:
            return f"code-{code}"
    return "unspecified"


def _rate_limit_retry_at(response):
    now = timezone.now()
    headers = getattr(response, "headers", {})
    seconds = []
    for key in ("x-rate-limit-reset", "retry-after"):
        value = headers.get(key)
        if isinstance(value, str) and value.isdecimal():
            delay = int(value) - now.timestamp() if key.endswith("reset") else int(value)
            seconds.append(delay)
    # Bound provider values; missing headers retain the existing 15-minute delay.
    return now + timedelta(seconds=min(86400, max(30, max(seconds, default=900))))


@dataclass
class XOwnerListClient:
    access_token: str = field(repr=False)
    list_id: str
    owner_id: str
    request: Callable = field(default=requests.request, repr=False)
    redactions: set[str] = field(default_factory=set, repr=False)
    timeout: float = 10
    # X permits 5000 members per list, returned in pages of at most 100.
    # The elapsed-time deadline also bounds reads when the provider is slow.
    max_pages: int = 50
    deadline: float = field(default_factory=lambda: time.monotonic() + 40)
    refresh: Callable | None = field(default=None, repr=False)
    _ready: bool = field(default=False, init=False)
    _refreshed: bool = field(default=False, init=False)
    provider_request_made: bool = field(default=False, init=False)

    def begin_invocation(self):
        self.provider_request_made = False

    def _error(self, code, *, error_origin="provider", **kwargs):
        return XListError(
            code, error_origin=error_origin,
            provider_request_made=self.provider_request_made, **kwargs,
        )

    def _call(self, method, path, **kwargs):
        remaining = self.deadline - time.monotonic()
        if remaining < 1:
            raise self._error("deadline", error_origin="local_configuration")
        try:
            self.provider_request_made = True
            response = self.request(
                method,
                "https://api.x.com/2" + path,
                headers={"Authorization": "Bearer " + self.access_token},
                timeout=min(self.timeout, remaining),
                allow_redirects=False,
                **kwargs,
            )
        except requests.RequestException as exc:
            raise self._error("transport", unknown=method == "POST") from exc
        if response.status_code == 401 and self.refresh and not self._refreshed:
            self._refreshed = True
            self.access_token = self.refresh()
            return self._call(method, path, **kwargs)
        if response.status_code == 401:
            raise self._error("owner_auth_denied", auth=True)
        if response.status_code == 403:
            refused = method == "POST" and path == f"/lists/{self.list_id}/members"
            code = "http_403:" + _forbidden_reason(response, self.access_token, redactions=self.redactions)
            billing = code == _BILLING_ERROR
            raise self._error(
                code,
                auth=not (refused or billing),
                write_refused=refused,
                billing=billing,
            )
        if response.status_code == 429:
            raise self._error("http_429", retry_at=_rate_limit_retry_at(response))
        if response.status_code >= 300:
            raise self._error(
                "http_" + str(response.status_code),
                unknown=method == "POST" and response.status_code >= 500,
            )
        try:
            payload = response.json()
            if not isinstance(payload, dict) or payload.get("errors"):
                raise ValueError("invalid payload")
            return payload
        except (ValueError, TypeError) as exc:
            raise self._error("invalid_response", unknown=method == "POST") from exc

    def preflight(self):
        if not self.access_token:
            raise self._error("missing_owner_token", auth=True, error_origin="local_configuration")
        user = self._call("GET", "/users/me").get("data", {})
        if user.get("id") != self.owner_id:
            raise self._error("owner_mismatch", auth=True, error_origin="local_configuration")
        target = self._call(
            "GET", "/lists/" + self.list_id, params={"list.fields": "owner_id,private"}
        ).get("data", {})
        if target.get("owner_id") != self.owner_id or target.get("private") is not True:
            raise self._error("owner_mismatch", auth=True, error_origin="local_configuration")
        self._ready = True

    def members(self):
        if not self._ready:
            raise self._error("preflight_required", auth=True, error_origin="local_configuration")
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
                raise self._error("invalid_members")
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
            raise self._error("preflight_required", auth=True, error_origin="local_configuration")
        if not str(identifier).isdecimal():
            raise ValueError("X native identifier required")
        payload = self._call(
            "POST", f"/lists/{self.list_id}/members", json={"user_id": str(identifier)}
        )
        if payload.get("data", {}).get("is_member") is not True:
            raise self._error("unconfirmed_add", unknown=True)


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


def _complete(claim, status, error="", *, retry_at=None, consume_attempt=True):
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
        intent.next_attempt_at = retry_at or (
            now + timedelta(minutes=15)
            if status in {"retry_due", "verify_needed"}
            else None
        )
        if error == "http_429" or not consume_attempt:
            # A provider cooldown is not an account-specific delivery failure.
            intent.attempts = max(0, intent.attempts - 1)
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
    # Scope the request fact to this invocation, including a reused client.
    begin = getattr(type(client), "begin_invocation", None)
    if begin is not None:
        begin(client)
    result = _sync_intents(cfg=cfg, client=client, deadline=deadline)
    result["provider_request_made"] = (
        result.get("provider_request_made") is True
        or getattr(client, "provider_request_made", False) is True
    )
    return result


def _error_diagnostics(exc):
    return (exc if isinstance(exc, XListError) else XListError("unexpected_error")).diagnostics()


def _sync_intents(*, cfg, client, deadline=None):
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
    pause = (
        OfficialCompanyListIntent.objects.filter(
            list_id=int(cfg.list_id),
            status__in=["retry_due", "verify_needed", "review_needed"],
            next_attempt_at__gt=now,
        )
        .filter(Q(last_error="http_429") | Q(last_error__startswith="http_403:"))
        .order_by("-next_attempt_at")
        .values("next_attempt_at", "last_error", "updated_at")
        .first()
    )
    if pause:
        result.update(
            status=(
                "deferred_rate_limit" if pause["last_error"] == "http_429" else
                "deferred_billing" if pause["last_error"] == _BILLING_ERROR else
                "deferred_write_refused"
            ),
            retry_at=pause["next_attempt_at"].isoformat(),
            error=safe_error_code(pause["last_error"]), error_origin="local_cooldown",
            queue_recorded_at=pause["updated_at"].isoformat(),
        )
        return result
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
        blocked = (
            OfficialCompanyListIntent.objects.filter(
                list_id=int(cfg.list_id), status="blocked_auth"
            )
            .order_by("updated_at", "pk")
            .values("last_error", "updated_at")
            .first()
        )
        if blocked:
            from core.official_company_credentials import credential_diagnostics

            result.update(
                status="blocked_auth", error=safe_error_code(blocked["last_error"]),
                error_origin="local_credential_gate", queue_recorded_at=blocked["updated_at"].isoformat(),
                **credential_diagnostics(),
            )
        else:
            result["status"] = "idle"
        return result
    result["claimed"] = len(claims)
    try:
        client.preflight()
        members, complete = client.members()
    except Exception as exc:  # noqa: BLE001 - preserve durable claims without logging credentials
        auth = isinstance(exc, XListError) and exc.auth
        billing = isinstance(exc, XListError) and exc.billing
        retry_at = (
            timezone.now() + timedelta(hours=24) if billing else
            exc.retry_at if isinstance(exc, XListError) else None
        )
        for claim in claims:
            _complete(
                claim,
                "blocked_auth" if auth else "verify_needed",
                str(exc) if isinstance(exc, XListError) else type(exc).__name__,
                retry_at=retry_at,
                consume_attempt=not billing,
            )
        result["status"] = (
            "blocked_auth" if auth else
            "deferred_billing" if billing else
            "deferred_rate_limit" if isinstance(exc, XListError) and str(exc) == "http_429"
            else "deferred"
        )
        result.update(_error_diagnostics(exc))
        if retry_at:
            result["retry_at"] = retry_at.isoformat()
        return result
    for position, claim in enumerate(claims):
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
            result.update(_error_diagnostics(exc))
            if isinstance(exc, XListError) and exc.write_refused:
                retry_at = timezone.now() + timedelta(hours=min(24, 2 ** claim.attempts))
                _complete(
                    claim,
                    "review_needed" if claim.attempts >= 5 else "verify_needed",
                    str(exc), retry_at=retry_at,
                )
                for paused in claims[position + 1:]:
                    _complete(
                        paused, "verify_needed", str(exc), retry_at=retry_at,
                        consume_attempt=False,
                    )
                result.update(
                    status="deferred_billing" if exc.billing else "deferred_write_refused",
                    error=str(exc),
                    retry_at=retry_at.isoformat(),
                )
                return result
            if isinstance(exc, XListError) and str(exc) == "http_429":
                retry_at = exc.retry_at or timezone.now() + timedelta(minutes=15)
                for paused in claims[position:]:
                    _complete(paused, "verify_needed", "http_429", retry_at=retry_at)
                result.update(status="deferred_rate_limit", retry_at=retry_at.isoformat())
                return result
            auth = isinstance(exc, XListError) and exc.auth
            if auth:
                for paused in claims[position:]:
                    _complete(
                        paused, "blocked_auth", str(exc),
                        consume_attempt=paused.pk == claim.pk,
                    )
                result.update(status="blocked_auth", error=str(exc))
                return result
            terminal = isinstance(exc, XListError) and str(exc) in {
                "http_400",
                "http_404",
            }
            _complete(
                claim,
                "review_needed" if terminal else "verify_needed",
                str(exc) if isinstance(exc, XListError) else type(exc).__name__,
            )
    result["status"] = "complete" if result["confirmed"] == len(claims) else "deferred"
    return result


def build_owner_list_client(cfg):
    from core.official_company_credentials import OwnerTokenStore

    # Lazy credential access: a saved queue stop never reads tokens or renews.
    class StoredClient:
        _client = None
        _deadline = None
        _store = None

        def begin_invocation(self):
            self._client = None
            self._store = None

        @property
        def provider_request_made(self):
            return bool(
                (self._client and self._client.provider_request_made)
                or (self._store and self._store.provider_request_made)
            )

        def limit_deadline(self, deadline):
            self._deadline = deadline

        def _invoke(self, method, *args):
            try:
                return method(*args)
            except XListError as exc:
                if self._store is not None:
                    if exc.auth and self._client is not None and exc.error_origin != "local_credential_gate":
                        self._store.block(reason=str(exc), origin=(
                            "provider" if exc.error_origin == "provider" else "local_configuration"
                        ))
                    self._store.annotate_error(exc)
                exc.provider_request_made |= self.provider_request_made
                raise

        def _preflight(self):
            self._store = OwnerTokenStore.from_env()
            self._store.begin_invocation()
            self._client = XOwnerListClient(
                access_token=self._store.access_token(),
                list_id=cfg.list_id,
                owner_id=cfg.owner_id,
                refresh=self._store.refresh,
                redactions=self._store.redactions,
            )
            if self._deadline is not None:
                self._client.deadline = self._deadline
            return self._client.preflight()

        def preflight(self):
            return self._invoke(self._preflight)

        def members(self):
            return self._invoke(self._client.members)

        def add(self, identifier):
            return self._invoke(self._client.add, identifier)

    return StoredClient()
