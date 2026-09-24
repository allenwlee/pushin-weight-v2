"""Deterministic, bounded Product identity corroboration.

This module never downloads repository files.  It reads only public Hub JSON
metadata and requires callers to provide explicit request/deadline budgets.
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import httpx
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from core.models import (
    Account,
    Brand,
    BrandAccount,
    BrandCompany,
    BrandDiscoveryCandidate,
    Company,
    HFOrg,
    ModelRelease,
    Post,
    PostBrandProduct,
    Product,
    ProductVerificationProposal,
    RareTypeCategoryAssignment,
)
from x_monitor.hf_client import HF_API_BASE, _next_cursor

POLICY_VERSION = "product-x-hf-v2"
logger = logging.getLogger(__name__)
_REPO_ID = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}/[A-Za-z0-9][A-Za-z0-9._-]{0,159}$"
)
_PUBLIC_HEADERS = {"Accept": "application/json"}


@dataclass(frozen=True)
class LegitimacyDecision:
    qualifies: bool
    reason: str
    trace: tuple[str, ...]


@dataclass(frozen=True)
class HFMetadataResult:
    outcome: str
    payload: dict[str, Any] | None


@dataclass(frozen=True)
class CatalogImportResult:
    imported: int
    updated: int
    requests: int
    complete: bool
    stop_reason: str
    next_cursor: str | None = None


@dataclass(frozen=True)
class VerificationDrainResult:
    attempted: int
    resolved: int
    deferred: int


class ProductReviewError(ValueError):
    """A fail-closed owner review validation or stale-decision error."""


def _walk_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _walk_strings(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            yield from _walk_strings(nested)


def _repo_from_hf_url(value: str) -> str | None:
    candidate = value.strip().rstrip(".,;:!?)]}")
    if not candidate.startswith(("https://", "http://")):
        return None
    try:
        parsed = urlparse(candidate)
        hostname = parsed.hostname
        port = parsed.port
        username = parsed.username
        password = parsed.password
    except (TypeError, ValueError):
        return None
    if (
        parsed.scheme != "https"
        or hostname is None
        or hostname.casefold() != "huggingface.co"
        or username
        or password
        or port not in (None, 443)
        or parsed.netloc.casefold() not in {"huggingface.co", "huggingface.co:443"}
        or parsed.query
        or parsed.fragment
    ):
        return None
    parts = [part for part in parsed.path.split("/") if part]
    repo_id = "/".join(parts)
    return repo_id if len(parts) == 2 and _REPO_ID.fullmatch(repo_id) else None


def source_repo_evidence(post: Post, candidate_repo_id: str) -> dict[str, Any]:
    """Prove an exact HF repository from stored source text/entities only."""
    repo_id = candidate_repo_id.strip()
    matched_urls: list[str] = []
    values = [str(post.text or ""), *_walk_strings(post.entities or {})]
    for value in values:
        for url in re.findall(r"https?://[^\s<>\"']+", value):
            source_repo = _repo_from_hf_url(url)
            if source_repo and source_repo.casefold() == repo_id.casefold():
                matched_urls.append(url.rstrip(".,;:!?)]}"))
    return {
        "candidate_repo_id": repo_id,
        "exact_hf_repo_link": bool(matched_urls),
        "matched_hf_urls": sorted(set(matched_urls)),
    }


@transaction.atomic
def decide_product_proposal(
    *,
    proposal_id: int,
    action: str,
    reviewer: str,
    reason: str,
    brand_id: str = "",
    product_type: str = "",
    catalog_mode: str = "x_only",
    new_brand_id: str = "",
    company_id: str = "",
) -> ProductVerificationProposal:
    """Apply one owner decision without provider calls or harvest mutations."""
    reviewer = reviewer.strip()
    reason = reason.strip()
    if not reviewer or not reason:
        raise ProductReviewError("reviewer and reason are required")
    if action not in {"approve", "reject"}:
        raise ProductReviewError("invalid review action")
    proposal = ProductVerificationProposal.objects.select_for_update().get(
        pk=proposal_id
    )
    if proposal.review_status != "pending":
        if action == "reject" and proposal.review_status == "rejected":
            return proposal
        if action == "approve" and proposal.review_status == "approved":
            product = proposal.resolved_product
            submitted_brand = brand_id or new_brand_id
            submitted_mode = "hf" if product and product.repo_id else "x_only"
            if (
                product
                and product.brand_id == submitted_brand
                and product.type == product_type
                and submitted_mode == catalog_mode
            ):
                return proposal
        raise ProductReviewError("proposal already decided")

    # An explicit owner decision fences any in-flight automatic verifier. Its
    # finalizer rechecks both this state and the cleared token before writing.
    proposal.verification_claim_token = None
    proposal.verification_claim_expires_at = None
    proposal.reviewer = reviewer
    proposal.review_reason = reason
    proposal.reviewed_at = timezone.now()
    if action == "reject":
        proposal.review_status = "rejected"
        proposal.save()
        return proposal

    if product_type not in {value for value, _label in Product.TYPES}:
        raise ProductReviewError("invalid product type")
    new_brand_id = new_brand_id.strip()
    company_id = company_id.strip()
    if brand_id and new_brand_id:
        raise ProductReviewError("choose an existing or new Brand, not both")
    if new_brand_id:
        if proposal.proposed_candidate_id is None:
            raise ProductReviewError("only candidate proposals can create a Brand")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_]{1,62}", new_brand_id):
            raise ProductReviewError("invalid new Brand nickname")
        try:
            with transaction.atomic():
                brand = Brand.objects.create(
                    nickname=new_brand_id,
                    display_name=proposal.proposed_candidate.observed_name,
                )
        except IntegrityError as exc:
            raise ProductReviewError(
                "new Brand nickname already exists; select the existing Brand instead"
            ) from exc
        if company_id:
            try:
                company = Company.objects.get(pk=company_id)
            except Company.DoesNotExist as exc:
                raise ProductReviewError("unknown Company") from exc
            BrandCompany.objects.get_or_create(brand=brand, company=company)
        candidate = BrandDiscoveryCandidate.objects.select_for_update().get(
            pk=proposal.proposed_candidate_id
        )
        if candidate.reviewed_brand_id not in (None, brand.pk):
            raise ProductReviewError("candidate already resolved to another Brand")
        candidate.reviewed_brand = brand
        candidate.verification_status = "confirmed"
        candidate.reviewer = reviewer
        candidate.review_note = reason
        candidate.reviewed_at = timezone.now()
        candidate.save()
    else:
        try:
            brand = Brand.objects.get(pk=brand_id, is_sentinel=False)
        except Brand.DoesNotExist as exc:
            raise ProductReviewError("unknown product brand") from exc
    if catalog_mode not in {"x_only", "hf"}:
        raise ProductReviewError("invalid catalog mode")
    repo_id = None
    if catalog_mode == "hf":
        if (
            proposal.hf_outcome != ProductVerificationProposal.HFOutcome.MATCHED
            or not _REPO_ID.fullmatch(proposal.candidate_repo_id)
        ):
            raise ProductReviewError("HF approval requires matched exact metadata")
        repo_id = proposal.candidate_repo_id

    product = None
    if proposal.source_release_id:
        ModelRelease.objects.select_for_update().get(pk=proposal.source_release_id)
        prior_product_id = (
            ProductVerificationProposal.objects.filter(
                source_release_id=proposal.source_release_id,
                review_status="approved",
                proposed_brand=brand,
                resolved_product__isnull=False,
            )
            .values_list("resolved_product_id", flat=True)
            .first()
        )
        if prior_product_id is not None:
            product = Product.objects.select_for_update().get(pk=prior_product_id)
    if repo_id:
        repo_product = (
            Product.objects.select_for_update().filter(repo_id=repo_id).first()
        )
        if product is not None:
            if repo_product is not None and repo_product.pk != product.pk:
                raise ProductReviewError(
                    "repository already resolves to another Product"
                )
            if product.repo_id not in (None, repo_id):
                raise ProductReviewError(
                    "release already resolves to another repository"
                )
            product.repo_id = repo_id
            product.raw = proposal.hf_evidence
            product.save(update_fields=["repo_id", "raw", "updated_at"])
        else:
            product, _created = Product.objects.get_or_create(
                repo_id=repo_id,
                defaults={
                    "brand": brand,
                    "display_name": proposal.observed_name,
                    "type": product_type,
                    "raw": proposal.hf_evidence,
                },
            )
            product = Product.objects.select_for_update().get(pk=product.pk)
        if product.brand_id not in (None, brand.pk):
            raise ProductReviewError("repository belongs to another Brand")
    if product is None:
        product = Product.objects.create(
            repo_id=repo_id,
            brand=brand,
            display_name=proposal.observed_name,
            type=product_type,
            raw=proposal.hf_evidence if repo_id else None,
        )
    else:
        product.brand = brand
        product.type = product_type
        if not product.display_name:
            product.display_name = proposal.observed_name
        product.save(update_fields=["brand", "type", "display_name", "updated_at"])

    PostBrandProduct.objects.get_or_create(
        post=proposal.source_post,
        brand=brand,
        product=product,
        defaults={
            "observed_name": proposal.observed_name,
            "source_evidence": {
                "proposal_key": proposal.proposal_key,
                "decision": "owner_approved",
            },
            "verification_policy_version": proposal.policy_version,
        },
    )
    proposal.proposed_brand = brand
    proposal.proposed_candidate = None
    proposal.resolved_product = product
    proposal.review_status = "approved"
    proposal.rule_trace = [*proposal.rule_trace, "owner_override:catalog_identity"]
    proposal.save()
    return proposal


def evaluate_known_publisher(
    *, account: Account, brand: Brand, namespace: str
) -> LegitimacyDecision:
    """Accept only a stable tracked official account and confirmed HF owner."""
    official = BrandAccount.objects.filter(
        account_id=account.pk, brand_id=brand.pk, role_id="official"
    ).exists()
    company_ids = BrandCompany.objects.filter(brand_id=brand.pk).values_list(
        "company_id", flat=True
    )
    owned_namespace = HFOrg.objects.filter(
        namespace=namespace, company_id__in=company_ids, confirmed=True
    ).exists()
    trace = (
        f"stable_account_id:{account.pk}",
        f"tracked_official:{str(official).lower()}",
        f"confirmed_hf_owner:{str(owned_namespace).lower()}",
        f"blue_subscription:{str(bool(account.is_blue_verified)).lower()}",
    )
    if not official:
        return LegitimacyDecision(False, "account_not_tracked_official", trace)
    if not owned_namespace:
        return LegitimacyDecision(False, "hf_namespace_not_confirmed_for_owner", trace)
    return LegitimacyDecision(True, "known_official_publisher", trace)


def _normalized_identity(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _proposal_source_gate(
    proposal: ProductVerificationProposal, *, namespace: str
) -> LegitimacyDecision:
    """Evaluate immutable source evidence plus current stable Account identity."""
    evidence = proposal.account_evidence or {}
    current_handle = str(proposal.account.handle or "").removeprefix("@")
    source_handle = str(proposal.account_handle_snapshot or "").removeprefix("@")
    post_handle = str(proposal.source_post.author_handle or "").removeprefix("@")
    handles_stable = bool(current_handle and source_handle and post_handle) and (
        current_handle.casefold() == source_handle.casefold() == post_handle.casefold()
    )
    source_account_id = str(evidence.get("stable_account_id") or "")
    account_stable = source_account_id == str(proposal.account_id) and str(
        proposal.source_post.author_id or ""
    ) == str(proposal.account_id)
    explicit_repo = bool(evidence.get("exact_hf_repo_link"))
    trace = (
        f"source_stable_account_id:{str(account_stable).lower()}",
        f"source_handle_unchanged:{str(handles_stable).lower()}",
        f"source_exact_hf_repo_link:{str(explicit_repo).lower()}",
    )
    if not account_stable:
        return LegitimacyDecision(False, "source_account_id_conflict", trace)
    if not handles_stable:
        return LegitimacyDecision(False, "source_handle_changed", trace)
    if not explicit_repo:
        return LegitimacyDecision(False, "source_exact_repo_link_missing", trace)
    if proposal.candidate_repo_id.split("/", 1)[0].casefold() != namespace.casefold():
        return LegitimacyDecision(False, "source_namespace_conflict", trace)
    return LegitimacyDecision(True, "source_identity_stable", trace)


def _evaluate_new_publisher_source(
    proposal: ProductVerificationProposal, *, namespace: str
) -> LegitimacyDecision:
    source = _proposal_source_gate(proposal, namespace=namespace)
    account_type = str(proposal.account.verified_type or "")
    post_type = str(proposal.source_post.author_verified_type or "")
    is_business = (
        account_type.casefold() == "business" and post_type.casefold() == "business"
    )
    candidate = proposal.proposed_candidate
    correlated = bool(candidate) and _normalized_identity(candidate.observed_name) in {
        _normalized_identity(namespace),
        _normalized_identity(proposal.account.handle),
    }
    trace = (
        *source.trace,
        f"x_business_gold:{str(is_business).lower()}",
        f"candidate_publisher_correlation:{str(correlated).lower()}",
        f"blue_subscription:{str(bool(proposal.account.is_blue_verified)).lower()}",
    )
    if not source.qualifies:
        return LegitimacyDecision(False, source.reason, trace)
    if not is_business:
        return LegitimacyDecision(False, "x_business_gold_missing", trace)
    if not correlated:
        return LegitimacyDecision(False, "candidate_publisher_not_correlated", trace)
    return LegitimacyDecision(True, "new_publisher_source_qualified", trace)


def exact_model_metadata(
    repo_id: str,
    *,
    client: httpx.Client,
    deadline: datetime | None = None,
) -> HFMetadataResult:
    """Fetch one exact model metadata document, once, with explicit outcomes."""
    if not _REPO_ID.fullmatch(repo_id):
        return HFMetadataResult("malformed", None)
    if deadline is not None and timezone.now() >= deadline:
        return HFMetadataResult("deferred", None)
    try:
        response = client.get(
            f"{HF_API_BASE}/models/{repo_id}", headers=_PUBLIC_HEADERS, timeout=2.0
        )
    except httpx.TimeoutException:
        return HFMetadataResult("timeout", None)
    except httpx.HTTPError:
        return HFMetadataResult("error", None)
    if response.status_code == 404:
        return HFMetadataResult("missing", None)
    if response.status_code in (401, 403):
        return HFMetadataResult("private", None)
    if response.status_code == 429:
        return HFMetadataResult("throttled", None)
    if response.status_code != 200:
        return HFMetadataResult("error", None)
    try:
        payload = response.json()
    except ValueError:
        return HFMetadataResult("malformed", None)
    if not isinstance(payload, dict):
        return HFMetadataResult("malformed", None)
    returned_id = str(payload.get("id") or payload.get("modelId") or "")
    if returned_id.casefold() != repo_id.casefold():
        return HFMetadataResult("malformed", None)
    returned_author = payload.get("author")
    if (
        returned_author is not None
        and str(returned_author).casefold() != repo_id.split("/", 1)[0].casefold()
    ):
        return HFMetadataResult("malformed", payload)
    return HFMetadataResult("matched", payload)


def hf_org_socials(
    namespace: str,
    *,
    client: httpx.Client,
    deadline: datetime | None = None,
) -> HFMetadataResult:
    """Fetch the official organization social-handle document once."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}", namespace):
        return HFMetadataResult("malformed", None)
    if deadline is not None and timezone.now() >= deadline:
        return HFMetadataResult("deferred", None)
    try:
        response = client.get(
            f"{HF_API_BASE}/organizations/{namespace}/socials",
            headers=_PUBLIC_HEADERS,
            timeout=2.0,
        )
    except httpx.TimeoutException:
        return HFMetadataResult("timeout", None)
    except httpx.HTTPError:
        return HFMetadataResult("error", None)
    if response.status_code == 404:
        return HFMetadataResult("missing", None)
    if response.status_code in (401, 403):
        return HFMetadataResult("private", None)
    if response.status_code == 429:
        return HFMetadataResult("throttled", None)
    if response.status_code != 200:
        return HFMetadataResult("error", None)
    try:
        payload = response.json()
    except ValueError:
        return HFMetadataResult("malformed", None)
    if not isinstance(payload, dict):
        return HFMetadataResult("malformed", None)
    if str(payload.get("org") or "").casefold() != namespace.casefold():
        return HFMetadataResult("malformed", payload)
    handles = payload.get("socialHandles")
    if not isinstance(handles, dict):
        return HFMetadataResult("malformed", payload)
    return HFMetadataResult("matched", payload)


def _product_defaults(
    payload: dict[str, Any], *, brand: Brand, hf_org: HFOrg | None
) -> dict[str, Any]:
    values: dict[str, Any] = {
        "brand": brand,
        "hf_org": hf_org,
        "hf_type": "model",
        "display_name": str(payload.get("id") or "").split("/", 1)[-1],
        "raw": payload,
    }
    field_keys = {
        "author": ("author",),
        "sha": ("sha",),
        "private": ("private",),
        "gated": ("gated",),
        "disabled": ("disabled",),
        "pipeline_tag": ("pipeline_tag", "pipelineTag"),
        "library_name": ("library_name", "libraryName"),
        "downloads": ("downloads",),
        "downloads_all_time": ("downloads_all_time", "downloadsAllTime"),
        "likes": ("likes",),
        "trending_score": ("trending_score", "trendingScore"),
        "paperswithcode_id": ("paperswithcode_id", "paperswithcodeId"),
        "created_at": ("created_at", "createdAt"),
        "last_modified": ("last_modified", "lastModified"),
        "tags": ("tags",),
        "siblings": ("siblings",),
        "card_data": ("card_data", "cardData"),
        "config": ("config",),
        "spaces": ("spaces",),
    }
    for field, keys in field_keys.items():
        for key in keys:
            if key in payload:
                values[field] = payload[key]
                break
    return values


def _upsert_hf_product(
    *,
    repo_id: str,
    brand: Brand,
    hf_org: HFOrg | None,
    metadata: dict[str, Any],
    product_type: str,
    source_release: ModelRelease | None = None,
) -> Product:
    """Converge an exact repo with any approved X-only release Product."""
    product = None
    if source_release is not None:
        ModelRelease.objects.select_for_update().get(pk=source_release.pk)
        prior_product_id = (
            ProductVerificationProposal.objects.filter(
                source_release_id=source_release.pk,
                review_status="approved",
                proposed_brand=brand,
                resolved_product__isnull=False,
            )
            .values_list("resolved_product_id", flat=True)
            .first()
        )
        if prior_product_id is not None:
            product = Product.objects.select_for_update().get(pk=prior_product_id)

    repo_product = Product.objects.select_for_update().filter(repo_id=repo_id).first()
    if (
        product is not None
        and repo_product is not None
        and repo_product.pk != product.pk
    ):
        raise ValueError("repository_product_conflict")
    if product is None:
        product = repo_product

    defaults = _product_defaults(metadata, brand=brand, hf_org=hf_org)
    defaults["type"] = product_type
    if product is None:
        product, _created = Product.objects.get_or_create(
            repo_id=repo_id,
            defaults=defaults,
        )
        product = Product.objects.select_for_update().get(pk=product.pk)
    if product.brand_id not in (None, brand.pk):
        raise ValueError("product_owner_conflict")
    if product.hf_org_id not in (None, hf_org.pk if hf_org else None):
        raise ValueError("product_owner_conflict")
    if product.repo_id not in (None, repo_id):
        raise ValueError("product_repository_conflict")
    if product.type not in (None, product_type):
        raise ValueError("product_type_conflict")
    product.repo_id = repo_id
    defaults["raw"] = {
        **(product.raw if isinstance(product.raw, dict) else {}),
        **metadata,
    }
    for field, value in defaults.items():
        setattr(product, field, value)
    product.save()
    return product


@transaction.atomic
def attach_verified_product(
    *,
    post: Post,
    brand: Brand,
    repo_id: str,
    observed_name: str,
    account: Account,
    metadata: dict[str, Any],
    evidence: dict[str, Any],
    product_type: str,
    policy_version: str = POLICY_VERSION,
    source_release: ModelRelease | None = None,
) -> Product:
    if product_type not in {value for value, _label in Product.TYPES}:
        raise ValueError("invalid_product_type")
    if not _REPO_ID.fullmatch(repo_id):
        raise ValueError("malformed_repo_id")
    returned_id = str(metadata.get("id") or metadata.get("modelId") or "")
    if returned_id.casefold() != repo_id.casefold():
        raise ValueError("metadata_identity_mismatch")
    namespace = repo_id.split("/", 1)[0]
    decision = evaluate_known_publisher(
        account=account, brand=brand, namespace=namespace
    )
    if not decision.qualifies:
        raise ValueError(decision.reason)
    hf_org = HFOrg.objects.select_for_update().get(namespace=namespace, confirmed=True)
    product = _upsert_hf_product(
        repo_id=repo_id,
        brand=brand,
        hf_org=hf_org,
        metadata=metadata,
        product_type=product_type,
        source_release=source_release,
    )
    PostBrandProduct.objects.get_or_create(
        post=post,
        brand=brand,
        product=product,
        defaults={
            "observed_name": observed_name,
            "source_evidence": evidence,
            "verification_policy_version": policy_version,
        },
    )
    return product


def import_known_org_catalog(
    *,
    brand: Brand,
    hf_org: HFOrg,
    client: httpx.Client,
    max_requests: int,
    max_models: int,
    cursor: str | None = None,
) -> CatalogImportResult:
    """Bounded, resumable catalog enumeration; never fetches model files."""
    if not hf_org.confirmed:
        raise ValueError("catalog import requires a confirmed HF organization")
    if not BrandCompany.objects.filter(
        brand=brand, company_id=hf_org.company_id
    ).exists():
        raise ValueError(
            "catalog import Brand does not own the confirmed HF organization"
        )
    if max_requests < 1 or max_models < 1:
        return CatalogImportResult(0, 0, 0, False, "budget_exhausted")
    cursor = cursor.strip() if cursor else None
    seen_cursors: set[str] = {cursor} if cursor else set()
    imported = updated = requests = 0
    while requests < max_requests and imported + updated < max_models:
        params: dict[str, Any] = {
            "author": hf_org.namespace,
            "limit": min(100, max_models - imported - updated),
            "full": "true",
            "sort": "lastModified",
            "direction": -1,
        }
        if cursor:
            params["cursor"] = cursor
        try:
            response = client.get(
                f"{HF_API_BASE}/models",
                params=params,
                headers=_PUBLIC_HEADERS,
                timeout=2.0,
            )
        except httpx.HTTPError:
            return CatalogImportResult(
                imported, updated, requests + 1, False, "request_error", cursor
            )
        requests += 1
        if response.status_code != 200:
            return CatalogImportResult(
                imported,
                updated,
                requests,
                False,
                f"http_{response.status_code}",
                cursor,
            )
        try:
            payload = response.json()
        except ValueError:
            return CatalogImportResult(
                imported, updated, requests, False, "malformed", cursor
            )
        if not isinstance(payload, list):
            return CatalogImportResult(
                imported, updated, requests, False, "malformed", cursor
            )
        remaining = max_models - imported - updated
        if len(payload) > remaining:
            return CatalogImportResult(
                imported, updated, requests, False, "provider_exceeded_limit", cursor
            )
        validated: list[tuple[str, dict[str, Any]]] = []
        for item in payload:
            if not isinstance(item, dict):
                return CatalogImportResult(
                    imported, updated, requests, False, "malformed", cursor
                )
            repo_id = str(item.get("id") or item.get("modelId") or "")
            if (
                not _REPO_ID.fullmatch(repo_id)
                or repo_id.split("/", 1)[0].casefold() != hf_org.namespace.casefold()
            ):
                return CatalogImportResult(
                    imported, updated, requests, False, "owner_mismatch", cursor
                )
            validated.append((repo_id, item))
        next_cursor = _next_cursor(response.headers.get("link", ""))
        if next_cursor and next_cursor in seen_cursors:
            return CatalogImportResult(
                imported, updated, requests, False, "no_progress", cursor
            )
        for repo_id, item in validated:
            with transaction.atomic():
                defaults = _product_defaults(item, brand=brand, hf_org=hf_org)
                product, created = Product.objects.get_or_create(
                    repo_id=repo_id, defaults=defaults
                )
                product = Product.objects.select_for_update().get(pk=product.pk)
                if product and (
                    product.brand_id not in (None, brand.pk)
                    or product.hf_org_id not in (None, hf_org.pk)
                ):
                    return CatalogImportResult(
                        imported, updated, requests, False, "owner_conflict", cursor
                    )
                if not created:
                    defaults["raw"] = {
                        **(product.raw if isinstance(product.raw, dict) else {}),
                        **item,
                    }
                    for field, value in defaults.items():
                        setattr(product, field, value)
                    product.save()
            imported += int(created)
            updated += int(not created)
            if imported + updated >= max_models:
                return CatalogImportResult(
                    imported,
                    updated,
                    requests,
                    not bool(next_cursor),
                    "exhausted" if not next_cursor else "model_cap",
                    next_cursor,
                )
        if not next_cursor:
            return CatalogImportResult(imported, updated, requests, True, "exhausted")
        if not payload:
            return CatalogImportResult(
                imported, updated, requests, False, "no_progress", cursor
            )
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    return CatalogImportResult(
        imported, updated, requests, False, "request_cap", cursor
    )


def proposal_key(
    *, post_id: str, account_id: str, observed_name: str, repo_id: str
) -> str:
    material = f"{post_id}\0{account_id}\0{observed_name}\0{repo_id.casefold()}"
    return hashlib.sha256(material.encode()).hexdigest()


def _proposal_categories(proposal: ProductVerificationProposal) -> list[str]:
    filters: dict[str, Any] = {"post_id": proposal.source_post_id}
    if proposal.proposed_brand_id:
        filters["brand_id"] = proposal.proposed_brand_id
    else:
        filters["brand_discovery_candidate_id"] = proposal.proposed_candidate_id
    return list(
        RareTypeCategoryAssignment.objects.filter(**filters)
        .values_list("category", flat=True)
        .distinct()[:2]
    )


def _release_claim(proposal: ProductVerificationProposal) -> None:
    proposal.verification_claim_token = None
    proposal.verification_claim_expires_at = None


def _transient_next_attempt(outcome: str):
    if outcome in {"timeout", "throttled", "error"}:
        return timezone.now() + timedelta(minutes=15)
    return None


@transaction.atomic
def _record_hf_outcome(
    proposal_id: int,
    claim_token: uuid.UUID,
    result: HFMetadataResult,
    *,
    evidence_key: str | None = None,
) -> bool:
    proposal = ProductVerificationProposal.objects.select_for_update().get(
        pk=proposal_id
    )
    if (
        proposal.verification_claim_token != claim_token
        or proposal.review_status != "pending"
    ):
        return False
    evidence = dict(proposal.hf_evidence or {})
    if evidence_key and result.payload is not None:
        evidence[evidence_key] = result.payload
    elif result.payload is not None:
        evidence = result.payload
    proposal.hf_evidence = evidence
    proposal.hf_outcome = result.outcome
    proposal.attempted_at = timezone.now()
    proposal.next_attempt_at = _transient_next_attempt(result.outcome)
    _release_claim(proposal)
    proposal.save()
    return True


@transaction.atomic
def _record_exact_for_socials(
    proposal_id: int, claim_token: uuid.UUID, payload: dict[str, Any]
) -> bool:
    proposal = ProductVerificationProposal.objects.select_for_update().get(
        pk=proposal_id
    )
    if (
        proposal.verification_claim_token != claim_token
        or proposal.review_status != "pending"
    ):
        return False
    proposal.hf_evidence = {
        **dict(proposal.hf_evidence or {}),
        "_exact_model": payload,
    }
    proposal.hf_outcome = ProductVerificationProposal.HFOutcome.DEFERRED
    proposal.attempted_at = timezone.now()
    proposal.next_attempt_at = None
    proposal.rule_trace = [
        *proposal.rule_trace,
        "exact_model_metadata_cached:awaiting_hf_org_socials",
    ]
    _release_claim(proposal)
    proposal.save()
    return True


@transaction.atomic
def _stop_automatic_verification(
    proposal_id: int,
    claim_token: uuid.UUID,
    decision: LegitimacyDecision,
) -> bool:
    proposal = ProductVerificationProposal.objects.select_for_update().get(
        pk=proposal_id
    )
    if (
        proposal.verification_claim_token != claim_token
        or proposal.review_status != "pending"
    ):
        return False
    proposal.hf_outcome = ProductVerificationProposal.HFOutcome.DEFERRED
    proposal.next_attempt_at = None
    proposal.rule_trace = [
        *decision.trace,
        "automatic_verification_stopped",
        f"automatic_verification_stopped:{decision.reason}",
    ]
    _release_claim(proposal)
    proposal.save()
    return True


def _brand_slug_for_namespace(namespace: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", namespace.casefold()).strip("_")[:63]


@transaction.atomic
def _finalize_new_publisher(
    proposal_id: int,
    claim_token: uuid.UUID,
    *,
    model_payload: dict[str, Any],
    socials_payload: dict[str, Any],
) -> bool:
    proposal = (
        ProductVerificationProposal.objects.select_related(
            "proposed_candidate", "account", "source_post", "source_release"
        )
        .select_for_update(of=("self",))
        .get(pk=proposal_id)
    )
    if (
        proposal.verification_claim_token != claim_token
        or proposal.review_status != "pending"
    ):
        return False
    proposal.account = Account.objects.select_for_update().get(pk=proposal.account_id)
    candidate = BrandDiscoveryCandidate.objects.select_for_update().get(
        pk=proposal.proposed_candidate_id
    )
    namespace = proposal.candidate_repo_id.split("/", 1)[0]
    decision = _evaluate_new_publisher_source(proposal, namespace=namespace)
    if not decision.qualifies:
        proposal.hf_outcome = ProductVerificationProposal.HFOutcome.DEFERRED
        proposal.rule_trace = [
            *decision.trace,
            "automatic_verification_stopped",
            f"automatic_verification_stopped:{decision.reason}",
        ]
        _release_claim(proposal)
        proposal.save()
        return False
    twitter_handle = str(
        (socials_payload.get("socialHandles") or {}).get("twitter") or ""
    ).removeprefix("@")
    if (
        str(socials_payload.get("org") or "").casefold() != namespace.casefold()
        or not twitter_handle
        or twitter_handle.casefold()
        != str(proposal.account.handle or "").removeprefix("@").casefold()
    ):
        _release_claim(proposal)
        proposal.hf_outcome = ProductVerificationProposal.HFOutcome.MATCHED
        proposal.hf_evidence = {
            **dict(proposal.hf_evidence or {}),
            "_hf_org_socials": socials_payload,
        }
        proposal.rule_trace = [
            *decision.trace,
            "automatic_verification_stopped",
            "automatic_verification_stopped:hf_social_handle_conflict",
        ]
        proposal.save()
        return False

    categories = _proposal_categories(proposal)
    if len(categories) != 1:
        raise ValueError("product_category_ambiguous")
    if candidate.reviewed_brand_id:
        brand = Brand.objects.select_for_update().get(pk=candidate.reviewed_brand_id)
    else:
        brand_id = _brand_slug_for_namespace(namespace)
        if not brand_id:
            raise ValueError("publisher_brand_id_invalid")
        if Brand.objects.filter(pk=brand_id).exists():
            raise ValueError("publisher_brand_collision")
        try:
            brand = Brand.objects.create(
                nickname=brand_id,
                display_name=candidate.observed_name,
            )
        except IntegrityError as exc:
            raise ValueError("publisher_brand_collision") from exc
        candidate.reviewed_brand = brand
        candidate.verification_status = "confirmed"
        candidate.reviewer = f"automatic:{POLICY_VERSION}"
        candidate.review_note = "Exact X Business/HF repository/social cross-links"
        candidate.reviewed_at = timezone.now()
        candidate.save()

    hf_org = (
        HFOrg.objects.select_for_update()
        .filter(namespace=namespace, confirmed=True)
        .first()
    )
    if hf_org:
        existing_company_ids = set(
            BrandCompany.objects.filter(brand=brand).values_list(
                "company_id", flat=True
            )
        )
        if existing_company_ids and hf_org.company_id not in existing_company_ids:
            raise ValueError("publisher_company_owner_conflict")
        BrandCompany.objects.get_or_create(brand=brand, company_id=hf_org.company_id)

    product = _upsert_hf_product(
        repo_id=proposal.candidate_repo_id,
        brand=brand,
        hf_org=hf_org,
        metadata=model_payload,
        product_type=categories[0],
        source_release=proposal.source_release,
    )
    PostBrandProduct.objects.get_or_create(
        post=proposal.source_post,
        brand=brand,
        product=product,
        defaults={
            "observed_name": proposal.observed_name,
            "source_evidence": {"proposal_key": proposal.proposal_key},
            "verification_policy_version": proposal.policy_version,
        },
    )
    proposal.proposed_brand = brand
    proposal.proposed_candidate = None
    proposal.resolved_product = product
    proposal.hf_outcome = ProductVerificationProposal.HFOutcome.MATCHED
    proposal.hf_evidence = {
        **dict(proposal.hf_evidence or {}),
        "_exact_model": model_payload,
        "_hf_org_socials": socials_payload,
    }
    proposal.rule_trace = [*decision.trace, "hf_social_handle_match:true"]
    proposal.review_status = "approved"
    proposal.review_reason = "automatic_cross_platform_publisher"
    proposal.reviewed_at = timezone.now()
    _release_claim(proposal)
    proposal.save()
    return True


@transaction.atomic
def _finalize_known_publisher(
    proposal_id: int,
    claim_token: uuid.UUID,
    result: HFMetadataResult,
) -> bool:
    proposal = (
        ProductVerificationProposal.objects.select_related(
            "account", "proposed_brand", "source_post"
        )
        .select_for_update(of=("self",))
        .get(pk=proposal_id)
    )
    if (
        proposal.verification_claim_token != claim_token
        or proposal.review_status != "pending"
    ):
        return False
    proposal.account = Account.objects.select_for_update().get(pk=proposal.account_id)
    proposal.attempted_at = timezone.now()
    proposal.hf_outcome = result.outcome
    proposal.hf_evidence = result.payload or {}
    proposal.next_attempt_at = _transient_next_attempt(result.outcome)
    did_resolve = False
    try:
        if result.outcome == "matched" and proposal.proposed_brand_id:
            categories = _proposal_categories(proposal)
            namespace = proposal.candidate_repo_id.split("/", 1)[0]
            decision = evaluate_known_publisher(
                account=proposal.account,
                brand=proposal.proposed_brand,
                namespace=namespace,
            )
            trace = list(decision.trace)
            if proposal.policy_version == POLICY_VERSION:
                source = _proposal_source_gate(proposal, namespace=namespace)
                trace.extend(source.trace)
                if not source.qualifies:
                    decision = source
            proposal.rule_trace = trace
            if decision.qualifies and len(categories) == 1:
                proposal.resolved_product = attach_verified_product(
                    post=proposal.source_post,
                    brand=proposal.proposed_brand,
                    repo_id=proposal.candidate_repo_id,
                    observed_name=proposal.observed_name,
                    account=proposal.account,
                    metadata=result.payload or {},
                    evidence={"proposal_key": proposal.proposal_key},
                    product_type=categories[0],
                    policy_version=proposal.policy_version,
                    source_release=proposal.source_release,
                )
                proposal.review_status = "approved"
                proposal.review_reason = "automatic_known_publisher"
                proposal.reviewed_at = timezone.now()
                did_resolve = True
    except (IntegrityError, ValueError) as exc:
        logger.warning(
            "product verification proposal %s retained for review: %s",
            proposal.pk,
            type(exc).__name__,
        )
        proposal.rule_trace = [
            *proposal.rule_trace,
            f"resolution_error:{type(exc).__name__}",
        ]
    _release_claim(proposal)
    proposal.save()
    return did_resolve


def drain_pending_verifications(
    *, max_requests: int, deadline: Any, client: httpx.Client | None = None
) -> VerificationDrainResult:
    """Drain due proposals after critical post-fetch work, within caller limits."""
    if max_requests < 1:
        return VerificationDrainResult(0, 0, 0)
    owned_client = client is None
    http = client or httpx.Client(timeout=2.0)
    attempted = resolved = deferred = 0
    try:
        for _slot in range(max_requests):
            now = timezone.now()
            claim_token = uuid.uuid4()
            with transaction.atomic():
                proposal = (
                    ProductVerificationProposal.objects.select_for_update(
                        skip_locked=True
                    )
                    .filter(
                        review_status="pending",
                        hf_outcome__in=[
                            ProductVerificationProposal.HFOutcome.PENDING,
                            ProductVerificationProposal.HFOutcome.DEFERRED,
                            ProductVerificationProposal.HFOutcome.TIMEOUT,
                            ProductVerificationProposal.HFOutcome.THROTTLED,
                            ProductVerificationProposal.HFOutcome.ERROR,
                        ],
                    )
                    .exclude(candidate_repo_id="")
                    .exclude(rule_trace__contains=["automatic_verification_stopped"])
                    .filter(
                        models.Q(next_attempt_at__isnull=True)
                        | models.Q(next_attempt_at__lte=now),
                        models.Q(verification_claim_expires_at__isnull=True)
                        | models.Q(verification_claim_expires_at__lte=now),
                    )
                    .order_by("created_at", "id")
                    .first()
                )
                if proposal is None:
                    break
                proposal.verification_claim_token = claim_token
                proposal.verification_claim_expires_at = now + timedelta(minutes=2)
                proposal.save(
                    update_fields=[
                        "verification_claim_token",
                        "verification_claim_expires_at",
                        "updated_at",
                    ]
                )
            namespace = proposal.candidate_repo_id.split("/", 1)[0]
            if proposal.policy_version == POLICY_VERSION:
                if proposal.proposed_candidate_id:
                    source_decision = _evaluate_new_publisher_source(
                        proposal, namespace=namespace
                    )
                else:
                    source_decision = _proposal_source_gate(
                        proposal, namespace=namespace
                    )
                if not source_decision.qualifies:
                    _stop_automatic_verification(
                        proposal.pk, claim_token, source_decision
                    )
                    deferred += 1
                    continue
            if deadline is not None and not deadline.can_start(2.0):
                _record_hf_outcome(
                    proposal.pk,
                    claim_token,
                    HFMetadataResult("deferred", None),
                )
                deferred += 1
                break
            exact_payload = (proposal.hf_evidence or {}).get("_exact_model")
            if proposal.proposed_candidate_id and isinstance(exact_payload, dict):
                result = hf_org_socials(namespace, client=http)
                attempted += 1
                if result.outcome != "matched":
                    _record_hf_outcome(
                        proposal.pk,
                        claim_token,
                        result,
                        evidence_key="_hf_org_socials",
                    )
                    continue
                try:
                    resolved += int(
                        _finalize_new_publisher(
                            proposal.pk,
                            claim_token,
                            model_payload=exact_payload,
                            socials_payload=result.payload or {},
                        )
                    )
                except (IntegrityError, ValueError) as exc:
                    logger.warning(
                        "product verification proposal %s retained for review: %s",
                        proposal.pk,
                        type(exc).__name__,
                    )
                    _stop_automatic_verification(
                        proposal.pk,
                        claim_token,
                        LegitimacyDecision(
                            False,
                            f"resolution_error:{type(exc).__name__}",
                            tuple(proposal.rule_trace),
                        ),
                    )
                continue

            result = exact_model_metadata(proposal.candidate_repo_id, client=http)
            attempted += 1
            if proposal.proposed_candidate_id and result.outcome == "matched":
                if _record_exact_for_socials(
                    proposal.pk, claim_token, result.payload or {}
                ):
                    deferred += 1
            else:
                resolved += int(
                    _finalize_known_publisher(proposal.pk, claim_token, result)
                )
    finally:
        if owned_client:
            http.close()
    return VerificationDrainResult(attempted, resolved, deferred)
