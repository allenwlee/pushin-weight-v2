"""Saved shared-content projections with the existing story/edition URL contract."""

from types import SimpleNamespace

from django.core import signing
from django.db.models import Case, DateTimeField, F, Q, When, Window
from django.db.models.functions import RowNumber

from core.models import OriginalContentSelection, OriginalContentText
from monitor.original_content import WORKFLOWS, chatter_pool, featured_scope


def text_query(track):
    return (
        OriginalContentText.objects.filter(
            narrative__workflow_key=WORKFLOWS[track],
            narrative__status="approved",
            public_id__isnull=False,
        )
        .annotate(edition_published_at=Case(
            When(narrative__consideration_state__isnull=False, then=F("created_at")),
            default=F("narrative__published_at"), output_field=DateTimeField(),
        ))
        .select_related("narrative__run", "producing_call")
        .defer(
            "narrative__run__snapshot", "narrative__run__config_snapshot",
            "narrative__run__decisions", "narrative__run__outcome",
            "producing_call__request_packet", "producing_call__response_payload",
            "producing_call__provenance",
        )
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
        published_at=text.created_at if parent.consideration_state is not None else parent.published_at,
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


def shared_feed_payload(
    cfg, *, track, locale, cursor, limit, source_locale=None, editorial_group=None,
):
    from monitor.editorial.readers import edition_payload, pictures_for_editions

    requested_locale = locale
    pool_query = text_query(track)
    if source_locale is not None or editorial_group is not None:
        if track != "chatter":
            raise ValueError("only Chatter supports source pools")
        source_locale, editorial_group = chatter_pool(source_locale, editorial_group)
        pool_query = pool_query.filter(
            narrative__source_locale_id=source_locale,
            narrative__editorial_group=editorial_group,
        )
    else:
        # The old global feed remains stable until its caller selects pool mode.
        pool_query = pool_query.filter(narrative__consideration_state__isnull=True)
    if locale != "en" and not pool_query.filter(locale=locale).exists():
        locale = "en"
    query = pool_query.filter(locale=locale).order_by(
        "-edition_published_at", "-public_id"
    )
    if cursor:
        value = signing.loads(cursor, salt="editorial-archive")
        if (
            value["track"] != track or value["locale"] != locale
            or value.get("source_locale") != source_locale
            or value.get("editorial_group") != editorial_group
        ):
            raise ValueError("cursor filter mismatch")
        query = query.filter(
            Q(edition_published_at__lt=value["at"])
            | Q(edition_published_at=value["at"], public_id__lt=value["id"])
        )
    editions = [saved_edition(text) for text in query[: limit + 1]]
    more = len(editions) > limit
    editions = editions[:limit]
    pointer = (
        OriginalContentSelection.objects.filter(
            scope_key=featured_scope(
                WORKFLOWS[track], locale,
                source_locale=source_locale, editorial_group=editorial_group,
            )
        ).first()
        if track == "chatter"
        else None
    )
    selected = pool_query.filter(pk=pointer.text_id, locale=locale).first() if pointer else None
    current = saved_edition(selected) if selected else None
    history = (
        [
            saved_edition(text)
            for text in pool_query
            .filter(locale=locale)
            .exclude(narrative__story_id=current.story_id if current else None)
            .annotate(
                story_rank=Window(
                    expression=RowNumber(),
                    partition_by=[F("narrative__story_id")],
                    order_by=[
                        F("edition_published_at").desc(),
                        F("public_id").desc(),
                    ],
                )
            )
            .filter(story_rank=1)
            .order_by("-edition_published_at", "-public_id")[:5]
        ]
        if track == "chatter"
        else []
    )
    next_cursor = (
        signing.dumps(
            {
                "track": track,
                "locale": locale,
                "source_locale": source_locale,
                "editorial_group": editorial_group,
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
