"""Deterministic account-profile history and affiliation candidates.

This module has no provider dependency.  It turns the author facts already
attached to a persisted post into a compressed profile timeline, then emits
source-bound, unreviewed person-to-brand claims from conservative rules.
Observation times describe when PushinWeight saw a profile; they are never
used as employment start or end dates.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import unquote, urlparse

from django.db import transaction
from django.db.models import F

from core.models import (
    Account,
    AccountProfileSnapshot,
    Brand,
    BrandAccount,
    Person,
    PersonAccount,
    PersonBrandAffiliation,
    PersonBrandAffiliationEvidence,
    Post,
    TwitterListMembership,
)
from monitor.twitterapi.user_about import SchemaDriftError, flatten_label

PROFILE_RULE_VERSION = "profile-affiliation-rules-v1"
PROFILE_HASH_VERSION = "profile-hash-v1"

_PROFILE_SOURCE_MAP: tuple[tuple[str, str], ...] = (
    ("handle", "author_handle"),
    ("display_name", "author_name"),
    ("description", "author_description"),
    ("profile_bio_text", "author_profile_bio_text"),
    ("location", "author_location"),
    ("profile_image_url", "author_profile_picture"),
    ("verified", "author_verified"),
    ("is_blue_verified", "author_is_blue_verified"),
    ("verified_type", "author_verified_type"),
)

_POST_FIELD_MAP: tuple[tuple[str, str], ...] = (
    ("handle", "author_handle"),
    ("display_name", "author_name"),
    ("description", "author_description"),
    ("profile_bio_text", "author_profile_bio"),
    ("location", "author_location"),
    ("profile_image_url", "author_profile_picture"),
    ("verified", "author_verified"),
    ("is_blue_verified", "author_is_blue_verified"),
    ("verified_type", "author_verified_type"),
)

_ACCOUNT_FIELD_MAP: tuple[tuple[str, str], ...] = (
    ("handle", "handle"),
    ("display_name", "display_name"),
    ("description", "description"),
    ("profile_bio_text", "profile_bio_text"),
    ("location", "location"),
    ("profile_image_url", "profile_picture"),
    ("verified", "verified"),
    ("is_blue_verified", "is_blue_verified"),
    ("verified_type", "verified_type"),
    ("affiliate_target_url", "affiliate_label_url"),
    ("affiliate_label_description", "affiliate_label_description"),
    ("affiliate_badge_image_url", "affiliate_label_badge_url"),
    ("affiliate_label_type", "affiliate_label_user_label_type"),
    ("affiliate_display_type", "affiliate_label_user_label_display_type"),
)

_SNAPSHOT_TYPED_FIELDS = frozenset(
    {
        *(target for target, _source in _ACCOUNT_FIELD_MAP),
        "affiliate_target_username",
    }
)

_COMMUNITY_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bambassador\b", re.IGNORECASE), "ambassador"),
    (re.compile(r"\bcreator\s+partner\b", re.IGNORECASE), "creator_partner"),
    (re.compile(r"\b(?:cpp|ecp)\b", re.IGNORECASE), "creator_partner"),
    (re.compile(r"\baffiliate\b", re.IGNORECASE), "affiliate"),
    (
        re.compile(r"\bcommunity\s+(?:member|partner|ambassador)\b", re.IGNORECASE),
        "community",
    ),
)
_FORMER_PATTERN = re.compile(
    r"(?:\bformer(?:ly)?\b|\bex[-\s]|\bpreviously\b|\bworked\s+(?:at|for)\b)",
    re.IGNORECASE,
)
_CURRENT_PATTERN = re.compile(
    r"(?:\bnow\b|\bcurrently\b)",
    re.IGNORECASE,
)
_STAFF_PATTERN = re.compile(
    r"(?:"
    r"\b(?:work(?:ing)?|researcher|engineer|scientist|designer|recruiter|"
    r"founder|cofounder|co-founder|executive|director|manager|lead|head|intern)"
    r"\s+(?:at|for|with)\b"
    r"|\bbuilding\s+(?:at\s+)?@"
    r")",
    re.IGNORECASE,
)
_STAFF_TITLE_PATTERN = re.compile(
    r"\b(?:researcher|engineer|scientist|designer|recruiter|founder|cofounder|"
    r"co-founder|executive|director|manager|lead|head|intern)\b",
    re.IGNORECASE,
)
_FORMER_SUFFIX_PATTERN = re.compile(
    r"^\s*(?:alum|alumni|formerly)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ProfileObservation:
    profile_hash: str
    profile_data: dict[str, Any]
    present_fields: tuple[str, ...]
    raw_profile_payload: dict[str, Any] | None


@dataclass(frozen=True)
class BrandReference:
    brand_id: str
    display_name: str
    handles: tuple[str, ...]
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class AffiliationSignal:
    brand_id: str
    observed_organization_name: str
    observed_organization_handle: str | None
    candidate_role: str
    affiliation_type: str
    status: str
    confidence: float
    evidence_kind: str
    evidence_text: str
    call_a_active: bool


@dataclass(frozen=True)
class AccountAffiliationContext:
    reviewed_edges: tuple[tuple[str, str], ...]
    call_a_active: bool


@dataclass(frozen=True)
class ProfileCaptureResult:
    snapshot: AccountProfileSnapshot
    snapshot_created: bool
    snapshot_changed: bool
    candidate_counts: dict[str, int]


def person_id_for_account(account_id: object) -> uuid.UUID:
    """Return the stable person identity shared by every self-account path."""

    return uuid.uuid5(uuid.NAMESPACE_URL, f"pushinweight:account:{account_id}")


def person_id_for_handle(handle: str) -> uuid.UUID:
    """Return the provisional identity used for a normalized X handle."""

    normalized = unicodedata.normalize("NFKC", handle).strip().removeprefix("@").casefold()
    if not normalized:
        raise ValueError("person handle must be nonblank")
    return uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"pushinweight:person:x-handle:{normalized}",
    )


def _json_safe(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except (TypeError, ValueError):
        return str(value)


def _normalized_hash_value(field: str, value: Any) -> Any:
    if isinstance(value, str):
        value = unicodedata.normalize("NFKC", value).strip()
        if field in {"handle", "affiliate_target_username"}:
            return value.removeprefix("@").casefold()
        return value
    if isinstance(value, dict):
        return {
            str(key): _normalized_hash_value(str(key), child)
            for key, child in sorted(value.items())
        }
    if isinstance(value, list):
        return [_normalized_hash_value(field, child) for child in value]
    return value


def _profile_hash(
    profile_data: Mapping[str, Any], present_fields: Iterable[str]
) -> str:
    fields = tuple(sorted(set(present_fields)))
    payload = {
        "version": PROFILE_HASH_VERSION,
        "present_fields": fields,
        "values": {
            field: _normalized_hash_value(field, profile_data.get(field))
            for field in fields
        },
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _username_from_url(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    parsed = urlparse(value.strip())
    segments = [unquote(segment) for segment in parsed.path.split("/") if segment]
    if not segments:
        return None
    ignored = {"i", "user", "intent", "search", "home"}
    for segment in reversed(segments):
        candidate = segment.removeprefix("@").strip()
        if (
            candidate
            and candidate.casefold() not in ignored
            and not candidate.isdigit()
        ):
            return candidate[:64]
    return None


def profile_observation_from_payload(raw: Mapping[str, Any]) -> ProfileObservation:
    """Extract one profile observation while preserving field presence.

    New normalized Twitter payloads carry ``_author_present_fields`` from the
    original author envelope.  Older callers lack that marker, so only their
    non-null values count as known-present facts.
    """

    upstream_presence = raw.get("_author_present_fields")
    has_presence_marker = isinstance(upstream_presence, (list, tuple, set))
    source_presence = {
        str(value) for value in upstream_presence or () if isinstance(value, str)
    }
    profile_data: dict[str, Any] = {}
    present: set[str] = set()
    raw_profile: dict[str, Any] = {}

    for target, source in _PROFILE_SOURCE_MAP:
        is_present = (
            source in source_presence
            if has_presence_marker
            else source in raw and raw.get(source) is not None
        )
        if not is_present:
            continue
        value = _json_safe(raw.get(source))
        profile_data[target] = value
        present.add(target)
        raw_profile[source] = value

    label_source = "author_affiliates_highlighted_label"
    label_present = (
        label_source in source_presence
        if has_presence_marker
        else label_source in raw and raw.get(label_source) is not None
    )
    if label_present:
        raw_label = _json_safe(raw.get(label_source))
        raw_profile[label_source] = raw_label
        try:
            values, _fields = flatten_label(
                raw_label,
                prefix="affiliate_label",
                path="post.author_affiliates_highlighted_label",
            )
        except SchemaDriftError:
            values = {}
        mapped = {
            "affiliate_target_url": values.get("affiliate_label_url"),
            "affiliate_label_description": values.get("affiliate_label_description"),
            "affiliate_badge_image_url": values.get("affiliate_label_badge_url"),
            "affiliate_label_type": values.get("affiliate_label_user_label_type"),
            "affiliate_display_type": values.get(
                "affiliate_label_user_label_display_type"
            ),
        }
        mapped["affiliate_target_username"] = _username_from_url(
            mapped["affiliate_target_url"]
        )
        profile_data.update(mapped)
        present.update(mapped)

    return ProfileObservation(
        profile_hash=_profile_hash(profile_data, present),
        profile_data=profile_data,
        present_fields=tuple(sorted(present)),
        raw_profile_payload=raw_profile or None,
    )


def profile_observation_from_post(post: Post) -> ProfileObservation:
    data: dict[str, Any] = {}
    present: set[str] = set()
    raw_profile: dict[str, Any] = {}
    for target, source in _POST_FIELD_MAP:
        value = getattr(post, source)
        if value is None:
            continue
        if source == "author_profile_bio":
            raw_profile[source] = _json_safe(value)
            if isinstance(value, dict) and "description" in value:
                data[target] = _json_safe(value.get("description"))
                present.add(target)
            continue
        data[target] = _json_safe(value)
        present.add(target)
        raw_profile[source] = _json_safe(value)

    raw_label = post.author_affiliates_highlighted_label
    if raw_label is not None:
        payload = profile_observation_from_payload(
            {
                "author_affiliates_highlighted_label": raw_label,
                "_author_present_fields": ["author_affiliates_highlighted_label"],
            }
        )
        for field in payload.present_fields:
            data[field] = payload.profile_data.get(field)
            present.add(field)
        raw_profile["author_affiliates_highlighted_label"] = _json_safe(raw_label)

    return ProfileObservation(
        profile_hash=_profile_hash(data, present),
        profile_data=data,
        present_fields=tuple(sorted(present)),
        raw_profile_payload=raw_profile or None,
    )


def profile_observation_from_account(account: Account) -> ProfileObservation:
    data: dict[str, Any] = {}
    present: set[str] = set()
    for target, source in _ACCOUNT_FIELD_MAP:
        value = getattr(account, source)
        if value is None:
            continue
        data[target] = _json_safe(value)
        present.add(target)
    if "affiliate_target_url" in data:
        data["affiliate_target_username"] = _username_from_url(
            data["affiliate_target_url"]
        )
        present.add("affiliate_target_username")
    return ProfileObservation(
        profile_hash=_profile_hash(data, present),
        profile_data=data,
        present_fields=tuple(sorted(present)),
        raw_profile_payload=None,
    )


def _snapshot_defaults(observation: ProfileObservation) -> dict[str, Any]:
    return {
        field: observation.profile_data.get(field)
        for field in observation.present_fields
        if field in _SNAPSHOT_TYPED_FIELDS
    }


def record_profile_snapshot(
    *,
    account: Account,
    observation: ProfileObservation,
    observed_at: datetime,
    source_kind: str,
    source_post: Post | None = None,
    source_run: str | None = None,
) -> tuple[AccountProfileSnapshot, bool, bool]:
    """Write one observation, collapsing only the latest identical version.

    Returns ``(snapshot, created, changed)``.  Replaying the same persisted
    post is a no-op; a later A → B → A sequence creates a third row.
    """

    with transaction.atomic():
        snapshots = AccountProfileSnapshot.objects.select_for_update().filter(
            account=account
        )
        if source_post is not None:
            exact = snapshots.filter(first_source_post=source_post).first()
            if exact is not None:
                return exact, False, False

        covering = snapshots.filter(
            profile_hash=observation.profile_hash,
            first_observed_at__lte=observed_at,
            last_observed_at__gte=observed_at,
        ).first()
        if covering is not None:
            return covering, False, False

        latest = snapshots.order_by("-last_observed_at", "-id").first()
        if latest is not None and latest.profile_hash == observation.profile_hash:
            if observed_at <= latest.last_observed_at:
                return latest, False, False
            AccountProfileSnapshot.objects.filter(pk=latest.pk).update(
                last_observed_at=observed_at,
                observation_count=F("observation_count") + 1,
            )
            latest.refresh_from_db()
            return latest, False, False

        defaults = _snapshot_defaults(observation)
        snapshot = AccountProfileSnapshot.objects.create(
            account=account,
            profile_hash=observation.profile_hash,
            first_observed_at=observed_at,
            last_observed_at=observed_at,
            observation_count=1,
            first_source_kind=source_kind[:32],
            first_source_post=source_post,
            first_source_run=(source_run or None),
            present_fields=list(observation.present_fields),
            profile_data=observation.profile_data,
            raw_profile_payload=observation.raw_profile_payload,
            **defaults,
        )
        return snapshot, True, latest is not None


def build_brand_reference_index() -> tuple[BrandReference, ...]:
    handles: dict[str, set[str]] = {}
    for brand_id, handle in BrandAccount.objects.exclude(
        account__handle__isnull=True
    ).values_list("brand_id", "account__handle"):
        if handle:
            handles.setdefault(str(brand_id), set()).add(
                str(handle).removeprefix("@").casefold()
            )

    references: list[BrandReference] = []
    for brand in Brand.objects.filter(is_sentinel=False).order_by("nickname"):
        aliases = {
            str(brand.nickname).replace("_", " ").strip(),
            str(brand.display_name or "").strip(),
            str(brand.display_name_en or "").strip(),
            str(brand.display_name_zh_cn or "").strip(),
        }
        references.append(
            BrandReference(
                brand_id=str(brand.nickname),
                display_name=str(brand.display_name or brand.nickname),
                handles=tuple(sorted(handles.get(str(brand.nickname), set()))),
                aliases=tuple(
                    sorted(
                        {alias for alias in aliases if len(alias) >= 3},
                        key=lambda value: (-len(value), value.casefold()),
                    )
                ),
            )
        )
    return tuple(references)


def build_account_affiliation_contexts(
    account_ids: Iterable[str],
) -> dict[str, AccountAffiliationContext]:
    """Load reviewed roles and Call A membership once for a persistence batch."""

    ids = tuple(sorted({str(account_id) for account_id in account_ids if account_id}))
    if not ids:
        return {}
    reviewed: dict[str, list[tuple[str, str]]] = {account_id: [] for account_id in ids}
    for account_id, brand_id, role_id in BrandAccount.objects.filter(
        account_id__in=ids
    ).values_list("account_id", "brand_id", "role_id"):
        reviewed[str(account_id)].append((str(brand_id), str(role_id)))
    call_a_accounts = {
        str(account_id)
        for account_id in TwitterListMembership.objects.filter(
            account_id__in=ids,
            active=True,
            source="call_a",
        ).values_list("account_id", flat=True)
    }
    return {
        account_id: AccountAffiliationContext(
            reviewed_edges=tuple(sorted(reviewed[account_id])),
            call_a_active=account_id in call_a_accounts,
        )
        for account_id in ids
    }


def _mentioned_references(
    *,
    observation: ProfileObservation,
    references: Iterable[BrandReference],
) -> dict[str, tuple[BrandReference, str, str | None]]:
    text = "\n".join(
        str(observation.profile_data.get(field) or "")
        for field in ("description", "profile_bio_text", "affiliate_label_description")
    )
    text_folded = unicodedata.normalize("NFKC", text).casefold()
    badge_username = (
        str(observation.profile_data.get("affiliate_target_username") or "")
        .removeprefix("@")
        .casefold()
    )
    matches: dict[str, tuple[BrandReference, str, str | None]] = {}
    for reference in references:
        for handle in reference.handles:
            if badge_username and badge_username == handle:
                matches[reference.brand_id] = (reference, "business_label", handle)
                break
        if reference.brand_id in matches:
            continue
        for handle in reference.handles:
            if re.search(rf"(?<![\w])@{re.escape(handle)}(?![\w])", text_folded):
                matches[reference.brand_id] = (reference, "handle", handle)
                break
        if reference.brand_id in matches:
            continue
        for alias in reference.aliases:
            alias_folded = unicodedata.normalize("NFKC", alias).casefold()
            if not alias_folded:
                continue
            if alias_folded.isascii():
                found = re.search(
                    rf"(?<![\w]){re.escape(alias_folded)}(?![\w])", text_folded
                )
            else:
                found = alias_folded in text_folded
            if found:
                matches[reference.brand_id] = (reference, "name", None)
                break
    return matches


def _reference_mentions(text: str, reference: BrandReference) -> tuple[tuple[int, int], ...]:
    """Return bio spans that refer to one brand."""

    expressions: list[str] = []
    for handle in reference.handles:
        normalized = unicodedata.normalize("NFKC", handle).casefold().removeprefix("@")
        if normalized:
            expressions.append(rf"(?<![\w])@?{re.escape(normalized)}(?![\w])")
    for alias in reference.aliases:
        normalized = unicodedata.normalize("NFKC", alias).casefold()
        if not normalized:
            continue
        if normalized.isascii():
            expressions.append(rf"(?<![\w]){re.escape(normalized)}(?![\w])")
        else:
            expressions.append(re.escape(normalized))
    if not expressions:
        return ()
    pattern = re.compile("|".join(dict.fromkeys(expressions)), re.IGNORECASE)
    return tuple(match.span() for match in pattern.finditer(text))


def _brand_local_relationship(
    *,
    bio_text: str,
    reference: BrandReference,
    other_brand_mentions: tuple[tuple[int, int], ...],
) -> tuple[str | None, bool, bool]:
    """Find relationship words attached to this brand rather than the whole bio."""

    mentions = _reference_mentions(bio_text, reference)
    community_type: str | None = None
    former = False
    staff = False
    for start, end in mentions:
        clause_start = max(
            bio_text.rfind(separator, 0, start)
            for separator in ("\n", ";", ".", "!", "?")
        ) + 1
        clause_end_candidates = [
            position
            for separator in ("\n", ";", ".", "!", "?")
            if (position := bio_text.find(separator, end)) >= 0
        ]
        clause_end = min(clause_end_candidates, default=len(bio_text))

        previous_brand_end = max(
            (other_end for _other_start, other_end in other_brand_mentions if other_end <= start),
            default=clause_start,
        )
        next_brand_start = min(
            (other_start for other_start, _other_end in other_brand_mentions if other_start >= end),
            default=clause_end,
        )
        prefix = bio_text[max(clause_start, previous_brand_end, start - 64) : start]
        suffix = bio_text[end : min(clause_end, next_brand_start, end + 48)]

        for pattern, affiliation_type in _COMMUNITY_PATTERNS:
            if pattern.search(prefix[-40:]) or pattern.search(suffix[:40]):
                community_type = affiliation_type
                break
        if community_type is not None:
            continue

        former_matches = list(_FORMER_PATTERN.finditer(prefix))
        current_matches = list(_CURRENT_PATTERN.finditer(prefix))
        last_former = former_matches[-1].start() if former_matches else -1
        last_current = current_matches[-1].start() if current_matches else -1
        if _FORMER_SUFFIX_PATTERN.search(suffix) or last_former > last_current:
            former = True
            continue

        if last_current >= 0 or _STAFF_PATTERN.search(prefix):
            staff = True
            continue
        if _STAFF_TITLE_PATTERN.match(suffix):
            staff = True

    return community_type, former, staff


def classify_affiliation_signals(
    *,
    account: Account,
    observation: ProfileObservation,
    references: Iterable[BrandReference],
    context: AccountAffiliationContext | None = None,
) -> tuple[AffiliationSignal, ...]:
    """Classify conservative staff/community/unknown profile evidence."""

    references = tuple(references)
    references_by_id = {reference.brand_id: reference for reference in references}
    matched = _mentioned_references(observation=observation, references=references)
    if context is None:
        reviewed_edges = {
            str(edge.brand_id): str(edge.role_id)
            for edge in BrandAccount.objects.filter(account=account)
        }
        call_a_active = TwitterListMembership.objects.filter(
            account=account, active=True, source="call_a"
        ).exists()
    else:
        reviewed_edges = dict(context.reviewed_edges)
        call_a_active = context.call_a_active
    for brand_id in reviewed_edges:
        reference = references_by_id.get(brand_id)
        if reference is not None:
            matched.setdefault(brand_id, (reference, "brands_accounts", None))

    bio_text = "\n".join(
        str(observation.profile_data.get(field) or "")
        for field in ("description", "profile_bio_text")
    )
    mention_spans = {
        brand_id: _reference_mentions(bio_text, reference)
        for brand_id, (reference, _evidence_kind, _observed_handle) in matched.items()
    }

    signals: list[AffiliationSignal] = []
    for brand_id, (reference, evidence_kind, observed_handle) in sorted(
        matched.items()
    ):
        other_brand_mentions = tuple(
            span
            for other_brand_id, spans in mention_spans.items()
            if other_brand_id != brand_id
            for span in spans
        )
        community_type, former, staff_language = _brand_local_relationship(
            bio_text=bio_text,
            reference=reference,
            other_brand_mentions=other_brand_mentions,
        )
        reviewed_role = reviewed_edges.get(brand_id)
        if reviewed_role == "official":
            candidate_role = "official"
            affiliation_type = "other"
            status = "current"
            confidence = 1.0
        elif reviewed_role == "staff":
            candidate_role = "staff"
            affiliation_type = "employment"
            status = "current"
            confidence = 1.0
        elif reviewed_role == "community":
            candidate_role = "community"
            affiliation_type = community_type or "community"
            status = "current"
            confidence = 1.0
        elif community_type is not None:
            candidate_role = "community"
            affiliation_type = community_type
            status = "current"
            confidence = 0.9
        elif former:
            candidate_role = "staff"
            affiliation_type = "employment"
            status = "former"
            confidence = 0.82
        elif staff_language:
            candidate_role = "staff"
            affiliation_type = "employment"
            status = "current"
            confidence = 0.82
        elif call_a_active:
            handle = str(observation.profile_data.get("handle") or "").casefold()
            organizational = any(handle == known for known in reference.handles)
            candidate_role = "official" if organizational else "staff"
            affiliation_type = "other" if organizational else "employment"
            status = "current"
            confidence = 0.78
        else:
            candidate_role = "unknown"
            affiliation_type = "other"
            status = "unknown"
            confidence = 0.45 if evidence_kind == "business_label" else 0.3

        evidence_text = bio_text.strip()
        if evidence_kind == "business_label":
            evidence_text = str(
                observation.profile_data.get("affiliate_label_description") or ""
            ).strip()
        signals.append(
            AffiliationSignal(
                brand_id=brand_id,
                observed_organization_name=reference.display_name,
                observed_organization_handle=observed_handle,
                candidate_role=candidate_role,
                affiliation_type=affiliation_type,
                status=status,
                confidence=confidence,
                evidence_kind=evidence_kind,
                evidence_text=evidence_text[:2000],
                call_a_active=call_a_active,
            )
        )
    return tuple(signals)


def persist_affiliation_candidates(
    *,
    account: Account,
    snapshot: AccountProfileSnapshot,
    signals: Iterable[AffiliationSignal],
    observed_at: datetime,
) -> dict[str, int]:
    counts = {"staff": 0, "community": 0, "unknown": 0, "official": 0}
    existing_link = (
        account.person_links.filter(resolution_status="confirmed").first()
        or account.person_links.exclude(resolution_status="rejected")
        .order_by("-is_primary", "person_id")
        .first()
    )
    person_id = existing_link.person_id if existing_link is not None else None
    if person_id is None and account.handle:
        handle_person_id = person_id_for_handle(account.handle)
        if Person.objects.filter(pk=handle_person_id).exists():
            person_id = handle_person_id
    person_id = person_id or person_id_for_account(account.pk)
    person: Person | None = None

    for signal in signals:
        counts[signal.candidate_role] = counts.get(signal.candidate_role, 0) + 1
        # Organization-controlled accounts belong in the operational role
        # review queue/report, not in the people table.
        if signal.candidate_role == "official":
            continue
        if person is None:
            person, _ = Person.objects.get_or_create(
                id=person_id,
                defaults={
                    "display_name": account.display_name
                    or account.handle
                    or str(account.pk)
                },
            )
            link, _ = PersonAccount.objects.get_or_create(
                person=person,
                account=account,
                defaults={
                    "first_observed_at": observed_at,
                    "last_observed_at": observed_at,
                    "confidence": signal.confidence,
                    "resolution_status": "pending",
                },
            )
            changed: list[str] = []
            if observed_at > link.last_observed_at:
                link.last_observed_at = observed_at
                changed.append("last_observed_at")
            if changed:
                link.save(update_fields=changed)

        claim_payload = {
            "account_id": str(account.pk),
            "brand_id": signal.brand_id,
            "affiliation_type": signal.affiliation_type,
            "status": signal.status,
            "rule_version": PROFILE_RULE_VERSION,
        }
        claim_identity = hashlib.sha256(
            json.dumps(claim_payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        affiliation, _ = PersonBrandAffiliation.objects.get_or_create(
            claim_identity=claim_identity,
            defaults={
                "person": person,
                "brand_id": signal.brand_id,
                "affiliation_type": signal.affiliation_type,
                "observed_organization_name": signal.observed_organization_name,
                "observed_organization_handle": signal.observed_organization_handle,
                "status": signal.status,
                "start_date": None,
                "start_date_precision": "unknown",
                "end_date": None,
                "end_date_precision": "unknown",
                "confidence": signal.confidence,
                "review_status": "pending",
                "review_note": f"candidate_role={signal.candidate_role}",
                "source_system": PROFILE_RULE_VERSION,
            },
        )
        evidence_payload = {
            **claim_payload,
            "snapshot_id": snapshot.pk,
            "profile_hash": snapshot.profile_hash,
            "evidence_kind": signal.evidence_kind,
            "candidate_role": signal.candidate_role,
            "call_a_active": signal.call_a_active,
        }
        evidence_hash = hashlib.sha256(
            json.dumps(evidence_payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        PersonBrandAffiliationEvidence.objects.get_or_create(
            affiliation=affiliation,
            evidence_hash=evidence_hash,
            defaults={
                "source_profile_snapshot": snapshot,
                "evidence_text": signal.evidence_text,
                "observed_at": observed_at,
                "extracted_claim_data": evidence_payload,
                "extraction_method": PROFILE_RULE_VERSION,
                "confidence": signal.confidence,
                "review_status": "pending",
            },
        )
    return counts


def capture_post_profile_snapshot(
    *,
    post: Post,
    raw: Mapping[str, Any],
    references: Iterable[BrandReference] | None = None,
    affiliation_context: AccountAffiliationContext | None = None,
) -> ProfileCaptureResult | None:
    if post.author_id is None:
        return None
    observation = profile_observation_from_payload(raw)
    if not observation.present_fields:
        return None
    observed_at = post.fetched_at
    snapshot, created, changed = record_profile_snapshot(
        account=post.author,
        observation=observation,
        observed_at=observed_at,
        source_kind="post",
        source_post=post,
    )
    signals = classify_affiliation_signals(
        account=post.author,
        observation=observation,
        references=references or build_brand_reference_index(),
        context=affiliation_context,
    )
    counts = persist_affiliation_candidates(
        account=post.author,
        snapshot=snapshot,
        signals=signals,
        observed_at=observed_at,
    )
    return ProfileCaptureResult(
        snapshot=snapshot,
        snapshot_created=created,
        snapshot_changed=changed,
        candidate_counts=counts,
    )
