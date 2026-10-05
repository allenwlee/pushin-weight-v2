"""Choose a subject, then a verified usable image, independently of layout."""

from django.db.models import Case, Value, When
from django.utils import timezone

from core.models import (
    EditorialPicture,
    PersonAccount,
    PersonBrandAffiliation,
    PersonMedia,
)
from core.staff_assets.media import fetch_public, media_storage, store_image

from .contracts import digest


def photo_eligible(photo, cfg):
    return (
        photo.source_verified
        and photo.individual_portrait
        and photo.suitability == "approved"
        and photo.availability == "available"
        and photo.reuse_status in cfg.permitted_reuse
        and photo.media_id
        and media_storage().exists(photo.media.storage_name)
    )


def role_current(role):
    today = timezone.now().date().isoformat()
    return (
        role.status == "current"
        and role.review_status == "confirmed"
        and role.superseded_by_id is None
        and role.person.merged_into_id is None
        and (not role.start_date or role.start_date <= today[: len(role.start_date)])
        and (not role.end_date or role.end_date > today[: len(role.end_date)])
    )


def assignment_eligible(row, cfg, *, affiliations=None):
    if (
        not row.source_media_id
        or row.provenance.get("reuse_status") not in cfg.permitted_reuse
    ):
        return False
    if row.person_media_id:
        role_id = row.provenance.get("affiliation_id")
        role = (
            affiliations.get(role_id)
            if affiliations is not None
            else PersonBrandAffiliation.objects.select_related("person")
            .filter(pk=role_id)
            .first()
        )
        if (
            not role
            or role.person_id != row.person_media.person_id
            or role.brand_id not in row.provenance.get("brand_keys", [])
            or not role_current(role)
            or row.source_media_id != row.person_media.media_id
            or not photo_eligible(row.person_media, cfg)
        ):
            return False
    return media_storage().exists(row.source_media.storage_name)


def candidate_roles(event, packet):
    subjects = [str(p) for p in event.person_ids]
    authors = {
        p.get("author_id") for p in packet.get("posts", []) if p["id"] in event.post_ids
    }
    author_people = {
        str(p)
        for p in PersonAccount.objects.filter(
            account_id__in=authors, resolution_status="confirmed"
        ).values_list("person_id", flat=True)
    }
    roles = list(
        PersonBrandAffiliation.objects.filter(
            brand_id__in=event.brand_keys,
            status="current",
            review_status="confirmed",
            superseded_by__isnull=True,
            person__merged_into__isnull=True,
        )
        .select_related("person")
        .annotate(
            candidate_group=Case(
                When(person_id__in=subjects, then=Value(0)),
                When(person_id__in=author_people, then=Value(1)),
                When(affiliation_type="founder", then=Value(2)),
                default=Value(3),
            )
        )
        .order_by("candidate_group", "person_id", "id")[:500]
    )
    roles = [r for r in roles if role_current(r)]

    def priority(role):
        pid = str(role.person_id)
        text = " ".join(
            v or ""
            for v in (
                role.team,
                role.job_function,
                role.title_normalized,
                role.title_raw,
            )
        ).casefold()
        if pid in subjects:
            return (0, subjects.index(pid))
        if not subjects and pid in author_people:
            return (1, 0)
        if event.subject_kind == "company_direction" and (
            role.affiliation_type == "founder"
            or any(
                x in text
                for x in ("ceo", "chief executive", "首席执行官", "最高経営責任者")
            )
        ):
            return (2, 0)
        if event.subject_kind == "agent_release" and any(
            x in text for x in ("agent", "智能体", "エージェント")
        ):
            return (2, 0)
        if event.subject_kind == "model_release" and any(
            x in text for x in ("research", "研究")
        ):
            return (2, 0)
        if role.affiliation_type == "founder":
            return (3, 0)
        return (9, 0)

    return [
        (priority(r), r)
        for r in sorted(roles, key=lambda r: (priority(r), str(r.person_id)))
        if priority(r)[0] < 9
    ]


def select_picture(
    event,
    packet,
    cfg,
    *,
    content_kind,
    content_id,
    revision,
    source_platform="x",
    assessment=None,
    visual_brief="",
):
    mode = cfg.picture_mode(content_kind, source_platform)
    if mode == "off":
        return None
    revision_hash = digest(
        {
            "revision": revision,
            "source": event.source_image_url,
            "people": [str(p) for p in event.person_ids],
            "treatment": "picture-v1",
            "brief": visual_brief,
        }
    )
    source = photo = None
    provenance = {
        "post_ids": event.post_ids,
        "brand_keys": event.brand_keys,
        "named_people": [str(p) for p in event.person_ids],
        "fallback": False,
    }
    if event.visual_essential:
        allowed = {
            url
            for p in packet.get("posts", []) + packet.get("context", [])
            if p["id"] in event.post_ids
            for url in p.get("images", [])
        }
        if event.source_image_url in allowed and "unknown" in cfg.permitted_reuse:
            source = store_image(fetch_public(event.source_image_url))
            provenance.update(
                source_url=event.source_image_url,
                source_kind="original_post",
                reuse_status="unknown",
            )
        else:
            provenance["missing_reason"] = (
                "essential source image unavailable or reuse policy disallows unknown"
            )
    else:
        roles = candidate_roles(event, packet)
        photos = (
            PersonMedia.objects.filter(
                person_id__in=[r.person_id for _, r in roles],
                source_verified=True,
                individual_portrait=True,
                suitability="approved",
                availability="available",
                reuse_status__in=cfg.permitted_reuse,
                media__isnull=False,
            )
            .select_related("media", "person")
            .order_by("-media__width", "-media__height", "-observed_at", "id")
        )
        by_person = {}
        for candidate in photos:
            if photo_eligible(candidate, cfg):
                by_person.setdefault(candidate.person_id, candidate)
        for priority, role in roles:
            if role.person_id in by_person:
                photo = by_person[role.person_id]
                source = photo.media
                provenance.update(
                    person_id=str(role.person_id),
                    person_name=role.person.display_name,
                    affiliation_id=role.pk,
                    role=role.title_raw or role.affiliation_type,
                    source_url=photo.source_url,
                    source_kind="verified_person",
                    fallback=priority[0] == 3
                    or bool(
                        event.person_ids and role.person_id not in event.person_ids
                    ),
                    reuse_status=photo.reuse_status,
                )
                break
    treatment = {
        "chatter": "Humorous editorial illustration with light visual wordplay grounded in this story.",
        "pulse": "Restrained editorial illustration; preserve the person and factual context.",
        "atomic": "Faithful source illustration; no imposed editorial joke.",
        "current_headline": "Restrained editorial illustration of the supported subject.",
    }[content_kind]
    treatment += (
        " Preserve identity. Do not depict fabricated real actions or add fake quotations. "
        + visual_brief
    )
    # Re-evaluate G1 corrections and newly available portraits before cache reuse.
    # A changed source creates a new assignment; prior source/derivative receipts survive.
    revision_hash = digest(
        [
            revision_hash,
            source.pk if source else None,
            photo.pk if photo else None,
            provenance.get("affiliation_id"),
        ]
    )
    row, _ = EditorialPicture.objects.get_or_create(
        content_kind=content_kind,
        content_id=str(content_id),
        revision_hash=revision_hash,
        defaults={
            "source_platform": source_platform,
            "assessment": assessment,
            "source_media": source,
            "person_media": photo,
            "provenance": provenance,
            "treatment": treatment,
            "mode": mode,
            "state": "selected" if source else "missing",
        },
    )
    return row
