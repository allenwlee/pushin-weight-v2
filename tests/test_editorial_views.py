import pytest
from django.utils import timezone

from core.models import (
    EditorialAssessment,
    EditorialEdition,
    EditorialHero,
    EditorialStory,
)
from monitor.editorial.config import EditorialConfig
from tests.editorial_support import editorial_storage  # noqa: F401

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def edition(headline="THE PRICE IS WANG!", **kwargs):
    now = timezone.now()
    assessment = EditorialAssessment.objects.create(
        interval=now,
        cutoff=now,
        source_cycle_id="fixture",
        lease_until=now,
        state="complete",
    )
    story = EditorialStory.objects.create(development_key=str(assessment.pk))
    data = {
        "story": story,
        "assessment": assessment,
        "track": "chatter",
        "locale": "en",
        "revision": 1,
        "headline": headline,
        "byline": "The founder corrects the price tags.",
        "article": "The post gives lower prices for the outfit.",
        "importance": 80,
        "occurred_at": now,
        "fingerprint": str(assessment.pk),
        "model": "fixture",
        "evidence": {
            "sources": [
                {
                    "id": "1",
                    "url": "https://x.com/i/status/1",
                    "original_text": "PRIVATE RAW SOURCE",
                }
            ],
            "cutoff": now.isoformat(),
        },
        "selection": {"chart_support": "unavailable"},
    }
    data.update(kwargs)
    return EditorialEdition.objects.create(**data)


def test_permanent_story_link_and_archive_expose_only_accepted_copy(
    client, monkeypatch
):
    from monitor.editorial.readers import edition_payload

    monkeypatch.setattr(
        "monitor.editorial.views.load_editorial_config",
        lambda: EditorialConfig(public_enabled=True),
    )
    old = edition()
    newer = edition("NEW HERO")
    EditorialHero.objects.create(key="chatter:en", edition=newer)
    url = edition_payload(old, EditorialConfig())["url"]
    response = client.get(url, secure=True)
    assert response.status_code == 200
    assert b"THE PRICE IS WANG!" in response.content
    assert b"PRIVATE RAW SOURCE" not in response.content
    assert b"og:title" in response.content
    assert b'href="/"' in response.content
    api = client.get("/api/v2/editorial-stories/", secure=True)
    assert api.status_code == 200
    assert "PRIVATE RAW SOURCE" not in api.content.decode()
    assert api.json()["hero"]["headline"] == "NEW HERO"


def test_unpublished_and_disabled_public_routes_are_hidden(client):
    import uuid

    assert client.get("/stories/", secure=True).status_code == 404
    assert client.get("/api/v2/editorial-stories/", secure=True).status_code == 404
    assert client.get(f"/stories/{uuid.uuid4()}/", secure=True).status_code == 404


def test_archive_pagination_fallback_and_untrusted_copy_are_safe(client, monkeypatch):
    monkeypatch.setattr(
        "monitor.editorial.views.load_editorial_config",
        lambda: EditorialConfig(public_enabled=True),
    )
    for number in range(23):
        edition(f"Headline {number}")
    first = client.get("/api/v2/editorial-stories/?lang=ja", secure=True).json()
    assert first["requested_locale"] == "ja" and first["locale"] == "en"
    assert len(first["items"]) == 20 and len(first["history"]) == 5
    second = client.get(
        "/api/v2/editorial-stories/",
        {"lang": "ja", "cursor": first["next_cursor"]},
        secure=True,
    ).json()
    assert len(second["items"]) == 3 and not second["next_cursor"]
    assert not {p["id"] for p in first["items"]} & {p["id"] for p in second["items"]}
    assert (
        client.get(
            "/api/v2/editorial-stories/?cursor=tampered", secure=True
        ).status_code
        == 400
    )
    unsafe = edition(
        '<script>alert("unsafe")</script>',
        evidence={"sources": [{"url": "javascript:alert(1)"}]},
    )
    response = client.get(f"/stories/{unsafe.story_id}/?lang=en", secure=True)
    assert (
        b"<script>alert" not in response.content
        and b"&lt;script&gt;" in response.content
    )
    assert b"javascript:" not in response.content


@pytest.mark.usefixtures("editorial_storage")
def test_feed_batches_portrait_and_affiliation_reads():
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from core.models import EditorialPicture
    from monitor.editorial.readers import feed_payload
    from tests.editorial_support import person_photo

    _, role, photo = person_photo("blue", "founder")
    for number in range(20):
        item = edition(f"Headline {number}")
        EditorialPicture.objects.create(
            content_kind="chatter",
            content_id=str(item.pk),
            revision_hash="fixture",
            source_media=photo.media,
            person_media=photo,
            mode="select_only",
            provenance={
                "reuse_status": "permitted",
                "brand_keys": ["deepseek"],
                "affiliation_id": role.pk,
            },
        )
    with CaptureQueriesContext(connection) as queries:
        result = feed_payload(EditorialConfig(pictures={"chatter": "select_only"}))
    assert len(result["items"]) == 20 and all(i["asset"] for i in result["items"])
    assert len(queries) <= 7, [q["sql"] for q in queries]


def picture_asset(monkeypatch, remote, variant):
    from django.urls import reverse

    from core.models import EditorialPicture
    from tests.editorial_support import active_config, person_photo

    _, role, photo = person_photo("blue", "founder")
    item = edition()
    picture = EditorialPicture.objects.create(
        content_kind="chatter",
        content_id=str(item.pk),
        revision_hash="fixture",
        source_media=photo.media,
        person_media=photo,
        mode="derive",
        state="complete",
        generated_storage_name="generated/fixture.mp4",
        provenance={
            "reuse_status": "permitted",
            "brand_keys": ["deepseek"],
            "affiliation_id": role.pk,
        },
    )
    cfg = active_config(public_enabled=True)
    monkeypatch.setattr("monitor.editorial.views.load_editorial_config", lambda: cfg)
    monkeypatch.setattr("monitor.editorial.views.media_storage", lambda: remote)
    monkeypatch.setattr("monitor.editorial.views.storages", {"editorial_media": remote})
    url = reverse(
        "editorial_asset",
        kwargs={
            "story_id": item.story_id,
            "picture_id": picture.pk,
            "variant": variant,
        },
    )
    return url, photo, cfg


class RemoteMedia:
    def __init__(self, url, exists=True):
        self.link = url
        self.present = exists
        self.issued = []

    def exists(self, name):
        return self.present

    def url(self, name, *, expire):
        self.issued.append((name, expire))
        return self.link

    def open(self, *args):
        pytest.fail("remote media bytes must not stream through the web service")


@pytest.mark.usefixtures("editorial_storage")
@pytest.mark.parametrize("variant", ["source", "generated"])
def test_remote_asset_redirect_is_short_lived_and_policy_checked(
    client, monkeypatch, variant
):
    remote = RemoteMedia(
        "https://media.example/object?X-Amz-Signature=test&X-Amz-Expires=300"
    )
    url, photo, cfg = picture_asset(monkeypatch, remote, variant)
    response = client.get(url, secure=True)
    assert response.status_code == 302 and response["Location"] == remote.link
    assert response["Cache-Control"] == "private, no-store"
    assert remote.issued[0][1] == 300
    photo.source_verified = False
    photo.save(update_fields=["source_verified"])
    assert client.get(url, secure=True).status_code == 404
    assert len(remote.issued) == 1
    photo.source_verified = True
    photo.save(update_fields=["source_verified"])
    monkeypatch.setattr(
        "monitor.editorial.views.load_editorial_config",
        lambda: cfg.model_copy(update={"pictures": {}}),
    )
    assert client.get(url, secure=True).status_code == 404
    assert len(remote.issued) == 1


@pytest.mark.usefixtures("editorial_storage")
@pytest.mark.parametrize(
    "link,present",
    [
        ("http://media.example/object?X-Amz-Signature=test&X-Amz-Expires=300", True),
        ("https://media.example/public/object", True),
        ("https://media.example/object?X-Amz-Signature=test&X-Amz-Expires=3600", True),
        ("https://media.example/object?X-Amz-Signature=test", True),
        ("https://media.example/object?X-Amz-Signature=test&X-Amz-Expires=300", False),
    ],
)
def test_remote_asset_rejects_missing_unsigned_or_unbounded_links(
    client, monkeypatch, link, present
):
    remote = RemoteMedia(link, exists=present)
    url, _, _ = picture_asset(monkeypatch, remote, "source")
    assert client.get(url, secure=True).status_code == 404


def test_source_attribution_deduplicates_posts_without_inventing_independence():
    from monitor.editorial.readers import edition_payload

    sources = [
        {"id": "1", "url": "https://x.com/i/status/1", "author_handle": "same"},
        {"id": "2", "url": "https://x.com/i/status/2", "author_handle": "same"},
    ]
    item = edition_payload(
        edition(evidence={"sources": sources + [sources[0]]}), EditorialConfig()
    )
    assert item["source_count"] == 2
    assert len(item["sources"]) == 2
    assert {s["label"] for s in item["sources"]} == {"same"}
