"""Small source adapters; every content kind uses the same picture selector."""

from django.db.models import Q
from django.utils import timezone

from core.models import (
    BrandTrendNarrative,
    EditorialEdition,
    Post,
    PostSynthesisArtifact,
)

from .config import load_editorial_config
from .contracts import Event, digest
from .evidence import post_evidence
from .media import start_derivative
from .persistence import claim_assessment, finish_assessment
from .pictures import select_picture


def narrative_posts(narrative):
    """Older headlines retain opaque evidence IDs. Resolve exact original text/time only."""
    clauses = Q(pk__in=[])
    evidence = narrative.selected_evidence_packet or []
    if isinstance(evidence, dict):
        evidence = evidence.get("evidence", [])
    if not isinstance(evidence, list):
        return []
    for source in evidence[:50]:
        original = source.get("original_text") or source.get(
            source.get("text_aliases", {}).get("original_text", ""), ""
        )
        if (
            source.get("evidence_id") in narrative.cited_evidence_ids
            and original
            and not source.get("excerpt_truncated")
            and source.get("created_at")
        ):
            clauses |= Q(text=original, created_at=source["created_at"])
    return list(
        Post.objects.filter(
            clauses,
            brands__brand_id=narrative.brand_key_snapshot,
            created_at__lte=narrative.run.facts_as_of,
            fetched_at__lte=narrative.run.facts_as_of,
        )
        .distinct()
        .prefetch_related("brands")[:50]
    )


def content_input(kind, content_id):
    if kind in {"chatter", "pulse"}:
        edition = EditorialEdition.objects.get(pk=content_id, track=kind)
        return (
            Event.model_validate(edition.selection),
            {"posts": edition.evidence["sources"]},
            edition.fingerprint,
        )
    if kind == "atomic":
        artifact = PostSynthesisArtifact.objects.select_related("post").get(
            pk=content_id, state="succeeded", is_current=True
        )
        posts = list(
            Post.objects.filter(pk=artifact.post_id).prefetch_related("brands")
        )
        summary = artifact.post.text or ""
        revision = artifact.input_context_fingerprint
    elif kind == "current_headline":
        narrative = BrandTrendNarrative.objects.select_related("run").get(
            pk=content_id, status="approved"
        )
        posts = narrative_posts(narrative)
        summary = narrative.headline_en + " " + narrative.secondary_en
        revision = digest([narrative.pk, narrative.headline_en, narrative.secondary_en])
    else:
        raise ValueError("unsupported picture content kind")
    if not posts or any(p.created_at is None for p in posts):
        raise ValueError("original source unavailable")
    packet = {"posts": [post_evidence(post) for post in posts]}
    brands = list(dict.fromkeys(b for p in packet["posts"] for b in p["brand_keys"]))
    event = Event(
        key="content-" + digest([kind, str(content_id)])[:24],
        summary=summary[:2000] or "Source commentary",
        post_ids=[str(p.pk) for p in posts],
        brand_keys=brands[:10],
        occurred_at=max(p.created_at for p in posts),
        chatter=False,
        pulse=False,
        importance=0,
        reason="Existing content picture binding",
    )
    return event, packet, revision


def picture_for_content(kind, content_id, *, source_platform="x", cfg=None):
    configured = cfg is not None
    cfg = cfg or load_editorial_config()
    if cfg.picture_mode(kind, source_platform) == "off":
        return {"state": "off"}
    event, packet, revision = content_input(kind, content_id)
    assessment = claim_assessment(
        timezone.now(),
        "picture-binding",
        scope="picture:" + digest([kind, str(content_id)]),
    )
    if assessment is None:
        return {"state": "already_claimed"}
    try:
        row = select_picture(
            event,
            packet,
            cfg,
            content_kind=kind,
            content_id=content_id,
            revision=revision,
            source_platform=source_platform,
            assessment=assessment,
        )
        row = start_derivative(
            row, assessment, cfg if configured else load_editorial_config()
        )
        if row.state == "pending":
            from .dispatch import dispatch_poll

            dispatch_poll(row.pk)
        result = {"state": row.state, "picture_id": str(row.pk)}
    except Exception as exc:  # noqa: BLE001 - persist bounded worker failure, never report success
        result = {"state": "held", "error": type(exc).__name__}
    finish_assessment(assessment, result)
    return result
