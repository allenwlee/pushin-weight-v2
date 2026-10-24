"""Typed current job classifications, with retained source wording."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from django.db import transaction
from django.db.models import Prefetch

from core import job_vocabulary_v1
from core.job_vocabulary_v1 import assignment_values, canonical_code
from core.models import (
    Currency,
    DefinitionVersion,
    JobEmploymentTypeAssignment,
    JobFunctionAssignment,
    JobListing,
    JobOrganizationAIRelationshipAssignment,
    JobRoleAIRelationshipAssignment,
    JobSeniorityAssignment,
    JobWorkplaceTypeAssignment,
    SalaryPeriod,
)

DIMENSIONS = {
    "job_function": (JobFunctionAssignment, "function_assignments"),
    "seniority": (JobSeniorityAssignment, "seniority_assignments"),
    "employment_type": (JobEmploymentTypeAssignment, "employment_assignments"),
    "workplace_type": (JobWorkplaceTypeAssignment, "workplace_assignments"),
    "organization_ai_relationship": (
        JobOrganizationAIRelationshipAssignment,
        "organization_ai_assignments",
    ),
    "role_ai_relationship": (JobRoleAIRelationshipAssignment, "role_ai_assignments"),
}
NORMALIZER_ID = uuid.uuid5(uuid.NAMESPACE_URL, "pushinweight:job-vocabulary:v1")
NORMALIZER_SOURCE_COMMIT = "20de98dbec531d6f34c791bad170a2349fa24818"
NORMALIZER_SOURCE_SHA256 = (
    "066612181d9027b903ea1f3edc85e87b27c3bd517a1baa977bd7793a3e89a914"
)


def register_job_normalizer(*, database="default"):
    """Register the actual frozen alias source, without a fictional observation."""
    source_hash = hashlib.sha256(
        Path(job_vocabulary_v1.__file__).read_bytes()
    ).hexdigest()
    if source_hash != NORMALIZER_SOURCE_SHA256:
        raise ValueError("Frozen job vocabulary source changed; register a new version")
    fields = {
        "definition_domain": "normalizer",
        "definition_key": "job_vocabulary",
        "reported_version_token": "v1",
        "identity_sha256": hashlib.sha256(
            b"pushinweight:job-vocabulary:v1"
        ).hexdigest(),
        "content_sha256": source_hash,
        "source_git_commit": NORMALIZER_SOURCE_COMMIT,
        "source_path": "core/job_vocabulary_v1.py",
        "provenance_state": "source_pinned",
    }
    version, _ = DefinitionVersion.objects.using(database).get_or_create(
        pk=NORMALIZER_ID,
        defaults=fields,
    )
    if any(getattr(version, key) != value for key, value in fields.items()):
        raise ValueError(
            "Frozen job vocabulary identity conflicts with its registered source"
        )
    return version


def compensation_references(record, *, database="default"):
    reported_currency = record.get("salary_currency")
    currency = (
        reported_currency.strip().upper()
        if isinstance(reported_currency, str)
        else None
    )
    period = canonical_code("salary_period", record.get("salary_period"))
    return {
        "salary_currency_reference_id": Currency.objects.using(database)
        .filter(pk=currency)
        .values_list("pk", flat=True)
        .first(),
        "salary_period_reference_id": SalaryPeriod.objects.using(database)
        .filter(code=period)
        .values_list("pk", flat=True)
        .first(),
    }


def write_job_classifications(listing, values, *, evidence=None, replace=False):
    """Replace an official current snapshot, or fill absent extracted dimensions.

    Source payloads and listing identity stay on their existing owners. A
    complete current snapshot may clear a dimension; missing extracted values
    never erase previously supported facts.
    """
    database = listing._state.db or "default"
    if evidence is not None and evidence.listing_id != listing.pk:
        raise ValueError("Classification evidence belongs to another job listing")
    fields = (
        "evidence_id",
        "category_id",
        "reported_value",
        "source_value_sha256",
        "normalizer_version_id",
        "resolution_state",
    )
    with transaction.atomic(using=database):
        JobListing.objects.using(database).select_for_update().only("pk").get(
            pk=listing.pk
        )
        for dimension, (model, relation) in DIMENSIONS.items():
            if dimension not in values:
                continue
            owner = model.objects.using(database).filter(job_listing=listing)
            rows = assignment_values(dimension, values[dimension])
            existing = set(owner.values_list(*fields))
            if not replace and (not rows or existing):
                continue
            if not rows and not existing:
                continue
            catalogue = model._meta.get_field("category").remote_field.model
            categories = dict(
                catalogue.objects.using(database).values_list("code", "pk")
            )
            assignments = []
            for row in rows:
                category_id = categories.get(row.category_code)
                if row.category_code is not None and category_id is None:
                    raise ValueError(
                        f"Missing registered {dimension} category: {row.category_code}"
                    )
                assignments.append(
                    model(
                        job_listing=listing,
                        evidence=evidence,
                        category_id=category_id,
                        reported_value=row.reported_value,
                        source_value_sha256=row.source_value_sha256,
                        normalizer_version_id=NORMALIZER_ID,
                        resolution_state="resolved"
                        if category_id is not None
                        else "unresolved",
                    )
                )
            if existing == {
                tuple(getattr(row, field) for field in fields) for row in assignments
            }:
                continue
            if replace:
                owner.delete()
            model.objects.using(database).bulk_create(assignments)
            getattr(listing, "_prefetched_objects_cache", {}).pop(relation, None)


def classification_prefetches(*, prefix="", dimensions=None):
    return [
        Prefetch(
            prefix + relation,
            queryset=model.objects.select_related("category").order_by("pk"),
        )
        for dimension, (model, relation) in DIMENSIONS.items()
        if dimensions is None or dimension in dimensions
    ]


def classification_text(listing, dimension):
    """Keep existing text response keys while reading their typed owner rows."""
    _model, relation = DIMENSIONS[dimension]
    values = [
        row.reported_value or row.category.code
        for row in getattr(listing, relation).all()
    ]
    return " · ".join(dict.fromkeys(values)) or None


def reported_compensation(listing, key):
    """Authorized source inspection only; ordinary readers use references."""
    from core.geolocation_evidence import source_evidence

    payload = source_evidence(listing).raw_payload
    if isinstance(payload, dict):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    for source in listing.evidence.all():
        payload = source_evidence(source).raw_evidence
        if not isinstance(payload, dict):
            continue
        record = payload.get("record", payload)
        value = record.get(key) if isinstance(record, dict) else None
        if isinstance(value, str) and value:
            return value
    return None
