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

import httpx
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from core.models import (
    Account,
    Brand,
    BrandAccount,
    BrandCompany,
    HFOrg,
    Post,
    PostBrandProduct,
    Product,
    ProductVerificationProposal,
    RareTypeCategoryAssignment,
)
from x_monitor.hf_client import HF_API_BASE, _next_cursor

POLICY_VERSION = "product-x-hf-v1"
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


@dataclass(frozen=True)
class VerificationDrainResult:
    attempted: int
    resolved: int
    deferred: int


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
    return HFMetadataResult("matched", payload)


def _product_defaults(
    payload: dict[str, Any], *, brand: Brand, hf_org: HFOrg
) -> dict[str, Any]:
    return {
        "brand": brand,
        "hf_org": hf_org,
        "hf_type": "model",
        "display_name": str(payload.get("id") or "").split("/", 1)[-1],
        "author": payload.get("author"),
        "sha": payload.get("sha"),
        "private": payload.get("private"),
        "gated": payload.get("gated"),
        "disabled": payload.get("disabled"),
        "pipeline_tag": payload.get("pipeline_tag"),
        "library_name": payload.get("library_name"),
        "downloads": payload.get("downloads"),
        "likes": payload.get("likes"),
        "tags": payload.get("tags"),
        "raw": payload,
    }


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
    defaults = _product_defaults(metadata, brand=brand, hf_org=hf_org)
    defaults["type"] = product_type
    product, created = Product.objects.get_or_create(repo_id=repo_id, defaults=defaults)
    product = Product.objects.select_for_update().get(pk=product.pk)
    if product and (
        product.brand_id not in (None, brand.pk)
        or product.hf_org_id not in (None, hf_org.pk)
    ):
        raise ValueError("product_owner_conflict")
    if not created:
        for field, value in defaults.items():
            setattr(product, field, value)
        product.save()
    PostBrandProduct.objects.get_or_create(
        post=post,
        brand=brand,
        product=product,
        defaults={
            "observed_name": observed_name,
            "source_evidence": evidence,
            "verification_policy_version": POLICY_VERSION,
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
) -> CatalogImportResult:
    """Bounded, resumable catalog enumeration; never fetches model files."""
    if not hf_org.confirmed:
        raise ValueError("catalog import requires a confirmed HF organization")
    if max_requests < 1 or max_models < 1:
        return CatalogImportResult(0, 0, 0, False, "budget_exhausted")
    cursor = None
    seen_cursors: set[str] = set()
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
                imported, updated, requests + 1, False, "request_error"
            )
        requests += 1
        if response.status_code != 200:
            return CatalogImportResult(
                imported, updated, requests, False, f"http_{response.status_code}"
            )
        try:
            payload = response.json()
        except ValueError:
            return CatalogImportResult(imported, updated, requests, False, "malformed")
        if not isinstance(payload, list):
            return CatalogImportResult(imported, updated, requests, False, "malformed")
        for item in payload:
            if not isinstance(item, dict):
                return CatalogImportResult(
                    imported, updated, requests, False, "malformed"
                )
            repo_id = str(item.get("id") or item.get("modelId") or "")
            if (
                not _REPO_ID.fullmatch(repo_id)
                or repo_id.split("/", 1)[0].casefold() != hf_org.namespace.casefold()
            ):
                return CatalogImportResult(
                    imported, updated, requests, False, "owner_mismatch"
                )
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
                        imported, updated, requests, False, "owner_conflict"
                    )
                if not created:
                    for field, value in defaults.items():
                        setattr(product, field, value)
                    product.save()
            imported += int(created)
            updated += int(not created)
            if imported + updated >= max_models:
                return CatalogImportResult(
                    imported, updated, requests, False, "model_cap"
                )
        next_cursor = _next_cursor(response.headers.get("link", ""))
        if not next_cursor:
            return CatalogImportResult(imported, updated, requests, True, "exhausted")
        if next_cursor in seen_cursors or not payload:
            return CatalogImportResult(
                imported, updated, requests, False, "no_progress"
            )
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    return CatalogImportResult(imported, updated, requests, False, "request_cap")


def proposal_key(
    *, post_id: str, account_id: str, observed_name: str, repo_id: str
) -> str:
    material = f"{post_id}\0{account_id}\0{observed_name}\0{repo_id.casefold()}"
    return hashlib.sha256(material.encode()).hexdigest()


@transaction.atomic
def _finalize_verification(
    proposal_id: int, claim_token: uuid.UUID, result: HFMetadataResult
) -> bool:
    proposal = ProductVerificationProposal.objects.select_for_update().get(
        pk=proposal_id
    )
    if proposal.verification_claim_token != claim_token:
        return False
    if proposal.review_status != "pending":
        proposal.verification_claim_token = None
        proposal.verification_claim_expires_at = None
        proposal.save(
            update_fields=[
                "verification_claim_token",
                "verification_claim_expires_at",
                "updated_at",
            ]
        )
        return False
    proposal.attempted_at = timezone.now()
    proposal.hf_outcome = result.outcome
    proposal.hf_evidence = result.payload or {}
    proposal.next_attempt_at = (
        timezone.now() + timedelta(minutes=15)
        if result.outcome in {"timeout", "throttled", "error"}
        else None
    )
    did_resolve = False
    try:
        if result.outcome == "matched" and proposal.proposed_brand_id:
            categories = list(
                RareTypeCategoryAssignment.objects.filter(
                    post_id=proposal.source_post_id,
                    brand_id=proposal.proposed_brand_id,
                )
                .values_list("category", flat=True)
                .distinct()[:2]
            )
            if len(categories) == 1:
                decision = evaluate_known_publisher(
                    account=proposal.account,
                    brand=proposal.proposed_brand,
                    namespace=proposal.candidate_repo_id.split("/", 1)[0],
                )
                proposal.rule_trace = list(decision.trace)
                if decision.qualifies:
                    proposal.resolved_product = attach_verified_product(
                        post=proposal.source_post,
                        brand=proposal.proposed_brand,
                        repo_id=proposal.candidate_repo_id,
                        observed_name=proposal.observed_name,
                        account=proposal.account,
                        metadata=result.payload or {},
                        evidence={"proposal_key": proposal.proposal_key},
                        product_type=categories[0],
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
    proposal.verification_claim_token = None
    proposal.verification_claim_expires_at = None
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
            if deadline is not None and not deadline.can_start(2.0):
                proposal.hf_outcome = ProductVerificationProposal.HFOutcome.DEFERRED
                proposal.verification_claim_token = None
                proposal.verification_claim_expires_at = None
                proposal.save(
                    update_fields=[
                        "hf_outcome",
                        "verification_claim_token",
                        "verification_claim_expires_at",
                        "updated_at",
                    ]
                )
                deferred += 1
                break
            result = exact_model_metadata(proposal.candidate_repo_id, client=http)
            attempted += 1
            resolved += int(_finalize_verification(proposal.pk, claim_token, result))
    finally:
        if owned_client:
            http.close()
    return VerificationDrainResult(attempted, resolved, deferred)
