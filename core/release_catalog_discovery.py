"""Discover native model identifiers from bounded, first-party public catalogs."""

import logging
import re
import unicodedata
from contextlib import closing
from hashlib import sha256

import httpx
from django.core.cache import cache
from django.db import transaction
from django.db.models import Q

from core import models
from core.benchmark_metric_identity import register_source
from core.collection_identity import (
    dedicated_product_mapping,
    qualified_catalog_ownership,
    review_catalog_mapping,
)
from core.collection_matching import name_key
from core.measurement_taxonomy import product_measurement_subject
from core.product_preview_names import chart_preview_names, preview_redirects
from core.release_arena_catalog import arena_candidates
from core.release_chart_handoff import lock_catalog_release
from core.release_provider_identity import release_product_query
from core.release_usage_catalogs import opencode_candidates, openrouter_candidates
from scripts.benchmark_download_collector.sources import (
    ARENA_LATEST,
    OPENROUTER_MODELS_URL,
    AmbiguousCatalogMatch,
)

CATALOGS = {
    "openrouter": openrouter_candidates,
    "opencode": opencode_candidates,
    "arena": arena_candidates,
}
SCOPES = {
    "openrouter": "catalog_id",
    "opencode": "model_id",
    "arena": "arena_model_name",
}
logger = logging.getLogger(__name__)


def catalog_document(budget, url, params=None):
    if url not in (ARENA_LATEST, OPENROUTER_MODELS_URL) and not re.fullmatch(
        r"https://opencode\.ai/data/(?:llms\.txt|[a-z0-9_-]+(?:/[a-z0-9_-]+)?\.json)",
        url,
    ):
        raise ValueError("unrecognized release catalog endpoint")
    key = (
        "pulse-public-catalog-v1:"
        + sha256(str(httpx.URL(url, params=params)).encode()).hexdigest()
    )
    content = cache.get(key)
    if content is None:
        if url == ARENA_LATEST:
            content = budget.arena_asset()
        else:
            request = budget.public_request(url, params)
            with closing(
                budget.client.send(
                    request, stream=True, auth=None, follow_redirects=False
                )
            ) as response:
                response.raise_for_status()
                content = budget.response_bytes(response)
        cache.set(key, content, 900)
    return content


def model_name_key(value):
    normalized = unicodedata.normalize("NFKC", value).translate(
        str.maketrans({"‐": "-", "‑": "-", "–": "-"})
    )
    # Removing formatting between digits must never turn version 1-2 into 12.
    return name_key(normalized), tuple(re.findall(r"\d+", normalized))


def _product_evidence(product, now):
    accounts = list(
        models.BrandAccount.objects.filter(
            brand_id=product.brand_id,
            role_id="official",
        )
        .select_related("account")
        .order_by("account_id")[:65]
    )
    if not accounts or len(accounts) > 64:
        return None
    accounts = [
        link.account
        for link in accounts
        if qualified_catalog_ownership(link.account, product=product)
    ]
    if not accounts:
        return None
    # An account shared across brand lines still identifies their common publisher.
    # The provider row must independently identify this exact model.
    preferred = next(
        (a for a in accounts if a.pk == product.publisher_account_id), accounts[0]
    )
    names = {product.display_name, *chart_preview_names(product, now, strict=False)}
    if product.repo_id and product.publisher_account_id:
        names.add(product.repo_id.rsplit("/", 1)[-1])
    brand = product.brand
    issuers = {
        brand.pk,
        brand.display_name,
        brand.display_name_en,
        brand.display_name_zh_cn,
    }
    for account in accounts:
        issuers.add(account.normalized_handle)
        if account.data_source_id == "hf":
            issuers.add(account.external_identifier)
    companies = list(
        models.BrandCompany.objects.filter(brand=brand).values_list(
            "company_id", flat=True
        )[:2]
    )
    if len(companies) == 1:
        issuers.add(companies[0])
        issuers.update(
            models.CompanyLabel.objects.filter(company_id=companies[0]).values_list(
                "label", flat=True
            )
        )
    return (
        preferred,
        {model_name_key(n) for n in names if n},
        {name_key(n) for n in issuers if n},
    )


def _existing(product, sources):
    rows = (
        models.SourceSubjectMapping.objects.filter(
            subject__product=product,
            source_id__in=sources,
            purpose="catalog",
        )
        .select_related("identifier_scope")
        .only(
            "source_id",
            "identifier_scope__code",
            "identity_snapshot",
            "identifier_metadata",
        )
    )
    states = {}
    for row in rows:
        if row.identifier_scope_code == SCOPES[row.source_id]:
            # Preserve human decisions, including a role that cannot supply model metrics.
            state = "existing" if dedicated_product_mapping(row) else "review_required"
            if row.source_id in states:
                state = "review_required"
            states[row.source_id] = state
    return states


def _competing_product(product, names, now):
    companies = models.BrandCompany.objects.filter(brand_id=product.brand_id).values(
        "company_id"
    )
    siblings = models.BrandCompany.objects.filter(company_id__in=companies).values(
        "brand_id"
    )
    shared_accounts = models.BrandAccount.objects.filter(
        brand_id=product.brand_id, role_id="official"
    ).values("account_id")
    related = models.BrandAccount.objects.filter(
        account_id__in=shared_accounts, role_id="official"
    ).values("brand_id")
    others = (
        models.Product.objects.exclude(pk=product.pk)
        .exclude(private=True)
        .exclude(disabled=True)
        .filter(
            Q(brand_id=product.brand_id)
            | Q(brand_id__in=siblings)
            | Q(brand_id__in=related)
            | Q(publisher_account_id__in=shared_accounts)
        )
        .order_by("pk")
        .values_list("pk", "brand_id", "display_name", "repo_id")[:10001]
    )
    collisions = []
    for i, (pk, brand, title, repo) in enumerate(others):
        if i == 10000:
            return True
        if any(
            model_name_key(n) in names
            for n in (title, repo.rsplit("/", 1)[-1] if repo else None)
            if n
        ):
            collisions.append((pk, brand, title))
    redirects = preview_redirects(collisions, cutoff=now, strict=False)
    return any(redirects.get(pk) != product.pk for pk, _, _ in collisions)


@transaction.atomic
def _store(release, product, evidence, source, candidate, now):
    lock_catalog_release(release)
    product = release_product_query().select_for_update(of=("self",)).get(pk=product.pk)
    if (
        product.brand_id != release.brand_id
        or _product_evidence(product, now) != evidence
    ):
        return "deferred"
    prior = _existing(product, [source])
    if prior:
        return prior[source]
    if _competing_product(product, evidence[1], now):
        return "ambiguous"
    identifier, scope, url, metadata = candidate
    if scope != SCOPES[source]:
        raise ValueError("wrong provider identifier namespace")
    provider, _ = register_source(source)
    subject = product_measurement_subject(product)
    review_catalog_mapping(
        source=provider,
        subject=subject,
        external_identifier=identifier,
        source_subject_kind="model",
        identifier_scope=scope,
        publisher_account=evidence[0],
        role="dedicated_model",
        version_selector=None,
        evidence_url=url,
        reviewed_by="pulse-release-catalog-v1",
        identity_snapshot={},
        identifier_metadata=metadata,
    )
    return "mapped"


def discover_release_catalogs(release, budget, *, now, catalogs=None):
    product = release_product_query().get(product_key=release.product_key)
    if product.brand_id != release.brand_id or product.product_type_code not in {
        "model-llm",
        "model-other",
    }:
        return {}
    catalogs = CATALOGS if catalogs is None else catalogs
    outcomes = _existing(product, catalogs)
    missing = [source for source in catalogs if source not in outcomes]
    if not missing:
        return outcomes
    evidence = _product_evidence(product, now)
    if evidence is None:
        return {**outcomes, **dict.fromkeys(missing, "publisher_pending")}
    _, names, issuers = evidence

    def fetch(url, params=None):
        return catalog_document(budget, url, params)

    def matches(name):
        return model_name_key(name) in names

    def owns(label):
        return name_key(label) in issuers

    for source in missing:
        if budget.clock() >= budget.deadline:
            outcomes[source] = "deferred"
            continue
        try:
            rows = catalogs[source](fetch, matches, owns)
            if len(rows) == 1:
                outcomes[source] = _store(
                    release, product, evidence, source, rows[0], now
                )
            else:
                outcomes[source] = "ambiguous" if rows else "no_verified_match"
        except AmbiguousCatalogMatch:
            outcomes[source] = "ambiguous"
        except (ValueError, httpx.HTTPError, TimeoutError) as exc:
            outcomes[source] = "deferred"
            logger.info(
                "Release catalog lookup deferred for %s on %s (%s)",
                product.pk,
                source,
                type(exc).__name__,
            )
    return outcomes
