import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext

from core.models import PostSynthesisDemand
from tests.general_helpers import classified_post, saved_commentary

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def test_pro_links_to_the_additive_general_page(client):
    response = client.get("/", secure=True)
    assert response.status_code == 200
    assert 'data-general-link' in response.content.decode()
    assert 'href="/general/?lang=' in response.content.decode()
    assert client.get("/general/?lang=en", secure=True).status_code == 200


def test_general_route_exposes_its_actual_deployment_revision(client, monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", "d" * 40)
    response = client.get("/general/?lang=en", secure=True)
    assert response["X-Bridgewright-Revision"] == "d" * 40


def test_general_is_anonymous_server_rendered_and_feed_matches_its_projection(client):
    for index, category in enumerate(
        ("events", "opportunities", "job_listings", "personnel_changes")
    ):
        saved_commentary(classified_post(str(5100 + index), category))
    with CaptureQueriesContext(connection) as queries:
        response = client.get("/general/?lang=en", secure=True)
    assert response.status_code == 200
    body = response.content.decode()
    for section in ("calendar", "free", "jobs", "moving"):
        assert f'id="{section}"' in body
        payload = client.get(
            f"/general/feed/?section={section}&lang=en", secure=True
        ).json()
        assert len(payload["items"]) == 1
        assert payload["items"][0]["url"] in body
        assert payload["items"][0]["commentary"]["text"] in body
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
