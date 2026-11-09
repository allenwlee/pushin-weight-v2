"""Permanent story and share surfaces; optional anonymous access is explicit."""

import hashlib
import re
from tempfile import SpooledTemporaryFile
from threading import BoundedSemaphore, Lock
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from botocore.exceptions import BotoCoreError, ClientError
from django.core import signing
from django.core.files.storage import FileSystemStorage, storages
from django.http import (
    FileResponse,
    Http404,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseRedirect,
    JsonResponse,
    StreamingHttpResponse,
)
from django.shortcuts import get_object_or_404, render
from django.utils import translation
from django.views.decorators.http import require_GET
from PIL import Image, UnidentifiedImageError

from core.models import EditorialPicture
from core.staff_assets.media import media_storage

from .config import load_editorial_config
from .graphics_artifacts import MAX_STILL_BYTES, MIME_FORMATS
from .graphics_generation import MAX_VIDEO_BYTES
from .graphics_reading import graphics_assets, is_graphics_edition
from .readers import (
    LOCALES,
    TRACKS,
    edition_payload,
    feed_payload,
    find_saved_edition,
    picture_for_edition,
)

# A worker may hold at most two snapshots (100 MiB of video) at once.
GRAPHICS_SNAPSHOT_SLOTS = 2
_graphics_snapshot_slots = BoundedSemaphore(GRAPHICS_SNAPSHOT_SLOTS)


def _snapshot_release(slots):
    """Create an idempotent slot release for the response and error paths."""
    lock = Lock()
    released = False
    def release():
        nonlocal released
        with lock:
            if not released:
                released = True
                slots.release()
    return release


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


def graphics_snapshot_response(request, snapshot, size, digest, content_type, release):
    """Serve the verified snapshot, including one bounded byte range for seeking."""
    # WSGI may later replace snapshot.close with response.close. Retain the
    # actual file closer now to avoid recursive response-close callbacks.
    close_file = snapshot.close
    def close_snapshot():
        try:
            close_file()
        finally:
            release()

    etag = f'"{digest}"'
    requested = request.headers.get('Range', '')
    if request.headers.get('If-Range', etag) != etag:
        requested = ''
    if requested:
        match = re.fullmatch(r'bytes=(\d*)-(\d*)', requested)
        try:
            if not match or not (match.group(1) or match.group(2)):
                raise ValueError('invalid range')
            start = int(match.group(1)) if match.group(1) else max(0, size - int(match.group(2)))
            end = min(size - 1, int(match.group(2))) if match.group(1) and match.group(2) else size - 1
            if start >= size or end < start or (not match.group(1) and int(match.group(2)) == 0):
                raise ValueError('unsatisfiable range')
        except ValueError:
            close_snapshot()
            response = HttpResponse(status=416)
            response['Content-Range'] = f'bytes */{size}'
        else:
            snapshot.seek(start)
            length = end - start + 1
            def chunks():
                remaining = length
                try:
                    while remaining:
                        data = snapshot.read(min(65536, remaining))
                        if not data:
                            break
                        remaining -= len(data)
                        yield data
                finally:
                    close_snapshot()
            response = StreamingHttpResponse(chunks(), status=206, content_type=content_type)
            response['Content-Length'] = str(length)
            response['Content-Range'] = f'bytes {start}-{end}/{size}'
    else:
        snapshot.seek(0)
        response = FileResponse(snapshot, content_type=content_type)
    response['Accept-Ranges'] = 'bytes'
    response['ETag'] = etag
    # Django closes this on normal completion and on a disconnected client,
    # including when a streaming iterator has not started yet.
    response._resource_closers.append(close_snapshot)
    return private_cache(response)


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
    try:
        edition = find_saved_edition(
            story_id, picture.content_kind, pinned=UUID(picture.content_id)
        )
    except (ValueError, TypeError):
        raise Http404 from None
    if edition is None:
        raise Http404
    metadata = picture.provenance if isinstance(picture.provenance, dict) else {}
    if is_graphics_edition(edition) or str(metadata.get("schema_version", "")).startswith("graphics-"):
        if not is_graphics_edition(edition) or cfg.picture_mode(edition.track, "x") == "off" or variant != "generated":
            raise Http404
        slots = _graphics_snapshot_slots
        if not slots.acquire(blocking=False):
            response = HttpResponse('Media temporarily busy', status=503)
            response['Retry-After'] = '2'
            return private_cache(response)
        release = _snapshot_release(slots)
        snapshot = None
        handed_off = False
        try:
            is_still = metadata.get('role') == 'still'
            selected = graphics_assets(edition, include_video=not is_still,
                                       verify_video_bytes=False, verify_still_bytes=not is_still)
            if selected is None or picture.pk not in {selected.still.pk, selected.video.pk if selected.video else None}:
                raise Http404
            storage = storages["editorial_media"]
            name = picture.generated_storage_name
            content_type = metadata["mime"]
            # The storage key is mutable. Serve the exact bounded snapshot whose
            # digest we verified, never a later read or a redirect to that key.
            limit = MAX_VIDEO_BYTES if metadata['role'] == 'video' else MAX_STILL_BYTES
            snapshot = SpooledTemporaryFile(max_size=2 * 1024 * 1024, mode='w+b')  # noqa: SIM115 -- response owns its lifetime
            checksum = hashlib.sha256()
            size = 0
            with storage.open(name, 'rb') as source:
                while chunk := source.read(65536):
                    size += len(chunk)
                    if size > limit:
                        raise ValueError('Graphics asset exceeds size limit')
                    checksum.update(chunk)
                    snapshot.write(chunk)
            if not size or checksum.hexdigest() != picture.generated_sha256:
                raise ValueError('Graphics asset bytes mismatch')
            if is_still:
                snapshot.seek(0)
                with Image.open(snapshot) as img:
                    if img.format != MIME_FORMATS[content_type]:
                        raise ValueError('Graphics still MIME mismatch')
                    img.verify()
            response = graphics_snapshot_response(request, snapshot, size, picture.generated_sha256, content_type, release)
            handed_off = True
            return response
        except (OSError, ValueError, KeyError, UnidentifiedImageError,
                Image.DecompressionBombError, BotoCoreError, ClientError):
            raise Http404 from None
        finally:
            if not handed_off:
                if snapshot is not None:
                    snapshot.close()
                release()
    else:
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
