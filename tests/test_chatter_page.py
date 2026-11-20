"""The General-styled Chatter archive reads saved editions in publication order."""

from datetime import timedelta
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from core.models import OriginalContentText
from tests.test_chatter_chain import chain_config
from tests.test_chatter_pool_readers import published
from tests.test_graphics_publication import publication_case  # noqa: F401
from tests.test_graphics_readers import graphic_edition  # noqa: F401

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


@pytest.fixture
def page_config(monkeypatch):
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    cfg = chain_config().model_copy(update={"public_enabled": True})
    monkeypatch.setattr("monitor.editorial.views.load_editorial_config", lambda: cfg)
    return cfg


def test_chatter_archive_orders_publications_instead_of_featured_selection(
    client, page_config
):
    at = timezone.now()
    rows = [published("rest", str(990100 + number)) for number in range(3)]
    for row, age in zip(rows, (1, 0, 2), strict=True):
        OriginalContentText.objects.filter(pk=row.pk).update(
            created_at=at - timedelta(hours=age)
        )
    # The last inserted/featured story is oldest; it must not jump above newer copy.
    with CaptureQueriesContext(connection) as queries:
        response = client.get("/chatter/?lang=en", secure=True)
    assert response.status_code == 200
    assert [item["id"] for item in response.context["feed"]["items"]] == [
        str(row.public_id) for row in (rows[1], rows[0], rows[2])
    ]
    body = response.content.decode()
    assert (
        body.index(str(rows[1].public_id))
        < body.index(str(rows[0].public_id))
        < body.index(str(rows[2].public_id))
    )
    assert response.context["initial_data"]["feeds"] == {}
    assert "PRIVATE RAW EVIDENCE" not in body
    assert not any(
        query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        for query in queries
    )


def test_chatter_stable_pages_with_ties_keep_every_edition(client, page_config):
    at = timezone.now()
    rows = [published("rest", str(990200 + number)) for number in range(23)]
    OriginalContentText.objects.filter(pk__in=[row.pk for row in rows]).update(
        created_at=at
    )
    expected = sorted((str(row.public_id) for row in rows), reverse=True)
    with CaptureQueriesContext(connection) as queries:
        first = client.get("/chatter/?lang=en&timezone=ca", secure=True)
    assert first.status_code == 200
    assert len(queries) <= 15, [query["sql"] for query in queries]
    assert not any(
        query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        for query in queries
    )
    assert len(first.context["feed"]["items"]) == 20
    next_url = first.context["next_url"]
    assert parse_qs(urlsplit(next_url).query)["timezone"] == ["ca"]
    second = client.get(next_url, secure=True)
    actual = [
        item["id"]
        for item in first.context["feed"]["items"] + second.context["feed"]["items"]
    ]
    assert actual == expected and len(set(actual)) == 23
    assert second.context["next_url"] is None
    assert (
        "chartjs" not in first.content.decode()
        and "single-brand-chart.js" not in first.content.decode()
    )
    for changed in ({"group": "giant"}, {"source_lang": "ja"}):
        args = {"cursor": first.context["feed"]["next_cursor"], **changed}
        assert client.get("/chatter/", args, secure=True).status_code == 400


@pytest.mark.parametrize(
    "query",
    [
        "cursor=tampered",
        "track=pulse",
        "group=unknown",
        "source_lang=fr",
        "edition_lang=fr",
        "lang=fr",
        "audience=unknown",
    ],
)
def test_chatter_rejects_invalid_or_cross_track_selection(client, page_config, query):
    assert client.get("/chatter/?" + query, secure=True).status_code == 400


def test_chatter_pool_and_edition_language_are_independent(client, page_config):
    rest = published("rest", "990300")
    giant = published("giant", "990301")
    rest.headline = "REST STORY"
    rest.save(update_fields=["headline"])
    giant.headline = "GIANT STORY"
    giant.save(update_fields=["headline"])
    default = client.get("/chatter/", secure=True)
    assert default.context["pool_controls"]["source_lang"] == "en"
    assert default.context["pool_controls"]["group"] == "rest"
    assert b"REST STORY" in default.content and b"GIANT STORY" not in default.content
    fallback = client.get(
        "/chatter/?lang=ja&source_lang=en&group=giant&edition_lang=ja", secure=True
    )
    assert fallback.status_code == 200
    assert b"GIANT STORY" in fallback.content and b"REST STORY" not in fallback.content
    assert fallback.context["feed"]["requested_locale"] == "ja"
    assert fallback.context["feed"]["locale"] == "en"
    assert fallback.context["locale"] == "ja"
    assert fallback.context["pool_controls"] == {
        "source_lang": "en",
        "group": "giant",
        "edition_lang": "ja",
        "hidden": [("lang", "ja")],
    }
    empty = client.get("/chatter/?lang=ja", secure=True)
    assert empty.context["pool_controls"]["source_lang"] == "ja"
    assert empty.context["feed"]["items"] == []
    for option in fallback.context["settings_links"]["lang"]:
        assert option["url"].startswith("/chatter/?")
        assert "source_lang=en" in option["url"] and "group=giant" in option["url"]


def test_chatter_access_sources_escaping_and_drafts(
    client, page_config, monkeypatch, django_user_model
):
    from tests.test_general_editorial import published_story
    from tests.test_original_content_models import saved_text

    row = published("rest", "990400")
    row.headline = '<script>alert("unsafe")</script>'
    row.body = "Accepted published copy"
    row.save(update_fields=["headline", "body"])
    published_story("pulse")
    hidden = saved_text()
    hidden.headline = "UNPUBLISHED PRIVATE DRAFT"
    hidden.public_id = uuid4()
    hidden.save(update_fields=["headline", "public_id"])
    hidden.narrative.source_locale_id = "en"
    hidden.narrative.editorial_group = "rest"
    hidden.narrative.published_at = timezone.now()
    hidden.narrative.save(
        update_fields=["source_locale", "editorial_group", "published_at"]
    )
    assert hidden.narrative.status == "prepared"
    row.narrative.provenance = {
        **row.narrative.provenance,
        "evidence": {
            "sources": [
                {
                    "id": "990400",
                    "url": "https://x.com/i/status/990400",
                    "original_text": "PRIVATE RAW EVIDENCE",
                }
            ]
        },
    }
    row.narrative.save(update_fields=["provenance"])
    public = client.get("/chatter/", secure=True)
    body = public.content.decode()
    assert "&lt;script&gt;" in body and '<script>alert("unsafe")</script>' not in body
    assert (
        "UNPUBLISHED PRIVATE DRAFT" not in body and "pulse saved headline" not in body
    )
    assert "Accepted published copy" in body
    assert "PRIVATE RAW EVIDENCE" not in body
    assert f"edition={row.public_id}" in body
    for source in row.sources.all():
        assert source.url_snapshot in body
    assert public["Cache-Control"] == "private, no-store"
    assert public["X-Content-Type-Options"] == "nosniff"

    private_cfg = page_config.model_copy(update={"public_enabled": False})
    monkeypatch.setattr(
        "monitor.editorial.views.load_editorial_config", lambda: private_cfg
    )
    unavailable = client.get("/chatter/", secure=True)
    assert unavailable.status_code == 200
    assert b"Published stories are currently unavailable." in unavailable.content
    assert b"Accepted published copy" not in unavailable.content
    user = django_user_model.objects.create_user(
        username="chatter-reader", is_staff=False
    )
    client.force_login(user)
    assert (
        b"Accepted published copy" not in client.get("/chatter/", secure=True).content
    )
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    assert b"Accepted published copy" in client.get("/chatter/", secure=True).content


def test_chatter_legacy_publications_and_general_archive_link(
    client, page_config, monkeypatch
):
    from tests.test_general_editorial import published_story

    cfg = page_config.model_copy(
        update={"chatter": page_config.chatter.model_copy(update={"enabled": False})}
    )
    monkeypatch.setattr("monitor.editorial.views.load_editorial_config", lambda: cfg)
    text = published_story()
    response = client.get("/chatter/", secure=True)
    assert str(text.public_id) in response.content.decode()
    general = client.get("/general/", secure=True)
    assert 'href="/chatter/?track=chatter' in general.content.decode()
    assert 'href="/stories/?track=pulse' in general.content.decode()
    redirect = client.get("/chatter?lang=ja", secure=True)
    assert redirect.status_code == 301 and redirect["Location"] == "/chatter/?lang=ja"
    assert client.post("/chatter/", secure=True).status_code == 405


@pytest.mark.parametrize("video", [False, True])
def test_chatter_renders_saved_graphics_lazily(client, graphic_edition, video):  # noqa: F811
    from monitor.editorial.readers import edition_payload
    from tests.test_graphics_readers import _video

    edition, _still, _storage, cfg = graphic_edition
    if video:
        _video(graphic_edition)
    item = edition_payload(edition, cfg)
    response = client.get("/chatter/", secure=True)
    body = response.content.decode()
    assert response.status_code == 200 and item["asset"]["url"] in body
    assert (
        f'poster="{item["asset"]["poster"]}"' in body
        if video
        else 'loading="lazy"' in body
    )
    if video:
        assert 'preload="none"' in body and "playsinline" in body


@pytest.mark.parametrize(
    ("locale", "empty", "unavailable"),
    [
        (
            "en",
            "No published stories yet.",
            "Published stories are currently unavailable.",
        ),
        ("ja", "公開された記事はまだありません。", "公開記事は現在利用できません。"),
        ("zh_hans", "暂无已发布报道。", "已发布的文章暂时不可用。"),
    ],
)
def test_chatter_empty_and_unavailable_are_localized(
    client, page_config, monkeypatch, locale, empty, unavailable
):
    response = client.get("/chatter/", {"lang": locale}, secure=True)
    assert response.status_code == 200 and empty in response.content.decode()
    cfg = page_config.model_copy(update={"public_enabled": False})
    monkeypatch.setattr("monitor.editorial.views.load_editorial_config", lambda: cfg)
    response = client.get("/chatter/", {"lang": locale}, secure=True)
    assert response.status_code == 200 and unavailable in response.content.decode()


def test_empty_delayed_archive_does_not_claim_a_story_is_shown(
    client, page_config, monkeypatch
):
    cfg = page_config.model_copy(
        update={
            "chatter": page_config.chatter.model_copy(
                update={"activated_at": timezone.now() - timedelta(hours=4)}
            )
        }
    )
    monkeypatch.setattr("monitor.editorial.views.load_editorial_config", lambda: cfg)
    empty = client.get("/chatter/", secure=True)
    assert empty.status_code == 200 and empty.context["feed"]["delay"]["delayed"]
    assert b"No published stories yet." in empty.content
    assert b"The latest available story is shown." not in empty.content
    published("rest", "990901")
    populated = client.get("/chatter/", secure=True)
    assert b"The latest available story is shown." in populated.content


def test_chatter_continuation_pins_filters_independently_of_locale_cookie(
    client, page_config
):
    for number in range(21):
        published("rest", str(991000 + number))
    first = client.get("/chatter/", secure=True)
    next_url = first.context["next_url"]
    params = parse_qs(urlsplit(next_url).query)
    assert params["lang"] == params["source_lang"] == params["edition_lang"] == ["en"]
    assert params["group"] == ["rest"]
    client.cookies["locale"] = "ja"
    with CaptureQueriesContext(connection) as queries:
        second = client.get(next_url, secure=True)
    assert second.status_code == 200 and second.context["locale"] == "en"
    assert len(second.context["feed"]["items"]) == 1
    assert not any(
        query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        for query in queries
    )


@pytest.mark.parametrize("backend", ["shared", "legacy"])
def test_chatter_cursor_binds_requested_language_and_freezes_fallback(
    client, page_config, monkeypatch, backend
):
    from tests.test_editorial_views import edition

    if backend == "shared":
        rows = [published("rest", str(991100 + number)) for number in range(21)]
        query = "lang=en&source_lang=en&edition_lang=en"
    else:
        monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "legacy")
        monkeypatch.setenv("ORIGINAL_CONTENT_MIRROR", "false")
        cfg = page_config.model_copy(
            update={
                "chatter": page_config.chatter.model_copy(update={"enabled": False})
            }
        )
        monkeypatch.setattr(
            "monitor.editorial.views.load_editorial_config", lambda: cfg
        )
        rows = [edition("Saved legacy story " + str(number)) for number in range(21)]
        query = "lang=en"
    first = client.get("/chatter/?" + query, secure=True)
    changed = (
        first.context["next_url"].replace("edition_lang=en", "edition_lang=ja")
        if backend == "shared"
        else first.context["next_url"].replace("lang=en", "lang=ja")
    )
    assert client.get(changed, secure=True).status_code == 400
    fallback_query = (
        query.replace("edition_lang=en", "edition_lang=ja")
        if backend == "shared"
        else "lang=ja"
    )
    fallback = client.get("/chatter/?" + fallback_query, secure=True)
    assert (
        fallback.context["feed"]["locale"] == "en"
        and fallback.context["feed"]["requested_locale"] == "ja"
    )
    if backend == "shared":
        OriginalContentText.objects.create(
            narrative=rows[0].narrative,
            locale="ja",
            headline="New Japanese edition",
            secondary="Published after page one",
            body="New copy",
            public_id=uuid4(),
        )
    else:
        edition("New Japanese edition", locale="ja")
    with CaptureQueriesContext(connection) as queries:
        continued = client.get(fallback.context["next_url"], secure=True)
    assert continued.status_code == 200
    assert continued.context["feed"]["locale"] == "en"
    assert continued.context["feed"]["requested_locale"] == "ja"
    assert len(continued.context["feed"]["items"]) == 1
    assert b"New Japanese edition" not in continued.content
    assert not any(
        query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        for query in queries
    )


@pytest.mark.parametrize("backend", ["shared", "legacy"])
def test_existing_archive_and_api_cursor_format_is_unchanged(
    client, page_config, monkeypatch, backend
):
    from django.core import signing

    from monitor.editorial.readers import feed_payload
    from tests.test_editorial_views import edition

    cfg = page_config
    if backend == "shared":
        for number in range(21):
            published("rest", str(992000 + number))
        filters = {"source_locale": "en", "editorial_group": "rest"}
        query = {"source_lang": "en", "group": "rest", "edition_lang": "en"}
    else:
        monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "legacy")
        monkeypatch.setenv("ORIGINAL_CONTENT_MIRROR", "false")
        cfg = page_config.model_copy(
            update={
                "chatter": page_config.chatter.model_copy(update={"enabled": False})
            }
        )
        monkeypatch.setattr(
            "monitor.editorial.views.load_editorial_config", lambda: cfg
        )
        for number in range(21):
            edition("Legacy archive " + str(number))
        filters, query = {}, {}
    first = feed_payload(cfg, **filters)
    token = first["next_cursor"]
    assert "requested_locale" not in signing.loads(token, salt="editorial-archive")
    assert len(feed_payload(cfg, cursor=token, **filters)["items"]) == 1
    response = client.get(
        "/api/v2/editorial-stories/", {"cursor": token, **query}, secure=True
    )
    assert response.status_code == 200 and len(response.json()["items"]) == 1
