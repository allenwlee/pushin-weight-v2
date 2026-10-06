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
    intent.next_attempt_at = None
    intent.save()
    client.reset_mock()
    client.members.return_value = ({"987654"}, True)
    sync_intents(cfg=cfg, client=client)
    assert not client.add.called
    intent.refresh_from_db()
    assert intent.status == "confirmed"
    assert TwitterListMembership.objects.get(account=intent.account).active


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
            response.json.return_value = {"data": {"owner_id": "17456158", "private": True}}
            return response
        requests.append(kwargs["params"].get("pagination_token"))
        page = len(requests)
        response.json.return_value = {
            "data": [{"id": str(page)}],
            "meta": {"next_token": str(page)} if page < 4 else {},
        }
        return response

    client = XOwnerListClient(
        access_token="test-token", list_id="2067062923525275922",
        owner_id="17456158", request=transport,
    )
    client.preflight()
    members, complete = client.members()
    assert members == {"1", "2", "3", "4"}
    assert complete
    assert requests == [None, "1", "2", "3"]
