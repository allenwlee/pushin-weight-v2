"""The Pulse release link opens a chart for that release."""
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlsplit

import pytest
from django.core.cache.backends.locmem import LocMemCache
from playwright.sync_api import sync_playwright

from tests.test_event_dossiers import dossier
from tests.test_geolocation_access import (
    serving_login,  # noqa: F401 -- production-style PostgreSQL role
)


@pytest.fixture
def pulse_live_server(settings, request):
    settings.SECURE_SSL_REDIRECT = False
    return request.getfixturevalue("live_server")


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_release_card_opens_its_chart_and_pending_release_stays_pending(
    pulse_live_server, settings, monkeypatch, tmp_path
):
    from monitor import single_brand_chart

    settings.SECURE_SSL_REDIRECT = False
    monkeypatch.setattr(single_brand_chart, "cache", LocMemCache("pulse-release", {}))
    monkeypatch.setattr(single_brand_chart, "_CHART_BUILD_INTERVAL_SECONDS", 0)
    from tests.test_release_chart_handoff import confirmed

    product, event, _, _ = confirmed(date(2026, 9, 10))
    from core.models import Post, PostBrand

    for day in (0, 7):
        for index in range(1 + day // 7):
            post = Post.objects.create(
                tweet_id=f"pulse-chart-example-{day}-{index}",
                created_at=datetime(2026, 9, 10, tzinfo=UTC) + timedelta(days=day),
            )
            PostBrand.objects.create(post=post, brand=product.brand)
    pending = dossier("pulse-chart-pending")
    with sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1200, "height": 900})

        def local_only(route):
            if urlsplit(route.request.url).hostname != urlsplit(pulse_live_server.url).hostname:
                route.abort()
            else:
                route.continue_()

        chart_requests = []
        page.on("request", lambda request: chart_requests.append(request.url)
                if "/general/chart/?" in request.url else None)
        page.route("**/*", local_only)
        page.goto(f"{pulse_live_server.url}/pulse?locale=en", wait_until="networkidle")
        assert chart_requests == []
        assert page.locator("#ce-live-pulse").count() == 0
        card = page.locator(f'[data-pulse-event="{event.pk}"]')
        assert card.count() == 1
        link = card.get_by_role("link", name="View chart")
        assert link.count() == 1
        with page.expect_response(
            lambda response: "/general/chart/?" in response.url
        ) as received:
            link.click()
        assert urlsplit(page.url).path == "/pulse"
        assert str(event.pk) in urlsplit(page.url).query
        assert len(chart_requests) == 1
        assert page.locator("[data-pulse-event]").count() >= 2
        assert page.locator("#ce-live-pulse").count() == 1
        response = received.value
        assert response.status == 200, response.text()
        result = response.json()
        assert result["product"]["key"] == str(product.product_key)
        assert result["product"]["release_date"] == "2026-09-10"
        assert result["product"]["anchor_source"] == "dossier-reviewed"
        assert result["product"]["milestone_kind"] == "announcement"
        counts = next(line for line in result["lines"] if line["key"] == "discussion:posts")
        assert product.brand_id in counts["label"]
        assert [
            int(point["raw"]) for point in counts["points"] if point["day"] in (0, 7)
        ] == [1, 2]
        page.locator("#ce-content").wait_for(state="visible")
        assert page.locator("#ce-title").inner_text() == "River"
        # Two stored count days cannot establish a complete reference week.
        assert page.locator("#ce-scale").count() == 1
        assert page.locator("#ce-scale").input_value() == "discussion:posts"
        assert page.evaluate("""() => Chart.getChart('ce-chart').isPluginEnabled('pulseReleaseDay')""")
        chart_data = page.evaluate("""() => Chart.getChart('ce-chart').data.datasets[0].data""")
        assert [value for value in chart_data if value is not None] == [1, 2]
        page.locator("#ce-scale").select_option("")
        assert page.locator("#ce-legend button").count() == 1  # this Product only has brand posts
        page.locator(".ce-details summary").click()
        assert "Product identifier unavailable" in page.locator("#ce-sources").inner_text()
        assert page.evaluate("Chart.getChart('ce-chart').data.datasets[0].data.every(v => v == null)")
        page.locator("#ce-scale").select_option("discussion:posts")
        assert page.locator("#ce-scale").input_value() == "discussion:posts"
        with page.expect_response(
            lambda response: "/general/chart/?" in response.url
        ) as refreshed:
            page.get_by_role("button", name="Update data").click()
        assert refreshed.value.status == 200
        assert f"release={event.pk}" in refreshed.value.url
        assert refreshed.value.json()["product"]["key"] == str(product.product_key)
        page.locator("#ce-content").wait_for(state="visible")
        page.screenshot(path=tmp_path / "pulse-release-chart.png", full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        canvas = page.locator("#ce-chart").bounding_box()
        assert canvas and 0 < canvas["width"] <= 390 and canvas["height"] > 0
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.locator("#ce-release").fill("2026-09-11")
        with page.expect_response(
            lambda response: "/general/chart/?" in response.url
        ) as changed:
            page.get_by_role("button", name="Update data").click()
        assert changed.value.status == 200
        assert "release_date=2026-09-11" in changed.value.url
        assert "release=" not in changed.value.url
        with page.expect_response(
            lambda response: "/general/chart/?" in response.url
        ) as pending_response:
            page.goto(f"{pulse_live_server.url}/pulse?release={pending.pk}&locale=en")
        assert pending_response.value.status == 400
        assert "pending product identity" in page.locator("#ce-status").inner_text()
        page.set_viewport_size({"width": 390, "height": 844})
        for locale, heading, pending_text in (
            ("ja", "リリースチャート", "製品の特定"),
            ("zh-cn", "发布图表", "产品身份"),
        ):
            with page.expect_response(
                lambda response: "/general/chart/?" in response.url
            ) as localized_response:
                page.goto(
                    f"{pulse_live_server.url}/pulse?release={pending.pk}&locale={locale}"
                )
            assert localized_response.value.status == 400
            assert page.get_by_role("heading", name=heading).count() == 1
            assert pending_text in page.locator("#ce-status").inner_text()
            assert page.locator("#ce-live-pulse").count() == 1
            assert page.locator(".release-list").is_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        browser.close()


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(("subtype", "prior_date", "reviewed", "expected_day"), [
    ("new_release", None, False, "2026-11-12"),
    ("availability_update", None, False, None),
    ("availability_update", "2026-10-04", False, "2026-10-04"),
    ("availability_update", None, True, "2026-09-17"),
])
def test_current_p1_p2_writer_supplies_chart_release(client, monkeypatch, request, subtype, prior_date, reviewed, expected_day):
    import hashlib
    from unittest.mock import patch

    from django.db import connections

    from monitor import single_brand_chart

    monkeypatch.setattr(single_brand_chart, "cache", LocMemCache("pulse-p2-writer", {}))
    monkeypatch.setattr(single_brand_chart, "_CHART_BUILD_INTERVAL_SECONDS", 0)

    from core.models import (
        Account,
        Brand,
        BrandAccount,
        Post,
        PostBrandProduct,
        Product,
        Role,
    )
    from core.product_identity import resolve_saved_release_finding
    from core.product_release_dossiers import persist_classified_release_findings
    from tests.test_pulse_finding_persistence import finding

    role, _ = Role.objects.get_or_create(key="official")
    brand = Brand.objects.create(nickname="pulse-chart-publisher")
    account = Account.objects.create(author_id="3317990132", handle="chartfixture")
    BrandAccount.objects.create(brand=brand, account=account, role=role)
    text = "We released River Alpha on November 12."
    if subtype == "availability_update":
        text = "River Alpha is now available through our API."
        product = Product.objects.create(brand=brand, display_name="River Alpha")
    if prior_date:
        Post.objects.create(tweet_id="pulse-chart-history", author=account, text="Introducing River Alpha: our newest model.",
                            created_at=datetime.fromisoformat(prior_date).replace(tzinfo=UTC))
    post = Post.objects.create(tweet_id="pulse-chart-p2", author=account, text=text,
                               created_at=datetime(2026, 11, 12, tzinfo=UTC))
    if subtype == "availability_update":
        PostBrandProduct.objects.create(post=post, brand=brand, product=product, observed_name=product.display_name,
                                        verification_policy_version="test", source_evidence={})
    item = finding(name="River Alpha", key=hashlib.sha256(post.pk.encode()).hexdigest())
    item["brand_id"] = brand.pk
    item["novelty"] = subtype
    if subtype == "availability_update":
        item["assertions"][0]["claim_kind"] = "availability"
    item["issuer_evidence"] = {
        "relation": "source_author",
        "source_locator": None,
        "source_excerpt": text,
        "observed_name": None,
    }
    item["assertions"][0].update(
        source_excerpt=text,
        assertion_text=text,
        effective_precision="day",
        effective_date="2026-11-12",
    )
    saved = persist_classified_release_findings(
        source={"kind": "post", "id": post.pk},
        revision_id="b" * 64,
        content_fingerprint=hashlib.sha256(text.encode()).hexdigest(),
        extraction_version="chart-producer-fixture-v1",
        findings=[item],
    )["findings"][0]
    result = resolve_saved_release_finding(claim_id=saved["anchor_claim_id"])
    assert result["status"] in ("created", "matched")
    from core.event_dossiers import ClaimDecision, ProductReleaseInput, add_claim
    from core.models import EventDossier, EventDossierClaim
    from core.pulse_readers import release_page
    from monitor.pulse_views import _card
    from tests.test_event_dossiers import claim, review

    if subtype == "new_release":
        # A stale date on the same source is neither the current finding nor its Product.
        add_claim(saved["source_id"], claim_kind="source_stated_release", scope_key="retired-milestone",
                  assertion_text="Old model release", source_excerpt="Former model", effective_precision="day",
                  effective_date=date(2025, 9, 9), extraction_version="retired-v1")
        from tests.test_release_chart_handoff import confirmed
        other_product, other, _, _ = confirmed(date(2026, 11, 11))
        add_claim(saved["source_id"], claim_kind="release_context", scope_key="pulse-self-identity-v1:" + "d" * 64,
                  assertion_text="Older source identity", source_excerpt="Former model",
                  extraction_version="pulse-product-identity-v1", reported_product_id=other_product.pk)
    if reviewed:
        event = EventDossier.objects.get(pk=saved["dossier_id"])
        anchor = EventDossierClaim.objects.get(pk=saved["anchor_claim_id"])
        prior = claim(event, "reviewed-source", effective_precision="day", effective_date=date.fromisoformat(expected_day))
        review(event, prior, review_state="confirmed",
               product_release=ProductReleaseInput(observed_name=product.display_name,
                                                   product_key=product.product_key, disclosure_state="announced"),
               claims=[ClaimDecision(anchor.pk, "accepted", "Access update"), ClaimDecision(prior.pk, "accepted", "Separate launch")])
    if prior_date:
        from core.product_identity import reconcile_product_release_events

        reconcile_product_release_events(claim_id=saved["anchor_claim_id"], candidate_limit=25, claim_limit=50,
                                         max_merges=4, max_seconds=5)
    serving, *_ = request.getfixturevalue("serving_login")
    with patch.object(connections["default"], "connection", serving):
        assert not serving.execute(
            "SELECT has_column_privilege(current_user, 'collection_evidence_archives', 'body', 'SELECT')"
        ).fetchone()[0]
        response = client.get("/general/chart/", {"release": saved["dossier_id"]}, secure=True)
        page = release_page(limit=1)
        row = page["entries"][0]
        assert row["id"] == saved["dossier_id"]
        if subtype == "new_release":
            assert release_page(cursor=page["next_cursor"], limit=1)["entries"][0]["id"] == str(other.pk)
            assert row["product_key"] == result["product_key"] and not row["identity_conflict"]
        assert row["timeline_date"] == (date.fromisoformat(expected_day) if expected_day else None)
        assert bool(_card(row)["can_open_chart"]) is bool(expected_day)
    if expected_day is None:
        assert response.status_code == 400
        assert response.json()["code"] == "release_pending"
        return
    assert response.status_code == 200, response.content
    assert response.json()["product"]["key"] == result["product_key"]
    assert response.json()["product"]["release_date"] == expected_day
    assert response.json()["product"]["anchor_source"] == ("dossier-reviewed" if reviewed else "p2-qualified")
    assert response.json()["product"]["milestone_kind"] == "announcement"
    if subtype == "new_release":
        from core.models import PostBrandClassificationJudgment
        from core.release_chart_handoff import resolve_release

        PostBrandClassificationJudgment.objects.create(
            brand=brand, post=post, stage="primary", revision_id="f" * 64, canonical_judgment={},
            validation_state="validated", changes_json={"release_output": {
                "schema": "pulse-classified-release-output-v1", "finding_keys": [],
            }},
        )
        rows = {r["id"]: r for r in release_page()["entries"]}
        assert rows[saved["dossier_id"]]["timeline_date"] is None
        with pytest.raises(ValueError, match="no unique qualified"):
            resolve_release(saved["dossier_id"])


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_serving_login_reads_product_measurement_from_selected_dossier(client, monkeypatch, request):
    from decimal import Decimal
    from unittest.mock import patch

    from django.db import connections

    from monitor import single_brand_chart
    from tests.test_benchmark_release_response import response_contract, seed
    from tests.test_release_chart_handoff import confirmed

    contract = response_contract()
    seed(contract)
    product = contract.mappings.get(source_id="hf").subject.product
    _, event, _, _ = confirmed(date(2026, 9, 10), product=product)
    monkeypatch.setattr(single_brand_chart, "cache", LocMemCache("restricted-measurement", {}))
    monkeypatch.setattr(single_brand_chart, "_CHART_BUILD_INTERVAL_SECONDS", 0)
    serving, *_ = request.getfixturevalue("serving_login")
    with patch.object(connections["default"], "connection", serving):
        result = client.get("/general/chart/", {"release": event.pk}, secure=True)
    assert result.status_code == 200, result.content
    line = next(line for line in result.json()["lines"] if line["key"] == "hf:downloads")
    points = {point["date"]: point["raw"] for point in line["points"]}
    assert Decimal(points["2026-09-09"]) == 110
    assert points["2026-09-19"] is None
