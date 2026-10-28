from unittest.mock import Mock

import pytest

from core.models import (
    Account,
    OfficialCompanyAccountState,
    OfficialCompanyListIntent,
    TwitterListMembership,
)
from core.official_company_lists import XListError, XOwnerListClient, sync_intents
from x_monitor.config import OfficialCompanyConfig

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


def setup_intent():
    account = Account.objects.create(author_id="987654", handle="voice_lab")
    state = OfficialCompanyAccountState.objects.create(
        account=account, status="registered", evidence_hash="a" * 64
    )
    intent = OfficialCompanyListIntent.objects.create(
        account=account,
        state=state,
        evidence_hash=state.evidence_hash,
        list_id=2067062923525275922,
    )
    cfg = OfficialCompanyConfig(
        enabled=True, registration_enabled=True, list_sync_enabled=True
    )
    return intent, cfg


def test_unknown_add_is_verified_before_retry_and_persists_membership():
    intent, cfg = setup_intent()
    client = Mock()
    client.members.return_value = (set(), True)
    client.add.side_effect = TimeoutError()
    sync_intents(cfg=cfg, client=client)
    intent.refresh_from_db()
    assert intent.status == "verify_needed"
    requested_at = intent.add_requested_at
    assert requested_at is not None
    assert intent.add_acknowledged_at is None
    intent.next_attempt_at = None
    intent.save()
    client.reset_mock()
    client.members.return_value = ({"987654"}, True)
    sync_intents(cfg=cfg, client=client)
    assert not client.add.called
    intent.refresh_from_db()
    assert intent.status == "confirmed"
    assert intent.add_requested_at == requested_at
    assert intent.add_acknowledged_at is None
    assert TwitterListMembership.objects.get(account=intent.account).active


def test_preexisting_membership_is_not_recorded_as_an_add():
    intent, cfg = setup_intent()
    client = Mock()
    client.members.return_value = ({"987654"}, True)
    sync_intents(cfg=cfg, client=client)
    intent.refresh_from_db()
    assert intent.status == "confirmed"
    assert intent.add_requested_at is None
    assert intent.add_acknowledged_at is None
    client.add.assert_not_called()


def test_add_acknowledgement_survives_a_superseding_claim():
    intent, cfg = setup_intent()
    client = Mock()
    client.members.return_value = (set(), True)

    def supersede(_identifier):
        intent.refresh_from_db()
        assert intent.add_requested_at is not None
        intent.claim_token = "newer-claim"
        intent.save(update_fields=["claim_token"])

    client.add.side_effect = supersede
    result = sync_intents(cfg=cfg, client=client)
    intent.refresh_from_db()
    assert result["confirmed"] == 0
    assert intent.claim_token == "newer-claim"
    assert intent.add_acknowledged_at is not None


def test_acknowledged_add_is_not_repeated_or_retimestamped():
    intent, cfg = setup_intent()
    client = Mock()
    client.members.return_value = (set(), True)
    sync_intents(cfg=cfg, client=client)
    intent.refresh_from_db()
    stamps = (intent.add_requested_at, intent.add_acknowledged_at)
    assert all(stamps)
    sync_intents(cfg=cfg, client=client)
    intent.refresh_from_db()
    assert stamps == (intent.add_requested_at, intent.add_acknowledged_at)
    client.add.assert_called_once_with("987654")


def test_incomplete_read_does_not_establish_absence_or_trigger_add():
    intent, cfg = setup_intent()
    intent.status = "verify_needed"
    intent.save()
    client = Mock()
    client.members.return_value = (set(), False)
    sync_intents(cfg=cfg, client=client)
    assert not client.add.called
    intent.refresh_from_db()
    assert intent.status == "verify_needed"


def test_owner_mismatch_blocks_remote_writes_until_explicit_retry():
    intent, cfg = setup_intent()
    client = Mock()
    client.preflight.side_effect = XListError("owner_mismatch", auth=True)
    sync_intents(cfg=cfg, client=client)
    intent.refresh_from_db()
    assert intent.status == "blocked_auth"
    client.reset_mock()
    sync_intents(cfg=cfg, client=client)
    assert not client.preflight.called
    assert not client.add.called


def test_disabled_and_stale_evidence_never_call_provider():
    intent, cfg = setup_intent()
    client = Mock()
    sync_intents(cfg=OfficialCompanyConfig(), client=client)
    assert not client.preflight.called
    intent.state.evidence_hash = "b" * 64
    intent.state.save()
    sync_intents(cfg=cfg, client=client)
    assert not client.add.called


def test_adapter_checks_both_owner_and_list_before_add():
    def transport(method, url, **kwargs):
        response = Mock(status_code=200)
        response.json.return_value = (
            {"data": {"id": "17456158"}}
            if url.endswith("/users/me")
            else {"data": {"owner_id": "wrong", "private": True}}
        )
        return response

    client = XOwnerListClient(
        access_token="secret",
        list_id="2067062923525275922",
        owner_id="17456158",
        request=transport,
    )
    with pytest.raises(XListError, match="owner_mismatch"):
        client.preflight()
    with pytest.raises(XListError, match="preflight_required"):
        client.add("123")


def test_observed_manual_removal_requires_review_and_is_never_readded():
    from datetime import timedelta

    from django.utils import timezone

    intent, cfg = setup_intent()
    now = timezone.now()
    intent.status = "confirmed"
    intent.confirmed_at = now - timedelta(hours=1)
    intent.save()
    TwitterListMembership.objects.create(
        account=intent.account,
        list_id=int(cfg.list_id),
        active=False,
        first_seen_at=now - timedelta(days=1),
        last_seen_at=now,
        last_complete_reconciliation_at=now,
        source="snapshot",
    )
    client = Mock()
    sync_intents(cfg=cfg, client=client)
    intent.refresh_from_db()
    assert intent.status == "review_needed"
    assert intent.last_error == "observed_member_removal"
    assert not client.preflight.called and not client.add.called


def test_list_read_reaches_fourth_page_before_confirming_absence():
    requests = []

    def transport(method, url, **kwargs):
        response = Mock(status_code=200)
        if url.endswith("/users/me"):
            response.json.return_value = {"data": {"id": "17456158"}}
            return response
        if not url.endswith("/members"):
            response.json.return_value = {
                "data": {"owner_id": "17456158", "private": True}
            }
            return response
        requests.append(kwargs["params"].get("pagination_token"))
        page = len(requests)
        response.json.return_value = {
            "data": [{"id": str(page)}],
            "meta": {"next_token": str(page)} if page < 4 else {},
        }
        return response

    client = XOwnerListClient(
        access_token="test-token",
        list_id="2067062923525275922",
        owner_id="17456158",
        request=transport,
    )
    client.preflight()
    members, complete = client.members()
    assert members == {"1", "2", "3", "4"}
    assert complete
    assert requests == [None, "1", "2", "3"]


def test_rate_limit_stops_batch_and_pauses_other_accounts_without_spending_retries():
    from datetime import timedelta

    from django.utils import timezone

    first, cfg = setup_intent()
    second_account = Account.objects.create(author_id="987655", handle="another_lab")
    second_state = OfficialCompanyAccountState.objects.create(
        account=second_account, status="registered", evidence_hash="b" * 64,
    )
    second = OfficialCompanyListIntent.objects.create(
        account=second_account, state=second_state, evidence_hash=second_state.evidence_hash,
        list_id=first.list_id,
    )
    client = Mock()
    client.members.return_value = (set(), True)
    reset = timezone.now() + timedelta(minutes=20)
    client.add.side_effect = XListError("http_429", retry_at=reset)
    result = sync_intents(cfg=cfg, client=client)
    assert result["status"] == "deferred_rate_limit" and result["writes"] == 1
    client.add.assert_called_once_with(first.account.author_id)
    for intent in [first, second]:
        intent.refresh_from_db()
        assert intent.status == "verify_needed" and intent.last_error == "http_429"
        assert intent.next_attempt_at == reset and intent.attempts == 0
        assert intent.claim_token == "" and intent.add_acknowledged_at is None
    assert second.add_requested_at is None
    client.reset_mock()
    assert sync_intents(cfg=cfg, client=client)["status"] == "deferred_rate_limit"
    client.preflight.assert_not_called()
    OfficialCompanyListIntent.objects.update(next_attempt_at=timezone.now() - timedelta(seconds=1))
    client.add.side_effect = None
    assert sync_intents(cfg=cfg, client=client)["confirmed"] == 2
    assert OfficialCompanyListIntent.objects.filter(status="confirmed", attempts=1).count() == 2


def test_repeated_provider_throttles_do_not_exhaust_account_retry_allowance():
    from datetime import timedelta

    from django.utils import timezone

    intent, cfg = setup_intent()
    client = Mock()
    client.members.return_value = (set(), True)
    client.add.side_effect = XListError("http_429")
    for _ in range(6):
        result = sync_intents(cfg=cfg, client=client)
        assert result["status"] == "deferred_rate_limit"
        intent.refresh_from_db()
        assert intent.attempts == 0 and intent.status == "verify_needed"
        intent.next_attempt_at = timezone.now() - timedelta(seconds=1)
        intent.save()
    client.add.side_effect = None
    assert sync_intents(cfg=cfg, client=client)["confirmed"] == 1


def test_adapter_preserves_bounded_provider_reset_on_429():
    from datetime import timedelta

    from django.utils import timezone

    reset = int((timezone.now() + timedelta(minutes=20)).timestamp())
    response = Mock(status_code=429, headers={"x-rate-limit-reset": str(reset)})
    client = XOwnerListClient(
        access_token="test-token", list_id="2067062923525275922", owner_id="17456158",
        request=Mock(return_value=response),
    )
    with pytest.raises(XListError, match="http_429") as error:
        client.preflight()
    assert error.value.retry_at.timestamp() == pytest.approx(reset, abs=0.01)
    assert not error.value.auth


def stored_client(monkeypatch, cfg, *, refusal_at="POST", status=403, payload=None):
    """Keep credential persistence and HTTP error routing real; fake only transport."""
    from functools import partial

    from cryptography.fernet import Fernet

    from core import official_company_lists as lists
    from core.official_company_credentials import OwnerTokenStore

    store = OwnerTokenStore(
        key=Fernet.generate_key(), client_id="test-client", client_secret="test-secret"
    )
    store.provision(access_token="private-access-token", refresh_token="private-refresh")
    calls = []

    def transport(method, url, **kwargs):
        calls.append((method, url))
        response = Mock(status_code=200)
        if (refusal_at == "POST" and method == "POST") or url.endswith(refusal_at):
            response.status_code = status
            response.json.return_value = payload or {
                "type": "https://api.x.com/2/problems/client-forbidden",
                "detail": "Never persist this raw detail: private-access-token",
            }
        elif url.endswith("/users/me"):
            response.json.return_value = {"data": {"id": cfg.owner_id}}
        elif url.endswith("/members"):
            response.json.return_value = {"data": []}
        else:
            response.json.return_value = {
                "data": {"owner_id": cfg.owner_id, "private": True}
            }
        return response

    monkeypatch.setattr(OwnerTokenStore, "from_env", lambda: store)
    monkeypatch.setattr(lists, "XOwnerListClient", partial(XOwnerListClient, request=transport))
    return lists.build_owner_list_client(cfg), store, calls


def test_real_add_refusal_preserves_credential_and_pauses_list_without_spending_unsent_attempts(monkeypatch):
    from datetime import timedelta

    from django.utils import timezone

    from core.models import OfficialCompanyOwnerCredential

    first, cfg = setup_intent()
    account = Account.objects.create(author_id="987655", handle="second_lab")
    state = OfficialCompanyAccountState.objects.create(
        account=account, status="registered", evidence_hash="b" * 64
    )
    second = OfficialCompanyListIntent.objects.create(
        account=account, state=state, evidence_hash=state.evidence_hash, list_id=first.list_id
    )
    client, store, calls = stored_client(monkeypatch, cfg)
    before = timezone.now()
    result = sync_intents(cfg=cfg, client=client)
    assert result["status"] == "deferred_write_refused"
    assert result["error"] == "http_403:client-forbidden"
    assert result["writes"] == 1
    assert OfficialCompanyOwnerCredential.objects.get().status == "ready"
    assert store.load()["access_token"] == "private-access-token"
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.attempts == 1 and second.attempts == 0
    for intent in (first, second):
        assert intent.status == "verify_needed"
        assert intent.last_error == "http_403:client-forbidden"
        assert before + timedelta(hours=2) <= intent.next_attempt_at <= timezone.now() + timedelta(hours=2)
        assert not intent.claim_token and intent.claim_expires_at is None
        assert intent.add_acknowledged_at is None
    assert first.add_requested_at and second.add_requested_at is None
    assert len([c for c in calls if c[0] == "POST"]) == 1
    calls.clear()
    assert sync_intents(cfg=cfg, client=client)["status"] == "deferred_write_refused"
    assert calls == []
    OfficialCompanyListIntent.objects.update(next_attempt_at=timezone.now() - timedelta(seconds=1))
    # A manual addition during cooldown is verified, never posted again.
    client = Mock()
    client.members.return_value = ({first.account.author_id, second.account.author_id}, True)
    assert sync_intents(cfg=cfg, client=client)["confirmed"] == 2
    client.add.assert_not_called()


def test_repeated_write_refusals_stop_at_review_and_keep_last_cooldown(monkeypatch):
    from datetime import timedelta

    from django.utils import timezone

    from core.models import OfficialCompanyOwnerCredential

    intent, cfg = setup_intent()
    client, _, calls = stored_client(monkeypatch, cfg)
    for attempt in range(1, 6):
        before = timezone.now()
        result = sync_intents(cfg=cfg, client=client)
        assert result["status"] == "deferred_write_refused"
        intent.refresh_from_db()
        assert intent.attempts == attempt
        assert intent.status == ("review_needed" if attempt == 5 else "verify_needed")
        assert before + timedelta(hours=min(24, 2 ** attempt)) <= intent.next_attempt_at
        assert sync_intents(cfg=cfg, client=client)["status"] == "deferred_write_refused"
        intent.next_attempt_at = timezone.now() - timedelta(seconds=1)
        intent.save(update_fields=["next_attempt_at"])
    assert sync_intents(cfg=cfg, client=client)["status"] == "idle"
    assert len([c for c in calls if c[0] == "POST"]) == 5
    assert OfficialCompanyOwnerCredential.objects.get().status == "ready"


@pytest.mark.parametrize("refusal_at", ["/users/me", "/members", "POST"])
def test_persistent_401_after_one_refresh_still_blocks_credential(monkeypatch, refusal_at):
    from core.models import OfficialCompanyOwnerCredential

    intent, cfg = setup_intent()
    client, store, _ = stored_client(monkeypatch, cfg, refusal_at=refusal_at, status=401)
    original_refresh = store.refresh
    response = Mock(status_code=200)
    response.json.return_value = {
        "access_token": "rotated-access", "refresh_token": "rotated-refresh",
        "expires_in": 7200,
        "scope": "tweet.read users.read list.read list.write offline.access",
    }
    refresh_transport = Mock(return_value=response)
    monkeypatch.setattr(store, "refresh", lambda: original_refresh(request=refresh_transport))
    result = sync_intents(cfg=cfg, client=client)
    assert result["status"] == "blocked_auth"
    intent.refresh_from_db()
    assert intent.status == "blocked_auth"
    credential = OfficialCompanyOwnerCredential.objects.get()
    assert credential.status == "blocked" and credential.revision == 2
    refresh_transport.assert_called_once()


@pytest.mark.parametrize("status, payload, error", [
    (403, {"reason": "client-not-enrolled"}, "http_403:client-not-enrolled"),
    (200, {"data": {"id": "wrong-owner"}}, "owner_mismatch"),
])
def test_preflight_permission_and_owner_failures_still_block_credential(monkeypatch, status, payload, error):
    from core.models import OfficialCompanyOwnerCredential

    intent, cfg = setup_intent()
    client, _, calls = stored_client(monkeypatch, cfg, refusal_at="/users/me", status=status, payload=payload)
    result = sync_intents(cfg=cfg, client=client)
    intent.refresh_from_db()
    assert result["status"] == intent.status == "blocked_auth"
    assert result["error"] == intent.last_error == error
    assert OfficialCompanyOwnerCredential.objects.get().status == "blocked"
    assert all(method == "GET" for method, _ in calls)


@pytest.mark.parametrize("payload, expected", [
    ({"reason": "client-not-enrolled"}, "http_403:client-not-enrolled"),
    ({"errors": [{"code": 326, "message": "private-access-token"}]}, "http_403:code-326"),
    ({"reason": "private-access-token"}, "http_403:unspecified"),
    ({"detail": "Bearer private-access-token"}, "http_403:unspecified"),
    (["invalid"], "http_403:unspecified"),
])
def test_write_refusal_reason_is_structured_bounded_and_does_not_copy_tokens(monkeypatch, payload, expected):
    intent, cfg = setup_intent()
    client, _, _ = stored_client(monkeypatch, cfg, payload=payload)
    result = sync_intents(cfg=cfg, client=client)
    assert result["error"] == expected
    intent.refresh_from_db()
    assert intent.last_error == expected and len(intent.last_error) <= 128
    assert "private-access-token" not in str(result)
