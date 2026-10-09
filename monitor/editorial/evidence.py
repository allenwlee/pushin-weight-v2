"""Bounded original-source packets, shared with existing headline projections."""

import math
from datetime import timedelta
from hashlib import sha256
from urllib.parse import urlsplit

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import F, Window
from django.db.models.functions import RowNumber, TruncHour

from core.models import (
    BrandTrendNarrative,
    EditorialEdition,
    EditorialHero,
    PersonBrandAffiliation,
    Post,
    TrendNarrativeRun,
)
from monitor.packet_maker import PacketProfile, encode, make_packet, packet_bytes
from monitor.trend_narrative_packet import project_dossier, project_evidence


def source_images(post):
    media = (post.extended_entities or {}).get("media", [])
    return list(
        dict.fromkeys(
            row.get("media_url_https", "")
            for row in media
            if row.get("type") == "photo"
            and safe_source_image(row.get("media_url_https", ""))
        )
    )[:8]


def safe_source_image(url):
    parsed = urlsplit(url)
    return (
        parsed.scheme == "https"
        and parsed.hostname == "pbs.twimg.com"
        and not parsed.username
        and not parsed.password
        and parsed.port in (None, 443)
    )


def post_evidence(post):
    text = post.text or ""
    row = project_evidence(
        {
            "evidence_id": str(post.pk),
            "original_text": text[:6000],
            "created_at": post.created_at.isoformat(),
            "source_language": post.lang or "",
            "excerpt_truncated": len(text) > 6000,
            "is_quote": bool(post.is_quote or post.quoted_status_id_id),
            "is_retweet": bool(post.is_retweet),
        }
    )
    row.update(
        id=str(post.pk),
        platform="x",
        url=f"https://x.com/i/status/{post.pk}" if str(post.pk).isdigit() else "",
        author_id=post.native_author_id,
        author_handle=post.author_handle or "",
        is_reply=bool(post.is_reply or post.in_reply_to_id),
        parent_post_id=post.in_reply_to_id or "",
        parent_author_handle=post.in_reply_to_username or "",
        quoted_post_id=str(post.quoted_status_id_id or ""),
        quoted_author_handle=post.quoted_author_handle or "",
        stored_quote=(post.quoted_text or "")[:4000],
        local_parent=(getattr(post, "_editorial_parent_text", "") or "")[:4000],
        images=source_images(post),
        brand_keys=[p.brand_id for p in post.brands.all()],
        preparation_revision=post_revision(post),
    )
    return row


def post_revision(post):
    def stored_fields(model):
        return {
            field.attname: getattr(model, field.attname)
            for field in model._meta.concrete_fields
        }

    try:
        enrichment = stored_fields(post.enrichment_state)
    except ObjectDoesNotExist:
        enrichment = None
    return sha256(
        encode(
            {
                "post": stored_fields(post),
                "enrichment": enrichment,
                "classification": [
                    stored_fields(state)
                    for state in sorted(
                        post.classification_states.all(),
                        key=lambda state: state.brand_id,
                    )
                ],
            }
        )
    ).hexdigest()


def build_packet(cutoff, cfg):
    profile = PacketProfile.create(
        "editorial-dispatch",
        cutoff=cutoff,
        max_bytes=cfg.max_packet_bytes,
        settings=cfg.model_dump(mode="json"),
    )
    return make_packet(
        profile,
        lambda: _collect_packet(cutoff, cfg),
        transform=lambda packet: trim_packet(packet, cfg.max_packet_bytes),
    ).payload


def _collect_packet(cutoff, cfg):
    base = Post.objects.filter(
        created_at__lte=cutoff,
        fetched_at__lte=cutoff,
        created_at__gte=cutoff - timedelta(days=7),
    )
    recent = base.filter(created_at__gte=cutoff - timedelta(days=1))
    total = recent.count()
    # Spread the cap across the day; a busy final minute cannot consume every slot.
    sampled = (
        recent.annotate(
            hour_rank=Window(
                expression=RowNumber(),
                partition_by=[TruncHour("created_at")],
                order_by=[F("created_at").desc(), F("tweet_id").asc()],
            )
        )
        .filter(hour_rank__lte=max(1, math.ceil(cfg.max_posts / 24)))
        .order_by("-created_at", "tweet_id")[: cfg.max_posts]
    )
    posts = list(
        sampled.prefetch_related("brands", "enrichment_state", "classification_states")
    )
    brands = {b.brand_id for post in posts for b in post.brands.all()}
    context = (
        list(
            base.filter(
                created_at__lt=cutoff - timedelta(days=1), brands__brand_id__in=brands
            )
            .distinct()
            .order_by("-created_at", "tweet_id")
            .prefetch_related("brands", "enrichment_state", "classification_states")[
                : cfg.max_context_posts
            ]
        )
        if brands
        else []
    )
    parent_ids = {
        post.in_reply_to_id for post in posts + context if post.in_reply_to_id
    }
    parents = dict(
        Post.objects.filter(
            pk__in=parent_ids, created_at__lte=cutoff, fetched_at__lte=cutoff
        ).values_list("pk", "text")
    )
    for post in posts + context:
        post._editorial_parent_text = parents.get(post.in_reply_to_id, "")
    roles = (
        PersonBrandAffiliation.objects.filter(
            brand_id__in=brands,
            review_status="confirmed",
            status="current",
            superseded_by__isnull=True,
        )
        .select_related("person")
        .order_by("person_id", "brand_id")[:200]
    )
    people = [
        {
            "id": str(r.person_id),
            "name": r.person.display_name,
            "brand": r.brand_id,
            "affiliation_id": r.pk,
            "role": r.title_normalized or r.title_raw or r.affiliation_type,
            "team": r.team or "",
            "kind": r.affiliation_type,
        }
        for r in roles
    ]
    editions = list(
        EditorialEdition.objects.filter(
            published_at__lte=cutoff, published_at__gte=cutoff - timedelta(days=7)
        )
        .select_related("story")
        .order_by("-published_at")[:100]
    )
    hero = (
        EditorialHero.objects.filter(key="chatter:en")
        .select_related("edition__story")
        .first()
    )
    if hero and hero.edition and hero.edition not in editions:
        editions.append(hero.edition)
    stories = {}
    for edition in editions:
        key = str(edition.story_id)
        if key not in stories:
            stories[key] = {
                "id": key,
                "key": edition.story.development_key,
                "summary": edition.selection.get("summary", edition.headline),
                "post_ids": edition.story.anchor_ids,
            }
    leads = list(
        BrandTrendNarrative.objects.filter(
            status="approved",
            verified_at__lte=cutoff,
            attempted_at__gte=cutoff - timedelta(days=1),
        )
        .order_by("brand_key_snapshot", "-attempted_at")
        .distinct("brand_key_snapshot")
        .values(
            "brand_key_snapshot", "headline_en", "secondary_en", "cited_evidence_ids"
        )[:40]
    )
    latest_chart = (
        TrendNarrativeRun.objects.filter(
            window_days=1,
            facts_as_of__lte=cutoff,
            facts_as_of__gte=cutoff - timedelta(days=1),
            status__in=["active", "superseded", "terminal"],
        )
        .order_by("-facts_as_of")
        .first()
    )
    chart_context = []
    if latest_chart:
        for dossier in latest_chart.snapshot.get("dossiers", [])[:40]:
            projected = project_dossier(dossier, rank=True)
            chart_context.append(
                {key: projected[key] for key in ("brand_key", "facts", "scopes")}
            )
    packet = {
        "schema": "editorial-evidence-v1",
        "cutoff": cutoff.isoformat(),
        "posts": [post_evidence(p) for p in posts],
        "context": [post_evidence(p) for p in context],
        "people": people,
        "stories": list(stories.values()),
        "headline_leads": leads,
        "chart_support": "available" if chart_context else "unavailable",
        "chart_context": chart_context,
        "coverage": {
            "eligible_24h": total,
            "included_24h": len(posts),
            "sampled": total > len(posts),
            "context_window_days": 7,
            "roles_observed_now": True,
        },
    }
    return packet


def trim_packet(packet, limit):
    """Trim whole rows, reserving a quarter of source bytes for background."""
    coverage = packet["coverage"]
    coverage["included_24h"] = len(packet["posts"])
    coverage["context_before_trim"] = len(packet["context"])
    coverage["included_context"] = len(packet["context"])
    coverage["context_trimmed"] = 0
    for field in ("headline_leads", "people", "stories", "chart_context"):
        while packet_bytes(packet) > limit and packet[field]:
            packet[field].pop()
    packet["chart_support"] = "available" if packet["chart_context"] else "unavailable"
    while packet_bytes(packet) > limit and (packet["posts"] or packet["context"]):
        field = (
            "context"
            if packet_bytes(packet["context"]) > limit // 4 or not packet["posts"]
            else "posts"
        )
        packet[field].pop()
        coverage["sampled"] = True
        coverage["included_24h"] = len(packet["posts"])
        coverage["included_context"] = len(packet["context"])
        coverage["context_trimmed"] = coverage["context_before_trim"] - len(
            packet["context"]
        )
    coverage["included_24h"] = len(packet["posts"])
    coverage["included_context"] = len(packet["context"])
    coverage["context_trimmed"] = coverage["context_before_trim"] - len(
        packet["context"]
    )
    packet["chart_support"] = "available" if packet["chart_context"] else "unavailable"
    if packet_bytes(packet) > limit:
        raise ValueError("packet metadata exceeds evidence cap")
    return packet
