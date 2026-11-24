"""Classification-gated structured extraction for rare post signals."""

from __future__ import annotations

import calendar
import hashlib
import json
import logging
import re
import time
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from core.account_vocabulary import code_for
from core.geolocation_evidence import AffiliationClaimEvidence, write_source_evidence
from core.job_locations import write_job_locations
from core.job_vocabulary import compensation_references, write_job_classifications
from core.models import (
    AffiliationType,
    Brand,
    BrandAccount,
    BrandDiscoveryCandidate,
    Event,
    EventEvidence,
    JobDiscoveryRun,
    JobListing,
    JobListingEvidence,
    Opportunity,
    OpportunityType,
    PersonBrandAffiliation,
    PersonBrandAffiliationEvidence,
    PersonnelDiscoveryRun,
    Post,
    ProductVerificationProposal,
    ProfileMovementCandidate,
    RareTypeCategoryAssignment,
    RareTypeSearchHit,
    SearchQuery,
    TargetedExtractionAttempt,
    TargetedExtractionState,
)
from core.person_affiliations import matching_moved_claim, require_claim_owner
from core.person_identity import subject_person
from core.product_release_dossiers import record_release_report
from core.product_verification import POLICY_VERSION, source_repo_evidence
from core.rare_type_search import record_unknown_name_tokens_from_movement
from core.shared_vocabulary import resolve_time_zone
from x_monitor.attribution import LLMCallBudgetExhausted
from x_monitor.config import TargetedExtractionConfig
from x_monitor.provider_telemetry import (
    ProviderResponse,
    emit_attempt,
    provider_host_class,
)

logger = logging.getLogger(__name__)

TYPE_TO_ROLE = {
    "events": "event_extraction",
    "opportunities": "opportunity_extraction",
    "job_listings": "job_listing_extraction",
    "personnel_changes": "personnel_change_extraction",
    "releases_updates": "model_release_extraction",
}
ALLOWED_AFFILIATION_TYPES = {
    value for value, _label in PersonBrandAffiliation.AFFILIATION_TYPES
}
ALLOWED_RELATIONSHIP_STATUSES = {"current", "former", "future", "unknown"}
ALLOWED_PRECISIONS = {"datetime", "day", "month", "year", "unknown"}
ALLOWED_JOB_STATUSES = {value for value, _label in JobListing.LISTING_STATUSES}
ALLOWED_APPLICATION_ROUTES = {
    value for value, _label in JobListing.APPLICATION_ROUTE_KINDS
}
ALLOWED_EVENT_MODES = {value for value, _label in Event.ATTENDANCE_MODES}
ALLOWED_EVENT_STATUSES = {value for value, _label in Event.SOURCE_STATUSES}
ALLOWED_OPPORTUNITY_TYPES = {value for value, _label in Opportunity.OPPORTUNITY_TYPES}
ALLOWED_RELEASE_CHANNELS = {"stable", "preview", "beta", "other"}
ALLOWED_RARE_CATEGORIES = {
    value for value, _label in RareTypeCategoryAssignment.CATEGORIES
}
ALLOWED_OPPORTUNITY_STATUSES = {value for value, _label in Opportunity.SOURCE_STATUSES}

TargetedCall = Callable[[str, str, str, int], Mapping[str, Any] | str]

_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+")
_MAX_RECORDS_PER_RESPONSE = 100
PERSONNEL_FIELD_EVIDENCE_SCHEMA = "personnel-field-evidence/v1"
_PERSONNEL_FIELD_EVIDENCE_VERSIONS = {
    "personnel-change-extraction-v3",
    "profile-affiliation-extraction-v3",
}
_PERSONNEL_EVIDENCE_FIELDS = {
    "person_name", "person_handle", "brand_id", "organization_name",
    "organization_handle", "affiliation_type", "title_raw", "title_normalized",
    "department", "team", "job_function", "description", "seniority",
    "employment_type", "status", "start_date", "end_date",
}

_ROLE_PROMPT_SPECS = {
    "event_extraction": """
Return one record per attendance-bearing event. An event requires attendance at
a scheduled in-person, live-online, or hybrid venue/session; an asynchronous
submission or application alone is not an event. Past, live, future, cancelled,
and postponed events may qualify. Fields: brand_id, organization_name,
organization_handle, title, external_event_source, external_event_id,
canonical_url, source_url,
attendance_mode (in_person,
online_live, hybrid, or unknown), physical_location, virtual_location,
attendance_url, start_value, start_precision (datetime, day, month, year, or
unknown), end_value, end_precision, source_timezone, source_schedule_text,
source_status (scheduled, live, completed, cancelled, postponed, or unknown),
and confidence.
""",
    "opportunity_extraction": """
Return one record per bounded action-for-benefit offer. It must ask someone to
act within a stated or inherently finite window in exchange for a concrete
benefit or chance to receive one. Jobs and routine event registration alone do
not qualify. Fields: brand_id, organization_name, organization_handle,
source_url, opportunity_type (giveaway, discount, free_credits, beta_access,
grant, bounty, contest, referral, collaboration, or other), action_type,
action_url, benefit_type, benefit_value, benefit_currency, benefit_text,
eligibility, geographic_restrictions, open_value, open_precision (datetime,
day, month, year, or unknown), close_value, close_precision, source_timezone,
source_availability_text, source_status (upcoming, open, closed, cancelled, or
unknown), related_event_title, and confidence.
""",
    "job_listing_extraction": """
Return one record per concrete public role or requisition. A record needs a
specific role and an application route: a supplied direct/careers URL, email,
source-stated QR code, or explicit direct-message instruction. Return zero
records for vague hiring promotion, culture posts, unnamed employers, or
unverified job-board claims. Fields: brand_id, organization_name,
organization_handle, source_name, source_listing_id, canonical_url,
application_url, application_route_kind (direct_url, careers_page, email, qr,
direct_message, other, or unresolved), application_contact,
application_resolution_status, title, description_text, department, team,
job_function, seniority, employment_type, workplace_type, locations_raw,
locations, remote_applicant_restrictions, salary_text, salary_min, salary_max,
salary_currency, salary_period, status (open, closed, future, or unknown),
posted_at, updated_source_at, expires_at, and closed_at (source-stated ISO 8601
timestamps with timezone or null), campaign_openings, role_openings, skills,
responsibilities, qualifications, education_requirements,
experience_requirements, benefits, eligibility, source_language,
organization_ai_relationship, role_ai_relationship, linked_urls, media_url,
and confidence. The server records the extraction method; do not return one.
""",
    "personnel_change_extraction": """
Return one record per named person's joining, leaving, appointment, or explicit
before-and-after employment transition involving an AI organization. Static
biographies, employee spotlights, and unchanged roles do not qualify. Fields:
person_name, person_handle, brand_id, organization_name, organization_handle,
affiliation_type (employment, founder, advisor, board_member, contractor,
ambassador, creator_partner, affiliate, investor, community, or other),
title_raw, title_normalized, department, team, job_function, description, seniority,
employment_type, status (current, former, future, or unknown), start_date,
start_date_precision (day, month, year, or unknown), end_date,
end_date_precision, and confidence. Keep an unstated effective date null with
unknown precision.
""",
    "model_release_extraction": """
Return one record per source-supported AI product release.
Recaps, reseller availability, price comparisons, and vague roadmap claims do
not qualify without an identifiable underlying release. Fields: brand_id,
organization_name, organization_handle, model_name, candidate_repo_id, version,
release_channel (stable, preview, beta, or other), release_value,
release_precision (day, month, year, or unknown), source_url, categories (one
or more of model-llm, model-other, agent, harness, other), and confidence. Use
model-llm for language models and derivatives, model-other for other AI models,
agent for goal-directed tool-using systems, harness for execution-control
software, and other for other identifiable products including hardware. Preserve
an unstated date as null with unknown precision.
""",
    "profile_affiliation_extraction": """
Review the supplied profile observations and return one record per supported
person-to-organization affiliation. A bare organization handle or business
badge is evidence for review but does not alone prove employment. Distinguish
employment from ambassador, creator-partner, affiliate, and community roles.
Fields: person_name, person_handle, brand_id, organization_name,
organization_handle, affiliation_type (employment, founder, advisor,
board_member, contractor, ambassador, creator_partner, affiliate, investor,
community, or other), title_raw, title_normalized, department, team,
job_function, description, seniority, employment_type, status (current, former, future, or
unknown), start_date, start_date_precision (day, month, year, or unknown),
end_date, end_date_precision, source_profile_snapshot_id, source_quote, and confidence.
For every record cite the supplied profile snapshot ID and an exact quote from
its description or profile biography. Keep unstated effective dates null with
unknown precision.
""",
}


@dataclass(frozen=True)
class TargetedExtractionResult:
    calls_made: int = 0
    records_written: int = 0
    evidence_written: int = 0
    organization_candidates_written: int = 0
    failed_roles: tuple[str, ...] = ()
    deferred_roles: tuple[str, ...] = ()


@dataclass
class _BrandEvidenceContext:
    source_text: str
    attributed_brand_ids: set[str]
    resolved: dict[str, Brand | None]


def build_targeted_extraction_calls(
    *,
    client: Any,
    roles: Mapping[str, Any],
    timeout_seconds: int,
) -> dict[str, TargetedCall]:
    """Build role-specific calls over the existing classifier client boundary."""

    if client is None:
        return {}
    telemetry_context = {"provider_host_class": provider_host_class(client)}

    def build(role: str) -> TargetedCall:
        def call(system: str, user: str, model: str, max_tokens: int):
            started = time.monotonic()
            try:
                response = client.messages_create(
                    model=model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                    timeout=timeout_seconds,
                )
            except LLMCallBudgetExhausted:
                raise
            except Exception as exc:
                emit_attempt(
                    logger,
                    role=role,
                    model=model,
                    attempt=1,
                    outcome="error",
                    started=started,
                    error=exc,
                    attempt_kind="single",
                    **telemetry_context,
                )
                raise
            emit_attempt(
                logger,
                role=role,
                model=model,
                attempt=1,
                outcome="success",
                started=started,
                response=response,
                attempt_kind="single",
                **telemetry_context,
            )
            if isinstance(response, ProviderResponse):
                # The direct DeepInfra adapter has already parsed and strictly
                # validated the JSON response. Anthropic-compatible clients
                # instead expose text content blocks below.
                payload = dict(response)
                usage = response.provider_usage
            else:
                content = response.get("content") or []
                text_parts = [
                    str(block.get("text") or "")
                    for block in content
                    if isinstance(block, Mapping) and block.get("type") == "text"
                ]
                payload = json.loads("\n".join(text_parts).strip())
                usage = response.get("usage")
            if not isinstance(payload, dict):
                raise TypeError("targeted provider response must be a JSON object")
            if isinstance(usage, Mapping) and "usage" not in payload:
                payload["usage"] = {
                    "input_tokens": usage.get("input_tokens"),
                    "output_tokens": usage.get("output_tokens"),
                }
            return payload

        return call

    return {role: build(role) for role in roles}


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _text(value: Any, *, required: bool = False, maximum: int = 20_000) -> str | None:
    if value is None:
        if required:
            raise ValueError("required text is missing")
        return None
    parsed = str(value).strip()
    if not parsed:
        if required:
            raise ValueError("required text is blank")
        return None
    return parsed[:maximum]


def _time_zone_reference_id(value: Any) -> str | None:
    zone = resolve_time_zone(_text(value, maximum=64))
    return zone.pk if zone else None


def _url(value: Any) -> str | None:
    parsed = _text(value, maximum=2048)
    if parsed is None:
        return None
    parts = urlparse(parsed)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("URL must use http or https and include a host")
    return parsed


def _source_urls(post: Post) -> tuple[str, ...]:
    found: set[str] = set()

    def collect(value: Any) -> None:
        if isinstance(value, str):
            for candidate in _URL_PATTERN.findall(value):
                try:
                    parsed = _url(candidate.rstrip(".,);]"))
                except ValueError:
                    continue
                if parsed:
                    found.add(parsed)
        elif isinstance(value, Mapping):
            for child in value.values():
                collect(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                collect(child)

    for value in (
        post.text,
        post.quoted_text,
        post.tweet_url,
        post.tweet_twitter_url,
        post.entities,
        post.extended_entities,
        post.card,
        post.article,
    ):
        collect(value)
    return tuple(sorted(found))


def _source_bound_url(
    value: Any, *, source_urls: tuple[str, ...], field: str
) -> str | None:
    parsed = _url(value)
    if parsed is not None and parsed not in source_urls:
        raise ValueError(f"{field} URL is not present in source evidence")
    return parsed


def _number(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("invalid decimal value") from exc
    if not parsed.is_finite():
        raise ValueError("decimal value must be finite")
    return parsed


def _temporal_value(
    value: Any,
    precision_value: Any,
    *,
    field: str,
    allow_datetime: bool,
) -> tuple[str | None, str, date | datetime | None]:
    """Validate one reduced-precision value before it reaches PostgreSQL."""

    allowed = ALLOWED_PRECISIONS if allow_datetime else ALLOWED_PRECISIONS - {
        "datetime"
    }
    precision = _choice(
        precision_value,
        allowed=allowed,
        default="unknown",
        field=f"{field} precision",
    )
    parsed_value = _text(value, maximum=64 if allow_datetime else 10)
    if parsed_value is None:
        if precision != "unknown":
            raise ValueError(f"{field} precision requires a value")
        return None, precision, None
    if precision == "unknown":
        raise ValueError(f"{field} value requires a known precision")
    try:
        if precision == "datetime":
            if not re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}"
                r"(:[0-9]{2}(\.[0-9]+)?)?(Z|[+-][0-9]{2}:[0-9]{2})",
                parsed_value,
            ):
                raise ValueError
            parsed: date | datetime = datetime.fromisoformat(
                parsed_value.replace("Z", "+00:00")
            )
            if parsed.tzinfo is None:
                raise ValueError
        elif precision == "day":
            if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", parsed_value):
                raise ValueError
            parsed = date.fromisoformat(parsed_value)
        elif precision == "month":
            if not re.fullmatch(r"[0-9]{4}-[0-9]{2}", parsed_value):
                raise ValueError
            parsed = date.fromisoformat(f"{parsed_value}-01")
        else:
            if not re.fullmatch(r"[0-9]{4}", parsed_value):
                raise ValueError
            parsed = date(int(parsed_value), 1, 1)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {field} value") from exc
    return parsed_value, precision, parsed


def _temporal_range(
    *,
    start: tuple[str | None, str, date | datetime | None],
    end: tuple[str | None, str, date | datetime | None],
    field: str,
) -> None:
    if (
        start[2] is not None
        and end[2] is not None
        and start[1] == end[1]
        and start[2] > end[2]
    ):
        raise ValueError(f"{field} end precedes start")


def _source_datetime(value: Any, *, field: str) -> datetime | None:
    parsed_value = _text(value, maximum=64)
    if parsed_value is None:
        return None
    try:
        parsed = datetime.fromisoformat(parsed_value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid {field}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed


def _identity_value(value: Any) -> Any:
    """Normalize only the fallback identity, retaining source values verbatim."""

    if isinstance(value, str):
        return " ".join(unicodedata.normalize("NFKC", value).casefold().split())
    if isinstance(value, list):
        return sorted((_identity_value(item) for item in value), key=str)
    return value


def _normalized_event_text(value: Any) -> str:
    """Normalize names for deterministic candidate matching only."""

    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return " ".join(re.findall(r"[\w]+", text, flags=re.UNICODE))


def _normalized_event_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return value
    path = parsed.path.rstrip("/") or "/"
    return parsed._replace(
        scheme=parsed.scheme.casefold(),
        netloc=parsed.netloc.casefold(),
        path=path,
        fragment="",
    ).geturl()


def _event_window_compatible(
    start_value: str | None,
    start_precision: str,
    end_value: str | None,
    end_precision: str,
    event: Event,
) -> bool:
    """Require explicit windows to agree; unknown windows never fuzzy-merge."""

    if start_value is None and end_value is None:
        return False
    if event.start_value is None and event.end_value is None:
        return False
    return (
        start_value == event.start_value
        and start_precision == event.start_precision
        and end_value == event.end_value
        and end_precision == event.end_precision
    )


def _event_window_conflicts(
    start_value: str | None,
    start_precision: str,
    end_value: str | None,
    end_precision: str,
    event: Event,
) -> bool:
    """Reject only contradictory date fields present in both observations."""

    start_conflict = (
        start_value is not None
        and event.start_value is not None
        and (
            start_value != event.start_value or start_precision != event.start_precision
        )
    )
    end_conflict = (
        end_value is not None
        and event.end_value is not None
        and (end_value != event.end_value or end_precision != event.end_precision)
    )
    return start_conflict or end_conflict


def _event_strong_identity_conflicts(
    event: Event,
    *,
    canonical_url: str | None,
    external_event_source: str | None,
    external_event_id: str | None,
) -> bool:
    incoming_external = (
        (external_event_source, external_event_id)
        if external_event_source and external_event_id
        else None
    )
    existing_external = (
        (event.external_event_source, event.external_event_id)
        if event.external_event_source and event.external_event_id
        else None
    )
    if (
        incoming_external is not None
        and existing_external is not None
        and incoming_external != existing_external
    ):
        return True
    return bool(
        canonical_url
        and event.canonical_url
        and _normalized_event_url(event.canonical_url) != canonical_url
    )


def _resolve_event_occurrence(
    *,
    brand: Brand,
    title: str,
    organizer_name: str,
    canonical_url: str | None,
    external_event_source: str | None,
    external_event_id: str | None,
    start_value: str | None,
    start_precision: str,
    end_value: str | None,
    end_precision: str,
) -> Event | None:
    """Resolve only strong or exact, date-compatible occurrence candidates."""

    candidates = Event.objects.filter(brand=brand)
    if external_event_source and external_event_id:
        for exact in candidates.filter(
            external_event_source=external_event_source,
            external_event_id=external_event_id,
        ):
            if not _event_window_conflicts(
                start_value,
                start_precision,
                end_value,
                end_precision,
                exact,
            ) and not _event_strong_identity_conflicts(
                exact,
                canonical_url=canonical_url,
                external_event_source=external_event_source,
                external_event_id=external_event_id,
            ):
                return exact
    if canonical_url:
        normalized_url = _normalized_event_url(canonical_url)
        for exact in candidates.filter(canonical_url=normalized_url):
            if _event_strong_identity_conflicts(
                exact,
                canonical_url=canonical_url,
                external_event_source=external_event_source,
                external_event_id=external_event_id,
            ):
                continue
            both_undated = (
                start_value is None
                and end_value is None
                and exact.start_value is None
                and exact.end_value is None
            )
            if both_undated or _event_window_compatible(
                start_value,
                start_precision,
                end_value,
                end_precision,
                exact,
            ):
                return exact
    normalized_title = _normalized_event_text(title)
    normalized_organizer = _normalized_event_text(organizer_name)
    if not normalized_title or not normalized_organizer:
        return None
    for event in candidates.filter(normalized_title=normalized_title):
        if _normalized_event_text(event.organizer_name) != normalized_organizer:
            continue
        if _event_strong_identity_conflicts(
            event,
            canonical_url=canonical_url,
            external_event_source=external_event_source,
            external_event_id=external_event_id,
        ):
            continue
        if _event_window_compatible(
            start_value, start_precision, end_value, end_precision, event
        ):
            return event
    return None


def _missing_job_value(value: Any) -> bool:
    return value is None or value == "" or value == []


def _choice(value: Any, *, allowed: set[str], default: str, field: str) -> str:
    parsed = _text(value, maximum=64) or default
    if parsed not in allowed:
        raise ValueError(f"invalid {field}")
    return parsed


def _confidence(value: Any) -> float:
    parsed = float(value if value is not None else 0.5)
    if not 0.0 <= parsed <= 1.0:
        raise ValueError("confidence must be between 0 and 1")
    return parsed


def _brand_source_text(post: Post) -> str:
    profile_values = post.profile_snapshots.values_list(
        "description",
        "profile_bio_text",
        "affiliate_target_username",
        "affiliate_label_description",
    )
    return "\n".join(
        [
            str(post.text or ""),
            str(post.quoted_text or ""),
            str(post.author_handle or ""),
            *(str(value or "") for row in profile_values for value in row),
        ]
    )


def _brand_evidence_context(post: Post) -> _BrandEvidenceContext:
    return _BrandEvidenceContext(
        source_text=unicodedata.normalize(
            "NFKC", _brand_source_text(post)
        ).casefold(),
        attributed_brand_ids=set(
            post.brands.values_list("brand_id", flat=True)
        ),
        resolved={},
    )


def _known_brand(context: _BrandEvidenceContext, value: Any) -> Brand | None:
    brand_id = _text(value, maximum=64)
    if brand_id is None:
        return None
    if brand_id in context.resolved:
        return context.resolved[brand_id]
    brand = Brand.objects.filter(nickname=brand_id, is_sentinel=False).first()
    if brand is None:
        context.resolved[brand_id] = None
        return None
    if brand.pk in context.attributed_brand_ids:
        context.resolved[brand_id] = brand
        return brand

    source_text = context.source_text
    names = {
        brand.nickname.replace("_", " "),
            brand.display_name,
            brand.display_name_en,
            brand.display_name_zh_cn,
        }
    for name in names:
        normalized = unicodedata.normalize("NFKC", str(name or "")).casefold().strip()
        if not normalized:
            continue
        if normalized.isascii():
            if re.search(rf"(?<![\w]){re.escape(normalized)}(?![\w])", source_text):
                context.resolved[brand_id] = brand
                return brand
        elif normalized in source_text:
            context.resolved[brand_id] = brand
            return brand
    handles = BrandAccount.objects.filter(account__data_source_id="x").filter(brand=brand).exclude(
        account__handle__isnull=True
    ).values_list("account__handle", flat=True)
    if any(
        re.search(
            rf"(?<![\w])@{re.escape(str(handle).removeprefix('@').casefold())}(?![\w])",
            source_text,
        )
        for handle in handles
        if handle
    ):
        context.resolved[brand_id] = brand
        return brand
    raise ValueError("brand_id is not present in source evidence")


def _organization_candidate(
    *, post: Post, name: str, handle: str | None, confidence: float | None
) -> tuple[BrandDiscoveryCandidate, bool]:
    identity = _hash(
        {
            "name": unicodedata.normalize("NFKC", name).casefold(),
            "handle": (handle or "").removeprefix("@").casefold(),
        }
    )
    source_query = None
    if post.source_query_id:
        source_query = SearchQuery.objects.filter(query_id=post.source_query_id).first()
    row, created = BrandDiscoveryCandidate.objects.get_or_create(
        candidate_identity=identity,
        defaults={
            "observed_name": name,
            "candidate_handles": [handle] if handle else [],
            "source_post": post,
            "source_query": source_query,
            "source_identities": [f"post:{post.pk}"],
            "confidence": confidence,
            "verification_status": "pending",
            "first_observed_at": post.fetched_at,
            "last_observed_at": post.fetched_at,
        },
    )
    if not created:
        row = BrandDiscoveryCandidate.objects.select_for_update().get(pk=row.pk)
        changed: list[str] = []
        if post.fetched_at < row.first_observed_at:
            row.first_observed_at = post.fetched_at
            changed.append("first_observed_at")
        if post.fetched_at > row.last_observed_at:
            row.last_observed_at = post.fetched_at
            changed.append("last_observed_at")
        identities = list(row.source_identities or [])
        source_identity = f"post:{post.pk}"
        if source_identity not in identities:
            identities.append(source_identity)
            row.source_identities = identities
            changed.append("source_identities")
        handles = list(row.candidate_handles or [])
        if handle and handle not in handles:
            handles.append(handle)
            row.candidate_handles = handles
            changed.append("candidate_handles")
        if row.source_query_id is None and source_query is not None:
            row.source_query = source_query
            changed.append("source_query")
        if changed:
            row.save(update_fields=changed)
    return row, created


def _organization_label(record: Mapping[str, Any]) -> str:
    """Return source-visible organization text without inventing a name."""

    name = _text(record.get("organization_name"))
    if name is not None:
        return name
    handle = _text(record.get("organization_handle"), maximum=64)
    if handle is not None:
        return handle
    raise ValueError("organization name or handle is required")


def _brand_or_candidate(
    post: Post,
    record: Mapping[str, Any],
    brand_context: _BrandEvidenceContext,
):
    brand = _known_brand(brand_context, record.get("brand_id"))
    if brand is not None:
        return brand, None, 0
    organization = _organization_label(record)
    candidate, created = _organization_candidate(
        post=post,
        name=organization,
        handle=_text(record.get("organization_handle"), maximum=64),
        confidence=_confidence(record.get("confidence")),
    )
    return None, candidate, int(created)


def _source_relationship(post: Post, brand: Brand | None) -> str:
    if post.author_id is None or brand is None:
        return "third_party"
    role = (
        BrandAccount.objects.filter(account__data_source_id="x").filter(account_id=post.author_id, brand=brand)
        .values_list("role_id", flat=True)
        .first()
    )
    return role if role in {"official", "staff"} else "third_party"


@transaction.atomic
def _persist_jobs(post: Post, records: list[Mapping[str, Any]], version: str):
    written = evidence = candidates = 0
    source_urls = _source_urls(post)
    brand_context = _brand_evidence_context(post)
    for record in records:
        organization = _organization_label(record)
        title = _text(record.get("title"), required=True) or ""
        brand, candidate, candidate_created = _brand_or_candidate(
            post, record, brand_context
        )
        candidates += candidate_created
        source_name = _text(record.get("source_name"))
        source_listing_id = _text(record.get("source_listing_id"))
        canonical_url = _source_bound_url(
            record.get("canonical_url"),
            source_urls=source_urls,
            field="canonical",
        )
        application_url = _source_bound_url(
            record.get("application_url"),
            source_urls=source_urls,
            field="application",
        )
        application_route_kind = _choice(
            record.get("application_route_kind"),
            allowed=ALLOWED_APPLICATION_ROUTES,
            default="unresolved",
            field="application route kind",
        )
        application_contact = _text(record.get("application_contact"))
        if application_route_kind in {"direct_url", "careers_page"} and not application_url:
            raise ValueError("URL application route requires an application URL")
        if application_route_kind == "email" and not application_contact:
            raise ValueError("email application route requires application contact")
        status = _choice(
            record.get("status"),
            allowed=ALLOWED_JOB_STATUSES,
            default="unknown",
            field="job status",
        )
        locations = (
            record.get("locations") if isinstance(record.get("locations"), list) else []
        )
        identity_basis = (
            [source_name, source_listing_id]
            if source_name and source_listing_id
            else [canonical_url]
            if canonical_url
            else [organization, title, locations, application_url]
        )
        listing_identity = _hash({"job": _identity_value(identity_basis)})
        now = post.fetched_at
        listing_values = {
            "brand": brand,
            "brand_discovery_candidate": candidate,
            "hiring_organization": organization,
            "source_name": source_name,
            "source_listing_id": source_listing_id,
            "canonical_url": canonical_url,
            "application_url": application_url,
            "application_route_kind": application_route_kind,
            "application_contact": application_contact,
            "application_resolution_status": _text(
                record.get("application_resolution_status")
            ),
            "title": title,
            "description_text": _text(record.get("description_text")),
            "department": _text(record.get("department")),
            "team": _text(record.get("team")),
            "remote_applicant_restrictions": _text(
                record.get("remote_applicant_restrictions")
            ),
            "salary_text": _text(record.get("salary_text")),
            "salary_min": _number(record.get("salary_min")),
            "salary_max": _number(record.get("salary_max")),
            **compensation_references(record),
            "posted_at": _source_datetime(
                record.get("posted_at"), field="posted_at"
            ),
            "updated_source_at": _source_datetime(
                record.get("updated_source_at"), field="updated_source_at"
            ),
            "first_seen_at": now,
            "last_seen_at": now,
            "expires_at": _source_datetime(
                record.get("expires_at"), field="expires_at"
            ),
            "closed_at": _source_datetime(
                record.get("closed_at"), field="closed_at"
            ),
            "status": status,
            "campaign_openings": record.get("campaign_openings"),
            "role_openings": record.get("role_openings"),
            "skills": record.get("skills")
            if isinstance(record.get("skills"), list)
            else [],
            "responsibilities": record.get("responsibilities")
            if isinstance(record.get("responsibilities"), list)
            else [],
            "qualifications": record.get("qualifications")
            if isinstance(record.get("qualifications"), list)
            else [],
            "education_requirements": _text(
                record.get("education_requirements")
            ),
            "experience_requirements": _text(
                record.get("experience_requirements")
            ),
            "benefits": record.get("benefits")
            if isinstance(record.get("benefits"), list)
            else [],
            "eligibility": _text(record.get("eligibility")),
            "source_language": _text(record.get("source_language"), maximum=32),
            "content_hash": _hash(record),
            "extraction_version": version,
            "extraction_confidence": _confidence(record.get("confidence")),
        }
        listing, created = JobListing.objects.get_or_create(
            listing_identity=listing_identity,
            defaults=listing_values,
        )
        written += int(created)
        if created:
            write_source_evidence(listing, raw_payload=dict(record))
        if not created:
            updates: list[str] = []
            if now < listing.first_seen_at:
                listing.first_seen_at = now
                updates.append("first_seen_at")
            if now > listing.last_seen_at:
                listing.last_seen_at = now
                updates.append("last_seen_at")
            for field, value in listing_values.items():
                if field in {
                    "brand",
                    "brand_discovery_candidate",
                    "hiring_organization",
                    "title",
                    "first_seen_at",
                    "last_seen_at",
                    "status",
                    "content_hash",
                    "extraction_version",
                    "extraction_confidence",
                }:
                    continue
                if _missing_job_value(getattr(listing, field)) and not _missing_job_value(
                    value
                ):
                    setattr(listing, field, value)
                    updates.append(field[:-3] if field.endswith("_reference_id") else field)
            if listing.status == "unknown" and status != "unknown":
                listing.status = status
                updates.append("status")
            if updates:
                listing.save(update_fields=[*updates, "updated_at"])
        evidence_hash = _hash(
            {"listing": listing_identity, "post": str(post.pk), "version": version}
        )
        raw_linked_urls = (
            record.get("linked_urls")
            if isinstance(record.get("linked_urls"), list)
            else []
        )
        linked_urls = []
        for value in raw_linked_urls:
            linked_url = _source_bound_url(
                value, source_urls=source_urls, field="linked"
            )
            if linked_url is None:
                raise ValueError("linked URL must be nonblank")
            linked_urls.append(linked_url)
        image_derived_fields = (
            record.get("image_derived_fields")
            if isinstance(record.get("image_derived_fields"), list)
            else []
        )
        if image_derived_fields:
            raise ValueError(
                "image-derived fields require an enabled vision capability"
            )
        _row, evidence_created = JobListingEvidence.objects.get_or_create(
            listing=listing,
            evidence_hash=evidence_hash,
            defaults={
                "source_post": post,
                "observed_author_handle": post.author_handle,
                "observed_author_display_name": post.author_name,
                "source_relationship": _source_relationship(post, brand),
                "evidence_text": (post.text or "")[:5000],
                "linked_urls": linked_urls,
                "observed_at": now,
                "media_url": _source_bound_url(
                    record.get("media_url"),
                    source_urls=source_urls,
                    field="media",
                ),
                "extraction_method": "structured_text",
                "image_derived_fields": image_derived_fields,
                "confidence": _confidence(record.get("confidence")),
                "extraction_identity": version,
            },
        )
        if evidence_created:
            write_source_evidence(_row, raw_evidence={
                "record": dict(record),
                "capabilities": {"ocr": False, "vision": False, "redirect_resolution": False},
            })
        write_job_classifications(listing, record, evidence=_row)
        write_job_locations(
            listing, locations, reported_value=_text(record.get("locations_raw")),
            evidence=_row, observed_at=now,
        )
        evidence += int(evidence_created)
    return written, evidence, candidates


def _personnel_source_packet(post, snapshot=None):
    """Return only exact fields from the selected source and its own clocks."""
    if snapshot is None:
        entries = {
            "text": post.text,
            "quoted_text": post.quoted_text,
            "author_name": post.author_name,
            "author_handle": post.author_handle,
        }
        return {
            f"post:{post.pk}:{field}": {
                "text": value,
                "source_kind": "post" if field != "quoted_text" else "quoted_post_text",
                "published_at": post.created_at.isoformat()
                if post.created_at and field == "text"
                else None,
                "observed_at": post.fetched_at.isoformat() if post.fetched_at else None,
            }
            for field, value in entries.items()
            if isinstance(value, str) and value
        }
    entries = {
        "description": snapshot.description,
        "profile_bio_text": snapshot.profile_bio_text,
        "display_name": snapshot.display_name,
        "handle": snapshot.handle,
    }
    return {
        f"profile:{snapshot.pk}:{field}": {
            "text": value,
            "source_kind": "profile_snapshot",
            "published_at": None,
            "observed_at": snapshot.first_observed_at.isoformat(),
            "last_observed_at": snapshot.last_observed_at.isoformat(),
        }
        for field, value in entries.items()
        if field in snapshot.present_fields and isinstance(value, str) and value
    }


def _personnel_field_evidence(post, snapshot, record):
    """Validate exact cited spans; semantic interpretation remains pending review."""
    allowed_record_fields = _PERSONNEL_EVIDENCE_FIELDS | {
        "start_date_precision",
        "end_date_precision",
        "confidence",
        "source_profile_snapshot_id",
        "source_quote",
        "field_evidence",
    }
    if set(record) - allowed_record_fields:
        raise ValueError("Unknown modern personnel record fields")
    payload = record.get("field_evidence")
    if (
        not isinstance(payload, Mapping)
        or set(payload) != {"schema", "fields"}
        or payload.get("schema") != PERSONNEL_FIELD_EVIDENCE_SCHEMA
        or not isinstance(payload.get("fields"), Mapping)
    ):
        raise ValueError("Personnel field evidence requires the versioned schema")
    fields = payload["fields"]
    if any(
        not isinstance(record.get(key), str)
        or not record[key].strip()
        or record[key].strip().casefold() == "unknown"
        for key in ("person_name", "organization_name", "affiliation_type")
    ):
        raise ValueError(
            "Modern personnel records require an explicit person, organization and affiliation type"
        )
    required = {
        key
        for key in _PERSONNEL_EVIDENCE_FIELDS
        if record.get(key) not in (None, "", "unknown")
    }
    required.update({"person_name", "organization_name", "affiliation_type"})
    if set(fields) != required:
        raise ValueError("Personnel evidence must cover exactly the populated fields")
    sources = _personnel_source_packet(post, snapshot)
    normalized = {}
    for field, claims in fields.items():
        if not isinstance(claims, list) or not 1 <= len(claims) <= 10:
            raise ValueError("Personnel field evidence requires one or more sources")
        normalized[field] = []
        for claim in claims:
            if not isinstance(claim, Mapping) or set(claim) != {
                "source_key",
                "span",
                "basis",
            }:
                raise ValueError("Invalid personnel field evidence claim")
            key, span, basis = claim["source_key"], claim["span"], claim["basis"]
            if not isinstance(key, str) or key not in sources:
                raise ValueError(
                    "Personnel field evidence source does not match the selected source"
                )
            if (
                not isinstance(span, str)
                or not span
                or len(span) > 5000
                or span not in sources[key]["text"]
            ):
                raise ValueError(
                    "Personnel field evidence span must match exact source text"
                )
            if not isinstance(basis, str) or basis not in {"explicit", "inferred"}:
                raise ValueError(
                    "Personnel field evidence basis must be explicit or inferred"
                )
            if basis == "explicit" and field in {
                "person_name",
                "person_handle",
                "organization_name",
                "organization_handle",
                "title_raw",
                "title_normalized",
                "department",
                "team",
                "job_function",
                "description",
                "seniority",
            }:
                value = str(record[field]).strip().removeprefix("@").casefold()
                if value not in span.casefold():
                    raise ValueError(
                        "Explicit personnel field value is not present in its cited span"
                    )
            if basis == "explicit" and field in {"start_date", "end_date"}:
                value = str(record[field])
                parts = value.split("-")
                if (
                    len(parts) not in (1, 2, 3)
                    or not parts[0].isdigit()
                    or parts[0] not in span
                ):
                    raise ValueError(
                        "Explicit personnel date year is not present in its cited span"
                    )
                if len(parts) > 1:
                    try:
                        month = int(parts[1])
                        names = (calendar.month_name[month], calendar.month_abbr[month])
                    except (IndexError, ValueError):
                        raise ValueError("Invalid explicit personnel date") from None
                    lower = span.casefold()
                    if not any(
                        name and name.casefold() in lower for name in names
                    ) and not re.search(rf"(?<!\d)0?{month}(?:\D|$)", span):
                        raise ValueError(
                            "Explicit personnel date month is not present in its cited span"
                        )
                if len(parts) > 2 and not re.search(
                    rf"(?<!\d)0?{int(parts[2])}(?:\D|$)", span
                ):
                    raise ValueError(
                        "Explicit personnel date day is not present in its cited span"
                    )
            if (
                field in {"start_date", "end_date"}
                and basis == "inferred"
                and not sources[key]["published_at"]
            ):
                raise ValueError(
                    "Inferred personnel dates require source publication time"
                )
            if field in {"start_date", "end_date"} and basis == "inferred":
                published = datetime.fromisoformat(sources[key]["published_at"])
                if published.day <= 2 or published.day >= 28:
                    raise ValueError(
                        "Relative personnel date crosses an uncertain time-zone boundary"
                    )
                lower = span.casefold()
                offsets = [
                    offset
                    for phrase, offset in (
                        ("next month", 1),
                        ("this month", 0),
                        ("last month", -1),
                    )
                    if phrase in lower
                ]
                if len(offsets) == 1:
                    month_index = published.year * 12 + published.month - 1 + offsets[0]
                    expected = f"{month_index // 12:04d}-{month_index % 12 + 1:02d}"
                elif not offsets and field == "start_date":
                    # A departure to join the named organization supports an
                    # inferred arrival; its semantics remain pending review.
                    names = "|".join(calendar.month_name[1:])
                    organization = re.escape(str(record["organization_name"]).strip())
                    match = re.search(
                        rf"\bleft\s+[^.?!,;]+?\s+in\s+({names})\s+to\s+join\s+{organization}\b",
                        span,
                        flags=re.IGNORECASE,
                    )
                    if match is None:
                        raise ValueError(
                            "Inferred personnel date needs a supported relative month"
                        )
                    month = list(calendar.month_name).index(match.group(1).capitalize())
                    year = published.year - (month > published.month)
                    expected = f"{year:04d}-{month:02d}"
                else:
                    raise ValueError(
                        "Inferred personnel date needs a supported relative month"
                    )
                if (
                    record[field] != expected
                    or record.get(field + "_precision") != "month"
                ):
                    raise ValueError(
                        "Inferred personnel date differs from its source publication month"
                    )
            normalized[field].append(
                {
                    "source_key": key,
                    "span": span,
                    "basis": basis,
                    **{k: v for k, v in sources[key].items() if k != "text"},
                }
            )
    return {
        "schema": PERSONNEL_FIELD_EVIDENCE_SCHEMA,
        "fields": normalized,
        "validation": "exact_span_verified_semantics_pending_review",
    }


@transaction.atomic
def _persist_personnel(post: Post, records: list[Mapping[str, Any]], version: str):
    written = evidence = candidates = 0
    brand_context = _brand_evidence_context(post)
    for record in records:
        source_snapshot = None
        source_quote = None
        snapshot_id = record.get("source_profile_snapshot_id")
        if snapshot_id is not None:
            if type(snapshot_id) is not int or snapshot_id <= 0:
                raise ValueError("Invalid profile snapshot identity")
            source_snapshot = post.profile_snapshots.filter(pk=snapshot_id, account_id=post.author_id).first()
            source_quote = _text(record.get("source_quote"), required=True)
            if source_snapshot is None or not any(source_quote in (value or "") for value in (source_snapshot.description, source_snapshot.profile_bio_text)):
                raise ValueError("Profile source quote or identity does not match")
            quote_context = _BrandEvidenceContext(
                source_text=unicodedata.normalize("NFKC", source_quote).casefold(),
                attributed_brand_ids=set(),
                resolved={},
            )
            if record.get("brand_id"):
                if _known_brand(quote_context, record["brand_id"]) is None:
                    raise ValueError("Profile quote does not support brand")
            else:
                organization = _text(record.get("organization_name"), required=True)
                if unicodedata.normalize("NFKC", organization).casefold() not in quote_context.source_text:
                    raise ValueError("Profile quote does not support organization")
        stored_record = dict(record)
        if version in _PERSONNEL_FIELD_EVIDENCE_VERSIONS or "field_evidence" in record:
            stored_record["field_evidence"] = _personnel_field_evidence(post, source_snapshot, record)
        person_name = _text(record.get("person_name"), required=True) or ""
        brand, candidate, candidate_created = _brand_or_candidate(
            post, record, brand_context
        )
        candidates += candidate_created
        if candidate is not None:
            movement = ProfileMovementCandidate.objects.filter(
                source_post=post, status__in=["pending", "failed"]
            ).order_by("id").first()
            if movement is not None:
                organization = _organization_label(record)
                handle = _text(record.get("organization_handle"), maximum=64)
                tokens = [{
                    "form": organization,
                    "kind": "spelling",
                    "script": (
                        "han" if any("\u4e00" <= char <= "\u9fff" for char in organization)
                        else "latn"
                    ),
                }]
                if handle and handle != organization:
                    tokens.append({"form": handle, "kind": "handle", "script": "latn"})
                record_unknown_name_tokens_from_movement(
                    movement=movement, candidate=candidate, tokens=tokens
                )
        person_handle = _text(record.get("person_handle"), maximum=64)
        normalized_handle = (person_handle or "").removeprefix("@").casefold()
        self_authored = bool(
            post.author_id
            and normalized_handle
            and post.author_handle
            and normalized_handle
            == post.author_handle.removeprefix("@").casefold()
        )
        person = subject_person(
            handle=normalized_handle,
            display_name=person_name,
            source_key="source-post:" + str(post.pk) + ":name:"
            + unicodedata.normalize("NFKC", person_name).casefold(),
            account=post.author if self_authored else None,
            observed_at=post.fetched_at,
        )
        affiliation_type = (
            _text(record.get("affiliation_type"), maximum=32) or "employment"
        )
        status = _text(record.get("status"), maximum=16) or "unknown"
        if (
            affiliation_type not in ALLOWED_AFFILIATION_TYPES
            or status not in ALLOWED_RELATIONSHIP_STATUSES
        ):
            raise ValueError("invalid affiliation type or status")
        start = _temporal_value(
            record.get("start_date"),
            record.get("start_date_precision"),
            field="affiliation start date",
            allow_datetime=False,
        )
        end = _temporal_value(
            record.get("end_date"),
            record.get("end_date_precision"),
            field="affiliation end date",
            allow_datetime=False,
        )
        _temporal_range(start=start, end=end, field="affiliation")
        start_value, start_precision, _start_parsed = start
        end_value, end_precision, _end_parsed = end
        organization_identity = (
            f"brand:{brand.pk}" if brand is not None else f"candidate:{candidate.pk}"
        )
        claim_payload = {
            "organization": organization_identity,
            "type": affiliation_type,
            "status": status,
            "title": _text(record.get("title_raw")),
            "start": start_value,
            "end": end_value,
        }

        def identity_for(pk, payload=claim_payload):
            return _hash({"person": str(pk), **payload})

        moved = matching_moved_claim(person, identity_for)
        claim_identity = moved.claim_identity if moved else identity_for(person.pk)
        affiliation, created = PersonBrandAffiliation.objects.get_or_create(
            claim_identity=claim_identity,
            defaults={
                "person": person,
                "brand": brand,
                "brand_discovery_candidate": candidate,
                "affiliation_type_reference": AffiliationType.objects.get(
                    code=affiliation_type
                ),
                "observed_organization_name": _text(
                    record.get("organization_name"), required=True
                ),
                "observed_organization_handle": _text(
                    record.get("organization_handle"), maximum=64
                ),
                "title_raw": _text(record.get("title_raw")),
                "title_normalized": _text(record.get("title_normalized")),
                "department": _text(record.get("department")),
                "team": _text(record.get("team")),
                "job_function": _text(record.get("job_function")),
                "description": _text(record.get("description")),
                "seniority": _text(record.get("seniority")),
                "employment_type": _text(record.get("employment_type")),
                "status": status,
                "start_date": start_value,
                "start_date_precision": start_precision,
                "end_date": end_value,
                "end_date_precision": end_precision,
                "confidence": _confidence(record.get("confidence")),
                "review_status": "pending",
                "source_system": version,
            },
        )
        require_claim_owner(affiliation, person)
        if not created:
            affiliation = PersonBrandAffiliation.objects.select_for_update().get(pk=affiliation.pk)
            require_claim_owner(affiliation, person)
            if affiliation.review_status != "rejected" and not affiliation.superseded_at and not affiliation.superseded_by_id:
                updates = {}
                for field in ("title_normalized", "department", "team", "job_function", "description", "seniority", "employment_type"):
                    candidate_value = _text(record.get(field))
                    if candidate_value and not getattr(affiliation, field):
                        updates[field] = candidate_value
                if updates:
                    PersonBrandAffiliation.objects.filter(pk=affiliation.pk).update(**updates)
        written += int(created)
        evidence_identity = {"claim": claim_identity, "post": str(post.pk), "version": version}
        if source_snapshot is not None:
            evidence_identity.update(snapshot=source_snapshot.pk, quote=source_quote)
        evidence_hash = _hash(evidence_identity)
        previous_evidence = PersonBrandAffiliationEvidence.objects.filter(
            affiliation=affiliation, evidence_hash=evidence_hash
        ).first()
        if previous_evidence is not None:
            previous_payload = AffiliationClaimEvidence.objects.filter(
                pk=previous_evidence.pk
            ).values_list("extracted_claim_data", flat=True).first()
            if previous_payload != stored_record:
                evidence_hash = _hash({**evidence_identity, "record": stored_record})
        _row, evidence_created = PersonBrandAffiliationEvidence.objects.get_or_create(
            affiliation=affiliation,
            evidence_hash=evidence_hash,
            defaults={
                "source_post": post if source_snapshot is None else None,
                "source_profile_snapshot": source_snapshot,
                "evidence_text": (post.text or "")[:5000] if source_snapshot is None else source_quote,
                "observed_at": post.fetched_at if source_snapshot is None else source_snapshot.first_observed_at,
                "extraction_method": "structured_text",
                "extraction_model": None,
                "extraction_prompt_version": version,
                "confidence": _confidence(record.get("confidence")),
                "review_status": "pending",
            },
        )
        if evidence_created:
            write_source_evidence(_row, extracted_claim_data=stored_record)
        evidence += int(evidence_created)
    return written, evidence, candidates


def _persist_profile_personnel(post: Post, records: list[Mapping[str, Any]], version: str):
    if any(record.get("source_profile_snapshot_id") is None for record in records):
        raise ValueError("Profile extraction requires a sourced snapshot")
    return _persist_personnel(post, records, version)


def _persist_events(post: Post, records: list[Mapping[str, Any]], version: str):
    written = evidence = candidates = 0
    source_urls = _source_urls(post)
    brand_context = _brand_evidence_context(post)
    for record in records:
        attendance_mode = _choice(
            record.get("attendance_mode"),
            allowed=ALLOWED_EVENT_MODES,
            default="unknown",
            field="event attendance mode",
        )
        source_status = _choice(
            record.get("source_status"),
            allowed=ALLOWED_EVENT_STATUSES,
            default="unknown",
            field="event source status",
        )
        start = _temporal_value(
            record.get("start_value"),
            record.get("start_precision"),
            field="event start",
            allow_datetime=True,
        )
        end = _temporal_value(
            record.get("end_value"),
            record.get("end_precision"),
            field="event end",
            allow_datetime=True,
        )
        _temporal_range(start=start, end=end, field="event")
        start_value, start_precision, _start_parsed = start
        end_value, end_precision, _end_parsed = end
        brand = _known_brand(brand_context, record.get("brand_id"))
        candidate = None
        if brand is None:
            candidate, created = _organization_candidate(
                post=post,
                name=_text(record.get("organization_name"), required=True) or "",
                handle=_text(record.get("organization_handle"), maximum=64),
                confidence=_confidence(record.get("confidence")),
            )
            candidates += int(created)
        title = _text(record.get("title"), required=True) or ""
        organizer_name = _text(record.get("organization_name"), required=True) or ""
        source_url = _source_bound_url(
            record.get("source_url"), source_urls=source_urls, field="source"
        )
        external_event_source = _normalized_event_text(
            record.get("external_event_source")
        )
        external_event_id = _text(record.get("external_event_id"))
        if not external_event_source or not external_event_id:
            external_event_source = None
            external_event_id = None
        canonical_url = _source_bound_url(
            record.get("canonical_url"),
            source_urls=source_urls,
            field="canonical",
        )
        canonical_url = _normalized_event_url(canonical_url)
        existing = _resolve_event_occurrence(
            brand=brand,
            title=title,
            organizer_name=organizer_name,
            canonical_url=canonical_url,
            external_event_source=external_event_source,
            external_event_id=external_event_id,
            start_value=start_value,
            start_precision=start_precision,
            end_value=end_value,
            end_precision=end_precision,
        ) if brand is not None else None
        owner_identity = str(brand.pk) if brand is not None else f"candidate:{candidate.pk}"
        identity = (
            _hash(
                {
                    "brand": owner_identity,
                    "external_event_source": external_event_source,
                    "external_event_id": external_event_id,
                    "canonical_url": canonical_url,
                    "start": [start_value, start_precision],
                    "end": [end_value, end_precision],
                }
            )
            if external_event_source and external_event_id
            else _hash(
                {
                    "brand": owner_identity,
                    "canonical_url": canonical_url,
                    "start": [start_value, start_precision],
                    "end": [end_value, end_precision],
                }
            )
            if canonical_url
            else _hash(
                {
                    "brand": owner_identity,
                    "title": _normalized_event_text(title),
                    "organizer": _normalized_event_text(organizer_name),
                    "start": [start_value, start_precision],
                    "end": [end_value, end_precision],
                    **(
                        {"post": str(post.pk)}
                        if start_value is None and end_value is None
                        else {}
                    ),
                }
            )
        )
        if existing is not None:
            _row, created = existing, False
        else:
            _row, created = Event.objects.get_or_create(
                event_identity=identity,
                defaults={
                    "brand": brand,
                    "brand_discovery_candidate": candidate,
                    "source_post": post,
                    "source_url": source_url,
                    "canonical_url": canonical_url,
                    "external_event_source": external_event_source,
                    "external_event_id": external_event_id,
                    "normalized_title": _normalized_event_text(title),
                    "title": title,
                    "organizer_name": organizer_name,
                    "organizer_handle": _text(
                        record.get("organization_handle"), maximum=64
                    ),
                    "attendance_mode": attendance_mode,
                    "physical_location": _text(record.get("physical_location")),
                    "virtual_location": _text(record.get("virtual_location")),
                    "attendance_url": _source_bound_url(
                        record.get("attendance_url"),
                        source_urls=source_urls,
                        field="attendance",
                    ),
                    "start_value": start_value,
                    "start_precision": start_precision,
                    "end_value": end_value,
                    "end_precision": end_precision,
                    "source_timezone_reference_id": _time_zone_reference_id(
                        record.get("source_timezone")
                    ),
                    "source_schedule_text": _text(record.get("source_schedule_text")),
                    "source_status": source_status,
                    "first_seen_at": post.fetched_at,
                    "last_seen_at": post.fetched_at,
                    "content_hash": _hash(record),
                    "extraction_version": version,
                    "extraction_confidence": _confidence(record.get("confidence")),
                    "review_status": "pending",
                    "raw_payload": dict(record),
                },
            )
        evidence_hash = _hash(
            {"post": str(post.pk), "record": record, "version": version}
        )
        _evidence, evidence_created = EventEvidence.objects.get_or_create(
            event=_row,
            source_post=post,
            evidence_hash=evidence_hash,
            defaults={
                "source_url": source_url,
                "observed_title": title,
                "observed_organizer_name": organizer_name,
                "observed_start_value": start_value,
                "observed_start_precision": start_precision,
                "observed_end_value": end_value,
                "observed_end_precision": end_precision,
                "observed_at": post.fetched_at,
                "extraction_version": version,
                "extraction_confidence": _confidence(record.get("confidence")),
                "raw_payload": dict(record),
            },
        )
        if not created:
            update_fields = []
            if post.fetched_at < _row.first_seen_at:
                _row.first_seen_at = post.fetched_at
                update_fields.append("first_seen_at")
            if post.fetched_at > _row.last_seen_at:
                _row.last_seen_at = post.fetched_at
                update_fields.append("last_seen_at")
            if external_event_source and external_event_id:
                merged_start = _temporal_value(
                    _row.start_value or start_value,
                    (
                        _row.start_precision
                        if _row.start_value is not None
                        else start_precision
                    ),
                    field="merged event start",
                    allow_datetime=True,
                )
                merged_end = _temporal_value(
                    _row.end_value or end_value,
                    (
                        _row.end_precision
                        if _row.end_value is not None
                        else end_precision
                    ),
                    field="merged event end",
                    allow_datetime=True,
                )
                _temporal_range(
                    start=merged_start,
                    end=merged_end,
                    field="merged event",
                )
                if _row.start_value is None and start_value is not None:
                    _row.start_value = start_value
                    _row.start_precision = start_precision
                    update_fields.extend(["start_value", "start_precision"])
                if _row.end_value is None and end_value is not None:
                    _row.end_value = end_value
                    _row.end_precision = end_precision
                    update_fields.extend(["end_value", "end_precision"])
                if _row.external_event_source is None:
                    _row.external_event_source = external_event_source
                    _row.external_event_id = external_event_id
                    update_fields.extend(["external_event_source", "external_event_id"])
            if _row.canonical_url is None and canonical_url is not None:
                _row.canonical_url = canonical_url
                update_fields.append("canonical_url")
            if update_fields:
                _row.save(update_fields=update_fields)
        written += int(created)
        evidence += int(evidence_created)
    return written, evidence, candidates


def _persist_opportunities(post: Post, records: list[Mapping[str, Any]], version: str):
    written = candidates = 0
    source_urls = _source_urls(post)
    brand_context = _brand_evidence_context(post)
    events_by_brand: dict[str, list[Event]] = {}
    for event in (
        Event.objects.filter(Q(source_post=post) | Q(evidence__source_post=post))
        .distinct()
        .order_by("id")
    ):
        events_by_brand.setdefault(str(event.brand_id), []).append(event)
    for record in records:
        opportunity_type = _choice(
            record.get("opportunity_type"),
            allowed=ALLOWED_OPPORTUNITY_TYPES,
            default="other",
            field="opportunity type",
        )
        source_status = _choice(
            record.get("source_status"),
            allowed=ALLOWED_OPPORTUNITY_STATUSES,
            default="unknown",
            field="opportunity source status",
        )
        opens = _temporal_value(
            record.get("open_value"),
            record.get("open_precision"),
            field="opportunity open",
            allow_datetime=True,
        )
        closes = _temporal_value(
            record.get("close_value"),
            record.get("close_precision"),
            field="opportunity close",
            allow_datetime=True,
        )
        _temporal_range(start=opens, end=closes, field="opportunity")
        open_value, open_precision, _open_parsed = opens
        close_value, close_precision, _close_parsed = closes
        brand = _known_brand(brand_context, record.get("brand_id"))
        candidate = None
        if brand is None:
            candidate, created = _organization_candidate(
                post=post,
                name=_text(record.get("organization_name"), required=True) or "",
                handle=_text(record.get("organization_handle"), maximum=64),
                confidence=_confidence(record.get("confidence")),
            )
            candidates += int(created)
        related_event = None
        related_event_title = _text(record.get("related_event_title"))
        possible_events = events_by_brand.get(str(brand.pk), []) if brand else []
        if related_event_title:
            related_event = next(
                (
                    event
                    for event in possible_events
                    if _normalized_event_text(event.title)
                    == _normalized_event_text(related_event_title)
                    and (
                        event.source_post_id == post.pk
                        or _event_window_compatible(
                            opens[0], opens[1], closes[0], closes[1], event
                        )
                    )
                ),
                None,
            )
        elif len(possible_events) == 1:
            related_event = possible_events[0]
        identity = _hash({"post": str(post.pk), "record": record, "version": version})
        _row, created = Opportunity.objects.get_or_create(
            opportunity_identity=identity,
            defaults={
                "brand": brand,
                "brand_discovery_candidate": candidate,
                "related_event": related_event,
                "source_post": post,
                "source_url": _source_bound_url(
                    record.get("source_url"),
                    source_urls=source_urls,
                    field="source",
                ),
                "sponsor_name": _text(record.get("organization_name"), required=True),
                "sponsor_handle": _text(record.get("organization_handle"), maximum=64),
                "opportunity_type_reference": OpportunityType.objects.get(
                    code=opportunity_type
                ),
                "action_type": _text(record.get("action_type"), required=True),
                "action_url": _source_bound_url(
                    record.get("action_url"),
                    source_urls=source_urls,
                    field="action",
                ),
                "benefit_type": _text(record.get("benefit_type"), required=True),
                "benefit_value": _number(record.get("benefit_value")),
                "benefit_currency": _text(record.get("benefit_currency"), maximum=8),
                "benefit_text": _text(record.get("benefit_text")),
                "eligibility": _text(record.get("eligibility")),
                "geographic_restrictions": _text(record.get("geographic_restrictions")),
                "open_value": open_value,
                "open_precision": open_precision,
                "close_value": close_value,
                "close_precision": close_precision,
                "source_timezone_reference_id": _time_zone_reference_id(
                    record.get("source_timezone")
                ),
                "source_availability_text": _text(
                    record.get("source_availability_text")
                ),
                "source_status": source_status,
                "first_seen_at": post.fetched_at,
                "last_seen_at": post.fetched_at,
                "content_hash": _hash(record),
                "extraction_version": version,
                "extraction_confidence": _confidence(record.get("confidence")),
                "review_status": "pending",
                "raw_payload": dict(record),
            },
        )
        written += int(created)
    return written, 0, candidates


def _persist_categories(
    *,
    post: Post,
    record: Mapping[str, Any],
    version: str,
    brand: Brand | None,
    candidate: BrandDiscoveryCandidate | None,
) -> int:
    categories = record.get("categories") or []
    if not isinstance(categories, list) or any(
        category not in ALLOWED_RARE_CATEGORIES for category in categories
    ):
        raise ValueError("invalid rare-type categories")
    written = 0
    for category in set(categories):
        _row, created = RareTypeCategoryAssignment.objects.get_or_create(
            post=post,
            brand=brand,
            brand_discovery_candidate=candidate,
            category=category,
            defaults={
                "source_evidence": dict(record),
                "classification_version": version,
            },
        )
        written += int(created)
    return written


def _persist_release_proposal(post, record, model_name, brand, candidate, dossier, *, publisher_scoped=False):
    candidate_repo_id = _text(record.get("candidate_repo_id"), maximum=256) or ""
    if post.author_id and (brand is not None or candidate is not None):
        source_identity_evidence = source_repo_evidence(post, candidate_repo_id)
        proposal, _ = ProductVerificationProposal.objects.get_or_create(
            proposal_key=_hash(
                {
                    "post": str(post.pk),
                    "account": str(post.author_id),
                    "model": model_name,
                    "repo": candidate_repo_id.casefold(),
                    **({"publisher": str(brand.pk) if brand else f"candidate:{candidate.pk}"}
                       if publisher_scoped else {}),
                }
            ),
            defaults={
                "source_post": post,
                "source_dossier": dossier,
                "proposed_brand": brand,
                "proposed_candidate": candidate,
                "account_id": post.author_id,
                "account_handle_snapshot": post.author_handle or "",
                "observed_name": model_name,
                "candidate_repo_id": candidate_repo_id,
                "account_evidence": {
                    "stable_account_id": post.author.author_id,
                    "handle": post.author_handle or "",
                    "account_handle_at_extraction": post.author.handle or "",
                    "account_verified_type": code_for(post.author, "verified_type"),
                    "post_author_verified_type": code_for(post, "author_verified_type"),
                    **source_identity_evidence,
                },
                "policy_version": POLICY_VERSION,
                "hf_outcome": "pending" if candidate_repo_id else "deferred",
                "rule_trace": [
                    (
                        "awaiting_exact_public_hf_metadata"
                        if source_identity_evidence["exact_hf_repo_link"]
                        else "source_exact_repo_link_missing_owner_review_required"
                    )
                    if candidate_repo_id
                    else "candidate_repo_id_missing_owner_review_required",
                ],
            },
        )
        if proposal.source_dossier_id is None:
            proposal.source_dossier = dossier
            proposal.save(update_fields=["source_dossier"])
        release_stops = {"automatic_verification_stopped:release_superseded",
                         "automatic_verification_stopped:release_reassessment_pending",
                         "automatic_verification_stopped:release_evidence_stale"}
        if proposal.review_status == "pending" and release_stops.intersection(proposal.rule_trace):
            trace = [item for item in proposal.rule_trace if item not in release_stops]
            proposal.account_evidence = {**dict(proposal.account_evidence or {}), **source_identity_evidence}
            if source_identity_evidence["exact_hf_repo_link"]:
                trace = [item for item in trace if item != "automatic_verification_stopped:source_exact_repo_link_missing"]
                if candidate_repo_id and proposal.hf_outcome == "deferred":
                    proposal.hf_outcome = "pending"
            if not any(str(item).startswith("automatic_verification_stopped:") for item in trace):
                trace = [item for item in trace if item != "automatic_verification_stopped"]
            proposal.rule_trace = trace
            proposal.source_dossier = dossier
            proposal.save(update_fields=["source_dossier", "account_evidence", "hf_outcome", "rule_trace", "updated_at"])
        # The established proposal key can cover several distinct reports
        # from the same Post. Keep its first linked dossier and preserve
        # every additional report as its own source claim.


def persist_pulse_release_projections(post, findings, version, *, reconcile=False):
    """Keep the existing rare-type and verification readers on the saved evidence."""
    from core.classified_product_releases import read_publication_findings
    from core.models import EventDossierClaim, PostBrandClassificationJudgment

    saved = {row["finding"]["finding_key"]: row for row in (read_publication_findings(post.pk, allow_pending=True) or [])}
    if reconcile:
        # These are projections of selected release claims. Keep the claims,
        # but retire projections that no longer represent the selected answer.
        keep_categories = {(f.get("brand_id"), f.get("brand_candidate_id"), f.get("category")) for f in findings}
        for category in RareTypeCategoryAssignment.objects.filter(post=post, classification_version=version):
            if (category.brand_id, category.brand_discovery_candidate_id, category.category) not in keep_categories:
                category.delete()
        revisions = PostBrandClassificationJudgment.objects.filter(
            post=post, prompt_version=version, provider_role="targeted-release",
        ).values_list("revision_id", flat=True)
        dossier_ids = EventDossierClaim.objects.filter(
            event_dossier_source__post=post,
            extraction_version__in=[f"pulse-classified-findings-v1:{revision}" for revision in revisions],
        ).values_list("event_dossier_source__event_dossier_id", flat=True)
        keep_proposals = {(str(f.get("observed_name") or ""), str(f.get("candidate_repo_id") or "").casefold(),
                           f.get("brand_id"), f.get("brand_candidate_id"))
                          for f in findings}
        for proposal in ProductVerificationProposal.objects.select_for_update().filter(
            source_post=post, source_dossier_id__in=dossier_ids, review_status="pending",
        ):
            if (proposal.observed_name, proposal.candidate_repo_id.casefold(), proposal.proposed_brand_id,
                    proposal.proposed_candidate_id) not in keep_proposals:
                proposal.rule_trace = [*proposal.rule_trace, "automatic_verification_stopped",
                                       "automatic_verification_stopped:release_superseded"]
                proposal.verification_claim_token = None
                proposal.verification_claim_expires_at = None
                proposal.save(update_fields=["rule_trace", "verification_claim_token", "verification_claim_expires_at", "updated_at"])
    for finding in findings:
        row = saved.get(finding["finding_key"])
        if row is None:
            raise ValueError("targeted_release_projection_missing_finding")
        brand = Brand.objects.filter(pk=finding.get("brand_id")).first() if finding.get("brand_id") else None
        candidate = (BrandDiscoveryCandidate.objects.filter(pk=finding["brand_candidate_id"]).first()
                     if finding.get("brand_candidate_id") else None)
        if brand is None and candidate is None:
            continue
        record = {"categories": [finding["category"]] if finding.get("category") else [],
                  "candidate_repo_id": finding.get("candidate_repo_id") or ""}
        _persist_categories(post=post, record=record, version=version, brand=brand, candidate=candidate)
        claim = EventDossierClaim.objects.select_related("event_dossier_source__event_dossier").get(pk=row["anchor_claim_id"])
        if finding.get("observed_name"):
            _persist_release_proposal(post, record, finding["observed_name"], brand, candidate,
                                      claim.event_dossier_source.event_dossier, publisher_scoped=True)


def _persist_product_release_reports(
    post: Post, records: list[Mapping[str, Any]], version: str
):
    written = evidence = candidates = 0
    source_urls = _source_urls(post)
    brand_context = _brand_evidence_context(post)
    for record in records:
        brand = _known_brand(brand_context, record.get("brand_id"))
        candidate = None
        organization_name = _text(record.get("organization_name"))
        if brand is None and organization_name:
            candidate, created = _organization_candidate(
                post=post,
                name=organization_name,
                handle=_text(record.get("organization_handle"), maximum=64),
                confidence=_confidence(record.get("confidence")),
            )
            candidates += int(created)
        model_name = _text(record.get("model_name")) or ""
        categories = record.get("categories") or []
        if not isinstance(categories, list) or any(
            category not in ALLOWED_RARE_CATEGORIES for category in categories
        ):
            raise ValueError("invalid rare-type categories")
        # Owner-bound category rows cannot represent an unidentified publisher.
        # The immutable source packet still retains the extracted categories.
        if brand is not None or candidate is not None:
            _persist_categories(
                post=post,
                record=record,
                version=version,
                brand=brand,
                candidate=candidate,
            )
        if not model_name:
            continue
        version_value = _text(record.get("version")) or ""
        channel = _choice(
            record.get("release_channel"),
            allowed=ALLOWED_RELEASE_CHANNELS,
            default="other",
            field="release channel",
        )
        release_value, release_precision, _parsed = _temporal_value(
            record.get("release_value"),
            record.get("release_precision"),
            field="model release",
            allow_datetime=False,
        )
        source_url = _source_bound_url(
            record.get("source_url"), source_urls=source_urls, field="source"
        )
        owner_identity = (
            f"brand:{brand.pk}" if brand is not None else
            f"candidate:{candidate.pk}" if candidate is not None else "owner:unknown"
        )
        identity = _hash(
            {
                "owner": owner_identity,
                "model": unicodedata.normalize("NFKC", model_name).casefold(),
                "version": version_value,
                "channel": channel,
                **({"source_url": source_url} if not version_value else {}),
                # A bare name is a source-level candidate, not a cross-post
                # release identity. Later evidence may reconcile these dossiers.
                **({"unresolved_source_post": str(post.pk)}
                   if (brand is None and candidate is None)
                   or (source_url is None and not version_value) else {}),
            }
        )
        dossier, created, evidence_created = record_release_report(
            post=post,
            record=dict(record),
            release_identity=identity,
            observed_name=model_name,
            source_url=source_url,
            brand=brand,
            candidate=candidate,
            maturity_code=channel,
            release_value=release_value,
            release_precision=release_precision,
            extraction_version=version,
            queue_acquisition=True,
        )
        _persist_release_proposal(post, record, model_name, brand, candidate, dossier)
        written += int(created)
        evidence += int(evidence_created)
    return written, evidence, candidates


_PERSISTERS = {
    "event_extraction": _persist_events,
    "opportunity_extraction": _persist_opportunities,
    "job_listing_extraction": _persist_jobs,
    "personnel_change_extraction": _persist_personnel,
    "profile_affiliation_extraction": _persist_profile_personnel,
    "model_release_extraction": _persist_product_release_reports,
}


def _parse_response(
    value: Mapping[str, Any] | str,
) -> tuple[list[Mapping[str, Any]], dict[str, int]]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, Mapping) or set(value) - {"records", "usage"}:
        raise ValueError(
            "targeted response must contain only records and optional usage"
        )
    records = value.get("records")
    if not isinstance(records, list) or not all(
        isinstance(row, Mapping) for row in records
    ):
        raise ValueError("targeted response records must be an array of objects")
    if len(records) > _MAX_RECORDS_PER_RESPONSE:
        raise ValueError("targeted response has too many records")
    usage = value.get("usage") if isinstance(value.get("usage"), Mapping) else {}
    return records, {
        "input_tokens": max(int(usage.get("input_tokens") or 0), 0),
        "output_tokens": max(int(usage.get("output_tokens") or 0), 0),
    }


def request_targeted_release(post_id, *, model, content_identity=None, reopen=False):
    """Record release work without changing an already published feed judgment."""
    state, created = TargetedExtractionState.objects.get_or_create(
        post_id=post_id, role="model_release_extraction",
        defaults={"content_identity": content_identity or "0" * 64, "model": model,
                  "prompt_version": "model-release-extraction-v2", "status": "pending"},
    )
    if not created and (reopen or state.status == "succeeded" or state.prompt_version != "model-release-extraction-v2"
                        or (content_identity is not None and state.content_identity != content_identity)):
        from core.models import EventDossierClaim, PostBrandClassificationJudgment

        revisions = PostBrandClassificationJudgment.objects.filter(
            post_id=post_id, prompt_version="model-release-extraction-v2", provider_role="targeted-release",
        ).values_list("revision_id", flat=True)
        dossier_ids = EventDossierClaim.objects.filter(
            event_dossier_source__post_id=post_id,
            extraction_version__in=[f"pulse-classified-findings-v1:{revision}" for revision in revisions],
        ).values_list("event_dossier_source__event_dossier_id", flat=True)
        with transaction.atomic():
            for proposal in ProductVerificationProposal.objects.select_for_update().filter(
                source_post_id=post_id, source_dossier_id__in=dossier_ids, review_status="pending",
            ):
                trace = list(proposal.rule_trace or [])
                for item in ("automatic_verification_stopped", "automatic_verification_stopped:release_reassessment_pending"):
                    if item not in trace:
                        trace.append(item)
                proposal.rule_trace = trace
                proposal.verification_claim_token = proposal.verification_claim_expires_at = None
                proposal.save(update_fields=["rule_trace", "verification_claim_token", "verification_claim_expires_at", "updated_at"])
        state.status = "pending"
        state.prompt_version = "model-release-extraction-v2"
        state.attempts = 0
        if content_identity is not None:
            state.content_identity = content_identity
        state.save(update_fields=["status", "prompt_version", "attempts", "content_identity", "updated_at"])
        from core.models import ProductReleaseDetectionState

        ProductReleaseDetectionState.objects.filter(
            post_id=post_id, error_code="release_extraction_exhausted",
        ).update(attempts=0, retry_at=None, error_code="")
    return state


def _effective_prompt_version(role, configured_version, *, pulse_release=False):
    if role == "model_release_extraction" and not pulse_release:
        return "model-release-extraction-v1"
    return configured_version


def _prompts(role: str, post: Post, *, version: str | None = None,
             pulse_release: bool = False, release_context: list | None = None) -> tuple[str, str]:
    source_kind = (
        "ambiguous profile observation"
        if role == "profile_affiliation_extraction"
        else "already-positive post"
    )
    system = (
        f"Extract {role} records from one {source_kind}. Return exactly one JSON "
        'object with {"records":[...]} and no markdown or extra keys. Use only '
        "facts in the supplied source, preserve unknown values as null, never "
        "invent dates, people, organizations, roles, URLs, or quantities, and "
        "keep one record per distinct entity. Return an empty records array when "
        "the source does not meet the boundary.\n" + _ROLE_PROMPT_SPECS[role].strip()
    )
    payload = {
        "post_id": str(post.pk),
        "text": post.text or "",
        "quoted_text": post.quoted_text or "",
        "author_handle": post.author_handle,
        "brand_ids": list(post.brands.values_list("brand_id", flat=True)),
        "source_urls": list(_source_urls(post)),
        "capabilities": {
            "text": True,
            "ocr": False,
            "vision": False,
            "redirect_resolution": False,
        },
    }
    if role == "model_release_extraction" and not pulse_release and post.in_reply_to_id:
        parent_text = Post.objects.filter(pk=post.in_reply_to_id).values_list("text", flat=True).first()
        if parent_text:
            payload["parent_text"] = parent_text
    if role == "model_release_extraction" and pulse_release:
        payload["context"] = release_context or []
        system += (
            " A suite announcement that mentions existing components is one release."
            " Include a component separately only when the source introduces it."
            " For each record supply source_excerpt as an exact quote identifying"
            " the offering and release, publisher_relation as source_author,"
            " attributed_party or null, and novelty as new_release, historical_release,"
            " availability_update or unresolved. The categories array must contain exactly one primary category."
            " For source-supported access, return claim_kind as availability and access_channel as"
            " api, weights, hosted_app, software_download, source_code, data_download or physical_product;"
            " otherwise use release_report and null. The exact quote must support the claim and channel."
            " For multiple access milestones on one offering, include milestones as a list of"
            " claim_kind, source_excerpt, access_channel, release_precision and release_value;"
            " quote and date each milestone separately. Use an empty list if none."
            " Supply family_name and family_excerpt only when the source explicitly"
            " names the family and the quote contains both family and model."
            " Supply lineage_evidence as a list of relationship_kind (new_version,"
            " finetune, adapter, quantized, merge), parent_observed_name and an exact"
            " source_excerpt containing both names. Use an empty list if absent."
        )
    if role == "model_release_extraction" and pulse_release and post.author_id:
        from core.models import BrandAccount
        from core.official_company_accounts import build_evidence

        evidence = build_evidence(post.author, [{
            "id": str(post.pk),
            "text": post.text,
            "author_description": post.author_description,
            "profile_bio": post.author_profile_bio,
            "observed_at": post.fetched_at.isoformat() if post.fetched_at else None,
        }])
        evidence["sources"] = [
            {**{key: value for key, value in source.items() if key != "observed_at"}, "text": source["text"][:2048]}
            for source in evidence["sources"]
            if source["id"] != f"post:{post.pk}"
        ][:12]
        payload["author_profile_evidence"] = evidence
        payload["author_affiliations"] = [
            {"brand_id": brand_id, "role": role_id, "reviewed": True}
            for brand_id, role_id in BrandAccount.objects.filter(
                account_id=post.author_id, account__data_source_id="x",
            ).order_by("brand_id", "role_id").values_list("brand_id", "role_id")
        ]
    if role in {"personnel_change_extraction", "profile_affiliation_extraction"}:
        payload["source_published_at"] = post.created_at.isoformat() if post.created_at else None
        payload["source_observed_at"] = post.fetched_at.isoformat() if post.fetched_at else None
        if role == "personnel_change_extraction":
            system += (
                " Interpret relative employment dates using the source publication time, "
                "not the later collection time; if the necessary time is missing, "
                "leave the effective date unknown."
            )
        else:
            system += (
                " A profile observation time is not its publication or effective time. "
                "Do not use the post publication time to date a profile. Leave relative "
                "employment dates unknown unless the profile supplies an actual anchor."
            )
    if role == "profile_affiliation_extraction":
        snapshots = post.profile_snapshots.order_by("account_id", "id").values(
            "id",
            "handle",
            "display_name",
            "description",
            "profile_bio_text",
            "first_observed_at",
            "last_observed_at",
            "affiliate_target_username",
            "affiliate_label_description",
            "affiliate_label_type__code",
            "affiliate_display_type__code",
        )
        payload["profile_observations"] = [
            {key.removesuffix("__code"): value.isoformat() if key in {"first_observed_at", "last_observed_at"} and value else value for key, value in row.items()}
            for row in snapshots
        ]
        payload["profile_movements"] = [
            {
                "id": movement.pk,
                "prior_description": movement.prior_description,
                "new_description": movement.new_description,
                "observed_at": movement.observed_at.isoformat(),
            }
            for movement in post.profile_movement_candidates.order_by("id")
        ]
    if version in _PERSONNEL_FIELD_EVIDENCE_VERSIONS and role in {
        "personnel_change_extraction",
        "profile_affiliation_extraction",
    }:
        sources = _personnel_source_packet(post)
        if role == "profile_affiliation_extraction":
            sources = {}
            for snapshot in post.profile_snapshots.filter(
                account_id=post.author_id
            ).order_by("id"):
                sources.update(_personnel_source_packet(post, snapshot))
        payload["field_evidence_sources"] = sources
        system += (
            " For every populated personnel field, return field_evidence with schema "
            '"personnel-field-evidence/v1" and fields mapping each field name to a '
            'nonempty list of {"source_key":...,"span":...,"basis":...}. '
            "The span must be copied exactly from the matching supplied source, and "
            "basis is explicit or inferred. Use only the same selected source for "
            "one record. Cite person_name, organization_name and affiliation_type. "
            "Unknown values stay null; do not cite fields that are not populated. "
            "Do not infer dates from profile capture time or quoted-post time."
        )
    user = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
    )
    return system, user


def targeted_request_input(role, post, role_config, *, pulse_release=False, release_context=None):
    version = _effective_prompt_version(role, role_config.prompt_version, pulse_release=pulse_release)
    system, user = _prompts(role, post, version=version,
                            pulse_release=role == "model_release_extraction" and pulse_release,
                            release_context=release_context)
    identity = _hash({"post": str(post.pk), "role": role, "system": system, "user": user,
                      "model": role_config.model, "prompt_version": version})
    return system, user, version, identity


def _increment_discovery_counts(
    *,
    post: Post,
    role: str,
    records_written: int,
    evidence_written: int,
    candidates_written: int,
) -> None:
    if not post.source_query_id:
        return
    if role == "job_listing_extraction":
        model = JobDiscoveryRun
        updates = {
            "extracted_listing_count": F("extracted_listing_count") + records_written,
            "discovered_organization_count": F("discovered_organization_count")
            + candidates_written,
        }
    elif role in {
        "personnel_change_extraction",
        "profile_affiliation_extraction",
    }:
        model = PersonnelDiscoveryRun
        updates = {
            "extracted_affiliation_count": F("extracted_affiliation_count")
            + records_written,
            "extracted_evidence_count": F("extracted_evidence_count")
            + evidence_written,
            "discovered_organization_count": F("discovered_organization_count")
            + candidates_written,
        }
    else:
        return
    run_id = (
        model.objects.filter(query__query_id=post.source_query_id)
        .order_by("-window_end", "-id")
        .values_list("id", flat=True)
        .first()
    )
    if run_id is not None:
        model.objects.filter(pk=run_id).update(**updates)


def run_targeted_extractions(
    *,
    post: Post,
    post_types: set[str],
    config: TargetedExtractionConfig,
    calls: Mapping[str, TargetedCall],
    max_calls: int,
    deadline: Any | None = None,
    release_persist: Callable | None = None,
    release_context: list | None = None,
    release_source_text: str | None = None,
    release_source_retweet: bool | None = None,
    release_reusable: bool | None = None,
) -> TargetedExtractionResult:
    if not config.enabled or max_calls < 1:
        return TargetedExtractionResult()
    roles = [
        TYPE_TO_ROLE[key]
        for key in TYPE_TO_ROLE
        if key in post_types
    ]
    if "model_release_extraction" in roles:
        from core.classified_product_releases import classifier_owns_release_extraction, selected_release_revision

        if ((release_reusable if release_reusable is not None else selected_release_revision(post.pk) is not None) if release_persist
                else classifier_owns_release_extraction(post.pk)):
            roles.remove("model_release_extraction")
    has_ambiguous_profile = AffiliationClaimEvidence.objects.filter(
        pk__in=PersonBrandAffiliationEvidence.objects.filter(
            source_profile_snapshot__first_source_post=post,
        ).values("pk"),
        extracted_claim_data__candidate_role="unknown",
    ).exists()
    has_profile_movement = ProfileMovementCandidate.objects.filter(
        source_post=post, status__in=["pending", "failed"]
    ).exists()
    if has_ambiguous_profile or has_profile_movement:
        roles.append("profile_affiliation_extraction")
    calls_made = records_written = evidence_written = candidates_written = 0
    failed: list[str] = []
    deferred: list[str] = []
    for role_index, role in enumerate(roles):
        if calls_made >= max_calls:
            deferred.extend(roles[role_index:])
            break
        if deadline is not None and not deadline.can_start(
            config.request_timeout_seconds + 8
        ):
            deferred.extend(roles[role_index:])
            break
        call = calls.get(role)
        if call is None:
            failed.append(role)
            continue
        role_config = config.roles[role]
        state = None
        dispatched_state_updated_at = None
        if role == "model_release_extraction" and release_persist:
            state, _ = TargetedExtractionState.objects.get_or_create(
                post=post, role=role,
                defaults={"content_identity": "0" * 64, "model": role_config.model,
                          "prompt_version": "model-release-extraction-v2", "status": "pending"},
            )
            dispatched_state_updated_at = state.updated_at
            current_post = Post.objects.get(pk=post.pk)
            context = {row.get("provenance"): row.get("text") for row in (release_context or []) if isinstance(row, dict)}
            current_parent = Post.objects.filter(pk=current_post.in_reply_to_id).values_list("text", flat=True).first()
            if release_source_text is not None and (
                release_source_text != (current_post.text or "")
                or release_source_retweet != current_post.is_retweet
                or context.get("stored_quote", "") != (current_post.quoted_text or "")
                or context.get("local_parent", "") != (current_parent or "")
            ):
                failed.append(role)
                continue
            if (current_post.text, current_post.quoted_text, _source_urls(current_post)) != (
                post.text, post.quoted_text, _source_urls(post),
            ):
                failed.append(role)
                continue
        try:
            system, user, prompt_version, content_identity = targeted_request_input(
                role, post, role_config, pulse_release=release_persist is not None,
                release_context=release_context,
            )
        except (TypeError, ValueError) as exc:
            if role != "model_release_extraction" or release_persist is None:
                raise
            state.status = "failed"
            state.attempts += 1
            state.last_error_code = type(exc).__name__[:128]
            TargetedExtractionState.objects.filter(pk=state.pk, updated_at=dispatched_state_updated_at).update(
                status=state.status, attempts=state.attempts, last_error_code=state.last_error_code,
                updated_at=timezone.now(),
            )
            failed.append(role)
            continue
        if state is None:
            state, _ = TargetedExtractionState.objects.get_or_create(
                post=post, role=role,
                defaults={"content_identity": content_identity, "model": role_config.model,
                          "prompt_version": prompt_version},
            )
        if state.status == "succeeded" and state.content_identity == content_identity:
            continue
        if state.content_identity != content_identity:
            state.attempts = 0
        if dispatched_state_updated_at is None:
            dispatched_state_updated_at = state.updated_at
        attempted_at = timezone.now()
        started = time.monotonic()
        usage = {"input_tokens": 0, "output_tokens": 0}
        outcome = "failed"
        error_code = ""
        result_hash = None
        try:
            response = call(system, user, role_config.model, role_config.max_tokens)
            records, usage = _parse_response(response)
            with transaction.atomic():
                if role == "model_release_extraction" and release_persist:
                    from core.models import PostEnrichmentState

                    PostEnrichmentState.objects.select_for_update().filter(post=post).first()
                    current = TargetedExtractionState.objects.select_for_update().get(pk=state.pk)
                    if current.updated_at != dispatched_state_updated_at:
                        raise ValueError("targeted_release_input_changed_during_request")
                persist = release_persist if role == "model_release_extraction" and release_persist else _PERSISTERS[role]
                written, evidence, candidates = persist(post, records, prompt_version)
            records_written += written
            evidence_written += evidence
            candidates_written += candidates
            if written or evidence or candidates:
                _increment_discovery_counts(
                    post=post,
                    role=role,
                    records_written=written,
                    evidence_written=evidence,
                    candidates_written=candidates,
                )
            result_hash = _hash(records)
            outcome = "succeeded"
        except LLMCallBudgetExhausted:
            deferred.extend(roles[role_index:])
            break
        except Exception as exc:  # noqa: BLE001 - one failed role must not stop the cycle
            error_code = type(exc).__name__[:128]
            failed.append(role)
        calls_made += 1
        def record_superseded_attempt():
            TargetedExtractionAttempt.objects.create(
                state_id=state.pk,
                attempt_identity=_hash({"state": state.pk, "at": attempted_at.isoformat(), "result": "superseded"}),
                attempted_at=attempted_at, outcome="failed", model=role_config.model,
                prompt_version=prompt_version, input_tokens=usage["input_tokens"], output_tokens=usage["output_tokens"],
                latency_ms=max(round((time.monotonic() - started) * 1000), 0), error_code="input_superseded",
            )
        if (role == "model_release_extraction" and release_persist
                and TargetedExtractionState.objects.filter(pk=state.pk).exclude(
                    updated_at=dispatched_state_updated_at,
                ).exists() and outcome != "succeeded"):
            # A newer harvest request owns this state. Never overwrite it with
            # the result of an older provider call.
            record_superseded_attempt()
            continue
        latency_ms = max(round((time.monotonic() - started) * 1000), 0)
        state.content_identity = content_identity
        state.model = role_config.model
        state.prompt_version = prompt_version
        state.attempts += 1
        state.status = outcome
        state.result_hash = result_hash
        state.last_error_code = error_code
        state.last_attempted_at = attempted_at
        state.completed_at = attempted_at if outcome == "succeeded" else None
        if role == "model_release_extraction" and release_persist:
            changed = TargetedExtractionState.objects.filter(
                pk=state.pk, updated_at=dispatched_state_updated_at,
            ).update(content_identity=state.content_identity, model=state.model,
                     prompt_version=state.prompt_version, attempts=state.attempts,
                     status=state.status, result_hash=state.result_hash,
                     last_error_code=state.last_error_code, last_attempted_at=state.last_attempted_at,
                     completed_at=state.completed_at, updated_at=timezone.now())
            if not changed:
                record_superseded_attempt()
                continue
        else:
            state.save()
        if role == "profile_affiliation_extraction":
            ProfileMovementCandidate.objects.filter(source_post=post).update(
                status=outcome,
                attempts=F("attempts") + 1,
                last_error_code=error_code,
            )
        TargetedExtractionAttempt.objects.create(
            state=state,
            attempt_identity=_hash(
                {
                    "state": state.pk,
                    "attempt": state.attempts,
                    "at": attempted_at.isoformat(),
                }
            ),
            attempted_at=attempted_at,
            outcome=outcome,
            model=role_config.model,
            prompt_version=prompt_version,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            latency_ms=latency_ms,
            error_code=error_code,
        )
    if (
        roles
        and not failed
        and not deferred
        and TargetedExtractionState.objects.filter(
            post=post, role__in=roles, status="succeeded"
        ).count() == len(set(roles))
    ):
        RareTypeSearchHit.objects.filter(
            post=post,
            gate_state=RareTypeSearchHit.GateState.KEPT,
            extracted_at__isnull=True,
        ).update(extracted_at=timezone.now())

    return TargetedExtractionResult(
        calls_made=calls_made,
        records_written=records_written,
        evidence_written=evidence_written,
        organization_candidates_written=candidates_written,
        failed_roles=tuple(failed),
        deferred_roles=tuple(deferred),
    )
