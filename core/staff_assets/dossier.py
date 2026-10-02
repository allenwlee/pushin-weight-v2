"""Produce a portable, private review dossier from persisted evidence."""

import shutil
from pathlib import Path
from urllib.parse import urlsplit

from django.template.loader import render_to_string
from django.utils import timezone

from core.models import Person
from core.person_affiliations import is_active_claim
from core.staff_assets.media import media_storage


def source_url(value):
    return value if value and urlsplit(value).scheme in {"https", "http"} else ""


def dossier_records(*, brand_id):
    people = (
        Person.objects.filter(brand_affiliations__brand_id=brand_id, merged_into__isnull=True)
        .distinct()
        .select_related("primary_name", "english_name")
        .prefetch_related(
            "names__evidence",
            "media__media",
            "brand_affiliations__evidence",
            "brand_affiliations__texts__translations",
            "texts",
            "staff_intakes",
            "staff_requests",
            "collection_work",
            "account_links__account",
        )
    )
    result = []
    for person in people:
        intakes = sorted(person.staff_intakes.all(), key=lambda row: row.pk)
        payload = next(
            (
                row.payload
                for row in reversed(intakes)
                if row.payload.get("source_dossier")
            ),
            {},
        )
        dossier = payload.get("source_dossier", {})
        presentation = dossier.get("presentation", {})
        roles = [
            role
            for role in person.brand_affiliations.all()
            if role.brand_id == brand_id and is_active_claim(role)
        ]
        if not roles:
            continue
        scope = (
            "current" if any(role.status == "current" for role in roles) else "history"
        )
        names = []
        for name in person.names.all():
            names.append(
                {
                    "value": name.full_name,
                    "language": name.language,
                    "origin": name.origin,
                    "status": name.review_status,
                    "given": name.given_name,
                    "family": name.family_name,
                    "sources": [
                        {
                            "url": source_url(e.source_reference),
                            "reference": e.source_reference,
                            "text": e.source_text,
                            "reason": e.review_reason,
                        }
                        for e in name.evidence.all()
                    ],
                }
            )
        media = []
        for row in person.media.all():
            media.append(
                {
                    "id": row.pk,
                    "object": row.media,
                    "path": "",
                    "kind": row.kind,
                    "availability": row.availability,
                    "source": source_url(row.source_url),
                    "provider": row.discovery_provider,
                    "verified": row.source_verified,
                    "portrait": row.individual_portrait,
                    "qualifies": row.source_verified
                    and row.individual_portrait
                    and row.suitability == "approved"
                    and row.availability == "available",
                    "reason": row.verification_reason
                    or "Source attribution has not been reviewed.",
                    "reuse": row.reuse_status,
                    "caption": row.evidence.get(
                        "caption", row.evidence.get("title", "")
                    ),
                }
            )
        title_fields = []
        for role in roles:
            titles = [row for row in role.texts.all() if row.kind == "title" and row.review_status != "rejected"]
            for row in titles:
                title_fields.append({
                    "label": {"zh-Hans": "Chinese job title", "en": "English job title"}.get(row.language, "Original job title"),
                    "value": row.text, "status": row.review_status + " · " + row.origin,
                    "source": source_url(row.source_reference), "note": row.review_note,
                    "role": role.title_raw or "Title unknown",
                })
                for translation in row.translations.all():
                    title_fields.append({"label": "Job title (" + translation.language + ")",
                        "value": translation.text, "status": "translation · " + translation.provider,
                        "source": source_url(row.source_reference), "note": "Translated from: " + row.text,
                        "role": role.title_raw or "Title unknown"})
            if not titles:
                evidence = list(role.evidence.all())
                title_fields.append({"label": "Original job title", "value": role.title_raw or "Not collected",
                    "status": role.review_status + " · language not recorded",
                    "source": source_url(evidence[0].source_url) if evidence else "", "note": ""})
            if not any(row.language == "en" or any(t.language == "en" for t in row.translations.all()) for row in titles):
                title_fields.append({"label": "English job title", "value": "Not collected", "status": "Translation not requested", "source": "", "note": ""})
        role_rows = []
        for role in roles:
            role_rows.append(
                {
                    "title": role.title_raw or "Title unknown",
                    "status": role.status,
                    "review": role.review_status,
                    "location": role.location or "Unknown",
                    "workplace": role.workplace_type or "Unknown",
                    "start": role.start_date or "Unknown",
                    "end": role.end_date or "Unknown",
                    "team": role.team or "",
                    "sources": [
                        {"url": source_url(e.source_url), "text": e.evidence_text}
                        for e in role.evidence.all()
                    ],
                }
            )
        searches = list(presentation.get("chinese_web", {}).get("attempts", []))
        for request in person.staff_requests.all():
            searches.append(
                {
                    "query": request.parameters.get("q", ""),
                    "provider": request.provider,
                    "status": request.state,
                    "count": len(request.response.get("organic_results", []))
                    if request.state == "complete"
                    else None,
                    "at": request.created_at.isoformat(),
                }
            )
        locations = [row for row in person.texts.all() if row.kind == "location" and row.affiliation_id is None and row.review_status != "rejected"]
        profile_location = max(locations, key=lambda row: (row.observed_at, row.pk), default=None)
        result.append(
            {
                "id": str(person.pk),
                "name": person.english_name.full_name
                if person.english_name_id
                else person.display_name,
                "primary": person.primary_name.full_name
                if person.primary_name_id
                else person.display_name,
                "scope": scope,
                "eligibility": "Current staff claim" if scope == "current" else "Former or dated staff claim",
                "names": names,
                "has_chinese": any(row["language"].startswith("zh") for row in names),
                "has_english": bool(person.english_name_id),
                "titles": title_fields,
                "roles": role_rows,
                "media": media,
                "portrait_count": sum(row["qualifies"] for row in media),
                "searches": searches,
                "search_summary": presentation.get("chinese_web", {}).get(
                    "summary", "No completed search recorded."
                ),
                "profile_location": profile_location.text if profile_location else None,
                "profile_location_source": source_url(profile_location.source_reference) if profile_location else "",
                "suggested_query": dossier.get("xiaohongshu_search", {}).get(
                    "query", ""
                ),
                "category": dossier.get("deepseek", {}).get("category", "other_staff"),
                "accounts": [
                    {
                        "handle": link.account.handle or link.account_id,
                        "status": link.resolution_status,
                    }
                    for link in person.account_links.all()
                ],
            }
        )
    return sorted(
        result,
        key=lambda person: (
            person["scope"] != "current",
            {"founder": 0, "researcher": 1, "c_suite": 2, "other_staff": 3}.get(
                person["category"], 3
            ),
            person["name"],
        ),
    )


def export_dossier(*, brand_id, output):
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    (root / "images").mkdir(exist_ok=True)
    records = dossier_records(brand_id=brand_id)
    storage = media_storage()
    unavailable = 0
    for person in records:
        for media in person["media"]:
            obj = media.pop("object")
            if not obj or media["availability"] != "available":
                continue
            name = "images/" + Path(obj.storage_name).name
            try:
                with (
                    storage.open(obj.storage_name, "rb") as source,
                    (root / name).open("wb") as target,
                ):
                    shutil.copyfileobj(source, target)
                media["path"] = name
            except OSError:
                unavailable += 1
                media["availability"] = "unavailable"
                media["qualifies"] = False
        person["portrait_count"] = sum(row["qualifies"] for row in person["media"])
    counts = {
        scope: sum(person["scope"] == scope for person in records)
        for scope in ("current", "history")
    }
    counts["portrait_gaps"] = sum(
        not person["portrait_count"]
        for person in records
        if person["scope"] == "current"
    )
    html = render_to_string(
        "staff/dossier.html",
        {
            "people": records,
            "brand": brand_id,
            "counts": counts,
            "generated_at": timezone.now(),
        },
    )
    (root / "index.html").write_text(html)
    return {
        "people": len(records),
        **counts,
        "unavailable_storage_objects": unavailable,
        "output": str(root / "index.html"),
    }
