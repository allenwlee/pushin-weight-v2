"""Classification-gated structured extraction for rare post signals."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import unicodedata
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

from django.db import transaction
from django.db.models import Case, F, IntegerField, Value, When
from django.utils import timezone

from core.models import (
    Brand,
    BrandAccount,
    BrandDiscoveryCandidate,
    Event,
    JobDiscoveryRun,
    JobListing,
    JobListingEvidence,
    Opportunity,
    Person,
    PersonAccount,
    PersonBrandAffiliation,
    PersonBrandAffiliationEvidence,
    PersonnelDiscoveryRun,
    Post,
    SearchQuery,
    TargetedExtractionAttempt,
    TargetedExtractionState,
)
from core.profile_snapshots import person_id_for_account, person_id_for_handle
from x_monitor.config import TargetedExtractionConfig
from x_monitor.provider_telemetry import emit_attempt, provider_host_class

logger = logging.getLogger(__name__)

TYPE_TO_ROLE = {
    "events": "event_extraction",
    "opportunities": "opportunity_extraction",
    "job_listings": "job_listing_extraction",
    "personnel_changes": "personnel_change_extraction",
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
ALLOWED_OPPORTUNITY_STATUSES = {value for value, _label in Opportunity.SOURCE_STATUSES}

TargetedCall = Callable[[str, str, str, int], Mapping[str, Any] | str]

_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+")
_MAX_RECORDS_PER_RESPONSE = 100

_ROLE_PROMPT_SPECS = {
    "event_extraction": """
Return one record per attendance-bearing event. An event requires attendance at
a scheduled in-person, live-online, or hybrid venue/session; an asynchronous
submission or application alone is not an event. Past, live, future, cancelled,
and postponed events may qualify. Fields: brand_id, organization_name,
organization_handle, title, source_url, attendance_mode (in_person,
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
extraction_method, and confidence.
""",
    "personnel_change_extraction": """
Return one record per named person's joining, leaving, appointment, or explicit
before-and-after employment transition involving an AI organization. Static
biographies, employee spotlights, and unchanged roles do not qualify. Fields:
person_name, person_handle, brand_id, organization_name, organization_handle,
affiliation_type (employment, founder, advisor, board_member, contractor,
ambassador, creator_partner, affiliate, investor, community, or other),
title_raw, title_normalized, department, team, job_function, seniority,
employment_type, status (current, former, future, or unknown), start_date,
start_date_precision (day, month, year, or unknown), end_date,
end_date_precision, and confidence. Keep an unstated effective date null with
unknown precision.
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
job_function, seniority, employment_type, status (current, former, future, or
unknown), start_date, start_date_precision (day, month, year, or unknown),
end_date, end_date_precision, and confidence. Keep unstated effective dates
null with unknown precision.
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
            content = response.get("content") or []
            text_parts = [
                str(block.get("text") or "")
                for block in content
                if isinstance(block, Mapping) and block.get("type") == "text"
            ]
            payload = json.loads("\n".join(text_parts).strip())
            if not isinstance(payload, dict):
                raise TypeError("targeted provider response must be a JSON object")
            usage = response.get("usage")
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
                parsed = _url(candidate.rstrip(".,);]"))
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
        brand.display_name_ja,
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
    handles = BrandAccount.objects.filter(brand=brand).exclude(
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


def _brand_or_candidate(
    post: Post,
    record: Mapping[str, Any],
    brand_context: _BrandEvidenceContext,
):
    brand = _known_brand(brand_context, record.get("brand_id"))
    if brand is not None:
        return brand, None, 0
    organization = _text(record.get("organization_name"), required=True) or ""
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
        BrandAccount.objects.filter(account_id=post.author_id, brand=brand)
        .values_list("role_id", flat=True)
        .first()
    )
    return role if role in {"official", "staff"} else "third_party"


def _persist_jobs(post: Post, records: list[Mapping[str, Any]], version: str):
    written = evidence = candidates = 0
    source_urls = _source_urls(post)
    brand_context = _brand_evidence_context(post)
    for record in records:
        organization = _text(record.get("organization_name"), required=True) or ""
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
            "job_function": _text(record.get("job_function")),
            "seniority": _text(record.get("seniority")),
            "employment_type": _text(record.get("employment_type")),
            "workplace_type": _text(record.get("workplace_type")),
            "locations_raw": _text(record.get("locations_raw")),
            "locations": locations,
            "remote_applicant_restrictions": _text(
                record.get("remote_applicant_restrictions")
            ),
            "salary_text": _text(record.get("salary_text")),
            "salary_min": _number(record.get("salary_min")),
            "salary_max": _number(record.get("salary_max")),
            "salary_currency": _text(record.get("salary_currency"), maximum=3),
            "salary_period": _text(record.get("salary_period"), maximum=32),
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
            "organization_ai_relationship": _text(
                record.get("organization_ai_relationship")
            ),
            "role_ai_relationship": _text(record.get("role_ai_relationship")),
            "content_hash": _hash(record),
            "extraction_version": version,
            "extraction_confidence": _confidence(record.get("confidence")),
            "raw_payload": dict(record),
        }
        listing, created = JobListing.objects.get_or_create(
            listing_identity=listing_identity,
            defaults=listing_values,
        )
        written += int(created)
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
                    "raw_payload",
                }:
                    continue
                if _missing_job_value(getattr(listing, field)) and not _missing_job_value(
                    value
                ):
                    setattr(listing, field, value)
                    updates.append(field)
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
        extraction_method = _choice(
            record.get("extraction_method"),
            allowed={"structured_text"},
            default="structured_text",
            field="extraction method",
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
                "extraction_method": extraction_method,
                "image_derived_fields": image_derived_fields,
                "confidence": _confidence(record.get("confidence")),
                "raw_evidence": {
                    "record": dict(record),
                    "capabilities": {
                        "ocr": False,
                        "vision": False,
                        "redirect_resolution": False,
                    },
                },
                "extraction_identity": version,
            },
        )
        evidence += int(evidence_created)
    return written, evidence, candidates


def _persist_personnel(post: Post, records: list[Mapping[str, Any]], version: str):
    written = evidence = candidates = 0
    brand_context = _brand_evidence_context(post)
    for record in records:
        person_name = _text(record.get("person_name"), required=True) or ""
        brand, candidate, candidate_created = _brand_or_candidate(
            post, record, brand_context
        )
        candidates += candidate_created
        person_handle = _text(record.get("person_handle"), maximum=64)
        normalized_handle = (person_handle or "").removeprefix("@").casefold()
        self_authored = bool(
            post.author_id
            and normalized_handle
            and post.author_handle
            and normalized_handle
            == post.author_handle.removeprefix("@").casefold()
        )
        linked_person = (
            PersonAccount.objects.filter(account_id=post.author_id)
            .exclude(resolution_status="rejected")
            .select_related("person")
            .order_by(
                Case(
                    When(resolution_status="confirmed", then=Value(0)),
                    When(is_primary=True, then=Value(1)),
                    default=Value(2),
                    output_field=IntegerField(),
                ),
                "person_id",
            )
            .first()
            if self_authored
            else None
        )
        if linked_person is None and normalized_handle:
            handle_links = list(
                PersonAccount.objects.filter(account__handle=normalized_handle)
                .exclude(resolution_status="rejected")
                .select_related("person")
                .order_by(
                    Case(
                        When(resolution_status="confirmed", then=Value(0)),
                        When(is_primary=True, then=Value(1)),
                        default=Value(2),
                        output_field=IntegerField(),
                    ),
                    "person_id",
                )[:2]
            )
            confirmed_links = [
                link
                for link in handle_links
                if link.resolution_status == "confirmed"
            ]
            if confirmed_links:
                linked_person = confirmed_links[0]
            elif len(handle_links) == 1:
                linked_person = handle_links[0]
        if linked_person is not None:
            person = linked_person.person
        else:
            person_identity = (
                f"x-handle:{normalized_handle}"
                if normalized_handle
                else "source-post:"
                + str(post.pk)
                + ":name:"
                + unicodedata.normalize("NFKC", person_name).casefold()
            )
            if normalized_handle:
                handle_person_id = person_id_for_handle(normalized_handle)
                person_id = handle_person_id
                if self_authored and not Person.objects.filter(
                    pk=handle_person_id
                ).exists():
                    person_id = person_id_for_account(post.author_id)
            elif self_authored:
                person_id = person_id_for_account(post.author_id)
            else:
                person_id = uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"pushinweight:person:{person_identity}",
                )
            person, _ = Person.objects.get_or_create(
                id=person_id, defaults={"display_name": person_name}
            )
        if self_authored:
            link, _ = PersonAccount.objects.get_or_create(
                person=person,
                account_id=post.author_id,
                defaults={
                    "first_observed_at": post.fetched_at,
                    "last_observed_at": post.fetched_at,
                    "confidence": _confidence(record.get("confidence")),
                    "resolution_status": "pending",
                },
            )
            if post.fetched_at > link.last_observed_at:
                link.last_observed_at = post.fetched_at
                link.save(update_fields=["last_observed_at"])
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
        claim_identity = _hash(
            {
                "person": str(person.pk),
                "organization": organization_identity,
                "type": affiliation_type,
                "status": status,
                "title": _text(record.get("title_raw")),
                "start": start_value,
                "end": end_value,
            }
        )
        affiliation, created = PersonBrandAffiliation.objects.get_or_create(
            claim_identity=claim_identity,
            defaults={
                "person": person,
                "brand": brand,
                "brand_discovery_candidate": candidate,
                "affiliation_type": affiliation_type,
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
        written += int(created)
        evidence_hash = _hash(
            {"claim": claim_identity, "post": str(post.pk), "version": version}
        )
        _row, evidence_created = PersonBrandAffiliationEvidence.objects.get_or_create(
            affiliation=affiliation,
            evidence_hash=evidence_hash,
            defaults={
                "source_post": post,
                "evidence_text": (post.text or "")[:5000],
                "observed_at": post.fetched_at,
                "extracted_claim_data": dict(record),
                "extraction_method": "structured_text",
                "extraction_model": None,
                "extraction_prompt_version": version,
                "confidence": _confidence(record.get("confidence")),
                "review_status": "pending",
            },
        )
        evidence += int(evidence_created)
    return written, evidence, candidates


def _persist_events(post: Post, records: list[Mapping[str, Any]], version: str):
    written = candidates = 0
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
        if brand is None:
            _candidate, created = _organization_candidate(
                post=post,
                name=_text(record.get("organization_name"), required=True) or "",
                handle=_text(record.get("organization_handle"), maximum=64),
                confidence=_confidence(record.get("confidence")),
            )
            candidates += int(created)
            continue
        identity = _hash({"post": str(post.pk), "record": record, "version": version})
        _row, created = Event.objects.get_or_create(
            event_identity=identity,
            defaults={
                "brand": brand,
                "source_post": post,
                "source_url": _source_bound_url(
                    record.get("source_url"),
                    source_urls=source_urls,
                    field="source",
                ),
                "title": _text(record.get("title"), required=True),
                "organizer_name": _text(record.get("organization_name"), required=True),
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
                "source_timezone": _text(record.get("source_timezone"), maximum=64),
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
        written += int(created)
    return written, 0, candidates


def _persist_opportunities(post: Post, records: list[Mapping[str, Any]], version: str):
    written = candidates = 0
    source_urls = _source_urls(post)
    brand_context = _brand_evidence_context(post)
    events_by_brand: dict[str, list[Event]] = {}
    for event in Event.objects.filter(source_post=post).order_by("id"):
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
        if brand is None:
            _candidate, created = _organization_candidate(
                post=post,
                name=_text(record.get("organization_name"), required=True) or "",
                handle=_text(record.get("organization_handle"), maximum=64),
                confidence=_confidence(record.get("confidence")),
            )
            candidates += int(created)
            continue
        related_event = None
        related_event_title = _text(record.get("related_event_title"))
        possible_events = events_by_brand.get(str(brand.pk), [])
        if related_event_title:
            related_event = next(
                (
                    event
                    for event in possible_events
                    if event.title.casefold() == related_event_title.casefold()
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
                "related_event": related_event,
                "source_post": post,
                "source_url": _source_bound_url(
                    record.get("source_url"),
                    source_urls=source_urls,
                    field="source",
                ),
                "sponsor_name": _text(record.get("organization_name"), required=True),
                "sponsor_handle": _text(record.get("organization_handle"), maximum=64),
                "opportunity_type": opportunity_type,
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
                "source_timezone": _text(record.get("source_timezone"), maximum=64),
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


_PERSISTERS = {
    "event_extraction": _persist_events,
    "opportunity_extraction": _persist_opportunities,
    "job_listing_extraction": _persist_jobs,
    "personnel_change_extraction": _persist_personnel,
    "profile_affiliation_extraction": _persist_personnel,
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


def _prompts(role: str, post: Post) -> tuple[str, str]:
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
    if role == "profile_affiliation_extraction":
        snapshots = post.profile_snapshots.order_by("account_id", "id").values(
            "id",
            "handle",
            "display_name",
            "description",
            "profile_bio_text",
            "affiliate_target_username",
            "affiliate_label_description",
            "affiliate_label_type",
            "affiliate_display_type",
        )
        payload["profile_observations"] = list(snapshots)
    user = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
    )
    return system, user


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
) -> TargetedExtractionResult:
    if not config.enabled or max_calls < 1:
        return TargetedExtractionResult()
    roles = [TYPE_TO_ROLE[key] for key in TYPE_TO_ROLE if key in post_types]
    has_ambiguous_profile = PersonBrandAffiliationEvidence.objects.filter(
        source_profile_snapshot__first_source_post=post,
        extracted_claim_data__candidate_role="unknown",
    ).exists()
    if has_ambiguous_profile:
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
        system, user = _prompts(role, post)
        content_identity = _hash(
            {
                "post": str(post.pk),
                "role": role,
                "system": system,
                "user": user,
                "model": role_config.model,
                "prompt_version": role_config.prompt_version,
            }
        )
        state, _ = TargetedExtractionState.objects.get_or_create(
            post=post,
            role=role,
            defaults={
                "content_identity": content_identity,
                "model": role_config.model,
                "prompt_version": role_config.prompt_version,
            },
        )
        if state.status == "succeeded" and state.content_identity == content_identity:
            continue
        attempted_at = timezone.now()
        started = time.monotonic()
        usage = {"input_tokens": 0, "output_tokens": 0}
        outcome = "failed"
        error_code = ""
        result_hash = None
        try:
            calls_made += 1
            response = call(system, user, role_config.model, role_config.max_tokens)
            records, usage = _parse_response(response)
            with transaction.atomic():
                written, evidence, candidates = _PERSISTERS[role](
                    post, records, role_config.prompt_version
                )
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
        except Exception as exc:  # noqa: BLE001 - one failed role must not stop the cycle
            error_code = type(exc).__name__[:128]
            failed.append(role)
        latency_ms = max(round((time.monotonic() - started) * 1000), 0)
        state.content_identity = content_identity
        state.model = role_config.model
        state.prompt_version = role_config.prompt_version
        state.attempts += 1
        state.status = outcome
        state.result_hash = result_hash
        state.last_error_code = error_code
        state.last_attempted_at = attempted_at
        state.completed_at = attempted_at if outcome == "succeeded" else None
        state.save()
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
            prompt_version=role_config.prompt_version,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            latency_ms=latency_ms,
            error_code=error_code,
        )
    return TargetedExtractionResult(
        calls_made=calls_made,
        records_written=records_written,
        evidence_written=evidence_written,
        organization_candidates_written=candidates_written,
        failed_roles=tuple(failed),
        deferred_roles=tuple(deferred),
    )
