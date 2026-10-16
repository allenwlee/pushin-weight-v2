"""Permanent Post resolution independent of General's transient membership."""

from urllib.parse import urlencode

from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone

from core.models import PostSynthesisArtifact
from monitor.general_readers import (
    _localized,
    jobs_people_facts,
    post_documents,
    public_posts,
    safe_external_url,
    temporal_facts,
)


def source_media(post):
    entities = post.extended_entities or post.entities or {}
    if not isinstance(entities, dict) or not isinstance(
        entities.get("media", []), list
    ):
        return []
    media = []
    for row in entities.get("media", []):
        if not isinstance(row, dict):
            continue
        poster = safe_external_url(row.get("media_url_https") or row.get("media_url"))
        if not poster:
            continue
        video_info = row.get("video_info")
        variants = (
            video_info.get("variants", []) if isinstance(video_info, dict) else []
        )
        video = (
            next(
                (
                    safe_external_url(v.get("url"))
                    for v in variants
                    if isinstance(v, dict)
                    and v.get("content_type") == "video/mp4"
                    and safe_external_url(v.get("url"))
                ),
                "",
            )
            if isinstance(variants, list)
            else ""
        )
        media.append(
            {
                "poster": poster,
                "video": video,
                "alt": str(row.get("ext_alt_text") or ""),
            }
        )
    return media


def read_post(post_id, *, locale="en", commentary=None):
    post = get_object_or_404(public_posts(), pk=post_id)
    item = post_documents([post], locale=locale)[str(post.pk)]
    revisions = PostSynthesisArtifact.objects.filter(
        post=post, state="succeeded"
    ).exclude(review_state__in=["withdrawn", "rejected"])
    if commentary is not None:
        try:
            revision_id = int(commentary)
        except (TypeError, ValueError) as exc:
            raise Http404 from exc
        revision = get_object_or_404(
            revisions.prefetch_related("texts"), pk=revision_id
        )
        item["commentary"] = _localized(
            {row.locale: row.text for row in revision.texts.all()}, locale, "normalized"
        )
        item["commentary"]["artifact_id"] = revision.pk
    as_of = timezone.now()
    facts = []
    for section in ("calendar", "free"):
        facts.extend(temporal_facts([post.pk], section, as_of=as_of)[post.pk])
    for section in ("jobs", "moving"):
        facts.extend(
            jobs_people_facts([post.pk], section, as_of=as_of, locale=locale)[post.pk]
        )
    item["facts"] = facts
    item["media"] = source_media(post)
    params = {"lang": locale}
    if item["commentary"]["artifact_id"]:
        params["commentary"] = item["commentary"]["artifact_id"]
    item["share_url"] = item["url"] + "?" + urlencode(params)
    item["revisions"] = [
        {
            "id": row.pk,
            "completed_at": row.completed_at.isoformat(),
            "url": item["url"]
            + "?"
            + urlencode({"lang": locale, "commentary": row.pk}),
        }
        for row in revisions.order_by("-completed_at", "-pk")[:20]
    ]
    return item
