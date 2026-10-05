"""Quarter-hour editorial orchestration; shared evidence, distinct track policies."""

from datetime import datetime

from django.db import transaction
from django.db.models import Max

from core.models import (
    EditorialAssessment,
    EditorialEdition,
    EditorialHero,
    EditorialStory,
)

from .config import load_editorial_config
from .contracts import digest
from .evidence import build_packet
from .media import start_derivative
from .persistence import BudgetHeld, claim_assessment, finish_assessment, require_fence
from .pictures import select_picture
from .providers import json_call
from .selection import aged_priority, should_replace, validate_decisions
from .voices import load_voice
from .writing import editor_request, validate_copy, writer_request


def packet_identity(packet):
    return digest(
        {
            k: packet[k]
            for k in ("posts", "context", "people", "headline_leads", "chart_context")
        }
    )


def find_story(event):
    if event.story_id:
        return EditorialStory.objects.filter(pk=event.story_id).first()
    found = EditorialStory.objects.filter(development_key=event.key).first()
    if found:
        return found
    # Exact source-set duplicates across brand windows share a story. Overlap alone
    # cannot merge two different developments mentioned in one source post.
    for story in EditorialStory.objects.filter(anchor_ids__contains=event.post_ids)[
        :50
    ]:
        if set(story.anchor_ids) == set(event.post_ids):
            return story
    return None


def event_sources(event, packet):
    return [
        p
        for p in packet["posts"] + packet.get("context", [])
        if p["id"] in event.post_ids
    ]


def unchanged(event, story, track):
    if event.change == "unchanged":
        return True
    if not story:
        return False
    latest = story.editions.filter(track=track).order_by("-published_at").first()
    return bool(
        latest
        and (
            latest.selection.get("summary") == event.summary
            or set(latest.evidence.get("post_ids", [])) == set(event.post_ids)
        )
    )


def publish_edition(row, event, packet, track, voice, copy, model, cfg):
    with transaction.atomic():
        require_fence(row)
        EditorialHero.objects.get_or_create(key=f"{track}:{voice.locale}")
        hero = (
            EditorialHero.objects.select_for_update(of=("self",))
            .select_related("edition__assessment")
            .get(pk=f"{track}:{voice.locale}")
        )
        if hero.edition and hero.edition.assessment.cutoff > row.cutoff:
            return None
        if track == "chatter" and not should_replace(
            event, hero.edition, row.cutoff, cfg
        ):
            return None
        if row.editions.filter(track=track, locale=voice.locale).count() >= (
            1 if track == "chatter" else cfg.pulse_limit
        ):
            return None
        story = find_story(event)
        if story is None:
            story, _ = EditorialStory.objects.get_or_create(
                development_key=event.key, defaults={"anchor_ids": event.post_ids}
            )
        story = EditorialStory.objects.select_for_update().get(pk=story.pk)
        # Locale variants in this assessment are one publication, not new facts.
        prior = (
            story.editions.filter(track=track, locale=voice.locale)
            .order_by("-published_at")
            .first()
        )
        if prior and (
            prior.assessment.cutoff > row.cutoff
            or prior.selection.get("summary") == event.summary
            or set(prior.evidence.get("post_ids", [])) == set(event.post_ids)
        ):
            return None
        sources = event_sources(event, packet)
        fingerprint = digest({"sources": sources, "summary": event.summary})
        revision = (
            story.editions.filter(track=track, locale=voice.locale).aggregate(
                n=Max("revision")
            )["n"]
            or 0
        ) + 1
        edition = EditorialEdition.objects.create(
            story=story,
            assessment=row,
            track=track,
            locale=voice.locale,
            revision=revision,
            headline=copy.headline,
            byline=copy.byline,
            article=copy.article,
            importance=event.importance,
            occurred_at=event.occurred_at,
            fingerprint=fingerprint,
            voice={"id": voice.id, "version": voice.version, "hash": voice.digest},
            model=model,
            evidence={
                "post_ids": event.post_ids,
                "sources": sources,
                "cutoff": packet["cutoff"],
                "coverage": packet.get("coverage", {}),
            },
            selection=event.model_dump(mode="json"),
        )
        story.anchor_ids = list(dict.fromkeys(story.anchor_ids + event.post_ids))[-200:]
        story.save(update_fields=["anchor_ids"])
        if track == "chatter":
            hero.edition = edition
            hero.save(update_fields=["edition"])
        return edition


def run_editorial(envelope, *, cfg=None, call=json_call, policy_reader=None):
    configured = cfg is not None
    cfg = cfg or load_editorial_config()
    if policy_reader is None:
        policy_reader = (lambda: cfg) if configured else load_editorial_config
    if not cfg.enabled:
        return {"status": "disabled", "published": 0}
    if (
        envelope.get("schema_version") != 1
        or envelope.get("dry_run") is not False
        or envelope.get("outcome") not in {"completed", "degraded"}
    ):
        return {"status": "ineligible", "published": 0}
    row = claim_assessment(
        datetime.fromisoformat(envelope["completed_at"]),
        str(envelope["source_cycle_id"]),
    )
    if row is None:
        return {"status": "already_claimed", "published": 0}
    outcome = {"status": "complete", "published": 0, "holds": []}
    try:
        packet = row.packet or build_packet(row.cutoff, cfg)
        with transaction.atomic():
            current = require_fence(row)
            current.packet = packet
            current.save(update_fields=["packet"])
        identity = packet_identity(packet)
        previous = (
            EditorialAssessment.objects.filter(
                scope="editorial", state="complete", cutoff__lt=row.cutoff
            )
            .order_by("-cutoff")
            .first()
        )
        if not packet["posts"] or (
            previous and previous.outcome.get("packet_identity") == identity
        ):
            outcome.update(status="unchanged", packet_identity=identity)
            finish_assessment(row, outcome)
            return outcome
        response = call(
            row, "editor:v1", cfg.routes["editor"], editor_request(packet, cfg), cfg
        )
        decisions = validate_decisions(response["data"], packet)
        with transaction.atomic():
            current = require_fence(row)
            current.decisions = decisions.model_dump(mode="json")
            current.save(update_fields=["decisions"])
        outcome["packet_identity"] = identity
        ordered = sorted(
            decisions.events,
            key=lambda e: (
                -aged_priority(e.importance, e.occurred_at, row.cutoff, cfg),
                e.key,
            ),
        )
        for track, limit in (("chatter", 1), ("pulse", cfg.pulse_limit)):
            selected = 0
            for event in ordered:
                if selected >= limit:
                    break
                if not getattr(event, track) or unchanged(
                    event, find_story(event), track
                ):
                    continue
                hero = (
                    EditorialHero.objects.filter(key=f"{track}:en")
                    .select_related("edition")
                    .first()
                )
                if track == "chatter" and not should_replace(
                    event, hero.edition if hero else None, row.cutoff, cfg
                ):
                    continue
                accepted = False
                for binding, profile in cfg.voices.items():
                    if not binding.startswith(track + ":"):
                        continue
                    locale = binding.split(":", 1)[1]
                    fresh = policy_reader()
                    if not fresh.enabled:
                        raise BudgetHeld("disabled before writer")
                    voice = load_voice(profile)
                    if (voice.track, voice.locale) != (track, locale):
                        raise ValueError("voice binding mismatch")
                    request = writer_request(event, packet, voice, fresh)
                    stage = (
                        f"writer:{track}:{locale}:{digest([event.key, voice.digest])}"
                    )
                    try:
                        response = call(row, stage, fresh.routes[track], request, fresh)
                        copy = validate_copy(response["data"], event, locale)
                        fresh = policy_reader()
                        if not fresh.enabled:
                            raise BudgetHeld("disabled before publication")
                        edition = publish_edition(
                            row,
                            event,
                            packet,
                            track,
                            voice,
                            copy,
                            response["model"],
                            fresh,
                        )
                    except (ValueError, TypeError) as exc:
                        outcome["holds"].append(
                            {
                                "track": track,
                                "key": event.key,
                                "reason": type(exc).__name__,
                            }
                        )
                        continue
                    if not edition:
                        continue
                    accepted = True
                    outcome["published"] += 1
                    try:
                        picture = select_picture(
                            event,
                            packet,
                            fresh,
                            content_kind=track,
                            content_id=edition.pk,
                            revision=edition.fingerprint,
                            assessment=row,
                            visual_brief=copy.visual_brief,
                        )
                        if picture:
                            picture = start_derivative(picture, row, policy_reader())
                            if picture.state == "pending":
                                from .dispatch import dispatch_poll

                                dispatch_poll(picture.pk)
                    except Exception as exc:  # noqa: BLE001 - persist bounded worker failure, never report success
                        outcome["holds"].append(
                            {
                                "track": track,
                                "stage": "picture",
                                "reason": type(exc).__name__,
                            }
                        )
                selected += int(accepted)
        finish_assessment(row, outcome)
    except Exception as exc:  # noqa: BLE001 - persist bounded worker failure, never report success
        outcome.update(status="held", error=type(exc).__name__)
        try:
            finish_assessment(row, outcome)
        except BudgetHeld:
            outcome["status"] = "stale"
    return outcome
