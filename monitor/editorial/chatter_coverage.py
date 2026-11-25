"""Compare published Chatter to gathered evidence inside the existing selection call."""

import re
from datetime import datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import F, Func, Q, TextField, Value, Window
from django.db.models.functions import RowNumber
from pydantic import BaseModel, ConfigDict, Field

from core.event_dossiers import add_claim, attach_source, create_dossier, identity_key
from core.models import (
    EditorialStory,
    EventDossier,
    EventDossierClaim,
    EventDossierSource,
    OriginalContentSource,
    OriginalContentText,
    PersonName,
)
from core.product_release_pipeline import canonical_dossier
from monitor.original_content import advisory_lock, digest

from .chatter_gathering import normalized_headline

LIMIT = 12
Short = Annotated[str, Field(min_length=1, max_length=200)]


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class Passage(Closed):
    source_id: Short
    excerpt: str = Field(min_length=4, max_length=1000)


class Assignment(Closed):
    reader_gets: str = Field(min_length=6, max_length=600)
    support: Passage
    source_detail: str = Field(min_length=2, max_length=160)
    # Short distinguishing words or translations the editor could naturally use.
    # Used to catch a writer citing the new fact while delivering yesterday's copy.
    detail_words: dict[
        Literal["en", "ja", "zh-cn"],
        Annotated[list[Short], Field(min_length=1, max_length=8)],
    ]


class Comparison(Closed):
    candidate_ref: Short
    kind: Literal["human_interest", "personnel_change", "product_release"]
    participants: list[Short] = Field(min_length=1, max_length=5)
    action: Short
    occasion: Short
    same_editions: list[Short] = Field(max_length=36)
    same_dossier: str | None
    passages: list[Passage] = Field(max_length=12)
    assignment: Assignment | None


SELECTOR_INSTRUCTION = (
    " For each candidate with event_history, compare participants, action, timing and cited "
    "passages. Names, tickers, authors and shared roundup posts only nominate a comparison. "
    "Return one event_comparisons entry per such candidate. Identify the original event using "
    "principal participants, a short normalized action and its original date or named occasion. "
    "Use the same identity for follow-ups. List only supplied edition IDs and dossier IDs "
    "that concern this specific event; include each relevant edition in every available language. "
    "Give short verbatim passages from current attributable original sources, limited to this event, "
    "including attributed opinions. Prior editions describe what readers saw and supply no evidence. "
    "What can we tell a reader who already read our last piece? For a continuation propose an "
    "assignment only when a current passage demonstrates a genuinely unused detail, reaction or "
    "development. An unsupported pitch, a new reporter repeating the story, or a peripheral detail "
    "that does not deliver the pitch gets null and no new edition. A meme pitch needs an actual "
    "example. Copy the distinctive detail that actually delivers the assignment verbatim in the original "
    "source language into source_detail; it must occur in the proposed passage. Include short distinctive terms for the new detail in each requested writer locale "
    "(synonyms or translations are fine). First stories have null assignment. No usable evidence "
    "gets no passages. Prefer the stronger supported pitch in each pool."
)


def _editions(query, cutoff):
    return (
        OriginalContentText.objects.filter(
            query,
            narrative__workflow_key="social-brief",
            narrative__status="approved",
            narrative__published_at__lte=cutoff,
            public_id__isnull=False,
            narrative__development__isnull=False,
        )
        .select_related("narrative__development")
        .order_by("-narrative__published_at", "-pk")[:LIMIT]
    )


def previous_coverage(row, evidence):
    """Bound direct and subject lookups separately; neither is limited to the discovery window."""
    pitch, cutoff = row.selection, row.run.facts_as_of
    people = pitch.get("people", [])
    person_ids = set(pitch.get("person_ids", []))
    # A confirmed mention nominates a person for comparison, never the event itself.
    for source in pitch.get("source_identities", []):
        person_ids.update(
            link["person_id"]
            for link in source.get("person_links", [])
            if link.get("role") == "mentioned"
            and link.get("resolution_status") == "confirmed"
        )
    person_ids = sorted(person_ids)[:LIMIT]
    names = (
        list(
            PersonName.objects.filter(person_id__in=person_ids)
            .exclude(review_status="rejected")
            .order_by("pk")
            .values_list("full_name", flat=True)[:LIMIT]
        )
        if person_ids
        else []
    )
    named_subjects = re.findall(
        r"\b[A-Z][\w.-]+(?: [A-Z][\w.-]+){0,2}", pitch.get("subject", "")
    )
    aliases = list(
        dict.fromkeys(
            people
            + names
            + pitch.get("event_aliases", [])
            + [brand for source in evidence for brand in source.get("brand_keys", [])]
            + named_subjects
        )
    )
    direct = Q(narrative__development_id=row.development_id)
    dossier_query = Q(
        sources__post_id__in=[s["id"] for s in evidence if s["kind"] == "x_post"],
        sources__linked_at__lte=cutoff,
    )
    documents = [
        source["dossier_source_id"]
        for source in evidence
        if source["kind"] == "dossier_source"
    ]
    if documents:
        observations = EventDossierSource.objects.filter(pk__in=documents).values(
            "collection_observation_id"
        )
        dossier_query |= Q(
            sources__collection_observation_id__in=observations,
            sources__linked_at__lte=cutoff,
        )
    if row.development.event_dossier_id:
        dossier_query |= Q(pk=row.development.event_dossier_id)
    # Typed reviews can nominate a shared event even when today's reporting uses
    # entirely different posts. Only the selector compares the actual occurrence.
    for alias in aliases[:LIMIT]:
        dossier_query |= Q(current_review__recorded_at__lte=cutoff) & (
            Q(current_review__product_release__observed_name__iexact=alias)
            | Q(current_review__personnel_change__observed_person_name__iexact=alias)
        )
    if person_ids:
        dossier_query |= Q(
            current_review__recorded_at__lte=cutoff,
            current_review__personnel_change__person_id__in=person_ids,
        )
    dossiers = list(
        EventDossier.objects.filter(
            dossier_query, merged_into__isnull=True, first_seen_at__lte=cutoff
        )
        .order_by("pk")
        .values_list("pk", flat=True)
        .distinct()[:LIMIT]
    )
    if dossiers:
        direct |= Q(narrative__development__event_dossier_id__in=dossiers)
    subjects = Q(pk__in=[])
    for person_id in person_ids:
        subjects |= Q(narrative__selection__person_ids__contains=[person_id])
    for alias in [value for value in aliases if len(value.strip()) > 1][:LIMIT]:
        subjects |= (
            Q(narrative__selection__subject__icontains=alias)
            | Q(headline__icontains=alias)
            | Q(secondary__icontains=alias)
            | Q(body__icontains=alias)
        )
    rows = {t.pk: t for t in [*_editions(direct, cutoff), *_editions(subjects, cutoff)]}
    excerpts = {}
    citations = (
        OriginalContentSource.objects.filter(
            text_id__in=rows, position__lt=3, post__isnull=False
        )
        .annotate(
            frozen=Func(
                F("snapshot_run__snapshot"),
                Value("sources"),
                F("post_id"),
                Value("original_text"),
                function="jsonb_extract_path_text",
                output_field=TextField(),
            ),
        )
        .values("text_id", "post_id", "author_label_snapshot", "frozen")
    )
    for citation in citations:
        if citation["frozen"]:
            excerpts.setdefault(citation["text_id"], []).append(
                {
                    "source_id": citation["post_id"],
                    "speaker": citation["author_label_snapshot"],
                    "excerpt": citation["frozen"][:300],
                }
            )
    editions = []
    for text in rows.values():
        content = text.narrative
        event_id = content.development.event_dossier_id
        if event_id and event_id not in dossiers:
            dossiers.append(event_id)
        editions.append(
            {
                "edition_id": str(text.public_id),
                "story_id": str(content.development_id),
                "dossier_id": str(event_id) if event_id else None,
                "locale": text.locale,
                "published": content.published_at.isoformat(),
                "headline": text.headline,
                "angle": text.secondary,
                "article": text.body[:1600],
                "cited_passages": excerpts.get(text.pk, []),
            }
        )
    event_path = "event_dossier_source__event_dossier_id"
    latest_claims = (
        EventDossierClaim.objects.filter(
            event_dossier_source__event_dossier_id__in=dossiers, recorded_at__lte=cutoff
        )
        .annotate(
            recent_rank=Window(
                RowNumber(),
                partition_by=F(event_path),
                order_by=[F("recorded_at").desc(), F("pk").desc()],
            )
        )
        .filter(recent_rank__lte=4)
        .order_by(event_path, "-recorded_at", "-pk")
        .values_list(event_path, "source_excerpt")
    )
    passages = {}
    for event_id, excerpt in latest_claims:
        passages.setdefault(event_id, []).append(excerpt[:360])
    events = [
        {
            "dossier_id": str(event_id),
            "kind": kind,
            "passages": passages.get(event_id, []),
        }
        for event_id, kind in EventDossier.objects.filter(pk__in=dossiers)
        .order_by("pk")
        .values_list("pk", "event_kind_reference__code")
    ]
    return {"editions": editions, "dossiers": events}


def event_schema(base):
    comparison = Comparison.model_json_schema()
    return {
        **base,
        "$defs": comparison.pop("$defs"),
        "properties": {
            **base["properties"],
            "event_comparisons": {"type": "array", "items": comparison},
        },
        "required": [*base["required"], "event_comparisons"],
    }


def decisions_for(raw, candidates, locales):
    """Only cited, attributed current passages can support evidence or a follow-up."""
    by_ref = {row["candidate_ref"]: row for row in candidates if "event_history" in row}
    result = {}
    for value in raw:
        compare = Comparison.model_validate(value)
        ref = compare.candidate_ref
        if ref not in by_ref or ref in result:
            raise ValueError("unknown or duplicate Chatter event comparison")
        candidate = by_ref[ref]
        history = candidate["event_history"]
        editions = {item["edition_id"]: item for item in history["editions"]}
        if (
            len(set(compare.same_editions)) != len(compare.same_editions)
            or set(compare.same_editions) - editions.keys()
        ):
            raise ValueError("unknown or duplicate Chatter edition")
        prior = [editions[key] for key in compare.same_editions]
        kinds = {item["dossier_id"]: item["kind"] for item in history["dossiers"]}
        event_ids = {item["dossier_id"] for item in prior if item["dossier_id"]}
        if compare.same_dossier:
            event_ids.add(compare.same_dossier)
        if len(event_ids) > 1 or any(
            kinds.get(key) != compare.kind for key in event_ids
        ):
            raise ValueError("inconsistent Chatter event dossier")
        matched_stories = {item["story_id"] for item in prior}
        prior = [
            item
            for item in editions.values()
            if item["story_id"] in matched_stories or item["dossier_id"] in event_ids
        ]
        sources = {
            s["id"]: s
            for s in candidate["evidence"]
            if candidate["source_usages"][s["id"]] == "consideration"
            and (s["author_handle"] or s["author_id"])
        }
        passages = [
            p.model_dump()
            for p in compare.passages
            if p.source_id in sources
            and p.excerpt in sources[p.source_id]["original_text"]
        ]
        assignment = compare.assignment
        if assignment and prior:
            support = assignment.support.model_dump()
            original_language = (
                sources.get(support["source_id"], {}).get("source_language", "").lower()
            )
            if original_language in {"zh", "zh-hans", "zh-hans-cn"}:
                original_language = "zh-cn"
            original_terms = assignment.detail_words.get(original_language, [])
            excerpt = normalized_headline(support["excerpt"])
            prior_copy = " ".join(
                normalized_headline(item["angle"] + " " + item["article"])
                for item in prior
                if item["locale"] == original_language
            )
            source_detail = normalized_headline(assignment.source_detail)
            fresh_terms = [
                term
                for term in map(normalized_headline, original_terms)
                if term and term in excerpt and term not in prior_copy
            ]
            if (
                not source_detail
                or source_detail not in excerpt
                or (original_terms and not fresh_terms)
                or support not in passages
                or set(locales) - assignment.detail_words.keys()
                or any(not assignment.detail_words[locale] for locale in locales)
                or any(
                    normalized_headline(support["excerpt"])
                    in normalized_headline(item["article"] + " " + item["angle"])
                    for item in prior
                )
            ):
                assignment = None
        else:
            assignment = None
        event_identity = [
            compare.kind,
            sorted(normalized_headline(p) for p in compare.participants),
            normalized_headline(compare.action),
            normalized_headline(compare.occasion),
        ]
        result[ref] = {
            "kind": compare.kind,
            "identity": identity_key("chatter-event-v1", digest(event_identity)),
            "same_dossier": next(iter(event_ids), None),
            "principals": sorted(
                {normalized_headline(person) for person in compare.participants}
            ),
            "prior": [
                {
                    field: item[field]
                    for field in (
                        "edition_id",
                        "story_id",
                        "dossier_id",
                        "locale",
                        "published",
                        "headline",
                        "angle",
                    )
                }
                for item in prior
            ],
            "passages": passages,
            "assignment": assignment.model_dump() if assignment else None,
        }
    if set(result) != set(by_ref):
        raise ValueError("missing Chatter event comparison")
    return result


def admission_identity(selection, coverage):
    episode = selection.get("episode_id")
    return (
        identity_key("chatter-episode-v1", episode) if episode else coverage["identity"]
    )


def admission_reason(content, coverage, locale):
    """Serialize first publications sharing a principal; check what appeared since selection."""
    if coverage["assignment"]:
        return None
    if coverage["prior"]:
        return "no_continuation_assignment"
    pitch = content.selection
    names = {
        normalized_headline(name)
        for name in [*pitch.get("people", []), *coverage.get("principals", [])]
    }
    people = set(pitch.get("person_ids", []))
    for principal in sorted((names | people) - {""}):
        advisory_lock("chatter-principal:" + principal)
    identity = admission_identity(pitch, coverage)
    advisory_lock("chatter-event:" + identity)
    published = OriginalContentText.objects.filter(
        narrative__workflow_key="social-brief",
        narrative__status="approved",
        public_id__isnull=False,
    )
    known = Q(
        narrative__development__event_dossier__identity_key__in=[
            identity,
            coverage["identity"],
        ]
    )
    if coverage["same_dossier"]:
        known |= Q(
            narrative__development__event_dossier_id=canonical_dossier(
                coverage["same_dossier"]
            ).pk
        )
    if episode := pitch.get("episode_id"):
        known |= Q(narrative__selection__episode_id=episode)
    if content.provenance.get("source_content_id"):
        known |= Q(
            narrative__provenance__source_content_id=content.provenance[
                "source_content_id"
            ]
        )
    if published.filter(known, locale=locale).exists():
        return "event_already_published"
    if published.filter(known).exists():
        return None  # Another language already established this specific event.
    same_principal = Q(pk__in=[])
    for name in pitch.get("people", []):
        same_principal |= Q(narrative__selection__people__contains=[name])
    for person in people:
        same_principal |= Q(narrative__selection__person_ids__contains=[person])
    for name in names - {""}:
        same_principal |= (
            Q(narrative__selection__event_coverage__principals__contains=[name])
            | Q(narrative__selection__subject__icontains=name)
            | Q(secondary__icontains=name)
        )
    if (
        published.filter(
            same_principal, narrative__published_at__gt=content.run.facts_as_of
        )
        .exclude(known)
        .exists()
    ):
        return "coverage_changed"
    return None


@transaction.atomic
def record_event(content, coverage, sources):
    """Bind one canonical dossier/story under lock; keep historical edition URLs intact."""
    story_ids = {row["story_id"] for row in coverage["prior"]}
    story_ids.add(str(content.development_id))
    identity = admission_identity(content.selection, coverage)
    advisory_lock("chatter-event:" + identity)
    stories = {
        str(s.pk): s
        for s in EditorialStory.objects.select_for_update()
        .filter(pk__in=story_ids)
        .order_by("pk")
    }
    prior = sorted(
        coverage["prior"], key=lambda row: (row["published"], row["edition_id"])
    )
    preferred = (
        stories[prior[0]["story_id"]] if prior else stories[str(content.development_id)]
    )
    linked = {
        str(stories[row["story_id"]].event_dossier_id)
        for row in prior
        if stories[row["story_id"]].event_dossier_id
    }
    if coverage["same_dossier"]:
        linked.add(coverage["same_dossier"])
    if episode := content.selection.get("episode_id"):
        linked.update(
            OriginalContentText.objects.filter(
                narrative__selection__episode_id=episode,
                narrative__workflow_key="social-brief",
                narrative__status="approved",
                narrative__development__event_dossier__isnull=False,
            )
            .values_list("narrative__development__event_dossier_id", flat=True)
            .distinct()
        )
    linked = {canonical_dossier(pk).pk for pk in linked}
    if len(linked) > 1:
        return None  # The frozen links now disagree. Reconsider at the next normal selection.
    if linked:
        event = EventDossier.objects.select_for_update().get(pk=linked.pop())
        if event.event_kind_reference.code != coverage["kind"]:
            return None
    else:
        event = create_dossier(
            event_kind=coverage["kind"],
            identity_key=identity,
            first_seen_at=content.run.facts_as_of,
        )
        event = EventDossier.objects.select_for_update().get(
            pk=canonical_dossier(event.pk).pk
        )
    # A concurrent merge can win before our target row lock.
    while event.merged_into_id:
        event = EventDossier.objects.select_for_update().get(pk=event.merged_into_id)
    canonical = EditorialStory.objects.filter(event_dossier=event).first()
    if (
        canonical is None
        and preferred.event_dossier_id
        and preferred.event_dossier_id != event.pk
    ):
        # The discovery development can carry an older link (e.g. a shared
        # roundup). An independently identified event needs its own story.
        canonical, _ = EditorialStory.objects.get_or_create(
            event_dossier=event,
            defaults={"development_key": "dossier:" + str(event.pk)},
        )
    if canonical is None:
        preferred.event_dossier = event
        preferred.save(update_fields=["event_dossier"])
        canonical = preferred
    by_id = {s["id"]: s for s in sources}
    for passage in coverage["passages"]:
        source = by_id[passage["source_id"]]
        if passage["excerpt"] not in source["original_text"]:
            raise ValueError("Chatter claim differs from source")
        if source["kind"] == "x_post":
            attached = attach_source(event.pk, post_id=source["id"])
        else:
            original = EventDossierSource.objects.get(pk=source["dossier_source_id"])
            attached = attach_source(
                event.pk,
                observation_id=original.collection_observation_id,
                post_id=original.post_id,
            )
        date = (
            datetime.fromisoformat(source["created_at"])
            if source["created_at"]
            else None
        )
        add_claim(
            attached.pk,
            claim_kind="attributed_statement",
            scope_key="chatter:reported-statement",
            assertion_text=f"{source['author_handle'] or source['author_id']} reported: {passage['excerpt']}",
            source_excerpt=passage["excerpt"],
            source_locator=source["url"],
            extraction_version="chatter-event-v1",
            effective_at=date,
            effective_precision="datetime" if date else "unknown",
        )
    return canonical


def continuation_handoff(coverage, facts, locale):
    """Pin the specific new excerpt to a distinct, citable fact in the writer packet."""
    assignment = coverage.get("assignment")
    if not assignment:
        return None
    support = assignment["support"]
    fact = next(
        item
        for item in facts
        if item.get("source_id") == support["source_id"]
        and item["source_role"] == "original"
        and support["excerpt"] in item["supporting_passage"]
    )
    lead = {
        **fact,
        "fact_id": fact["fact_id"] + "-NEW",
        "supporting_passage": support["excerpt"],
        "edition_role": "today's assignment",
    }
    for item in facts:
        item["edition_role"] = "background"
    facts.insert(0, lead)
    prior = sorted(
        (item for item in coverage["prior"] if item["locale"] == locale),
        key=lambda item: item["published"],
        reverse=True,
    )

    def publication_date(item):
        return (
            datetime.fromisoformat(item["published"])
            .astimezone(ZoneInfo("Asia/Tokyo"))
            .date()
        )

    earlier = "\n".join(
        f"We already ran “{item['headline']}” on {publication_date(item)} JST "
        f"and covered this angle: {item['angle']}"
        for item in prior
    )
    return (
        f"You're writing the next Chatter piece on this event. Today's assignment is "
        f"{assignment['reader_gets']} Lead with that. Your reader saw the earlier coverage.\n"
        f"{earlier}\nWhat supports today's assignment: {lead['fact_id']}, "
        f"{lead['speaker']}: “{lead['supporting_passage']}”. Carry this detail through the "
        "headline or byline and article and cite its fact ID in both. Write your one best treatment."
    )


def repeat_reason(coverage, canonical, locale, copy, c1, facts):
    if coverage["prior"] and not coverage["assignment"]:
        return "no_continuation_assignment"
    previous = OriginalContentText.objects.filter(
        Q(narrative__development=canonical)
        | Q(public_id__in=[p["edition_id"] for p in coverage["prior"]]),
        locale=locale,
        narrative__workflow_key="social-brief",
        narrative__status="approved",
        public_id__isnull=False,
    )
    prior_ids = {p["edition_id"] for p in coverage["prior"]}
    for edition_id, headline, selection in previous.values_list(
        "public_id", "headline", "narrative__selection"
    ):
        if normalized_headline(copy["headline"]) == normalized_headline(headline):
            return "same_headline"
        if str(edition_id) not in prior_ids:
            if coverage["assignment"] is None:
                return "event_already_published"
            earlier = selection.get("event_coverage", {}).get("assignment")
            if earlier and normalized_headline(
                earlier["support"]["excerpt"]
            ) == normalized_headline(coverage["assignment"]["support"]["excerpt"]):
                return "assignment_already_published"
    if assignment := coverage["assignment"]:
        fact = next(
            item for item in facts if item.get("edition_role") == "today's assignment"
        )
        if (
            fact["fact_id"] not in c1["used_fact_ids"]
            or fact["fact_id"] not in c1["candidates"][0]["used_fact_ids"]
        ):
            return "assignment_not_cited"
        markers = [
            normalized_headline(word) for word in assignment["detail_words"][locale]
        ]
        for part in (copy["headline"] + " " + copy["byline"], copy["article"]):
            if not any(word and word in normalized_headline(part) for word in markers):
                return "assignment_missing_from_copy"
    return None
