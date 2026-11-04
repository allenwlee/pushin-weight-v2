"""Admit retained release dossiers without network calls or attention thresholds."""

from datetime import timedelta
from urllib.parse import urlsplit

from django.utils import timezone

from core.models import EditorialStory, EventDossier
from core.product_release_sources import stored_observations

from .chatter_history import freeze_sources, project_post, validated_packet


def prepare_releases(cutoff):
    dossiers = list(
        EventDossier.objects.filter(
            event_kind_reference__code="product_release",
            merged_into__isnull=True,
            last_seen_at__gte=cutoff - timedelta(hours=2),
            first_seen_at__lte=cutoff,
        )
        .prefetch_related("sources__post")
        .order_by("-last_seen_at")[:201]
    )
    if len(dossiers) > 200:
        raise ValueError(
            "release consideration capacity exceeded; no silent truncation"
        )
    result = {}
    for dossier in dossiers:
        story, _ = EditorialStory.objects.get_or_create(
            event_dossier=dossier,
            defaults={
                "development_key": "dossier:" + str(dossier.pk),
                "anchor_ids": [],
            },
        )
        sources = []
        for source in list(dossier.sources.all())[:20]:
            if source.post_id:
                post = source.post
                if post.text and post.created_at and post.created_at <= cutoff:
                    sources.append(project_post(post))
            else:
                saved = stored_observations([source.collection_observation_id])
                if not saved or not saved[0].source_url:
                    continue
                saved = saved[0]
                text = "\n".join(item.text for item in saved.record.texts)
                if not text:
                    continue
                snapshot = {
                    "kind": "dossier_source",
                    "id": f"dossier-source:{source.pk}",
                    "dossier_source_id": source.pk,
                    "original_text": text[:6000],
                    "url": saved.source_url,
                    "author_handle": urlsplit(saved.source_url).hostname or "",
                    "created_at": saved.published_at.isoformat()
                    if saved.published_at
                    else None,
                    "observed_at": timezone.now().isoformat(),
                    "verification_basis": "saved_record",
                    "excerpt_truncated": len(text) > 6000,
                }
                snapshot = validated_packet(
                    {"schema_version": 1, "sources": {snapshot["id"]: snapshot}}
                )["sources"][snapshot["id"]]
                sources.append(snapshot)
        result[str(story.pk)] = {
            "story": story,
            "dossier": dossier,
            "sources": sources,
            "subject": (
                sources[0]["original_text"][:300]
                if sources
                else "Unresolved retained product-release dossier"
            ),
        }
    return result


def admit_releases(run, producing, consider, prepared=None):
    prepared = prepare_releases(run.facts_as_of) if prepared is None else prepared
    for row in prepared.values():
        packet = validated_packet(run.__class__.objects.get(pk=run.pk).snapshot)
        additions = [
            source for source in row["sources"] if source["id"] not in packet["sources"]
        ]
        if additions:
            freeze_sources(run, additions, fence=run.fence)
        previous = (
            row["story"]
            .content_considerations.exclude(run=run)
            .order_by("-attempted_at")
            .first()
        )
        kind = (
            "release"
            if previous is None or row["dossier"].last_seen_at > previous.attempted_at
            else "memory_only"
        )
        consider(
            run,
            row["story"],
            {
                "schema_version": 1,
                "subject": row["subject"],
                "angle": "Retained release evidence; attention and occurrence date may be unknown.",
                "story_ref": None,
            },
            [s["id"] for s in row["sources"]],
            kind,
            producing,
        )
