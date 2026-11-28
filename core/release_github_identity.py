"""Turn retained publisher links into official GitHub identities for an exact release."""

import logging
import re

import httpx
from django.db import transaction
from django.db.models import Min

from core import models
from core.collection_identity import dedicated_product_mapping, review_github_mapping
from core.github_catalog import register_github_source
from core.github_metadata_client import GitHubMetadataClient
from core.measurement_taxonomy import product_measurement_subject
from core.product_release_acquisition import github_repository_outcome
from core.release_chart_handoff import lock_catalog_release
from core.release_provider_identity import bind_release_publisher, release_product_query

GITHUB_SOURCE_VERSION = "pulse-github-source-v1"
_GITHUB_URL = re.compile(
    r"https://github\.com/([a-z0-9](?:[a-z0-9-]{0,37}[a-z0-9])?)(?:/([a-z0-9_.-]{1,100}))?/?",
    re.IGNORECASE | re.ASCII,
)


def _path(url):
    match = _GITHUB_URL.fullmatch(url) if isinstance(url, str) else None
    if not match or match[2] in (".", ".."):
        return None
    return (match[1], match[2])


def publisher_github_links(profile_urls, urls, product):
    """Only a self-profile link explicitly identifies the owner of unrelated repositories."""
    from core.release_publisher_recovery import _offering_key

    profiles = {
        parts[0].casefold(): parts[0]
        for url in profile_urls
        if (parts := _path(url)) and not parts[1]
    }
    if len(profiles) > 1:
        return None, None
    profile = next(iter(profiles.values()), None)
    repos = {}
    for url in urls:
        parts = _path(url)
        if not parts:
            continue
        owner, name = parts
        if (
            (not profile or owner.casefold() == profile.casefold())
            and name
            and _offering_key(name) == _offering_key(product)
        ):
            repos[(owner.casefold(), name.casefold())] = f"{owner}/{name}"
    return profile, next(iter(repos.values())) if len(repos) == 1 else None


def _claims(release, product):
    return tuple(
        models.EventDossierClaim.objects.filter(
            event_dossier_source__event_dossier_id=release.dossier_id,
            reported_product=product,
            reported_brand_id=release.brand_id,
            claim_kind_reference__code="release_context",
            extraction_version=GITHUB_SOURCE_VERSION,
        )
        .values("scope_key", "assertion_text")
        .annotate(locator=Min("source_locator"))
        .order_by("scope_key", "assertion_text")
        .values_list("scope_key", "assertion_text", "locator")[:8]
    )


def _owner_id(owner, login):
    if not isinstance(owner, dict):
        return None
    identifier = owner.get("id")
    if (
        owner.get("type") == "Organization"
        and type(identifier) is int
        and identifier > 0
        and str(owner.get("login")).casefold() == login.casefold()
        and str(owner.get("html_url")).rstrip("/").casefold()
        == f"https://github.com/{login}".casefold()
    ):
        return str(identifier)
    return None


def discover_github_release(release, *, budget):
    """Check native IDs for first-party links. Preserve the claims for a later wake."""
    if not budget.remaining:
        return False
    product = release_product_query().get(product_key=release.product_key)
    if product.brand_id != release.brand_id or product.product_type_code not in {
        "model-other",
        "model-llm",
    }:
        return False
    proofs = _claims(release, product)
    if not proofs or len(proofs) == 8:
        return False
    profiles, repos = {}, {}
    for scope, url, locator in proofs:
        parsed = _path(url)
        if not parsed or not locator:
            continue
        login, name = parsed
        if not name and scope == "github-publisher:" + login.casefold():
            profiles[login.casefold()] = (login, locator)
        elif name and scope == "github-repository:" + f"{login}/{name}".casefold():
            repos[f"{login}/{name}".casefold()] = (url, locator)
    if len(profiles) > 1:
        return False
    profile, locator = next(iter(profiles.values()), (None, None))
    repo, repo_locator = (
        next(iter(repos.values()), (None, None)) if len(repos) == 1 else (None, None)
    )
    profile_urls = [f"https://github.com/{profile}"] if profile else []
    profile, full_name = publisher_github_links(
        profile_urls, [repo], product.display_name or ""
    )
    if not profile and not full_name:
        return False
    login = profile or full_name.split("/")[0]
    links = models.BrandAccount.objects.filter(
        brand_id=product.brand_id,
        role_id="official",
        account__data_source_id="github",
        account__normalized_handle=login.casefold(),
    )
    accounts = list(links.values_list("account__external_identifier", flat=True)[:2])
    if len(accounts) > 1:
        return False
    verified = accounts[0] if accounts else None
    if verified and not full_name:
        return False
    catalog = models.SourceSubjectMapping.objects.filter(
        source_id="github",
        purpose="catalog",
        subject__product=product,
        identifier_scope__code="repository_id",
    )
    # Preserve existing dedicated reviews. A family or dependency is not a dedicated match.
    if any(dedicated_product_mapping(mapping) for mapping in catalog):
        full_name = None
    if verified and not full_name:
        return False
    client = GitHubMetadataClient(budget)
    native_repo = None
    try:
        if not verified:
            response = client.owner(login)
            owner = response.payload
            verified = _owner_id(owner, login) if response.status == 200 else None
            if not verified:
                return False
            if not profile:
                # A repo link alone may point to a dependency. Corroborate GitHub's
                # stated X handle with an existing official account for this brand.
                twitter = owner.get("twitter_username")
                if (
                    not isinstance(twitter, str)
                    or not twitter.strip()
                    or not models.BrandAccount.objects.filter(
                        brand_id=product.brand_id,
                        role_id="official",
                        account__data_source_id="x",
                        account__normalized_handle=twitter.lstrip("@").casefold(),
                    ).exists()
                ):
                    return False
        if full_name and budget.remaining:
            response = client.repository(full_name)
            candidate = response.payload
            if (
                github_repository_outcome(response.status, candidate, full_name)
                == "found"
                and _owner_id(candidate.get("owner"), login) == verified
                and str(candidate.get("html_url")).casefold()
                == f"https://github.com/{full_name}".casefold()
                and candidate.get("fork") is False
            ):
                native_repo = candidate
    except (ValueError, httpx.HTTPError):
        # An independently verified profile can survive temporary repo unavailability.
        if not verified:
            return False
    with transaction.atomic():
        lock_catalog_release(release)
        if _claims(release, product) != proofs:
            return False
        register_github_source()
        account = bind_release_publisher(
            product.brand_id, "github", verified, login, locator or repo_locator
        )
        if not account:
            return False
        if native_repo:
            subject = product_measurement_subject(product)
            try:
                if not any(
                    dedicated_product_mapping(mapping) for mapping in catalog.all()
                ):
                    review_github_mapping(
                        subject=subject,
                        repo=native_repo,
                        role="dedicated_model",
                        evidence_url=native_repo["html_url"],
                        reviewed_by=GITHUB_SOURCE_VERSION,
                    )
                    return True
            except ValueError as exc:
                logging.getLogger(__name__).info(
                    "GitHub repository mapping deferred for product %s: %s",
                    product.pk,
                    exc,
                )
        return not accounts
