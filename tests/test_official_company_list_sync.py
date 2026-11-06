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


def stored_client(monkeypatch, cfg, *, refusal_at="POST", status=403, payload=None, refusal_page=None):
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
        refused = (refusal_at == "POST" and method == "POST") or url.endswith(refusal_at)
        if refusal_page is not None:
            refused = refused and kwargs.get("params", {}).get("pagination_token") == refusal_page
        if refused:
            response.status_code = status
            response.json.return_value = payload or {
                "type": "https://api.x.com/2/problems/client-forbidden",
                "detail": "Never persist this raw detail: private-access-token",
            }
        elif url.endswith("/users/me"):
            response.json.return_value = {"data": {"id": cfg.owner_id}}
        elif url.endswith("/members"):
            response.json.return_value = {"data": []}
            if refusal_page is not None:
                response.json.return_value["meta"] = {"next_token": refusal_page}
        else:
            response.json.return_value = {
                "data": {"owner_id": cfg.owner_id, "private": True}
            }
        return response

    monkeypatch.setattr(OwnerTokenStore, "from_env", lambda: store)
    monkeypatch.setattr(lists, "XOwnerListClient", partial(XOwnerListClient, request=transport))
    return lists.build_owner_list_client(cfg), store, calls


@pytest.mark.parametrize("reason, status", [
    ("client-forbidden", "deferred_write_refused"),
    ("spend-cap-reached", "deferred_billing"),
])
def test_real_add_refusal_preserves_credential_and_pauses_list_without_spending_unsent_attempts(monkeypatch, reason, status):
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
    client, store, calls = stored_client(monkeypatch, cfg, payload={"reason": reason})
    before = timezone.now()
    result = sync_intents(cfg=cfg, client=client)
    assert result["status"] == status
    assert result["error"] == "http_403:" + reason
    assert result["writes"] == 1
    assert OfficialCompanyOwnerCredential.objects.get().status == "ready"
    assert store.load()["access_token"] == "private-access-token"
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.attempts == 1 and second.attempts == 0
    for intent in (first, second):
        assert intent.status == "verify_needed"
        assert intent.last_error == "http_403:" + reason
        assert before + timedelta(hours=2) <= intent.next_attempt_at <= timezone.now() + timedelta(hours=2)
        assert not intent.claim_token and intent.claim_expires_at is None
        assert intent.add_acknowledged_at is None
    assert first.add_requested_at and second.add_requested_at is None
    assert len([c for c in calls if c[0] == "POST"]) == 1
    calls.clear()
    assert sync_intents(cfg=cfg, client=client)["status"] == status
    assert calls == []
    OfficialCompanyListIntent.objects.update(next_attempt_at=timezone.now() - timedelta(seconds=1))
    # A manual addition during cooldown is verified, never posted again.
    client = Mock()
    client.members.return_value = ({first.account.author_id, second.account.author_id}, True)
    assert sync_intents(cfg=cfg, client=client)["confirmed"] == 2
    client.add.assert_not_called()


@pytest.mark.parametrize("reason, status", [
    ("client-forbidden", "deferred_write_refused"),
    ("spend-cap-reached", "deferred_billing"),
])
def test_repeated_write_refusals_stop_at_review_and_keep_last_cooldown(monkeypatch, reason, status):
    from datetime import timedelta

    from django.utils import timezone

    from core.models import OfficialCompanyOwnerCredential

    intent, cfg = setup_intent()
    client, _, calls = stored_client(monkeypatch, cfg, payload={"reason": reason})
    for attempt in range(1, 6):
        before = timezone.now()
        result = sync_intents(cfg=cfg, client=client)
        assert result["status"] == status
        intent.refresh_from_db()
        assert intent.attempts == attempt
        assert intent.status == ("review_needed" if attempt == 5 else "verify_needed")
        assert before + timedelta(hours=min(24, 2 ** attempt)) <= intent.next_attempt_at
        assert sync_intents(cfg=cfg, client=client)["status"] == status
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
    (403, {"detail": "spend-cap-reached"}, "http_403:unspecified"),
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


@pytest.mark.parametrize("refusal_at", ["POST", "/users/me"])
def test_cycle_logs_list_billing_and_keeps_cooldown_visible_without_provider_retry(monkeypatch, caplog, refusal_at):
    import json
    import logging
    from datetime import timedelta

    from django.utils import timezone

    from core.models import OfficialCompanyOwnerCredential
    from core.official_company_lists import build_owner_list_client
    from monitor.cycle import CycleRunner
    from x_monitor.config import Config

    intent, list_cfg = setup_intent()
    client, _, calls = stored_client(
        monkeypatch, list_cfg, refusal_at=refusal_at, payload={"reason": "spend-cap-reached"}
    )
    credential = OfficialCompanyOwnerCredential.objects.get()
    original_tokens, original_revision = bytes(credential.encrypted_tokens), credential.revision
    cfg = Config(enabled_models=["deepseek"], daily_ceiling=100, official_company=list_cfg)
    before = timezone.now()
    with caplog.at_level(logging.INFO, logger="monitor.cycle"):
        for index in range(2):
            # A new runner/client must honor persisted cooldowns without loading tokens.
            runner = CycleRunner(
                cfg=cfg, cycle_kind="scheduled",
                _official_list_client=client if not index else build_owner_list_client(list_cfg),
                _official_company_call=Mock(side_effect=AssertionError("unexpected model call")),
            )
            result = runner._run_official_company_discovery(
                run_id=f"list-refusal-{index}", deadline=cfg.harvest.start_deadline()
            )
            assert result["list_sync"]["status"] == "deferred_billing"
            assert result["list_sync"]["error"] == "http_403:spend-cap-reached"
            intent.refresh_from_db()
            credential.refresh_from_db()
            assert credential.status == "ready"
            assert bytes(credential.encrypted_tokens) == original_tokens
            assert credential.revision == original_revision
            assert intent.status == "verify_needed"
            assert intent.attempts == (1 if refusal_at == "POST" else 0)
            assert not intent.claim_token and intent.claim_expires_at is None
            delay = timedelta(hours=2 if refusal_at == "POST" else 24)
            assert before + delay <= intent.next_attempt_at <= timezone.now() + delay
            assert result["list_sync"]["retry_at"] == intent.next_attempt_at.isoformat()
            if index:
                assert not calls
            else:
                assert bool(intent.add_requested_at) == (refusal_at == "POST")
                assert result["list_sync"]["writes"] == (1 if refusal_at == "POST" else 0)
            calls.clear()
    records = [
        json.loads(record.message.removeprefix("OFFICIAL_COMPANY_LIST_SYNC "))
        for record in caplog.records if record.message.startswith("OFFICIAL_COMPANY_LIST_SYNC ")
    ]
    assert len(records) == 2
    assert all(row["status"] == "deferred_billing" and row["error"] == "http_403:spend-cap-reached" for row in records)
    assert "private-access-token" not in caplog.text


@pytest.mark.parametrize("refusal_at, refusal_page", [
    ("/users/me", None),
    ("/lists/2067062923525275922", None),
    ("/members", "page-two"),
])
def test_billing_read_cooldown_preserves_all_attempts_and_recovers_when_due(
    monkeypatch, refusal_at, refusal_page,
):
    from datetime import timedelta
    from functools import partial

    from django.utils import timezone

    from core import official_company_lists as lists
    from core.models import OfficialCompanyOwnerCredential

    first, cfg = setup_intent()
    first.attempts = 3
    first.save(update_fields=["attempts"])
    account = Account.objects.create(author_id="987655", handle="second_lab")
    state = OfficialCompanyAccountState.objects.create(
        account=account, status="registered", evidence_hash="b" * 64,
    )
    second = OfficialCompanyListIntent.objects.create(
        account=account, state=state, evidence_hash=state.evidence_hash, list_id=first.list_id,
    )
    client, _, calls = stored_client(
        monkeypatch, cfg, refusal_at=refusal_at, refusal_page=refusal_page,
        payload={"type": "https://api.x.com/2/problems/spend-cap-reached"},
    )
    credential = OfficialCompanyOwnerCredential.objects.get()
    original_tokens = bytes(credential.encrypted_tokens)
    before = timezone.now()
    result = sync_intents(cfg=cfg, client=client)
    assert result["status"] == "deferred_billing"
    assert result["writes"] == 0 and result["claimed"] == 2
    first.refresh_from_db()
    second.refresh_from_db()
    assert (first.attempts, second.attempts) == (3, 0)
    for intent in (first, second):
        assert intent.status == "verify_needed"
        assert intent.last_error == "http_403:spend-cap-reached"
        assert not intent.claim_token and intent.claim_expires_at is None
        assert before + timedelta(hours=24) <= intent.next_attempt_at <= timezone.now() + timedelta(hours=24)
        assert intent.next_attempt_at.isoformat() == result["retry_at"]
        assert intent.add_requested_at is None and intent.add_acknowledged_at is None
    assert all(method == "GET" for method, _ in calls)
    if refusal_page:
        assert len([url for _, url in calls if url.endswith("/members")]) == 2
    credential.refresh_from_db()
    assert credential.status == "ready" and bytes(credential.encrypted_tokens) == original_tokens

    # Even a newly queued account must wait for the whole-list billing cooldown.
    third_account = Account.objects.create(author_id="987656", handle="third_lab")
    third_state = OfficialCompanyAccountState.objects.create(
        account=third_account, status="registered", evidence_hash="c" * 64,
    )
    third = OfficialCompanyListIntent.objects.create(
        account=third_account, state=third_state, evidence_hash=third_state.evidence_hash,
        list_id=first.list_id,
    )
    calls.clear()
    assert sync_intents(cfg=cfg, client=lists.build_owner_list_client(cfg))["status"] == "deferred_billing"
    assert calls == []
    third.refresh_from_db()
    assert third.status == "pending" and third.attempts == 0

    # Once due, real owner/member reads confirm an independently added account
    # and deliver the still-absent sibling once, through the same stored client.
    recovered_calls = []

    def recovered_transport(method, url, **kwargs):
        recovered_calls.append((method, url))
        response = Mock(status_code=200)
        if method == "POST":
            assert kwargs["json"] == {"user_id": second.account.author_id}
            response.json.return_value = {"data": {"is_member": True}}
        elif url.endswith("/users/me"):
            response.json.return_value = {"data": {"id": cfg.owner_id}}
        elif url.endswith("/members"):
            response.json.return_value = {"data": [{"id": first.account.author_id}]}
        else:
            response.json.return_value = {"data": {"owner_id": cfg.owner_id, "private": True}}
        return response

    monkeypatch.setattr(lists, "XOwnerListClient", partial(XOwnerListClient, request=recovered_transport))
    OfficialCompanyListIntent.objects.filter(pk__in=[first.pk, second.pk]).update(
        next_attempt_at=timezone.now() - timedelta(seconds=1),
    )
    result = sync_intents(cfg=cfg, client=lists.build_owner_list_client(cfg))
    assert result["confirmed"] == 2 and result["writes"] == 1
    assert len([method for method, _ in recovered_calls if method == "POST"]) == 1
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.status == second.status == "confirmed"
    assert first.add_requested_at is None
    assert second.add_requested_at is not None and second.add_acknowledged_at is not None
