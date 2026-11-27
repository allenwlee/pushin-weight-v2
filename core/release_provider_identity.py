"""Bind an explicitly publisher-linked HF model to the same catalog Product."""

import json
import re
from contextlib import closing

from django.db import IntegrityError, transaction
from django.utils.dateparse import parse_datetime
from django.utils.timezone import is_aware

from core import models
from core.account_identity import upsert_account
from core.collection_capture import archive_document
from core.collection_identity import review_catalog_mapping
from core.measurement_taxonomy import resolve_subject_id
from core.product_verification import _repo_from_hf_url
from core.release_chart_handoff import lock_qualified_release


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
    mappings = models.SourceSubjectMapping.objects.filter(
        purpose="catalog",
        source_id="hf",
        subject__product=product,
        identifier_scope__code="model",
        source_subject_kind="repository",
    )
    if mappings.exists() or (
        product.repo_id and product.repo_id.casefold() != repo.casefold()
    ):
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
                account__data_source_id="x", account__handle__iexact=namespace
            ).exists()
        )

    if not publisher_matches():
        return False

    endpoint = "https://huggingface.co/api/models/" + repo
    request = budget.public_request(endpoint)
    with closing(
        budget.client.send(request, stream=True, follow_redirects=False)
    ) as response:
        if response.status_code != 200:
            return False
        raw = budget.response_bytes(response)
    if len(raw) > 1024 * 1024:
        return False
    metadata = json.loads(raw)
    if not isinstance(metadata, dict):
        return False
    created = parse_datetime(str(metadata.get("createdAt", "")))
    if (
        str(metadata.get("id", "")).casefold() != repo.casefold()
        or not re.fullmatch("[0-9a-f]{24}", str(metadata.get("_id")))
        or not created
        or not is_aware(created)
        or metadata.get("private") is not False
        or metadata.get("disabled") is True
    ):
        return False

    with transaction.atomic():
        lock_qualified_release(release.dossier_id, fingerprint=release.fingerprint)
        product = models.Product.objects.select_for_update().get(pk=product.pk)
        if (
            list(scope_keys.all()) != repos
            or mappings.exists()
            or not publisher_matches()
            or product.brand_id != release.brand_id
            or product.repo_id
            and product.repo_id.casefold() != repo.casefold()
            or product.created_at
            and product.created_at != created
        ):
            return False
        account = (
            models.Account.objects.select_for_update()
            .filter(data_source_id="hf", normalized_identifier=namespace.casefold())
            .first()
        )
        if product.publisher_account_id and (
            not account or product.publisher_account_id != account.pk
        ):
            return False
        if not account:
            try:
                with transaction.atomic():
                    account = upsert_account(
                        source="hf", external_identifier=namespace, handle=namespace
                    )
            except IntegrityError:
                account = models.Account.objects.select_for_update().get(
                    data_source_id="hf", normalized_identifier=namespace.casefold()
                )
        if (
            models.Product.objects.filter(repo_id__iexact=repo)
            .exclude(pk=product.pk)
            .exists()
        ):
            return False
        if (
            models.BrandAccount.objects.filter(account=account)
            .exclude(brand_id=product.brand_id, role_id="official")
            .exists()
        ):
            return False
        models.BrandAccount.objects.get_or_create(
            brand_id=product.brand_id, account=account, defaults={"role_id": "official"}
        )
        product.repo_id = metadata["id"]
        product.publisher_account = account
        product.created_at = created
        product.save(update_fields=["repo_id", "publisher_account", "created_at"])
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
