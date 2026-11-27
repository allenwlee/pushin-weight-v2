"""Bind an explicitly publisher-linked HF model to the same catalog Product."""

import json
import re
from contextlib import closing

import httpx
from django.db import IntegrityError, transaction
from django.utils.dateparse import parse_datetime
from django.utils.timezone import is_aware

from core import models
from core.account_identity import upsert_account
from core.collection_capture import archive_document
from core.collection_identity import dedicated_product_mapping, review_catalog_mapping
from core.measurement_taxonomy import resolve_subject_id
from core.product_verification import _repo_from_hf_url
from core.publisher_accounts import register_publisher
from core.release_chart_handoff import lock_qualified_release


@transaction.atomic
def bind_hf_publisher(brand_id, namespace, evidence_url):
    """One HF account can supply both the brand and its established company URL."""
    brand = models.Brand.objects.select_for_update().get(pk=brand_id)
    account_q = models.Account.objects.select_for_update().filter(
        data_source_id="hf", normalized_identifier=namespace.casefold()
    )
    account = account_q.first()
    if account is None:
        try:
            with transaction.atomic():
                account = upsert_account(
                    source="hf",
                    external_identifier=namespace,
                    handle=namespace,
                    provider_metadata={"discovered_via": evidence_url},
                )
        except IntegrityError:
            account = account_q.get()
    companies = list(
        models.BrandCompany.objects.filter(brand=brand).values_list(
            "company_id", flat=True
        )[:2]
    )
    owners = models.BrandAccount.objects.filter(account=account)
    if owners.exclude(role_id="official").exists():
        return None
    siblings = owners.exclude(brand=brand)
    if siblings.exists():
        # A company may publish several verified brand lines under one HF account.
        if len(companies) != 1:
            return None
        related = models.BrandCompany.objects.filter(
            brand_id__in=siblings.values("brand_id")
        )
        if (
            siblings.exclude(brand_id__in=related.values("brand_id")).exists()
            or related.exclude(company_id=companies[0]).exists()
            or not models.CompanyAccount.objects.filter(
                account=account,
                company_id=companies[0],
                role_id="official",
                ownership_confirmed=True,
            ).exists()
        ):
            return None
    if len(companies) == 1:
        if (
            models.CompanyAccount.objects.filter(account=account)
            .exclude(company_id=companies[0], role_id="official")
            .exists()
        ):
            return None
        register_publisher(
            source="hf", identifier=namespace, company_id=companies[0], confirmed=True
        )
    role, _ = models.Role.objects.get_or_create(pk="official")
    models.BrandAccount.objects.get_or_create(
        brand=brand, account=account, defaults={"role": role}
    )
    return account


def hf_model_metadata(repo, budget):
    """Only a matching public Hub model detail response can supply a native model ID."""
    if _repo_from_hf_url("https://huggingface.co/" + repo) != repo:
        return None
    endpoint = "https://huggingface.co/api/models/" + repo
    # An exact, reviewed native response can be reused by another announcement.
    mapping = models.SourceSubjectMapping.objects.filter(
        purpose="catalog",
        source_id="hf",
        identifier_scope__code="model",
        source_subject_kind="repository",
        external_identifier__iexact=repo,
        subject__product__repo_id__iexact=repo,
        publisher_account__data_source_id="hf",
        publisher_account__normalized_identifier=repo.split("/")[0].casefold(),
    ).first()
    raw = None
    if mapping and dedicated_product_mapping(mapping):
        capture = mapping.identifier_metadata.get("release_endpoint") or {}
        if capture.get("url", "").casefold() == endpoint.casefold() and capture.get(
            "archive_sha256"
        ):
            body = (
                models.CollectionEvidenceArchive.objects.filter(
                    content_sha256=capture["archive_sha256"],
                    encoding="decoded-body-v1",
                    capture_kind="response",
                    byte_count__lte=1024 * 1024,
                )
                .values_list("body", flat=True)
                .first()
            )
            if body is not None:
                raw = bytes(body)
    if raw is None:
        request = budget.public_request(endpoint)
        with closing(
            budget.client.send(request, stream=True, follow_redirects=False)
        ) as response:
            if response.status_code != 200:
                return None
            raw = budget.response_bytes(response)
    if len(raw) > 1024 * 1024:
        return None
    metadata = json.loads(raw)
    if not isinstance(metadata, dict):
        return None
    created = parse_datetime(str(metadata.get("createdAt", "")))
    if (
        str(metadata.get("id", "")).casefold() != repo.casefold()
        or not re.fullmatch("[0-9a-f]{24}", str(metadata.get("_id")))
        or not created
        or not is_aware(created)
        or metadata.get("private") is not False
        or metadata.get("disabled") is True
    ):
        return None

    return raw, metadata, created


def _known_namespace(raw):
    brands = list(
        models.BrandAccount.objects.filter(
            role_id="official",
            account__data_source_id="x",
            account__normalized_identifier=str(raw.get("author_id") or ""),
        )
        .values_list("brand_id", flat=True)
        .distinct()[:2]
    )
    if len(brands) != 1:
        return None
    namespaces = list(
        models.BrandAccount.objects.filter(
            brand_id=brands[0], role_id="official", account__data_source_id="hf"
        ).values_list("account__external_identifier", flat=True)[:2]
    )
    return namespaces[0] if len(namespaces) == 1 else None


def _hub_json(budget, url, params=None):
    request = budget.public_request(url, params)
    with closing(
        budget.client.send(request, stream=True, follow_redirects=False)
    ) as response:
        if response.status_code == 200 and "next" not in response.links:
            return json.loads(budget.response_bytes(response))
    return None


def _find_publisher_model(slug, raw, budget):
    from core.release_publisher_recovery import _offering_key, _urls

    handle = (raw.get("author_handle") or "").casefold()

    if not handle or budget.remaining < 3:
        return None
    rows = _hub_json(
        budget, "https://huggingface.co/api/models", {"search": slug, "limit": 10}
    )
    if not isinstance(rows, list):
        return None
    candidates = set()
    for row in rows:
        model = row.get("id") if isinstance(row, dict) else None
        if (
            not isinstance(model, str)
            or _repo_from_hf_url("https://huggingface.co/" + model) != model
        ):
            continue
        _, name = model.split("/")
        if _offering_key(name) == _offering_key(slug):
            candidates.add(model)
    if len(candidates) != 1:
        return None
    repo = candidates.pop()
    namespace = repo.split("/")[0]
    if namespace.casefold() != handle and not any(
        (_repo_from_hf_url(url) or "").casefold() == repo.casefold()
        for url in _urls(raw)
    ):
        return None
    socials = _hub_json(
        budget, f"https://huggingface.co/api/organizations/{namespace}/socials"
    )
    if (
        not isinstance(socials, dict)
        or str(socials.get("org", "")).casefold() != namespace.casefold()
    ):
        return None
    accounts = socials.get("socialHandles")
    if (
        isinstance(accounts, dict)
        and str(accounts.get("twitter", "")).lstrip("@").casefold() == handle
    ):
        return repo
    return None


def lookup_release_hf_model(raw, product_name, profile, cited_repo, budget):
    """Use a cited repo, a known namespace, or a corroborated public search result."""
    if not budget.remaining:
        return None
    try:
        repo = cited_repo
        if repo is None:
            slug = re.sub(r"\s+", "-", product_name.strip())
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}", slug):
                return None
            namespace = profile or _known_namespace(raw)
            repo = (
                f"{namespace}/{slug}"
                if namespace
                else _find_publisher_model(slug, raw, budget)
            )
        return hf_model_metadata(repo, budget) if repo else None
    except (ValueError, TimeoutError, httpx.HTTPError):
        # Unavailable model metadata leaves the launch and publisher evidence usable.
        return None


def _model_mappings(product):
    return models.SourceSubjectMapping.objects.filter(
        purpose="catalog",
        source_id="hf",
        subject__product=product,
        identifier_scope__code="model",
        source_subject_kind="repository",
    )


@transaction.atomic
def bind_hf_model(product, payload, evidence_url):
    raw, metadata, created = payload
    repo = metadata["id"]
    namespace = repo.split("/")[0]
    product = models.Product.objects.select_for_update().get(
        pk=product.pk, brand_id=product.brand_id
    )
    if (
        product.product_type_code not in {"model-other", "model-llm"}
        or product.repo_id
        and product.repo_id.casefold() != repo.casefold()
        or product.created_at
        and product.created_at != created
        or product.publisher_account_id
        and (
            product.publisher_account.data_source_id != "hf"
            or product.publisher_account.normalized_identifier != namespace.casefold()
        )
        or _model_mappings(product).exclude(external_identifier__iexact=repo).exists()
        or models.Product.objects.filter(repo_id__iexact=repo)
        .exclude(pk=product.pk)
        .exists()
    ):
        return False
    existing = _model_mappings(product).filter(external_identifier__iexact=repo).first()
    if existing and (
        not existing.publisher_account_id
        or existing.publisher_account.normalized_identifier != namespace.casefold()
    ):
        return False
    account = bind_hf_publisher(product.brand_id, namespace, evidence_url)
    if account is None:
        return False
    url = "https://huggingface.co/" + repo
    endpoint = "https://huggingface.co/api/models/" + repo
    product.repo_id = metadata["id"]
    product.publisher_account = account
    product.created_at = created
    product.save(update_fields=["repo_id", "publisher_account", "created_at"])
    if existing:
        return True
    subject, _ = models.MeasurementSubject.objects.get_or_create(
        pk=resolve_subject_id("product", str(product.product_key)),
        defaults={"subject_kind": "product", "product": product},
    )
    archive = archive_document(raw, encoding="decoded-body-v1")
    review_catalog_mapping(
        source=models.DataSource.objects.get(pk="hf"),
        subject=subject,
        external_identifier=metadata["id"],
        source_subject_kind="repository",
        identifier_scope="model",
        publisher_account=account,
        role="dedicated_model",
        version_selector=None,
        evidence_url=url,
        reviewed_by="pulse-publisher-source-v1",
        identity_snapshot={},
        identifier_metadata={
            "release_endpoint": {
                "url": endpoint,
                "archive_sha256": archive.content_sha256,
                "selector": [],
            }
        },
    )
    return True


def discover_verified_hf_model(release, *, budget):
    product = models.Product.objects.get(product_key=release.product_key)
    if product.product_type_code not in {"model-other", "model-llm"}:
        return False
    proofs = models.EventDossierClaim.objects.filter(
        event_dossier_source__event_dossier_id=release.dossier_id,
        claim_kind_reference__code="release_context",
        extraction_version="pulse-publisher-source-v1",
        reported_product=product,
        scope_key__startswith="official-hf-model:",
    )
    scope_keys = proofs.order_by().values_list("scope_key", flat=True).distinct()[:2]
    repos = list(scope_keys)
    if len(repos) != 1:
        return False
    repo = repos[0].removeprefix("official-hf-model:")
    url = "https://huggingface.co/" + repo
    if _repo_from_hf_url(url) != repo:
        return False
    namespace = repo.split("/", 1)[0]
    mappings = _model_mappings(product)
    if product.repo_id and product.repo_id.casefold() != repo.casefold():
        return False
    if mappings.exists():
        # Existing native evidence also supplies missing publisher ownership on replay.
        existing = mappings.filter(
            external_identifier__iexact=repo,
            publisher_account__normalized_identifier=namespace.casefold(),
            publisher_account__data_source_id="hf",
        ).first()
        if existing and product.publisher_account_id == existing.publisher_account_id:
            bind_hf_publisher(product.brand_id, namespace, existing.evidence_url)
        return False
    accounts = models.BrandAccount.objects.filter(
        brand_id=product.brand_id, role_id="official"
    )

    def publisher_matches():
        return (
            accounts.filter(
                account__data_source_id="hf",
                account__normalized_identifier=namespace.casefold(),
            ).exists()
            or accounts.filter(
                account__data_source_id="x",
                account__normalized_handle=namespace.casefold(),
            ).exists()
        )

    if not publisher_matches():
        return False

    payload = hf_model_metadata(repo, budget)
    if payload is None:
        return False
    with transaction.atomic():
        lock_qualified_release(release.dossier_id, fingerprint=release.fingerprint)
        if (
            list(scope_keys.all()) != repos
            or not publisher_matches()
            or product.brand_id != release.brand_id
        ):
            return False
        return bind_hf_model(product, payload, url)
