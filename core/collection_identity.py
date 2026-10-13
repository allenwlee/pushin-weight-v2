"""Reviewed catalog crosswalks reuse native accounts and canonical subjects.

Candidates remain evidence until an operator admits their qualified relation.
Catalog mappings never become numeric mappings by changing their purpose.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from django.db import transaction
from django.utils import timezone

from core.benchmark_metric_identity import validate_evidence_url
from core.benchmark_metric_store import safe_payload
from core.measurement_taxonomy import digest, require
from core.models import (
    Account,
    BrandAccount,
    BrandCompany,
    CompanyAccount,
    DataSource,
    MeasurementSubject,
    SourceSubjectMapping,
)

RELATION_ROLES = {
    "dedicated_model",
    "family_repository",
    "implementation",
    "recipe",
    "agent_harness",
}


def qualified_ownership(account, subject):
    if subject.subject_kind == "account":
        return subject.account_id == account.pk
    if subject.subject_kind == "company":
        return CompanyAccount.objects.filter(
            account=account, company_id=subject.company_id, role_id="official"
        ).exists()
    if subject.subject_kind == "brand":
        brand_id = subject.brand_id
    elif subject.subject_kind == "product":
        brand_id = subject.product.brand_id
    else:
        brand_id = None
    if not brand_id:
        return False
    if BrandAccount.objects.filter(
        account=account, brand_id=brand_id, role_id="official"
    ).exists():
        return True
    companies = BrandCompany.objects.filter(brand_id=brand_id).values_list(
        "company_id", flat=True
    )
    return CompanyAccount.objects.filter(
        account=account, company_id__in=companies, role_id="official"
    ).exists()


@transaction.atomic
def review_catalog_mapping(
    *,
    source,
    subject,
    external_identifier,
    source_subject_kind,
    identifier_scope,
    publisher_account,
    role,
    version_selector,
    evidence_url,
    reviewed_by,
    identity_snapshot,
    identifier_metadata=None,
    allow_owner_transfer=False,
):
    # Serialize repeated reviews of an absent mapping through its existing subject.
    subject = MeasurementSubject.objects.select_for_update().get(pk=subject.pk)
    require(
        role in RELATION_ROLES,
        "dependency or unqualified relation cannot establish identity",
    )
    require(isinstance(reviewed_by, str) and reviewed_by.strip(), "reviewer required")
    validate_evidence_url(evidence_url)
    require(
        isinstance(external_identifier, str)
        and external_identifier.strip() == external_identifier
        and 0 < len(external_identifier) <= 256,
        "exact native identifier required",
    )
    require(
        source_subject_kind in {"repository", "model", "lab", "account"},
        "unsupported subject kind",
    )
    require(
        publisher_account is not None
        and qualified_ownership(publisher_account, subject),
        "reviewed publisher ownership required",
    )
    if role == "family_repository":
        require(
            isinstance(version_selector, str) and version_selector.strip(),
            "family version selector required",
        )
    safe_payload(identity_snapshot)
    safe_payload(identifier_metadata or {})
    native = (
        external_identifier.casefold() if source.pk == "hf" else external_identifier
    )
    snapshot = {
        **identity_snapshot,
        "role": role,
        "version_selector": version_selector,
        "publisher_account_key": str(publisher_account.pk),
        "subject_id": str(subject.pk),
    }
    # Labels and URLs can change without changing native repository identity.
    identity = {
        "source": source.pk,
        "kind": source_subject_kind,
        "scope": identifier_scope,
        "native_id": native,
        "subject": str(subject.pk),
        "publisher": str(publisher_account.pk),
        "role": role,
        "version_selector": version_selector,
    }
    key = {
        "purpose": "catalog",
        "source": source,
        "source_subject_kind": source_subject_kind,
        "identifier_scope": identifier_scope,
        "normalized_identifier": native,
        "subject": subject,
    }
    mapping = SourceSubjectMapping.objects.select_for_update().filter(**key).first()
    if mapping is None:
        mapping = SourceSubjectMapping(
            **key,
            external_identifier=external_identifier,
            publisher_account=publisher_account,
            identity_snapshot=snapshot,
            mapping_hash=digest(identity),
            evidence_url=evidence_url,
            reviewed_by=reviewed_by,
            identifier_metadata=identifier_metadata or {},
        )
    else:
        require(
            mapping.identity_snapshot.get("role") == role
            and mapping.identity_snapshot.get("version_selector") == version_selector,
            "relation changed; requires separate adjudication",
        )
        if mapping.publisher_account_id != publisher_account.pk:
            require(allow_owner_transfer, "ownership transfer requires explicit review")
            history = mapping.identifier_metadata.get("ownership_history", [])
            mapping.identifier_metadata = {
                **mapping.identifier_metadata,
                "ownership_history": [
                    *history,
                    {
                        "identity_snapshot": mapping.identity_snapshot,
                        "mapping_hash": mapping.mapping_hash,
                        "evidence_url": mapping.evidence_url,
                        "replaced_at": timezone.now().isoformat(),
                    },
                ],
            }
            mapping.publisher_account = publisher_account
            mapping.identity_snapshot = snapshot
            mapping.mapping_hash = digest(identity)
            mapping.evidence_url = evidence_url
            mapping.reviewed_by, mapping.reviewed_at = reviewed_by, timezone.now()
        additions = identifier_metadata or {}
        aliases = set(mapping.identifier_metadata.get("aliases", [])) | set(
            additions.get("aliases", [])
        )
        mapping.identifier_metadata = {
            **mapping.identifier_metadata,
            **additions,
            "aliases": sorted(aliases),
        }
    mapping.save()
    return mapping


def review_github_mapping(
    *,
    subject,
    repo,
    role,
    version_selector=None,
    evidence_url,
    reviewed_by,
    allow_owner_transfer=False,
):
    safe_payload(repo)
    require(
        isinstance(repo, dict) and type(repo.get("id")) is int and repo["id"] > 0,
        "native repository ID required",
    )
    require(repo.get("private") is False, "public repository evidence required")
    owner = repo.get("owner", {})
    require(
        type(owner.get("id")) is int and owner["id"] > 0, "native publisher ID required"
    )
    full_name = repo.get("full_name", "")
    require(
        isinstance(full_name, str)
        and full_name.count("/") == 1
        and full_name.split("/")[0].casefold()
        == str(owner.get("login", "")).casefold(),
        "native owner/full-name mismatch",
    )
    parsed = urlsplit(validate_evidence_url(evidence_url))
    require(
        parsed.hostname in {"github.com", "api.github.com"}
        and parsed.port in (None, 443),
        "GitHub evidence URL required",
    )
    account = Account.objects.filter(
        data_source_id="github", normalized_identifier=str(owner["id"])
    ).first()
    require(
        account is not None and qualified_ownership(account, subject),
        "reviewed GitHub publisher ownership required",
    )
    return review_catalog_mapping(
        source=DataSource.objects.get(pk="github"),
        subject=subject,
        external_identifier=str(repo["id"]),
        source_subject_kind="repository",
        identifier_scope="repository_id",
        publisher_account=account,
        role=role,
        version_selector=version_selector,
        evidence_url=evidence_url,
        reviewed_by=reviewed_by,
        allow_owner_transfer=allow_owner_transfer,
        identity_snapshot={
            "provider": "github",
            "repository_id": repo["id"],
            "owner_id": owner["id"],
            "observed_full_name": full_name,
        },
        identifier_metadata={"aliases": [full_name]},
    )
