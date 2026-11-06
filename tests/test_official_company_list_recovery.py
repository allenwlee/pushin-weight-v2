"""Exact-target recovery uses real encrypted state and a fake HTTP boundary."""

import hashlib
import json
from contextlib import contextmanager
from copy import copy
from datetime import timedelta
from functools import partial
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from cryptography.fernet import Fernet
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.utils import timezone

from core.models import (
    Account,
    OfficialCompanyAccountState,
    OfficialCompanyListIntent,
    OfficialCompanyOwnerCredential,
    TwitterListMembership,
)
from core.official_company_credentials import OwnerTokenStore
from tests.test_official_company_list_sync import setup_intent

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


@pytest.fixture(autouse=True)
def forbid_real_network(monkeypatch):
    monkeypatch.setattr(
        "requests.sessions.Session.send",
        Mock(side_effect=AssertionError("Recovery tests must never contact a provider")),
    )


def recovery_fixture(monkeypatch):
    intent, cfg = setup_intent()
    intent.status = "blocked_auth"
    intent.last_error = "http_403:spend-cap-reached"
    intent.attempts = 2
    intent.add_requested_at = timezone.now()
    intent.save()
    key = Fernet.generate_key()
    store = OwnerTokenStore(key=key, client_id="client", client_secret="private-secret")
    store.provision(access_token="private-access", refresh_token="private-refresh")
    OfficialCompanyOwnerCredential.objects.update(
        status="blocked", blocked_reason="http_403:spend-cap-reached",
        blocked_origin="provider", blocked_at=timezone.now(),
    )
    monkeypatch.setattr(
        "monitor.management.commands.official_co_account_extraction.load_config",
        lambda path: SimpleNamespace(official_company=cfg),
    )
    return intent, cfg, store


def stored_rows():
    return {
        model.__name__: list(model.objects.order_by("pk").values())
        for model in (OfficialCompanyOwnerCredential, OfficialCompanyListIntent, OfficialCompanyAccountState)
    }


def test_recovery_command_defaults_to_offline_preview_without_touching_tokens(monkeypatch):
    intent, cfg, _ = recovery_fixture(monkeypatch)
    before = stored_rows()
    forbidden = Mock(side_effect=AssertionError("Preview must not load secrets or contact X"))
    monkeypatch.setattr(OwnerTokenStore, "from_env", forbidden)
    monkeypatch.setattr("requests.sessions.Session.send", forbidden)
    output = StringIO()
    call_command(
        "official_co_account_extraction", "recover-list-billing",
        intent_id=intent.pk, list_id=str(cfg.list_id), stdout=output,
    )
    result = json.loads(output.getvalue())
    assert result["status"] == "preview"
    assert result["eligible"] is True
    assert result["provider_request_made"] is False
    assert result["credential"]["blocked_origin"] == "provider"
    assert result["snapshot"]["intent_id"] == intent.pk
    assert result["snapshot"]["intent_error"] == "http_403:spend-cap-reached"
    assert stored_rows() == before
    forbidden.assert_not_called()
    assert "private-" not in output.getvalue()


def preview(intent, cfg, **kwargs):
    from core.official_company_list_recovery import recover_list_billing

    return recover_list_billing(cfg=cfg, intent_id=intent.pk, list_id=str(cfg.list_id), **kwargs)


def apply_recovery(intent, cfg, **kwargs):
    from core.official_company_list_recovery import recover_list_billing

    snapshot = kwargs.pop("expected_snapshot", preview(intent, cfg, **kwargs).get("snapshot"))
    return recover_list_billing(
        cfg=cfg, intent_id=intent.pk, list_id=str(cfg.list_id), apply=True,
        expected_snapshot=snapshot, **kwargs,
    )


def wire_client(monkeypatch, cfg, store, *, member=True, response_hook=None, refresh_hook=None, incomplete=False):
    from core import official_company_lists as lists

    calls = []
    holds = []

    def transport(method, url, **kwargs):
        assert connection.in_atomic_block is False
        calls.append((method, url))
        row = OfficialCompanyOwnerCredential.objects.get()
        assert row.status == "blocked"
        assert row.blocked_origin == "operator"
        assert row.blocked_reason == "recovery_validation_pending"
        holds.append((row.revision, row.blocked_at))
        assert method == "GET", "Recovery must never add a list member"
        response = response_hook(method, url, kwargs) if response_hook else None
        if response is not None:
            return response
        if url.endswith("/users/me"):
            payload = {"data": {"id": str(cfg.owner_id)}}
        elif url.endswith("/members"):
            payload = {"data": [{"id": "987654"}] if member else [], "meta": {}}
            if incomplete:
                payload["meta"]["next_token"] = "repeated-page"
        else:
            payload = {"data": {"owner_id": str(cfg.owner_id), "private": True}}
        return response_with(payload)

    refresh_calls = []

    def refresh_transport(method, url, **kwargs):
        assert connection.in_atomic_block is False
        row = OfficialCompanyOwnerCredential.objects.get()
        assert row.status == "refreshing"
        assert row.blocked_origin == "refresh"
        refresh_calls.append((method, url))
        if refresh_hook:
            return refresh_hook(method, url, kwargs)
        return response_with({
            "access_token": "rotated-access", "refresh_token": "rotated-refresh",
            "expires_in": 7200, "scope": "tweet.read users.read list.read list.write offline.access",
        })

    original_refresh = store.refresh
    monkeypatch.setattr(store, "refresh", lambda: original_refresh(request=refresh_transport))
    monkeypatch.setattr(OwnerTokenStore, "from_env", lambda: store)
    monkeypatch.setattr(lists, "XOwnerListClient", partial(lists.XOwnerListClient, request=transport))
    return calls, refresh_calls, holds


def response_with(payload, status=200):
    result = Mock(status_code=status, headers={})
    result.json.return_value = payload
    return result


@pytest.mark.parametrize("member", [True, False])
def test_apply_uses_get_only_and_preserves_history_and_unrelated_rows(monkeypatch, member):
    intent, cfg, store = recovery_fixture(monkeypatch)
    sibling = OfficialCompanyListIntent.objects.create(
        account=intent.account, state=intent.state, evidence_hash=intent.evidence_hash,
        list_id=123, status="suppressed", attempts=4, last_error="owner_auth_denied",
    )
    before_sibling = OfficialCompanyListIntent.objects.values().get(pk=sibling.pk)
    before_states = list(OfficialCompanyAccountState.objects.values())
    stamps = (intent.add_requested_at, intent.add_acknowledged_at)
    calls, refreshes, _ = wire_client(monkeypatch, cfg, store, member=member)
    result = apply_recovery(intent, cfg)
    assert result["status"] == ("confirmed" if member else "verify_needed")
    assert result["provider_request_made"] is True
    assert len(calls) == 3 and not refreshes
    intent.refresh_from_db()
    assert intent.attempts == 2
    assert intent.claim_token == ""
    assert (intent.add_requested_at, intent.add_acknowledged_at) == stamps
    assert OfficialCompanyListIntent.objects.values().get(pk=sibling.pk) == before_sibling
    assert list(OfficialCompanyAccountState.objects.values()) == before_states
    assert TwitterListMembership.objects.filter(account=intent.account, active=True).exists() is member
    row = OfficialCompanyOwnerCredential.objects.get()
    assert (row.status, row.blocked_reason, row.blocked_origin, row.blocked_at) == ("ready", "", "", None)
    calls.clear()
    repeated = apply_recovery(intent, cfg)
    assert repeated["status"] == "blocked" and not calls


@pytest.mark.parametrize("key,value", [
    ("credential_key", "other"), ("credential_revision", 0), ("credential_status", "ready"),
    ("credential_updated_at", "2000-01-01T00:00:00+00:00"), ("intent_status", "verify_needed"),
    ("intent_error", "owner_auth_denied"), ("evidence_hash", "b" * 64),
    ("account_id", "other"), ("list_id", "1"), ("state_status", "suppressed"),
    ("blocked_reason", "unknown"),
])
def test_snapshot_mismatch_is_readonly_and_never_opens_tokens(monkeypatch, key, value):
    intent, cfg, _ = recovery_fixture(monkeypatch)
    snapshot = preview(intent, cfg)["snapshot"]
    snapshot[key] = value
    before = stored_rows()
    forbidden = Mock(side_effect=AssertionError("Snapshot mismatch must stop offline"))
    monkeypatch.setattr(OwnerTokenStore, "from_env", forbidden)
    result = apply_recovery(intent, cfg, expected_snapshot=snapshot)
    assert result["error"] == "recovery_snapshot_mismatch"
    assert result["provider_request_made"] is False
    assert stored_rows() == before
    forbidden.assert_not_called()


@pytest.mark.parametrize("target,fields,expected", [
    ("intent", {"status": "suppressed"}, "recovery_target_state"),
    ("intent", {"status": "review_needed"}, "recovery_target_state"),
    ("state", {"status": "suppressed"}, "recovery_target_state"),
    ("state", {"status": "review_needed"}, "recovery_target_state"),
    ("state", {"evidence_hash": "b" * 64}, "recovery_target_state"),
    ("intent", {"attempts": 5}, "recovery_attempt_limit"),
    ("intent", {"claim_token": "other-worker"}, "recovery_active_claim"),
    ("intent", {"last_error": "owner_auth_denied"}, "recovery_not_billing"),
    ("credential", {"status": "refreshing", "blocked_reason": "refresh_in_progress", "blocked_origin": "refresh"}, "recovery_credential_state"),
    ("credential", {"blocked_reason": "refresh_transport_uncertain", "blocked_origin": "refresh"}, "recovery_credential_state"),
    ("credential", {"blocked_reason": "credential_decryption", "blocked_origin": "local_configuration"}, "recovery_credential_state"),
    ("credential", {"blocked_reason": "credential_client_mismatch", "blocked_origin": "local_configuration"}, "recovery_credential_state"),
])
def test_ineligible_target_or_credentials_never_change_state(monkeypatch, target, fields, expected):
    intent, cfg, _ = recovery_fixture(monkeypatch)
    model, pk = {
        "intent": (OfficialCompanyListIntent, intent.pk),
        "state": (OfficialCompanyAccountState, intent.state_id),
        "credential": (OfficialCompanyOwnerCredential, OfficialCompanyOwnerCredential.objects.get().pk),
    }[target]
    model.objects.filter(pk=pk).update(**fields)
    before = stored_rows()
    result = apply_recovery(intent, cfg)
    assert result["error"] == expected
    assert result["provider_request_made"] is False
    assert stored_rows() == before


def legacy_receipt(tmp_path, credential):
    receipt = {
        "status": "confirmed", "automated_credential_hold_preserved": True,
        "independently_confirmed": True, "refresh_attempts": 1, "refresh_http_status": 200,
        "credential_revision_before": credential.revision - 1,
        "credential_revision_after": credential.revision,
        "attempted_at": (credential.updated_at - timedelta(seconds=1)).isoformat(),
        "confirmed_at": (credential.updated_at + timedelta(seconds=1)).isoformat(),
    }
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(receipt))
    return {
        "acknowledge_operator_hold": True, "operator_hold_receipt": str(path),
        "operator_hold_receipt_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


@pytest.mark.parametrize("receipt_problem", [None, "no_ack", "wrong_hash", "wrong_revision", "no_read", "wrong_time"])
def test_unknown_hold_requires_exact_rotation_read_receipt(monkeypatch, tmp_path, receipt_problem):
    intent, cfg, store = recovery_fixture(monkeypatch)
    OfficialCompanyOwnerCredential.objects.update(revision=27, blocked_reason="unknown", blocked_origin="legacy_unknown", blocked_at=None)
    row = OfficialCompanyOwnerCredential.objects.get()
    assert preview(intent, cfg)["error"] == "recovery_operator_receipt_required"
    kwargs = legacy_receipt(tmp_path, row)
    path = tmp_path / "receipt.json"
    if receipt_problem == "no_ack":
        kwargs["acknowledge_operator_hold"] = False
    elif receipt_problem == "wrong_hash":
        kwargs["operator_hold_receipt_sha256"] = "0" * 64
    elif receipt_problem:
        value = json.loads(path.read_text())
        key, wrong = {
            "wrong_revision": ("credential_revision_after", 26),
            "no_read": ("independently_confirmed", False),
            "wrong_time": ("attempted_at", (row.updated_at + timedelta(seconds=10)).isoformat()),
        }[receipt_problem]
        value[key] = wrong
        path.write_text(json.dumps(value))
        kwargs["operator_hold_receipt_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    before = stored_rows()
    calls, _, _ = wire_client(monkeypatch, cfg, store)
    result = apply_recovery(intent, cfg, **kwargs)
    if receipt_problem:
        assert result["status"] == "blocked" and not calls
        assert stored_rows() == before
    else:
        assert result["status"] == "confirmed" and len(calls) == 3


@pytest.mark.parametrize("member", [True, False])
def test_incomplete_read_never_promotes_even_if_selected_member_was_seen(monkeypatch, member):
    intent, cfg, store = recovery_fixture(monkeypatch)
    calls, _, _ = wire_client(monkeypatch, cfg, store, member=member, incomplete=True)
    result = apply_recovery(intent, cfg)
    assert result["error"] == "recovery_incomplete_membership"
    row = OfficialCompanyOwnerCredential.objects.get()
    assert row.status == "blocked" and row.blocked_reason == "recovery_validation_pending"
    intent.refresh_from_db()
    assert intent.status == "blocked_auth" and intent.attempts == 2
    assert intent.next_attempt_at > timezone.now()
    assert len(calls) == 4
    assert not TwitterListMembership.objects.exists()


def test_billing_failure_retains_hold_and_resume_requires_fresh_snapshot(monkeypatch):
    intent, cfg, store = recovery_fixture(monkeypatch)
    stale = preview(intent, cfg)["snapshot"]
    calls, _, _ = wire_client(
        monkeypatch, cfg, store,
        response_hook=lambda *args: response_with({"reason": "spend-cap-reached"}, 403),
    )
    result = apply_recovery(intent, cfg, expected_snapshot=stale)
    assert result["error"] == "http_403:spend-cap-reached"
    assert result["blocked_origin"] == "operator"
    assert result["blocked_reason"] == "recovery_validation_pending"
    intent.refresh_from_db()
    assert intent.next_attempt_at > timezone.now() + timedelta(hours=23)
    assert intent.attempts == 2 and intent.claim_token.startswith("recovery:")
    calls.clear()
    assert apply_recovery(intent, cfg, expected_snapshot=stale)["error"] == "recovery_snapshot_mismatch"
    assert not calls
    wire_client(monkeypatch, cfg, store)
    assert apply_recovery(intent, cfg)["status"] == "confirmed"


@pytest.mark.parametrize("failure", ["permission", "owner", "decrypt", "client", "configuration"])
def test_genuine_auth_or_configuration_failure_replaces_hold_with_actual_cause(monkeypatch, failure):
    from core.official_company_lists import XListError

    intent, cfg, store = recovery_fixture(monkeypatch)
    if failure == "decrypt":
        store._cipher = Fernet(Fernet.generate_key())
    if failure == "client":
        store._client_id = "wrong-client"

    def refused(method, url, kwargs):
        if failure == "permission":
            return response_with({"reason": "client-not-enrolled"}, 403)
        if failure == "owner":
            return response_with({"data": {"id": "wrong-owner"}})

    wire_client(monkeypatch, cfg, store, response_hook=refused)
    if failure == "configuration":
        monkeypatch.setattr(OwnerTokenStore, "from_env", Mock(side_effect=XListError("missing_owner_client_configuration", auth=True)))
    result = apply_recovery(intent, cfg)
    expected = {
        "permission": "http_403:client-not-enrolled", "owner": "owner_mismatch",
        "decrypt": "credential_decryption", "client": "credential_client_mismatch",
        "configuration": "missing_owner_client_configuration",
    }[failure]
    assert result["error"] == expected
    assert result["blocked_reason"] == expected
    assert result["blocked_origin"] == ("provider" if failure == "permission" else "local_configuration")
    assert result["provider_request_made"] is (failure in {"permission", "owner"})


def expire_tokens(store):
    row = OfficialCompanyOwnerCredential.objects.get()
    value = store._decode(row)
    value["expires_at"] = 1
    row.encrypted_tokens = store._encode(value)
    row.save(update_fields=["encrypted_tokens", "updated_at"])


@pytest.mark.parametrize("failure_after_refresh", [False, True])
def test_real_expiry_rotation_stays_held_and_never_restores_old_ciphertext(monkeypatch, failure_after_refresh):
    intent, cfg, store = recovery_fixture(monkeypatch)
    expire_tokens(store)
    old_cipher = bytes(OfficialCompanyOwnerCredential.objects.get().encrypted_tokens)
    calls, refreshes, holds = wire_client(
        monkeypatch, cfg, store,
        response_hook=(lambda *args: response_with({"reason": "spend-cap-reached"}, 403)) if failure_after_refresh else None,
    )
    result = apply_recovery(intent, cfg)
    row = OfficialCompanyOwnerCredential.objects.get()
    assert row.revision == 2 and bytes(row.encrypted_tokens) != old_cipher
    assert store._decode(row)["refresh_token"] == "rotated-refresh"
    assert len(refreshes) == 1 and calls
    assert all(revision == 2 for revision, _ in holds)
    assert result["provider_request_made"] is True
    assert row.status == ("blocked" if failure_after_refresh else "ready")
    if failure_after_refresh:
        assert row.blocked_reason == "recovery_validation_pending"


@pytest.mark.parametrize("expired", [False, True])
def test_expiry_and_401_share_one_refresh_limit(monkeypatch, expired):
    intent, cfg, store = recovery_fixture(monkeypatch)
    if expired:
        expire_tokens(store)
    calls, refreshes, _ = wire_client(monkeypatch, cfg, store, response_hook=lambda *args: response_with({}, 401))
    result = apply_recovery(intent, cfg)
    assert len(refreshes) == 1
    assert len(calls) == (1 if expired else 2)
    assert result["error"] == "owner_auth_denied"
    row = OfficialCompanyOwnerCredential.objects.get()
    assert row.revision == 2 and row.blocked_reason == "owner_auth_denied"
    assert store._decode(row)["refresh_token"] == "rotated-refresh"


class ProcessCrash(BaseException):
    pass


@pytest.mark.parametrize("crash_at", ["before_http", "during_refresh", "after_rotation", "before_promotion"])
def test_crashes_keep_durable_hold_or_uncertain_refresh(monkeypatch, crash_at):
    intent, cfg, store = recovery_fixture(monkeypatch)
    if crash_at in {"during_refresh", "after_rotation"}:
        expire_tokens(store)

    def crash(*args, **kwargs):
        raise ProcessCrash

    wire_client(
        monkeypatch, cfg, store,
        refresh_hook=crash if crash_at == "during_refresh" else None,
        response_hook=crash if crash_at == "after_rotation" else None,
    )
    if crash_at == "before_http":
        monkeypatch.setattr(OwnerTokenStore, "from_env", crash)
    if crash_at == "before_promotion":
        monkeypatch.setattr("core.official_company_list_recovery._complete", crash)
    with pytest.raises(ProcessCrash):
        apply_recovery(intent, cfg)
    row = OfficialCompanyOwnerCredential.objects.get()
    intent.refresh_from_db()
    assert intent.status == "blocked_auth" and intent.attempts == 2 and intent.claim_token
    assert row.status == ("refreshing" if crash_at == "during_refresh" else "blocked")
    assert row.blocked_reason == ("refresh_in_progress" if crash_at == "during_refresh" else "recovery_validation_pending")
    assert row.revision == (2 if crash_at == "after_rotation" else 1)
    if crash_at == "during_refresh":
        assert preview(intent, cfg)["eligible"] is False
    assert not TwitterListMembership.objects.exists()


@pytest.mark.parametrize("changed", ["suppression", "evidence", "account"])
def test_concurrent_target_changes_prevent_promotion_and_are_preserved(monkeypatch, changed):
    intent, cfg, store = recovery_fixture(monkeypatch)
    replacement = Account.objects.create(author_id="123456", handle="replacement") if changed == "account" else None

    def change_target(method, url, kwargs):
        if url.endswith("/members"):
            if changed == "suppression":
                OfficialCompanyListIntent.objects.filter(pk=intent.pk).update(status="suppressed")
            elif changed == "evidence":
                OfficialCompanyAccountState.objects.filter(pk=intent.state_id).update(evidence_hash="b" * 64)
            else:
                OfficialCompanyListIntent.objects.filter(pk=intent.pk).update(
                    account=replacement, native_account_id=replacement.author_id,
                )

    wire_client(monkeypatch, cfg, store, response_hook=change_target)
    result = apply_recovery(intent, cfg)
    assert result["error"] == "recovery_target_changed"
    assert OfficialCompanyOwnerCredential.objects.get().status == "blocked"
    intent.refresh_from_db()
    assert intent.last_error == "http_403:spend-cap-reached"
    if changed == "suppression":
        assert intent.status == "suppressed"
    assert not TwitterListMembership.objects.exists()


def test_absence_keeps_longer_list_cooldown_and_scheduler_confirms_without_add(monkeypatch):
    from core.official_company_lists import sync_intents

    intent, cfg, store = recovery_fixture(monkeypatch)
    until = timezone.now() + timedelta(days=2)
    intent.next_attempt_at = until
    intent.save(update_fields=["next_attempt_at", "updated_at"])
    wire_client(monkeypatch, cfg, store, member=False)
    assert apply_recovery(intent, cfg)["status"] == "verify_needed"
    intent.refresh_from_db()
    assert intent.next_attempt_at == until
    client = Mock()
    client.members.return_value = ({intent.native_account_id}, True)
    intent.next_attempt_at = timezone.now() - timedelta(seconds=1)
    intent.save(update_fields=["next_attempt_at", "updated_at"])
    assert sync_intents(cfg=cfg, client=client)["confirmed"] == 1
    client.add.assert_not_called()
    intent.refresh_from_db()
    assert intent.status == "confirmed"


def test_cli_apply_uses_only_dedicated_lock_and_requires_saved_snapshot(monkeypatch, tmp_path):
    intent, cfg, store = recovery_fixture(monkeypatch)
    wire_client(monkeypatch, cfg, store)
    broad = Mock(side_effect=AssertionError("Recovery must not take essential harvest lock"))
    monkeypatch.setattr("monitor.management.commands.official_co_account_extraction.harvest_writer_lock", broad)
    scopes = []

    @contextmanager
    def lock(**kwargs):
        scopes.append(kwargs["lock_scope"])
        yield SimpleNamespace(acquired=True)

    monkeypatch.setattr("core.official_company_lock.harvest_writer_lock", lock)
    with pytest.raises(CommandError, match="recovery_snapshot_required"):
        call_command("official_co_account_extraction", "recover-list-billing", intent_id=intent.pk, list_id=str(cfg.list_id), apply=True)
    snapshot_path = tmp_path / "preview.json"
    snapshot_path.write_text(json.dumps(preview(intent, cfg)))
    output = StringIO()
    call_command(
        "official_co_account_extraction", "recover-list-billing", intent_id=intent.pk,
        list_id=str(cfg.list_id), apply=True, expected_snapshot=str(snapshot_path), stdout=output,
    )
    assert json.loads(output.getvalue())["status"] == "confirmed"
    assert scopes == ["official-company"]
    broad.assert_not_called()


def test_ready_credential_with_saved_billing_queue_reports_queue_gate(monkeypatch):
    from core.official_company_lists import sync_intents

    intent, cfg, store = recovery_fixture(monkeypatch)
    store.provision(access_token="newer-access", refresh_token="newer-refresh", replace=True)
    client = Mock()
    result = sync_intents(cfg=cfg, client=client)
    assert result["status"] == "blocked_auth"
    assert result["error_origin"] == "local_queue_gate"
    assert result["credential_status"] == "ready"
    assert result["error"] == "http_403:spend-cap-reached"
    assert result["blocked_reason"] == "" and result["provider_request_made"] is False
    assert preview(intent, cfg)["error_origin"] == "local_queue_gate"
    wire_client(monkeypatch, cfg, store)
    assert apply_recovery(intent, cfg)["status"] == "confirmed"


@pytest.mark.parametrize("refused", [True, False])
def test_concurrent_replacement_preserves_new_pair_and_reports_attempted_revision(monkeypatch, refused):
    intent, cfg, store = recovery_fixture(monkeypatch)

    def replace_during_read(method, url, kwargs):
        if url.endswith("/members"):
            # Simulate another authorized credential replacement after this GET began.
            replacement = copy(store)
            replacement.provision(access_token="replacement-access", refresh_token="replacement-refresh", replace=True)
            if refused:
                return response_with({"reason": "client-not-enrolled"}, 403)

    wire_client(monkeypatch, cfg, store, response_hook=replace_during_read)
    result = apply_recovery(intent, cfg)
    assert result["status"] == "blocked"
    assert result["credential_revision"] == 1
    assert result["credential"]["credential_revision"] == 2
    assert result["credential"]["credential_status"] == "ready"
    assert result["provider_request_made"] is True
    row = OfficialCompanyOwnerCredential.objects.get()
    assert row.status == "ready" and row.revision == 2 and row.blocked_reason == ""
    assert store._decode(row)["refresh_token"] == "replacement-refresh"
    intent.refresh_from_db()
    assert intent.status == "blocked_auth" and intent.attempts == 2
    assert not TwitterListMembership.objects.exists()


@pytest.mark.parametrize("failure", ["timeout", "rejected", "bad_response"])
def test_uncertain_or_rejected_refresh_is_never_retried_by_recovery(monkeypatch, failure):
    intent, cfg, store = recovery_fixture(monkeypatch)
    expire_tokens(store)

    def fail_refresh(method, url, kwargs):
        if failure == "timeout":
            raise TimeoutError("private-refresh must not be exposed")
        return response_with({}, 401 if failure == "rejected" else 200)

    calls, refreshes, _ = wire_client(monkeypatch, cfg, store, refresh_hook=fail_refresh)
    result = apply_recovery(intent, cfg)
    assert not calls and len(refreshes) == 1
    assert result["blocked_origin"] == "refresh"
    assert result["blocked_reason"] == {
        "timeout": "refresh_transport_uncertain", "rejected": "refresh_http_401",
        "bad_response": "refresh_response_uncertain",
    }[failure]
    assert result["provider_request_made"] is True
    before = stored_rows()
    assert apply_recovery(intent, cfg)["eligible"] is False
    assert stored_rows() == before and len(refreshes) == 1
    assert "private-" not in json.dumps(result)


def test_recovery_hold_cannot_be_borrowed_by_another_intent(monkeypatch):
    intent, cfg, store = recovery_fixture(monkeypatch)
    wire_client(monkeypatch, cfg, store, incomplete=True)
    apply_recovery(intent, cfg)
    other_account = Account.objects.create(author_id="123456", handle="other_lab")
    other_state = OfficialCompanyAccountState.objects.create(
        account=other_account, status="registered", evidence_hash="c" * 64,
    )
    other = OfficialCompanyListIntent.objects.create(
        account=other_account, state=other_state, evidence_hash=other_state.evidence_hash,
        list_id=intent.list_id, status="blocked_auth", last_error="http_403:spend-cap-reached",
    )
    before = stored_rows()
    forbidden = Mock(side_effect=AssertionError("Only the selected target can resume its hold"))
    monkeypatch.setattr(OwnerTokenStore, "from_env", forbidden)
    assert apply_recovery(other, cfg)["error"] == "recovery_active_claim"
    assert stored_rows() == before
    forbidden.assert_not_called()


def test_resumed_hold_preserves_longer_target_cooldown_after_nonbilling_error(monkeypatch):
    intent, cfg, store = recovery_fixture(monkeypatch)
    until = timezone.now() + timedelta(days=2)
    intent.next_attempt_at = until
    intent.save(update_fields=["next_attempt_at", "updated_at"])
    wire_client(monkeypatch, cfg, store, incomplete=True)
    assert apply_recovery(intent, cfg)["error"] == "recovery_incomplete_membership"
    intent.refresh_from_db()
    assert intent.last_error == "recovery_incomplete_membership" and intent.next_attempt_at == until
    wire_client(monkeypatch, cfg, store, member=False)
    assert apply_recovery(intent, cfg)["status"] == "verify_needed"
    intent.refresh_from_db()
    assert intent.next_attempt_at == until


def test_other_intent_longer_list_cooldown_survives_selected_recovery(monkeypatch):
    intent, cfg, store = recovery_fixture(monkeypatch)
    other_account = Account.objects.create(author_id="123456", handle="other_lab")
    other_state = OfficialCompanyAccountState.objects.create(
        account=other_account, status="registered", evidence_hash="c" * 64,
    )
    until = timezone.now() + timedelta(days=2)
    other = OfficialCompanyListIntent.objects.create(
        account=other_account, state=other_state, evidence_hash=other_state.evidence_hash,
        list_id=intent.list_id, status="verify_needed", last_error="http_429", next_attempt_at=until,
    )
    before = OfficialCompanyListIntent.objects.values().get(pk=other.pk)
    wire_client(monkeypatch, cfg, store, member=False)
    assert apply_recovery(intent, cfg)["status"] == "verify_needed"
    intent.refresh_from_db()
    assert intent.next_attempt_at == until
    assert OfficialCompanyListIntent.objects.values().get(pk=other.pk) == before


@pytest.mark.parametrize("contents", ["{broken", "[]", "x" * 65537])
def test_cli_invalid_snapshot_is_offline_and_does_not_echo_input(monkeypatch, tmp_path, contents):
    intent, cfg, _ = recovery_fixture(monkeypatch)
    path = tmp_path / "invalid.json"
    path.write_text(contents)
    before = stored_rows()
    forbidden = Mock(side_effect=AssertionError("Invalid input must stop offline"))
    monkeypatch.setattr(OwnerTokenStore, "from_env", forbidden)
    with pytest.raises(CommandError, match="recovery_snapshot_invalid") as error:
        call_command(
            "official_co_account_extraction", "recover-list-billing", intent_id=intent.pk,
            list_id=str(cfg.list_id), apply=True, expected_snapshot=str(path),
        )
    assert contents not in str(error.value)
    assert stored_rows() == before
    forbidden.assert_not_called()


def test_cli_refresh_reports_saved_cause_in_shared_safe_diagnostics(monkeypatch):
    _, _, store = recovery_fixture(monkeypatch)
    monkeypatch.setattr(OwnerTokenStore, "from_env", lambda: store)
    with pytest.raises(CommandError) as error:
        call_command("official_co_account_extraction", "refresh-owner")
    result = json.loads(str(error.value))
    assert result["error"] == "credential_blocked"
    assert result["blocked_reason"] == "http_403:spend-cap-reached"
    assert result["error_origin"] == "local_credential_gate"
    assert result["provider_request_made"] is False
    assert result["credential_status"] == "blocked"
    assert "private-" not in str(error.value)


def test_cli_refresh_preserves_attempted_revision_when_pair_is_concurrently_replaced(monkeypatch):
    _, _, store = recovery_fixture(monkeypatch)
    OfficialCompanyOwnerCredential.objects.update(
        status="ready", blocked_reason="", blocked_origin="", blocked_at=None,
    )
    requests = []

    def refresh_transport(method, url, **kwargs):
        requests.append((method, url))
        assert OfficialCompanyOwnerCredential.objects.get().status == "refreshing"
        replacement = copy(store)
        replacement.provision(access_token="replacement-access", refresh_token="replacement-refresh", replace=True)
        return response_with({}, 400)

    original = store.refresh
    monkeypatch.setattr(store, "refresh", lambda: original(request=refresh_transport))
    monkeypatch.setattr(OwnerTokenStore, "from_env", lambda: store)
    with pytest.raises(CommandError) as error:
        call_command("official_co_account_extraction", "refresh-owner")
    result = json.loads(str(error.value))
    assert result["credential_revision"] == 1
    assert result["credential"]["credential_revision"] == 2
    assert result["credential"]["credential_status"] == "ready"
    assert result["error"] == "refresh_failed"
    assert result["provider_request_made"] is True
    assert len(requests) == 1
    row = OfficialCompanyOwnerCredential.objects.get()
    assert row.status == "ready" and row.revision == 2
    assert store._decode(row)["refresh_token"] == "replacement-refresh"
    assert "replacement-" not in str(error.value)
