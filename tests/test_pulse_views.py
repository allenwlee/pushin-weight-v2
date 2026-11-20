"""Pulse's actual routes keep pending discoveries and operator controls honest."""

import hashlib
import json
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.middleware.csrf import get_token
from django.test import Client, RequestFactory
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django.utils.html import escape

from core.collection_capture import archive_document
from core.event_dossiers import (
    ClaimDecision,
    ProductReleaseInput,
    add_claim,
    attach_source,
    complete_review,
    create_dossier,
    identity_key,
)
from core.models import (
    Brand,
    BrandCompany,
    CollectionObservation,
    CollectionRun,
    Company,
    CompanyLabel,
    DataSource,
    Post,
    Product,
    ProductType,
    ReleaseMaturity,
)
from tests.collection_fixtures import evidence_job
from tests.test_pulse_readers import (
    historical_product,
    pending_release,
    reviewed_release,
)

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


@pytest.fixture(autouse=True)
def local_requests(settings):
    settings.SECURE_SSL_REDIRECT = False


def identity_evidence_release(kind):
    """Saved self-identity and lineage claims use their existing writer conventions."""
    observed_name = "Observed child release" if kind == "lineage" else "Reported product"
    event = pending_release("route-" + kind, observed_name)
    category, _ = ProductType.objects.get_or_create(code="agent")
    brand = Brand.objects.create(nickname=kind + "-brand", display_name="Reported publisher")
    company = Company.objects.create(nickname=kind + "-company")
    CompanyLabel.objects.create(company=company, locale_id="und", label="Reported owner")
    BrandCompany.objects.create(brand=brand, company=company)
    product = Product.objects.create(display_name="Reported product", brand=brand, product_type=category)
    is_lineage = kind == "lineage"
    claim = add_claim(
        event.sources.get().pk, claim_kind="release_context",
        scope_key="hf_base_product:fixture" if is_lineage else "github_named_product:123",
        assertion_text="Source identity evidence", source_excerpt="Source identity evidence",
        extraction_version="hf-base-product-v1" if is_lineage else "github-named-product-v1",
        reported_product_id=product.pk,
    )
    if kind == "rejected":
        issuer = Company.objects.create(nickname="reviewed-issuer")
        CompanyLabel.objects.create(company=issuer, locale_id="und", label="Reviewed issuer")
        complete_review(
            event.pk, expected_current_review_id=None, display_title="Unresolved release",
            review_state="unresolved", evidence_cutoff_at=timezone.now(),
            method_version="route-fixture", actor="fixture", reason="Wrong product rejected",
            claims=[ClaimDecision(claim.pk, "rejected", "Wrong product")],
            product_release=ProductReleaseInput(
                observed_name="Reviewed release", release_issuer_company_id=issuer.pk,
            ),
        )
    return event


def saved_category_release(key, categories):
    """Store synthetic P1-shaped finding packets, without importing a pending writer."""
    event = create_dossier(event_kind="product_release", identity_key=identity_key("category-route", key))
    post = Post.objects.create(tweet_id=key, text="Saved category release is available.")
    source = attach_source(event.pk, post_id=post.pk)
    for index, category in enumerate(categories):
        finding_key = hashlib.sha256(f"{key}-{index}".encode()).hexdigest()
        revision_id = hashlib.sha256(f"revision-{key}-{index}".encode()).hexdigest()
        packet = {
            "schema": "pulse-release-intake-v1",
            "source": {"kind": "post", "id": post.pk},
            "revision_id": revision_id,
            "content_fingerprint": hashlib.sha256(post.text.encode()).hexdigest(),
            "extraction_version": "compressed8-pulse-content-v1",
            "finding": {
                "finding_key": finding_key, "observed_name": "Saved category release",
                "category": category, "novelty": "new_release", "version": None,
                "variant": None, "brand_id": None, "brand_candidate_id": None,
                "candidate_repo_id": None,
                "assertions": [{
                    "claim_kind": "availability", "assertion_text": post.text,
                    "source_excerpt": post.text, "source_locator": None,
                    "access_channel": "weights", "effective_precision": "unknown",
                    "effective_at": None, "effective_date": None,
                    "effective_month": None, "effective_year": None,
                    "event_timezone": None, "not_after": None, "not_before": None,
                }],
            },
        }
        archive = archive_document(
            json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode(),
            encoding="selected-json-canonical-v1", capture_kind="product_release_intake",
        )
        add_claim(
            source.pk, claim_kind="release_report", scope_key=f"pulse-finding-v1:{finding_key}",
            assertion_text="Saved category release", source_excerpt=post.text,
            extraction_version=f"pulse-classified-findings-v1:{revision_id}",
            source_archive_id=archive.pk,
            release_maturity_id=ReleaseMaturity.objects.get(code="unknown").pk,
        )
    return event


def test_pulse_real_route_includes_dossier_with_no_review_or_identity(client):
    event = create_dossier(event_kind="product_release", identity_key=identity_key("pulse-test", "pending"))
    post = Post.objects.create(tweet_id="pulse-pending", text="A source discussing a release")
    attach_source(event.pk, post_id=post.pk)
    with CaptureQueriesContext(connection) as queries, patch(
        "requests.sessions.Session.request", side_effect=AssertionError("Page fetched a provider")
    ), patch("httpx.Client.send", side_effect=AssertionError("Page fetched a provider")):
        response = client.get("/pulse?locale=en")
    assert response.status_code == 200
    html = response.content.decode()
    assert str(event.pk) in html
    assert "Release candidate with no linked product name" in html and "Category pending" in html
    assert "No saved P1 decision for this post" in html
    assert "A source discussing a release" in html
    assert f"/pulse/{event.pk}/sources" in html
    unexpected = [query["sql"] for query in queries if not query["sql"].lstrip().upper().startswith("SELECT")]
    assert unexpected == []


@pytest.mark.parametrize("locale,title", [("en", "Release discoveries"), ("zh_hans", "发布动态"), ("ja", "リリースの発見")])
def test_pulse_empty_state_and_locale(client, locale, title):
    response = client.get("/pulse", {"locale": locale})
    assert response.status_code == 200
    assert title in response.content.decode()
    assert response.context["entries"] == []
    assert response.context["read_error"] is False


def test_pulse_slash_redirect_and_invalid_cursor(client):
    response = client.get("/pulse/?locale=en")
    assert response.status_code == 301 and response["Location"] == "/pulse?locale=en"
    assert client.get("/pulse?cursor=bad&locale=en").status_code == 400


def test_pulse_read_failure_is_not_empty_success(client):
    from django.db import OperationalError
    with patch("monitor.pulse_views.release_page", side_effect=OperationalError("private database details")):
        response = client.get("/pulse?locale=en")
    assert response.status_code == 503
    html = response.content.decode()
    assert "temporarily unavailable" in html
    assert "No release discoveries" not in html
    assert "private database details" not in html


@pytest.mark.parametrize("kind", ["rejected", "lineage", "reported"])
def test_real_route_separates_reviewed_identity_from_source_claims(client, kind):
    event = identity_evidence_release(kind)
    response = client.get("/pulse?locale=en")
    assert response.status_code == 200
    html = response.content.decode()
    assert f'data-pulse-event="{event.pk}"' in html
    if kind == "reported":
        assert "Reported product" in html
        assert "Reported publisher" in html and "Reported owner" in html
        assert "Reported product identity — awaiting review" in html
        assert "Product identity pending" not in html
    else:
        assert "Product identity pending" in html and "Category pending" in html
        assert "<h2>Reported product</h2>" not in html and "Reported publisher" not in html
        assert "Reported owner" not in html
        if kind == "rejected":
            assert "Reviewed release" in html and "Reviewed issuer" in html
        else:
            assert "Observed child release" in html


@pytest.mark.parametrize("locale,label,pending", [
    ("en", "Legacy category: model", "Category pending"),
    ("zh_hans", "旧版类别：model", "类别待确认"),
    ("ja", "旧分類: model", "分類未確定"),
])
def test_real_route_renders_legacy_category_in_each_locale(client, locale, label, pending):
    product = historical_product(display_name="Legacy product")
    reviewed_release("legacy-category", product=product)
    response = client.get("/pulse", {"locale": locale})
    assert response.status_code == 200
    html = response.content.decode()
    assert label in html
    assert pending not in html


@pytest.mark.parametrize("locale,category,identity", [
    ("en", "Reported category: Language model", "Product identity pending"),
    ("zh_hans", "来源报告的类别：语言模型", "产品身份待确认"),
    ("ja", "報告された分類: 言語モデル", "製品の同一性は未確定"),
])
def test_real_route_reports_saved_category_before_product_identity(client, locale, category, identity):
    event = saved_category_release("saved-category", ["model-llm"])
    with CaptureQueriesContext(connection) as queries, patch(
        "requests.sessions.Session.request", side_effect=AssertionError("Page fetched a provider")
    ), patch("httpx.Client.send", side_effect=AssertionError("Page fetched a provider")):
        response = client.get("/pulse", {"locale": locale})
    assert response.status_code == 200
    html = response.content.decode()
    assert f'data-pulse-event="{event.pk}"' in html
    assert category in html and identity in html
    assert response.context["entries"][0]["product_key"] is None
    assert not Product.objects.exists()
    assert all(query["sql"].lstrip().upper().startswith("SELECT") for query in queries)


@pytest.mark.parametrize("categories,conflict", [(["model-llm", "agent"], True), (["invalid-category"], False)])
@pytest.mark.parametrize("locale,pending,incomplete,conflicting", [
    ("en", "Category pending", "Category evidence is incomplete.", "Sources report different categories: Agent / Language model."),
    ("zh_hans", "类别待确认", "类别证据不完整。", "来源报告了不同的类别：智能体 / 语言模型。"),
    ("ja", "分類未確定", "分類の根拠が不完全です。", "情報源ごとに報告された分類が異なります: エージェント / 言語モデル。"),
])
def test_real_route_keeps_conflicting_or_invalid_saved_category_pending(
    client, categories, conflict, locale, pending, incomplete, conflicting,
):
    saved_category_release("uncertain-category", categories)
    response = client.get("/pulse", {"locale": locale})
    assert response.status_code == 200
    html = response.content.decode()
    assert pending in html
    assert (incomplete in html) is (not conflict)
    assert (conflicting in html) is conflict
    assert response.context["entries"][0]["category"] is None


def test_related_sources_keep_claimless_posts_and_reject_other_event_kinds(client):
    event = create_dossier(event_kind="product_release", identity_key=identity_key("pulse-test", "sources"))
    post = Post.objects.create(tweet_id="later-post", text="Later discussion")
    attach_source(event.pk, post_id=post.pk)
    response = client.get(f"/pulse/{event.pk}/sources?locale=en")
    assert response.status_code == 200
    assert "/posts/later-post/" in response.content.decode()
    other = create_dossier(event_kind="personnel_change", identity_key=identity_key("pulse-test", "other"))
    assert client.get(f"/pulse/{other.pk}/sources").status_code == 404


def test_related_sources_render_observation_label_url_and_count_without_post_link(client):
    event = create_dossier(event_kind="product_release", identity_key=identity_key("pulse-test", "observation"))
    source_url = "https://github.com/fixture/observed/releases"
    DataSource.objects.create(id="pulse-observation", name="Saved fixture", source_type="model_adoption")
    run = CollectionRun.objects.create(
        job=evidence_job(source_id="pulse-observation"), ingestion_key="a" * 64,
        source_url=source_url, status="success", completed_at=timezone.now(),
    )
    observation = CollectionObservation.objects.create(
        run=run, source_identifier="fixture/observed", source_subject_kind="repository",
        observation_key="b" * 64,
    )
    source = attach_source(event.pk, observation_id=observation.pk)
    feed = client.get("/pulse?locale=en")
    assert feed.status_code == 200
    assert '<span class="count">1</span>' in feed.content.decode()
    response = client.get(f"/pulse/{event.pk}/sources?locale=en")
    assert response.status_code == 200
    html = response.content.decode()
    assert html.count("data-pulse-source=") == 1
    assert f'data-pulse-source="{source.pk}"' in html
    assert "fixture/observed" in html and f'href="{source_url}"' in html
    assert "Stored post" not in html and "/posts/" not in html


def test_control_requires_authenticated_owner_staff_and_post():
    client = Client(enforce_csrf_checks=True)
    assert client.post("/admin/pulse/control").status_code in {302, 403}
    user = get_user_model().objects.create_user(username="ordinary")
    client.force_login(user)
    assert client.get("/admin/pulse/control").status_code in {403, 405}
    assert client.post("/admin/pulse/control").status_code == 403
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    assert client.post("/admin/pulse/control").status_code == 403
    assert client.get("/admin/pulse/control").status_code == 405


@pytest.mark.parametrize("locale,language,message", [
    ("en", "en", "Pulse control requires owner or staff access."),
    ("zh_hans", "zh-hans", "Pulse 控制需要所有者或管理人员权限。"),
    ("ja", "ja", "Pulse の操作には所有者またはスタッフ権限が必要です。"),
])
def test_control_rejects_ordinary_user_with_valid_csrf_without_changing_file(settings, tmp_path, locale, language, message):
    from monitor import pulse_control

    settings.PULSE_CONTROL_DIRECTORY = str(tmp_path)
    settings.PRODUCT_REVIEW_OWNER_EMAILS = {"owner@example.com"}
    pulse_control.initialize(directory=tmp_path, state="running", actor="fixture", reason="Local test")
    before = (tmp_path / "pulse-control.json").read_bytes()
    client = Client(enforce_csrf_checks=True)
    client.force_login(get_user_model().objects.create_user(username="ordinary-valid-csrf", email="ordinary@example.com"))
    before_session = dict(client.session)
    token = get_token(RequestFactory().get("/"))
    client.cookies[settings.CSRF_COOKIE_NAME] = token
    with CaptureQueriesContext(connection) as queries:
        response = client.post("/admin/pulse/control?locale=" + locale, {
            "state": "stopped", "revision": 1, "reason": "Unauthorized stop", "csrfmiddlewaretoken": token,
        })
    assert response.status_code == 403
    assert response.content.decode() == message
    assert response["Content-Language"] == language
    assert dict(client.session) == before_session
    assert all(query["sql"].lstrip().upper().startswith("SELECT") for query in queries)
    assert (tmp_path / "pulse-control.json").read_bytes() == before


def test_allowlisted_nonstaff_owner_can_request_control_with_valid_csrf(settings, tmp_path):
    from monitor import pulse_control

    settings.PULSE_CONTROL_DIRECTORY = str(tmp_path)
    settings.PRODUCT_REVIEW_OWNER_EMAILS = {"owner@example.com"}
    pulse_control.initialize(directory=tmp_path, state="running", actor="fixture", reason="Local test")
    client = Client(enforce_csrf_checks=True)
    user = get_user_model().objects.create_user(username="owner", email="owner@example.com", is_staff=False)
    client.force_login(user)
    assert client.get("/admin?locale=en").status_code == 200
    token = client.cookies[settings.CSRF_COOKIE_NAME].value
    response = client.post("/admin/pulse/control?locale=en", {
        "state": "stopped", "revision": 1, "reason": "Owner requested stop", "csrfmiddlewaretoken": token,
    })
    assert response.status_code == 302
    state = pulse_control.read_status()
    assert state["status"] == "stop_requested"
    assert state["desired_revision"] == 2
    assert state["requested_by"] == "owner@example.com"


def test_control_posts_use_real_revisioned_file_without_acknowledging(settings, tmp_path):
    from monitor import pulse_control

    settings.PULSE_CONTROL_DIRECTORY = str(tmp_path)
    pulse_control.initialize(directory=tmp_path, state="running", actor="fixture", reason="Local test")
    pulse_control.acknowledge(1, boundary="fixture boundary")
    client = Client()
    user = get_user_model().objects.create_user(username="operator", is_staff=True)
    client.force_login(user)
    before = (tmp_path / "pulse-control.json").read_bytes()
    assert client.get("/admin?locale=en").status_code == 200
    assert (tmp_path / "pulse-control.json").read_bytes() == before
    url = "/admin/pulse/control?locale=en"
    assert client.post(url, {"state": "stopped", "revision": 1, "reason": ""}).status_code == 400
    assert (tmp_path / "pulse-control.json").read_bytes() == before
    response = client.post(url, {"state": "stopped", "revision": 1, "reason": "Investigate an identity"})
    assert response.status_code == 302
    state = pulse_control.read_status()
    assert (state["status"], state["desired_revision"], state["acknowledged_revision"]) == ("stop_requested", 2, 1)
    requested = (tmp_path / "pulse-control.json").read_bytes()
    assert client.post(url, {"state": "running", "revision": 1, "reason": "Stale browser"}).status_code == 409
    assert (tmp_path / "pulse-control.json").read_bytes() == requested
    (tmp_path / "pulse-control.json").write_text("invalid")
    assert client.post(url, {"state": "running", "revision": 2, "reason": "Cannot resume"}).status_code == 503


def test_admin_unavailable_storage_preserves_existing_review_page(settings, client):
    settings.PULSE_CONTROL_DIRECTORY = ""
    client.force_login(get_user_model().objects.create_user(username="staff", is_staff=True))
    response = client.get("/admin?locale=en")
    assert response.status_code == 200
    html = response.content.decode()
    assert 'data-pulse-control-status="unavailable"' in html
    assert 'action="/admin/pulse/control' not in html
    assert "Product review" in html or "Product Review" in html


@pytest.mark.parametrize("locale,language,message", [
    ("en", "en", "Pulse processing needs investigation."),
    ("zh_hans", "zh-hans", "Pulse 处理需要调查。"),
    ("ja", "ja", "Pulse の処理状況を調査する必要があります。"),
])
def test_admin_localizes_known_processing_errors_without_rewriting_custom_diagnostics(
    settings, client, tmp_path, locale, language, message,
):
    from monitor import pulse_control

    settings.PULSE_CONTROL_DIRECTORY = str(tmp_path)
    pulse_control.initialize(directory=tmp_path, state="running", actor="fixture", reason="Locale fixture")
    fixed = "Pulse processing needs investigation."
    custom = "Operator note <script>window.unexpected=true</script>"
    cases = [
        ("identity", "identity_processing_error", fixed, True),
        ("publication", "classification_publication_conflict", fixed, True),
        ("classification", "classification_transport_error", fixed, True),
        ("classification", "classification_budget_deferred", fixed, True),
        ("classification", "classification_timeout", fixed, True),
        ("classification", "classification_invalid_finding", fixed, True),
        ("identity", "identity_processing_error", custom, False),
        ("classification", "classification_timeout", custom, False),
        ("identity", "identity_processing_error", fixed + " Operator note.", False),
        ("publication", "identity_processing_error", fixed, False),
        ("identity", "custom_code", fixed, False),
        ("identity", "classification_timeout", fixed, False),
    ]
    for stage, code, original_message, _ in cases:
        pulse_control.record_diagnostic(stage=stage, code=code, message=original_message)
    before = (tmp_path / "pulse-control.json").read_bytes()
    client.force_login(get_user_model().objects.create_user(username="diagnostic-locale-staff", is_staff=True))
    response = client.get("/admin", {"locale": locale})
    assert response.status_code == 200
    assert response["Content-Language"] == language
    diagnostics = response.context["pulse_control"]["diagnostics"]
    assert len(diagnostics) == len(cases)
    for diagnostic, (stage, code, original_message, translated) in zip(diagnostics, cases, strict=True):
        assert (diagnostic["stage"], diagnostic["code"], diagnostic["message"]) == (stage, code, original_message)
        assert diagnostic["display_message"] == (message if translated else original_message)
    html = response.content.decode()
    assert message in html and escape(custom) in html
    assert "<script>window.unexpected=true</script>" not in html
    assert (tmp_path / "pulse-control.json").read_bytes() == before


@pytest.mark.parametrize("contents", ["invalid json", "[" * 10_000 + "]" * 10_000], ids=["invalid", "deeply-nested"])
def test_admin_corrupt_storage_preserves_existing_review_page(settings, client, tmp_path, contents):
    settings.PULSE_CONTROL_DIRECTORY = str(tmp_path)
    control_file = tmp_path / "pulse-control.json"
    control_file.write_text(contents)
    before = control_file.read_bytes()
    client.force_login(get_user_model().objects.create_user(username="corrupt-control-staff", is_staff=True))
    response = client.get("/admin?locale=en")
    assert response.status_code == 200
    html = response.content.decode()
    assert 'data-pulse-control-status="unavailable"' in html
    assert "Control unavailable" in html
    assert "Product review" in html or "Product Review" in html
    assert 'action="/admin/pulse/control' not in html
    assert control_file.read_bytes() == before


@pytest.mark.parametrize("post_id,link_expected", [("legacy/imported-id", False), ("normal-post", True)])
def test_valid_diagnostic_reference_cannot_crash_admin(settings, client, tmp_path, post_id, link_expected):
    from monitor import pulse_control

    settings.PULSE_CONTROL_DIRECTORY = str(tmp_path)
    pulse_control.initialize(directory=tmp_path, state="running", actor="fixture", reason="Local probe")
    pulse_control.record_diagnostic(
        stage="identity", code="test", message="Unusual <script>reference</script>",
        references={"post_id": post_id},
    )
    client.force_login(get_user_model().objects.create_user(username="probe-staff", is_staff=True))
    response = client.get("/admin?locale=en")
    assert response.status_code == 200
    html = response.content.decode()
    assert post_id in html
    assert "Unusual &lt;script&gt;reference&lt;/script&gt;" in html
    assert (f'href="/posts/{post_id}/?locale=en"' in html) is link_expected
    assert "Product review" in html or "Product Review" in html


def test_pulse_renders_a_confirmed_products_family_and_keeps_pending_visible(client):
    from core.measurement_taxonomy import configure_taxonomy
    from tests.test_pulse_readers import pulse_identity_release

    event, product, _ = pulse_identity_release("view-family")
    key = str(product.product_key)
    configure_taxonomy({
        "reviewed_by": "test",
        "subjects": [{"kind": "product", "key": key}],
        "groups": [{"key": "family:view", "name": "BotPsy", "group_kind": "family", "include": [key]}],
    })
    pending_release("view-pending")
    response = client.get("/pulse?locale=en")
    assert response.status_code == 200
    html = response.content.decode()
    assert "BotPsy" in html
    assert str(event.pk) in html
    assert "Product identity pending" in html
