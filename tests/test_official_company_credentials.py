from unittest.mock import Mock

import pytest
from cryptography.fernet import Fernet

from core.models import OfficialCompanyOwnerCredential
from core.official_company_credentials import OwnerTokenStore
from core.official_company_lists import XListError

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


def test_rotation_saves_both_tokens_encrypted_and_next_process_reads_them():
    key = Fernet.generate_key()
    store = OwnerTokenStore(key=key, client_id="client", client_secret="client-secret")
    store.provision(access_token="old-access", refresh_token="old-refresh")
    from django.utils import timezone

    # Old writers could leave stale provenance on a ready row during rollout.
    OfficialCompanyOwnerCredential.objects.update(
        blocked_reason="owner_auth_denied", blocked_origin="provider", blocked_at=timezone.now(),
    )
    response = Mock(status_code=200)
    response.json.return_value = {
        "access_token": "new-access",
        "refresh_token": "new-refresh",
        "expires_in": 7200,
        "scope": "tweet.read users.read list.read list.write offline.access",
    }
    request = Mock(return_value=response)
    assert store.refresh(request=request) == "new-access"
    row = OfficialCompanyOwnerCredential.objects.get()
    assert (row.blocked_reason, row.blocked_origin, row.blocked_at) == ("", "", None)
    assert b"new-access" not in bytes(row.encrypted_tokens)
    assert b"new-refresh" not in bytes(row.encrypted_tokens)
    fresh = OwnerTokenStore(key=key, client_id="client", client_secret="client-secret")
    assert fresh.load()["refresh_token"] == "new-refresh"
    assert fresh.load()["expires_at"] > 0


def test_failed_or_ambiguous_refresh_blocks_repeated_refresh_attempts():
    store = OwnerTokenStore(
        key=Fernet.generate_key(), client_id="client", client_secret="secret"
    )
    store.provision(access_token="old-access", refresh_token="old-refresh")
    request = Mock(side_effect=TimeoutError())
    with pytest.raises(XListError, match="refresh_failed"):
        store.refresh(request=request)
    with pytest.raises(XListError, match="credential_blocked"):
        store.refresh(request=request)
    assert request.call_count == 1


def test_wrong_key_or_client_cannot_read_and_refresh_other_app_tokens():
    key = Fernet.generate_key()
    store = OwnerTokenStore(key=key, client_id="client", client_secret="secret")
    store.provision(access_token="access", refresh_token="refresh")
    with pytest.raises(XListError, match="credential_decryption"):
        OwnerTokenStore(
            key=Fernet.generate_key(), client_id="client", client_secret="secret"
        ).load()
    with pytest.raises(XListError, match="credential_client_mismatch"):
        OwnerTokenStore(key=key, client_id="different", client_secret="secret").load()


def test_saved_credential_stop_reports_unknown_legacy_cause_without_network():
    from core.official_company_credentials import CREDENTIAL_KEY

    store = OwnerTokenStore(key=Fernet.generate_key(), client_id="client", client_secret="secret")
    store.provision(access_token="private-access", refresh_token="private-refresh")
    OfficialCompanyOwnerCredential.objects.filter(pk=CREDENTIAL_KEY).update(status="blocked")
    row = OfficialCompanyOwnerCredential.objects.get()
    saved = (bytes(row.encrypted_tokens), row.revision, row.updated_at)
    with pytest.raises(XListError) as error:
        store.load()
    assert error.value.diagnostics() == {
        "error": "credential_blocked", "error_origin": "local_credential_gate",
        "blocked_reason": "unknown", "blocked_origin": "legacy_unknown", "blocked_at": None,
        "credential_revision": row.revision, "provider_request_made": False,
    }
    row.refresh_from_db()
    assert (bytes(row.encrypted_tokens), row.revision, row.updated_at) == saved


def test_block_preserves_first_cause_and_replacement_clears_it_with_revision_fence():
    key = Fernet.generate_key()
    old = OwnerTokenStore(key=key, client_id="client", client_secret="secret")
    old.provision(access_token="old-access", refresh_token="old-refresh")
    old.load()
    assert old.block(reason="owner_auth_denied", origin="provider")
    row = OfficialCompanyOwnerCredential.objects.get()
    stopped = (row.blocked_reason, row.blocked_origin, row.blocked_at, row.updated_at)
    assert not old.block(reason="owner_mismatch", origin="local_configuration")
    with pytest.raises(XListError) as error:
        old.load()
    row.refresh_from_db()
    assert (row.blocked_reason, row.blocked_origin, row.blocked_at, row.updated_at) == stopped
    assert error.value.diagnostics()["blocked_reason"] == "owner_auth_denied"
    replacement = OwnerTokenStore(key=key, client_id="client", client_secret="secret")
    replacement.provision(access_token="new-access", refresh_token="new-refresh", replace=True)
    assert not old.block(reason="owner_auth_denied", origin="provider")
    row.refresh_from_db()
    assert row.status == "ready" and row.revision == 2
    assert (row.blocked_reason, row.blocked_origin, row.blocked_at) == ("", "", None)
    assert replacement.load()["refresh_token"] == "new-refresh"


@pytest.mark.parametrize("failure, reason", [
    ("rejected", "refresh_http_401"),
    ("transport", "refresh_transport_uncertain"),
    ("payload", "refresh_response_uncertain"),
])
def test_refresh_failure_retains_safe_cause_on_a_new_process(failure, reason):
    key = Fernet.generate_key()
    store = OwnerTokenStore(key=key, client_id="client", client_secret="private-secret")
    store.provision(access_token="private-access", refresh_token="private-refresh")
    before = OfficialCompanyOwnerCredential.objects.get()
    response = Mock(status_code=401 if failure == "rejected" else 200)
    response.json.return_value = {"detail": "private-access private-refresh private-secret"}
    request = Mock(return_value=response)
    if failure == "transport":
        request.side_effect = TimeoutError("private-access private-refresh private-secret")
    with pytest.raises(XListError) as first:
        store.refresh(request=request)
    row = OfficialCompanyOwnerCredential.objects.get()
    assert row.status == "blocked" and row.blocked_reason == reason and row.blocked_origin == "refresh"
    assert row.blocked_at is not None
    assert (bytes(row.encrypted_tokens), row.revision) == (bytes(before.encrypted_tokens), before.revision)
    assert first.value.diagnostics()["provider_request_made"] is True
    fresh = OwnerTokenStore(key=key, client_id="client", client_secret="private-secret")
    with pytest.raises(XListError) as later:
        fresh.refresh(request=request)
    facts = later.value.diagnostics()
    assert facts["error_origin"] == "local_credential_gate" and facts["provider_request_made"] is False
    assert facts["blocked_reason"] == reason and facts["blocked_at"] == row.blocked_at.isoformat()
    assert request.call_count == 1
    assert all(secret not in str(first.value.diagnostics()) + str(facts)
               for secret in ("private-access", "private-refresh", "private-secret"))


def test_crash_during_refresh_keeps_inflight_cause_and_never_reuses_refresh_token():
    class ProcessCrash(BaseException):
        pass

    key = Fernet.generate_key()
    store = OwnerTokenStore(key=key, client_id="client", client_secret="secret")
    store.provision(access_token="access", refresh_token="refresh")
    request = Mock(side_effect=ProcessCrash())
    with pytest.raises(ProcessCrash):
        store.refresh(request=request)
    row = OfficialCompanyOwnerCredential.objects.get()
    assert row.status == "refreshing" and row.blocked_reason == "refresh_in_progress"
    assert row.blocked_origin == "refresh" and row.blocked_at is not None
    fresh = OwnerTokenStore(key=key, client_id="client", client_secret="secret")
    with pytest.raises(XListError) as error:
        fresh.refresh(request=request)
    assert error.value.diagnostics()["blocked_reason"] == "refresh_in_progress"
    assert request.call_count == 1


def test_stop_writer_rejects_unbounded_or_uncontrolled_provenance():
    store = OwnerTokenStore(key=Fernet.generate_key(), client_id="client", client_secret="secret")
    store.provision(access_token="access", refresh_token="refresh")
    for reason, origin in (("x" * 129, "provider"), ("owner_auth_denied", "arbitrary")):
        with pytest.raises(ValueError, match="Invalid credential stop"):
            store.block(reason=reason, origin=origin)
    assert OfficialCompanyOwnerCredential.objects.get().status == "ready"
    from django.db import IntegrityError, transaction

    with pytest.raises(IntegrityError), transaction.atomic():
        OfficialCompanyOwnerCredential.objects.update(blocked_origin="arbitrary")


def test_legacy_migration_labels_stopped_rows_without_changing_tokens_or_history():
    from importlib import import_module
    from types import SimpleNamespace

    from django.apps import apps

    migration = import_module("core.migrations.0225_official_company_credential_provenance")
    for revision, status in enumerate(("ready", "blocked", "refreshing"), 1):
        OfficialCompanyOwnerCredential.objects.create(
            key="fixture-" + status, encrypted_tokens=b"cipher-" + status.encode(),
            revision=revision, status=status,
        )
    before = list(OfficialCompanyOwnerCredential.objects.order_by("key").values_list(
        "key", "status", "revision", "encrypted_tokens", "updated_at",
    ))
    migration.mark_legacy_stops(apps, SimpleNamespace(connection=SimpleNamespace(alias="default")))
    after = list(OfficialCompanyOwnerCredential.objects.order_by("key").values_list(
        "key", "status", "revision", "encrypted_tokens", "updated_at",
    ))
    assert before == after
    for row in OfficialCompanyOwnerCredential.objects.all():
        expected = ("", "", None) if row.status == "ready" else ("unknown", "legacy_unknown", None)
        assert (row.blocked_reason, row.blocked_origin, row.blocked_at) == expected
