"""Bounded, resumable portrait research for a single already resolved person."""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime
from decimal import Decimal
from functools import partial
from pathlib import Path
from urllib.parse import urlsplit

from django.core.files.storage import storages
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.models import (
    Person,
    PersonName,
    StaffIntake,
    StaffMediaObject,
    StaffProviderRequest,
)
from core.staff_assets.g2_cast_ingest import ingest_portrait_bytes
from core.staff_assets.graphics_references import read_graphics_references
from core.staff_assets.media import MAX_BYTES, review_media, store_image
from core.staff_assets.public_fetch import fetch_before_deadline
from core.staff_assets.queue import (
    AmbiguousRequest,
    BudgetExhausted,
    record_response,
    reserve_request,
)
from core.staff_assets.worker import lease_live
from monitor.editorial.graphics_generation import MIME_TYPES
from monitor.editorial.graphics_search import (
    EXA_SEARCH_ESTIMATE_PER_QUERY_USD,
    search_exa_query,
)
from monitor.editorial.persistence import completed_text_cost

from .person_portrait_assessment import (
    PortraitAssessment,
    assess_source,
    grounded_job_history,
    grounded_observation,
    portrait_supported,
)
from .person_portrait_sources import contains_name, public_url, read_page

# Both supplied pages and pages discovered by the paid search use the same cap.
LIMITS = {
    "portrait_page": 3,
    "portrait_image": 1,
    "portrait_exa": 1,
    "portrait_assessment": 1,
}
COUNTERS = {
    "portrait_page": "pages_fetched",
    "portrait_image": "images_downloaded",
    "portrait_exa": "search_requests",
    "portrait_assessment": "person_research_llm_calls",
}
PAID = {"portrait_exa", "portrait_assessment"}
PAGE_SECONDS = 20


class PortraitGap(Exception):
    pass


def _report(work):
    counts = dict.fromkeys(COUNTERS.values(), 0)
    counts.update(page_requests=0, image_requests=0, uncertain_requests=0)
    costs = []
    if work:
        for req in StaffProviderRequest.objects.filter(
            work=work, provider__in=LIMITS
        ).order_by("pk"):
            if req.provider in PAID:
                counts[COUNTERS[req.provider]] += 1
                counts["uncertain_requests"] += int(
                    req.state in {"reserved", "needs_review"}
                )
            else:
                counter = (
                    "page_requests"
                    if req.provider == "portrait_page"
                    else "image_requests"
                )
                counts[counter] += 1
                counts[COUNTERS[req.provider]] += int(
                    req.state == "complete" and "gap" not in req.response
                )
            if req.provider in PAID:
                costs.append(
                    {
                        "request_id": req.pk,
                        "operation": req.provider,
                        "state": req.state,
                        "reserved_usd": req.parameters.get("reserved_usd"),
                        "estimated_usd": req.response.get("estimated_usd"),
                        "billed_usd": req.response.get("billed_usd"),
                    }
                )
    return {"counters": counts, "costs": costs}


def _once(work, provider, params, send, *, deadline=None):
    # Completed results survive a worker restart. Interrupted sends retain their
    # reservation, even if the provider response never made it back to Django.
    params = {"schema": "person-portrait/v1", **params}
    if provider not in PAID:
        params["work_id"] = work.pk
    run_id = uuid.uuid5(uuid.NAMESPACE_URL, f"person-portrait:{work.pk}")
    if deadline is not None and time.monotonic() >= deadline:
        from core.person_names import digest

        prior = StaffProviderRequest.objects.filter(
            work=work, provider=provider, fingerprint=digest(params)
        ).first()
        if prior is None:
            raise PortraitGap("retrieval_deadline")
    setting = {
        "portrait_exa": "PERSON_RESEARCH_DAILY_SEARCH_LIMIT",
        "portrait_assessment": "PERSON_RESEARCH_DAILY_ASSESSMENT_LIMIT",
    }.get(provider)
    cap = os.environ.get(setting) if setting else None
    req, dispatch = reserve_request(
        work,
        run_id=run_id,
        provider=provider,
        parameters=params,
        per_person=None,
        per_run=LIMITS[provider],
        per_day=int(cap) if cap is not None else None,
    )
    if not dispatch:
        if req.response.get("gap"):
            raise PortraitGap(req.response["gap"])
        return req.response
    try:
        response = send()
    except Exception as exc:
        gap = f"{provider}_failed:{type(exc).__name__}"
        usage = getattr(exc, "diagnostics", {}).get("usage", {})
        record_response(
            req,
            response={
                "gap": gap,
                "billed_usd": usage.get("provider_reported_cost_usd"),
            },
            error=type(exc).__name__ if provider in PAID else "",
        )
        if provider in PAID:
            raise AmbiguousRequest(gap) from exc
        raise PortraitGap(gap) from exc
    if not record_response(req, response=response):
        raise AmbiguousRequest("request completion lost")
    return response


def _source_urls(observations):
    urls = []
    for row in observations:
        supplied = row.get("source_urls") or []
        if not isinstance(supplied, list):
            supplied = []
        for value in [*supplied, row.get("source_url")]:
            url = public_url(value)
            if url and url not in urls:
                urls.append(url)
    # The story already contains its X passages. Use linked non-social sources first.
    return sorted(
        urls,
        key=lambda url: (
            (urlsplit(url).hostname or "").casefold()
            in {"x.com", "www.x.com", "twitter.com", "www.twitter.com", "t.co"}
        ),
    )


def _query(name, observations, *, jobs_only):
    for row in observations:
        affiliation = row.get("affiliation") or {}
        org = (
            affiliation.get("organization")
            or affiliation.get("brand_id")
            or affiliation.get("company_id")
        )
        match = (
            re.search(re.escape(str(org)), row.get("passage", ""), re.IGNORECASE)
            if org
            else None
        )
        if match:
            return f'"{name}" "{match[0][:160]}"'
    # Reuse a grounded employer in the saved story even when the caller passed plain text.
    for row in observations:
        match = re.search(
            rf"{re.escape(name)},?\s+(?:is\s+)?(?:the\s+)?(?:CEO|CTO|researcher|director|founder)"
            r"\s+(?:of|at)\s+([A-Z][\w-]*(?: [A-Z][\w-]*){0,2})",
            row.get("passage", ""),
        )
        if match:
            return f'"{name}" "{match[1]}"'
    suffix = "employment biography" if jobs_only else "portrait"
    return f'"{name}" {suffix}'


def _collect_page(url, name, deadline):
    raw, final, media_type = fetch_before_deadline(
        url, max_bytes=2 * 1024 * 1024, deadline=deadline
    )
    if "html" not in media_type.lower():
        raise ValueError("page_is_not_html")
    return {
        **read_page(raw, name=name, requested_url=url, final_url=final),
        "observed_at": timezone.now().isoformat(),
        "page_sha256": hashlib.sha256(raw).hexdigest(),
    }


def _collect_image(url, deadline):
    data, final, _ = fetch_before_deadline(url, max_bytes=MAX_BYTES, deadline=deadline)
    obj = store_image(data)
    return {"url": final, "sha256": obj.pk, "mime": obj.media_type}


def _read_image(image):
    obj = StaffMediaObject.objects.get(pk=image["sha256"])
    with storages["staff_media"].open(obj.storage_name, "rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES or not data or hashlib.sha256(data).hexdigest() != obj.pk:
        raise PortraitGap("stored_candidate_integrity_failed")
    return data


def _compare_face(person, data, candidate_sha):
    pack = read_graphics_references(
        person.pk, permitted_reuse={"unknown", "permitted", "restricted"}, max_images=10
    )
    reference = next(
        (
            ref
            for ref in pack.references
            if ref.kind == "image"
            and ref.sha256 != candidate_sha
            and (ref.owner_confirmed or ref.source_verified and ref.individual_portrait)
            and ref.suitability != "rejected"
        ),
        None,
    )
    if not reference:
        raise PortraitGap("face_reference_unavailable")
    collector = Path(
        os.environ.get("PERSON_CHINA_COLLECTOR_ROOT")
        or Path.home() / "development/collect-chinese-workers"
    )
    matcher = Path.home() / "development/face-matcher"
    if (
        not (collector / "person_collect/local_faces.py").is_file()
        or not (matcher / ".venv/bin/python").is_file()
        or not all(
            (matcher / "models" / file).is_file()
            and (matcher / "models" / file).stat().st_size >= 1000
            for file in (
                "face_detection_yunet_2023mar.onnx",
                "face_recognition_sface_2021dec.onnx",
            )
        )
    ):
        raise PortraitGap("candidate_file_face_match_runtime_missing")
    with tempfile.TemporaryDirectory() as tmp:
        photo, candidate = Path(tmp) / "reference", Path(tmp) / "candidate"
        photo.write_bytes(reference.data)
        candidate.write_bytes(data)
        # This helper runs the collector's existing file-only OpenCV comparison.
        # Do not invoke its name search, account search, or network workflow.
        script = (
            "import sys,json; from person_collect.local_faces import measure, matching_face; "
            "r=measure(files=[sys.argv[2]],references=[sys.argv[1]])['images'][0]; "
            "print(json.dumps({'face_count':len(r['faces']),'scores':[f['score'] for f in r['faces']],"
            "'matched':len(r['faces'])==1 and matching_face(r) is not None}))"
        )
        run = subprocess.run(
            [sys.executable, "-c", script, str(photo), str(candidate)],
            cwd=tmp,
            env={**os.environ, "PYTHONPATH": str(collector.resolve())},
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if run.returncode:
            raise PortraitGap("candidate_file_face_match_unavailable")
        return {
            "reference_sha256": reference.sha256,
            "reference_media_id": reference.person_media_id,
            "candidate_sha256": candidate_sha,
            **json.loads(run.stdout),
        }


def _reserve_assessment(work):
    def reserve(_owner, _stage, _kind, ceiling, cfg, send, *, request_metadata):
        if ceiling > Decimal(str(cfg.chatter.max_call_usd)):
            raise BudgetExhausted("person assessment exceeds per-call ceiling")

        def measured():
            reply = send()
            estimate = completed_text_cost(reply, request_metadata)
            return {
                **reply,
                "estimated_usd": str(estimate) if estimate is not None else None,
                "billed_usd": reply["usage"].get("provider_reported_cost_usd"),
            }

        return _once(
            work,
            "portrait_assessment",
            {
                "request_hash": request_metadata["request_hash"],
                "reserved_usd": str(ceiling),
                "provider": request_metadata["provider"],
                "model": request_metadata["model"],
            },
            measured,
        )

    return reserve


def _persist(person, work, *, page, image, data, assessment, comparison, search_origin):
    source = page["candidate"]
    credit = (
        assessment.image_credit
        if assessment.image_credit and assessment.image_credit in source["caption"]
        else ""
    )
    license_text = (
        assessment.image_license
        if assessment.image_license and assessment.image_license in source["caption"]
        else ""
    )
    entry = {
        "expected_sha256": image["sha256"],
        "person_key": str(person.pk),
        "candidate_person_id": str(person.pk),
        "role": "identity-still",
        "source_url": page["source_url"],
        "original_url": image["url"],
        "identity_resolution": {
            "state": "verified",
            "person_id": str(person.pk),
            "evidence": [assessment.identity_quote, assessment.attribution_quote],
        },
        "source_evidence": {
            "page": page,
            "assessment": assessment.model_dump(),
            "face_comparison": comparison,
        },
        "credit": credit or f"Source: {page['source_url']} (image creator unconfirmed)",
        "credit_as_recorded": credit or None,
        "credit_origin": "caption" if credit else "source_page",
        "reuse_status": "unknown",
        "license": license_text or None,
    }
    with transaction.atomic():
        current = Person.objects.select_for_update().get(pk=person.pk)
        if current.merged_into_id or not lease_live(work):
            raise PortraitGap("person_or_lease_changed")
        row, created = ingest_portrait_bytes(
            person=current,
            entry=entry,
            data=data,
            storage=storages["staff_media"],
            observed_at=parse_datetime(page["observed_at"]),
            provider=search_origin,
        )
        if created:
            row = review_media(
                row,
                reviewer="person-portrait assessment",
                reason=assessment.attribution_quote,
                source_verified=True,
                individual_portrait=True,
                suitability="approved",
                reuse_status=row.reuse_status,
            )
        return (
            row.pk
            if row.suitability != "rejected" and row.individual_portrait
            else None
        )


def research_general_portrait(
    *, person, subject, evidence, facematch=False, work=None, jobs=False, portrait=True
):
    """Research one portrait, preserving attempt ceilings and the actual source evidence."""
    start = time.monotonic()
    result = {"status": "needs_evidence", "evidence": [], "asset_ids": [], "gaps": []}
    try:
        if (
            work is None
            or person is None
            or person.merged_into_id
            or work.person_id != person.pk
            or not subject
            or not lease_live(work)
        ):
            raise PortraitGap("resolved_person_and_running_receipt_required")
        observations = (
            [evidence] if isinstance(evidence, dict) else list(evidence or [])
        )
        if jobs:
            prior = StaffIntake.objects.filter(
                person=person, payload__person_intake__has_key="affiliation"
            ).order_by("-observed_at")
            for payload in prior.values_list("payload", flat=True)[:12]:
                known = payload["person_intake"]
                if (
                    known.get("passage")
                    and known.get("observed_at")
                    and known.get("source_url")
                ):
                    if known not in observations:
                        observations.append(known)
                    if known.get("affiliation"):
                        result["evidence"].append(
                            {**known, "person_id": str(person.pk)}
                        )
        _lookup(
            person,
            subject,
            observations,
            work,
            facematch,
            result,
            jobs=jobs,
            portrait=portrait,
        )
    except (BudgetExhausted, AmbiguousRequest) as exc:
        result["status"] = "needs_review"
        result["gaps"].append(type(exc).__name__)
    except PortraitGap as exc:
        result["gaps"].append(str(exc))
    except Exception as exc:  # noqa: BLE001 -- one failed intake cannot interrupt Chatter
        result["status"] = "needs_review"
        result["gaps"].append("portrait_research_failed:" + type(exc).__name__)
    result.update(_report(work))
    result["counters"]["duration_seconds"] = round(time.monotonic() - start, 3)
    return result


def _lookup(person, subject, observations, work, facematch, result, *, jobs, portrait):
    first = (
        StaffProviderRequest.objects.filter(work=work, provider__in=LIMITS)
        .order_by("pk")
        .first()
    )
    # A deliberate operator resume gets a fresh wall-clock window. Previously
    # journaled requests still own their individual attempt and spending limits.
    resumed = work.context.get("resumed_after_configuration_at")
    start = (
        max(first.created_at, datetime.fromisoformat(resumed))
        if first and resumed
        else (first.created_at if first else None)
    )
    elapsed = (timezone.now() - start).total_seconds() if start else 0
    deadline = time.monotonic() + PAGE_SECONDS - elapsed
    urls = _source_urls(observations)
    visited = set()
    pages = []
    origin = "story_source"
    while len(visited) < LIMITS["portrait_page"]:
        if not urls:
            if origin == "exa":
                break
            origin = "exa"
            key = os.environ.get("EXA_API_KEY")
            if not key:
                result["gaps"].append("exa_credential_unavailable")
                break
            query = _query(subject, observations, jobs_only=jobs and not portrait)
            group = _once(
                work,
                "portrait_exa",
                {
                    "query": query,
                    "reserved_usd": str(EXA_SEARCH_ESTIMATE_PER_QUERY_USD),
                },
                partial(
                    search_exa_query,
                    query,
                    api_key=key,
                    timeout=max(0.01, min(15, deadline - time.monotonic())),
                ),
                deadline=deadline,
            )
            urls = [row["url"] for row in group["results"] if row["url"] not in visited]
            if not urls:
                break
        url = urls.pop(0)
        if url in visited:
            continue
        visited.add(url)
        try:
            page = _once(
                work,
                "portrait_page",
                {"url": url, "subject": subject},
                partial(_collect_page, url, subject, deadline),
                deadline=deadline,
            )
        except PortraitGap as exc:
            result["gaps"].append(str(exc))
            if str(exc) == "retrieval_deadline":
                break
            continue
        if page["candidate"] or contains_name(page["passage"], subject):
            pages.append((page, origin))
        if (portrait and page["candidate"]) or (
            not portrait and contains_name(page["passage"], subject)
        ):
            break
    if not pages:
        raise PortraitGap("no_source_page_identifies_subject")
    page, origin = pages[-1]
    data = image = comparison = None
    if portrait and page["candidate"]:
        url = page["candidate"]["url"]
        try:
            image = _once(
                work,
                "portrait_image",
                {"url": url},
                lambda: _collect_image(url, deadline),
                deadline=deadline,
            )
            if image["mime"] in MIME_TYPES:
                data = _read_image(image)
            else:
                result["gaps"].append("unsupported_cast_image_format")
        except PortraitGap as exc:
            result["gaps"].append(str(exc))
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise PortraitGap("assessment_credential_unavailable")
    reply = assess_source(
        subject=subject,
        observations=observations,
        additional_sources=[source for source, _ in pages[:-1]],
        page=page,
        data=data,
        jobs=jobs,
        reservation=_reserve_assessment(work),
    )
    assessment = PortraitAssessment.model_validate(reply["data"])
    recovered = grounded_observation(assessment, page, subject)
    if not recovered:
        result["status"] = "identity_unresolved"
        raise PortraitGap("source_does_not_resolve_identity")
    from core.staff_assets.person_intake import create_or_update_person

    # A story can name an already resolved person while a newly fetched
    # page describes a different namesake. Resolve that page on its own.
    namesakes = (
        PersonName.objects.filter(
            full_name__iexact=subject, person__merged_into__isnull=True
        )
        .exclude(review_status="rejected")
        .exclude(person=person)
    )
    if namesakes.exists():
        independent = create_or_update_person(
            subject, recovered, needs=set(), apply=False
        )
        if independent["person_id"] != str(person.pk):
            result["status"] = "identity_unresolved"
            raise PortraitGap("source_does_not_disambiguate_namesakes")

    recovered["person_id"] = str(person.pk)
    verified = create_or_update_person(subject, recovered, needs=set(), apply=False)
    if "personal_account_unresolved" in verified["gaps"]:
        # A self-link to a handle absent from the catalog cannot establish an
        # account row. Preserve the source link separately from the person claim.
        result["gaps"].append("personal_account_unresolved")
        recovered["unresolved_personal_account"] = recovered.pop("personal_account")
        verified = create_or_update_person(subject, recovered, needs=set(), apply=False)
    if verified["person_id"] != str(person.pk):
        result["status"] = "identity_unresolved"
        result["gaps"].extend(verified["gaps"])
        raise PortraitGap("conflicting_identity_observation")
    result["evidence"].append(recovered)
    if jobs:
        for claim in grounded_job_history(
            assessment, [source for source, _ in pages], subject
        ):
            sourced = {**claim, "person_id": str(person.pk)}
            if sourced not in result["evidence"]:
                result["evidence"].append(sourced)
        if not any(item.get("affiliation") for item in result["evidence"]):
            result["gaps"].append("job_history_unresolved")
    if not portrait:
        result["status"] = (
            "needs_evidence"
            if "job_history_unresolved" in result["gaps"]
            else "complete"
        )
        return
    if not data or not portrait_supported(assessment, page, subject):
        raise PortraitGap("portrait_unusable_or_unattributed:" + assessment.image)
    if facematch:
        comparison = _compare_face(person, data, image["sha256"])
        result["face_comparison"] = comparison
        if not comparison["matched"]:
            raise PortraitGap("face_match_inconclusive")
    asset_id = _persist(
        person,
        work,
        page=page,
        image=image,
        data=data,
        assessment=assessment,
        comparison=comparison,
        search_origin=origin,
    )
    if not asset_id:
        raise PortraitGap("saved_media_review_conflict")
    result.update(status="complete", asset_ids=[asset_id])
