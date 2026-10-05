"""Saved, approved reader projection. No generation, raw evidence or internal audit."""

from urllib.parse import urlencode

from django.core import signing
from django.core.files.storage import storages
from django.db.models import F, Q, Window
from django.db.models.functions import RowNumber
from django.urls import reverse

from core.models import (
    EditorialEdition,
    EditorialHero,
    EditorialPicture,
    PersonBrandAffiliation,
)

from .pictures import assignment_eligible

LOCALES = {"en", "zh-cn", "ja"}
TRACKS = {"chatter", "pulse"}


def picture_for_edition(edition, cfg):
    return pictures_for_editions([edition], cfg).get(edition.pk)


def pictures_for_editions(editions, cfg):
    enabled = [e for e in editions if cfg.picture_mode(e.track, "x") != "off"]
    if not enabled:
        return {}
    rows = list(
        EditorialPicture.objects.filter(
            content_kind__in={e.track for e in enabled},
            content_id__in=[str(e.pk) for e in enabled],
            source_media__isnull=False,
        )
        .select_related("source_media", "person_media__media")
        .order_by("content_kind", "content_id", "-created_at")
        .distinct("content_kind", "content_id")
    )
    affiliations = {
        role.pk: role
        for role in PersonBrandAffiliation.objects.select_related("person").filter(
            pk__in=[
                r.provenance.get("affiliation_id") for r in rows if r.person_media_id
            ]
        )
    }
    eligible = {
        (r.content_kind, r.content_id): r
        for r in rows
        if assignment_eligible(r, cfg, affiliations=affiliations)
    }
    return {e.pk: eligible.get((e.track, str(e.pk))) for e in enabled}


def asset_payload(edition, cfg, pictures=None):
    picture = (
        picture_for_edition(edition, cfg)
        if pictures is None
        else pictures.get(edition.pk)
    )
    if picture is None:
        return None
    args = {"story_id": edition.story_id, "picture_id": picture.pk}
    photo_url = reverse("editorial_asset", kwargs={**args, "variant": "source"})
    generated = (
        cfg.picture_mode(edition.track, "x") == "derive"
        and picture.state == "complete"
        and picture.generated_storage_name
        and storages["editorial_media"].exists(picture.generated_storage_name)
    )
    return {
        "type": "video" if generated else "image",
        "url": reverse("editorial_asset", kwargs={**args, "variant": "generated"})
        if generated
        else photo_url,
        "poster": photo_url,
        "generated": bool(generated),
        "caption": ("AI-generated illustration · " if generated else "")
        + picture.provenance.get("person_name", "Source image"),
    }


def edition_payload(edition, cfg, *, pictures=None):
    return {
        "id": str(edition.pk),
        "story_id": str(edition.story_id),
        "track": edition.track,
        "locale": edition.locale,
        "headline": edition.headline,
        "byline": edition.byline,
        "article": edition.article,
        "published_at": edition.published_at.isoformat(),
        "revision": edition.revision,
        "url": reverse("editorial_story", kwargs={"story_id": edition.story_id})
        + "?"
        + urlencode(
            {"track": edition.track, "lang": edition.locale, "edition": str(edition.pk)}
        ),
        "sources": [
            {"url": source["url"], "label": source.get("author_handle") or "X"}
            for source in edition.evidence.get("sources", [])
            if source.get("url", "").startswith("https://x.com/")
        ],
        "chart_support": edition.selection.get("chart_support", "unavailable"),
        "asset": asset_payload(edition, cfg, pictures),
    }


def feed_payload(cfg, *, track="chatter", locale="en", cursor="", limit=20):
    if track not in TRACKS or locale not in LOCALES:
        raise ValueError("unsupported track or locale")
    requested_locale = locale
    if (
        locale != "en"
        and not EditorialEdition.objects.filter(track=track, locale=locale).exists()
    ):
        locale = "en"
    query = EditorialEdition.objects.filter(track=track, locale=locale).order_by(
        "-published_at", "-id"
    )
    if cursor:
        value = signing.loads(cursor, salt="editorial-archive")
        if value["track"] != track or value["locale"] != locale:
            raise ValueError("cursor filter mismatch")
        query = query.filter(
            Q(published_at__lt=value["at"])
            | Q(published_at=value["at"], id__lt=value["id"])
        )
    editions = list(query[: limit + 1])
    more = len(editions) > limit
    editions = editions[:limit]
    hero = (
        EditorialHero.objects.filter(key=f"chatter:{locale}")
        .select_related("edition")
        .first()
        if track == "chatter"
        else None
    )
    current = hero.edition if hero else None
    history = (
        list(
            EditorialEdition.objects.filter(track="chatter", locale=locale)
            .exclude(story_id=current.story_id if current else None)
            .annotate(
                story_rank=Window(
                    expression=RowNumber(),
                    partition_by=[F("story_id")],
                    order_by=[F("published_at").desc(), F("id").desc()],
                )
            )
            .filter(story_rank=1)
            .order_by("-published_at", "-id")[:5]
        )
        if track == "chatter"
        else []
    )
    next_cursor = (
        signing.dumps(
            {
                "track": track,
                "locale": locale,
                "at": editions[-1].published_at.isoformat(),
                "id": str(editions[-1].pk),
            },
            salt="editorial-archive",
        )
        if more
        else ""
    )
    all_editions = {
        e.pk: e for e in editions + history + ([current] if current else [])
    }
    pictures = pictures_for_editions(all_editions.values(), cfg)
    payloads = {
        pk: edition_payload(e, cfg, pictures=pictures) for pk, e in all_editions.items()
    }
    return {
        "track": track,
        "locale": locale,
        "requested_locale": requested_locale,
        "hero": payloads[current.pk] if current else None,
        "history": [payloads[e.pk] for e in history],
        "items": [payloads[e.pk] for e in editions],
        "next_cursor": next_cursor,
    }


def longitudinal_subject(edition):
    """Private G3 handoff; history never changes G2's selection decision."""
    return {
        "story_id": str(edition.story_id),
        "edition_id": str(edition.pk),
        "brand_keys": edition.selection.get("brand_keys", []),
        "post_ids": edition.evidence.get("post_ids", []),
        "evidence_cutoff": edition.evidence.get("cutoff"),
        "development_at": edition.occurred_at.isoformat(),
    }
