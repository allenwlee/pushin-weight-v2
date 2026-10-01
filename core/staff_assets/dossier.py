"""Produce a portable, private review dossier from persisted evidence."""

import shutil
from pathlib import Path
from urllib.parse import urlsplit

from django.template.loader import render_to_string
from django.utils import timezone

from core.models import Person
from core.staff_assets.media import media_storage


def source_url(value):
    return value if value and urlsplit(value).scheme in {"https", "http"} else ""


def dossier_records(*, brand_id):
    people = (
        Person.objects.filter(brand_affiliations__brand_id=brand_id)
        .distinct()
        .select_related("primary_name", "english_name")
        .prefetch_related(
            "names__evidence",
            "media__media",
            "brand_affiliations__evidence",
            "staff_intakes",
            "staff_requests",
            "collection_work",
            "account_links__account",
        )
    )
    result = []
    for person in people:
        intakes = sorted(person.staff_intakes.all(), key=lambda row: row.pk)
        payload = intakes[-1].payload if intakes else {}
        dossier = payload.get("source_dossier", {})
        presentation = dossier.get("presentation", {})
        roles = [
            role
            for role in person.brand_affiliations.all()
            if role.brand_id == brand_id and role.review_status != "rejected"
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
        for key, label in (
            ("job_title_zh", "Chinese job title"),
            ("job_title_en", "English job title"),
        ):
            field = presentation.get("fields", {}).get(key, {})
            title_fields.append(
                {
                    "label": label,
                    "value": field.get("value") or "Not collected",
                    "status": field.get("status", "Unknown"),
                    "source": source_url(field.get("source")),
                    "note": field.get("note", ""),
                }
            )
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
                "eligibility": dossier.get("deepseek", {})
                .get("staff_eligibility", {})
                .get("label", "Stored staff claim"),
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
                "profile_location": dossier.get("location"),
                "profile_location_source": source_url(dossier.get("location_source")),
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
