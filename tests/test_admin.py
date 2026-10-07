from unittest.mock import Mock

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.models import Account, OfficialCompanyAccountState, OfficialCompanyListIntent
from core.official_company_accounts import POLICY_VERSION, register_account
from core.official_company_admin import account_report
from core.official_company_lists import sync_intents
from x_monitor.config import OfficialCompanyConfig

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
LIST_ID = 2067062923525275922


def test_candidates_show_existing_official_brands_without_duplicate_counts(owner_client):
    from core.models import Brand, BrandAccount, Role
    from core.official_company_candidates import CANDIDATE_POLICY

    a = Account.objects.create(author_id="1019503378517200897", handle="SenseTime_AI")
    state = OfficialCompanyAccountState.objects.create(account=a, evidence_hash="b" * 64, candidate_priority=1, candidate_policy_version=CANDIDATE_POLICY, status="review_needed")
    role, _ = Role.objects.get_or_create(key="official")
    for key in ["sensechat", "sensenova"]:
        BrandAccount.objects.create(account=a, brand=Brand.objects.create(nickname=key), role=role)
    response = owner_client.get(reverse("product_review"), {"candidate_status": "already_tracked"})
    report = response.context["official_candidates"]
    assert report["summary"]["already_tracked"] == 1
    assert report["summary"]["llm_evaluated"] == 0
    assert report["page"].paginator.count == 1
    assert report["rows"][0]["state"].pk == state.pk
    assert set(report["rows"][0]["tracked_brands"]) == {"sensechat", "sensenova"}
    assert b"sensechat" in response.content and b"sensenova" in response.content


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
        model="owner-attestation",
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
        model="owner-attestation",
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


def test_candidate_filters_preserve_pagination_and_exclude_unscreened(owner_client):
    from core.official_company_candidates import CANDIDATE_POLICY

    for number in range(53):
        account = Account.objects.create(author_id=str(94000 + number), handle=f"selected_lab_{number}")
        OfficialCompanyAccountState.objects.create(
            account=account, evidence_hash="f" * 64, status="pending",
            candidate_priority=1 if number == 52 else 2, candidate_policy_version=CANDIDATE_POLICY,
        )
    for identifier, priority, policy in [("95000", None, ""), ("95001", 2, "old-filter")]:
        OfficialCompanyAccountState.objects.create(
            account=Account.objects.create(author_id=identifier, handle="legacy_unfiltered_" + identifier),
            evidence_hash="a" * 64, candidate_priority=priority, candidate_policy_version=policy,
        )
    response = owner_client.get("/admin", {"candidate_page": 2, "candidate_status": "waiting", "locale": "ja", "accounts_page": 1})
    candidates = response.context["official_candidates"]
    assert candidates["summary"]["selected"] == 53
    assert len(candidates["rows"]) == 3 and candidates["page"].paginator.count == 53
    assert "candidate_status=waiting" in candidates["previous_url"] and "locale=ja" in candidates["previous_url"]
    assert "accounts_page=1" in candidates["previous_url"]
    response = owner_client.get("/admin", {"candidate_q": "@selected_lab_52", "candidate_status": "waiting"})
    assert [r["state"].account.handle for r in response.context["official_candidates"]["rows"]] == ["selected_lab_52"]
    response = owner_client.get("/admin", {"candidate_status": "unknown", "candidate_q": '"><script>alert(1)</script>'})
    assert response.context["official_candidates"]["status"] == "all"
    assert '<script>alert(1)</script>' not in response.content.decode()


def test_candidate_llm_count_uses_completed_attempts_not_owner_or_failures():
    from core.models import OfficialCompanyAttempt
    from core.official_company_admin import candidate_report
    from core.official_company_candidates import CANDIDATE_POLICY

    for index, model, attempt_status, state_status in [
        (0, "test-model", "completed", "review_needed"),
        (1, "owner-attestation", "owner_attested", "accepted"),
        (2, "test-model", "failed", "review_needed"),
    ]:
        state = OfficialCompanyAccountState.objects.create(
            account=Account.objects.create(author_id=str(96000 + index)),
            evidence_hash="a" * 64, model=model, status=state_status,
            candidate_priority=1, candidate_policy_version=CANDIDATE_POLICY,
        )
        for number in range(2):
            OfficialCompanyAttempt.objects.create(
                state=state, evidence_hash=state.evidence_hash, claim_token=f"{index}-{number}",
                model=model, policy_version="test", status=attempt_status, reserved_usd=0,
            )
    report = candidate_report()
    assert report["summary"]["selected"] == 3
    assert report["summary"]["llm_evaluated"] == 1
    assert report["summary"]["owner_settled"] == 1
    assert report["summary"]["review_needed"] == 1
    assert report["summary"]["failed_evaluations"] == 1
    assert candidate_report(status="owner_settled")["page"].paginator.count == 1


def test_attention_tabs_partition_current_failures_tracked_and_review(owner_client):
    from core.models import (
        Brand,
        BrandAccount,
        Company,
        CompanyAccount,
        OfficialCompanyAttempt,
        Role,
    )
    from core.official_company_candidates import CANDIDATE_POLICY

    states = {}
    for index, name, status, error in [
        (0, "ordinary", "review_needed", "human_review_required"),
        (1, "latest_failed", "review_needed", "ValueError"),
        (2, "retry_failed", "retry_due", "TimeoutError"),
        (3, "recovered", "review_needed", "human_review_required"),
        (4, "stale_failure", "review_needed", ""),
        (5, "tracked_brand", "review_needed", "ValueError"),
        (6, "tracked_company", "accepted", ""),
        (7, "registered", "registered", ""),
        (8, "blocked", "review_needed", "evidence_envelope_exceeded"),
    ]:
        state = OfficialCompanyAccountState.objects.create(
            account=Account.objects.create(author_id=str(97300 + index), handle=name),
            evidence_hash="a" * 64, status=status, last_error=error,
            candidate_priority=1, candidate_policy_version=CANDIDATE_POLICY,
        )
        states[name] = state
        attempt_statuses = {
            "latest_failed": ["completed", "failed"], "retry_failed": ["failed"],
            "recovered": ["failed", "completed"], "stale_failure": ["failed"],
            "tracked_brand": ["failed"], "registered": ["failed"],
        }.get(name, [])
        for number, attempt_status in enumerate(attempt_statuses):
            OfficialCompanyAttempt.objects.create(
                state=state, evidence_hash="b" * 64 if name == "stale_failure" else state.evidence_hash,
                claim_token=f"{name}-{number}", model="test-model", policy_version="test",
                status=attempt_status, reserved_usd=0,
            )
    role, _ = Role.objects.get_or_create(key="official")
    for name in ["alpha", "beta"]:
        BrandAccount.objects.create(
            account=states["tracked_brand"].account,
            brand=Brand.objects.create(nickname=name), role=role,
        )
    company = Company.objects.create(nickname="existing_company")
    for name in ["tracked_company", "registered"]:
        CompanyAccount.objects.create(account=states[name].account, company=company, role=role)
    expected = {
        "review": {"ordinary", "recovered", "stale_failure"},
        "failed": {"latest_failed", "retry_failed", "blocked"},
        "tracked": {"tracked_brand", "tracked_company"},
    }
    for tab, names in expected.items():
        response = owner_client.get("/admin", {"accounts_tab": tab, "candidate_status": "registered", "locale": "en"})
        assert response.status_code == 200
        context = response.context
        assert {r["state"].account.handle for r in context["official_candidates"]["rows"]} == names
        assert context["candidate_metrics"][0]["value"] == len(names)
        assert len(context["candidate_metrics"]) == 1
        assert 'select name="candidate_status"' not in response.content.decode()
        assert context["official_candidates"]["summary"]["selected"] == 9
    tracked_row = next(r for r in context["official_candidates"]["rows"] if r["state"].account.handle == "tracked_company")
    assert tracked_row["tracked_companies"] == ["existing_company"]
    assert tracked_row["status_label"] == "Already tracked"


@pytest.mark.parametrize("tab,error", [("failed", "ValueError"), ("tracked", "already_tracked")])
def test_attention_tabs_preserve_search_pagination_and_fixed_status(owner_client, tab, error):
    from core.models import OfficialCompanyAttempt
    from core.official_company_candidates import CANDIDATE_POLICY

    for number in range(53):
        state = OfficialCompanyAccountState.objects.create(
            account=Account.objects.create(author_id=str(97400 + number), handle=f"attention_{number}"),
            evidence_hash="a" * 64, status="review_needed", last_error=error,
            candidate_priority=1, candidate_policy_version=CANDIDATE_POLICY,
        )
        if tab == "failed":
            OfficialCompanyAttempt.objects.create(
                state=state, evidence_hash=state.evidence_hash, claim_token=str(number),
                model="test-model", policy_version="test", status="failed", reserved_usd=0,
            )
    response = owner_client.get("/admin", {"accounts_tab": tab, "candidate_page": 2, "candidate_status": "registered", "locale": "ja"})
    report = response.context["official_candidates"]
    assert len(report["rows"]) == 3 and report["page"].paginator.count == 53
    assert f"accounts_tab={tab}" in report["previous_url"]
    assert "locale=ja" in report["previous_url"]
    response = owner_client.get("/admin", {"accounts_tab": tab, "candidate_q": "attention_52"})
    assert [r["state"].account.handle for r in response.context["official_candidates"]["rows"]] == ["attention_52"]


def test_review_tab_forces_review_status_and_keeps_navigation(owner_client):
    from core.official_company_candidates import CANDIDATE_POLICY

    for number in range(53):
        OfficialCompanyAccountState.objects.create(
            account=Account.objects.create(author_id=str(98100 + number), handle=f"review_lab_{number}"),
            evidence_hash="a" * 64, status="review_needed",
            candidate_priority=1, candidate_policy_version=CANDIDATE_POLICY,
        )
    OfficialCompanyAccountState.objects.create(
        account=Account.objects.create(author_id="98001", handle="verified_lab"),
        evidence_hash="b" * 64, status="registered",
        candidate_priority=1, candidate_policy_version=CANDIDATE_POLICY,
    )
    response = owner_client.get("/admin", {
        "accounts_tab": "review", "candidate_status": "registered",
        "candidate_page": 2, "locale": "ja",
    })
    context = response.context
    assert context["accounts_tab"] == "review"
    assert context["official_candidates"]["status"] == "review_needed"
    assert context["official_candidates"]["page"].paginator.count == 53
    assert len(context["official_candidates"]["rows"]) == 3
    assert "accounts_tab=review" in context["official_candidates"]["previous_url"]
    assert "locale=ja" in context["official_candidates"]["previous_url"]
    assert 'data-admin-account="98001"' not in response.content.decode()
    for tab in context["account_tabs"]:
        assert "candidate_page=" not in tab["url"] and "candidate_status=" not in tab["url"]
    response = owner_client.get("/admin", {"accounts_tab": "review", "candidate_q": "@review_lab_52"})
    assert [r["state"].account.handle for r in response.context["official_candidates"]["rows"]] == ["review_lab_52"]
    response = owner_client.get("/admin", {"accounts_tab": "invalid", "candidate_status": "waiting"})
    assert response.context["accounts_tab"] == "found"
    assert [r["state"].account.handle for r in response.context["official_accounts"]["rows"]] == ["verified_lab"]


def test_frozen_run_is_read_only_and_limits_tabs_to_frozen_results(owner_client):
    from datetime import timedelta

    from django.utils import timezone

    from core.models import OfficialCompanyAttempt, OfficialCompanyScan
    from core.official_company_requalification import cohort_report, initialize_cohort
    from tests.test_official_company_requalification import manifest, state

    fresh, prior, retry, waiting, stale, rejected, outside = [state(98001 + n) for n in range(7)]
    prior.decision = {"outcome": "accepted"}
    prior.save()
    initialize_cohort(manifest([fresh, prior, retry, waiting, stale, rejected]))
    for s, status, outcome, evidence_hash, policy in [
        (fresh, "completed", "accepted", fresh.evidence_hash, POLICY_VERSION),
        (prior, "completed", "accepted", prior.evidence_hash, POLICY_VERSION),
        (retry, "failed", None, retry.evidence_hash, POLICY_VERSION),
        (stale, "completed", "accepted", "b" * 64, POLICY_VERSION),
        (stale, "completed", "accepted", stale.evidence_hash, "old-policy"),
        (rejected, "completed", "rejected", rejected.evidence_hash, POLICY_VERSION),
        (outside, "completed", "accepted", outside.evidence_hash, POLICY_VERSION),
    ]:
        OfficialCompanyAttempt.objects.create(
            state=s, claim_token=f"frozen-scope-{s.pk}-{policy}-{evidence_hash[:1]}",
            status=status, evidence_hash=evidence_hash, policy_version=policy, model="test",
            reserved_usd=0, error_code="TimeoutError" if status == "failed" else "",
            decision={"outcome": outcome, "organization_name": "<script>company</script>",
                      "development_type": "agent", "rationale": "Own agent"},
        )
    retry.status = "retry_due"
    retry.next_attempt_at = timezone.now() + timedelta(minutes=15)
    retry.save()
    waiting.status = "claimed"
    waiting.save()
    OfficialCompanyAttempt.objects.create(
        state=waiting, evidence_hash=waiting.evidence_hash, claim_token="frozen-in-flight",
        status="reserved", model="test", policy_version=POLICY_VERSION, reserved_usd=0,
    )
    detailed = cohort_report(include_members=True)
    assert cohort_report() == {key: value for key, value in detailed.items() if key not in {'members', 'frozen_at'}}
    snapshots = list(OfficialCompanyAccountState.objects.order_by('pk').values())
    cursor = OfficialCompanyScan.objects.get().cursor
    for tab, expected in [("newly", [fresh]), ("awaiting", [retry]), ("pending", [waiting, stale])]:
        response = owner_client.get('/admin/official-accounts/frozen-run', {'tab': tab, 'account_id': outside.account_id, 'locale': 'en'})
        report = response.context['frozen_run']
        assert [row['state_id'] for row in report['rows']] == [s.pk for s in expected]
        assert report['summary']['population'] == 6 and report['summary']['newly_qualified'] == 1
        assert len(response.context['frozen_tabs']) == 3
        assert b'<script>company</script>' not in response.content
        if tab == 'pending':
            assert b'Evaluation in flight' in response.content and b'Waiting for evaluation' in response.content
    assert list(OfficialCompanyAccountState.objects.order_by('pk').values()) == snapshots
    assert OfficialCompanyScan.objects.get().cursor == cursor
    assert not OfficialCompanyListIntent.objects.exists()
    assert owner_client.get('/admin/official-accounts/frozen-run', {'tab': 'unknown'}).context['frozen_run']['tab'] == 'newly'


def test_frozen_page_search_pagination_and_query_bounds(owner_client):
    from core.official_company_requalification import initialize_cohort
    from core.official_company_requalification_admin import frozen_run_report
    from tests.test_official_company_requalification import manifest, state

    candidates = [state(98200 + index) for index in range(53)]
    initialize_cohort(manifest(candidates))
    with CaptureQueriesContext(connection) as queries:
        report = frozen_run_report(tab='pending')
    assert len(queries) <= 4 and len(report['rows']) == 50 and report['page'].paginator.count == 53
    response = owner_client.get('/admin/official-accounts/frozen-run', {'tab': 'pending', 'page': 2, 'locale': 'ja'})
    assert len(response.context['frozen_run']['rows']) == 3
    assert 'tab=pending' in response.context['previous_url'] and 'locale=ja' in response.context['previous_url']
    for tab in response.context['frozen_tabs']:
        assert tab['url'].count('tab=') == 1 and 'page=1' in tab['url']
    matched = owner_client.get('/admin/official-accounts/frozen-run', {'tab': 'pending', 'q': '@company_98252'})
    assert [row['state_id'] for row in matched.context['frozen_run']['rows']] == [candidates[-1].pk]
    escaped = owner_client.get('/admin/official-accounts/frozen-run', {'tab': 'pending', 'q': '"><script>alert(1)</script>'})
    assert b'<script>alert(1)</script>' not in escaped.content
    assert not escaped.context['frozen_run']['rows']


def test_frozen_page_keeps_admin_auth_and_handles_uninitialized_run(owner_client):
    path = '/admin/official-accounts/frozen-run'
    assert Client().get(path).status_code == 302
    ordinary = Client()
    ordinary.force_login(get_user_model().objects.create_user(username='frozen-ordinary'))
    assert ordinary.get(path).status_code == 403
    response = owner_client.get(path, {'locale': 'en'})
    assert response.status_code == 200 and response.context['frozen_run']['summary'] is None
    assert b'has not been initialized' in response.content
