"""Durable writers for the current U18A classification projection.

The classifier is deliberately responsible only for a fully validated result.
This module adds its post-brand and post-level v4 projections inside the
publisher's existing transaction; it never calls a model or mutates legacy
unsanctioned-flag records.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from django.utils import timezone

from core.models import (
    Account,
    AudienceTopicConcept,
    AudienceTopicScheme,
    BrandDiscoveryCandidate,
    Post,
    PostBrandAudienceTopic,
    PostBrandGeopoliticalMode,
    PostUntrackedBrandPromotion,
    UntrackedBrandPromotionEvidence,
)
from core.classification_contract import UNTRACKED_BRAND_PROMOTION_KEYS

AUDIENCE_TOPIC_SCHEME_KEY = "ai_audience_topics/v1"
_HANDLE_RE = re.compile(r"^@?([A-Za-z0-9_]{1,64})$")
_HASHTAG_RE = re.compile(r"(?<!\w)#([\w-]+)", re.UNICODE)


def _stable_strings(values: Iterable[Any]) -> list[str]:
    """Return nonblank, case-insensitively unique visible values."""
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        cleaned = value.strip()
        if not cleaned or cleaned.casefold() in seen:
            continue
        seen.add(cleaned.casefold())
        output.append(cleaned)
    return sorted(output, key=str.casefold)


def _normalized_handle(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = _HANDLE_RE.fullmatch(value.strip())
    return match.group(1).casefold() if match else None


def _normalized_domain(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip().casefold()
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    domain = (parsed.hostname or "").removeprefix("www.")
    return domain or None


def _normalized_visible_name(value: Any) -> str | None:
    """Normalize an exact catalog alias without treating a substring as a match."""
    if not isinstance(value, str):
        return None
    normalized = " ".join(unicodedata.normalize("NFKC", value).split()).casefold()
    return normalized or None


def _identity(*, name: str, handles: list[str], domains: list[str]) -> str:
    """Return a deterministic subject identity from only normalized evidence."""
    payload = {
        "name": name.strip().casefold(),
        "handles": sorted({_normalized_handle(item) for item in handles if _normalized_handle(item)}),
        "domains": sorted({_normalized_domain(item) for item in domains if _normalized_domain(item)}),
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _targeted_extraction_identity(*, name: str, handle: str | None) -> str | None:
    """Return the existing targeted-extraction identity when a handle exists."""
    normalized = _normalized_handle(handle)
    if normalized is None:
        return None
    payload = {
        "name": unicodedata.normalize("NFKC", name).casefold(),
        "handle": normalized,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _evidence_span(*, text: str, excerpt: str) -> dict[str, Any]:
    start = text.casefold().find(excerpt.casefold())
    span: dict[str, Any] = {"text": excerpt}
    if start >= 0:
        span.update({"start": start, "end": start + len(excerpt)})
    return span


def _stable_evidence_spans(values: Iterable[Any]) -> list[dict[str, Any]]:
    """Keep a replay from duplicating the same visible evidence span."""
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        identity = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if identity in seen:
            continue
        seen.add(identity)
        output.append(value)
    return output


def _exact_account(*, account_handle: Any, handle: Any) -> Account | None:
    """Resolve only an exact visible X handle; do not infer an account."""
    for value in (account_handle, handle):
        normalized = _normalized_handle(value)
        if normalized:
            account = Account.objects.filter(handle__iexact=normalized).first()
            if account is not None:
                return account
    return None


def _subject_is_tracked(subject: dict[str, Any], tracked_catalog: Iterable[Any]) -> bool:
    """Return true only for exact evidence already belonging to a tracked brand.

    Promotion output is about a subject outside the tracked catalog.  An exact
    known alias, product, keyword, official handle/account, or domain is
    therefore a contract violation.  This deliberately avoids fuzzy matching:
    a new company that merely contains a tracked brand's word remains a
    candidate for later human review.
    """
    subject_name = _normalized_visible_name(subject.get("name"))
    subject_handles = {
        value
        for value in (
            _normalized_handle(subject.get("handle")),
            _normalized_handle(subject.get("account_handle")),
        )
        if value
    }
    subject_domain = _normalized_domain(subject.get("domain"))
    for row in tracked_catalog:
        if not isinstance(row, dict):
            continue
        known_names = {
            value
            for field in ("brand_id", "aliases", "products", "keywords")
            for raw in (
                [row.get(field)]
                if field == "brand_id"
                else (row.get(field) or [])
            )
            for value in (_normalized_visible_name(raw),)
            if value
        }
        if subject_name and subject_name in known_names:
            return True
        known_handles = {
            value
            for raw in row.get("handles") or []
            for value in (_normalized_handle(raw),)
            if value
        }
        for account in row.get("accounts") or []:
            if isinstance(account, dict):
                value = _normalized_handle(account.get("handle"))
                if value:
                    known_handles.add(value)
        if subject_handles.intersection(known_handles):
            return True
        known_domains = {
            value
            for raw in row.get("domains") or []
            for value in (_normalized_domain(raw),)
            if value
        }
        if subject_domain and subject_domain in known_domains:
            return True
    return False


def _merge_candidate(
    *,
    identity: str,
    name: str,
    aliases: list[str],
    handles: list[str],
    domains: list[str],
    subject_handle: str | None,
    exact_account: Account | None,
    post: Post,
    observed_at: datetime,
) -> BrandDiscoveryCandidate:
    """Create or advance one stable discovery candidate without semantic guesses."""
    # Stable external identities survive renames. Resolve the strongest
    # evidence first, then fall back to name-derived identities shared with
    # targeted extraction.
    legacy_identity = _targeted_extraction_identity(
        name=name,
        handle=subject_handle,
    )
    candidate = None
    if exact_account is not None:
        candidate = (
            BrandDiscoveryCandidate.objects.filter(
                untracked_brand_promotion_evidence__exact_matched_account=exact_account,
            )
            .order_by("id")
            .first()
        )
    if candidate is None and handles:
        for stable_handle in handles:
            candidate = (
                BrandDiscoveryCandidate.objects.filter(
                    untracked_brand_promotion_evidence__handles__contains=[stable_handle]
                )
                .order_by("id")
                .first()
            )
            if candidate is not None:
                break
    if candidate is None and domains:
        for stable_domain in domains:
            candidate = (
                BrandDiscoveryCandidate.objects.filter(
                    untracked_brand_promotion_evidence__domains__contains=[stable_domain]
                )
                .order_by("id")
                .first()
            )
            if candidate is not None:
                break
    if candidate is None and legacy_identity:
        candidate = BrandDiscoveryCandidate.objects.filter(
            candidate_identity=legacy_identity
        ).first()
    if candidate is None:
        candidate = BrandDiscoveryCandidate.objects.filter(
            candidate_identity=identity
        ).first()
    created = candidate is None
    if created:
        candidate = BrandDiscoveryCandidate.objects.create(
            candidate_identity=identity,
            observed_name=name,
            aliases=aliases,
            candidate_handles=handles,
            source_post=post,
            source_identities=[f"post:{post.pk}"],
            first_observed_at=observed_at,
            last_observed_at=observed_at,
        )
    assert candidate is not None
    if created:
        return candidate

    # Reclassification can replay the same source; retain all visible aliases
    # and source identifiers while advancing only the observed window.
    source_identities = _stable_strings(
        [*(candidate.source_identities or []), f"post:{post.pk}"]
    )
    update_fields: list[str] = []
    merged_aliases = _stable_strings([*(candidate.aliases or []), *aliases])
    merged_handles = _stable_strings([*(candidate.candidate_handles or []), *handles])
    if merged_aliases != candidate.aliases:
        candidate.aliases = merged_aliases
        update_fields.append("aliases")
    if merged_handles != candidate.candidate_handles:
        candidate.candidate_handles = merged_handles
        update_fields.append("candidate_handles")
    if source_identities != candidate.source_identities:
        candidate.source_identities = source_identities
        update_fields.append("source_identities")
    if observed_at < candidate.first_observed_at:
        candidate.first_observed_at = observed_at
        update_fields.append("first_observed_at")
    if observed_at > candidate.last_observed_at:
        candidate.last_observed_at = observed_at
        update_fields.append("last_observed_at")
    if update_fields:
        candidate.save(update_fields=[*update_fields, "updated_at"])
    return candidate


def _write_promoted_subject(
    *, promotion: PostUntrackedBrandPromotion, post: Post, subject: dict[str, Any], observed_at: datetime,
) -> None:
    name = str(subject["name"]).strip()
    handle = subject.get("handle")
    account_handle = subject.get("account_handle")
    domain = subject.get("domain")
    excerpt = str(subject["evidence"]).strip()
    handles = _stable_strings([f"@{item}" for item in (
        _normalized_handle(handle), _normalized_handle(account_handle)
    ) if item])
    domains = _stable_strings([item for item in (_normalized_domain(domain),) if item])
    aliases = _stable_strings([name])
    subject_identity = _identity(name=name, handles=handles, domains=domains)
    exact_account = _exact_account(account_handle=account_handle, handle=handle)
    candidate = _merge_candidate(
        identity=subject_identity,
        name=name,
        aliases=aliases,
        handles=handles,
        domains=domains,
        subject_handle=_normalized_handle(handle),
        exact_account=exact_account,
        post=post,
        observed_at=observed_at,
    )
    evidence, created = UntrackedBrandPromotionEvidence.objects.get_or_create(
        promotion=promotion,
        subject_identity=subject_identity,
        defaults={
            "brand_discovery_candidate": candidate,
            "source_post": post,
            "exact_matched_account": exact_account,
            "observed_name": name,
            "aliases": aliases,
            "handles": handles,
            "domains": domains,
            # The fixed-slot v4 contract has no product field.  Keep this
            # explicit empty evidence rather than deriving a product name.
            "products": [],
            "hashtags": _stable_strings(f"#{tag}" for tag in _HASHTAG_RE.findall(excerpt)),
            "evidence_spans": [_evidence_span(text=post.text or "", excerpt=excerpt)],
            "first_seen_at": observed_at,
            "last_seen_at": observed_at,
            "recurrence_count": 1,
        },
    )
    if created:
        # This count includes the just-created row and is stable on replay.
        recurrence_count = UntrackedBrandPromotionEvidence.objects.filter(
            brand_discovery_candidate=candidate
        ).count()
        UntrackedBrandPromotionEvidence.objects.filter(
            brand_discovery_candidate=candidate
        ).update(recurrence_count=recurrence_count)
        return

    # A retry of the same full result is idempotent.  Update bounded visible
    # evidence without turning the retry itself into a repeated promotion.
    updates: dict[str, Any] = {
        "brand_discovery_candidate": candidate,
        "exact_matched_account": exact_account,
        "observed_name": name,
        "aliases": _stable_strings([*(evidence.aliases or []), *aliases]),
        "handles": _stable_strings([*(evidence.handles or []), *handles]),
        "domains": _stable_strings([*(evidence.domains or []), *domains]),
        "hashtags": _stable_strings([*(evidence.hashtags or []), *(f"#{tag}" for tag in _HASHTAG_RE.findall(excerpt))]),
        "evidence_spans": _stable_evidence_spans(
            [*list(evidence.evidence_spans or []), _evidence_span(text=post.text or "", excerpt=excerpt)]
        ),
        "first_seen_at": min(evidence.first_seen_at, observed_at),
        "last_seen_at": max(evidence.last_seen_at, observed_at),
    }
    for field, value in updates.items():
        setattr(evidence, field, value)
    evidence.save(update_fields=[*updates, "updated_at"])


def persist_v4_extensions(
    *,
    post: Post,
    canonical: dict[str, dict[str, Any]],
    result: dict[str, Any],
    final_judgment_ids: dict[str, Any],
    fingerprint: str,
    contract_version: str,
    taxonomy_version: str,
    model: str,
    content_prompt_version: str,
    content_provider_role: str,
    brand_prompt_version: str,
    brand_provider_role: str,
    tracked_catalog: Iterable[Any] = (),
) -> str:
    """Replace only the v4 extension projections for one atomically-published post.

    Returns ``persisted`` for a nonempty current promotion and ``cleared`` for
    an explicit no-promotion result, preserving the publisher's existing
    success convention without using the retired flag writer.
    """
    try:
        scheme = AudienceTopicScheme.objects.get(key=AUDIENCE_TOPIC_SCHEME_KEY)
    except AudienceTopicScheme.DoesNotExist as exc:
        # A deployment that ran code before the additive migration/seed must
        # retain the last good projection rather than publish a partial v4 row.
        raise ValueError("classification_audience_topic_catalog_missing") from exc
    concepts = {
        row.key: row
        for row in AudienceTopicConcept.objects.filter(scheme=scheme)
    }
    for brand_id, classification in canonical.items():
        PostBrandAudienceTopic.objects.filter(post=post, brand_id=brand_id).delete()
        PostBrandGeopoliticalMode.objects.filter(post=post, brand_id=brand_id).delete()
        final_judgment_id = final_judgment_ids.get(brand_id)
        for topic in classification["audience_topics"]:
            concept = concepts.get(topic)
            if concept is None:
                raise ValueError("classification_audience_topic_catalog_missing")
            PostBrandAudienceTopic.objects.create(
                post=post,
                brand_id=brand_id,
                concept=concept,
                scheme=scheme,
                scheme_revision=scheme.revision,
                evidence={"axis": "audience_topics", "value": topic, "input_context_fingerprint": fingerprint},
                prompt_version=content_prompt_version,
                model=model,
                provider_role=content_provider_role,
                final_judgment_id=final_judgment_id,
            )
        for mode in classification["geopolitical_modes"]:
            PostBrandGeopoliticalMode.objects.create(
                post=post,
                brand_id=brand_id,
                geopolitical_mode_id=mode,
                taxonomy_version=taxonomy_version,
                evidence={"axis": "geopolitical_modes", "value": mode, "input_context_fingerprint": fingerprint},
                prompt_version=brand_prompt_version,
                model=model,
                provider_role=brand_provider_role,
                final_judgment_id=final_judgment_id,
            )

    promotions = result.get("untracked_brand_promotions")
    subjects = result.get("promoted_subjects")
    if not isinstance(promotions, list) or not isinstance(subjects, list):
        raise ValueError("classification_untracked_promotion_missing")
    if (
        not promotions
        and subjects
    ) or any(
        not isinstance(key, str) or key not in UNTRACKED_BRAND_PROMOTION_KEYS
        for key in promotions
    ) or len(set(promotions)) != len(promotions) or (
        "general" in promotions and promotions != ["general"]
    ):
        raise ValueError("classification_untracked_promotion_invalid")
    if not promotions:
        PostUntrackedBrandPromotion.objects.filter(post=post).delete()
        return "cleared"
    if not subjects:
        raise ValueError("classification_untracked_promotion_subject_missing")

    primary_final_judgment = final_judgment_ids.get(sorted(canonical)[0]) if final_judgment_ids else None
    promotion, _created = PostUntrackedBrandPromotion.objects.update_or_create(
        post=post,
        defaults={
            "promotion_keys": promotions,
            "evidence": {
                "axis": "untracked_brand_promotions",
                "input_context_fingerprint": fingerprint,
                "keys": promotions,
            },
            "contract_version": contract_version,
            "taxonomy_version": taxonomy_version,
            # Promotions are a post-level output owned by the content role.
            # The optional judgment link still identifies the merged final
            # decision selected for this publication.
            "prompt_version": content_prompt_version,
            "model": model,
            "provider_role": content_provider_role,
            "final_judgment_id": primary_final_judgment,
        },
    )
    incoming: set[str] = set()
    for subject in subjects:
        if not isinstance(subject, dict):
            raise ValueError("classification_untracked_promotion_subject_invalid")
        # Model-side parser has checked this shape. This second boundary keeps
        # direct publisher callers fail-closed as well.
        expected = {"name", "handle", "domain", "account_handle", "evidence"}
        if set(subject) != expected or any(
            not isinstance(subject[key], str) or not subject[key].strip()
            for key in ("name", "evidence")
        ) or any(
            subject[key] is not None
            and (not isinstance(subject[key], str) or not subject[key].strip())
            for key in ("handle", "domain", "account_handle")
        ):
            raise ValueError("classification_untracked_promotion_subject_invalid")
        handles = [item for item in (subject.get("handle"), subject.get("account_handle")) if isinstance(item, str)]
        identity = _identity(
            name=subject["name"], handles=handles,
            domains=[subject["domain"]] if isinstance(subject.get("domain"), str) else [],
        )
        if identity in incoming:
            continue
        if _subject_is_tracked(subject, tracked_catalog):
            raise ValueError("classification_untracked_promotion_subject_is_tracked")
        incoming.add(identity)
        _write_promoted_subject(
            promotion=promotion,
            post=post,
            subject=subject,
            observed_at=post.created_at or post.fetched_at or timezone.now(),
        )
    if not incoming:
        raise ValueError("classification_untracked_promotion_subject_missing")
    promotion.subject_evidence.exclude(subject_identity__in=incoming).delete()
    return "persisted"
