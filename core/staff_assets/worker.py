"""Execute one short leased collection unit independently of source ingestion."""

import urllib3
from django.db import connection, transaction
from django.utils import timezone
from PIL import Image

from core.models import PersonMedia, StaffCollectionWork
from core.staff_assets.media import fetch_public, record_media, store_image
from core.staff_assets.providers import media_candidates, sanitized
from core.staff_assets.queue import (
    AmbiguousRequest,
    BudgetExhausted,
    claim,
    finish,
    record_response,
    reserve_request,
)


def lease_live(work):
    return StaffCollectionWork.objects.filter(
        pk=work.pk,
        state="running",
        lease_token=work.lease_token,
        lease_expires_at__gt=timezone.now(),
    ).exists()


def run_once(
    *,
    run_id,
    provider=None,
    allow_network=False,
    per_person=0,
    per_run=0,
    per_day=0,
    max_downloads=2,
    fetcher=fetch_public,
):
    if connection.in_atomic_block:
        raise RuntimeError("Collection must run outside source transactions")
    if not 0 <= max_downloads <= 3:
        raise ValueError("A lease supports at most three media downloads")
    work = claim()
    if work is None:
        return {"state": "idle"}
    result = {"requests": 0, "downloads": 0, "unavailable": 0}
    context = work.context
    try:
        if (
            context.get("baidu_eligible") is True
            and context.get("baidu_query")
            and allow_network
            and provider
        ):
            parameters = {
                "engine": "baidu",
                "q": context["baidu_query"],
                "rn": 50,
                "pn": 0,
            }
            request, send = reserve_request(
                work,
                run_id=run_id,
                provider=provider.name,
                parameters=parameters,
                per_person=per_person,
                per_run=per_run,
                per_day=per_day,
            )
            if send:
                try:
                    response = sanitized(provider.search(parameters))
                except Exception as exc:  # noqa: BLE001 — any post-reservation failure may have incurred a charge
                    record_response(request, error=type(exc).__name__)
                    raise AmbiguousRequest(
                        "Provider failure needs review before another charged request"
                    ) from None
                record_response(request, response=response)
                result["requests"] = 1
            else:
                response = request.response
            # Hold a row lock only while persisting returned candidates, never during HTTP.
            with transaction.atomic():
                StaffCollectionWork.objects.select_for_update().get(pk=work.pk)
                if not lease_live(work):
                    return {"state": "stale", **result}
                for entry in media_candidates(response):
                    record_media(work.person, entry)
                result["organic_results"] = len(response.get("organic_results", []))
        if allow_network:
            candidates = list(
                PersonMedia.objects.filter(
                    person_id=work.person_id,
                    availability="unfetched",
                    kind__in=["image", "avatar", "portrait"],
                )
                .exclude(original_url="")
                .order_by("id")[:max_downloads]
            )
            for row in candidates:
                if not lease_live(work):
                    return {"state": "stale", **result}
                try:
                    media = store_image(fetcher(row.original_url))
                    availability = "available"
                except (
                    OSError,
                    ValueError,
                    urllib3.exceptions.HTTPError,
                    Image.DecompressionBombError,
                ):
                    media, availability = None, "unavailable"
                with transaction.atomic():
                    StaffCollectionWork.objects.select_for_update().get(pk=work.pk)
                    if not lease_live(work):
                        return {"state": "stale", **result}
                    PersonMedia.objects.filter(pk=row.pk).update(
                        media=media, availability=availability
                    )
                result["downloads" if media else "unavailable"] += 1
        covered = PersonMedia.objects.filter(
            person_id=work.person_id,
            source_verified=True,
            individual_portrait=True,
            suitability="approved",
            availability="available",
        ).exists()
        state = "complete" if covered else "needs_evidence"
        if context.get("baidu_eligible") and not (allow_network and provider):
            result["search_status"] = "not_run_network_disabled"
        if not finish(work, state=state, result=result):
            state = "stale"
        return {"state": state, **result}
    except BudgetExhausted:
        finish(work, state="retry_due", error="budget_exhausted")
        return {"state": "retry_due", "error": "budget_exhausted"}
    except AmbiguousRequest:
        finish(work, state="needs_review", error="request_needs_review")
        return {"state": "needs_review"}
    except Exception as exc:
        finish(
            work,
            state="needs_review" if work.attempts >= 3 else "retry_due",
            error=type(exc).__name__,
        )
        raise
