"""Opt-in model-kind qualification from a pinned first-party HF registry capture."""

from core.measurement_taxonomy import digest, require
from core.models import BrandCompany, CollectionObservation

MODEL_KIND_POLICY = "hf-public-model-registry-v1"


def _qualification(product, observation):
    ownership = product.publisher_ownership
    require(
        product.type is None
        and product.hf_type == "model"
        and product.repo_id
        and product.publisher_account_id
        and product.publisher_account.data_source_id == "hf"
        and product.private is False
        and product.disabled is not True
        and ownership
        and ownership.ownership_confirmed
        and BrandCompany.objects.filter(
            brand_id=product.brand_id, company_id=ownership.company_id
        ).exists(),
        "public model publisher/brand identity is unqualified",
    )
    raw = observation.listing
    require(
        observation.run.source_id == "hf"
        and observation.run.purpose == "catalog"
        and observation.status == "ok"
        and observation.product_id == product.pk
        and observation.source_subject_kind == "repository"
        and observation.source_identifier.casefold() == product.repo_id.casefold()
        and (raw.get("id") or raw.get("modelId") or "").casefold()
        == product.repo_id.casefold()
        and raw.get("private") is False
        and raw.get("disabled") is not True
        and product.repo_id.split("/", 1)[0].casefold()
        == product.hf_namespace.casefold(),
        "first-party model evidence identity mismatch",
    )
    # These are the existing model-registry writers, not arbitrary HF datasets.
    require(
        observation.dimensions.get("kind") in {"creation_inventory", "hf_metadata"}
        or observation.groups.get("listing") == "ok"
        and observation.scope_run is not None
        and observation.scope_run.ownership.get("namespace", "").casefold()
        == product.hf_namespace.casefold(),
        "model-registry capture required",
    )
    return {
        "policy": MODEL_KIND_POLICY,
        "native_kind": "model",
        "subtype": "unknown",
        "observation_id": observation.pk,
        "payload_sha256": digest(raw),
        "evidence_identity_sha256": digest(
            [
                observation.dimensions,
                observation.groups,
                observation.source_metadata,
                str(observation.run_id),
                observation.source_identifier,
                observation.observed_at.isoformat(),
            ]
        ),
        "product_key": str(product.product_key),
        "repo_id": product.repo_id,
        "registry_created_at": raw.get("createdAt"),
        "brand_id": product.brand_id,
        "publisher_account_key": str(product.publisher_account_id),
        "publisher_identifier": product.publisher_account.normalized_identifier,
        "publisher_kind": product.publisher_account.account_kind,
        "company_id": ownership.company_id,
    }


def qualify_model_kind(product):
    observations = (
        CollectionObservation.objects.filter(
            product=product,
            run__source_id="hf",
            run__purpose="catalog",
            status="ok",
            source_subject_kind="repository",
        )
        .select_related("run", "scope_run")
        .order_by("pk")
    )
    for observation in observations.iterator():
        try:
            return _qualification(product, observation)
        except (ValueError, AttributeError):
            continue
    return None


def validate_model_kind(product, pin):
    require(pin.get("policy") == MODEL_KIND_POLICY, "unsupported model-kind policy")
    observation = CollectionObservation.objects.select_related("run", "scope_run").get(
        pk=pin["observation_id"]
    )
    require(
        _qualification(product, observation) == pin,
        "frozen model-kind evidence changed",
    )
    return pin
