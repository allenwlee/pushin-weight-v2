from unittest.mock import Mock

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.models import Account, OfficialCompanyAccountState, OfficialCompanyListIntent
from core.official_company_accounts import MODEL, POLICY_VERSION, register_account
from core.official_company_admin import account_report
from core.official_company_lists import sync_intents
from x_monitor.config import OfficialCompanyConfig

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
LIST_ID = 2067062923525275922


@pytest.fixture
def owner_client(settings):
    settings.SECURE_SSL_REDIRECT = False
    user = get_user_model().objects.create_user(username="admin-staff", is_staff=True)
    client = Client()
    client.force_login(user)
    return client


def test_registration_sync_and_admin_display_share_real_data(owner_client):
    account = Account.objects.create(author_id="44556", handle="speech_lab")
    state = OfficialCompanyAccountState.objects.create(
        account=account,
        evidence_hash="a" * 64,
        status="accepted",
        model=MODEL,
        policy_version=POLICY_VERSION,
        decision={
            "outcome": "accepted",
            "organization_name": "Speech Lab",
            "rationale": "We develop speech models.",
            "model_types": ["speech"],
        },
    )
    cfg = OfficialCompanyConfig(
        enabled=True, registration_enabled=True, list_sync_enabled=True
    )
    assert register_account(state.pk, cfg=cfg)
    provider = Mock()
    provider.members.return_value = (set(), True)
    sync_intents(cfg=cfg, client=provider)
    response = owner_client.get("/admin?locale=en")
    assert response.status_code == 200
    assert reverse("product_review") == "/admin"
    report = response.context["official_accounts"]
    assert report["summary"]["found"] == report["summary"]["registered"] == 1
    assert report["summary"]["added"] == 1
    assert report["rows"][0]["list_outcome"] == "added"
    assert "Speech Lab" in response.content.decode()
    assert "We develop speech models." in response.content.decode()
    assert "Add acknowledged" in response.content.decode()
    assert report["rows"][0]["intent"].add_acknowledged_at is not None


def test_existing_member_does_not_inflate_add_count(owner_client):
    account = Account.objects.create(author_id="77556", handle="existing_lab")
    state = OfficialCompanyAccountState.objects.create(
        account=account, evidence_hash="a" * 64, status="registered"
    )
    OfficialCompanyListIntent.objects.create(
        account=account,
        state=state,
        evidence_hash="a" * 64,
        list_id=LIST_ID,
        status="confirmed",
    )
    response = owner_client.get("/admin?locale=en")
    assert response.context["official_accounts"]["summary"]["added"] == 0
    assert "Already present; no add requested" in response.content.decode()


def test_pending_scan_does_not_bury_official_accounts_or_list_history():
    official = OfficialCompanyAccountState.objects.create(
        account=Account.objects.create(author_id="61000"),
        evidence_hash="b" * 64,
        status="accepted",
    )
    previous = OfficialCompanyAccountState.objects.create(
        account=Account.objects.create(author_id="61001"),
        evidence_hash="c" * 64,
        status="pending",
        candidate_priority=2,
    )
    OfficialCompanyListIntent.objects.create(
        account=previous.account,
        state=previous,
        evidence_hash="c" * 64,
        list_id=LIST_ID,
        status="confirmed",
    )
    for index in range(60):
        OfficialCompanyAccountState.objects.create(
            account=Account.objects.create(author_id=str(62000 + index)),
            evidence_hash="a" * 64,
            status="pending",
            candidate_priority=2,
        )
    report = account_report(list_id=LIST_ID)
    assert {row["state"].pk for row in report["rows"]} == {official.pk, previous.pk}
    assert report["summary"]["pending"] == 61
    assert report["summary"]["found"] == 1
    assert not report["page"].has_next()


def test_console_query_count_and_pagination_are_bounded():
    for index in range(52):
        account = Account.objects.create(
            author_id=str(50000 + index), handle=f"lab{index}"
        )
        state = OfficialCompanyAccountState.objects.create(
            account=account, evidence_hash="b" * 64, status="registered"
        )
        OfficialCompanyListIntent.objects.create(
            account=account, state=state, evidence_hash="b" * 64, list_id=LIST_ID
        )
    with CaptureQueriesContext(connection) as queries:
        report = account_report(list_id=LIST_ID, page=1)
        assert len(report["rows"]) == 50
        assert report["page"].has_next()
        assert report["summary"]["found"] == 52
        assert len(queries) <= 6
    assert len(account_report(list_id=LIST_ID, page=2)["rows"]) == 2
    assert account_report(list_id=LIST_ID, page="bad")["page"].number == 1


def test_admin_redirects_preserve_locale_and_access(owner_client):
    assert owner_client.get("/product-review/?locale=ja").url == "/admin?locale=ja"
    assert owner_client.get("/admin/").url == "/admin"
    assert (
        owner_client.get("/product-review/42/?locale=en").url
        == "/admin/products/42/?locale=en"
    )
    assert Client().get("/admin").status_code == 302
    user = get_user_model().objects.create_user(username="ordinary-admin")
    client = Client()
    client.force_login(user)
    assert client.get("/admin").status_code == 403
    assert client.get("/product-review/").status_code == 403


def test_legacy_post_keeps_csrf_protection(owner_client):
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.cookies = owner_client.cookies
    assert (
        csrf_client.post("/product-review/42/", {"action": "approve"}).status_code
        == 403
    )


def test_already_open_legacy_approval_form_still_saves(owner_client):
    from core.models import Brand
    from tests.test_product_review import _proposal

    brand = Brand.objects.create(nickname="legacy_lab")
    proposal = _proposal("k", brand=brand)
    response = owner_client.post(
        f"/product-review/{proposal.pk}/?locale=en",
        {
            "action": "approve",
            "reason": "Confirmed official model",
            "brand_id": brand.pk,
            "product_type": "llm-model",
            "catalog_mode": "x_only",
        },
    )
    assert response.status_code == 302
    assert response.url == f"/admin/products/{proposal.pk}/?locale=en"
    proposal.refresh_from_db()
    assert proposal.review_status == "approved"
