"""Freeze a reviewed, creation-ordered cohort in the existing job definitions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from django.db import transaction

from core.benchmark_metric_store import aware_instant
from core.collection_capture import observation_object_documents
from core.collection_identity import qualified_ownership
from core.collection_jobs import register_job
from core.measurement_taxonomy import digest, require
from core.models import (
    Brand,
    BrandCompany,
    CollectionObservation,
    DataSource,
    Product,
    SourceSubjectMapping,
)
from scripts.benchmark_download_collector.history import date_chunks

HISTORY_SOURCES = ("github", "hf", "openrouter", "arena")
MODEL_TYPES = {"llm-model", "other-ai-model"}


def _provider_pins(mappings):
    return [
        {
            "mapping_id": str(m.pk),
            "mapping_hash": m.mapping_hash,
            "source": m.source_id,
            "source_subject_kind": m.source_subject_kind,
            "identifier_scope": m.identifier_scope_code,
            "native_identifier": m.external_identifier,
            "publisher_account_key": str(m.publisher_account_id)
            if m.publisher_account_id
            else None,
            "role": m.identity_snapshot.get("role"),
            "version_selector": m.identity_snapshot.get("version_selector"),
        }
        for m in mappings
    ]


def _creation_record(product, aliases, mappings, company_ids, cutoff):
    hf_dates = []
    for candidate in aliases:
        if (
            candidate.repo_id
            and candidate.created_at
            and candidate.private is False
            and candidate.hf_namespace
            and candidate.publisher_ownership
            and candidate.publisher_ownership.ownership_confirmed
            and candidate.publisher_ownership.company_id in company_ids
        ):
            native = aware_instant(candidate.created_at)
            if native <= cutoff:
                hf_dates.append((native, candidate.repo_id))
    if hf_dates:
        native, identifier = min(hf_dates)
        return {
            "at": native.isoformat(),
            "source": "hf",
            "basis": "repository_createdAt",
            "precision": "instant",
            "native_identifier": identifier,
        }
    for mapping in mappings:
        if mapping.source_id == "openrouter" and product.repo_id is None:
            observation = (
                CollectionObservation.objects.filter(
                    run__job__source_id="openrouter",
                    run__job__purpose="catalog",
                    source_identifier=mapping.external_identifier,
                    observation_kind="model_catalog",
                    status="ok",
                )
                .select_related("legacy_archive")
                .order_by("observed_at", "pk")
                .first()
            )
            listing = observation_object_documents(observation)[0] if observation else {}
            if (
                observation
                and type(listing.get("created")) is int
                and listing["created"] > 0
            ):
                native = datetime.fromtimestamp(listing["created"], UTC)
                if native <= cutoff:
                    return {
                        "at": native.isoformat(),
                        "source": "openrouter",
                        "basis": "listing_created",
                        "precision": "instant",
                        "native_identifier": mapping.external_identifier,
                        "observation_id": observation.pk,
                    }
        if (
            mapping.source_id == "github"
            and mapping.identity_snapshot.get("role") == "dedicated_model"
        ):
            observation = (
                CollectionObservation.objects.filter(
                    run__job__source_id="github",
                    run__job__purpose="catalog",
                    source_identifier=mapping.external_identifier,
                    observation_kind="repository",
                    status="ok",
                )
                .select_related("legacy_archive")
                .order_by("observed_at", "pk")
                .first()
            )
            listing = observation_object_documents(observation)[0] if observation else {}
            if observation and listing.get("created_at"):
                native = aware_instant(listing["created_at"])
                if native <= cutoff:
                    return {
                        "at": native.isoformat(),
                        "source": "github",
                        "basis": "dedicated_repository_created_at",
                        "precision": "instant",
                        "native_identifier": mapping.external_identifier,
                        "observation_id": observation.pk,
                    }
    return None


def build_cohort(*, brand_ids, cutoff, cap=100, qualification_policy=None):
    from core.model_kind_qualification import MODEL_KIND_POLICY, qualify_model_kind

    require(
        qualification_policy in {None, MODEL_KIND_POLICY},
        "unknown cohort qualification policy",
    )
    cutoff = aware_instant(cutoff)
    require(
        isinstance(brand_ids, list)
        and len(brand_ids) == 21
        and len(set(brand_ids)) == 21,
        "exactly 21 distinct tracked brands required",
    )
    require(
        not any(b.casefold() == "google" for b in brand_ids)
        and not BrandCompany.objects.filter(
            brand_id__in=brand_ids, company__nickname__iexact="google"
        ).exists(),
        "Google is outside this historical cohort",
    )
    require(
        set(Brand.objects.filter(pk__in=brand_ids).values_list("pk", flat=True))
        == set(brand_ids),
        "tracked brand is missing",
    )
    require(type(cap) is int and 1 <= cap <= 100, "model cap must be at most 100")
    products = list(
        Product.objects.filter(brand_id__in=brand_ids)
        .select_related("publisher_account", "product_type")
        .prefetch_related("publisher_account__companies")
        .order_by("product_key")
    )
    by_key = {p.product_key: p for p in products}
    mappings = list(
        SourceSubjectMapping.objects.filter(
            purpose="catalog",
            subject__subject_kind="product",
            subject__product_id__in=by_key,
        )
        .select_related("subject", "publisher_account", "identifier_scope")
        .order_by("source_id", "normalized_identifier", "pk")
    )
    per_product = {key: [] for key in by_key}
    aliases = {}
    for mapping in mappings:
        per_product[mapping.subject.product_id].append(mapping)
        if (
            mapping.source_id == "hf"
            and mapping.identity_snapshot.get("role") == "dedicated_model"
        ):
            aliases.setdefault(mapping.normalized_identifier.casefold(), set()).add(
                mapping.subject.product_id
            )
    groups = {key: [] for key in by_key}
    alias_conflicts = []
    for product in products:
        targets = (
            aliases.get(product.repo_id.casefold(), set()) if product.repo_id else set()
        )
        target = next(iter(targets)) if len(targets) == 1 else product.product_key
        if (
            len(targets) > 1
            or target not in by_key
            or by_key[target].brand_id != product.brand_id
        ):
            alias_conflicts.append(str(product.product_key))
            target = product.product_key
        groups[target].append(product)
    ownership = {
        brand: set(
            BrandCompany.objects.filter(brand_id=brand).values_list(
                "company_id", flat=True
            )
        )
        for brand in brand_ids
    }
    reports = {}
    for brand in brand_ids:
        ranked, unranked, unqualified = [], [], []
        for key, candidates in groups.items():
            product = by_key[key]
            if product.brand_id != brand or not candidates:
                continue
            qualification = (
                qualify_model_kind(product)
                if qualification_policy and product.product_type_code is None
                else None
            )
            if product.product_type_code not in MODEL_TYPES and qualification is None:
                unqualified.append(
                    {
                        "product_key": str(key),
                        "reason": "product_type_unqualified"
                        if product.product_type_code is None
                        else "outside_model_slots",
                    }
                )
                continue
            links = per_product[key]
            creation = _creation_record(
                product, candidates, links, ownership[brand], cutoff
            )
            if qualification:
                try:
                    created = aware_instant(qualification["registry_created_at"])
                    creation = (
                        {
                            "at": created.isoformat(),
                            "source": "hf",
                            "basis": "repository_createdAt",
                            "precision": "instant",
                            "native_identifier": qualification["repo_id"],
                            "observation_id": qualification["observation_id"],
                        }
                        if created <= cutoff
                        else None
                    )
                except (ValueError, TypeError):
                    creation = None
            if creation is None:
                unranked.append(
                    {"product_key": str(key), "reason": "creation_unqualified"}
                )
                continue
            ranked.append(
                {
                    "product_key": str(key),
                    "display_name": product.display_name,
                    "creation": creation,
                    "aliases": sorted(str(p.product_key) for p in candidates),
                    "provider_pins": _provider_pins(links),
                    "qualification": qualification or "confirmed_model",
                }
            )
        ranked.sort(key=lambda row: row["product_key"])
        ranked.sort(key=lambda row: aware_instant(row["creation"]["at"]), reverse=True)
        reports[brand] = {
            "models": ranked[:cap],
            "selected_count": min(len(ranked), cap),
            "dated_count": len(ranked),
            "unranked": unranked,
            "unranked_count": len(unranked),
            "unqualified": unqualified,
            "selection_complete": False,
            "inventory_basis": "observed_database_inventory",
            "alias_conflicts": alias_conflicts,
            "limitations": [
                "Deleted/private/unobserved models cannot be certified",
                "A family repository does not date a model version",
                "Arena appearance is not a creation date",
            ],
        }
    manifest = {
        "schema_version": 1,
        "cutoff": cutoff.isoformat(),
        "brand_ids": list(brand_ids),
        "cap_per_brand": cap,
        "brands": reports,
        "date_policy": "hf-first-party-earliest-or-api-only-or-dedicated-gh-v1",
    }
    if qualification_policy:
        manifest["qualification_policy"] = qualification_policy
    return manifest


@transaction.atomic
def freeze_model_history(
    *, brand_ids, cutoff, job_key_prefix, budgets, cap=100, qualification_policy=None
):
    manifest = build_cohort(
        brand_ids=brand_ids,
        cutoff=cutoff,
        cap=cap,
        qualification_policy=qualification_policy,
    )
    identity = digest(manifest)
    dates = [
        row["creation"]["at"]
        for brand in manifest["brands"].values()
        for row in brand["models"]
    ]
    global_start_at = min(dates) if dates else None
    jobs = []
    for brand in brand_ids:
        report = manifest["brands"][brand]
        for provider in HISTORY_SOURCES:
            source, _ = DataSource.objects.get_or_create(
                pk=provider,
                defaults={
                    "name": provider,
                    "source_type": "benchmark"
                    if provider == "arena"
                    else "model_adoption",
                    "adapter_key": provider + "-catalog-v1",
                },
            )
            scope = {
                "brand_id": brand,
                "cohort_hash": identity,
                "cutoff": manifest["cutoff"],
                "global_start_at": global_start_at,
                "brand_ids": manifest["brand_ids"],
                "cap_per_brand": cap,
                **report,
            }
            if qualification_policy:
                scope["qualification_policy"] = qualification_policy
            job = register_job(
                job_key=f"{job_key_prefix}:{brand}:{provider}",
                source=source,
                purpose="catalog",
                operation="model_history",
                mode="historical",
                definition={
                    "version": 1,
                    "scope": scope,
                    "schedule": {"kind": "manual", "driver": "manual"},
                    "budgets": budgets,
                },
            )
            jobs.append(job)
    return jobs


def cohort_report(jobs):
    brands = {}
    cohort_hashes = set()
    for job in jobs:
        scope = job.scope
        cohort_hashes.add(scope["cohort_hash"])
        brands.setdefault(scope["brand_id"], {**scope, "jobs": {}})["jobs"][
            job.source_id
        ] = str(job.pk)
    require(len(cohort_hashes) == 1, "mixed frozen cohorts")
    return {
        "cohort_hash": next(iter(cohort_hashes)),
        "brands": brands,
        "selected_models": sum(b["selected_count"] for b in brands.values()),
        "coverage_cells": sum(b["selected_count"] for b in brands.values())
        * len(HISTORY_SOURCES),
    }


def history_windows(start_at, cutoff, source, *, size=365):
    start, end = (
        aware_instant(start_at).astimezone(UTC).date(),
        aware_instant(cutoff).astimezone(UTC).date() - timedelta(days=1),
    )
    gaps = []
    if source == "openrouter" and start < datetime(2025, 1, 1, tzinfo=UTC).date():
        floor = datetime(2025, 1, 1, tzinfo=UTC).date()
        gaps.append(
            {
                "outcome": "outside_provider_coverage",
                "start_date": start.isoformat(),
                "end_date": min(end, floor - timedelta(days=1)).isoformat(),
                "reason": "provider_history_floor_2025_01_01",
            }
        )
        start = floor
    return (
        list(date_chunks(start.isoformat(), end.isoformat(), size=size))
        if start <= end
        else []
    ), gaps


def validate_model_pins(job):
    """Frozen ownership and identifiers cannot silently follow a later edit."""
    models = job.scope.get("models", [])
    require(
        isinstance(models, list) and len(models) <= 100,
        "bounded frozen model list required",
    )
    keys = [row["product_key"] for row in models]
    require(len(set(keys)) == len(keys), "duplicate frozen model")
    products = {
        str(p.product_key): p for p in Product.objects.filter(product_key__in=keys).select_related("product_type")
    }
    require(set(products) == set(keys), "frozen product no longer exists")
    for row in models:
        product = products[row["product_key"]]
        require(
            product.brand_id == job.scope["brand_id"]
            and (
                product.product_type_code in MODEL_TYPES
                or isinstance(row.get("qualification"), dict)
            ),
            "frozen product ownership/type changed",
        )
        if isinstance(row.get("qualification"), dict):
            from core.model_kind_qualification import validate_model_kind

            validate_model_kind(product, row["qualification"])
        for pin in row.get("provider_pins", []):
            mapping = SourceSubjectMapping.objects.select_related(
                "subject", "publisher_account"
            ).get(pk=pin["mapping_id"], purpose="catalog")
            require(
                mapping.mapping_hash == pin["mapping_hash"]
                and mapping.subject.product_id == product.product_key,
                "frozen mapping changed",
            )
            require(
                mapping.publisher_account is not None
                and qualified_ownership(mapping.publisher_account, mapping.subject),
                "publisher ownership changed",
            )
            if mapping.source_id == "github":
                require(
                    mapping.publisher_account.normalized_identifier
                    == str(mapping.identity_snapshot["owner_id"]),
                    "native publisher identity changed",
                )
    return products
