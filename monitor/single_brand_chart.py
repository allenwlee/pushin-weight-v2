"""Public, bounded read-only release chart requests for General."""

import fcntl
import hashlib
import logging
import os
import re
import time as clock
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from threading import Lock
from uuid import UUID

from django.core.cache import caches
from django.db import DatabaseError, connection, transaction
from django.db.models import Q
from django.db.models.functions import Collate
from django.http import Http404, HttpResponseBadRequest, JsonResponse
from django.utils import timezone, translation
from django.utils.translation import gettext
from django.views.decorators.http import require_GET

from core.chart_engine import ChartRequest, ReleaseAnchor, build_single_brand_chart
from core.models import Product
from monitor.content_views import content_locale, private_response

logger = logging.getLogger(__name__)
try:
    cache = caches["chartengine"]
except OSError:
    logger.warning("Chart cache unavailable; using process-local cache", exc_info=True)
    cache = caches["default"]
_CHART_CACHE_SECONDS = 300
_CHART_BUILD_LOCK = Lock()
_CHART_BUILD_INTERVAL_SECONDS = 3
_LAST_BUILD_FINISHED = float("-inf")


def _public_products():
    return Product.objects.all()


def _cached_chart(key):
    try:
        return cache.get(key)
    except OSError:
        logger.warning("Chart cache read failed", exc_info=True)
        return None


def _build_lock_name(product_key, anchor):
    # A fixed set of stripes bounds lock files while allowing different charts
    # to build concurrently. Both provenance variants share a stripe.
    token = f"{product_key}:{anchor.isoformat()}".encode()
    stripe = int.from_bytes(hashlib.sha256(token).digest()[:2], "big") % 128
    return f"build-{stripe:03d}.lock"


def _busy():
    response = JsonResponse({"error": "Chart is busy. Try again shortly."}, status=429)
    response["Retry-After"] = str(_CHART_BUILD_INTERVAL_SECONDS)
    return response


def _calculate_chart(request_data):
    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
                )
                cursor.execute("SET LOCAL statement_timeout = '15000ms'")
        return build_single_brand_chart(request_data)


@require_GET
def products(request):
    query = request.GET.get("q", "").strip()
    if not 2 <= len(query) <= 80:
        return HttpResponseBadRequest("Enter at least two characters.")
    results = (
        _public_products()
        .annotate(search_repo=Collate("repo_id", "C"))
        .filter(Q(display_name__icontains=query) | Q(search_repo__icontains=query))
        .order_by("display_name", "id")
        .values("product_key", "display_name", "repo_id")[:20]
    )
    return private_response(
        JsonResponse(
            {
                "products": [
                    {
                        "key": str(row["product_key"]),
                        "label": row["display_name"] or row["repo_id"],
                    }
                    for row in results
                ]
            }
        )
    )


@require_GET
def chart(request):
    global _LAST_BUILD_FINISHED
    product_id = request.GET.get("product")
    release = request.GET.get("release_date")
    if not product_id and not release:
        # Owner-confirmed release is a starting example, not a limitation of
        # the engine or the endpoint. The date is an explicitly supplied anchor.
        product = (
            _public_products()
            .filter(repo_id="deepseek-ai/DeepSeek-V4-Pro-0813")
            .first()
        )
        anchor = date(2026, 8, 13)
        anchor_source = "owner-confirmed"
    else:
        try:
            product_key = UUID(product_id)
            if not isinstance(release, str) or not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}", release
            ):
                raise ValueError("invalid release date")
            anchor = date.fromisoformat(release)
        except (ValueError, TypeError, AttributeError):
            return HttpResponseBadRequest("A product and release date are required.")
        product = _public_products().filter(product_key=product_key).first()
        anchor_source = "caller-supplied"
    if product is None:
        raise Http404("Product is unavailable.")
    now = timezone.now().astimezone(UTC)
    if anchor.year < 1970 or anchor > now.date():
        return HttpResponseBadRequest("Invalid release date.")
    request_data = ChartRequest(
        target=ReleaseAnchor(
            product_key=product.product_key, date=anchor, source=anchor_source
        ),
        start=datetime.combine(anchor - timedelta(days=14), time.min, tzinfo=UTC),
        end=datetime.combine(anchor + timedelta(days=29), time.min, tzinfo=UTC),
        cutoff=now,
        history_mode="hindsight",
    )
    cache_key = f"single-brand-comp:v1:{product.product_key}:{anchor.isoformat()}:{anchor_source}"
    refresh = request.GET.get("refresh") == "1"
    result = None if refresh else _cached_chart(cache_key)
    if result is None:
        if not _CHART_BUILD_LOCK.acquire(blocking=False):
            return _busy()
        lock_file = None
        try:
            # File cache is shared by workers on this instance; its build lock
            # must share the same scope to keep old calculations from winning.
            cache_dir = getattr(cache, "_dir", None)
            if cache_dir:
                try:
                    Path(cache_dir).mkdir(mode=0o700, parents=True, exist_ok=True)
                    fd = os.open(
                        str(Path(cache_dir) / _build_lock_name(product.product_key, anchor)),
                        os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                        0o600,
                    )
                    lock_file = os.fdopen(fd, "a+")
                    fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return _busy()
                except OSError:
                    logger.exception("Chart build lock unavailable")
                    return JsonResponse({"error": "Chart data is temporarily unavailable."}, status=503)
            # Recheck after acquiring the shared admission lock.
            result = None if refresh else _cached_chart(cache_key)
            if result is None:
                if (
                    clock.monotonic() - _LAST_BUILD_FINISHED
                    < _CHART_BUILD_INTERVAL_SECONDS
                ):
                    return _busy()
                try:
                    result = _calculate_chart(request_data)
                except (ValueError, TypeError):
                    return HttpResponseBadRequest("The requested chart is unavailable.")
                except DatabaseError:
                    return JsonResponse(
                        {"error": "Chart data is temporarily unavailable."}, status=503
                    )
                finally:
                    _LAST_BUILD_FINISHED = clock.monotonic()
                try:
                    if refresh:
                        other_source = (
                            "owner-confirmed" if anchor_source == "caller-supplied"
                            else "caller-supplied"
                        )
                        other_key = (
                            f"single-brand-comp:v1:{product.product_key}:"
                            f"{anchor.isoformat()}:{other_source}"
                        )
                        cache.delete(other_key)
                    cache.set(cache_key, result, timeout=_CHART_CACHE_SECONDS)
                except OSError:
                    logger.warning("Chart cache write failed", exc_info=True)
        finally:
            if lock_file is not None:
                lock_file.close()
            _CHART_BUILD_LOCK.release()
    locale = content_locale(request)
    result = {**result, "lines": [dict(line) for line in result["lines"]]}
    with translation.override("zh-hans" if locale == "zh-cn" else locale):
        for line in result["lines"]:
            line["label"] = gettext(line["label"])
            line["unit"] = gettext(line["unit"])
        result["notes"] = [gettext(note) for note in result["notes"]]
    return private_response(JsonResponse(result))
