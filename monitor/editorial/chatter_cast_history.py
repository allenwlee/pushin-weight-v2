"""Corroborate Chatter subjects against portraits selected in earlier published editions."""

import re
from collections import defaultdict
from datetime import datetime

from django.utils import timezone

from core.models import OriginalContentText, PersonMedia
from core.staff_assets.person_roles import named_employers, phrase, sourced_role

# Only an attributed leadership role is interchangeable across these expressions.
_EXECUTIVE = r"(?:CEO|chief executive(?: officer)?|president|PDG|patron)"
_ORG = r"[A-Z][\w&-]*(?:[ \t]+[A-Z][\w&-]*){0,2}"
_UNCERTAIN = re.compile(
    r"\b(?:if|whether|assuming|unless|may|might|could|would|should|not|never|"
    r"false(?:ly)?|untrue|den(?:y|ies|ied)|rumou?red|urged?|wants?|hopes?)\b|n[’']t\b",
    re.IGNORECASE,
)


def _observed_by(value, cutoff):
    if not isinstance(value, str):
        return False
    try:
        when = datetime.fromisoformat(value)
    except ValueError:
        return False
    return timezone.is_aware(when) and when <= cutoff


def current_primary_fact(fact, cutoff):
    return (
        fact.get("source_role") == "original"
        and fact.get("source_usage") == "consideration"
        and _observed_by(fact.get("observed_at"), cutoff)
    )


def _statements(passage):
    for match in re.finditer(r"([^.!?;\n]+)([.!?;\n]|$)", passage):
        if match[2] != "?" and not _UNCERTAIN.search(match[1]):
            yield match[1]


def _roles(name, passage):
    """Read an employer and role from an affirmative clause about the known subject."""
    result = set()
    subject = phrase(name)
    french = rf"(?i:{subject},\s*(?:l['’])?(?:ex-|ancien\s+)?(?:patron|PDG)\s+de\s+)(?P<org>{_ORG})"
    for sentence in _statements(passage):
        for match in re.finditer(french, sentence):
            result.add((match["org"], "executive"))
        for org in named_employers(name, sentence):
            role = sourced_role(name, org, sentence)
            if role:
                title = role["title"].casefold()
                result.add(
                    (
                        org,
                        "executive"
                        if re.fullmatch(_EXECUTIVE, title, re.IGNORECASE)
                        else title,
                    )
                )
    return result


def _matches_role(name, org, group, passage):
    # Evaluate one sentence at a time so a board vote cannot inherit an employer
    # or a qualifier from an unrelated item in a market roundup.
    for sentence in _statements(passage):
        if not re.search(phrase(org), sentence, re.IGNORECASE) or not re.search(
            phrase(name), sentence, re.IGNORECASE
        ):
            continue
        if any(
            employer.casefold() == org.casefold() and title == group
            for employer, title in _roles(name, sentence)
        ):
            return True
        if group != "executive":
            continue
        actor = rf"(?i:{phrase(org)})(?: \$?[A-Z]{{2,6}})?(?i:(?:['’]s)?(?: board(?: of directors)?)?)"
        action = r"(?:officially |unanimously )?(?:reinstated|reinstates|appointed|appoints|named|names|reappointed|reappoints|voted (?:unanimously )?to (?:reinstate|appoint|bring))"
        if re.search(
            actor
            + rf"(?i: {action} {phrase(name)}(?: back)? as (?:its |the |an? )?{_EXECUTIVE}\b)",
            sentence,
        ):
            return True
    return False


def confirmed_appearances(people, cutoff):
    """Read the eligible media and earlier published cast for all namesakes together."""
    appearances = defaultdict(set)
    if not people or not cutoff:
        return appearances
    cutoff = datetime.fromisoformat(cutoff)
    media = PersonMedia.objects.filter(
        person_id__in=people,
        person__merged_into__isnull=True,
        observed_at__lte=cutoff,
        availability="available",
        media__isnull=False,
        kind="image",
    ).exclude(suitability="rejected")
    confirmed = {}
    for row in media.only(
        "pk",
        "person_id",
        "media_id",
        "source_verified",
        "individual_portrait",
        "review_history",
    ):
        pid, sha = str(row.person_id), row.media_id
        reviews = [event for event in row.review_history if isinstance(event, dict)]
        owner_confirmed = any(
            event.get("event") == "owner_confirmed_media"
            and event.get("person_id") == pid
            and event.get("sha256") == sha
            and event.get("source_reference")
            and _observed_by(event.get("confirmed_at") or event.get("recorded_at"), cutoff)
            for event in reviews
        )
        source_verified = (
            row.source_verified
            and row.individual_portrait
            and any(
                event.get("source_verified") is True
                and event.get("individual_portrait") is True
                and event.get("reviewer")
                and event.get("reason")
                and _observed_by(event.get("at"), cutoff)
                for event in reviews
            )
        )
        if owner_confirmed or source_verified:
            confirmed[f"person:{row.pk}"] = (pid, sha, row.pk)
    if not confirmed:
        return appearances
    texts = OriginalContentText.objects.filter(
        narrative__workflow_key="social-brief",
        narrative__published_at__lt=cutoff,
        created_at__lt=cutoff,
        public_id__isnull=False,
        producing_call__stage__endswith=":C1",
        producing_call__state="completed",
        producing_call__completed_at__lt=cutoff,
        producing_call__run__workflow_key="graphics-package",
        producing_call__run__snapshot__request__person_ids__has_any_keys=sorted(
            {pid for pid, _, _ in confirmed.values()}
        ),
    ).order_by("-narrative__published_at", "-pk")
    for selected, facts, assets in texts.values_list(
        "producing_call__run__snapshot__request__person_ids",
        "producing_call__run__snapshot__request__handoff__fact_items",
        "producing_call__run__decisions__writer_cast__assets",
    ).iterator():
        for asset in assets or ():
            previous = confirmed.get(asset.get("asset_ref"))
            if not previous or asset.get("role") != "identity_reference":
                continue
            pid, sha, pk = previous
            if (
                pid not in selected
                or pid != asset.get("person_id")
                or sha != asset.get("sha256")
            ):
                continue
            for fact in facts or ():
                if fact.get("fact_id") in asset.get(
                    "fact_ids", ()
                ) and current_primary_fact(fact, cutoff):
                    for org, group in _roles(
                        asset["person_name"], fact["supporting_passage"]
                    ):
                        appearances[pid].add((org, group, pk))
    return appearances


def matching_appearances(name, candidates, facts, appearances, observed_by):
    """Return independently supported identities, keeping their particular facts and portraits."""
    matches = {}
    for pid in candidates & appearances.keys():
        evidence, media = set(), set()
        for org, group, pk in appearances[pid]:
            for fact in facts:
                if current_primary_fact(fact, observed_by) and _matches_role(
                    name, org, group, fact["supporting_passage"]
                ):
                    evidence.add(fact["fact_id"])
                    media.add(pk)
        if evidence:
            matches[pid] = ([f for f in facts if f["fact_id"] in evidence], media)
    return matches


def _stored_mentions(facts, observed_by):
    """Read native mention IDs only for intact primary X posts present at selection."""
    from core.models import Post
    from x_monitor.tweet_entities import entity_text, mention_id, normalize_entities

    originals = [f for f in facts if current_primary_fact(f, observed_by)]
    authors = {f.get("speaker_id") for f in originals}
    author_handles = {(f.get("speaker") or "").casefold() for f in originals}
    cited = {
        f["source_post_id"]: f
        for f in originals
        if f.get("source_kind") == "x_post"
        and f.get("source_post_id")
        and "@" in f["supporting_passage"]
    }
    for post in Post.objects.filter(pk__in=cited, fetched_at__lte=observed_by).only(
        "pk", "text", "entities", "native_author_id", "author_handle", "fetched_at"
    ):
        fact = cited[post.pk]
        if post.text != fact[
            "supporting_passage"
        ] or post.fetched_at > datetime.fromisoformat(fact["observed_at"]):
            continue
        for mention in normalize_entities(post.entities).get("user_mentions", ()):
            native = mention_id(mention)
            handle = entity_text(mention, "screen_name").casefold()
            label = entity_text(mention, "name").casefold()
            if (
                not native
                or native == post.native_author_id
                or native in authors
                or handle == (post.author_handle or "").casefold()
                or handle in author_handles
                or not label
                or not re.fullmatch(r"[a-z0-9_]{1,15}", handle)
                or not re.search(
                    rf"(?<![\w@])@{re.escape(handle)}(?!\w)", post.text, re.IGNORECASE
                )
            ):
                continue
            yield native, handle, label, fact["fact_id"]


def verified_subject_mentions(candidates, facts, observed_by):
    """Return cited mention facts and conflicting person IDs. No account review state changes."""
    from core.models import Person, PersonAccount, PersonName
    from core.person_identity import account_observation_person_ids

    matches, conflicts = defaultdict(set), set()
    if not candidates:
        return matches, conflicts
    mentions = list(_stored_mentions(facts, observed_by))
    if not mentions:
        return matches, conflicts
    aliases = defaultdict(set)
    for pid, name in (
        PersonName.objects.filter(person_id__in=candidates)
        .exclude(review_status="rejected")
        .values_list("person_id", "full_name")
    ):
        aliases[str(pid)].add(name.strip().casefold())
    links = defaultdict(list)
    accounts = PersonAccount.objects.filter(
        account__data_source_id="x",
        account__verified=True,
        account__author_id__in={native for native, *_ in mentions},
    )
    for native, handle, pid, status, first, merged in accounts.values_list(
        "account__author_id",
        "account__normalized_handle",
        "person_id",
        "resolution_status",
        "first_observed_at",
        "person__merged_into_id",
    ):
        links[(native, handle)].append((pid, status, first, merged))
    provisional_ids = {
        native: set(account_observation_person_ids(native)) for native, *_ in mentions
    }
    existing = set(
        Person.objects.filter(pk__in=set.union(*provisional_ids.values())).values_list(
            "pk", flat=True
        )
    )
    for native, handle, label, fact_id in mentions:
        linked = links[native, handle]
        relevant = {
            str(pid) for pid, *_ in linked if label in aliases.get(str(pid), ())
        }
        if not relevant:
            continue
        active = [
            (pid, state, first, merged)
            for pid, state, first, merged in linked
            if state != "rejected"
        ]
        if len(active) != 1:
            conflicts.update(relevant)
            continue
        pid, state, first, merged = active[0]
        if str(pid) not in relevant or merged or state == "needs_review":
            conflicts.update(relevant)
            continue
        if first <= observed_by and (
            state == "confirmed"
            or state == "pending"
            and provisional_ids[native] & existing == {pid}
        ):
            matches[str(pid)].add(fact_id)
    return matches, conflicts
