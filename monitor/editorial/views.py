"""Permanent story and share surfaces; optional anonymous access is explicit."""

from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from django.core import signing
from django.core.files.storage import FileSystemStorage, storages
from django.http import (
    FileResponse,
    Http404,
    HttpResponseBadRequest,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, render
from django.utils import translation
from django.views.decorators.http import require_GET

from core.models import EditorialPicture
from core.staff_assets.media import media_storage

from .config import load_editorial_config
from .readers import (
    LOCALES,
    TRACKS,
    edition_payload,
    feed_payload,
    find_saved_edition,
    picture_for_edition,
)


def access(request):
    cfg = load_editorial_config()
    if not cfg.public_enabled and not (
        request.user.is_authenticated and request.user.is_staff
    ):
        raise Http404
    return cfg


def filters(request):
    locale = request.GET.get("lang", getattr(request, "LANGUAGE_CODE", "en")).lower()
    locale = {"zh-hans": "zh-cn", "zh_cn": "zh-cn"}.get(locale, locale)
    track = request.GET.get("track", "chatter")
    if locale not in LOCALES or track not in TRACKS:
        raise ValueError("unsupported track or locale")
    return track, locale


def private_cache(response):
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def pool_options(request, cfg, track, locale):
    if track != "chatter" or not cfg.chatter.enabled:
        return {}
    source = request.GET.get("source_lang", locale).casefold()
    edition = request.GET.get("edition_lang", locale).casefold()
    group = request.GET.get("group", "rest")
    if source not in LOCALES or edition not in LOCALES or group not in {"giant", "rest"}:
        raise ValueError("unsupported Chatter pool")
    return {"source_locale": source, "editorial_group": group, "locale": edition}


def pool_controls(request, options):
    if not options:
        return None
    return {"source_lang": options["source_locale"], "group": options["editorial_group"],
            "edition_lang": options["locale"],
            "hidden": [(key, value) for key, values in request.GET.lists()
                       if key not in {"source_lang", "group", "edition_lang", "cursor"} for value in values]}


@require_GET
def story(request, story_id):
    cfg = access(request)
    try:
        track, locale = filters(request)
        pinned = UUID(request.GET["edition"]) if request.GET.get("edition") else None
        edition = find_saved_edition(story_id, track, locale=locale, pinned=pinned)
    except (ValueError, TypeError):
        return HttpResponseBadRequest("Invalid story selection")
    if edition is None:
        raise Http404
    item = edition_payload(edition, cfg)
    context = {
        "item": item,
        "requested_locale": locale,
        "fallback": edition.locale != locale,
        "canonical_url": request.build_absolute_uri(item["url"]),
        "poster_url": request.build_absolute_uri(item["asset"]["poster"])
        if item["asset"]
        else "",
    }
    with translation.override("zh-hans" if locale == "zh-cn" else locale):
        return private_cache(render(request, "monitor/editorial/story.html", context))


@require_GET
def archive(request):
    cfg = access(request)
    try:
        track, locale = filters(request)
        options = pool_options(request, cfg, track, locale)
        feed = feed_payload(
            cfg, track=track, cursor=request.GET.get("cursor", ""), **({"locale": locale} | options)
        )
    except (ValueError, TypeError, KeyError, signing.BadSignature):
        return HttpResponseBadRequest("Invalid archive selection")
    with translation.override("zh-hans" if locale == "zh-cn" else locale):
        return private_cache(
            render(request, "monitor/editorial/archive.html", {"feed": feed, "pool_controls": pool_controls(request, options)})
        )


@require_GET
def stories_api(request):
    cfg = access(request)
    try:
        track, locale = filters(request)
        options = pool_options(request, cfg, track, locale)
        return private_cache(
            JsonResponse(
                feed_payload(
                    cfg,
                    track=track,
                    **({"locale": locale} | options),
                    cursor=request.GET.get("cursor", ""),
                )
            )
        )
    except (ValueError, TypeError, KeyError, signing.BadSignature):
        return HttpResponseBadRequest("Invalid archive selection")


@require_GET
def asset(request, story_id, picture_id, variant):
    cfg = access(request)
    picture = get_object_or_404(
        EditorialPicture, pk=picture_id, content_kind__in=["chatter", "pulse"]
    )
    edition = find_saved_edition(
        story_id, picture.content_kind, pinned=UUID(picture.content_id)
    )
    if edition is None:
        raise Http404
    eligible = picture_for_edition(edition, cfg)
    if eligible is None or eligible.pk != picture.pk:
        raise Http404
    if variant == "source":
        storage = media_storage()
        name = picture.source_media.storage_name
        content_type = picture.source_media.media_type
    elif (
        variant == "generated"
        and picture.state == "complete"
        and cfg.picture_mode(edition.track, "x") == "derive"
    ):
        storage = storages["editorial_media"]
        name = picture.generated_storage_name
        content_type = "video/mp4"
    else:
        raise Http404
    try:
        if not isinstance(storage, FileSystemStorage):
            if not storage.exists(name):
                raise Http404
            # The shared S3-compatible adapter owns credentials and URL signing.
            # Never persist the temporary URL or cache this authorization response.
            url = storage.url(name, expire=300)
            parts = urlsplit(url)
            query = parse_qs(parts.query)
            expires = query.get("X-Amz-Expires", [])
            if (
                parts.scheme != "https"
                or not parts.hostname
                or not query.get("X-Amz-Signature")
                or len(expires) != 1
                or not 0 < int(expires[0]) <= 300
            ):
                raise Http404
            return private_cache(HttpResponseRedirect(url))
        stream = storage.open(name, "rb")
    except (OSError, ValueError):
        raise Http404 from None
    return private_cache(FileResponse(stream, content_type=content_type))
