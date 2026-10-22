import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext

from core.models import (
    Event,
    Opportunity,
    OpportunityType,
    PostSynthesisDemand,
    TimeZone,
)
from tests.general_helpers import NOW, classified_post, saved_commentary

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


@pytest.mark.parametrize("locale", ["en", "zh_cn", "zh_hans", "ja"])
def test_home_omits_general_navigation_but_direct_general_route_remains(client, locale):
    response = client.get(f"/?locale={locale}", secure=True)
    assert response.status_code == 200
    assert 'data-general-link' not in response.content.decode()
    assert 'href="/general/' not in response.content.decode()
    assert client.get("/general/?lang=en", secure=True).status_code == 200


def test_general_route_exposes_its_actual_deployment_revision(client, monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", "d" * 40)
    response = client.get("/general/?lang=en", secure=True)
    assert response["X-Bridgewright-Revision"] == "d" * 40


@pytest.mark.parametrize("locale", ["en", "zh_hans", "ja"])
@pytest.mark.parametrize(
    "zone,payload,reported_zone",
    [
        ("Asia/Tokyo", {}, "Asia/Tokyo"),
        (None, {"source_timezone": " Pacific Time "}, "Pacific Time"),
        (None, {}, None),
        ("UTC", {"source_timezone": None}, None),
    ],
)
def test_general_is_anonymous_server_rendered_and_feed_matches_its_projection(
    client, monkeypatch, locale, zone, payload, reported_zone
):
    posts = {}
    for index, category in enumerate(
        ("events", "opportunities", "job_listings", "personnel_changes")
    ):
        posts[category] = classified_post(str(5100 + index), category)
        saved_commentary(posts[category])
    if zone:
        TimeZone.objects.get_or_create(code=zone)
    shared = {
        "brand_id": "qwen",
        "source_timezone_reference_id": zone,
        "raw_payload": payload,
        "first_seen_at": NOW,
        "last_seen_at": NOW,
        "review_status": "confirmed",
    }
    Event.objects.create(
        **shared, source_post=posts["events"], title="Developer workshop",
        organizer_name="Qwen", event_identity="general-timezone-event",
    )
    Opportunity.objects.create(
        **shared, source_post=posts["opportunities"], sponsor_name="Qwen",
        opportunity_type_reference=OpportunityType.objects.get(code="free_credits"),
        action_type="apply", benefit_type="credits",
        benefit_text="Timezone credits", opportunity_identity="general-timezone-offer",
    )
    monkeypatch.setattr("monitor.general_views.timezone.now", lambda: NOW)
    with CaptureQueriesContext(connection) as queries:
        response = client.get(f"/general/?lang={locale}", secure=True)
    assert response.status_code == 200
    body = response.content.decode()
    for section in ("calendar", "free", "jobs", "moving"):
        assert f'id="{section}"' in body
        payload = client.get(
            f"/general/feed/?section={section}&lang={locale}", secure=True
        ).json()
        assert len(payload["items"]) == 1
        assert payload["items"][0]["url"] in body
        assert payload["items"][0]["commentary"]["text"] in body
        if section in {"calendar", "free"}:
            assert payload["items"][0]["facts"][0]["timezone"] == reported_zone
            assert response.context["panels"][section]["items"][0]["facts"][0]["timezone"] == reported_zone
    assert response.context["panels"]["calendar"]["items"][0]["facts"][0]["title"] == "Developer workshop"
    assert response.context["panels"]["free"]["items"][0]["facts"][0]["title"] == "Timezone credits"
    assert "/accounts/login/" in body and 'method="post"' not in body
    assert PostSynthesisDemand.objects.count() == 0
    assert not any(
        row["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        for row in queries
    )


@pytest.mark.parametrize(
    "query",
    [
        "section=invalid",
        "section=jobs&weights=invalid",
        "section=jobs&lang=fr",
        "section=jobs&limit=51",
        "section=jobs&cursor=modified",
        "section=jobs&brand=not-tracked",
    ],
)
def test_invalid_feed_selection_returns_400(client, query):
    assert client.get("/general/feed/?" + query, secure=True).status_code == 400


def test_weights_filter_before_pagination_and_settings_do_not_leak_between_accounts(
    client,
):
    classified_post("5201", brand="qwen")
    classified_post("5202", brand="claude")
    opened = client.get("/general/feed/?section=jobs&weights=open", secure=True).json()
    empty = client.get("/general/feed/?section=jobs&weights=none", secure=True).json()
    assert [item["id"] for item in opened["items"]] == ["5201"]
    assert empty["items"] == []
    for weights in ("closed", "both"):
        unavailable = client.get(f"/general/?weights={weights}", secure=True)
        assert unavailable.context["state"]["weights"] == "open"
        assert unavailable.context["initial_data"]["closed_weights_notice"]
        assert 'data-post-id="5202"' not in unavailable.content.decode()
    anon = client.get("/general/", secure=True)
    user = get_user_model().objects.create_user(
        username="g5-reader", email="reader@example.org"
    )
    client.force_login(user)
    signed_in = client.get("/general/", secure=True)
    assert anon.context["preferences_namespace"] == "anonymous"
    assert signed_in.context["preferences_namespace"].startswith("user-")
    body = signed_in.content.decode()
    assert (
        "/accounts/logout/" in body
        and 'method="post"' in body
        and 'name="csrfmiddlewaretoken"' in body
    )


@pytest.mark.parametrize(
    "locale,labels",
    [
        ("en", ["Calendar", "Free stuff", "Jobs", "Who’s moving"]),
        ("zh_hans", ["日历", "福利", "招聘", "人事动态"]),
        ("ja", ["カレンダー", "無料・特典", "求人", "人の動き"]),
    ],
)
def test_general_chrome_is_translated_through_the_actual_route(client, locale, labels):
    body = client.get(f"/general/?lang={locale}", secure=True).content.decode()
    for label in labels:
        assert label in body
