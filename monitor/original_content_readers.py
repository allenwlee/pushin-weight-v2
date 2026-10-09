"""Saved shared-content projections with the existing story/edition URL contract."""

from types import SimpleNamespace

from django.core import signing
from django.db.models import F, Q, Window
from django.db.models.functions import RowNumber

from core.models import OriginalContentSelection, OriginalContentText
from monitor.original_content import WORKFLOWS


def text_query(track):
    return (
        OriginalContentText.objects.filter(
            narrative__workflow_key=WORKFLOWS[track],
            narrative__status="approved",
            public_id__isnull=False,
        )
        .select_related("narrative__run", "producing_call")
        .prefetch_related("sources")
    )


def saved_edition(text):
    """Read-only compatibility shape; the public UUID never becomes the integer PK."""
    parent = text.narrative
    return SimpleNamespace(
        id=text.public_id,
        pk=text.public_id,
        story_id=parent.story_id,
        track=next(
            track for track, key in WORKFLOWS.items() if key == parent.workflow_key
        ),
        locale=text.locale,
        revision=parent.revision,
        headline=text.headline,
        byline=text.secondary,
        article=text.body,
        published_at=parent.published_at,
        importance=parent.importance,
        occurred_at=parent.occurred_at,
        fingerprint=parent.fingerprint,
        selection=parent.selection,
        evidence=parent.provenance.get("evidence", {}),
        voice=text.provenance.get("voice", {}),
        model=parent.provenance.get("model", ""),
        assessment=SimpleNamespace(cutoff=parent.run.facts_as_of, pk=parent.run_id),
        _original_content_text=text,
    )


def shared_story(story_id, track, locale="en", pinned=None):
    query = text_query(track).filter(narrative__story_id=story_id)
    if pinned:
        query = query.filter(public_id=pinned)
    text = query.filter(locale=locale).order_by("-narrative__revision").first()
    if text is None:
        text = query.filter(locale="en").order_by("-narrative__revision").first()
    return saved_edition(text) if text is not None else None


def shared_feed_payload(cfg, *, track, locale, cursor, limit):
    from monitor.editorial.readers import edition_payload, pictures_for_editions

    requested_locale = locale
    query = text_query(track)
    if locale != "en" and not query.filter(locale=locale).exists():
        locale = "en"
    query = query.filter(locale=locale).order_by(
        "-narrative__published_at", "-public_id"
    )
    if cursor:
        value = signing.loads(cursor, salt="editorial-archive")
        if value["track"] != track or value["locale"] != locale:
            raise ValueError("cursor filter mismatch")
        query = query.filter(
            Q(narrative__published_at__lt=value["at"])
            | Q(narrative__published_at=value["at"], public_id__lt=value["id"])
        )
    editions = [saved_edition(text) for text in query[: limit + 1]]
    more = len(editions) > limit
    editions = editions[:limit]
    pointer = (
        OriginalContentSelection.objects.filter(
            scope_key=f"featured:{WORKFLOWS[track]}:{locale}"
        ).first()
        if track == "chatter"
        else None
    )
    selected = text_query(track).filter(pk=pointer.text_id).first() if pointer else None
    current = saved_edition(selected) if selected else None
    history = (
        [
            saved_edition(text)
            for text in text_query(track)
            .filter(locale=locale)
            .exclude(narrative__story_id=current.story_id if current else None)
            .annotate(
                story_rank=Window(
                    expression=RowNumber(),
                    partition_by=[F("narrative__story_id")],
                    order_by=[
                        F("narrative__published_at").desc(),
                        F("public_id").desc(),
                    ],
                )
            )
            .filter(story_rank=1)
            .order_by("-narrative__published_at", "-public_id")[:5]
        ]
        if track == "chatter"
        else []
    )
    next_cursor = (
        signing.dumps(
            {
                "track": track,
                "locale": locale,
                "at": editions[-1].published_at.isoformat(),
                "id": str(editions[-1].pk),
            },
            salt="editorial-archive",
        )
        if more
        else ""
    )
    all_editions = {
        e.pk: e for e in editions + history + ([current] if current else [])
    }
    pictures = pictures_for_editions(all_editions.values(), cfg)
    payloads = {
        pk: edition_payload(e, cfg, pictures=pictures) for pk, e in all_editions.items()
    }
    return {
        "track": track,
        "locale": locale,
        "requested_locale": requested_locale,
        "hero": payloads[current.pk] if current else None,
        "history": [payloads[e.pk] for e in history],
        "items": [payloads[e.pk] for e in editions],
        "next_cursor": next_cursor,
    }
